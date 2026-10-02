# Random Info That You Can't Find Online

A static website of information found in person (on boxes, labels, shelf tags, and parts) that isn't published anywhere online. One page per item. It's built to be found by Google web and image search.

There's no server, database, login, or forms. It's just HTML, CSS, and a few lines of inline JavaScript for the filter box. Hosted free on GitHub Pages.

## Adding a new entry

The easiest way is to give Claude the photo(s) along with the brand, product name, SKU/model, and what the photo shows. Claude handles the steps below and checks the photo for personal info. The manual steps are:

1. **Put the original photo(s) in `originals/`.** This folder is git-ignored and never published.
2. **Check the photo yourself** for faces, license plates, receipts, card or loyalty numbers, employee names or badges, and anything else that shows where you were.
3. **Create the entry.** This strips metadata, resizes the image to 1600px, compresses it, makes a thumbnail, and writes a JSON file:

   ```bash
   py tools/new_entry.py --brand "Harbor Freight" --product "Roadshock 3 in. LED Spotlight" --id SKU 64323 --shows "Beam Pattern" --found-on "Printed on the retail box" --tags "Lighting,Automotive" --photo originals/IMG_1234.jpg beam-pattern
   ```

   If a photo needs cropping or blurring, process it first and pass it in with `--image` instead of `--photo`:

   ```bash
   py tools/process_image.py originals/IMG_1234.jpg --name harbor-freight-roadshock-3in-led-spotlight-64323-beam-pattern --crop 0.05,0.1,0.95,0.9 --blur 0.7,0.8,0.95,0.95
   ```

   Boxes are `left,top,right,bottom` as fractions (0 to 1) of the upright photo, or as pixels. Use `--redact` to cover an area with solid black, which is safer than `--blur` for text such as card numbers.

4. **Fill in every `TODO`** in `content/entries/<slug>.json`. The fields are:
   - `summary`: 1–2 sentences, shown in Google results and on the home page (keep it under about 160 characters)
   - `body`: a few plain-text paragraphs (Google matches images to the text around them)
   - `specs`: optional `[["Beam angle", "30°"], ...]` table
   - `transcription` / `transcription_notes`: printed text, copied exactly. Write `[illegible]` rather than guessing.
   - `sources`: official pages you checked, e.g. `{"label": "...", "url": "...", "note": "no beam pattern shown"}`
   - `images[].alt` and `images[].caption`: descriptive text for each photo
5. **Build:**

   ```bash
   py tools/build.py
   ```

   This regenerates every page, `sitemap.xml`, and `robots.txt`. It refuses to build if any `TODO` is left, an image is missing, or any image still contains metadata.
6. **Preview** at http://localhost:8000/:

   ```bash
   py -m http.server 8000
   ```

7. **Publish** by committing and pushing. GitHub Pages redeploys in about a minute.

   ```bash
   git add -A && git commit -m "Add <product> entry" && git push
   ```

To fix or remove an entry, edit or delete its JSON file (and its images) and rebuild. When you change an entry, set `updated` to that day's date.

## Layout

```
config.json              site name, base URL, disclaimer, Search Console verification code
content/entries/*.json   one file per entry (the source of truth)
templates/               layout.html, entry-template.html, about-content.html
tools/process_image.py   strip metadata, redact, crop, resize, compress
tools/new_entry.py       process photos and create the entry JSON
tools/build.py           generate index, about, entry pages, tag pages, sitemap, robots
style.css, favicon.svg
index.html, about.html, entries/, tags/, sitemap.xml, robots.txt   generated, don't edit by hand
images/, images/thumbs/  cleaned photos only
originals/               git-ignored raw photos
```

## Requirements

Python 3 with Pillow (`py -m pip install --user Pillow`). For iPhone HEIC photos, also install `pillow-heif`.

## Privacy rules

- Raw photos stay in `originals/`, which is never committed.
- `build.py` won't build while any published image still has EXIF, GPS, or XMP data.
- No names, addresses, emails, or store locations go on the site. Keep `found_on` generic, e.g. "Printed on the retail box".
- Only use your own photos with short factual descriptions. Summarize and link to manufacturer material rather than copying it.

## License

The code is licensed under AGPL-3.0 (see `LICENSE`). The photos and entry text are the site author's own.
