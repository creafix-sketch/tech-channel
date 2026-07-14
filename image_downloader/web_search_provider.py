"""Optional Google / SerpAPI image search for near-complete coverage.

These are the closest automated equivalent to manual Google Images searching.
Requires API keys via environment variables or CLI flags.
"""

from __future__ import annotations

import os
import time
from typing import Any

import requests

from .models import ImageCandidate

USER_AGENT = (
    "ScriptImageDownloader/0.3 "
    "(https://github.com/creafix-sketch/tech-channel; computing-history B-roll helper)"
)


class GoogleCseProvider:
    """Google Programmable Search (Custom Search JSON API) — image mode."""

    name = "google_cse"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        cx: str | None = None,
        session: requests.Session | None = None,
        pause_sec: float = 0.35,
    ):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_CSE_KEY")
        self.cx = cx or os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CSE_CX")
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pause_sec = pause_sec
        self._cache: dict[str, list[ImageCandidate]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.cx)

    def search_candidates(self, query: str, *, limit: int = 8) -> list[ImageCandidate]:
        if not self.enabled:
            return []
        key = f"{query}|{limit}"
        if key in self._cache:
            return [ImageCandidate(**c.__dict__) for c in self._cache[key]]

        params = {
            "key": self.api_key,
            "cx": self.cx,
            "q": query,
            "searchType": "image",
            "num": min(limit, 10),
            "safe": "active",
        }
        try:
            resp = self.session.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                timeout=40,
            )
            if resp.status_code == 429:
                time.sleep(2)
                resp = self.session.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                    timeout=40,
                )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            return []

        out: list[ImageCandidate] = []
        for row in data.get("items") or []:
            link = row.get("link")
            if not link:
                continue
            image = row.get("image") or {}
            out.append(
                ImageCandidate(
                    title=row.get("title") or query,
                    page_url=row.get("image", {}).get("contextLink") or row.get("displayLink") or link,
                    image_url=link,
                    thumb_url=image.get("thumbnailLink") or link,
                    description=row.get("snippet") or "",
                    categories=["google_cse"],
                    artist=row.get("displayLink") or "",
                    license="check source page before publishing",
                    width=int(image.get("width") or 0),
                    height=int(image.get("height") or 0) or 720,
                )
            )
        self._cache[key] = out
        time.sleep(self.pause_sec)
        return [ImageCandidate(**c.__dict__) for c in out]


class SerpApiProvider:
    """SerpAPI Google Images — strong coverage; paid key required."""

    name = "serpapi"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        session: requests.Session | None = None,
        pause_sec: float = 0.35,
    ):
        self.api_key = api_key or os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY")
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pause_sec = pause_sec
        self._cache: dict[str, list[ImageCandidate]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def search_candidates(self, query: str, *, limit: int = 8) -> list[ImageCandidate]:
        if not self.enabled:
            return []
        key = f"{query}|{limit}"
        if key in self._cache:
            return [ImageCandidate(**c.__dict__) for c in self._cache[key]]

        params = {
            "engine": "google_images",
            "q": query,
            "api_key": self.api_key,
            "num": min(limit, 20),
            "safe": "active",
        }
        try:
            resp = self.session.get("https://serpapi.com/search.json", params=params, timeout=45)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException:
            return []

        out: list[ImageCandidate] = []
        for row in (data.get("images_results") or [])[:limit]:
            link = row.get("original") or row.get("thumbnail")
            if not link:
                continue
            out.append(
                ImageCandidate(
                    title=row.get("title") or query,
                    page_url=row.get("link") or row.get("source") or link,
                    image_url=link,
                    thumb_url=row.get("thumbnail") or link,
                    description=row.get("source") or "",
                    categories=["serpapi", "google_images"],
                    artist=row.get("source") or "",
                    license="check source page before publishing",
                    width=int(row.get("original_width") or 0),
                    height=int(row.get("original_height") or 0) or 720,
                )
            )
        self._cache[key] = out
        time.sleep(self.pause_sec)
        return [ImageCandidate(**c.__dict__) for c in out]


# Aliases used by pipeline / CLI
GoogleCseClient = GoogleCseProvider
SerpApiClient = SerpApiProvider


def web_search_enabled() -> bool:
    """True when at least one optional web image API is configured."""
    return GoogleCseProvider().enabled or SerpApiProvider().enabled
