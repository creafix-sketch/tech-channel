"""Export missing beats as a fill checklist with ready-to-use search queries."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote_plus

from .concepts import visual_queries_for_text
from .models import SegmentResult
from .normalize import normalize_script_text


def write_missing_beats(results: list[SegmentResult], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    missing = [r for r in results if r.status != "matched" or not r.chosen]
    path = output_dir / "missing_beats.md"
    lines = [
        "# Missing beats — fill these for 100% coverage",
        "",
        "The auto-fetcher only uses free/safe sources by default. For full coverage,",
        "search these queries (Google Images / archives), download unique images,",
        "and drop them into a local library folder named with keywords, then re-run:",
        "",
        "```bash",
        "python -m image_downloader SCRIPT.txt -o output/run --local-library ./my_images",
        "```",
        "",
        f"Missing: **{len(missing)}** / {len(results)}",
        "",
    ]
    for r in missing:
        seg = r.segment
        norm = normalize_script_text(seg.text)
        queries = list(r.queries) + visual_queries_for_text(norm)
        # de-dupe preserve order
        seen = set()
        q_out = []
        for q in queries:
            if q and q.lower() not in seen:
                seen.add(q.lower())
                q_out.append(q)
        lines.append(
            f"## Beat {seg.index:03d}  ({seg.start_sec:.1f}s–{seg.end_sec:.1f}s)"
        )
        lines.append(f"- Script: {seg.text}")
        lines.append(f"- Subject: {r.primary_subject}")
        lines.append(f"- Why empty: {r.notes or 'no unique relevant free match'}")
        lines.append("- Suggested searches:")
        for q in q_out[:6]:
            g = f"https://www.google.com/search?tbm=isch&q={quote_plus(q)}"
            lines.append(f"  - [{q}]({g})")
        lines.append(
            f"- Suggested local filename: "
            f"`{seg.index:03d}_{r.primary_subject.lower().replace(' ', '-')[:40]}.jpg`"
        )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")

    # Also CSV for spreadsheets
    csv_path = output_dir / "missing_beats.csv"
    rows = ["index,start_sec,end_sec,subject,query1,query2,google1,script"]
    for r in missing:
        seg = r.segment
        norm = normalize_script_text(seg.text)
        queries = list(r.queries) + visual_queries_for_text(norm)
        q1 = queries[0] if queries else r.primary_subject
        q2 = queries[1] if len(queries) > 1 else ""
        g1 = f"https://www.google.com/search?tbm=isch&q={quote_plus(q1)}"
        script = seg.text.replace('"', "'")
        rows.append(
            ",".join(
                [
                    str(seg.index),
                    f"{seg.start_sec:.2f}",
                    f"{seg.end_sec:.2f}",
                    f"\"{r.primary_subject}\"",
                    f"\"{q1}\"",
                    f"\"{q2}\"",
                    f"\"{g1}\"",
                    f"\"{script}\"",
                ]
            )
        )
    csv_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path
