from dataclasses import dataclass
import io
import posixpath
import tarfile
from typing import Any

import docker
from docker.errors import DockerException, ImageNotFound, NotFound
from docker.utils import parse_repository_tag

from config import get_settings

settings = get_settings()


class DockerManagerError(RuntimeError):
    pass


@dataclass
class ContainerRuntimeInfo:
    container_id: str
    ip_address: str | None


def _docker_archive_member_relpath(member_name: str, listed_path: str, *, member_is_dir: bool) -> str | None:
    """Map get_archive member names to paths relative to the listed directory.

    Docker prefixes tarball members with the archived directory basename (e.g. ``kuser/foo``
    when listing ``/home/kuser``). Strip that so the UI shows ``foo``, not a nested ``kuser``.
    """
    rel = member_name.lstrip("./").strip("/")
    if not rel:
        return None
    base = posixpath.basename(listed_path.rstrip("/"))
    if not base:
        return rel
    if rel == base:
        return None if member_is_dir else rel
    prefix = f"{base}/"
    if rel.startswith(prefix):
        inner = rel[len(prefix) :].strip("/")
        return inner if inner else None
    return rel


class DockerManager:
    def __init__(self) -> None:
        self._client = docker.DockerClient(base_url=f"unix://{settings.docker_socket}")

    @staticmethod
    def _canonical_image_ref(image: str) -> str:
        repo, tag = parse_repository_tag(image)
        if not tag:
            return f"{repo}:latest"
        return image

    def _ensure_workspace_image(self, image: str) -> str:
        """Resolve tag (default :latest), then ensure image exists locally or pull."""
        ref = self._canonical_image_ref(image)
        try:
            self._client.images.get(ref)
            return ref
        except ImageNotFound:
            pass
        try:
            self._client.images.pull(ref)
            return ref
        except DockerException as exc:
            raise DockerManagerError(
                f"Workspace image '{ref}' is not available locally and could not be pulled. "
                f"Build or tag it on this Docker host (see Bastion_templates README), e.g. "
                f"`docker tag myimage:debug {ref}`. Docker: {exc}"
            ) from exc

    def ping(self) -> bool:
        try:
            self._client.ping()
            return True
        except DockerException:
            return False

    def pull_image(self, image: str) -> None:
        try:
            self._client.images.pull(image)
        except DockerException as exc:
            raise DockerManagerError(f"Failed to pull image '{image}'") from exc

    def list_local_images(self) -> list[str]:
        """List local repo:tag image refs available on this Docker host."""
        try:
            images = self._client.images.list()
        except DockerException as exc:
            raise DockerManagerError(f"Failed to list local images: {exc}") from exc
        refs: set[str] = set()
        for image in images:
            for tag in image.tags:
                # Ignore dangling/untagged entries.
                if tag and "<none>" not in tag:
                    refs.add(tag)
        return sorted(refs)

    def _ensure_named_volume(self, name: str) -> None:
        try:
            self._client.volumes.get(name)
        except NotFound:
            try:
                self._client.volumes.create(name=name, driver="local")
            except DockerException as exc:
                raise DockerManagerError(f"Failed to create volume '{name}': {exc}") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to inspect volume '{name}': {exc}") from exc

    def start_workspace_container(
        self,
        *,
        image: str,
        name: str,
        env: dict[str, str] | None = None,
        cpu_limit: float | None = None,
        memory_mb: int | None = None,
        persistent_volume: bool = False,
        named_volume_name: str | None = None,
        volume_mount_path: str | None = None,
    ) -> ContainerRuntimeInfo:
        env = env or {}
        mounts: list[Any] = []
        if persistent_volume:
            if not named_volume_name or not volume_mount_path:
                raise DockerManagerError("persistent_volume requires named_volume_name and volume_mount_path")
            self._ensure_named_volume(named_volume_name)
            mounts.append(
                docker.types.Mount(
                    target=volume_mount_path,
                    source=named_volume_name,
                    type="volume",
                    read_only=False,
                )
            )
        try:
            resolved_image = self._ensure_workspace_image(image)
            # Connect to INTERNAL_DOCKER_NETWORK at create time (session/start runs only after
            # pre-connect MFA). Starting with network_mode="none" breaks images whose entrypoints
            # need DNS/hostname (e.g. TigerVNC) before a late attach.
            # Do not cap_drop=ALL: many workspace images use runuser/su in entrypoints, which fails.
            run_kw: dict[str, Any] = dict(
                image=resolved_image,
                name=name,
                detach=True,
                environment=env,
                network=settings.internal_docker_network,
                cpu_quota=int((cpu_limit or settings.container_cpu_limit) * 100000),
                mem_limit=f"{memory_mb or settings.container_memory_limit_mb}m",
            )
            if mounts:
                run_kw["mounts"] = mounts
            container = self._client.containers.run(**run_kw)
            return ContainerRuntimeInfo(container_id=container.id, ip_address=None)
        except DockerException as exc:
            raise DockerManagerError(f"Failed to start workspace container: {exc}") from exc

    def stop_container(self, container_id: str) -> None:
        try:
            container = self._client.containers.get(container_id)
            container.stop(timeout=10)
            container.remove(v=True, force=True)
        except NotFound:
            return
        except DockerException as exc:
            raise DockerManagerError(f"Failed to stop container {container_id}") from exc

    def pause_container(self, container_id: str) -> None:
        try:
            container = self._client.containers.get(container_id)
            container.pause()
        except NotFound as exc:
            raise DockerManagerError(f"Container {container_id} not found") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to pause container {container_id}") from exc

    def resume_container(self, container_id: str) -> None:
        try:
            container = self._client.containers.get(container_id)
            container.unpause()
        except NotFound as exc:
            raise DockerManagerError(f"Container {container_id} not found") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to resume container {container_id}") from exc

    def attach_network(self, container_id: str, network_name: str) -> None:
        try:
            network = self._client.networks.get(network_name)
            container = self._client.containers.get(container_id)
            network.connect(container)
        except DockerException as exc:
            raise DockerManagerError(
                f"Failed to attach network '{network_name}' to {container_id}"
            ) from exc

    def detach_network(self, container_id: str, network_name: str) -> None:
        try:
            network = self._client.networks.get(network_name)
            container = self._client.containers.get(container_id)
            network.disconnect(container, force=True)
        except NotFound:
            return
        except DockerException as exc:
            raise DockerManagerError(
                f"Failed to detach network '{network_name}' from {container_id}"
            ) from exc

    def get_container_network_ip(self, container_id: str, network_name: str) -> str | None:
        def _endpoint_ip(ep: dict) -> str | None:
            v4 = (ep.get("IPAddress") or "").strip()
            if v4:
                return v4
            v6 = (ep.get("GlobalIPv6Address") or "").strip()
            if v6:
                return f"[{v6}]" if ":" in v6 else v6
            return None

        try:
            container = self._client.containers.get(container_id)
            container.reload()
            nets = container.attrs.get("NetworkSettings", {}).get("Networks") or {}
            ep = nets.get(network_name)
            if ep is not None:
                got = _endpoint_ip(ep)
                if got:
                    return got
            want_id: str | None = None
            try:
                want_id = self._client.networks.get(network_name).id
            except DockerException:
                want_id = None
            if want_id:
                for cfg in nets.values():
                    if cfg.get("NetworkID") == want_id:
                        got = _endpoint_ip(cfg)
                        if got:
                            return got
            for cfg in nets.values():
                got = _endpoint_ip(cfg)
                if got:
                    return got
            return None
        except NotFound:
            return None
        except DockerException as exc:
            raise DockerManagerError(f"Failed to inspect container {container_id}") from exc

    def _get_container(self, container_id: str):
        try:
            return self._client.containers.get(container_id)
        except NotFound as exc:
            raise DockerManagerError(f"Container {container_id} not found") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to access container {container_id}") from exc

    def list_files(
        self, container_id: str, path: str, *, workspace_root: str = "/home/kuser"
    ) -> tuple[str, list[dict]]:
        container = self._get_container(container_id)
        root = posixpath.normpath((workspace_root or "/home/kuser").strip() or "/home/kuser")
        normalized = posixpath.normpath(path or root)
        if not normalized.startswith("/"):
            normalized = posixpath.normpath(f"{root}/{normalized}")
        if not (normalized == root or normalized.startswith(f"{root}/")):
            raise DockerManagerError("path_outside_workspace")
        try:
            stream, _ = container.get_archive(normalized)
            tar_bytes = b"".join(stream)
        except NotFound as exc:
            raise DockerManagerError("path_not_found") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to list files in container at {normalized}") from exc

        items_map: dict[str, dict] = {}
        saw_nested_entry = False
        try:
            with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
                for member in tar.getmembers():
                    rel = _docker_archive_member_relpath(
                        member.name, normalized, member_is_dir=member.isdir()
                    )
                    if not rel:
                        continue
                    first = rel.split("/", 1)[0]
                    existing = items_map.get(first)
                    if existing and existing["type"] == "directory":
                        continue
                    if "/" in rel:
                        saw_nested_entry = True
                        items_map[first] = {"name": first, "type": "directory", "size": 0}
                    else:
                        item_type = "directory" if member.isdir() else "file"
                        size = 0 if item_type == "directory" else int(member.size)
                        items_map[first] = {"name": first, "type": item_type, "size": size}
        except tarfile.TarError as exc:
            raise DockerManagerError("Invalid archive returned by container") from exc

        # If archive resolves to a single file at root, caller asked for a non-directory.
        if not saw_nested_entry and len(items_map) == 1:
            only = next(iter(items_map.values()))
            if only["type"] == "file":
                raise DockerManagerError("not_a_directory")
        items = sorted(items_map.values(), key=lambda x: (x["type"] != "directory", x["name"].lower()))
        return normalized, items

    def upload_file_bytes(
        self,
        container_id: str,
        destination_dir: str,
        filename: str,
        content: bytes,
    ) -> str:
        container = self._get_container(container_id)
        safe_name = posixpath.basename(filename) or "upload.bin"
        dest = destination_dir.rstrip("/") or "/"
        archive_buffer = io.BytesIO()
        with tarfile.open(fileobj=archive_buffer, mode="w") as tar:
            info = tarfile.TarInfo(name=safe_name)
            info.size = len(content)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(content))
        archive_buffer.seek(0)
        try:
            ok = container.put_archive(dest, archive_buffer.getvalue())
        except NotFound as exc:
            raise DockerManagerError("destination_not_found") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to upload file to {dest}") from exc
        if not ok:
            raise DockerManagerError("Container rejected uploaded archive")
        return posixpath.join(dest, safe_name)

    def download_file_bytes(self, container_id: str, path: str) -> tuple[str, bytes]:
        container = self._get_container(container_id)
        try:
            stream, _ = container.get_archive(path)
        except NotFound as exc:
            raise DockerManagerError("file_not_found") from exc
        except DockerException as exc:
            raise DockerManagerError(f"Failed to read file {path}") from exc
        tar_bytes = b"".join(stream)
        try:
            with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
                members = [m for m in tar.getmembers() if m.isfile()]
                if not members:
                    raise DockerManagerError("Requested path is not a file")
                member = members[0]
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise DockerManagerError("Could not extract downloaded file")
                return posixpath.basename(member.name), extracted.read()
        except tarfile.TarError as exc:
            raise DockerManagerError("Invalid archive returned by container") from exc

    @staticmethod
    def _cpu_percent_from_docker_stats(s: dict[str, Any]) -> float:
        """Approximate container CPU % using Docker stats (same idea as `docker stats`)."""
        try:
            cpu_stats = s.get("cpu_stats") or {}
            precpu = s.get("precpu_stats") or {}
            cpu_usage = cpu_stats.get("cpu_usage") or {}
            pre_usage = precpu.get("cpu_usage") or {}
            total = cpu_usage.get("total_usage")
            pre_total = pre_usage.get("total_usage")
            sys_total = cpu_stats.get("system_cpu_usage")
            pre_sys = precpu.get("system_cpu_usage")
            if None in (total, pre_total, sys_total, pre_sys):
                return 0.0
            cpu_delta = float(total) - float(pre_total)
            sys_delta = float(sys_total) - float(pre_sys)
            if sys_delta <= 0 or cpu_delta < 0:
                return 0.0
            percpu = cpu_usage.get("percpu_usage") or []
            ncpu = len(percpu) if percpu else int(cpu_stats.get("online_cpus") or 1)
            return (cpu_delta / sys_delta) * float(ncpu) * 100.0
        except (TypeError, ValueError, ZeroDivisionError):
            return 0.0

    def get_container_resource_snapshot(self, container_id: str) -> dict[str, Any]:
        """One-shot CPU and memory snapshot for a running container."""
        container = self._get_container(container_id)
        try:
            s = container.stats(stream=False)
        except DockerException as exc:
            raise DockerManagerError(f"Failed to read container stats: {exc}") from exc
        mem = s.get("memory_stats") or {}
        usage = mem.get("usage")
        limit = mem.get("limit") or 0
        cpu_percent = self._cpu_percent_from_docker_stats(s)
        mem_pct: float | None = None
        try:
            if limit and usage is not None:
                mem_pct = min(100.0, (float(usage) / float(limit)) * 100.0)
        except (TypeError, ValueError, ZeroDivisionError):
            mem_pct = None
        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_bytes": int(usage) if usage is not None else None,
            "memory_limit_bytes": int(limit) if limit else None,
            "memory_percent": round(mem_pct, 2) if mem_pct is not None else None,
            "container_status": container.status,
        }


docker_manager_singleton: DockerManager | None = None


def get_docker_manager() -> DockerManager:
    global docker_manager_singleton
    if docker_manager_singleton is None:
        docker_manager_singleton = DockerManager()
    return docker_manager_singleton
