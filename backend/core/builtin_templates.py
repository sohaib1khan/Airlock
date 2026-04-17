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
    """Insert missing built-in templates. Returns count of rows inserted."""
    root = get_settings().builtin_templates_root()
    if root is None:
        logger.info("No built-in templates directory found; skipping seed")
        return 0

    inserted = 0
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
        existing = db.get(ContainerTemplate, tid)
        if existing is not None:
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

    if not inserted:
        return 0
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        logger.warning("Built-in template seed hit a DB conflict; another process may have seeded")
        return 0
    return inserted
