"""Shared helpers for the site tools."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "images"
THUMBS = IMAGES / "thumbs"
CONTENT = ROOT / "content" / "entries"
TEMPLATES = ROOT / "templates"

# JPEG/PNG metadata blocks that can carry personal info (camera, GPS, timestamps, editing history).
METADATA_KEYS = ("exif", "xmp", "XML:com.adobe.xmp", "photoshop", "comment", "iptc")


def load_config() -> dict:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    if not cfg["base_url"].endswith("/"):
        cfg["base_url"] += "/"
    return cfg


def slugify(text: str) -> str:
    """'Roadshock 3 in. LED Spotlight' -> 'roadshock-3in-led-spotlight'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ")
    text = re.sub(r"(\d)\s*(?:in\.|inch(?:es)?\b|\")", r"\1in", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return re.sub(r"-{2,}", "-", text)


def metadata_problems(path: Path) -> list[str]:
    """Return the names of any metadata blocks still present in an image file."""
    from PIL import Image

    with Image.open(path) as im:
        found = [k for k in METADATA_KEYS if im.info.get(k)]
        if im.getexif() and "exif" not in found:
            found.append("exif")
    return found
