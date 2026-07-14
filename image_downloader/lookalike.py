"""Visual lookalike families — limit how many near-identical B-roll shots we keep."""

from __future__ import annotations

import re

from .models import ImageCandidate

# Max images allowed per visual family in one video (reduces spam).
DEFAULT_FAMILY_CAPS: dict[str, int] = {
    "os2_media": 16,
    "dos_media": 8,
    "windows3": 10,
    "windows95": 5,
    "windows_nt": 6,
    "ibm_ps2": 8,
    "ibm_building": 5,
    "ibm_pc": 8,
    "floppy_generic": 6,
    "microsoft_person": 5,
    "atm": 5,
    "citrix": 3,
    "lotus": 3,
    "subway": 4,
    "office_pc": 10,
    "other": 20,
}


def image_family(candidate: ImageCandidate) -> str:
    blob = f"{candidate.title} {candidate.description} {' '.join(candidate.categories)}".lower()
    if re.search(r"os/?2|os-2|(?<![a-z])os2(?![a-z0-9])|warp|ecomstation|arcaos", blob):
        return "os2_media"
    if re.search(r"windows\s*95|win95", blob):
        return "windows95"
    if re.search(r"windows\s*nt|winnt", blob):
        return "windows_nt"
    if re.search(r"windows\s*3|workgroups", blob):
        return "windows3"
    if re.search(r"ms-?dos|(?<![a-z])dos(?![a-z])|pc dos", blob):
        return "dos_media"
    if re.search(r"ps/?2|ps-2|(?<![a-z])ps2(?![a-z0-9])", blob):
        return "ibm_ps2"
    if re.search(r"5150|ibm pc|personal computer xt|personal computer at", blob):
        return "ibm_pc"
    if re.search(r"boca raton|ibm building|ibm campus|ibm facility|ibm research|ibm france", blob):
        return "ibm_building"
    if re.search(r"floppy|diskette", blob):
        return "floppy_generic"
    if re.search(r"bill gates|paul allen", blob):
        return "microsoft_person"
    if re.search(r"\batm\b|teller machine|cash machine", blob):
        return "atm"
    if re.search(r"citrix", blob):
        return "citrix"
    if re.search(r"lotus 1-2-3|lotus notes|lotus symphony|lotus smart", blob):
        return "lotus"
    if re.search(r"subway|metrocard|turnstile", blob):
        return "subway"
    if re.search(r"office|desktop pc|crt monitor|workstation", blob):
        return "office_pc"
    return "other"


class LookalikeLimiter:
    def __init__(self, caps: dict[str, int] | None = None):
        self.caps = caps or DEFAULT_FAMILY_CAPS
        self.counts: dict[str, int] = {}

    def allows(self, candidate: ImageCandidate) -> bool:
        family = image_family(candidate)
        cap = self.caps.get(family, self.caps.get("other", 99))
        return self.counts.get(family, 0) < cap

    def record(self, candidate: ImageCandidate) -> None:
        family = image_family(candidate)
        self.counts[family] = self.counts.get(family, 0) + 1
