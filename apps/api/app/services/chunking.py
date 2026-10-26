"""Split resume-style Markdown into evidence chunks: one per bullet, tagged with its headings.

A generic character splitter would cut a role in the middle and lose which company a bullet
belongs to. Resumes are already split into the right units, so this follows their structure:

    ## Experience                                  -> section
    ### Senior Engineer · Acme | 2022 – 2024       -> context
    _Healthcare data platform_                     -> appended to the context
    - Built clinical dashboards with React.        -> one chunk

Paragraphs under a heading that has bullets describe it, so they go into the context.
Paragraphs under a heading without bullets (a summary, for example) become chunks.
"""

import re
from dataclasses import dataclass, field

from langchain_text_splitters import RecursiveCharacterTextSplitter

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(?<!\w)(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1(?!\w)")


@dataclass
class TextChunk:
    section: str
    context: str
    content: str

    @property
    def embed_text(self) -> str:
        """What gets embedded: the bullet plus where it came from."""
        return f"{self.context}\n{self.content}" if self.context else self.content


@dataclass
class _Node:
    section: str
    path: list[str]
    # Each item is a list of source lines, joined once the block is complete
    paragraphs: list[list[str]] = field(default_factory=list)
    bullets: list[list[str]] = field(default_factory=list)


def clean_inline(text: str) -> str:
    text = _LINK.sub(r"\1", text)
    text = _EMPHASIS.sub(r"\2", text)
    return re.sub(r"\s+", " ", text).strip()


def chunk_markdown(markdown: str) -> list[TextChunk]:
    nodes: list[_Node] = []
    section = ""
    path: list[str] = []  # headings below the section, by depth
    node: _Node | None = None
    current: list[str] | None = None  # the paragraph or bullet being built

    def start_node() -> _Node:
        nonlocal node
        node = _Node(section=section, path=list(path))
        nodes.append(node)
        return node

    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            current = None
            continue

        heading = _HEADING.match(line)
        if heading:
            level, title = len(heading.group(1)), clean_inline(heading.group(2))
            current = None
            if level == 1:
                node = None  # the document title (a name) isn't evidence
                continue
            if level == 2:
                section, path = title, []
            else:
                depth = level - 3
                path = path[:depth] + [title]
            start_node()
            continue

        target = node or start_node()
        bullet = _BULLET.match(line)
        if bullet:
            current = [bullet.group(1)]
            target.bullets.append(current)
        elif current is not None:
            current.append(line.strip())  # wrapped line of a bullet or paragraph
        else:
            current = [line.strip()]
            target.paragraphs.append(current)

    chunks: list[TextChunk] = []
    for n in nodes:
        bullets = [clean_inline(" ".join(b)) for b in n.bullets]
        paragraphs = [clean_inline(" ".join(p)) for p in n.paragraphs]
        if bullets:
            context = " > ".join(n.path + paragraphs)
            chunks.extend(TextChunk(n.section, context, b) for b in bullets if b)
        else:
            context = " > ".join(n.path)
            chunks.extend(TextChunk(n.section, context, p) for p in paragraphs if p)
    return chunks


def chunk_plain_text(text: str, label: str) -> list[TextChunk]:
    """Fallback for PDFs and text files without Markdown structure."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    return [TextChunk(section="", context=label, content=c) for c in splitter.split_text(text)]
