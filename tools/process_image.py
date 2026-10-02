"""Clean a photo for publishing.

  * applies the camera's rotation, then strips ALL metadata (EXIF, GPS, XMP, comments)
  * optional: --redact (solid box) / --blur (pixelate) regions, --crop, --rotate
  * converts to sRGB, resizes to 1600px on the long side, saves a compressed JPEG
  * writes a 640px thumbnail to images/thumbs/
  * re-opens the output and refuses to finish if any metadata survived

Box coordinates are LEFT,TOP,RIGHT,BOTTOM in the (upright) original photo, either
in pixels or as fractions 0-1 of the width/height. Redact/blur are applied before
cropping, so all boxes use the same coordinates.

Example:
  py tools/process_image.py originals/IMG_1234.jpg --name harbor-freight-roadshock-3in-led-spotlight-64323-beam-pattern \
     --crop 0.05,0.10,0.95,0.90 --blur 0.70,0.80,0.95,0.95
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from PIL import Image, ImageCms, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import IMAGES, THUMBS, metadata_problems, slugify  # noqa: E402

try:  # iPhone HEIC support, if `py -m pip install --user pillow-heif` was run
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

MAX_SIDE = 1600
THUMB_SIDE = 640
QUALITY = 82
THUMB_QUALITY = 78

GPS_IFD = 0x8825
EXIF_IFD = 0x8769
DATETIME_ORIGINAL = 36867
DATETIME = 306


def parse_box(spec: str, w: int, h: int) -> tuple[int, int, int, int]:
    vals = [float(v) for v in spec.split(",")]
    if len(vals) != 4:
        raise SystemExit(f"Box must be LEFT,TOP,RIGHT,BOTTOM: {spec!r}")
    if all(0 <= v <= 1 for v in vals):
        vals = [vals[0] * w, vals[1] * h, vals[2] * w, vals[3] * h]
    l, t, r, b = (round(v) for v in vals)
    l, r = max(0, min(l, w)), max(0, min(r, w))
    t, b = max(0, min(t, h)), max(0, min(b, h))
    if r <= l or b <= t:
        raise SystemExit(f"Box is empty after clamping to the {w}x{h} image: {spec!r}")
    return l, t, r, b


def to_srgb(im: Image.Image) -> Image.Image:
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    icc = im.info.get("icc_profile")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:  # broken/unsupported profile: plain conversion is fine
            pass
    return im.convert("RGB")


def pixelate(im: Image.Image, box: tuple[int, int, int, int]) -> None:
    region = im.crop(box)
    w, h = region.size
    block = max(8, max(w, h) // 12)
    small = region.resize((max(1, w // block), max(1, h // block)), Image.Resampling.BILINEAR)
    region = small.resize((w, h), Image.Resampling.NEAREST).filter(ImageFilter.GaussianBlur(block // 2))
    im.paste(region, box)


def process(src: Path, name: str, crop: str | None = None, redact: list[str] = (), blur: list[str] = (),
            rotate: int = 0, max_side: int = MAX_SIDE, quality: int = QUALITY) -> dict:
    name = slugify(Path(name).stem)
    out = IMAGES / f"{name}.jpg"
    thumb = THUMBS / f"{name}.jpg"
    IMAGES.mkdir(exist_ok=True)
    THUMBS.mkdir(exist_ok=True)

    with Image.open(src) as im:
        im.load()
        exif = im.getexif()
        had = metadata_problems(src)
        gps = bool(exif.get_ifd(GPS_IFD))
        taken = exif.get_ifd(EXIF_IFD).get(DATETIME_ORIGINAL) or exif.get(DATETIME)
        orig_size = im.size
        im = ImageOps.exif_transpose(im)
        im = to_srgb(im)

    if rotate:
        im = im.rotate(-rotate, expand=True)  # positive = clockwise
    w, h = im.size
    for spec in redact:
        im.paste((0, 0, 0), parse_box(spec, w, h))
    for spec in blur:
        pixelate(im, parse_box(spec, w, h))
    if crop:
        im = im.crop(parse_box(crop, w, h))

    im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    im.save(out, "JPEG", quality=quality, optimize=True, progressive=True)
    t = im.copy()
    t.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.Resampling.LANCZOS)
    t.save(thumb, "JPEG", quality=THUMB_QUALITY, optimize=True, progressive=True)

    for p in (out, thumb):
        left = metadata_problems(p)
        if left:
            p.unlink()
            raise SystemExit(f"ERROR: metadata {left} survived in {p.name}; output deleted.")

    info = {
        "file": out.name,
        "width": im.width,
        "height": im.height,
        "bytes": out.stat().st_size,
        "date_taken": str(taken).strip() if taken else None,
    }
    print(f"{src.name}: {orig_size[0]}x{orig_size[1]} -> images/{out.name} "
          f"{im.width}x{im.height}, {info['bytes'] // 1024} KB (+ thumbnail)")
    print(f"  metadata removed: {', '.join(had) if had else 'none was present'}"
          f"{'  [GPS location was present and has been removed]' if gps else ''}")
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path, help="original photo (keep originals in originals/, which is git-ignored)")
    ap.add_argument("--name", required=True, help="descriptive output name, e.g. brand-product-sku-what-it-shows")
    ap.add_argument("--crop", help="LEFT,TOP,RIGHT,BOTTOM to keep")
    ap.add_argument("--redact", action="append", default=[], help="box to cover with solid black (repeatable)")
    ap.add_argument("--blur", action="append", default=[], help="box to pixelate (repeatable)")
    ap.add_argument("--rotate", type=int, default=0, help="extra clockwise rotation in degrees, e.g. 90")
    ap.add_argument("--max", type=int, default=MAX_SIDE, help=f"long side in px (default {MAX_SIDE})")
    ap.add_argument("--quality", type=int, default=QUALITY, help=f"JPEG quality (default {QUALITY})")
    a = ap.parse_args()
    process(a.src, a.name, a.crop, a.redact, a.blur, a.rotate, a.max, a.quality)


if __name__ == "__main__":
    main()
