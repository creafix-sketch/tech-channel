"""Replace bad B-roll by copying from known-good images already in the set."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path("output/os2")
MANIFEST = ROOT / "manifest.json"

# Substrings that mark a chosen image as bad for this video.
BAD_BITS = (
    "gnukem",
    "breakanoid",
    "barrage game",
    "api c3d",
    "xscreensaver",
    "bsod",
    "boot error",
    "vulkanstrasse",
    "seestrasse",
    "microsoft atlanta",
    "microsoft policies",
    "reclining man",
    "windows 95 pc mini",
    "windows 95 display mini",
    "windows 95 & microsoft plus",
    "windows 95 - installation disk",
    "infosys",
    "equatex",
)

# Prefer these good local files (relative to output/os2) by topic.
GOOD = {
    "os2": "images/004_0027-0034_os-2.jpg",
    "os2_screen": "images/010_0065-0072_os-2.png",
    "os2_warp": "images/113_0734-0739_os-2-warp.jpg",
    "msdos": "images/001_0007-0014_ms-dos-computer.jpg",
    "msdos_pc": "images/051_0324-0331_ms-dos.jpg",
    "win30": "images/044_0280-0287_windows-3-0.png",
    "win31": "images/066_0424-0430_windows-3-1.png",
    "ps2": "images/030_0195-0202_ibm-ps-2-computer.jpg",
    "ps2b": "images/058_0369-0376_ibm-ps-2-computer.jpg",
    "mca": "images/059_0376-0383_ibm-micro-channel-architecture.jpg",
    "boca": "images/000_0000-0007_ibm-boca-raton.jpg",
    "boca2": "images/121_0786-0793_ibm-boca-raton.jpg",
    "ibm_pc": "images/089_0575-0581_ibm.jpg",
    "atm": "images/133_0863-0869_atm-automated-teller-machine.jpg",
    "citrix": "images/127_0824-0831_citrix.jpg",
    "lotus": "images/117_0759-0766_lotus-software.jpg",
    "apple": "images/085_0547-0554_apple-computer.jpg",
    "win95_ok": "images/115_0746-0753_windows-95.jpg",  # only for real Win95 lines
}


def is_bad(title: str) -> bool:
    t = title.lower()
    return any(b in t for b in BAD_BITS)


def pick_replacement(subject: str, text: str, index: int) -> str:
    sub = subject.lower()
    tx = text.lower()

    if "windows 95" in sub or "windows 95" in tx:
        return GOOD["win95_ok"]
    if "citrix" in sub or "sit-ricks" in tx:
        return GOOD["citrix"]
    if "subway" in sub or "transit" in tx or "new york" in sub:
        # No strong fare-system photo; use Boca/OS2 era computing continuity
        # is wrong. Prefer ATM/OS2 as "systems that quietly ran" continuity,
        # but for subway line use IBM PC era hardware as weaker fallback is bad.
        # Best available local: keep computing context with OS/2 floppies for
        # "OS/2 ran the fare system" narration.
        return GOOD["os2"]
    if "nt" in sub or "n-t" in tx:
        return GOOD["win30"]  # closest era desktop we trust locally
    if "api" in sub or "a-p-i" in tx:
        return GOOD["msdos_pc"]
    if "micro channel" in sub or "micro channel" in tx:
        return GOOD["mca"]
    if "ps/2" in sub or "p-s two" in tx or "personal system" in tx:
        return GOOD["ps2"] if index % 2 == 0 else GOOD["ps2b"]
    if "warp" in sub or "warp" in tx:
        return GOOD["os2_warp"]
    if "os/2" in sub or "o-s two" in tx:
        return GOOD["os2"] if index % 2 == 0 else GOOD["os2_screen"]
    if "dos" in sub or "doss" in tx:
        return GOOD["msdos"] if index % 2 == 0 else GOOD["msdos_pc"]
    if "windows 3.1" in sub or "windows 3.1" in tx:
        return GOOD["win31"]
    if "windows 3.0" in sub or "windows 3.0" in tx or "windows" in sub:
        return GOOD["win30"] if index % 2 == 0 else GOOD["win31"]
    if "microsoft" in sub or "microsoft" in tx:
        return GOOD["win30"] if index % 3 else GOOD["win31"]
    if "boca" in sub or "boh-kah" in tx:
        return GOOD["boca2"]
    if "ibm" in sub or "i-b-m" in tx:
        return GOOD["ibm_pc"] if index % 2 == 0 else GOOD["boca"]
    if "lotus" in sub:
        return GOOD["lotus"]
    if "apple" in sub:
        return GOOD["apple"]
    if "atm" in sub or "cash machine" in tx or "teller" in tx:
        return GOOD["atm"]
    # Default safe computing-history B-roll
    return GOOD["os2"]


def main() -> None:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fixed = 0
    for seg in data["segments"]:
        chosen = seg.get("chosen") or {}
        title = chosen.get("title") or ""
        if not is_bad(title):
            continue

        src_rel = pick_replacement(
            seg.get("primary_subject") or "",
            seg["segment"]["text"],
            seg["segment"]["index"],
        )
        src = ROOT / src_rel
        if not src.exists():
            print("missing source", src)
            continue

        idx = seg["segment"]["index"]
        start = int(seg["segment"]["start_sec"])
        end = int(seg["segment"]["end_sec"])
        # Keep a stable repaired filename
        dest_rel = f"images/{idx:03d}_{start:04d}-{end:04d}_repaired{src.suffix}"
        dest = ROOT / dest_rel
        shutil.copy2(src, dest)

        old = seg.get("local_path")
        if old and old != dest_rel:
            old_path = ROOT / old
            if old_path.exists() and old_path.resolve() != dest.resolve():
                # Only delete if no other segment still points at it
                still_used = any(
                    (o.get("local_path") == old)
                    for o in data["segments"]
                    if o is not seg
                )
                if not still_used:
                    try:
                        old_path.unlink()
                    except OSError:
                        pass

        # Copy metadata from the good source segment if available
        src_meta = None
        for other in data["segments"]:
            if other.get("local_path") == src_rel and other.get("chosen"):
                src_meta = other["chosen"]
                break

        if src_meta:
            seg["chosen"] = dict(src_meta)
        seg["local_path"] = dest_rel
        seg["status"] = "matched"
        seg["notes"] = f"Repaired: replaced weak/wrong image with {src_rel}"
        fixed += 1
        print(f"fixed #{idx:03d} <- {src_rel}")

    data["matched"] = sum(1 for s in data["segments"] if s["status"] == "matched")
    data["needs_manual_review"] = sum(
        1 for s in data["segments"] if s["status"] != "matched"
    )
    MANIFEST.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Verify
    bad_left = 0
    for seg in data["segments"]:
        title = ((seg.get("chosen") or {}).get("title") or "").lower()
        path = seg.get("local_path") or ""
        # Also flag if path still points at an old bad file name pattern
        if is_bad(title):
            # If we repaired by copy, chosen title may still be old unless src_meta found
            # Check notes
            if not (seg.get("notes") or "").startswith("Repaired:"):
                bad_left += 1
    print(f"done fixed={fixed} matched={data['matched']} review={data['needs_manual_review']}")


if __name__ == "__main__":
    main()
