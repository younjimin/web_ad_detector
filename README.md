# Public WebScan

A tool that crawls a public-sector website and finds advertising text hidden from human readers but visible to search engines and bots. Built for the 2026 MOIS / NIA contest "Illegal Advertisement Detection Tool for Public Websites".

It runs fully offline apart from the crawl itself: no external APIs, no cloud services. Detection is rule-based, with a keyword dictionary that ships with the tool.

## What it detects

The four techniques defined by the contest:

| Technique | What it looks for |
|---|---|
| `HOMOGLYPH` | Look-alike characters (Cyrillic/Greek/full-width letters, leet digits) used to spell banned words |
| `JAMO` | Hangul syllables split into separate jamo (`ㅋㅏㅈㅣㄴㅗ`) to dodge keyword filters |
| `TRANSPARENT` | Text with `opacity:0`, `color:transparent`, or the same color as its background |
| `OFFSCREEN` | Text with font-size 0-1px, pushed far off-screen with `position`, or `display:none` |

A banned keyword must be present for a finding to be reported. Text that is merely hidden (skip-navigation links, for example) is ignored.

Techniques outside the contest definition are reported separately as `ETC` in `result_extra.json`: `visibility:hidden`, `clip` / `clip-path`, 1px boxes with `overflow:hidden`, `text-indent` and `transform` shifts, and zero-width characters inserted between letters. An element already reported under the four main techniques is not repeated there.

## Output

Each scan writes three files next to the executable (or next to `scan_core.py` when run from source):

- `result.json`: findings for the four main techniques, in the contest schema
- `result_extra.json`: `ETC` findings
- `report.html`: a self-contained report you can open in any browser

Each finding carries the page URL, a CSS selector that matches exactly one element (iframe content is addressed as `iframe[src="..."] >>> selector`), and the original text.

## Usage

### Windows executable

Unzip the release and run `PublicWebScan.exe`. Enter a start URL, press start, and open the report when it finishes. A scan is capped at 23 minutes of crawling so the whole run stays under 30 minutes.

### From source

Python 3.11 is what the build uses.

```
pip install -r requirements-dev.txt
python -m playwright install --only-shell chromium
python src/main.py https://example.go.kr
```

Running `src/main.py` without a URL starts the GUI.

### Tests

```
cd src
python -m pytest -q
```

### Building the executable

The Windows build runs on GitHub Actions (`.github/workflows/build.yml`): tests, then PyInstaller (`--onedir`, Chromium bundled), then a smoke test against a local test page. To build by hand:

```
pyinstaller --noconfirm --onedir --console --name "PublicWebScan" --paths src --collect-all playwright src/main.py
```

## Extending the dictionary

Put a `banned_keywords.json` next to the executable. It is merged with the built-in dictionary at startup, so no rebuild is needed. Generate a template with:

```
python src/keywords.py --export banned_keywords.json
```

Keys: `strong_ko`, `strong_en` (reported on their own), `weak_ko`, `weak_en` (reported only alongside a contact/invitation phrase such as a Telegram handle, URL or phone number), `cues`, `soft_cues`, `exceptions`. The `AD_DICT_PATH` environment variable points to a different file.

## Layout

```
src/
  main.py            entry point (CLI / GUI)
  gui.py             Tkinter front end
  scan_core.py       crawl -> detect -> write files
  crawler.py         Playwright crawler, collects text nodes with computed styles
  pipeline.py        runs the detectors
  homoglyph.py  jamo.py  transparent.py  offscreen.py   main detectors
  extra.py           ETC detector
  keywords.py        dictionary and matching rules
  result_writer.py   result.json / result_extra.json
  report.py          report.html
  verify_selectors.py  checks that every selector matches one element
  eval_v2.py         scores a run against test_site_v2/expected.json
  test_*.py          unit tests
test_site/  test_site_v2/   hand-made pages with known hidden text
.github/workflows/build.yml
```

## Crawler behavior

- Playwright (Chromium), 4 parallel tabs, same-domain links only, up to 1000 pages.
- Pages are visited fairly across URL patterns, so one huge section (a bulletin board with thousands of posts, say) cannot use up the page budget.
- The crawler does not read `robots.txt` and does not throttle requests. Use it only on sites you are authorized to scan.

## Accuracy

I have no ground-truth data from the contest sites. The numbers below come from the test pages in this repository, which I labelled myself, so they say the detectors do what I designed them to do, not how they will do on real sites:

- `test_site_v2`: 12 of 12 labelled items found, 0 false positives
- the contest test kit: 13 findings

Known limits: the dictionary is finite, and a keyword that is not in it is not found. Text rendered into images or canvas is out of scope. Classification of `text-indent` and `transform` shifts (main `OFFSCREEN` vs `ETC`) is my reading of the contest definition.

## Possible extension

A model-based classifier could sit behind the dictionary stage to judge borderline text. It is intentionally not part of this version, which keeps the tool free of external services.
