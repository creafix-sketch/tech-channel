"""Map abstract narration to concrete visual search ideas.

Human editors don't leave "Banks ran it" empty — they search bank terminals,
airline counters, trading floors, etc. This module does the same.
"""

from __future__ import annotations

import re

# (script pattern, visual search queries, must-ish tokens for soft verify)
_CONCEPT_VISUALS: list[tuple[re.Pattern[str], list[str], list[str]]] = [
    (re.compile(r"\bbanks?\b", re.I), ["1980s bank computer terminal", "bank teller computer 1990s", "ATM 1990s"], ["bank", "atm", "teller"]),
    (re.compile(r"\bairlines?\b|\bairport\b", re.I), ["airline check-in computer 1990s", "airport ticket counter computer", "airline reservation terminal"], ["airline", "airport", "ticket"]),
    (re.compile(r"\btrading\s+desk\b|\btransaction\b", re.I), ["stock trading floor computers 1990s", "trading desk monitors 1980s"], ["trading", "stock", "desk"]),
    (re.compile(r"\binstaller\b|\bdiskettes?\b|\bfeed them\b", re.I), ["floppy disk installation computer", "installing software from floppy disks 1990s"], ["floppy", "disk", "install"]),
    (re.compile(r"\bmemory\b|\bmegabytes?\b", re.I), ["computer RAM memory modules 1990s", "SIMM memory sticks PC"], ["memory", "ram", "simm"]),
    (re.compile(r"\bprinter\b", re.I), ["1990s office printer computer", "dot matrix printer PC"], ["printer"]),
    (re.compile(r"\bmultitasking\b|\bthreads?\b|\bsessions?\b", re.I), ["OS/2 desktop screenshot", "Windows 3.1 Program Manager", "multitasking computer desktop 1990s"], ["desktop", "window", "os"]),
    (re.compile(r"\bpartnership\b|\bagreement\b|\bjoint\b", re.I), ["Bill Gates IBM", "Microsoft IBM partnership 1980s", "Bill Gates 1980s"], ["gates", "ibm", "microsoft"]),
    (re.compile(r"\blicensing\b|\broyalt", re.I), ["software license agreement 1990s", "MS-DOS license", "software box retail 1990s"], ["software", "license", "dos"]),
    (re.compile(r"\bclone\b|\bcompatible\b", re.I), ["IBM PC clone computer 1980s", "Compaq portable computer", "PC compatible desktop 1980s"], ["compaq", "clone", "pc"]),
    (re.compile(r"\bhardware\b", re.I), ["1980s computer hardware motherboard", "PC hardware open case 1990s"], ["hardware", "motherboard", "computer"]),
    (re.compile(r"\bsoftware\b", re.I), ["1990s software boxes retail", "PC software packaging 1980s"], ["software", "box"]),
    (re.compile(r"\bdeveloper|\bprogramming\b|\bcode\b|\bapi\b|\ba-p-i\b", re.I), ["computer programmer 1990s", "coding on CRT monitor 1980s", "software developer workstation"], ["program", "computer", "code"]),
    (re.compile(r"\bmarketing\b|\bcampaign\b|\badvertis", re.I), ["1990s computer magazine advertisement", "PC software magazine ad"], ["advertisement", "magazine", "ad"]),
    (re.compile(r"\bmainframe\b", re.I), ["IBM mainframe computer room", "mainframe data center 1980s"], ["mainframe", "ibm"]),
    (re.compile(r"\boffice\b|\bcorporate\b", re.I), ["1990s office personal computer", "office desktop PC CRT 1990s"], ["office", "computer", "desktop"]),
    (re.compile(r"\bsupermarket\b|\bcheckout\b|\bregister\b", re.I), ["supermarket checkout computer 1990s", "point of sale terminal 1990s"], ["checkout", "pos", "register"]),
    (re.compile(r"\bsubway\b|\btransit\b|\bfare\b", re.I), ["New York City subway station", "subway turnstile New York", "MetroCard"], ["subway", "transit", "turnstile"]),
    (re.compile(r"\bcash machine\b|\batm\b|\bteller\b", re.I), ["ATM automated teller machine", "bank ATM exterior"], ["atm", "teller"]),
    (re.compile(r"\bserver\b", re.I), ["Windows NT Server", "1990s PC server rack"], ["server", "nt"]),
]


def visual_queries_for_text(text: str) -> list[str]:
    """Extra visual search queries derived from abstract/script concepts."""
    out: list[str] = []
    for pattern, queries, _tokens in _CONCEPT_VISUALS:
        if pattern.search(text):
            for q in queries:
                if q not in out:
                    out.append(q)
    return out[:6]


def concept_tokens_for_text(text: str) -> list[str]:
    tokens: list[str] = []
    for pattern, _queries, toks in _CONCEPT_VISUALS:
        if pattern.search(text):
            for t in toks:
                if t not in tokens:
                    tokens.append(t)
    return tokens[:6]
