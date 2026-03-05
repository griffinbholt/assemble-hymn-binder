# "Hymns—For Home and Church" Binder Assembler

[![CI](https://github.com/griffinbholt/assemble-hymn-binder/actions/workflows/ci.yml/badge.svg)](https://github.com/griffinbholt/assemble-hymn-binder/actions/workflows/ci.yml)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A Python script for preparing the new [Hymns—For Home and Church](https://www.churchofjesuschrist.org/media/music/collections/hymns-for-home-and-church?lang=eng) for printing and inserting into soft-cover pew binders.

The Church of Jesus Christ of Latter-day Saints releases new hymns digitally but does not print them. This script automatically downloads the [latest hymns PDF](https://www.churchofjesuschrist.org/media/music/statics/book-pdf/hymns-for-home-and-church/eng/hymns-for-home-and-church-letter.pdf) and produces print-ready binder PDFs that respect spread layout — no singer ever has to turn a page mid-hymn — while minimising reprints when new hymns are released.

## Features

- **Auto-downloads** the latest hymns PDF directly from ChurchofJesusChrist.org — no manual downloading required, with a live progress indicator
- Generates a single combined binder PDF (cover + all sections) for initial printing
- Cover page displays the official hymnal artwork with a "Last Updated" date
- Section title pages always land on right-hand pages
- Consecutive single-page hymns share a spread; two-page hymns get their own full spread
- No wasted leaves — sections flow directly into each other, and the last leaf of the binder is never blank
- On updates: generates a fresh cover PDF and one targeted update PDF per affected section, containing only what needs to be printed — including any sheet that must be reprinted because new content fills its previously-blank back side
- Validates the downloaded PDF and warns loudly if something looks wrong (e.g. the Church changed the URL or file format)
- Guards against bad `--since` values: typos, nonexistent hymn numbers, and edge cases

## Repository contents

```
assemble_hymn_binder.py
requirements.txt
README.md
tests/
    test_assemble_hymn_binder.py
.github/workflows/
    ci.yml                          ← runs tests on every push and pull request
```

Note: `cover_image.jpg` is **not** included in the repository. You must provide your own — see Installation below.

## Requirements

- Python 3.10+
- [pypdf](https://pypdf.readthedocs.io/)
- [pdfplumber](https://github.com/jsvine/pdfplumber)
- [reportlab](https://www.reportlab.com/)

## Installation

```bash
pip install -r requirements.txt
```

Clone or download this repository. Python 3.10 or later is required.

You must also provide a cover image named **`cover_image.jpg`** in the same directory as the script. This is not included in the repository — source an appropriate image yourself (e.g. from the Church's official media library at [media.churchofjesuschrist.org](https://media.churchofjesuschrist.org)). The script expects a portrait-oriented image and will scale it to fit the page with margins.

To run the tests:

```bash
python -m pytest tests/ -v
```

## Usage

### Initial assembly

Builds a single combined binder PDF — cover page followed by each section.

```bash
python assemble_hymn_binder.py assemble [--out-dir ./]
```

Output:

```
binder_full.pdf    ← Print this entire file and insert into binders
```

The combined PDF is structured as:

```
Page 1    Cover page (right-hand)
Page 2    Blank (back of cover leaf)
Page 3    "Sabbath and Weekday" title (right-hand)
Page 4+   Hymns 1001–1062
Page 103  "Easter and Christmas" title (right-hand)  ← flows directly, no wasted leaf
Page 104+ Hymns 1201–1210                            ← last page in binder, nothing after
```

Sections flow directly into each other without a wasted leaf between them. The last page in the binder is always a hymn, never blank.

### Updating when new hymns are released

The Church periodically releases new hymns. When they do, run:

```bash
python assemble_hymn_binder.py update --since 1063 [--out-dir ./]
```

`--since 1063` means "hymn 1063 and everything after it in its section is new." The script infers that 1062 was the last printed hymn.

If new hymns appear in multiple sections at once, pass multiple `--since` flags:

```bash
python assemble_hymn_binder.py update --since 1063 --since 1212 [--out-dir ./]
```

Output (one file per updated section, plus a new cover):

```
binder_cover.pdf       ← Replace the cover page in every binder
update_1000s.pdf       ← Print and insert into the Sabbath & Weekday section
update_1200s.pdf       ← Print and insert into the Easter & Christmas section
```

The script tells you whether any existing sheet needs to be discarded and replaced. This can happen in two ways:

- The new hymn fills the previously-blank back of the last printed sheet (e.g. hymn 1051 was on the front, back was blank, now hymn 1052 goes on the back — that sheet must be reprinted)
- The layout of earlier hymns shifted, requiring pages to be reprinted

Example output for a clean append:

```
============================================================
Section: Sabbath and Weekday (1000s)
✅  Keep all existing pages — no reprints needed.

📄  Update file: update_1000s.pdf
    2 pages to print  (0 reprints, 2 new)

    Pg   Side  Content
  --------------------------------------
   101  right  Hymn #1063 p1
   102  LEFT   Hymn #1064 p1

🖨️  Print settings: duplex (double-sided), flip on long edge. Do not add page numbers or headers.
```

Example output when the last sheet must be replaced:

```
============================================================
Section: Sabbath and Weekday (1000s)
⚠️  DISCARD the last printed sheet from your binders and replace it.
   (The sheet currently ending with hymn #1051)

📄  Update file: update_1000s.pdf
    3 pages to print  (1 reprint, 2 new)

    Pg   Side  Content
  --------------------------------------
    83  right  Hymn #1051 p1 ← reprint
    84  LEFT   Hymn #1052 p1
    85  right  Hymn #1052 p2
```

## Print settings

**Always print duplex (double-sided), flip on long edge.** Tell the print center not to add their own page numbers or headers.

## Adding a new section

When the Church introduces a new hymn range (e.g. 1400s), open the script and add an entry to the `SECTIONS` list near the top:

```python
SECTIONS = [
    {
        "key":     "1000s",
        "title":   "Sabbath and Weekday",
        "num_min": 1000,
        "num_max": 1199,
    },
    {
        "key":     "1200s",
        "title":   "Easter and Christmas",
        "num_min": 1200,
        "num_max": 1299,
    },
    {
        "key":     "1400s",
        "title":   "Section Title Here",
        "num_min": 1400,
        "num_max": 1499,
    },
]
```

Both `assemble` and `update` pick it up automatically.

## Layout rules

- **Cover page** is always page 1 (right-hand), with a blank back
- **Section title pages** always land on a right-hand page; a blank is inserted before a section only if needed for alignment
- **Hymns** always start on a left-hand page immediately after the section title
- Consecutive **single-page hymns** share a spread (left + right); if unpaired, the right side is blank
- **Two-page hymns** always occupy a full left+right spread on their own
- **No trailing blank leaves** — sections end on the last hymn page; the binder ends on the last hymn in the last section
- Each section can be updated independently — changes to one section never require reprinting another
