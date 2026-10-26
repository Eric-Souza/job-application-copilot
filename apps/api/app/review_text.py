"""Plain-text review for the CLI: show a paused draft, and turn an edited file back into a decision.

The edit file numbers each bullet, [1] [2] ..., and the number carries that bullet's evidence and
requirement ids, so the reviewer only touches text. New bullets need evidence, so they come
from a revision, not the editor.
"""

import re
from typing import Any

EDIT_HELP = """\
# Edit the summary and the bullets, then save and close the editor.
# Keep the [n] at the start of each bullet: it links the bullet to its evidence.
# Delete a bullet's line to drop it. Lines starting with # are ignored.
"""
_BULLET = re.compile(r"^\[(\d+)\]\s*(.*)$")


def format_request(request: dict[str, Any]) -> str:
    lines = [f"Draft {request['revision']}", "", "Summary:", f"  {request['summary']}", "", "Bullets:"]
    for i, b in enumerate(request["bullets"], start=1):
        lines.append(f"  [{i}] {b['text']}")
        lines.append(f"      {b['role']} · {', '.join(b['evidence_ids'])}")
        lines.extend(f"      Check: {flag}" for flag in b["flags"])
    if not request["bullets"]:
        lines.append("  (none)")
    if request["warnings"]:
        lines += ["", "Warnings:"] + [f"  - {w}" for w in request["warnings"]]
    if request.get("error"):
        lines += ["", f"Last decision was rejected: {request['error']}"]
    return "\n".join(lines)


def edit_text(request: dict[str, Any]) -> str:
    bullets = "\n".join(f"[{i}] {b['text']}" for i, b in enumerate(request["bullets"], start=1))
    return f"{EDIT_HELP}\n## Summary\n\n{request['summary']}\n\n## Bullets\n\n{bullets}\n"


def parse_edit(text: str, request: dict[str, Any]) -> dict[str, Any]:
    """Return an "edit" decision. Raises ValueError for a missing heading or an unknown [n]."""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        heading = line.strip().lower()
        if heading in ("## summary", "## bullets"):
            current = heading[3:]
            sections[current] = []
        elif current and not line.lstrip().startswith("#"):
            sections[current].append(line.rstrip())
    if set(sections) != {"summary", "bullets"}:
        raise ValueError("keep the '## Summary' and '## Bullets' headings")

    original = request["bullets"]
    bullets = []
    for line in filter(None, (s.strip() for s in sections["bullets"])):
        match = _BULLET.match(line)
        if not match:
            raise ValueError(f"a bullet line must start with its [n]: {line!r}")
        n, bullet_text = int(match[1]), match[2].strip()
        if not 1 <= n <= len(original):
            raise ValueError(f"there's no bullet [{n}]")
        if bullet_text:
            source = original[n - 1]
            bullets.append(
                {
                    "text": bullet_text,
                    "evidence_ids": source["evidence_ids"],
                    "requirement_ids": source["requirement_ids"],
                }
            )
    summary = " ".join(s.strip() for s in sections["summary"] if s.strip())
    return {"action": "edit", "summary": summary, "bullets": bullets}
