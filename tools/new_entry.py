"""Start a new entry: clean the photos and write content/entries/<slug>.json.

Example:
  py tools/new_entry.py --brand "Harbor Freight" --product "Roadshock 3 in. LED Spotlight" \
     --id SKU 64323 --shows "Beam Pattern" --found-on "Printed on the retail box" \
     --tags "Lighting,Automotive" \
     --photo originals/IMG_1234.jpg beam-pattern

Each --photo is PATH LABEL; the image is saved as images/<slug>-<label>.jpg.
If a photo needs cropping/redaction, run tools/process_image.py on it yourself first
and pass the result with --image FILENAME instead.

Then fill in every "TODO" in the JSON file and run: py tools/build.py
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTENT, IMAGES, slugify  # noqa: E402
from process_image import process  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brand", required=True)
    ap.add_argument("--product", required=True, help="product name without the brand if possible")
    ap.add_argument("--id", nargs=2, action="append", default=[], metavar=("LABEL", "VALUE"),
                    help="identifier, e.g. --id SKU 64323 --id Model ABC-1 (first one goes in the title)")
    ap.add_argument("--shows", required=True, help='what the photo shows, e.g. "Beam Pattern"')
    ap.add_argument("--found-on", default="TODO: e.g. Printed on the retail box",
                    help="where the info is printed (keep it generic: no store address)")
    ap.add_argument("--tags", default="", help="comma-separated, e.g. Lighting,Automotive")
    ap.add_argument("--photo", nargs=2, action="append", default=[], metavar=("PATH", "LABEL"))
    ap.add_argument("--image", action="append", default=[], help="already-processed file in images/")
    ap.add_argument("--slug", help="override the generated page slug")
    ap.add_argument("--force", action="store_true", help="overwrite an existing entry file")
    a = ap.parse_args()

    if not a.photo and not a.image:
        ap.error("give at least one --photo or --image")
    first_id = a.id[0][1] if a.id else ""
    slug = slugify(a.slug or f"{a.brand} {a.product} {first_id}")
    path = CONTENT / f"{slug}.json"
    if path.exists() and not a.force:
        sys.exit(f"{path.relative_to(CONTENT.parent.parent)} already exists (use --force to overwrite)")

    images, taken = [], []
    for src, label in a.photo:
        info = process(Path(src), f"{slug}-{slugify(label)}")
        images.append(info["file"])
        if info["date_taken"]:
            taken.append(info["date_taken"])
    for name in a.image:
        if not (IMAGES / name).exists():
            sys.exit(f"images/{name} not found")
        images.append(name)

    # EXIF dates look like "2026:09:28 14:03:11"; only the month is kept.
    photographed = min(taken)[:7].replace(":", "-") if taken else date.today().isoformat()[:7]
    today = date.today().isoformat()
    entry = {
        "brand": a.brand,
        "product": a.product,
        "ids": [{"label": label, "value": value} for label, value in a.id],
        "shows": a.shows,
        "found_on": a.found_on,
        "photographed": photographed,
        "published": today,
        "updated": today,
        "tags": [t.strip() for t in a.tags.split(",") if t.strip()],
        "summary": "TODO: one or two sentences for search results (under ~160 characters).",
        "body": ["TODO: a few sentences of plain text describing what the photo shows and why it's useful."],
        "beam": [],
        "specs": [],
        "transcription": "",
        "transcription_notes": "",
        "sources": [],
        "images": [{"file": f, "alt": "TODO: descriptive alt text", "caption": "TODO: visible caption"}
                   for f in images],
    }
    CONTENT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nWrote content/entries/{slug}.json. Fill in the TODOs, then run: py tools/build.py")


if __name__ == "__main__":
    main()
