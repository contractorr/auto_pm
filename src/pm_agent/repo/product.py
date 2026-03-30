"""Load structured product context from PRODUCT.md."""

from __future__ import annotations

import re
from pathlib import Path

from pm_agent.models.contracts import ProductContext

SECTION_RE = re.compile(r"^#{1,6}\s+(?P<title>.+?)\s*$")


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _extract_sections(markdown: str) -> dict[str, list[str]]:
    current = "_preamble"
    sections: dict[str, list[str]] = {current: []}
    for line in markdown.splitlines():
        match = SECTION_RE.match(line)
        if match:
            current = _normalize_heading(match.group("title"))
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _parse_list_or_paragraph(lines: list[str]) -> list[str]:
    values: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            values.append(stripped[2:].strip())
        else:
            values.append(stripped)
    return values


def _section_value(sections: dict[str, list[str]], *candidates: str) -> list[str]:
    for candidate in candidates:
        key = _normalize_heading(candidate)
        if key in sections:
            return _parse_list_or_paragraph(sections[key])
    return []


def load_product_context(path: str | Path) -> ProductContext:
    product_path = Path(path)
    if not product_path.exists():
        return ProductContext(vision="")
    text = product_path.read_text(encoding="utf-8")
    sections = _extract_sections(text)

    vision_values = _section_value(sections, "Product Vision", "Vision")
    if not vision_values:
        preamble = _parse_list_or_paragraph(sections.get("_preamble", []))
        vision_values = preamble[:1]

    strategic = _section_value(
        sections,
        "Current Strategic Priority",
        "Current Strategic Priorities",
        "Strategic Priority",
        "Strategic Priorities",
    )

    return ProductContext(
        vision=" ".join(vision_values).strip(),
        target_users=_section_value(sections, "Target Users", "Users"),
        non_goals=_section_value(sections, "Non-Goals", "Non Goals"),
        strategic_priorities=strategic,
    )
