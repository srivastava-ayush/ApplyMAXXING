"""Skill discovery and loading.

Mirrors the skill scanning of Claude Code / opencode: every directory
containing a SKILL.md under the workspace's skill roots is a skill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

SKILL_ROOTS = [
    WORKSPACE / ".claude" / "skills",
    WORKSPACE / ".agents" / "skills",
    WORKSPACE / ".opencode" / "skills",
]

MAX_SKILL_CHARS = 60_000


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path


def _parse_frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[4:end]
    fields: dict[str, str] = {}
    key = None
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            key = m.group(1)
            value = m.group(2).strip()
            if value in (">", "|"):
                value = ""
            fields[key] = value
        elif key and line.startswith(("  ", "\t")):
            fields[key] = (fields[key] + " " + line.strip()).strip()
    return fields


def catalog() -> list[Skill]:
    skills = []
    seen = set()
    for root in SKILL_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*/SKILL.md")):
            fields = _parse_frontmatter(path.read_text(encoding="utf-8"))
            name = fields.get("name") or path.parent.name
            if name in seen:
                continue
            seen.add(name)
            skills.append(
                Skill(
                    name=name,
                    description=fields.get("description", "").strip(),
                    path=path,
                )
            )
    return skills


def load(name: str) -> str:
    for skill in catalog():
        if skill.name == name:
            text = skill.path.read_text(encoding="utf-8")
            if len(text) > MAX_SKILL_CHARS:
                text = text[:MAX_SKILL_CHARS] + "\n\n[truncated]"
            return text
    known = ", ".join(s.name for s in catalog())
    raise KeyError(f"unknown skill {name!r}; available: {known}")
