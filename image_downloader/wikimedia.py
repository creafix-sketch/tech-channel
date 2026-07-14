"""Wikimedia Commons client — preferred source for historically accurate images."""

from __future__ import annotations

import re
import time
from typing import Any
from urllib.parse import quote

import requests

from .models import ImageCandidate

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "ScriptImageDownloader/0.1 "
    "(YouTube computing-history B-roll helper; contact: local-tool)"
)


class WikimediaClient:
    def __init__(self, *, session: requests.Session | None = None, pause_sec: float = 0.75):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pause_sec = pause_sec
        self._cache: dict[str, list[ImageCandidate]] = {}

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        """Search file titles/text on Commons; return page stubs."""
        params = {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6,  # File:
            "gsrlimit": limit,
            "prop": "imageinfo|categories|info",
            "inprop": "url",
            "iiprop": "url|size|extmetadata|mime",
            "iiurlwidth": 1280,
            "cllimit": 50,
        }
        data = self._get(params)
        pages = (data.get("query") or {}).get("pages") or {}
        results = list(pages.values())
        results.sort(key=lambda p: p.get("index", 999))
        return results

    def search_candidates(self, query: str, *, limit: int = 8) -> list[ImageCandidate]:
        cache_key = f"{query}|{limit}"
        if cache_key in self._cache:
            # Return shallow copies so per-segment scoring doesn't mutate cache.
            return [ImageCandidate(**c.__dict__) for c in self._cache[cache_key]]

        pages = self.search(query, limit=limit)
        out: list[ImageCandidate] = []
        for page in pages:
            cand = self._page_to_candidate(page)
            if cand:
                out.append(cand)
        self._cache[cache_key] = out
        time.sleep(self.pause_sec)
        return [ImageCandidate(**c.__dict__) for c in out]

    def _page_to_candidate(self, page: dict[str, Any]) -> ImageCandidate | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        mime = (info.get("mime") or "").lower()
        if not mime.startswith("image/") or mime == "image/svg+xml":
            # Prefer raster photos/scans for B-roll; skip SVG diagrams by default.
            if mime == "image/svg+xml":
                return None
            if not mime.startswith("image/"):
                return None

        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        if width < 400 or height < 300:
            return None

        meta = info.get("extmetadata") or {}
        description = _meta_value(meta, "ImageDescription")
        artist = _meta_value(meta, "Artist")
        license_name = _meta_value(meta, "LicenseShortName") or _meta_value(meta, "UsageTerms")
        categories = [
            (c.get("title") or "").replace("Category:", "")
            for c in (page.get("categories") or [])
        ]

        title = (page.get("title") or "").replace("File:", "")
        image_url = info.get("url")
        if not image_url:
            return None

        return ImageCandidate(
            title=title,
            page_url=page.get("fullurl")
            or f"https://commons.wikimedia.org/wiki/File:{quote(title.replace(' ', '_'))}",
            image_url=image_url,
            thumb_url=info.get("thumburl"),
            description=_strip_html(description),
            categories=categories,
            artist=_strip_html(artist),
            license=license_name,
            width=width,
            height=height,
        )

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                resp = self.session.get(API, params=params, timeout=45)
                if resp.status_code == 429:
                    wait = min(30.0, (2 ** attempt) + self.pause_sec)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(min(20.0, (2 ** attempt) * 0.5))
        if last_error:
            raise last_error
        raise RuntimeError("Wikimedia request failed without response")


def _meta_value(meta: dict[str, Any], key: str) -> str:
    block = meta.get(key) or {}
    return str(block.get("value") or "")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    # Lightweight tag stripper — enough for Commons metadata snippets.
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return " ".join(no_tags.split())
