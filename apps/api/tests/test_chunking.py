from app.config import REPO_ROOT
from app.services.chunking import chunk_markdown, chunk_plain_text, clean_inline

SAMPLE = REPO_ROOT / "data" / "samples" / "sample-resume.md"


def test_one_chunk_per_bullet_with_role_context():
    chunks = chunk_markdown(SAMPLE.read_text(encoding="utf-8"))
    parcelly = [c for c in chunks if "Parcelly" in c.context]

    assert len(parcelly) == 4
    assert all(c.section == "Experience" for c in parcelly)
    # The italic description under the role is context, not a chunk of its own
    assert parcelly[0].context == (
        "Senior Backend Engineer · Parcelly (logistics) | Mar 2023 – Present > "
        "Delivery tracking platform, 2M shipments a day"
    )
    assert parcelly[0].content.startswith("Built a delivery-time prediction service")
    # The heading alone identifies the role, without the description
    assert parcelly[0].heading == "Senior Backend Engineer · Parcelly (logistics) | Mar 2023 – Present"
    assert parcelly[0].embed_text == f"{parcelly[0].context}\n{parcelly[0].content}"


def test_paragraphs_without_bullets_become_chunks():
    chunks = chunk_markdown(SAMPLE.read_text(encoding="utf-8"))
    summary = [c for c in chunks if c.section == "Summary"]

    assert len(summary) == 1
    assert summary[0].context == ""
    assert summary[0].content.startswith("Backend engineer with 6 years")


def test_nested_headings_and_wrapped_bullets():
    md = """# Name
## Experience
### Agency | 2025 – Present
#### Engineer · Client A | 2025
- First line of a bullet
  that wraps onto a second line.
- Second bullet
#### Engineer · Client B | 2026
- Only bullet
"""
    chunks = chunk_markdown(md)

    assert [c.content for c in chunks] == [
        "First line of a bullet that wraps onto a second line.",
        "Second bullet",
        "Only bullet",
    ]
    assert chunks[0].context == "Agency | 2025 – Present > Engineer · Client A | 2025"
    # A sibling heading replaces the previous one instead of nesting under it
    assert chunks[2].context == "Agency | 2025 – Present > Engineer · Client B | 2026"


def test_markdown_formatting_is_stripped():
    assert (
        clean_inline("**Doc AI:** see [the repo](https://x.dev) and _notes_")
        == "Doc AI: see the repo and notes"
    )
    # Underscores inside words aren't emphasis
    assert clean_inline("snake_case_name") == "snake_case_name"


def test_plain_text_fallback_labels_chunks_with_the_file_name():
    chunks = chunk_plain_text("word " * 400, label="cover-letter")

    assert len(chunks) > 1
    assert {c.context for c in chunks} == {"cover-letter"}
