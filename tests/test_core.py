"""Unit tests for segmentation, query building, and verification (no network)."""

from __future__ import annotations

import unittest

from image_downloader.models import ImageCandidate
from image_downloader.normalize import normalize_script_text
from image_downloader.query_builder import build_query_plan
from image_downloader.segmenter import estimate_seconds, segment_script, word_count
from image_downloader.verifier import pick_best, score_candidate


SAMPLE = """
In 1945, engineers unveiled ENIAC, a giant machine of vacuum tubes.
Alan Turing had already imagined a universal computing device.
By the 1970s, the Altair 8800 brought computing into hobbyist homes.
Steve Wozniak and Steve Jobs launched the Apple II in 1977.
The IBM PC arrived in 1981 and standardized personal computing.
Then Tim Berners-Lee created the World Wide Web, connecting the planet.
"""


class SegmenterTests(unittest.TestCase):
    def test_word_count(self):
        self.assertEqual(word_count("ENIAC was huge"), 3)

    def test_estimate_seconds(self):
        # 15 words at 150 wpm => 6 seconds
        text = " ".join(["word"] * 15)
        self.assertAlmostEqual(estimate_seconds(text, wpm=150), 6.0, places=2)

    def test_segments_hit_5_to_7_seconds(self):
        segments = segment_script(SAMPLE, wpm=150, min_sec=5, max_sec=7, target_sec=6)
        self.assertGreaterEqual(len(segments), 3)
        for seg in segments:
            self.assertGreaterEqual(seg.duration_sec, 5.0)
            self.assertLessEqual(seg.duration_sec, 7.0)
            self.assertTrue(seg.text.strip())

    def test_timeline_is_contiguous(self):
        segments = segment_script(SAMPLE)
        self.assertEqual(segments[0].start_sec, 0.0)
        for i in range(1, len(segments)):
            self.assertAlmostEqual(segments[i].start_sec, segments[i - 1].end_sec, places=2)


class NormalizeTests(unittest.TestCase):
    def test_phonetic_os2_names(self):
        raw = (
            "Inside I-B-M's lab in Boh-kah Rah-tone, Ed Ee-ah-koh-boo-chee "
            "pressed O-S Two disks to replace Doss on the P-S Two."
        )
        norm = normalize_script_text(raw)
        self.assertIn("IBM", norm)
        self.assertIn("Boca Raton", norm)
        self.assertIn("Ed Iacobucci", norm)
        self.assertIn("OS/2", norm)
        self.assertIn("DOS", norm)
        self.assertIn("PS/2", norm)
        self.assertNotIn("Ee-ah-koh", norm)


class QueryBuilderTests(unittest.TestCase):
    def test_known_subject_eniac(self):
        plan = build_query_plan("In 1945, engineers unveiled ENIAC, a giant machine of vacuum tubes.")
        self.assertIn("ENIAC", plan.primary_subject)
        self.assertGreaterEqual(plan.confidence_hint, 0.85)
        self.assertTrue(plan.queries)

    def test_known_person(self):
        plan = build_query_plan("Alan Turing had already imagined a universal computing device.")
        self.assertIn("Turing", plan.primary_subject)

    def test_os2_preferred_over_ibm_brand(self):
        plan = build_query_plan(
            normalize_script_text(
                "Engineers who used O-S Two will tell you it was better than what Microsoft sold."
            )
        )
        self.assertIn("OS/2", plan.primary_subject)

    def test_iacobucci_preferred(self):
        plan = build_query_plan(
            normalize_script_text(
                "Ed Ee-ah-koh-boo-chee watched his team press O-S Two onto floppy disks at I-B-M."
            )
        )
        self.assertIn("Iacobucci", plan.primary_subject)


class VerifierTests(unittest.TestCase):
    def test_accepts_matching_image(self):
        plan = build_query_plan("Engineers unveiled ENIAC in 1945.")
        cand = ImageCandidate(
            title="ENIAC computer at the Moore School",
            page_url="https://commons.wikimedia.org/wiki/File:ENIAC.jpg",
            image_url="https://example.com/eniac.jpg",
            thumb_url=None,
            description="Photograph of the ENIAC computer",
            categories=["ENIAC", "Computers"],
            artist="US Army",
            license="Public domain",
            width=2000,
            height=1500,
        )
        best, scored = pick_best([cand], plan, min_score=0.55)
        self.assertIsNotNone(best)
        self.assertGreaterEqual(best.score, 0.55)

    def test_rejects_substring_false_positive(self):
        plan = build_query_plan("Ed Iacobucci pressed OS/2 disks.")
        cand = ImageCandidate(
            title="T-Rex Technology Center Fountain (cropped).JPG",
            page_url="https://commons.wikimedia.org/wiki/File:x.jpg",
            image_url="https://example.com/x.jpg",
            thumb_url=None,
            description="A fountain",
            categories=["Florida"],
            artist="Someone",
            license="CC BY 4.0",
            width=2000,
            height=1500,
        )
        best, _ = pick_best([cand], plan, min_score=0.55)
        self.assertIsNone(best)

    def test_rejects_aerynos_for_os2(self):
        plan = build_query_plan("Engineers who used OS/2 will tell you it was better.")
        cand = ImageCandidate(
            title="AerynOS 2025.12 GNOME System about - English.png",
            page_url="https://commons.wikimedia.org/wiki/File:a.png",
            image_url="https://example.com/a.png",
            thumb_url=None,
            description="Screenshot of AerynOS",
            categories=["Operating systems"],
            artist="Someone",
            license="CC BY 4.0",
            width=2000,
            height=1500,
        )
        best, _ = pick_best([cand], plan, min_score=0.55)
        self.assertIsNone(best)

    def test_accepts_real_os2_title(self):
        plan = build_query_plan("Engineers who used OS/2 will tell you it was better.")
        cand = ImageCandidate(
            title="IBM OS/2 Warp box.jpg",
            page_url="https://commons.wikimedia.org/wiki/File:os2.jpg",
            image_url="https://example.com/os2.jpg",
            thumb_url=None,
            description="Retail box of IBM OS/2 Warp",
            categories=["OS/2", "IBM software"],
            artist="IBM",
            license="Fair use",
            width=2000,
            height=1500,
        )
        best, _ = pick_best([cand], plan, min_score=0.55)
        self.assertIsNotNone(best)


if __name__ == "__main__":
    unittest.main()
