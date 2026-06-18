"""KB card writer — creates and updates incident cards in kb/incidents/.

All writes are atomic (write to .tmp then os.replace) to avoid corrupt card
reads by a concurrent KBIndex reload.
Slug validation reuses SLUG_PATTERN from kafka-agent-toolkit (same guard
as core/mission.py — prevents YAML comment leakage, spec 003 SC-005).
"""

from __future__ import annotations

import os
import re
import time
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

try:
    from kafka_agent_toolkit.kb.schemas import SLUG_PATTERN, validate_slug, MAX_LEN_KB_SLUG
except ImportError:
    SLUG_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    MAX_LEN_KB_SLUG = 64
    def validate_slug(v: str, **kwargs: Any) -> str:
        return v.split("#")[0].strip()

if TYPE_CHECKING:
    pass

_INDEX_HEADER = "# Knowledge Index — Régénéré le {date}\n\n"

def _validate_slug(slug: str) -> str:
    """Wrapper to use toolkit validation logic."""
    return validate_slug(slug, max_len=MAX_LEN_KB_SLUG)


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


class KBCardWriter:
    """Create, update, and index KB cards in kb/incidents/."""

    def __init__(self, kb_dir: str | Path = "kb") -> None:
        self._kb_dir = Path(kb_dir)
        self._incidents_dir = self._kb_dir / "incidents"
        self._index_path = self._kb_dir / "INDEX.md"

    def card_exists(self, slug: str) -> bool:
        slug = _validate_slug(slug)
        return (self._incidents_dir / f"{slug}.md").exists()

    def create_card(
        self,
        *,
        slug: str,
        title: str,
        theme: str,
        tags: list[str],
        severity: str,
        symptoms: list[str],
        root_cause: str,
        body: str,
        mission_id: str,
        env: str,
    ) -> Path:
        """Write a new KB card. Raises ValueError if slug already exists."""
        slug = _validate_slug(slug)
        card_path = self._incidents_dir / f"{slug}.md"
        if card_path.exists():
            raise ValueError(
                f"KB card {slug!r} already exists — use update_card() instead."
            )
        self._incidents_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        content = self._render_card(
            slug=slug,
            title=title,
            theme=theme,
            tags=tags,
            severity=severity,
            environments_seen=[env.upper()],
            first_seen=today,
            last_seen=today,
            occurrences=1,
            symptoms=symptoms,
            root_cause=root_cause,
            related_missions=[mission_id],
            body=body,
        )
        _atomic_write(card_path, content)
        return card_path

    def update_card(self, slug: str, mission_id: str) -> Path:
        """Increment occurrences, update last_seen, append mission_id."""
        slug = _validate_slug(slug)
        card_path = self._incidents_dir / f"{slug}.md"
        if not card_path.exists():
            raise FileNotFoundError(f"KB card not found: {slug!r}")

        text = card_path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            raise ValueError(f"Card {slug!r} has no YAML frontmatter")

        if yaml is None:
            raise RuntimeError("pyyaml required for update_card()")

        parts = text.split("---", 2)
        if len(parts) < 3:
            raise ValueError(f"Card {slug!r} has malformed frontmatter")

        fm = yaml.safe_load(parts[1]) or {}
        fm["occurrences"] = int(fm.get("occurrences", 1)) + 1
        fm["last_seen"] = date.today().isoformat()
        missions = list(fm.get("related_missions") or [])
        if mission_id not in missions:
            missions.append(mission_id)
        fm["related_missions"] = missions

        new_fm = yaml.dump(fm, allow_unicode=True, sort_keys=False, default_flow_style=False)
        new_content = f"---\n{new_fm}---\n{parts[2]}"
        _atomic_write(card_path, new_content)
        return card_path

    def regenerate_index(self) -> int:
        """Scan incidents dir, regenerate INDEX.md. Returns card count."""
        if yaml is None:
            raise RuntimeError("pyyaml required for regenerate_index()")

        cards: list[dict] = []
        for md_path in sorted(self._incidents_dir.glob("*.md")):
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
            if " " in slug or "#" in slug or not slug:
                continue
            cards.append({
                "slug": slug,
                "title": str(fm.get("title", slug)),
                "theme": str(fm.get("theme", "")),
                "severity": str(fm.get("severity", "")),
                "occurrences": int(fm.get("occurrences", 1)),
                "last_mission": (fm.get("related_missions") or [""])[-1],
                "tags": list(fm.get("tags") or []),
            })

        lines = [_INDEX_HEADER.format(date=date.today().isoformat())]
        lines.append("## Cartes thématiques\n")
        lines.append("| Slug | Thème | Sévérité | Occurrences | Dernière mission |")
        lines.append("|---|---|---|---|---|")
        for c in sorted(cards, key=lambda x: (x["theme"], x["slug"])):
            lines.append(
                f"| [{c['slug']}](incidents/{c['slug']}.md)"
                f" | {c['theme']}"
                f" | {c['severity']}"
                f" | {c['occurrences']}"
                f" | {c['last_mission']} |"
            )

        lines.append("\n## Index par tags\n")
        tag_index: dict[str, list[str]] = {}
        for c in cards:
            for tag in c["tags"]:
                # Force string type for tags (yaml parser may return ints like 403)
                tag_str = str(tag)
                tag_index.setdefault(tag_str, []).append(c["slug"])
        
        for tag in sorted(tag_index):
            slugs = " ".join(
                f"[{s}](incidents/{s}.md)" for s in sorted(tag_index[tag])
            )
            lines.append(f"**{tag}** → {slugs} ")

        lines.append(f"\n---\n_Cartes : {len(cards)}_")
        _atomic_write(self._index_path, "\n".join(lines) + "\n")
        return len(cards)

    def delete_card(self, slug: str) -> None:
        """Physically delete a KB card and regenerate the index."""
        slug = _validate_slug(slug)
        card_path = self._incidents_dir / f"{slug}.md"
        if not card_path.exists():
            raise FileNotFoundError(f"KB card not found: {slug!r}")
        
        card_path.unlink()
        self.regenerate_index()

    @staticmethod
    def _render_card(
        *,
        slug: str,
        title: str,
        theme: str,
        tags: list[str],
        severity: str,
        environments_seen: list[str],
        first_seen: str,
        last_seen: str,
        occurrences: int,
        symptoms: list[str],
        root_cause: str,
        related_missions: list[str],
        body: str,
    ) -> str:
        tags_yaml = "[" + ", ".join(tags) + "]"
        envs_yaml = "[" + ", ".join(environments_seen) + "]"
        missions_yaml = "[" + ", ".join(related_missions) + "]"
        symptom_lines = "\n".join(f'  - "{s}"' for s in symptoms)
        return (
            f"---\n"
            f"slug: {slug}\n"
            f'title: "{title}"\n'
            f'theme: "{theme}"\n'
            f"tags: {tags_yaml}\n"
            f"severity: {severity}\n"
            f"environments_seen: {envs_yaml}\n"
            f"first_seen: {first_seen}\n"
            f"last_seen: {last_seen}\n"
            f"occurrences: {occurrences}\n"
            f"symptoms:\n{symptom_lines}\n"
            f'root_cause: "{root_cause}"\n'
            f"agents_involved: []\n"
            f"related_missions: {missions_yaml}\n"
            f"---\n\n"
            f"{body}\n"
        )
