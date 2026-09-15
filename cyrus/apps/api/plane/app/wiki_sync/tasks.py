from __future__ import annotations

import logging
import os
from html import escape
from pathlib import Path
from typing import Any

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from plane.db.models import Page, Workspace
logger = logging.getLogger(__name__)


def _resolve_wiki_root() -> Path:
    configured = os.environ.get("CYRUS_WIKI_ROOT")
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR).parent.parent.parent / "wiki"


def _markdown_to_html(text: str) -> str:
    blocks = [f"<p>{escape(block).replace(chr(10), '<br/>')}</p>" for block in text.split("\n\n") if block.strip()]
    return "".join(blocks) or "<p></p>"


def _upsert_page(workspace: Workspace, path_parts: list[str], markdown_text: str) -> Page:
    parent = None
    for idx, part in enumerate(path_parts):
        page, _ = Page.objects.get_or_create(
            workspace=workspace,
            parent=parent,
            name=part,
            defaults={
                "owned_by": workspace.owner,
                "description_html": "<p></p>",
                "description_json": {},
                "access": Page.PUBLIC_ACCESS,
            },
        )
        if idx == len(path_parts) - 1:
            page.description_html = _markdown_to_html(markdown_text)
            page.description_json = {}
            page.owned_by = workspace.owner
            page.save(update_fields=["description_html", "description_json", "owned_by", "updated_at"])
        parent = page
    return parent


@shared_task
def archivist_wiki_loop(workspace_id: str | None = None) -> dict[str, Any]:
    workspaces = Workspace.objects.filter(deleted_at__isnull=True)
    if workspace_id:
        workspaces = workspaces.filter(id=workspace_id)
    stats = {"workspaces": 0, "pages_upserted": 0, "missing_roots": 0}
    wiki_root = _resolve_wiki_root()
    if not wiki_root.exists():
        stats["missing_roots"] = workspaces.count() or 1
        return stats
    for workspace in workspaces:
        stats["workspaces"] += 1
        for md_file in wiki_root.rglob("*.md"):
            parts = list(md_file.relative_to(wiki_root).parts)
            parts[-1] = md_file.stem
            _upsert_page(workspace, parts, md_file.read_text(encoding="utf-8"))
            stats["pages_upserted"] += 1
    logger.info("Archivist wiki loop completed", extra={"stats": stats, "timestamp": timezone.now().isoformat()})
    return stats
