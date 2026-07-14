"""Wikipedia / Wikidata lead images for named entities."""

from __future__ import annotations

import time
from urllib.parse import quote

import requests

from .models import ImageCandidate

USER_AGENT = (
    "ScriptImageDownloader/0.3 "
    "(https://github.com/creafix-sketch/tech-channel; computing-history B-roll helper)"
)
API = "https://en.wikipedia.org/w/api.php"


class WikipediaProvider:
    name = "wikipedia"

    def __init__(self, *, session: requests.Session | None = None, pause_sec: float = 0.2):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.pause_sec = pause_sec
        self._cache: dict[str, list[ImageCandidate]] = {}

    def search_candidates(self, query: str, *, limit: int = 8) -> list[ImageCandidate]:
        key = f"{query}|{limit}"
        if key in self._cache:
            return [ImageCandidate(**c.__dict__) for c in self._cache[key]]

        # 1) search pages
        params = {
            "action": "query",
            "format": "json",
            "list": "search",
            "srsearch": query,
            "srlimit": min(limit, 8),
        }
        try:
            data = self._get(params)
        except requests.RequestException:
            return []
        hits = (data.get("query") or {}).get("search") or []
        titles = [h.get("title") for h in hits if h.get("title")]
        if not titles:
            return []

        # 2) pageimages for those titles
        params2 = {
            "action": "query",
            "format": "json",
            "titles": "|".join(titles[:8]),
            "prop": "pageimages|info|description",
            "pithumbsize": 1280,
            "inprop": "url",
            "pilicense": "any",
        }
        try:
            data2 = self._get(params2)
        except requests.RequestException:
            return []

        out: list[ImageCandidate] = []
        pages = (data2.get("query") or {}).get("pages") or {}
        for page in pages.values():
            thumb = page.get("thumbnail") or {}
            src = thumb.get("source")
            if not src:
                continue
            title = page.get("title") or query
            desc = page.get("description") or ""
            out.append(
                ImageCandidate(
                    title=f"Wikipedia: {title}",
                    page_url=page.get("fullurl")
                    or f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                    image_url=src,
                    thumb_url=src,
                    description=desc,
                    categories=["wikipedia"],
                    artist="Wikipedia",
                    license="see Wikipedia page",
                    width=int(thumb.get("width") or 1280),
                    height=int(thumb.get("height") or 720),
                )
            )
        self._cache[key] = out
        time.sleep(self.pause_sec)
        return [ImageCandidate(**c.__dict__) for c in out]

    def _get(self, params: dict) -> dict:
        resp = self.session.get(API, params=params, timeout=40)
        resp.raise_for_status()
        return resp.json()


# Alias used by pipeline
WikipediaImageClient = WikipediaProvider
