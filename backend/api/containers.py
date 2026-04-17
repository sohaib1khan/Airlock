import uuid
from datetime import datetime, timezone
import json

import yaml
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import delete as sa_delete, select
from sqlalchemy.orm import Session

from api.deps import get_current_user_full_scope
from api.schemas import (
    ContainerTemplateCreateRequest,
    ContainerTemplateExportResponse,
    ContainerTemplateImportRequest,
    ContainerTemplateResponse,
    ContainerTemplateUpdateRequest,
)
from core.audit_log import log_security_event
from core.docker_manager import DockerManagerError, get_docker_manager
from db.database import get_db
from db.models import ContainerTemplate, SessionStatus, User, WorkspaceSession

router = APIRouter(prefix="/containers", tags=["containers"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _template_to_response(tpl: ContainerTemplate) -> ContainerTemplateResponse:
    return ContainerTemplateResponse(
        id=tpl.id,
        name=tpl.name,
        description=tpl.description,
        docker_image=tpl.docker_image,
        tools=list(tpl.tools or []),
        persistent_volume=tpl.persistent_volume,
        volume_path=tpl.volume_path,
        env_vars=dict(tpl.env_vars or {}),
        resource_limits=dict(tpl.resource_limits or {}),
        max_runtime_minutes=tpl.max_runtime_minutes,
        workspace_home=tpl.workspace_home,
        created_at=tpl.created_at.isoformat(),
        is_builtin=tpl.created_by_id is None,
    )


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _template_to_create_payload(tpl: ContainerTemplate) -> ContainerTemplateCreateRequest:
    return ContainerTemplateCreateRequest(
        name=tpl.name,
        description=tpl.description,
        docker_image=tpl.docker_image,
        tools=list(tpl.tools or []),
        persistent_volume=tpl.persistent_volume,
        volume_path=tpl.volume_path,
        env_vars=dict(tpl.env_vars or {}),
        resource_limits=dict(tpl.resource_limits or {}),
        max_runtime_minutes=tpl.max_runtime_minutes,
        workspace_home=tpl.workspace_home,
    )


@router.get("", response_model=list[ContainerTemplateResponse])
def list_templates(
    _request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user_full_scope),
) -> list[ContainerTemplateResponse]:
    stmt = select(ContainerTemplate).order_by(ContainerTemplate.created_at.desc())
    templates = db.execute(stmt).scalars().all()
    return [_template_to_response(t) for t in templates]


@router.get("/{template_id}", response_model=ContainerTemplateResponse)
def get_template(
    template_id: str,
    _request: Request,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user_full_scope),
) -> ContainerTemplateResponse:
    tpl = db.get(ContainerTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return _template_to_response(tpl)


@router.get("/{template_id}/export", response_model=ContainerTemplateExportResponse)
def export_template(
    template_id: str,
    _request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> ContainerTemplateExportResponse:
    _require_admin(user)
    tpl = db.get(ContainerTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return ContainerTemplateExportResponse(
        format_version="airlock-template-v1",
        exported_at=datetime.now(timezone.utc).isoformat(),
        template=_template_to_create_payload(tpl),
    )


@router.get("/{template_id}/export.yaml", response_class=PlainTextResponse)
def export_template_yaml(
    template_id: str,
    _request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> PlainTextResponse:
    _require_admin(user)
    tpl = db.get(ContainerTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    payload = {
        "format_version": "airlock-template-v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "template": _template_to_create_payload(tpl).model_dump(),
    }
    dumped = yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)
    filename = f"{tpl.name or 'template'}.airlock-template.yaml".replace(" ", "_")
    return PlainTextResponse(
        content=dumped,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("", response_model=ContainerTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    request: Request,
    body: ContainerTemplateCreateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> ContainerTemplateResponse:
    _require_admin(user)
    tpl = ContainerTemplate(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        docker_image=body.docker_image,
        tools=body.tools,
        persistent_volume=body.persistent_volume,
        volume_path=body.volume_path,
        env_vars=body.env_vars,
        resource_limits=body.resource_limits,
        max_runtime_minutes=body.max_runtime_minutes,
        workspace_home=body.workspace_home,
        created_by_id=user.id,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    log_security_event(
        "container_template_create",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _template_to_response(tpl)


@router.put("/{template_id}", response_model=ContainerTemplateResponse)
def update_template(
    template_id: str,
    request: Request,
    body: ContainerTemplateUpdateRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> ContainerTemplateResponse:
    _require_admin(user)
    tpl = db.get(ContainerTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")

    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(tpl, key, value)
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    log_security_event(
        "container_template_update",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _template_to_response(tpl)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> None:
    _require_admin(user)
    tpl = db.get(ContainerTemplate, template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if tpl.created_by_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Built-in templates cannot be deleted",
        )
    active_statuses = (SessionStatus.STARTING, SessionStatus.RUNNING, SessionStatus.PAUSED)
    active_session = db.execute(
        select(WorkspaceSession).where(
            WorkspaceSession.template_id == template_id,
            WorkspaceSession.status.in_(active_statuses),
        )
    ).scalars().first()
    if active_session is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template has active sessions and cannot be deleted",
        )
    # Purge stopped/error sessions so the DB RESTRICT FK doesn't block the delete.
    db.execute(
        sa_delete(WorkspaceSession).where(WorkspaceSession.template_id == template_id)
    )
    db.delete(tpl)
    db.commit()
    log_security_event(
        "container_template_delete",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )


@router.post("/actions/test-pull", status_code=status.HTTP_200_OK)
def test_pull_image(
    request: Request,
    body: ContainerTemplateCreateRequest,
    user: User = Depends(get_current_user_full_scope),
) -> dict[str, str]:
    _require_admin(user)
    docker_manager = get_docker_manager()
    try:
        docker_manager.pull_image(body.docker_image)
    except DockerManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    log_security_event(
        "container_template_test_pull",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return {"message": "Image pulled successfully"}


@router.get("/actions/local-images", response_model=list[str], status_code=status.HTTP_200_OK)
def list_local_images(
    _request: Request,
    user: User = Depends(get_current_user_full_scope),
) -> list[str]:
    _require_admin(user)
    docker_manager = get_docker_manager()
    try:
        return docker_manager.list_local_images()
    except DockerManagerError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@router.post("/actions/import", response_model=ContainerTemplateResponse, status_code=status.HTTP_201_CREATED)
def import_template(
    request: Request,
    body: ContainerTemplateImportRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> ContainerTemplateResponse:
    _require_admin(user)
    data = body.template
    existing = db.execute(select(ContainerTemplate).where(ContainerTemplate.name == data.name)).scalar_one_or_none()
    if existing is not None and not body.overwrite_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template name already exists; enable overwrite to update it",
        )
    if existing is not None and body.overwrite_existing:
        existing.description = data.description
        existing.docker_image = data.docker_image
        existing.tools = data.tools
        existing.persistent_volume = data.persistent_volume
        existing.volume_path = data.volume_path
        existing.env_vars = data.env_vars
        existing.resource_limits = data.resource_limits
        existing.max_runtime_minutes = data.max_runtime_minutes
        existing.workspace_home = data.workspace_home
        db.add(existing)
        db.commit()
        db.refresh(existing)
        log_security_event(
            "container_template_import_update",
            _ip(request),
            "SUCCESS",
            trace_id=getattr(request.state, "trace_id", None),
            user_id=str(user.id),
        )
        return _template_to_response(existing)

    tpl = ContainerTemplate(
        id=str(uuid.uuid4()),
        name=data.name,
        description=data.description,
        docker_image=data.docker_image,
        tools=data.tools,
        persistent_volume=data.persistent_volume,
        volume_path=data.volume_path,
        env_vars=data.env_vars,
        resource_limits=data.resource_limits,
        max_runtime_minutes=data.max_runtime_minutes,
        workspace_home=data.workspace_home,
        created_by_id=user.id,
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    log_security_event(
        "container_template_import_create",
        _ip(request),
        "SUCCESS",
        trace_id=getattr(request.state, "trace_id", None),
        user_id=str(user.id),
    )
    return _template_to_response(tpl)


@router.post("/actions/import-file", response_model=ContainerTemplateResponse, status_code=status.HTTP_201_CREATED)
async def import_template_file(
    request: Request,
    file: UploadFile = File(...),
    overwrite_existing: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_full_scope),
) -> ContainerTemplateResponse:
    _require_admin(user)
    raw_bytes = await file.read()
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template file must be UTF-8 text")

    parsed = None
    filename = (file.filename or "").lower()
    parse_errors = []

    if filename.endswith((".yaml", ".yml")):
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            parse_errors.append(f"yaml parse failed: {exc}")
    elif filename.endswith(".json"):
        try:
            parsed = json.loads(text)
        except Exception as exc:
            parse_errors.append(f"json parse failed: {exc}")
    else:
        try:
            parsed = yaml.safe_load(text)
        except Exception as exc:
            parse_errors.append(f"yaml parse failed: {exc}")
        if parsed is None:
            try:
                parsed = json.loads(text)
            except Exception as exc:
                parse_errors.append(f"json parse failed: {exc}")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Template file content is invalid")

    try:
        body = ContainerTemplateImportRequest.model_validate(
            {
                **parsed,
                "overwrite_existing": overwrite_existing,
            }
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Template file format is invalid for Airlock import",
        )

    return import_template(
        request=request,
        body=body,
        db=db,
        user=user,
    )
