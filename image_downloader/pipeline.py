"""End-to-end pipeline: script → segments → verified UNIQUE images.

Coverage strategy (in order):
1. Wikimedia Commons + Openverse + Wikipedia page images (free)
2. Optional Google CSE / SerpAPI if API keys are set
3. Optional local image library (user-collected fills)
4. Remaining empties get a missing_beats checklist with Google Image links

Hard policy:
- Never reuse the same image URL (or local path) in one run
- Never ship a clearly wrong match — leave empty instead
- Cap lookalike families so one topic does not spam near-identical frames
"""

from __future__ import annotations

from pathlib import Path

from .concepts import concept_tokens_for_text, visual_queries_for_text
from .local_library import LocalLibrary
from .lookalike import LookalikeLimiter, image_family
from .missing import write_missing_beats
from .models import ImageCandidate, SegmentResult
from .normalize import normalize_script_text
from .openverse import OpenverseClient
from .query_builder import QueryPlan, build_query_plan
from .segmenter import segment_script
from .verifier import pick_best, score_candidate
from .web_search_provider import GoogleCseClient, SerpApiClient, web_search_enabled
from .wikimedia import WikimediaClient
from .wikipedia_provider import WikipediaImageClient


class _NoopSearcher:
    def search_candidates(self, query: str, *, limit: int = 12):
        return []


def _empty_result(segment, plan: QueryPlan, *, candidates=None, notes: str) -> SegmentResult:
    return SegmentResult(
        segment=segment,
        queries=plan.queries,
        primary_subject=plan.primary_subject,
        status="needs_manual_review",
        chosen=None,
        candidates=(candidates or [])[:5],
        notes=notes,
    )


def _gather_candidates(
    *,
    queries: list[str],
    searchers: list,
    seen_urls: set[str],
    limiter: LookalikeLimiter,
    search_limit: int,
    max_found: int = 36,
) -> list[ImageCandidate]:
    found: list[ImageCandidate] = []
    for query in queries:
        for client in searchers:
            try:
                hits = client.search_candidates(query, limit=search_limit)
            except Exception:
                hits = []
            for cand in hits:
                if cand.image_url in seen_urls:
                    continue
                if not limiter.allows(cand):
                    continue
                found.append(cand)
        if len(found) >= max_found:
            break
    uniq: dict[str, ImageCandidate] = {}
    for cand in found:
        uniq.setdefault(cand.image_url, cand)
    return list(uniq.values())


def run_pipeline(
    script: str,
    *,
    wpm: float = 150.0,
    min_sec: float = 5.0,
    max_sec: float = 7.0,
    target_sec: float = 6.0,
    min_score: float = 0.55,
    search_limit: int = 12,
    max_segments: int | None = None,
    client: WikimediaClient | None = None,
    cache_dir: Path | None = None,
    fast: bool = True,
    allow_reuse: bool = False,
    max_lookalikes: int | None = None,
    use_openverse: bool = True,
    use_wikipedia: bool = True,
    use_web_search: bool = True,
    local_library: Path | None = None,
) -> list[SegmentResult]:
    commons = client or WikimediaClient(
        cache_dir=cache_dir or Path(".cache/wikimedia"),
        fast=fast,
    )
    openverse: object = OpenverseClient() if use_openverse else _NoopSearcher()
    wikipedia: object = WikipediaImageClient() if use_wikipedia else _NoopSearcher()
    web_clients: list = []
    if use_web_search and web_search_enabled():
        for cls in (GoogleCseClient, SerpApiClient):
            provider = cls()
            if getattr(provider, "enabled", False):
                web_clients.append(provider)

    free_searchers = [commons, openverse, wikipedia]
    library = LocalLibrary(local_library) if local_library else None

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

    last_concrete_plan: QueryPlan | None = None

    for segment in segments:
        search_text = normalize_script_text(segment.text)
        plan = build_query_plan(search_text)

        # Abstract beat: still search concept visuals + last concrete subject,
        # but only accept a NEW unique image (never reuse).
        concept_qs = visual_queries_for_text(search_text)
        queries = list(plan.queries)
        for q in concept_qs:
            if q not in queries:
                queries.append(q)

        if plan.confidence_hint < 0.5:
            if last_concrete_plan is not None:
                for q in last_concrete_plan.queries:
                    if q not in queries:
                        queries.append(q)
                concept_tokens = concept_tokens_for_text(search_text)
                if concept_tokens:
                    plan = QueryPlan(
                        primary_subject=concept_qs[0]
                        if concept_qs
                        else last_concrete_plan.primary_subject,
                        queries=queries,
                        must_include_tokens=concept_tokens[:4]
                        or last_concrete_plan.must_include_tokens,
                        confidence_hint=0.6,
                    )
                else:
                    plan = QueryPlan(
                        primary_subject=last_concrete_plan.primary_subject,
                        queries=queries,
                        must_include_tokens=last_concrete_plan.must_include_tokens,
                        confidence_hint=0.6,
                    )
            elif concept_qs:
                plan = QueryPlan(
                    primary_subject=concept_qs[0],
                    queries=queries,
                    must_include_tokens=concept_tokens_for_text(search_text)[:4],
                    confidence_hint=0.6,
                )
            else:
                results.append(
                    _empty_result(
                        segment,
                        plan,
                        notes=(
                            "No concrete subject or visual concept found. "
                            "See missing_beats.md for a Google Images link."
                        ),
                    )
                )
                continue

        searchers = [*free_searchers, *web_clients]
        candidates = _gather_candidates(
            queries=queries[:8],
            searchers=searchers,
            seen_urls=seen_urls if not allow_reuse else set(),
            limiter=limiter,
            search_limit=search_limit,
        )

        best, scored = pick_best(candidates, plan, min_score=min_score)

        # Soft pass for concept visuals: require at least one concept token in title/desc.
        if best is None and concept_qs:
            concept_tokens = concept_tokens_for_text(search_text)
            ranked = [score_candidate(c, plan) for c in candidates]
            ranked.sort(key=lambda c: c.score, reverse=True)
            for cand in ranked:
                blob = f"{cand.title} {cand.description}".lower()
                if concept_tokens and not any(t in blob for t in concept_tokens):
                    continue
                if cand.score >= max(0.35, min_score - 0.2) and limiter.allows(cand):
                    best = cand
                    scored = ranked
                    break

        # Local library fill for remaining empties
        if best is None and library is not None:
            local_hits = library.search_candidates(queries[:8], limit=8)
            local_hits = [c for c in local_hits if c.image_url not in seen_urls]
            if local_hits:
                # Local files are user-curated — softer gate, still unique
                local_hits.sort(key=lambda c: c.score, reverse=True)
                if local_hits[0].score >= 0.25:
                    best = local_hits[0]
                    scored = local_hits

        if best is None:
            results.append(
                _empty_result(
                    segment,
                    plan,
                    candidates=scored,
                    notes=(
                        "No unique verified image — see missing_beats.md "
                        "for a Google Images link"
                    ),
                )
            )
            continue

        if not allow_reuse:
            seen_urls.add(best.image_url)
        if library is not None and "local_library" in (best.categories or []):
            library.mark_used(best.image_url)
        limiter.record(best)
        if plan.confidence_hint >= 0.7:
            last_concrete_plan = plan

        results.append(
            SegmentResult(
                segment=segment,
                queries=queries[:8],
                primary_subject=plan.primary_subject,
                status="matched",
                chosen=best,
                candidates=scored[:5],
                notes=f"Verified unique match (family={image_family(best)}).",
            )
        )

    return results


def save_pipeline_outputs(
    results: list[SegmentResult],
    output_dir: Path,
    *,
    download: bool = True,
    workers: int = 4,
    full_size: bool = False,
) -> Path:
    """Save downloads + manifest + missing-beats checklist."""
    from .downloader import save_results

    manifest = save_results(
        results,
        output_dir,
        download=download,
        workers=workers,
        full_size=full_size,
    )
    write_missing_beats(results, output_dir)
    return manifest
