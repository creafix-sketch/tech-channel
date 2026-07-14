"""Download chosen images and write a production-ready manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from .models import SegmentResult

USER_AGENT = (
    "ScriptImageDownloader/0.1 "
    "(YouTube computing-history B-roll helper; contact: local-tool)"
)


def _safe_slug(text: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug or "image")[:max_len]


def download_image(
    url: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
    max_attempts: int = 5,
) -> Path:
    import time

    sess = session or requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            with sess.get(url, stream=True, timeout=60) as resp:
                if resp.status_code == 429:
                    wait = min(45.0, (2 ** attempt) * 2.0)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with dest.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)
            return dest
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(30.0, (2 ** attempt) * 1.5))
    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to download {url}")


def extension_from_url(url: str) -> str:
    path = url.split("?", 1)[0]
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}:
        return suffix
    return ".jpg"


def save_results(
    results: list[SegmentResult],
    output_dir: Path,
    *,
    download: bool = True,
    session: requests.Session | None = None,
) -> Path:
    """Download matched images and write manifest.json + attributions.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    sess = session or requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})

    for result in results:
        if not download or result.status != "matched" or not result.chosen:
            continue
        chosen = result.chosen
        start = int(result.segment.start_sec)
        end = int(result.segment.end_sec)
        slug = _safe_slug(result.primary_subject or chosen.title)
        ext = extension_from_url(chosen.image_url)
        filename = f"{result.segment.index:03d}_{start:04d}-{end:04d}_{slug}{ext}"
        path = images_dir / filename
        try:
            download_image(chosen.image_url, path, session=sess)
            result.local_path = str(path.relative_to(output_dir))
            import time

            time.sleep(0.75)  # be polite to upload.wikimedia.org
        except requests.RequestException as exc:
            result.status = "needs_manual_review"
            result.notes = f"Download failed: {exc}"
            result.local_path = None

    manifest_path = output_dir / "manifest.json"
    payload = {
        "segment_count": len(results),
        "matched": sum(1 for r in results if r.status == "matched"),
        "needs_manual_review": sum(
            1 for r in results if r.status == "needs_manual_review"
        ),
        "segments": [r.to_dict() for r in results],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    attr_path = output_dir / "attributions.md"
    lines = [
        "# Image attributions",
        "",
        "Images sourced from Wikimedia Commons. Check each license before publishing.",
        "",
    ]
    for result in results:
        seg = result.segment
        lines.append(
            f"## Segment {seg.index:03d} ({seg.start_sec:.1f}s–{seg.end_sec:.1f}s) — {result.status}"
        )
        lines.append(f"- Script: {seg.text}")
        lines.append(f"- Subject: {result.primary_subject}")
        if result.chosen:
            c = result.chosen
            lines.append(f"- File: `{result.local_path or '(not downloaded)'}`")
            lines.append(f"- Title: {c.title}")
            lines.append(f"- Commons: {c.page_url}")
            lines.append(f"- Artist: {c.artist or 'n/a'}")
            lines.append(f"- License: {c.license or 'n/a'}")
            lines.append(f"- Score: {c.score}")
        if result.notes:
            lines.append(f"- Notes: {result.notes}")
        lines.append("")
    attr_path.write_text("\n".join(lines), encoding="utf-8")

    # Timeline helper for editors
    timeline_path = output_dir / "timeline.csv"
    rows = ["index,start_sec,end_sec,status,subject,local_path,commons_url,script"]
    for result in results:
        c = result.chosen
        script = result.segment.text.replace('"', "'")
        rows.append(
            ",".join(
                [
                    str(result.segment.index),
                    f"{result.segment.start_sec:.2f}",
                    f"{result.segment.end_sec:.2f}",
                    result.status,
                    f"\"{result.primary_subject}\"",
                    f"\"{result.local_path or ''}\"",
                    f"\"{c.page_url if c else ''}\"",
                    f"\"{script}\"",
                ]
            )
        )
    timeline_path.write_text("\n".join(rows) + "\n", encoding="utf-8")

    return manifest_path
