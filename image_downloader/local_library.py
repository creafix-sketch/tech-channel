"""Match a local folder of images to script beats (for full-coverage workflows).

Put images you already collected (from Google, archives, screenshots) into a
folder. Filenames/folder names that contain subject keywords get preferred.

Example:
  my_images/
    012_bill-gates-os2.jpg
    ibm-pc-at-1984.png
    boca-raton-campus.jpg
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import ImageCandidate

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}


class LocalLibrary:
    """Searchable pool of user-collected images; each file used at most once."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self._items: list[tuple[Path, ImageCandidate]] = []
        self._used: set[str] = set()
        if self.folder.exists():
            for path in sorted(self.folder.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in _IMAGE_EXTS:
                    continue
                rel = str(path.relative_to(self.folder))
                stem = path.stem.replace("_", " ").replace("-", " ")
                resolved = str(path.resolve())
                self._items.append(
                    (
                        path,
                        ImageCandidate(
                            title=f"Local: {rel}",
                            page_url=path.as_uri(),
                            image_url=f"file://{resolved}",
                            thumb_url=f"file://{resolved}",
                            description=stem,
                            categories=["local_library"],
                            artist="local",
                            license="user-provided",
                            width=1280,
                            height=720,
                        ),
                    )
                )

    def __len__(self) -> int:
        return len(self._items)

    def mark_used(self, image_url: str) -> None:
        self._used.add(image_url)
        # Also mark by resolved path if present
        if image_url.startswith("file://"):
            self._used.add(image_url)

    def search_candidates(self, queries: list[str], *, limit: int = 8) -> list[ImageCandidate]:
        blob_tokens: set[str] = set()
        for q in queries:
            blob_tokens.update(re.findall(r"[a-z0-9]{3,}", q.lower()))
        if not blob_tokens:
            return []

        ranked: list[tuple[float, ImageCandidate]] = []
        for path, cand in self._items:
            if cand.image_url in self._used:
                continue
            name_blob = f"{path.stem} {path.parent.name}".lower().replace("-", " ").replace("_", " ")
            name_tokens = set(re.findall(r"[a-z0-9]{3,}", name_blob))
            overlap = len(blob_tokens & name_tokens)
            if overlap == 0:
                continue
            score = overlap / max(3, min(8, len(blob_tokens)))
            scored = ImageCandidate(
                title=cand.title,
                page_url=cand.page_url,
                image_url=cand.image_url,
                thumb_url=cand.thumb_url,
                description=cand.description,
                categories=cand.categories,
                artist=cand.artist,
                license=cand.license,
                width=cand.width,
                height=cand.height,
                score=score,
                reasons=[f"local_overlap={score:.2f}", f"tokens={overlap}"],
            )
            ranked.append((score, scored))

        ranked.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in ranked[:limit]]
