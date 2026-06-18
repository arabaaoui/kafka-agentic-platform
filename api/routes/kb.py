"""KB routes — browse incident knowledge cards."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from api.deps import get_db
from api.schemas import KBCardListResponse, KBCardSummary
from core.kb_writer import KBCardWriter
from core.models import SystemAudit

router = APIRouter(prefix="/v1/kb", tags=["knowledge-base"])

_KB_DIR = Path(os.getenv("KB_DIR", "/app/kb"))


def _parse_cards() -> list[KBCardSummary]:
    try:
        import yaml
    except ImportError:
        return []

    incidents_dir = _KB_DIR / "incidents"
    if not incidents_dir.is_dir():
        return []

    cards: list[KBCardSummary] = []
    for md_path in sorted(incidents_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            continue
        slug = str(fm.get("slug", ""))
        if not slug or " " in slug or "#" in slug:
            continue
        missions = list(fm.get("related_missions") or [""])
        cards.append(
            KBCardSummary(
                slug=slug,
                title=str(fm.get("title", slug)),
                theme=str(fm.get("theme", "")),
                severity=str(fm.get("severity", "info")),
                occurrences=int(fm.get("occurrences", 1)),
                last_mission=missions[-1] if missions else "",
            )
        )
    return cards


@router.get("/cards", response_model=KBCardListResponse)
async def list_cards(
    theme: str | None = None,
    tag: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> KBCardListResponse:
    """List all KB incident cards with optional theme/tag filter."""
    cards = _parse_cards()
    if theme:
        cards = [c for c in cards if theme.lower() in c.theme.lower()]
    if tag:
        pass  # tag filtering needs frontmatter tags — skipped for now (list is small)
    
    total = len(cards)
    paged_cards = cards[offset : offset + limit]
    
    return KBCardListResponse(items=paged_cards, total=total, limit=limit, offset=offset)


@router.get("/cards/{slug}", response_class=PlainTextResponse)
async def get_card(slug: str) -> str:
    """Return the full KB card content as Markdown."""
    card_path = _KB_DIR / "incidents" / f"{slug}.md"
    if not card_path.exists():
        raise HTTPException(status_code=404, detail=f"KB card not found: {slug!r}")
    return card_path.read_text(encoding="utf-8")


@router.delete("/cards/{slug}", status_code=204)
async def delete_card(
    slug: str,
    db=Depends(get_db),
) -> None:
    """Delete a KB card and log the action in the audit trail."""
    writer = KBCardWriter(kb_dir=_KB_DIR)
    if not writer.card_exists(slug):
        raise HTTPException(status_code=404, detail=f"KB card not found: {slug!r}")

    try:
        writer.delete_card(slug)

        # Log the action
        audit = SystemAudit(
            action="DELETE_KB_CARD",
            resource_type="KB_CARD",
            resource_id=slug,
            audit_metadata={"slug": slug},
            created_by="system",  # TODO: replace with actual user when auth is implemented
        )
        db.add(audit)
        await db.commit()

    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"KB card not found: {slug!r}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
