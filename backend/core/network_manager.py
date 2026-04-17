from config import get_settings
from core.docker_manager import DockerManager, get_docker_manager

settings = get_settings()


class NetworkManager:
    def __init__(self, docker_manager: DockerManager | None = None) -> None:
        self._docker = docker_manager or get_docker_manager()

    def attach_internal_network(self, container_id: str) -> None:
        self._docker.attach_network(container_id, settings.internal_docker_network)

    def detach_internal_network(self, container_id: str) -> None:
        self._docker.detach_network(container_id, settings.internal_docker_network)
