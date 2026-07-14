"""End-to-end pipeline: script → segments → verified UNIQUE images.

Hard policy:
- Never reuse the same image URL in one run.
- Never ship a weak/wrong match — leave the beat empty instead.
- Cap lookalike families (e.g. max a few DOS-disk photos per video).
"""

from __future__ import annotations

from pathlib import Path

from .lookalike import LookalikeLimiter, image_family
from .models import SegmentResult
from .normalize import normalize_script_text
from .query_builder import QueryPlan, build_query_plan
from .segmenter import segment_script
from .verifier import pick_best
from .wikimedia import WikimediaClient


def _tokens_for(subject: str) -> list[str]:
    import re

    parts = re.findall(r"[A-Za-z0-9]+", subject.lower())
    return [p for p in parts if len(p) > 1][:6]


def _empty_result(
    segment,
    plan: QueryPlan,
    *,
    candidates=None,
    notes: str,
) -> SegmentResult:
    return SegmentResult(
        segment=segment,
        queries=plan.queries,
        primary_subject=plan.primary_subject,
        status="needs_manual_review",
        chosen=None,
        candidates=(candidates or [])[:5],
        notes=notes,
    )


def run_pipeline(
    script: str,
    *,
    wpm: float = 150.0,
    min_sec: float = 5.0,
    max_sec: float = 7.0,
    target_sec: float = 6.0,
    min_score: float = 0.65,
    search_limit: int = 10,
    max_segments: int | None = None,
    client: WikimediaClient | None = None,
    cache_dir: Path | None = None,
    fast: bool = True,
    allow_reuse: bool = False,
    max_lookalikes: int | None = None,
) -> list[SegmentResult]:
    """
    allow_reuse: if False (default), each image URL may appear only once.
    max_lookalikes: optional override cap applied to all families.
    """
    client = client or WikimediaClient(
        cache_dir=cache_dir or Path(".cache/wikimedia"),
        fast=fast,
    )
    segments = segment_script(
        script,
        wpm=wpm,
        min_sec=min_sec,
        max_sec=max_sec,
        target_sec=target_sec,
    )
    if max_segments is not None:
        segments = segments[: max(0, max_segments)]

    results: list[SegmentResult] = []
    seen_urls: set[str] = set()
    limiter = LookalikeLimiter()
    if max_lookalikes is not None:
        limiter.caps = {k: max_lookalikes for k in limiter.caps}

    for segment in segments:
        search_text = normalize_script_text(segment.text)
        plan = build_query_plan(search_text)

        # Abstract beats with no concrete subject: leave empty rather than guess.
        if plan.confidence_hint < 0.5:
            results.append(
                _empty_result(
                    segment,
                    plan,
                    notes=(
                        "Abstract narration beat with no concrete visual subject. "
                        "Left empty rather than invent unrelated B-roll."
                    ),
                )
            )
            continue

        all_candidates = []
        for i, query in enumerate(plan.queries):
            found = client.search_candidates(query, limit=search_limit)
            for cand in found:
                if not allow_reuse and cand.image_url in seen_urls:
                    continue
                if not limiter.allows(cand):
                    continue
                all_candidates.append(cand)
            if i == 0 and all_candidates:
                prelim_best, _ = pick_best(all_candidates, plan, min_score=min_score)
                if prelim_best is not None:
                    break

        uniq = {}
        for cand in all_candidates:
            uniq.setdefault(cand.image_url, cand)
        candidates = list(uniq.values())

        best, scored = pick_best(candidates, plan, min_score=min_score)

        # Try alternate known-subject queries, still unique + lookalike-capped.
        if best is None:
            for alt in plan.queries[1:4]:
                alt_plan = build_query_plan(alt)
                if alt_plan.confidence_hint < 0.7:
                    alt_plan = QueryPlan(
                        primary_subject=alt,
                        queries=[alt],
                        must_include_tokens=_tokens_for(alt),
                        confidence_hint=0.85,
                    )
                alt_cands = []
                for cand in client.search_candidates(alt, limit=search_limit):
                    if not allow_reuse and cand.image_url in seen_urls:
                        continue
                    if not limiter.allows(cand):
                        continue
                    alt_cands.append(cand)
                alt_best, alt_scored = pick_best(alt_cands, alt_plan, min_score=min_score)
                if alt_best is not None:
                    best, scored, plan = alt_best, alt_scored, alt_plan
                    break

        if best is None:
            results.append(
                _empty_result(
                    segment,
                    plan,
                    candidates=scored,
                    notes=(
                        "No unique, high-confidence, non-lookalike match. "
                        "Left empty rather than use a weak/wrong image."
                    ),
                )
            )
            continue

        if not allow_reuse:
            seen_urls.add(best.image_url)
        limiter.record(best)

        results.append(
            SegmentResult(
                segment=segment,
                queries=plan.queries,
                primary_subject=plan.primary_subject,
                status="matched",
                chosen=best,
                candidates=scored[:5],
                notes=(
                    f"Verified unique match (family={image_family(best)})."
                ),
            )
        )

    return results
