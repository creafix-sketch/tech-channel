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
    "aerynos",
    "endless os",
    "red star",
    "wikivoyage",
    "virus for",
    "malware",
    "ibm watson",
    "watson.",
    "gnukem",
    "breakanoid",
    "barrage",
    "xscreensaver",
    "vulkanstrasse",
    "seestrasse",
    "infosys",
    "equatex",
    "reclining man",
)

# Product/person phrases that must appear as phrases, not loose tokens.
_PHRASE_REQUIREMENTS: list[tuple[re.Pattern[str], re.Pattern[str]]] = [
    # Allow "OS/2", "OS-2", "OS2", and "OS 2" — but not "OS 2.0" (other products).
    (
        re.compile(r"os/?2", re.I),
        re.compile(r"\bos/?2\b|\bos-2\b|(?<![a-z])os2(?![a-z0-9])|\bos\s+2(?!\.\d)\b", re.I),
    ),
    (re.compile(r"iacobucci", re.I), re.compile(r"\biacobucci\b", re.I)),
    (re.compile(r"ps/?2", re.I), re.compile(r"\bps/?2\b|\bps2\b|\bps\s*2\b", re.I)),
    (re.compile(r"ms-?dos", re.I), re.compile(r"\bms-?dos\b|\bdos\b", re.I)),
    (re.compile(r"windows\s*nt", re.I), re.compile(r"\bwindows\s*nt\b|\bwinnt\b", re.I)),
    (re.compile(r"windows\s*95", re.I), re.compile(r"\bwindows\s*95\b|\bwin95\b", re.I)),
    (re.compile(r"windows\s*3", re.I), re.compile(r"\bwindows\s*3", re.I)),
    (re.compile(r"citrix", re.I), re.compile(r"\bcitrix\b", re.I)),
    (re.compile(r"bill gates", re.I), re.compile(r"\bbill\s+gates\b", re.I)),
]


def _word_present(token: str, blob: str) -> bool:
    """Match tokens as whole words — never as substrings ('ed' in 'cropped')."""
    token = token.lower().strip()
    if not token:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", blob) is not None


def _phrase_requirement_ok(subject: str, blob: str) -> bool:
    for subject_pat, require_pat in _PHRASE_REQUIREMENTS:
        if subject_pat.search(subject):
            return require_pat.search(blob) is not None
    return True


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

    # Hard phrase requirements for known products/people.
    if not _phrase_requirement_ok(plan.primary_subject, blob):
        candidate.score = -1.0
        candidate.reasons = ["phrase_requirement_failed"]
        return candidate

    tokens = plan.must_include_tokens
    primary_tokens = _significant_tokens(plan.primary_subject) or tokens

    if primary_tokens:
        hits = [t for t in primary_tokens if _word_present(t, blob)]
        miss = [t for t in primary_tokens if not _word_present(t, blob)]
        if hits:
            ratio = len(hits) / len(primary_tokens)
            score += 0.55 * ratio
            reasons.append(f"token_hits={hits}")
        if miss and len(miss) == len(primary_tokens):
            score -= 0.7
            reasons.append(f"missing_all_tokens={miss}")
        elif miss:
            score -= 0.25 * (len(miss) / len(primary_tokens))
            reasons.append(f"missing_tokens={miss}")

        # Title must usually carry the primary subject — categories alone are weak.
        title_hits = [t for t in primary_tokens if _word_present(t, title_blob)]
        if len(title_hits) >= max(1, (len(primary_tokens) + 1) // 2):
            score += 0.25
            reasons.append(f"title_token_hits={title_hits}")
        else:
            score -= 0.25
            reasons.append("weak_title_match")
    else:
        score -= 0.2
        reasons.append("no_required_tokens")

    subject = plan.primary_subject.lower().strip()
    if subject and subject in blob:
        score += 0.35
        reasons.append("subject_phrase_match")
        if subject in title_blob:
            score += 0.2
            reasons.append("subject_in_title")
    else:
        subject_words = [w for w in re.findall(r"[a-z0-9]+", subject) if len(w) > 2]
        if subject_words:
            present = sum(1 for w in subject_words if _word_present(w, blob))
            if present / len(subject_words) >= 0.6:
                score += 0.12
                reasons.append("partial_subject_match")

    photoish = any(
        k in blob
        for k in ("photograph", "photo", "portrait", "museum", "archive", "scan")
    )
    if photoish:
        score += 0.08
        reasons.append("photo_or_archive")

    for bad in _NEGATIVE_HINTS:
        if bad in blob:
            score -= 0.45
            reasons.append(f"negative:{bad}")

    px = candidate.width * candidate.height
    if px >= 1_500_000:
        score += 0.05
    elif px < 400_000:
        score -= 0.05

    score += 0.1 * plan.confidence_hint

    candidate.score = round(score, 4)
    candidate.reasons = reasons
    return candidate


def _significant_tokens(subject: str) -> list[str]:
    parts = re.findall(r"[a-z0-9]+", subject.lower())
    stop = {
        "a", "an", "the", "of", "and", "or", "in", "at", "for", "to", "computer",
        "computers", "historic", "history", "early", "personal", "operating",
        "system", "software", "machine", "installation",
    }
    # Drop ultra-short tokens that are substring hazards unless alphanumeric product ids.
    tokens = [p for p in parts if p not in stop and (len(p) > 2 or p.isdigit())]
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
    if best.score < 0:
        return None, scored

    blob = f"{best.title} {best.description} {' '.join(best.categories)}".lower()
    title_blob = best.title.lower()

    if not _phrase_requirement_ok(plan.primary_subject, blob):
        return None, scored

    primary_tokens = _significant_tokens(plan.primary_subject) or plan.must_include_tokens
    if primary_tokens:
        hits = sum(1 for t in primary_tokens if _word_present(t, blob))
        title_hits = sum(1 for t in primary_tokens if _word_present(t, title_blob))
        if hits < max(1, (len(primary_tokens) + 1) // 2):
            return None, scored
        if title_hits < 1:
            return None, scored

    # Never soft-accept when a required surname/product token is missing.
    must = plan.must_include_tokens
    if must:
        critical = [t for t in must if len(t) > 3]
        if critical and not any(_word_present(t, blob) for t in critical):
            return None, scored

    if best.score < min_score:
        return None, scored

    return best, scored
