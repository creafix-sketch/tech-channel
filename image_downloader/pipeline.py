"""End-to-end pipeline: script → segments → queries → verified images."""

from __future__ import annotations

from .models import SegmentResult
from .normalize import normalize_script_text
from .query_builder import build_query_plan
from .segmenter import segment_script
from .verifier import pick_best
from .wikimedia import WikimediaClient


def run_pipeline(
    script: str,
    *,
    wpm: float = 150.0,
    min_sec: float = 5.0,
    max_sec: float = 7.0,
    target_sec: float = 6.0,
    min_score: float = 0.55,
    search_limit: int = 8,
    max_segments: int | None = None,
    client: WikimediaClient | None = None,
) -> list[SegmentResult]:
    client = client or WikimediaClient()
    # Keep original wording in segments for the editor, but search against
    # phonetically normalized text so "O-S Two" finds OS/2 images.
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
    last_concrete_plan = None

    for segment in segments:
        search_text = normalize_script_text(segment.text)
        plan = build_query_plan(search_text)
        continuation = False
        # Abstract narration beats: keep showing the last concrete subject
        # rather than inventing a vague keyword image.
        if plan.confidence_hint < 0.5 and last_concrete_plan is not None:
            plan = last_concrete_plan
            continuation = True

        all_candidates = []
        # Search primary subject first; only widen if needed for coverage.
        for i, query in enumerate(plan.queries):
            found = client.search_candidates(query, limit=search_limit)
            for cand in found:
                # Prefer unseen images; continuations may reuse a prior shot.
                if cand.image_url in seen_urls and not continuation:
                    continue
                all_candidates.append(cand)
            if i == 0 and all_candidates:
                prelim_best, _ = pick_best(all_candidates, plan, min_score=min_score)
                if prelim_best is not None:
                    break

        # Deduplicate by image URL within this segment.
        uniq = {}
        for cand in all_candidates:
            uniq.setdefault(cand.image_url, cand)
        candidates = list(uniq.values())

        best, scored = pick_best(candidates, plan, min_score=min_score)

        if best is None:
            if plan.confidence_hint >= 0.85 and scored and scored[0].score >= min_score - 0.05:
                soft_best, scored = pick_best(candidates, plan, min_score=min_score - 0.05)
                best = soft_best

        # If Commons has few unique files for this subject, reuse a prior
        # matching image rather than leaving a concrete beat empty.
        if best is None and plan.confidence_hint >= 0.7:
            reused = []
            for query in plan.queries[:2]:
                for cand in client.search_candidates(query, limit=search_limit):
                    reused.append(cand)
            reuse_uniq = {}
            for cand in reused:
                reuse_uniq.setdefault(cand.image_url, cand)
            best, scored = pick_best(list(reuse_uniq.values()), plan, min_score=min_score)
            if best is not None:
                continuation = True

        if best is None:
            # Still remember concrete subjects so later abstract beats can continue.
            if plan.confidence_hint >= 0.85 and not continuation:
                last_concrete_plan = plan
            results.append(
                SegmentResult(
                    segment=segment,
                    queries=plan.queries,
                    primary_subject=plan.primary_subject,
                    status="needs_manual_review",
                    chosen=None,
                    candidates=scored[:5],
                    notes=(
                        "No high-confidence Commons match. "
                        "Refusing to guess — review manually."
                    ),
                )
            )
            continue

        if plan.confidence_hint >= 0.85 and not continuation:
            last_concrete_plan = plan

        seen_urls.add(best.image_url)
        note = "Verified against segment subject tokens."
        if continuation:
            note = (
                "Continued/reused subject "
                f"({plan.primary_subject}) for B-roll continuity."
            )
        results.append(
            SegmentResult(
                segment=segment,
                queries=plan.queries,
                primary_subject=plan.primary_subject,
                status="matched",
                chosen=best,
                candidates=scored[:5],
                notes=note,
            )
        )

    return results
