"""Normalize spoken / phonetic narration into searchable proper nouns.

YouTube scripts often spell names the way a narrator should pronounce them
(e.g. "Boh-kah Rah-tone", "Ee-ah-koh-boo-chee"). Search APIs need the
real orthography.
"""

from __future__ import annotations

import re

# Longer / more specific patterns first.
_PHONETIC_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bEd\s+Ee-ah-koh-boo-chee\b", re.I), "Ed Iacobucci"),
    (re.compile(r"\bEe-ah-koh-boo-chee\b", re.I), "Iacobucci"),
    (re.compile(r"\bBoh-kah\s+Rah-tone\b", re.I), "Boca Raton"),
    (re.compile(r"\bSit-ricks\b", re.I), "Citrix"),
    (re.compile(r"\bNazdak\b", re.I), "Nasdaq"),
    (re.compile(r"\bAr-ka-O-S\b", re.I), "ArcaOS"),
    (re.compile(r"\be-Com-Station\b", re.I), "eComStation"),
    (re.compile(r"\bCom-pack\b", re.I), "Compaq"),
    (re.compile(r"\bS\s+and\s+P\s+500\b", re.I), "S&P 500"),
    (re.compile(r"\bPersonal\s+System\s+Two\b", re.I), "PS/2"),
    (re.compile(r"\bO-S\s+Two\b", re.I), "OS/2"),
    (re.compile(r"\bP-S\s+Two\b", re.I), "PS/2"),
    (re.compile(r"\bM-S\s+Doss\b", re.I), "MS-DOS"),
    (re.compile(r"\bWindows\s+N-T\b", re.I), "Windows NT"),
    (re.compile(r"\bN-T\b", re.I), "NT"),
    (re.compile(r"\bI-B-M\b", re.I), "IBM"),
    (re.compile(r"\bS-N-C-F\b", re.I), "SNCF"),
    (re.compile(r"\bA-P-I\b", re.I), "API"),
    (re.compile(r"\bD-O-S\b", re.I), "DOS"),
    (re.compile(r"\bP-C\b", re.I), "PC"),
    (re.compile(r"\bDoss\b", re.I), "DOS"),
    (re.compile(r"\bnineteen\s+nineties\b", re.I), "1990s"),
]


def normalize_script_text(text: str) -> str:
    """Return a copy of text with phonetic spellings replaced for search."""
    out = text
    for pattern, repl in _PHONETIC_REPLACEMENTS:
        out = pattern.sub(repl, out)
    out = re.sub(r"\s+", " ", out)
    return out
