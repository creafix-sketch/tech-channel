# Script Image Downloader

Segment a YouTube computing-history script and download **one relevant image every 5–7 seconds**.

Built for B-roll research: images come from **Wikimedia Commons** (strong for historical machines, people, and labs), and the tool **refuses low-confidence matches** instead of guessing wrong.

## Why this approach

| Goal | How it's handled |
|------|------------------|
| One image per 5–7s | Script is timed at ~150 WPM and packed into 5–7s beats |
| Relevant to the line | Named subjects (ENIAC, Turing, Apple II, …) drive the search |
| Never wrong | Token/subject scoring; weak matches → `needs_manual_review` |
| Safe for publishing | Commons + attribution file (always re-check license) |

Wrong B-roll is worse than a missing beat. Beats without a solid match are left empty on purpose.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Preview the beat plan (no network):

```bash
python -m image_downloader examples/sample_computing_history.txt --plan-only
```

Search + download:

```bash
python -m image_downloader examples/sample_computing_history.txt -o output/sample
```

Dry-run (search + score, skip file downloads):

```bash
python -m image_downloader examples/sample_computing_history.txt -o output/sample --dry-run
```

## Your OS/2 script

A ready-to-run narration file is included:

```bash
python -m image_downloader examples/os2_ibm_microsoft.txt --plan-only
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2
```

Phonetic spellings in the script (`O-S Two`, `Boh-kah Rah-tone`, `Ee-ah-koh-boo-chee`, `Sit-ricks`, …) are normalized automatically before search.

Use `--limit 20` to process only the first N beats while testing.

## Output

```
output/
  images/           # downloaded files: 000_0000-0006_eniac-computer.jpg
  manifest.json     # full segment + candidate + score data
  timeline.csv      # editor-friendly sheet
  attributions.md   # Commons title, artist, license, URL
```

## CLI options

```
python -m image_downloader SCRIPT.txt
  -o, --output DIR       Output folder (default: ./output)
  --wpm 150              Narration speed for timing
  --min-sec 5            Minimum beat length
  --max-sec 7            Maximum beat length
  --target-sec 6         Preferred beat length
  --min-score 0.55       Relevance gate (higher = stricter)
  --dry-run              Don't download binaries
  --plan-only            Segment only
```

## Accuracy policy

Wrong B-roll is worse than a missing beat.

1. Prefer known computing-history entities over vague keywords.
2. Search Wikimedia Commons (photos/scans preferred over SVG icons).
3. Score title + description + categories against required subject tokens.
4. **Each image URL is used at most once** per run (no duplicates).
5. **Lookalike caps** limit near-identical families (e.g. only a few DOS-disk photos).
6. If the best score is below `--min-score` (default **0.65**), **do not download** — leave empty.
7. Abstract narration with no concrete subject is left empty (no guessing).

Raise `--min-score` (e.g. `0.75`) for even stricter picks.

Wikimedia rate-limits aggressive traffic. This tool mitigates that by:

1. **Disk-caching** Commons search results in `.cache/wikimedia` (re-runs are much faster)
2. **Downloading 1280px thumbnails** by default (smaller/faster than originals)
3. **Parallel downloads** of unique URLs only (`--workers 4`), then copying for reused beats
4. **Adaptive backoff** that respects `Retry-After` on HTTP 429

Recommended for a full video:

```bash
# First pass: search + score (fills disk cache)
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2 --dry-run

# Second pass: download unique thumbs in parallel (reuses cache → much faster)
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2 --workers 6
```

If you still see 429s:

```bash
python -m image_downloader SCRIPT.txt -o output/run --slow --workers 2
```

Use `--full-size` only when you need archival originals for zoom/crop.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- Timing assumes spoken narration ≈ 150 words/minute. Adjust `--wpm` if you speak faster/slower.
- Always verify Commons licenses and personality rights before publishing.
- This tool does not generate AI images; it finds existing archive/photo matches.
