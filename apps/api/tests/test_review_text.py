import pytest

from app.review_text import edit_text, format_request, parse_edit

REQUEST = {
    "revision": 2,
    "summary": "Backend engineer.",
    "bullets": [
        {
            "text": "Designed a Go payments API.",
            "role": "Engineer · Acme",
            "evidence_ids": ["E1"],
            "requirement_ids": ["R1"],
            "flags": [],
        },
        {
            "text": "Ran Kubernetes for 40 teams.",
            "role": "SRE · Orbit",
            "evidence_ids": ["E3", "E4"],
            "requirement_ids": ["R2"],
            "flags": ["numbers not in the cited evidence: 40"],
        },
    ],
    "warnings": ["Dropped a bullet (no valid evidence): 'Ghost.'"],
    "coverage": [],
}


def test_format_shows_numbered_bullets_with_their_checks():
    text = format_request(REQUEST)
    assert text.startswith("Draft 2\n\nSummary:\n  Backend engineer.")
    assert "  [2] Ran Kubernetes for 40 teams.\n      SRE · Orbit · E3, E4\n      Check: numbers" in text
    assert "Warnings:\n  - Dropped a bullet" in text
    assert "rejected" not in text
    assert "Last decision was rejected: bad" in format_request({**REQUEST, "error": "bad"})


def test_unchanged_file_round_trips():
    decision = parse_edit(edit_text(REQUEST), REQUEST)
    assert decision == {
        "action": "edit",
        "summary": "Backend engineer.",
        "bullets": [
            {"text": "Designed a Go payments API.", "evidence_ids": ["E1"], "requirement_ids": ["R1"]},
            {"text": "Ran Kubernetes for 40 teams.", "evidence_ids": ["E3", "E4"], "requirement_ids": ["R2"]},
        ],
    }


def test_edits_keep_each_bullets_evidence_and_drop_deleted_lines():
    edited = """# a comment
## Summary

Go engineer who
builds payment APIs.

## Bullets

[2] Ran Kubernetes clusters.
"""
    decision = parse_edit(edited, REQUEST)
    assert decision["summary"] == "Go engineer who builds payment APIs."
    assert decision["bullets"] == [
        {"text": "Ran Kubernetes clusters.", "evidence_ids": ["E3", "E4"], "requirement_ids": ["R2"]}
    ]


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("## Summary\nx\n", "keep the '## Summary' and '## Bullets' headings"),
        ("## Summary\nx\n## Bullets\n[3] New bullet\n", r"there's no bullet \[3\]"),
        ("## Summary\nx\n## Bullets\nA bullet with no number\n", "must start with its"),
    ],
)
def test_malformed_edits_are_rejected(text, error):
    with pytest.raises(ValueError, match=error):
        parse_edit(text, REQUEST)
