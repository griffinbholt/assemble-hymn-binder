#!/usr/bin/env python3
"""
LDS Hymn Binder Assembler
=========================
Automatically downloads the latest hymns PDF from ChurchofJesusChrist.org.

Two modes:

1. ASSEMBLE — Build a single combined binder PDF (cover + all sections).

   python assemble_hymn_binder.py assemble [--out-dir ./]

2. UPDATE — Generate a fresh cover PDF and one update PDF per affected
   section, containing only the pages that need to be printed.

   python assemble_hymn_binder.py update --since 1063 --since 1212 [--out-dir ./]

   Each --since N means "hymn N and everything after it in its section is new."
   Last-printed is implicitly N-1.

Print settings: duplex, flip on long edge.

To add a new section, add one entry to SECTIONS below.
"""

import argparse
import io
import re
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path
from pypdf import PdfReader, PdfWriter


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

HYMNS_URL = (
    "https://www.churchofjesuschrist.org/media/music/statics/book-pdf/"
    "hymns-for-home-and-church/eng/hymns-for-home-and-church-letter.pdf"
)

# Sanity check: warn if fewer than this many hymns are detected per section.
MIN_HYMNS_PER_SECTION = 5

# To add a new section when the Church introduces a new hymn range, append
# an entry here. Both `assemble` and `update` pick it up automatically.
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
    # Example: uncomment when a 1400s section is released
    # {
    #     "key":     "1400s",
    #     "title":   "...",
    #     "num_min": 1400,
    #     "num_max": 1499,
    # },
]

COVER_IMAGE = Path(__file__).parent / "cover_image.jpg"

DUPLEX_REMINDER = (
    "🖨️  Print settings: duplex (double-sided), flip on long edge. "
    "Do not add page numbers or headers."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def section_for_hymn(num: int) -> dict | None:
    for s in SECTIONS:
        if s["num_min"] <= num <= s["num_max"]:
            return s
    return None


def download_hymns() -> str:
    """Download the hymns PDF to a temp file and return its path.
    Shows a progress indicator. Caller is responsible for deleting the file."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp.close()

    downloaded_bytes = 0

    def progress(block_num, block_size, total_size):
        nonlocal downloaded_bytes
        downloaded_bytes = min(block_num * block_size, total_size)
        if total_size > 0:
            pct = downloaded_bytes / total_size * 100
            mb  = downloaded_bytes / 1_048_576
            print(f"\r  Downloading... {mb:.1f} MB ({pct:.0f}%)", end="", flush=True)
        else:
            mb = downloaded_bytes / 1_048_576
            print(f"\r  Downloading... {mb:.1f} MB", end="", flush=True)

    print("Downloading latest hymns PDF...")
    try:
        urllib.request.urlretrieve(HYMNS_URL, tmp.name, reporthook=progress)
    except Exception as e:
        print()  # newline after progress
        print(f"Error downloading hymns PDF: {e}", file=sys.stderr)
        Path(tmp.name).unlink(missing_ok=True)
        sys.exit(1)

    final_mb = Path(tmp.name).stat().st_size / 1_048_576
    print(f"\r  Downloaded {final_mb:.1f} MB ✓                    ")
    return tmp.name


def detect_hymns(pdf_path: str) -> list[dict]:
    """Return sorted list of {num, title, start (0-idx), page_count}."""
    import pdfplumber
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        starts = []
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if lines and re.match(r"^\d{3,4}$", lines[0]):
                starts.append({
                    "num":   int(lines[0]),
                    "title": lines[1] if len(lines) > 1 else "",
                    "start": i,
                })
    hymns = []
    for idx, h in enumerate(starts):
        end = starts[idx + 1]["start"] - 1 if idx + 1 < len(starts) else total - 1
        h["page_count"] = end - h["start"] + 1
        hymns.append(h)
    return sorted(hymns, key=lambda x: x["num"])


def validate_hymns(all_hymns: list[dict]):
    """Warn loudly if the detected hymn list looks suspicious."""
    if not all_hymns:
        print(
            "\n⚠️  WARNING: No hymns detected in the downloaded PDF.\n"
            "   The Church may have changed the file format or URL.\n"
            "   Output files may be empty or incorrect.",
            file=sys.stderr,
        )
        return

    for section in SECTIONS:
        section_hymns = [h for h in all_hymns
                         if section["num_min"] <= h["num"] <= section["num_max"]]
        if len(section_hymns) < MIN_HYMNS_PER_SECTION:
            print(
                f"\n⚠️  WARNING: Only {len(section_hymns)} hymn(s) detected in the "
                f"{section['key']} section (expected at least {MIN_HYMNS_PER_SECTION}).\n"
                f"   The Church may have changed the file format or URL.\n"
                f"   Output files may be incomplete or incorrect.",
                file=sys.stderr,
            )


def validate_since(since_num: int, all_hymns: list[dict], section: dict):
    """
    Guard against bad --since values:
    - Reject if it's the very first hymn in the section (nothing to preserve).
    - Reject if it doesn't exist in the downloaded PDF.
    """
    hymn_nums = {h["num"] for h in all_hymns}
    first_in_section = section["num_min"]

    if since_num == first_in_section:
        print(
            f"Error: --since {since_num} is the first hymn in the "
            f"{section['key']} section. If you want to reprint the entire "
            f"section, use `assemble` instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    if since_num not in hymn_nums:
        print(
            f"Error: hymn {since_num} was not found in the downloaded PDF.\n"
            f"  Check that the hymn number is correct.\n"
            f"  Available hymns in {section['key']}: "
            f"{min(h for h in hymn_nums if section['num_min'] <= h <= section['num_max'])}–"
            f"{max(h for h in hymn_nums if section['num_min'] <= h <= section['num_max'])}",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Page generators
# ---------------------------------------------------------------------------

def make_binder_cover(width: float, height: float) -> PdfReader:
    """Cover image with white margins and black 'Last Updated' line."""
    from reportlab.pdfgen import canvas as rl_canvas

    if not COVER_IMAGE.exists():
        raise FileNotFoundError(
            f"Cover image not found: {COVER_IMAGE}\n"
            "Place cover_image.jpg alongside this script."
        )

    label = date.today().strftime("Last Updated: %-d %B %Y")
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))

    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    label_height = 28
    margin = 54
    avail_w = width - 2 * margin
    avail_h = height - margin - label_height

    img_w, img_h = 773, 1000
    scale = min(avail_w / img_w, avail_h / img_h)
    draw_w, draw_h = img_w * scale, img_h * scale
    img_x = (width - draw_w) / 2
    img_y = label_height + (avail_h - draw_h) / 2

    c.drawImage(str(COVER_IMAGE), img_x, img_y, draw_w, draw_h)

    c.setFont("Helvetica", 12)
    c.setFillColorRGB(0, 0, 0)
    c.drawCentredString(width / 2, 14, label)

    c.save()
    buf.seek(0)
    return PdfReader(buf)


def make_section_title_page(title: str, width: float, height: float) -> PdfReader:
    from reportlab.pdfgen import canvas as rl_canvas
    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(width, height))
    c.setFont("Helvetica-Bold", 36)
    c.drawCentredString(width / 2, height / 2, title)
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def blank_page(width: float, height: float):
    w = PdfWriter()
    w.add_blank_page(width=width, height=height)
    return w.pages[0]


def page_size(reader: PdfReader, page_idx: int = 0) -> tuple[float, float]:
    p = reader.pages[page_idx]
    return float(p.mediabox.width), float(p.mediabox.height)


# ---------------------------------------------------------------------------
# Layout planning
# ---------------------------------------------------------------------------

def plan_section(hymns: list[dict]) -> list[tuple]:
    """
    Returns list of (output_page, hymn_num|None, rel_page_idx|None, entry_type).
    entry_type: 'title' | 'blank' | 'hymn'

    Page 1 = title (right-hand). Hymns start on page 2 (left-hand).
    No trailing blank — the combined layout handles inter-section alignment.
    """
    cursor = 1
    plan = []

    def on_left():
        return cursor % 2 == 0

    def pad_to_left():
        nonlocal cursor
        if not on_left():
            plan.append((cursor, None, None, "blank"))
            cursor += 1

    plan.append((cursor, None, None, "title")); cursor += 1
    # cursor == 2 (left-hand) — hymns start immediately

    for hymn in hymns:
        num = hymn["num"]
        pc  = hymn["page_count"]
        if pc == 2:
            pad_to_left()
            plan.append((cursor, num, 0, "hymn")); cursor += 1
            plan.append((cursor, num, 1, "hymn")); cursor += 1
        else:
            plan.append((cursor, num, 0, "hymn")); cursor += 1

    # No trailing blank — sections end on the last hymn page.

    return plan


def render_section(plan, hymn_map, reader, section, page_w, page_h) -> PdfWriter:
    """Turn a plan into a PdfWriter."""
    bp = blank_page(page_w, page_h)
    title_page = make_section_title_page(section["title"], page_w, page_h).pages[0]
    writer = PdfWriter()
    for (_, num, rel_idx, entry_type) in plan:
        if entry_type == "title":
            writer.add_page(title_page)
        elif entry_type == "blank" or rel_idx is None:
            writer.add_page(bp)
        else:
            writer.add_page(reader.pages[hymn_map[num]["start"] + rel_idx])
    return writer


# ---------------------------------------------------------------------------
# ASSEMBLE mode
# ---------------------------------------------------------------------------

def cmd_assemble(args):
    pdf_path = download_hymns()
    try:
        reader    = PdfReader(pdf_path)
        all_hymns = detect_hymns(pdf_path)
        validate_hymns(all_hymns)

        out    = Path(args.out_dir)
        page_w, page_h = page_size(reader, all_hymns[0]["start"])
        bp = blank_page(page_w, page_h)

        combined = PdfWriter()

        # Cover (right-hand, p1) + blank back (p2)
        combined.add_page(make_binder_cover(page_w, page_h).pages[0])
        combined.add_page(bp)

        for section in SECTIONS:
            hymns = [h for h in all_hymns
                     if section["num_min"] <= h["num"] <= section["num_max"]]
            if not hymns:
                print(f"\n{section['key']}: no hymns found, skipping.")
                continue

            hymn_map = {h["num"]: h for h in hymns}
            plan     = plan_section(hymns)

            # Section title must land on a right-hand (odd) page.
            if (len(combined.pages) + 1) % 2 == 0:
                combined.add_page(bp)

            for p in render_section(plan, hymn_map, reader, section, page_w, page_h).pages:
                combined.add_page(p)

            print(f"  {section['key']} — {section['title']}: {len(hymns)} hymns, {len(plan)} pages")

        out_path = out / "binder_full.pdf"
        with open(out_path, "wb") as f:
            combined.write(f)
        print(f"\n✓ Full binder saved: {out_path}  ({len(combined.pages)} pages total)")
        print(f"\n{DUPLEX_REMINDER}")
    finally:
        Path(pdf_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# UPDATE mode
# ---------------------------------------------------------------------------

def cmd_update(args):
    pdf_path = download_hymns()
    try:
        reader    = PdfReader(pdf_path)
        all_hymns = detect_hymns(pdf_path)
        validate_hymns(all_hymns)

        # Parse and validate --since values
        since_map: dict[str, int] = {}
        for num in args.since:
            section = section_for_hymn(num)
            if section is None:
                print(
                    f"Error: --since {num} doesn't belong to any configured section.",
                    file=sys.stderr,
                )
                sys.exit(1)
            if section["key"] in since_map:
                print(
                    f"Error: multiple --since values in the same section ({section['key']}).",
                    file=sys.stderr,
                )
                sys.exit(1)
            validate_since(num, all_hymns, section)
            since_map[section["key"]] = num

        out    = Path(args.out_dir)
        page_w, page_h = page_size(reader, all_hymns[0]["start"])
        bp = blank_page(page_w, page_h)

        # Always write a fresh cover
        cover_path   = out / "binder_cover.pdf"
        cover_writer = PdfWriter()
        cover_writer.add_page(make_binder_cover(page_w, page_h).pages[0])
        with open(cover_path, "wb") as f:
            cover_writer.write(f)
        print(f"\n✓ Cover saved: {cover_path}")

        # Process each affected section
        for section in SECTIONS:
            if section["key"] not in since_map:
                continue

            first_new    = since_map[section["key"]]
            last_printed = first_new - 1

            section_hymns = [h for h in all_hymns
                             if section["num_min"] <= h["num"] <= section["num_max"]]
            hymn_map  = {h["num"]: h for h in section_hymns}
            old_hymns = [h for h in section_hymns if h["num"] <= last_printed]

            old_plan = plan_section(old_hymns)
            new_plan = plan_section(section_hymns)

            old_last_page = max(
                (p for (p, n, idx, t) in old_plan if n == last_printed),
                default=1,
            )

            def plan_key(plan, out_page):
                for (p, n, idx, t) in plan:
                    if p == out_page:
                        return (n, idx, t)
                return None

            # Find first page where old and new layouts diverge
            first_changed = None
            for p in range(1, old_last_page + 1):
                if plan_key(old_plan, p) != plan_key(new_plan, p):
                    first_changed = p
                    break

            if first_changed is not None:
                pages_to_print = [(p, n, idx, t) for (p, n, idx, t) in new_plan
                                  if p >= first_changed]
                discard_last = True
            else:
                # No divergence within the already-printed range. But check whether
                # the new layout fills the back of the last printed sheet.
                # Pages print in duplex pairs: pages N (odd) and N+1 share one sheet.
                # If old_last_page is odd (right-hand) and the new plan puts content
                # on old_last_page+1 (previously blank), that sheet must be reprinted.
                next_page    = old_last_page + 1
                old_next     = plan_key(old_plan, next_page)
                new_next     = plan_key(new_plan, next_page)
                back_changed = (old_next != new_next) and (old_last_page % 2 == 1)

                if back_changed:
                    pages_to_print = [(p, n, idx, t) for (p, n, idx, t) in new_plan
                                      if p >= old_last_page]
                    discard_last = True
                else:
                    pages_to_print = [(p, n, idx, t) for (p, n, idx, t) in new_plan
                                      if p > old_last_page]
                    discard_last = False

            old_last_entry = plan_key(old_plan, old_last_page)

            # Write update PDF
            title_page = make_section_title_page(section["title"], page_w, page_h).pages[0]
            writer = PdfWriter()
            for (_, num, rel_idx, entry_type) in pages_to_print:
                if entry_type == "title":
                    writer.add_page(title_page)
                elif entry_type == "blank" or rel_idx is None:
                    writer.add_page(bp)
                else:
                    writer.add_page(reader.pages[hymn_map[num]["start"] + rel_idx])

            update_path = out / f"update_{section['key']}.pdf"
            with open(update_path, "wb") as f:
                writer.write(f)

            # Report
            reprint_count = sum(1 for (p, n, idx, t) in pages_to_print
                                if p <= old_last_page and t == "hymn")
            new_count     = sum(1 for (p, n, idx, t) in pages_to_print
                                if p >  old_last_page and t == "hymn")

            print(f"\n{'='*60}")
            print(f"Section: {section['title']} ({section['key']})")
            if discard_last:
                old_num = old_last_entry[0] if old_last_entry else None
                print("⚠️  DISCARD the last printed sheet from your binders and replace it.")
                if old_num:
                    print(f"   (The sheet currently ending with hymn #{old_num})")
            else:
                print("✅  Keep all existing pages — no reprints needed.")

            print(f"\n📄  Update file: {update_path}")
            print(f"    {len(pages_to_print)} pages to print  "
                  f"({reprint_count} reprint{'s' if reprint_count != 1 else ''}, "
                  f"{new_count} new)")

            print(f"\n  {'Pg':>4}  {'Side':>5}  Content")
            print("  " + "-" * 38)
            for (p, num, rel_idx, entry_type) in pages_to_print:
                side    = "LEFT " if p % 2 == 0 else "right"
                reprint = " ← reprint" if p <= old_last_page else ""
                if entry_type == "title":
                    content = f"[Title: {section['title']}]"
                elif entry_type == "blank" or rel_idx is None:
                    content = "blank"
                else:
                    content = f"Hymn #{num} p{rel_idx + 1}"
                print(f"  {p:>4}  {side}  {content}{reprint}")

        print(f"\n{'='*60}")
        print(f"📄  New cover: {cover_path}  — replace in every binder.")
        print(f"\n{DUPLEX_REMINDER}")
    finally:
        Path(pdf_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LDS Hymn Binder Assembler")
    sub = parser.add_subparsers(dest="command", required=True)

    p_a = sub.add_parser("assemble", help="Build full combined binder PDF")
    p_a.add_argument("--out-dir", default=".", help="Output directory (default: current)")

    p_u = sub.add_parser("update", help="Generate update PDFs for new hymns")
    p_u.add_argument("--since", type=int, action="append", required=True,
                     metavar="HYMN_NUM",
                     help="First new hymn number in a section (repeatable). "
                          "E.g. --since 1063 --since 1212")
    p_u.add_argument("--out-dir", default=".", help="Output directory (default: current)")

    args = parser.parse_args()

    if args.command == "assemble":
        cmd_assemble(args)
    elif args.command == "update":
        cmd_update(args)


if __name__ == "__main__":
    main()
