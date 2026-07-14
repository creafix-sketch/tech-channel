"""Wikimedia Commons client — preferred source for historically accurate images."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .cache import DiskCache
from .models import ImageCandidate

API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = (
    "ScriptImageDownloader/0.2 "
    "(https://github.com/creafix-sketch/tech-channel; computing-history B-roll helper)"
)


class WikimediaClient:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        pause_sec: float = 0.35,
        cache_dir: Path | None = None,
        fast: bool = True,
    ):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pause_sec = 0.2 if fast else pause_sec
        self._memory: dict[str, list[ImageCandidate]] = {}
        self._disk = DiskCache(cache_dir or Path(".cache/wikimedia"))
        self._last_request = 0.0
        self._cooldown_until = 0.0

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        """Search file titles/text on Commons; return page stubs."""
        cache_key = f"search|{query}|{limit}"
        cached = self._disk.get("api", cache_key)
        if cached is not None:
            return cached

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
            "maxlag": 5,
        }
        data = self._get(params)
        pages = (data.get("query") or {}).get("pages") or {}
        results = list(pages.values())
        results.sort(key=lambda p: p.get("index", 999))
        self._disk.set("api", cache_key, results)
        return results

    def search_candidates(self, query: str, *, limit: int = 8) -> list[ImageCandidate]:
        cache_key = f"{query}|{limit}"
        if cache_key in self._memory:
            return [ImageCandidate(**c.__dict__) for c in self._memory[cache_key]]

        pages = self.search(query, limit=limit)
        out: list[ImageCandidate] = []
        for page in pages:
            cand = self._page_to_candidate(page)
            if cand:
                out.append(cand)
        self._memory[cache_key] = out
        self._pace()
        return [ImageCandidate(**c.__dict__) for c in out]

    def _page_to_candidate(self, page: dict[str, Any]) -> ImageCandidate | None:
        infos = page.get("imageinfo") or []
        if not infos:
            return None
        info = infos[0]
        mime = (info.get("mime") or "").lower()
        if not mime.startswith("image/") or mime == "image/svg+xml":
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

    def _pace(self) -> None:
        now = time.time()
        if now < self._cooldown_until:
            time.sleep(self._cooldown_until - now)
            now = time.time()
        elapsed = now - self._last_request
        if elapsed < self.pause_sec:
            time.sleep(self.pause_sec - elapsed)
        self._last_request = time.time()

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(6):
            self._pace()
            try:
                resp = self.session.get(API, params=params, timeout=45)
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else min(
                        45.0, (2 ** attempt) * 1.5 + self.pause_sec
                    )
                    self._cooldown_until = time.time() + wait
                    self.pause_sec = min(2.0, self.pause_sec + 0.15)
                    last_error = requests.HTTPError(
                        f"429 Too Many Requests (attempt {attempt + 1})",
                        response=resp,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                # Healthy responses: gently speed up again.
                self.pause_sec = max(0.15, self.pause_sec * 0.95)
                self._last_request = time.time()
                return resp.json()
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(min(20.0, (2 ** attempt) * 0.75))
        assert last_error is not None
        raise last_error


def _meta_value(meta: dict[str, Any], key: str) -> str:
    block = meta.get(key) or {}
    return str(block.get("value") or "")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return " ".join(no_tags.split())
