from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Segment:
    index: int
    start_sec: float
    end_sec: float
    text: str
    word_count: int

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ImageCandidate:
    title: str
    page_url: str
    image_url: str
    thumb_url: str | None
    description: str
    categories: list[str]
    artist: str
    license: str
    width: int
    height: int
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SegmentResult:
    segment: Segment
    queries: list[str]
    primary_subject: str
    status: str  # matched | needs_manual_review | skipped
    chosen: ImageCandidate | None = None
    candidates: list[ImageCandidate] = field(default_factory=list)
    local_path: str | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.to_dict(),
            "queries": self.queries,
            "primary_subject": self.primary_subject,
            "status": self.status,
            "chosen": self.chosen.to_dict() if self.chosen else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "local_path": self.local_path,
            "notes": self.notes,
        }
