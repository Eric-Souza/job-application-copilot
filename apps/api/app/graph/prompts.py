PARSE_SYSTEM = """You read job postings and extract what the employer requires.

Rules:
- List each requirement once, short and specific, in the posting's own terms.
- Split compound requirements ("Python and Go" is two) unless they only make sense together.
- kind="must" for required qualifications; kind="nice" for preferred, bonus, or "a plus".
- Skip boilerplate (benefits, equal-opportunity text, "great communication" with no specifics).
- Aim for 6 to 15 requirements."""

MATCH_SYSTEM = """You compare a candidate's resume evidence with a job's requirements.

For every requirement, decide coverage from the evidence listed under it (you may also cite
other listed evidence ids if they clearly apply):
- strong: the evidence directly shows this skill or experience
- partial: the evidence shows something related or adjacent, but not exactly this
- missing: nothing in the evidence supports it

Be strict. A skill named only in a skills list is partial for an experience requirement
("5 years building X"), strong for a plain skill requirement ("knows X").
Cite evidence ids exactly as given, like E3. Return one match per requirement."""

RESEARCH_SYSTEM = """You look for more resume evidence for job requirements that seem weakly covered.

Each requirement was searched once, with its own wording. Resumes often describe the same thing
differently: a related tool, the task instead of the skill, the industry only in a job title.
Use the search_experience tool to look again in other words.

Rules:
- One query per call, naming the requirement it's for. You can make several calls at once.
- Don't repeat the requirement's wording; try synonyms, related tools, or the concrete work
  that would show it (for "stakeholder management": "worked with clients", "led planning").
- Skip requirements no resume wording could plausibly show.
- After seeing the results, search again only if a different angle could still help.
  When you're done, reply with the word done and no tool calls.
You only find evidence. Whether it covers a requirement is decided later."""

DRAFT_SYSTEM = """You write tailored resume bullets for a specific job, using only the candidate's evidence.

Rules:
- Every claim must come from the evidence you cite. Never add technologies, numbers,
  employers, scope, or outcomes that the cited evidence doesn't state.
- Rephrase to use the posting's terminology where the evidence supports it.
- Lead with the requirements marked must and strong.
- Evidence is grouped by role. Each bullet draws on one role only; never merge roles or employers.
- Only name a technology in a bullet if that role's evidence names it. The skills list shows
  the candidate knows a tool, not where they used it.
- Profile evidence (summary, skills) is for the summary only. Don't write bullets from it,
  and no "N+ years of experience" bullets.
- Do not mention requirements listed as gaps.
- Write 4 to 8 bullets, each one sentence, starting with a past-tense verb.
- The summary is 2 to 3 sentences, grounded in the evidence.
Cite evidence ids exactly as given (E3) and requirement ids (R2)."""

REVISE_SYSTEM = """The candidate reviewed your previous draft and asked for changes.
Apply their feedback, keep what they didn't ask to change, and follow all the rules above.
Feedback can change wording, emphasis, and which evidence you use. It can't add claims
the evidence doesn't support; if it asks for that, leave it out."""

PROFILE_GROUP = "Profile (for the summary only)"


def parse_user(posting: str) -> str:
    return f"Job posting:\n\n{posting.strip()}"


def match_user(requirements, evidence_by_requirement, evidence) -> str:
    blocks = []
    for r in requirements:
        lines = [evidence[e].prompt_line() for e in evidence_by_requirement.get(r.id, [])]
        listed = "\n".join(f"  {line}" for line in lines) or "  (no evidence found)"
        blocks.append(f"{r.id} [{r.kind}] {r.text}\n{listed}")
    return "Requirements and the evidence retrieved for each:\n\n" + "\n\n".join(blocks)


def research_user(requirements, matches, evidence) -> str:
    by_req = {m.requirement_id: m for m in matches}
    blocks = []
    for r in requirements:
        m = by_req[r.id]
        lines = [evidence[e].prompt_line() for e in m.evidence_ids]
        found = "\n".join(f"  {line}" for line in lines) or "  (nothing relevant)"
        blocks.append(f"{r.id} [{r.kind}, {m.coverage}] {r.text}\n  Why: {m.rationale}\n{found}")
    return "Weakly covered requirements, with what the first search found:\n\n" + "\n\n".join(blocks)


def draft_user(analysis, requirements, matches, evidence) -> str:
    by_id = {r.id: r for r in requirements}
    covered = [m for m in matches if m.coverage != "missing"]
    gaps = [by_id[m.requirement_id] for m in matches if m.coverage == "missing"]
    cited = list(dict.fromkeys(e for m in covered for e in m.evidence_ids))

    req_lines = "\n".join(
        f"{m.requirement_id} [{by_id[m.requirement_id].kind}, {m.coverage}] {by_id[m.requirement_id].text}"
        f" <- {', '.join(m.evidence_ids)}"
        for m in covered
    )
    # Grouped by role, so the model sees which accomplishments belong together
    groups: dict[str, list[str]] = {}
    profile: list[str] = []
    for e in cited:
        item = evidence[e]
        (profile if item.is_profile else groups.setdefault(item.anchor, [])).append(item.prompt_line())
    if profile:
        groups[PROFILE_GROUP] = profile  # listed last
    evidence_lines = "\n\n".join(f"### {key}\n" + "\n".join(lines) for key, lines in groups.items())
    gap_lines = "\n".join(f"- {r.text}" for r in gaps) or "- none"
    return (
        f"Role: {analysis.title}" + (f" at {analysis.company}" if analysis.company else "") + "\n"
        f"About the role: {analysis.summary}\n\n"
        f"Requirements the candidate covers:\n{req_lines}\n\n"
        f"Evidence by role:\n\n{evidence_lines}\n\n"
        f"Gaps (don't claim these):\n{gap_lines}"
    )


def revise_user(draft, feedback: str) -> str:
    bullets = "\n".join(f"- {b.text} ({', '.join(b.evidence_ids)})" for b in draft.bullets) or "- none"
    return (
        f"Your previous draft:\n\nSummary: {draft.summary}\n\nBullets:\n{bullets}\n\n"
        f"Reviewer feedback:\n{feedback.strip()}"
    )
