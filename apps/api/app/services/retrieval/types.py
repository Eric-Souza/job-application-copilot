from dataclasses import dataclass, field


@dataclass
class Evidence:
    """A retrieved experience chunk plus the scores each retrieval stage gave it."""

    chunk_id: str
    filename: str
    section: str
    context: str
    content: str
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def score(self) -> float:
        """The score from the last stage that ranked this chunk."""
        for key in ("rrf", "vector", "keyword"):
            if key in self.scores:
                return self.scores[key]
        return 0.0
