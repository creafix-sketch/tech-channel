"""Download chosen images and write a production-ready manifest."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

from .models import SegmentResult

USER_AGENT = (
    "ScriptImageDownloader/0.2 "
    "(https://github.com/creafix-sketch/tech-channel; computing-history B-roll helper)"
)


def _safe_slug(text: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return (slug or "image")[:max_len]


def download_image(
    url: str,
    dest: Path,
    *,
    session: requests.Session | None = None,
    max_attempts: int = 6,
) -> Path:
    sess = session or requests.Session()
    sess.headers.update({"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            with sess.get(url, stream=True, timeout=60) as resp:
                if resp.status_code == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after and retry_after.isdigit() else min(
                        30.0, (2 ** attempt) * 2.0
                    )
                    last_error = requests.HTTPError(
                        f"429 Too Many Requests downloading {url}",
                        response=resp,
                    )
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_suffix(dest.suffix + ".partial")
                with tmp.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 64):
                        if chunk:
                            f.write(chunk)
                tmp.replace(dest)
            return dest
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(15.0, (2 ** attempt) * 1.0))
    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to download {url}")


def extension_from_url(url: str) -> str:
    path = url.split("?", 1)[0]
    suffix = Path(path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff"}:
        return suffix
    return ".jpg"


def _best_url(chosen, *, full_size: bool) -> str:
    if full_size:
        return chosen.image_url
    return chosen.thumb_url or chosen.image_url


def save_results(
    results: list[SegmentResult],
    output_dir: Path,
    *,
    download: bool = True,
    session: requests.Session | None = None,
    workers: int = 4,
    full_size: bool = False,
) -> Path:
    """Download matched images and write manifest.json + attributions.md.

    Speed strategy:
    1. Prefer 1280px Commons thumbnails (much smaller than originals).
    2. Download each unique URL once, in parallel.
    3. Copy that file into every beat that reused the same image.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"

    if download:
        jobs: dict[str, list[tuple[SegmentResult, Path]]] = {}
        for result in results:
            if result.status != "matched" or not result.chosen:
                continue
            chosen = result.chosen
            start = int(result.segment.start_sec)
            end = int(result.segment.end_sec)
            slug = _safe_slug(result.primary_subject or chosen.title)
            url = _best_url(chosen, full_size=full_size)
            ext = extension_from_url(url)
            filename = f"{result.segment.index:03d}_{start:04d}-{end:04d}_{slug}{ext}"
            path = images_dir / filename
            jobs.setdefault(url, []).append((result, path))

        images_dir.mkdir(parents=True, exist_ok=True)
        masters_dir = images_dir / "_masters"
        masters_dir.mkdir(parents=True, exist_ok=True)
        url_to_master: dict[str, Path] = {}

        def _fetch(url: str) -> tuple[str, Path | None, str | None]:
            digest = hashlib.sha1(url.encode()).hexdigest()[:16]
            master = masters_dir / f"{digest}{extension_from_url(url)}"
            try:
                # Fresh session per worker avoids shared-connection contention.
                download_image(url, master, session=requests.Session())
                return url, master, None
            except Exception as exc:  # noqa: BLE001
                return url, None, str(exc)

        workers = max(1, min(workers, 8))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fetch, url) for url in jobs]
            for fut in as_completed(futures):
                url, master, err = fut.result()
                if master is not None:
                    url_to_master[url] = master
                else:
                    for result, _path in jobs[url]:
                        result.status = "needs_manual_review"
                        result.notes = f"Download failed: {err}"
                        result.local_path = None

        for url, items in jobs.items():
            master = url_to_master.get(url)
            if not master:
                continue
            for result, dest in items:
                shutil.copy2(master, dest)
                result.local_path = str(dest.relative_to(output_dir))

        # Masters are an implementation detail; remove after copies.
        shutil.rmtree(masters_dir, ignore_errors=True)

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
