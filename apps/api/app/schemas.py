"""Pydantic models for the agent: what the LLM returns, and what the graph keeps in state."""

import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


# --- research_gaps -------------------------------------------------------------------------


class SearchExperience(BaseModel):
    """Search the candidate's resume, project write-ups, and articles for evidence of a requirement.

    Use different wording than the requirement itself: synonyms, related tools, or the kind of
    work that would show it. Returns the matching resume bullets with their evidence ids.
    """

    requirement_id: str = Field(description="The requirement this search is for, like R3")
    query: str = Field(description="What to look for, in words a resume might use")


class Search(BaseModel):
    """One search the agent ran while looking for more evidence, kept to show what it tried."""

    requirement_id: str
    query: str
    found: list[str] = Field(default_factory=list)  # evidence ids new to this requirement


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
    # Dropped bullets and summary problems. Kept with the draft, so a revision replaces them
    warnings: list[str] = Field(default_factory=list)
    revision: int = 1


# --- human_review --------------------------------------------------------------------------


class ReviewDecision(BaseModel):
    """What the reviewer sends back when the graph pauses on a draft.

    approve: finalize this draft.
    revise:  redraft with the feedback.
    edit:    replace the summary and/or bullets, then review again (edits are checked too).
    """

    action: Literal["approve", "revise", "edit"]
    feedback: str = ""
    summary: str | None = None
    bullets: list[BulletSpec] | None = None

    @model_validator(mode="after")
    def _has_what_the_action_needs(self) -> "ReviewDecision":
        if self.action == "revise" and not self.feedback.strip():
            raise ValueError("revise needs feedback")
        if self.action == "edit" and self.summary is None and self.bullets is None:
            raise ValueError("edit needs a summary or bullets")
        return self


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
