"""Pydantic models for the agent: what the LLM returns, and what the graph keeps in state."""

import re
from typing import Literal

from pydantic import BaseModel, Field

RequirementKind = Literal["must", "nice"]
Coverage = Literal["strong", "partial", "missing"]

# Sections that describe the candidate in general rather than a specific accomplishment
_PROFILE_SECTION = re.compile(
    r"summary|skill|about|profile|additional|education|language|certification", re.IGNORECASE
)


# --- parse_posting -------------------------------------------------------------------------


class RequirementSpec(BaseModel):
    text: str = Field(description="One requirement, short and specific, in the posting's own terms")
    kind: RequirementKind = Field(description="must = required; nice = preferred, bonus, or 'a plus'")
    category: Literal["skill", "experience", "domain", "leadership", "education", "other"]


class PostingAnalysis(BaseModel):
    title: str
    company: str | None = None
    seniority: str | None = Field(None, description="e.g. Senior, Staff, Lead, if stated or clearly implied")
    summary: str = Field(description="Two sentences: what the role does and what it emphasizes")
    requirements: list[RequirementSpec]


class Requirement(RequirementSpec):
    id: str  # R1, R2, ... assigned by the graph, not the LLM


# --- retrieve_experience -------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """A resume chunk the agent may cite, with a short id the LLM can reference."""

    id: str  # E1, E2, ...
    chunk_id: str
    section: str
    context: str
    heading: str = ""
    content: str
    score: float

    @property
    def is_profile(self) -> bool:
        """Summary and skills-list chunks: true about the candidate, but not tied to any role."""
        return bool(_PROFILE_SECTION.search(self.section))

    @property
    def anchor(self) -> str:
        """The role or project a chunk belongs to. Bullets may only draw on one anchor."""
        if self.heading:
            return self.heading
        name, sep, _ = self.content.partition(":")  # "Doc Processing AI: RAG chat over ..."
        if sep and len(name) <= 60:
            return f"{self.section} > {name.strip()}"
        return self.section

    def prompt_line(self) -> str:
        where = f"{self.section} > {self.context}" if self.context else self.section
        return f"[{self.id}] ({where}) {self.content}"


# --- match_requirements --------------------------------------------------------------------


class Match(BaseModel):
    requirement_id: str
    coverage: Coverage = Field(
        description="strong = the evidence directly shows it; partial = related or adjacent; missing = none"
    )
    evidence_ids: list[str] = Field(description="Evidence ids that support this requirement, best first")
    rationale: str = Field(description="One sentence on why, naming what the evidence shows or lacks")


class MatchReport(BaseModel):
    matches: list[Match]


# --- draft_bullets -------------------------------------------------------------------------


class BulletSpec(BaseModel):
    text: str
    requirement_ids: list[str] = Field(description="Requirements this bullet addresses")
    evidence_ids: list[str] = Field(
        description="Evidence this bullet is based on; every claim must come from it"
    )


class DraftSpec(BaseModel):
    summary: str = Field(description="A 2-3 sentence professional summary tailored to this role")
    bullets: list[BulletSpec]


class Bullet(BulletSpec):
    # Set by the graph's grounding check, never by the LLM
    role: str = ""  # the anchor of the evidence it cites
    flags: list[str] = Field(default_factory=list)


class Draft(BaseModel):
    summary: str
    bullets: list[Bullet]


# --- finalize ------------------------------------------------------------------------------


class TailoredResume(BaseModel):
    title: str
    company: str | None
    summary: str
    bullets: list[Bullet]
    coverage: dict[Coverage, int]
    gaps: list[str]  # must-have requirements with no evidence
    warnings: list[str]
    markdown: str
