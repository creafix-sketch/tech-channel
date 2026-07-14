"""Turn a script segment into precise image search queries.

For computing-history B-roll, wrong images are worse than missing ones.
We bias toward concrete named subjects (machines, people, labs, chips)
and avoid vague mood queries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Common stop / filler words for query cleaning.
_STOP = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "at", "for",
    "from", "by", "with", "as", "is", "was", "were", "are", "be", "been", "being",
    "this", "that", "these", "those", "it", "its", "their", "our", "his", "her",
    "they", "them", "we", "you", "he", "she", "who", "which", "what", "when",
    "where", "while", "into", "over", "after", "before", "about", "than", "then",
    "so", "if", "not", "no", "yes", "just", "also", "even", "still", "only",
    "very", "more", "most", "some", "any", "all", "each", "every", "both",
    "would", "could", "should", "will", "can", "may", "might", "must", "shall",
    "had", "have", "has", "did", "do", "does", "done", "make", "made", "making",
    "became", "become", "becomes", "called", "known", "using", "used", "use",
    "like", "such", "through", "during", "between", "among", "across", "around",
    "here", "there", "now", "later", "early", "first", "next", "last", "once",
    "one", "two", "three", "many", "few", "much", "way", "ways", "world",
    "people", "time", "year", "years", "history", "story", "today", "new",
    "old", "great", "big", "small", "real", "true", "important", "famous",
    "your", "my", "mine", "ours", "yours", "them", "themselves", "himself",
    "herself", "itself", "someone", "something", "everything", "nothing",
    "anyone", "anything", "everyone", "everybody", "somebody", "nobody",
    "things", "thing", "code", "system", "systems", "company", "companies",
    "market", "reason", "difference", "error", "design", "version",
}

# Computing-history visual anchors: prefer these when present.
# Order matters — more specific subjects should appear before broader ones.
_KNOWN_SUBJECTS: list[tuple[re.Pattern[str], str]] = [
    # --- OS/2 / IBM PC era (this channel's current script) ---
    (re.compile(r"\bEd\s+Iacobucci\b|\bIacobucci\b", re.I), "Ed Iacobucci"),
    (re.compile(r"\bBoca\s+Raton\b", re.I), "IBM Boca Raton"),
    (re.compile(r"\bOS/?2\s+Warp\b|\bcalled\s+Warp\b", re.I), "OS/2 Warp"),
    (re.compile(r"\bOS/?2\b", re.I), "OS/2"),
    (re.compile(r"\bWorkplace\s+Shell\b", re.I), "OS/2 Workplace Shell"),
    (re.compile(r"\bPS/?2\b|\bPersonal\s+System(?:\s+Two)?\b", re.I), "IBM PS/2 computer"),
    (re.compile(r"\bMicro\s+Channel\b", re.I), "IBM Micro Channel Architecture"),
    (re.compile(r"\bMS-?DOS\b", re.I), "MS-DOS"),
    (re.compile(r"\bDOS\b", re.I), "MS-DOS computer"),
    (re.compile(r"\bWindows\s*NT\b", re.I), "Windows NT"),
    (re.compile(r"\bWindows\s*95\b", re.I), "Windows 95"),
    (re.compile(r"\bWindows\s*3\.1\b", re.I), "Windows 3.1"),
    (re.compile(r"\bWindows\s*3\.0\b", re.I), "Windows 3.0"),
    (re.compile(r"\bWindows\b", re.I), "Microsoft Windows"),
    (re.compile(r"\bMicrosoft\b", re.I), "Microsoft"),
    (re.compile(r"\bBill\s+Gates\b", re.I), "Bill Gates"),
    (re.compile(r"\bCitrix\b", re.I), "Citrix"),
    (re.compile(r"\bCompaq\b", re.I), "Compaq computer"),
    (re.compile(r"\bLotus\b", re.I), "Lotus software"),
    (re.compile(r"\beComStation\b", re.I), "eComStation OS/2"),
    (re.compile(r"\bArcaOS\b", re.I), "ArcaOS"),
    (re.compile(r"\bSNCF\b", re.I), "SNCF train ticket"),
    (re.compile(r"\bIBM\s+PC\b|\bIBM\s*5150\b", re.I), "IBM PC 5150"),
    (re.compile(r"\bIBM\b", re.I), "IBM"),
    (re.compile(r"\bfloppy\s+disks?\b|\bdiskettes?\b", re.I), "floppy disk installation"),
    (re.compile(r"\bATM\b|\bautomated\s+teller\b|\bcash\s+machine\b", re.I), "ATM automated teller machine"),
    (re.compile(r"\bNew\s+York\s+City\s+transit\b|\bsubway\b", re.I), "New York City subway"),
    (re.compile(r"\bmainframe\b", re.I), "IBM mainframe computer"),
    (re.compile(r"\bAPI\b|\bapplication\s+programming\s+interface\b", re.I), "software API programming"),
    # --- Classic computing history ---
    (re.compile(r"\bENIAC\b", re.I), "ENIAC computer"),
    (re.compile(r"\bEDVAC\b", re.I), "EDVAC computer"),
    (re.compile(r"\bUNIVAC\b", re.I), "UNIVAC computer"),
    (re.compile(r"\bColossus\b", re.I), "Colossus computer Bletchley Park"),
    (re.compile(r"\bMark\s*I\b|\bHarvard\s+Mark\s*I\b", re.I), "Harvard Mark I computer"),
    (re.compile(r"\bAnalytical\s+Engine\b", re.I), "Babbage Analytical Engine"),
    (re.compile(r"\bDifference\s+Engine\b", re.I), "Babbage Difference Engine"),
    (re.compile(r"\bApple\s*II\b", re.I), "Apple II computer"),
    (re.compile(r"\bMacintosh\b|\bApple\s+Macintosh\b", re.I), "Apple Macintosh 1984"),
    (re.compile(r"\bCommodore\s*64\b|\bC64\b", re.I), "Commodore 64"),
    (re.compile(r"\bAltair\b", re.I), "Altair 8800"),
    (re.compile(r"\bXerox\s+Alto\b", re.I), "Xerox Alto"),
    (re.compile(r"\bXerox\s+PARC\b", re.I), "Xerox PARC"),
    (re.compile(r"\bARPANET\b", re.I), "ARPANET"),
    (re.compile(r"\bWorld\s+Wide\s+Web\b|\bWWW\b", re.I), "World Wide Web Tim Berners-Lee"),
    (re.compile(r"\btransistor\b", re.I), "transistor Bell Labs"),
    (re.compile(r"\bintegrated\s+circuit\b|\bmicrochip\b", re.I), "integrated circuit chip"),
    (re.compile(r"\bvacuum\s+tubes?\b", re.I), "vacuum tube computer"),
    (re.compile(r"\bpunch(?:ed)?\s+cards?\b", re.I), "punched card computer"),
    (re.compile(r"\bAlan\s+Turing\b", re.I), "Alan Turing"),
    (re.compile(r"\bAda\s+Lovelace\b", re.I), "Ada Lovelace"),
    (re.compile(r"\bCharles\s+Babbage\b", re.I), "Charles Babbage"),
    (re.compile(r"\bGrace\s+Hopper\b", re.I), "Grace Hopper"),
    (re.compile(r"\bJohn\s+von\s+Neumann\b", re.I), "John von Neumann"),
    (re.compile(r"\bSteve\s+Jobs\b", re.I), "Steve Jobs"),
    (re.compile(r"\bSteve\s+Wozniak\b|\bWozniak\b", re.I), "Steve Wozniak"),
    (re.compile(r"\bTim\s+Berners[- ]Lee\b", re.I), "Tim Berners-Lee"),
    (re.compile(r"\bMoore'?s\s+Law\b", re.I), "Gordon Moore integrated circuit"),
    (re.compile(r"\bIntel\b", re.I), "Intel microprocessor"),
    (re.compile(r"\bBell\s+Labs\b", re.I), "Bell Labs"),
    (re.compile(r"\bBletchley\s+Park\b", re.I), "Bletchley Park"),
    (re.compile(r"\bSilicon\s+Valley\b", re.I), "Silicon Valley"),
    (re.compile(r"\bApple\b", re.I), "Apple Computer"),
    (re.compile(r"\bpersonal\s+computer\b", re.I), "personal computer 1980s"),
    (re.compile(r"\blaptop\b", re.I), "laptop computer"),
    (re.compile(r"\bsmartphone\b", re.I), "smartphone"),
    (re.compile(r"\binternet\b", re.I), "early internet computer network"),
]

_YEAR = re.compile(r"\b(1[89]\d{2}|20[0-2]\d)\b")
_PROPER = re.compile(
    r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}|[A-Z]{2,}(?:\s+[A-Z]{2,})*)\b"
)
_TECH_NOUN = re.compile(
    r"\b(?:computer|processor|microprocessor|chip|circuit|server|terminal|"
    r"keyboard|monitor|mouse|disk|drive|memory|cpu|gpu|router|modem|"
    r"prototype|machine|device|console|workstation|supercomputer)\b",
    re.I,
)


@dataclass
class QueryPlan:
    primary_subject: str
    queries: list[str]
    must_include_tokens: list[str]
    confidence_hint: float  # 0–1 how concrete the subject is


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
    return out


def _extract_proper_nouns(text: str) -> list[str]:
    """Extract likely proper nouns, ignoring sentence-initial capitalization."""
    # Split into sentences so we can ignore the first capitalized word of each.
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    found: list[str] = []
    for sentence in sentences:
        matches = list(_PROPER.finditer(sentence))
        for i, m in enumerate(matches):
            name = m.group(0)
            if name.lower() in _STOP or len(name) <= 2:
                continue
            # Skip a lone Capitalized word at the very start of a sentence —
            # usually just English sentence case ("Airlines ran it").
            if i == 0 and m.start() == 0 and " " not in name and not name.isupper():
                continue
            found.append(name)
    return found


def _year_in_text(text: str) -> str | None:
    m = _YEAR.search(text)
    return m.group(1) if m else None


# Broad brand labels — demote when a more specific subject is also present.
_GENERIC_SUBJECTS = {
    "IBM",
    "Microsoft",
    "Microsoft Windows",
    "Apple Computer",
    "personal computer 1980s",
    "computer software code",
    "computer hardware",
    "software API programming",
}


def _rank_known_hits(hits: list[str]) -> list[str]:
    """Keep discovery order for specific subjects; push broad brands last."""
    uniq = _dedupe(hits)
    specific = [h for h in uniq if h not in _GENERIC_SUBJECTS]
    generic = [h for h in uniq if h in _GENERIC_SUBJECTS]
    return specific + generic


def build_query_plan(text: str) -> QueryPlan:
    """Extract a concrete visual subject and search queries from segment text."""
    known_hits: list[str] = []
    for pattern, subject in _KNOWN_SUBJECTS:
        if pattern.search(text):
            known_hits.append(subject)
    known_hits = _rank_known_hits(known_hits)

    year = _year_in_text(text)
    proper_nouns = _extract_proper_nouns(text)

    tech = [m.group(0).lower() for m in _TECH_NOUN.finditer(text)]

    queries: list[str] = []
    must_tokens: list[str] = []
    confidence = 0.35
    primary = ""

    if known_hits:
        primary = known_hits[0]
        # Workplace Shell screenshots are rare on Commons — treat as OS/2 visually.
        if primary == "OS/2 Workplace Shell":
            primary = "OS/2"
            known_hits = ["OS/2 Workplace Shell", "OS/2"] + [
                h for h in known_hits if h not in {"OS/2 Workplace Shell", "OS/2"}
            ]
        confidence = 0.9 if primary not in _GENERIC_SUBJECTS else 0.7
        # Prefer searchable Commons phrases for slash-products.
        if primary == "OS/2":
            queries.append("IBM OS/2")
            queries.append("OS/2")
        elif primary == "OS/2 Warp":
            queries.append("OS/2 Warp")
            queries.append("IBM OS/2")
        else:
            queries.append(primary)
        if year and year not in primary:
            queries.append(f"{queries[0]} {year}")
        for subject in known_hits[1:3]:
            if subject not in queries:
                queries.append(subject)
        must_tokens.extend(_subject_tokens(primary))
    elif proper_nouns:
        # Prefer multi-word proper names / acronyms.
        proper_nouns = sorted(proper_nouns, key=lambda s: (-(" " in s), -len(s)))
        primary = proper_nouns[0]
        confidence = 0.7
        base = primary
        if tech:
            base = f"{primary} {tech[0]}"
        queries.append(base)
        if year:
            queries.append(f"{base} {year}")
        must_tokens.extend(_subject_tokens(primary))
        if tech:
            must_tokens.append(tech[0].lower())
    elif tech:
        primary = tech[0]
        confidence = 0.45
        q = f"historic {tech[0]}" if not year else f"{tech[0]} {year}"
        queries.append(q)
        queries.append(f"{tech[0]} computer history")
        must_tokens.append(tech[0].lower())
    else:
        # Last resort: keyword skeleton — low confidence, likely needs review.
        keywords = [
            w.lower()
            for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)
            if w.lower() not in _STOP
        ][:6]
        primary = " ".join(keywords[:3]) or "computer history"
        confidence = 0.25
        queries.append(primary)
        must_tokens = keywords[:2]

    queries = _dedupe(queries)[:4]
    must_tokens = _dedupe([t.lower() for t in must_tokens if t])[:6]
    return QueryPlan(
        primary_subject=primary,
        queries=queries,
        must_include_tokens=must_tokens,
        confidence_hint=confidence,
    )


def _subject_tokens(subject: str) -> list[str]:
    parts = re.findall(r"[A-Za-z0-9]+", subject.lower())
    return [p for p in parts if p not in _STOP and len(p) > 1]
