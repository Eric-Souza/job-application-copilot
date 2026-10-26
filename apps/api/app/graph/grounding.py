"""Deterministic checks on drafted bullets, so the resume never claims more than the evidence.

The draft prompt tells the model to use only the evidence it cites, but a prompt is a request,
not a guarantee. The first real run showed the typical failures, and each one is checked here:

- citing nothing real, or only the summary or skills list   -> the bullet is dropped
- merging accomplishments from different roles             -> flagged
- numbers the cited evidence doesn't contain ("cut by 40%") -> flagged
- a skill from the skills list that this role never used   -> flagged

Flags don't remove a bullet; they tell the reviewer exactly what to check. The same checks
run on the reviewer's own edits.
"""

import re

from app.schemas import Bullet, BulletSpec, EvidenceItem

# 18%, 2M, 4,000, 3.5x, 300 ... but not the "3" in "Web3" or "S3"
_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")
_SKILL_SECTION = re.compile(r"skill", re.IGNORECASE)


def numbers_in(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(text)}


def skill_terms(evidence: list[EvidenceItem]) -> set[str]:
    """Named technologies from skills-list chunks, e.g. "Cloud: AWS (EC2, S3), Kubernetes"."""
    terms: set[str] = set()
    for e in evidence:
        if not _SKILL_SECTION.search(e.section):
            continue
        _, _, items = e.content.partition(":")
        for raw in re.split(r"[,()/;]", items or e.content):
            term = raw.strip()
            # Keep names (Kubernetes, GitHub Actions, SSE), skip phrases (event-driven systems)
            has_caps = term[1:] != term[1:].lower()
            if term and (has_caps or (term[:1].isupper() and " " not in term)):
                terms.add(term)
    return terms


def mentions(text: str, term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text, re.IGNORECASE) is not None


def check_bullet(
    bullet: BulletSpec,
    evidence: dict[str, EvidenceItem],
    requirement_ids: set[str],
    terms: set[str] = frozenset(),
) -> tuple[Bullet | None, str]:
    """Return (checked bullet, "") or (None, why it was dropped)."""
    cited = [evidence[e] for e in dict.fromkeys(bullet.evidence_ids) if e in evidence]
    if not cited:
        return None, "no valid evidence"
    work = [e for e in cited if not e.is_profile]
    if not work:
        return None, "only backed by the summary or skills list"

    flags = []
    anchors = list(dict.fromkeys(e.anchor for e in work))
    if len(anchors) > 1:
        flags.append(f"combines different roles: {'; '.join(anchors)}")

    cited_text = " ".join(f"{e.context} {e.content}" for e in cited)
    if unsupported := sorted(numbers_in(bullet.text) - numbers_in(cited_text)):
        flags.append(f"numbers not in the cited evidence: {', '.join(unsupported)}")

    work_text = " ".join(f"{e.context} {e.content}" for e in work)
    claimed = sorted(t for t in terms if mentions(bullet.text, t) and not mentions(work_text, t))
    if claimed:
        flags.append(f"mentions {', '.join(claimed)}, which this role's evidence doesn't")

    checked = Bullet(
        text=bullet.text,
        evidence_ids=[e.id for e in cited],
        requirement_ids=[r for r in dict.fromkeys(bullet.requirement_ids) if r in requirement_ids],
        role=anchors[0],
        flags=flags,
    )
    return checked, ""


def check_draft(
    bullets: list[BulletSpec], evidence: dict[str, EvidenceItem], requirement_ids: set[str]
) -> tuple[list[Bullet], list[str]]:
    """Grounding-check every bullet. Returns the kept bullets and a warning per dropped one."""
    terms = skill_terms(list(evidence.values()))
    kept: list[Bullet] = []
    dropped: list[str] = []
    for b in bullets:
        checked, reason = check_bullet(b, evidence, requirement_ids, terms)
        if checked is None:
            dropped.append(f"Dropped a bullet ({reason}): {b.text!r}")
        else:
            kept.append(checked)
    return kept, dropped


def check_summary(summary: str, evidence: dict[str, EvidenceItem]) -> list[str]:
    """The summary may draw on any evidence, so only numbers missing from the whole pool count."""
    pool_text = " ".join(f"{e.context} {e.content}" for e in evidence.values())
    if unsupported := sorted(numbers_in(summary) - numbers_in(pool_text)):
        return [f"The summary has numbers not in the evidence: {', '.join(unsupported)}"]
    return []
