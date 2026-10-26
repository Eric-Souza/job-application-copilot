from app.graph.grounding import check_bullet, check_draft, numbers_in, skill_terms
from app.schemas import BulletSpec, EvidenceItem


def item(id: str, section: str, content: str, heading: str = "", context: str = "") -> EvidenceItem:
    return EvidenceItem(
        id=id,
        chunk_id=f"c{id}",
        section=section,
        context=context or heading,
        heading=heading,
        content=content,
        score=0.03,
    )


PAYLANE = "Backend Engineer · Paylane | 2020 – 2023"
EVIDENCE = {
    e.id: e
    for e in [
        item("E1", "Experience", "Designed a payments API in Go handling 300 requests per second.", PAYLANE),
        item("E2", "Technical Skills", "Infrastructure: AWS (EC2, S3), Kubernetes, event-driven systems"),
        item("E3", "Experience", "Migrated the ledger to PostgreSQL.", PAYLANE),
        item("E4", "Experience", "Ran Kubernetes clusters on AWS.", "Platform Engineer · Orbit | 2023 – now"),
        item("E5", "Summary", "Backend engineer with 8+ years of experience."),
        item("E6", "Projects", "Ledger CLI: a Go tool for reconciling bank exports."),
    ]
}
REQS = {"R1", "R2"}


def check(text: str, *evidence_ids: str):
    bullet = BulletSpec(text=text, requirement_ids=["R1"], evidence_ids=list(evidence_ids))
    return check_bullet(bullet, EVIDENCE, REQS, skill_terms(list(EVIDENCE.values())))


def test_numbers_ignore_digits_inside_names():
    assert numbers_in("Ran EC2 and S3 for a Web3 app, 4,000 users, 18% faster, 2.5x") == {"4000", "18", "2.5"}


def test_profile_and_anchor():
    assert [e.is_profile for e in EVIDENCE.values()] == [False, True, False, False, True, False]
    assert EVIDENCE["E1"].anchor == PAYLANE
    assert EVIDENCE["E6"].anchor == "Projects > Ledger CLI"
    assert EVIDENCE["E5"].anchor == "Summary"


def test_skill_terms_keep_names_and_skip_phrases():
    assert skill_terms(list(EVIDENCE.values())) == {"AWS", "EC2", "S3", "Kubernetes"}


def test_grounded_bullet_passes_and_gets_its_role():
    bullet, reason = check("Built a Go payments API serving 300 requests per second.", "E1", "E3")

    assert reason == ""
    assert (bullet.role, bullet.flags) == (PAYLANE, [])


def test_invented_numbers_are_flagged():
    bullet, _ = check("Cut payment latency by 40% while serving 300 requests per second.", "E1")

    assert bullet.flags == ["numbers not in the cited evidence: 40"]


def test_bullets_backed_only_by_profile_evidence_are_dropped():
    assert check("Leveraged 8+ years of backend experience.", "E5") == (
        None,
        "only backed by the summary or skills list",
    )


def test_mixing_roles_is_flagged():
    bullet, _ = check("Built Go APIs and ran Kubernetes on AWS.", "E1", "E4")

    assert bullet.flags == [f"combines different roles: {PAYLANE}; Platform Engineer · Orbit | 2023 – now"]


def test_skills_the_role_never_used_are_flagged_even_if_the_skills_list_is_cited():
    bullet, _ = check("Deployed the Go payments API to Kubernetes on AWS.", "E1", "E2")

    assert bullet.flags == ["mentions AWS, Kubernetes, which this role's evidence doesn't"]


def test_unknown_ids_are_removed_and_uncited_bullets_dropped():
    bullets = [
        BulletSpec(
            text="Migrated the ledger to PostgreSQL.",
            requirement_ids=["R1", "R9"],
            evidence_ids=["E7", "E3", "E3"],
        ),
        BulletSpec(text="Led a team of 12.", requirement_ids=["R2"], evidence_ids=["E9"]),
    ]

    kept, dropped = check_draft(bullets, EVIDENCE, REQS)

    assert [(b.evidence_ids, b.requirement_ids) for b in kept] == [(["E3"], ["R1"])]
    assert dropped == ["Dropped a bullet (no valid evidence): 'Led a team of 12.'"]
