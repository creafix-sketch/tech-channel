"""Split narration into ~5–7 second visual beats."""

from __future__ import annotations

import re

from .models import Segment

# Documentary / YouTube history narration is typically ~145–155 wpm.
DEFAULT_WORDS_PER_MINUTE = 150
MIN_SEGMENT_SEC = 5.0
MAX_SEGMENT_SEC = 7.0
TARGET_SEGMENT_SEC = 6.0

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE_SPLIT = re.compile(r"(?<=[,;:—–-])\s+")
_WORD_RE = re.compile(r"\b[\w''-]+\b")


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def estimate_seconds(text: str, wpm: float = DEFAULT_WORDS_PER_MINUTE) -> float:
    words = word_count(text)
    if words == 0:
        return 0.0
    return words / (wpm / 60.0)


def _split_sentences(script: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", script.strip())
    if not cleaned:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(cleaned) if p.strip()]
    return parts or [cleaned]


def _split_long_sentence(sentence: str, max_words: int) -> list[str]:
    words = _WORD_RE.findall(sentence)
    # Prefer keeping a sentence intact unless it is clearly too long for one beat.
    if len(words) <= int(max_words * 1.35):
        return [sentence.strip()]

    clauses = [c.strip() for c in _CLAUSE_SPLIT.split(sentence) if c.strip()]
    if len(clauses) > 1:
        chunks: list[str] = []
        buf: list[str] = []
        buf_words = 0
        for clause in clauses:
            cw = word_count(clause)
            if buf and buf_words + cw > max_words:
                chunks.append(" ".join(buf).strip())
                buf = [clause]
                buf_words = cw
            else:
                buf.append(clause)
                buf_words += cw
        if buf:
            chunks.append(" ".join(buf).strip())
        final: list[str] = []
        for chunk in chunks:
            if word_count(chunk) > max_words * 1.6:
                final.extend(_force_word_chunks(chunk, max_words))
            else:
                final.append(chunk)
        return final

    return _force_word_chunks(sentence, max_words)


def _force_word_chunks(text: str, max_words: int) -> list[str]:
    words = text.split()
    return [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]


def segment_script(
    script: str,
    *,
    wpm: float = DEFAULT_WORDS_PER_MINUTE,
    min_sec: float = MIN_SEGMENT_SEC,
    max_sec: float = MAX_SEGMENT_SEC,
    target_sec: float = TARGET_SEGMENT_SEC,
) -> list[Segment]:
    """
    Build timed segments targeting ~target_sec (clamped to min/max).

    Strategy:
    1. Split into sentences / clauses.
    2. Pack consecutive units until we'd exceed max_sec.
    3. Prefer packing near target_sec when possible.
    """
    if min_sec <= 0 or max_sec < min_sec or target_sec < min_sec or target_sec > max_sec:
        raise ValueError("Invalid segment timing bounds")

    max_words = max(1, int(round((max_sec / 60.0) * wpm)))
    target_words = max(1, int(round((target_sec / 60.0) * wpm)))
    min_words = max(1, int(round((min_sec / 60.0) * wpm)))

    units: list[str] = []
    for sentence in _split_sentences(script):
        units.extend(_split_long_sentence(sentence, max_words))

    packed: list[str] = []
    buf: list[str] = []
    buf_words = 0

    for unit in units:
        uw = word_count(unit)
        if not buf:
            buf = [unit]
            buf_words = uw
            continue

        # If adding keeps us under max and we're still short of target, pack.
        if buf_words < min_words or (
            buf_words < target_words and buf_words + uw <= max_words
        ):
            buf.append(unit)
            buf_words += uw
            continue

        # Closing current buffer; start new one.
        packed.append(" ".join(buf).strip())
        buf = [unit]
        buf_words = uw

    if buf:
        # Merge tiny trailing buffer into previous if possible.
        if packed and buf_words < min_words:
            prev = packed[-1]
            if word_count(prev) + buf_words <= max_words + 2:
                packed[-1] = f"{prev} {' '.join(buf)}".strip()
            else:
                packed.append(" ".join(buf).strip())
        else:
            packed.append(" ".join(buf).strip())

    segments: list[Segment] = []
    cursor = 0.0
    for i, text in enumerate(packed):
        wc = word_count(text)
        duration = max(min_sec, min(max_sec, estimate_seconds(text, wpm=wpm) or target_sec))
        # Keep timeline continuous even if estimated duration is clamped.
        end = cursor + duration
        segments.append(
            Segment(
                index=i,
                start_sec=round(cursor, 2),
                end_sec=round(end, 2),
                text=text,
                word_count=wc,
            )
        )
        cursor = end

    return segments
