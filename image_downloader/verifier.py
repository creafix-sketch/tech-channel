"""Score and reject image candidates that do not match the segment subject.

Policy: never pick a wrong image. Low-confidence matches are rejected so the
pipeline can flag the beat for manual review instead of shipping a mismatch.
"""

from __future__ import annotations

import re

from .models import ImageCandidate
from .query_builder import QueryPlan

# Titles/categories that often look related but are wrong for literal B-roll.
_NEGATIVE_HINTS = (
    "logo only",
    "wordmark",
    "svg",
    "icon",
    "map of",
    "coat of arms",
    "flag of",
    "qr code",
    "screenshot of wikipedia",
)


def score_candidate(candidate: ImageCandidate, plan: QueryPlan) -> ImageCandidate:
    title_blob = candidate.title.lower()
    blob = " ".join(
        [
            candidate.title,
            candidate.description,
            " ".join(candidate.categories),
        ]
    ).lower()

    score = 0.0
    reasons: list[str] = []

    tokens = plan.must_include_tokens
    # Prefer the primary subject's own tokens for hard matching.
    primary_tokens = _significant_tokens(plan.primary_subject) or tokens

    if primary_tokens:
        hits = [t for t in primary_tokens if t in blob]
        miss = [t for t in primary_tokens if t not in blob]
        if hits:
            ratio = len(hits) / len(primary_tokens)
            score += 0.55 * ratio
            reasons.append(f"token_hits={hits}")
        if miss and len(miss) == len(primary_tokens):
            score -= 0.7
            reasons.append(f"missing_all_tokens={miss}")
        elif miss:
            score -= 0.2 * (len(miss) / len(primary_tokens))
            reasons.append(f"missing_tokens={miss}")

        # Title must usually carry the primary subject — categories alone are weak.
        title_hits = [t for t in primary_tokens if t in title_blob]
        if len(title_hits) >= max(1, (len(primary_tokens) + 1) // 2):
            score += 0.25
            reasons.append(f"title_token_hits={title_hits}")
        else:
            score -= 0.2
            reasons.append("weak_title_match")
    else:
        score -= 0.2
        reasons.append("no_required_tokens")

    # Subject phrase match is a strong signal.
    subject = plan.primary_subject.lower().strip()
    if subject and subject in blob:
        score += 0.35
        reasons.append("subject_phrase_match")
        if subject in title_blob:
            score += 0.2
            reasons.append("subject_in_title")
    else:
        # Partial phrase: majority of subject words present.
        subject_words = [w for w in re.findall(r"[a-z0-9]+", subject) if len(w) > 2]
        if subject_words:
            present = sum(1 for w in subject_words if w in blob)
            if present / len(subject_words) >= 0.6:
                score += 0.12
                reasons.append("partial_subject_match")

    # Prefer photos/scans over diagrams when categories suggest photos.
    photoish = any(
        k in blob
        for k in ("photograph", "photo", "portrait", "museum", "archive", "scan")
    )
    if photoish:
        score += 0.08
        reasons.append("photo_or_archive")

    for bad in _NEGATIVE_HINTS:
        if bad in blob:
            score -= 0.35
            reasons.append(f"negative:{bad}")

    # Mild preference for larger images (better B-roll).
    px = candidate.width * candidate.height
    if px >= 1_500_000:
        score += 0.05
    elif px < 400_000:
        score -= 0.05

    # Bias with how concrete the query plan was.
    score += 0.1 * plan.confidence_hint

    candidate.score = round(score, 4)
    candidate.reasons = reasons
    return candidate


def _significant_tokens(subject: str) -> list[str]:
    parts = re.findall(r"[a-z0-9]+", subject.lower())
    stop = {
        "a", "an", "the", "of", "and", "or", "in", "at", "for", "to", "computer",
        "computers", "historic", "history", "early", "personal",
    }
    # Keep "computer" only when it's the whole subject; otherwise drop filler nouns.
    tokens = [p for p in parts if len(p) > 1 and p not in stop]
    # If filtering removed everything (e.g. subject == "computer"), keep originals.
    return tokens or [p for p in parts if len(p) > 1]


def pick_best(
    candidates: list[ImageCandidate],
    plan: QueryPlan,
    *,
    min_score: float = 0.55,
) -> tuple[ImageCandidate | None, list[ImageCandidate]]:
    """Return (best_or_None, scored_sorted). None means needs manual review."""
    scored = [score_candidate(c, plan) for c in candidates]
    scored.sort(key=lambda c: c.score, reverse=True)

    if not scored:
        return None, scored

    best = scored[0]
    primary_tokens = _significant_tokens(plan.primary_subject) or plan.must_include_tokens
    if primary_tokens:
        blob = f"{best.title} {best.description} {' '.join(best.categories)}".lower()
        title_blob = best.title.lower()
        hits = sum(1 for t in primary_tokens if t in blob)
        title_hits = sum(1 for t in primary_tokens if t in title_blob)
        # Hard gate: majority of primary tokens somewhere, and at least one in title.
        if hits < max(1, (len(primary_tokens) + 1) // 2):
            return None, scored
        if title_hits < 1:
            return None, scored

    if best.score < min_score:
        return None, scored

    return best, scored
