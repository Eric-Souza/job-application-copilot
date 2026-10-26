from app.graph.state import GraphState
from app.schemas import Draft, TailoredResume


def render_markdown(result: TailoredResume, state: GraphState) -> str:
    by_id = {r.id: r for r in state["requirements"]}
    lines = [f"# {result.title}" + (f" at {result.company}" if result.company else ""), ""]
    if result.summary:
        lines += ["## Summary", "", result.summary, ""]
    if result.bullets:
        lines += ["## Tailored bullets", ""]
        by_role: dict[str, list] = {}
        for b in result.bullets:
            by_role.setdefault(b.role, []).append(b)
        for role, bullets in by_role.items():
            if role:
                lines += [f"### {role}", ""]
            for b in bullets:
                lines.append(f"- {b.text}")
                lines.extend(f"  - Check: {flag}" for flag in b.flags)
            lines.append("")
    lines += [
        "## Requirement coverage",
        "",
        "| | Requirement | Kind | Coverage | Evidence |",
        "|---|---|---|---|---|",
    ]
    for m in state["matches"]:
        r = by_id[m.requirement_id]
        lines.append(f"| {r.id} | {r.text} | {r.kind} | {m.coverage} | {', '.join(m.evidence_ids) or '-'} |")
    if result.gaps:
        lines += ["", "## Gaps (must-haves with no evidence)", ""] + [f"- {g}" for g in result.gaps]
    if result.warnings:
        lines += ["", "## Warnings", ""] + [f"- {w}" for w in result.warnings]
    return "\n".join(lines) + "\n"


async def finalize(state: GraphState) -> GraphState:
    """Assemble the tailored resume section. No LLM call: every piece was already checked."""
    analysis = state["analysis"]
    draft = state.get("draft") or Draft(summary="", bullets=[])
    by_id = {r.id: r for r in state["requirements"]}
    matches = state["matches"]

    coverage = {c: sum(m.coverage == c for m in matches) for c in ("strong", "partial", "missing")}
    gaps = [
        by_id[m.requirement_id].text
        for m in matches
        if m.coverage == "missing" and by_id[m.requirement_id].kind == "must"
    ]

    warnings = state.get("warnings", []) + draft.warnings

    result = TailoredResume(
        title=analysis.title,
        company=analysis.company,
        summary=draft.summary,
        bullets=draft.bullets,
        coverage=coverage,
        gaps=gaps,
        warnings=warnings,
        markdown="",
    )
    return {"result": result.model_copy(update={"markdown": render_markdown(result, state)})}
