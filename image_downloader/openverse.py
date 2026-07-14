"""Openverse (Creative Commons) search — extra unique images when Commons is exhausted."""

from __future__ import annotations

import time
from typing import Any

import requests

from .models import ImageCandidate

API = "https://api.openverse.org/v1/images/"
USER_AGENT = (
    "ScriptImageDownloader/0.2 "
    "(https://github.com/creafix-sketch/tech-channel; computing-history B-roll helper)"
)


class OpenverseClient:
    def __init__(self, *, session: requests.Session | None = None, pause_sec: float = 0.25):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pause_sec = pause_sec
        self._cache: dict[str, list[ImageCandidate]] = {}

    def search_candidates(self, query: str, *, limit: int = 12) -> list[ImageCandidate]:
        key = f"{query}|{limit}"
        if key in self._cache:
            return [ImageCandidate(**c.__dict__) for c in self._cache[key]]

        params = {
            "q": query,
            "page_size": min(limit, 20),
            "license_type": "commercial",  # safer for YouTube monetization
        }
        try:
            resp = self.session.get(API, params=params, timeout=45)
            if resp.status_code == 429:
                time.sleep(3)
                resp = self.session.get(API, params=params, timeout=45)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            return []

        out: list[ImageCandidate] = []
        for row in data.get("results") or []:
            cand = self._row_to_candidate(row)
            if cand:
                out.append(cand)
        self._cache[key] = out
        time.sleep(self.pause_sec)
        return [ImageCandidate(**c.__dict__) for c in out]

    def _row_to_candidate(self, row: dict[str, Any]) -> ImageCandidate | None:
        url = row.get("url") or row.get("thumbnail")
        if not url:
            return None
        width = int(row.get("width") or 0)
        height = int(row.get("height") or 0)
        if width and height and (width < 400 or height < 300):
            return None
        title = row.get("title") or "Openverse image"
        return ImageCandidate(
            title=title,
            page_url=row.get("foreign_landing_url") or row.get("detail_url") or url,
            image_url=url,
            thumb_url=row.get("thumbnail") or url,
            description=row.get("description") or "",
            categories=[row.get("source") or "openverse"],
            artist=str((row.get("creator") or "")),
            license=str(row.get("license") or row.get("license_version") or "CC"),
            width=width or 1280,
            height=height or 720,
        )
