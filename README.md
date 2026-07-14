# Script Image Downloader

Segment a YouTube computing-history script and download **one relevant image every 5–7 seconds**.

Built for B-roll research. Free sources first (Commons + Openverse + Wikipedia); optional Google/SerpAPI and a local image library for **full video coverage**. Wrong matches are refused — empty beats preferred over bad B-roll.

## Why this approach

| Goal | How it's handled |
|------|------------------|
| One image per 5–7s | Script timed at ~150 WPM into 5–7s beats |
| Relevant to the line | Named subjects + concept visuals drive search |
| Never wrong | Token/subject scoring; weak matches → empty |
| No duplicates | Each image URL/path used at most once |
| Full coverage | Missing-beat checklist + local library re-run |

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

## Getting images for an entire video

Free APIs alone usually will **not** fill every beat (humans also use Google, archives, screenshots). Use this workflow:

### 1) Auto-fetch (free sources)

```bash
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2 --workers 6
```

Sources: Wikimedia Commons, Openverse, Wikipedia page images. Concept queries help abstract lines (banks, airlines, floppies, …).

### 2) Fill the gaps from `missing_beats.md`

Every run writes:

- `missing_beats.md` — empty beats with **clickable Google Images links** + suggested filenames
- `missing_beats.csv` — same data for spreadsheets

Open the markdown file, search each link, save unique images into a folder (name files with keywords, e.g. `bill-gates-os2.jpg`).

### 3) Re-run with your local library

```bash
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2 \
  --local-library ./my_images --workers 6
```

The tool matches filename keywords to empty beats, copies those files in, and still refuses weak matches / duplicates.

### 4) Optional: Google-like APIs (closest to manual Google Images)

Set one of:

```bash
export GOOGLE_API_KEY=...
export GOOGLE_CSE_ID=...          # Programmable Search engine ID (image mode)

# or
export SERPAPI_KEY=...            # SerpAPI Google Images
```

Then re-run the same command — web results are searched automatically when keys are present. Use `--no-web-search` to force free-only.

Licenses from Google/SerpAPI are **not** Commons-cleared — check before publishing.

## Your OS/2 script

```bash
python -m image_downloader examples/os2_ibm_microsoft.txt --plan-only
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2
```

Phonetic spellings (`O-S Two`, `Boh-kah Rah-tone`, `Ee-ah-koh-boo-chee`, `Sit-ricks`, …) are normalized automatically.

Use `--limit 20` while testing.

## Output

```
output/
  images/              # downloaded / copied files
  manifest.json        # full segment + candidate + score data
  timeline.csv         # editor-friendly sheet
  attributions.md      # title, artist, license, URL
  missing_beats.md     # empty beats + Google Images links
  missing_beats.csv
```

## CLI options

```
python -m image_downloader SCRIPT.txt
  -o, --output DIR         Output folder (default: ./output)
  --local-library DIR      Match user-collected images to empty beats
  --wpm 150                Narration speed for timing
  --min-sec 5              Minimum beat length
  --max-sec 7              Maximum beat length
  --target-sec 6           Preferred beat length
  --min-score 0.55         Relevance gate (higher = stricter)
  --dry-run                Don't download binaries
  --plan-only              Segment only
  --workers 4              Parallel download workers
  --no-wikipedia           Disable Wikipedia page images
  --no-openverse           Disable Openverse
  --no-web-search          Disable Google CSE / SerpAPI
  --slow                   Gentler pacing if you hit 429s
  --full-size              Original files instead of 1280px thumbs
```

## Accuracy policy

1. Prefer known computing-history entities over vague keywords.
2. Search Commons + Openverse + Wikipedia (and optional web APIs).
3. Score title + description + categories against subject tokens.
4. **Each image URL/path is used at most once** per run.
5. **Lookalike caps** limit near-identical families (e.g. only a few DOS-disk photos).
6. Below `--min-score` → leave empty (see `missing_beats.md`).
7. Abstract narration may use concept visuals; still no guessing wrong product photos.

Raise `--min-score` (e.g. `0.75`) for stricter picks.

Wikimedia rate-limits aggressive traffic. Mitigations:

1. Disk-cache Commons results in `.cache/wikimedia`
2. Download 1280px thumbnails by default
3. Parallel downloads of unique URLs only (`--workers 4`)
4. Adaptive backoff on HTTP 429

```bash
# First pass: search + score (fills disk cache)
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2 --dry-run

# Second pass: download unique thumbs
python -m image_downloader examples/os2_ibm_microsoft.txt -o output/os2 --workers 6
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Notes

- Timing assumes spoken narration ≈ 150 words/minute. Adjust `--wpm` if needed.
- Always verify licenses and personality rights before publishing.
- This tool does not generate AI images; it finds existing archive/photo matches.
