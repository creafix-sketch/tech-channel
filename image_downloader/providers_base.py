"""Shared search-provider interface."""

from __future__ import annotations

from typing import Protocol

from .models import ImageCandidate


class ImageProvider(Protocol):
    name: str

    def search_candidates(self, query: str, *, limit: int = 10) -> list[ImageCandidate]:
        ...
