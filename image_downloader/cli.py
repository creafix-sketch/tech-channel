"""CLI for script image downloader."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .downloader import save_results
from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="script-images",
        description=(
            "Segment a YouTube script into ~5–7s beats and download one "
            "historically relevant Wikimedia Commons image per beat. "
            "Low-confidence matches are refused rather than guessed."
        ),
    )
    p.add_argument(
        "script",
        type=Path,
        help="Path to the video script (.txt)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output"),
        help="Output directory (default: ./output)",
    )
    p.add_argument(
        "--wpm",
        type=float,
        default=150.0,
        help="Narration words-per-minute for timing (default: 150)",
    )
    p.add_argument(
        "--min-sec",
        type=float,
        default=5.0,
        help="Minimum seconds per image beat (default: 5)",
    )
    p.add_argument(
        "--max-sec",
        type=float,
        default=7.0,
        help="Maximum seconds per image beat (default: 7)",
    )
    p.add_argument(
        "--target-sec",
        type=float,
        default=6.0,
        help="Target seconds per image beat (default: 6)",
    )
    p.add_argument(
        "--min-score",
        type=float,
        default=0.55,
        help="Minimum relevance score to accept an image (default: 0.55)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N segments (useful for testing)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Segment + search + score only; do not download image files",
    )
    p.add_argument(
        "--plan-only",
        action="store_true",
        help="Only segment the script and print the beat plan (no network)",
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel download workers (default: 4, max useful ~6)",
    )
    p.add_argument(
        "--full-size",
        action="store_true",
        help="Download original Commons files instead of 1280px thumbnails",
    )
    p.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/wikimedia"),
        help="Disk cache for Commons search results (default: .cache/wikimedia)",
    )
    p.add_argument(
        "--slow",
        action="store_true",
        help="More polite pacing (use if you still hit 429s)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()

    if not args.script.exists():
        console.print(f"[red]Script not found:[/red] {args.script}")
        return 1

    script = args.script.read_text(encoding="utf-8")
    if not script.strip():
        console.print("[red]Script file is empty.[/red]")
        return 1

    if args.plan_only:
        from .normalize import normalize_script_text
        from .query_builder import build_query_plan
        from .segmenter import segment_script

        segments = segment_script(
            script,
            wpm=args.wpm,
            min_sec=args.min_sec,
            max_sec=args.max_sec,
            target_sec=args.target_sec,
        )
        table = Table(title="Segment plan")
        table.add_column("#", justify="right")
        table.add_column("Time")
        table.add_column("Sec", justify="right")
        table.add_column("Subject")
        table.add_column("Script")
        for seg in segments[: args.limit] if args.limit else segments:
            plan = build_query_plan(normalize_script_text(seg.text))
            table.add_row(
                str(seg.index),
                f"{seg.start_sec:.1f}–{seg.end_sec:.1f}",
                f"{seg.duration_sec:.1f}",
                plan.primary_subject,
                seg.text[:80] + ("…" if len(seg.text) > 80 else ""),
            )
        shown = segments[: args.limit] if args.limit else segments
        console.print(table)
        console.print(f"\n{len(shown)} beats · target {args.target_sec}s · {args.wpm} wpm")
        return 0

    console.print("[bold]Searching Wikimedia Commons…[/bold] (prefer accuracy over coverage)")
    results = run_pipeline(
        script,
        wpm=args.wpm,
        min_sec=args.min_sec,
        max_sec=args.max_sec,
        target_sec=args.target_sec,
        min_score=args.min_score,
        max_segments=args.limit,
        cache_dir=args.cache_dir,
        fast=not args.slow,
    )

    manifest = save_results(
        results,
        args.output,
        download=not args.dry_run,
        workers=args.workers,
        full_size=args.full_size,
    )

    table = Table(title="Results")
    table.add_column("#", justify="right")
    table.add_column("Time")
    table.add_column("Status")
    table.add_column("Subject")
    table.add_column("Image / note")
    for r in results:
        label = ""
        if r.chosen:
            label = r.chosen.title[:60]
        elif r.notes:
            label = r.notes[:60]
        status_style = {
            "matched": "green",
            "needs_manual_review": "yellow",
            "skipped": "dim",
        }.get(r.status, "white")
        table.add_row(
            str(r.segment.index),
            f"{r.segment.start_sec:.1f}–{r.segment.end_sec:.1f}",
            f"[{status_style}]{r.status}[/{status_style}]",
            r.primary_subject[:40],
            label,
        )
    console.print(table)

    matched = sum(1 for r in results if r.status == "matched")
    review = sum(1 for r in results if r.status == "needs_manual_review")
    console.print(
        f"\nMatched [green]{matched}[/green] · "
        f"Needs review [yellow]{review}[/yellow] · "
        f"Manifest: {manifest}"
    )
    if review:
        console.print(
            "[yellow]Beats marked needs_manual_review were intentionally left empty "
            "to avoid wrong B-roll.[/yellow]"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
