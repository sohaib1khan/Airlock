"""Seed built-in container templates from Bastion_templates/*.airlock-template.yaml."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import yaml
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.schemas import ContainerTemplateImportRequest
from config import get_settings
from db.models import ContainerTemplate

logger = logging.getLogger(__name__)


def _stable_template_id(path: Path) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_OID, f"airlock:builtin_template:{path.resolve()}")


def seed_builtin_templates(db: Session) -> int:
    """Insert missing built-ins and refresh existing built-in rows from disk."""
    root = get_settings().builtin_templates_root()
    if root is None:
        logger.info("No built-in templates directory found; skipping seed")
        return 0

    inserted = 0
    updated = 0
    removed = 0
    seen_builtin_ids: set[str] = set()
    for path in sorted(root.rglob("*.airlock-template.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Skip invalid built-in template %s: %s", path, e)
            continue
        if not isinstance(raw, dict):
            logger.warning("Skip built-in template %s: root must be a mapping", path)
            continue

        try:
            req = ContainerTemplateImportRequest.model_validate(raw)
        except Exception as e:
            logger.warning("Skip built-in template %s: validation failed: %s", path, e)
            continue

        data = req.template
        tid = str(_stable_template_id(path))
        seen_builtin_ids.add(tid)
        existing = db.get(ContainerTemplate, tid)
        if existing is not None:
            # Keep built-ins in sync with the repo-shipped template files.
            # Skip templates created by users/admins.
            if existing.created_by_id is not None:
                continue
            changed = False
            if existing.name != data.name:
                existing.name = data.name
                changed = True
            if existing.description != data.description:
                existing.description = data.description
                changed = True
            if existing.docker_image != data.docker_image:
                existing.docker_image = data.docker_image
                changed = True
            if existing.tools != data.tools:
                existing.tools = data.tools
                changed = True
            if existing.persistent_volume != data.persistent_volume:
                existing.persistent_volume = data.persistent_volume
                changed = True
            if existing.volume_path != data.volume_path:
                existing.volume_path = data.volume_path
                changed = True
            if existing.env_vars != data.env_vars:
                existing.env_vars = data.env_vars
                changed = True
            if existing.resource_limits != data.resource_limits:
                existing.resource_limits = data.resource_limits
                changed = True
            if existing.max_runtime_minutes != data.max_runtime_minutes:
                existing.max_runtime_minutes = data.max_runtime_minutes
                changed = True
            if existing.workspace_home != data.workspace_home:
                existing.workspace_home = data.workspace_home
                changed = True
            if changed:
                updated += 1
                logger.info("Updated built-in template %s (%s)", data.name, path.name)
            continue

        tpl = ContainerTemplate(
            id=tid,
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
            created_by_id=None,
        )
        db.add(tpl)
        inserted += 1
        logger.info("Seeded built-in template %s (%s)", data.name, path.name)

    # Remove stale built-ins whose source files were deleted from Bastion_templates.
    for existing in db.query(ContainerTemplate).filter(ContainerTemplate.created_by_id.is_(None)).all():
        if existing.id not in seen_builtin_ids:
            logger.info("Removing stale built-in template %s (%s)", existing.name, existing.id)
            db.delete(existing)
            removed += 1

    if not inserted and not updated and not removed:
        return 0
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("Built-in template seed hit a DB conflict; another process may have seeded")
        return 0
    return inserted + updated + removed
