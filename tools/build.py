"""Build the whole site from content/entries/*.json and templates/.

Regenerates index.html, about.html, entries/*.html, tags/*.html, sitemap.xml and
robots.txt. Refuses to build if an entry still has a TODO, is missing an image, or
if any image in images/ still contains metadata.

  py tools/build.py
Preview locally:
  py -m http.server 8000      (then open http://localhost:8000/)
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date
from pathlib import Path
from string import Template
from xml.sax.saxutils import escape as xml_escape

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CONTENT, IMAGES, ROOT, TEMPLATES, THUMBS, load_config, metadata_problems, slugify  # noqa: E402

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]

e = html.escape  # escape every piece of entry text that goes into HTML


def month(ym: str) -> str:
    y, m = ym.split("-")[:2]
    return f"{MONTHS[int(m) - 1]} {y}"


def long_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return f"{MONTHS[int(m) - 1]} {int(d)}, {y}"


def json_ld(data: dict) -> str:
    text = json.dumps(data, indent=1, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">\n{text}\n</script>'


# ---------------------------------------------------------------- loading / validation

def find_todos(value, path="") -> list[str]:
    if isinstance(value, str):
        return [path] if "TODO" in value else []
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in find_todos(v, f"{path}[{i}]")]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in find_todos(v, f"{path}.{k}" if path else k)]
    return []


def load_entries() -> list[dict]:
    entries, errors = [], []
    for f in sorted(CONTENT.glob("*.json")):
        ent = json.loads(f.read_text(encoding="utf-8"))
        ent["slug"] = f.stem
        where = f"content/entries/{f.name}"
        for key in ("brand", "product", "shows", "summary", "body", "images", "published", "photographed"):
            if not ent.get(key):
                errors.append(f"{where}: missing '{key}'")
        errors += [f"{where}: TODO left in '{p}'" for p in find_todos(ent)]
        if len(ent.get("summary", "")) > 170:
            print(f"warning: {where}: summary is {len(ent['summary'])} chars; Google shows ~160")
        for img in ent.get("images", []):
            for key in ("file", "alt", "caption"):
                if not img.get(key):
                    errors.append(f"{where}: image missing '{key}'")
            for p in (IMAGES / img.get("file", "?"), THUMBS / img.get("file", "?")):
                if not p.exists():
                    errors.append(f"{where}: {p.relative_to(ROOT).as_posix()} not found")
                    continue
                with Image.open(p) as im:
                    img["thumb_size" if p.parent == THUMBS else "size"] = im.size
        entries.append(ent)

    for p in sorted(IMAGES.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            left = metadata_problems(p)
            if left:
                errors.append(f"{p.relative_to(ROOT).as_posix()}: still has metadata {left}; run tools/process_image.py")

    used = {i["file"] for ent in entries for i in ent.get("images", [])}
    for p in sorted(IMAGES.glob("*.jpg")):
        if p.name not in used:
            print(f"warning: images/{p.name} isn't used by any entry")

    if errors:
        print("Build stopped:\n  " + "\n  ".join(errors))
        sys.exit(1)
    entries.sort(key=lambda x: (x["published"], x["slug"]), reverse=True)
    return entries


# ---------------------------------------------------------------- entry helpers

# Everyday comparisons for light levels (rough, commonly cited values), brightest first.
LUX_SCALE = [
    (10000, "full daylight (not direct sun)"),
    (1000, "daylight on an overcast day"),
    (300, "a brightly lit office or store"),
    (100, "a typical living room at night"),
    (50, "a dimly lit room"),
    (10, "a well-lit street at night"),
    (3, "a dim side street at night"),
    (1, "deep twilight, or a candle about 3 ft away"),
    (0.2, "a bright full moon"),
    (0, "moonlight or less"),
]


def lux_compare(lux: float) -> str:
    return next(text for floor, text in LUX_SCALE if lux >= floor)


def fmt_num(n: float) -> str:
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def brightness(ent: dict) -> str:
    """'How bright is that?' box for entries with a `beam` list of {distance_ft, lux} points."""
    if not ent.get("beam"):
        return ""
    rows = "".join(
        f"<tr><td>{fmt_num(p['distance_ft'])} ft</td><td>{fmt_num(p['lux'])} lx</td>"
        f"<td>{e(lux_compare(p['lux']))}</td></tr>" for p in ent["beam"])
    return f"""  <section class="brightness" aria-labelledby="bright-h">
    <h2 id="bright-h">How bright is that?</h2>
    <table><thead><tr><th scope="col">Distance from light</th><th scope="col">Light level (chart)</th><th scope="col">Roughly as bright as</th></tr></thead>
    <tbody>{rows}</tbody></table>
    <p class="note">Lux (lx) is how much light lands on a surface. For reference: full moon about 0.1–0.3 lx, a candle 3 ft away about 1 lx, a lit street 10–20 lx, a living room 50–150 lx, an office 300–500 lx, an overcast day 1,000+ lx. Advertised &ldquo;beam distance&rdquo; is usually measured to 0.25 lx (the ANSI FL1 standard), about full-moon brightness, so treat it as the edge of usable light, not where the beam is still bright.</p>
  </section>"""


def ids_text(ent: dict) -> str:
    return " · ".join(f"{i['label']} {i['value']}" for i in ent.get("ids", []))


def title(ent: dict) -> str:
    ids = ent.get("ids", [])
    ident = f" ({ids[0]['label']} {ids[0]['value']})" if ids else ""
    return f"{ent['brand']} {ent['product']}{ident} - {ent['shows']}"


def all_tags(ent: dict) -> list[str]:
    seen, out = set(), []
    for t in [ent["brand"], *ent.get("tags", [])]:
        if slugify(t) not in seen:
            seen.add(slugify(t))
            out.append(t)
    return out


def tag_links(ent: dict, root: str) -> str:
    return "".join(f'<li><a href="{root}tags/{slugify(t)}.html">{e(t)}</a></li>' for t in all_tags(ent))


def card(ent: dict, root: str) -> str:
    img = ent["images"][0]
    tw, th = img["thumb_size"]
    url = f"{root}entries/{ent['slug']}.html"
    bits = [e(ent["brand"])]
    if ent.get("ids"):
        bits.append(e(ids_text(ent)))
    bits.append(f"Photographed {month(ent['photographed'])}")
    search = " ".join([title(ent), ent["summary"], *all_tags(ent)]).lower()
    return f"""<li class="card" data-search="{e(search)}">
  <a href="{url}" tabindex="-1" aria-hidden="true"><img src="{root}images/thumbs/{e(img['file'])}" width="{tw}" height="{th}" alt="" loading="lazy" decoding="async"></a>
  <div>
    <h2><a href="{url}">{e(title(ent))}</a></h2>
    <p class="brandline">{' · '.join(bits)}</p>
    <p class="summary">{e(ent['summary'])}</p>
    <ul class="tags">{tag_links(ent, root)}</ul>
  </div>
</li>"""


# ---------------------------------------------------------------- page rendering

class Site:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.base = cfg["base_url"]
        self.layout = Template((TEMPLATES / "layout.html").read_text(encoding="utf-8"))
        self.entry_tpl = Template((TEMPLATES / "entry-template.html").read_text(encoding="utf-8"))
        self.written: set[Path] = set()

    def page(self, rel: str, *, title: str, description: str, content: str, root: str,
             og_type: str = "website", image: dict | None = None, head_extra: str = "") -> None:
        canonical = self.base + ("" if rel == "index.html" else rel)
        og = ""
        if image:
            w, h = image["size"]
            og = (f'<meta property="og:image" content="{self.base}images/{e(image["file"])}">\n'
                  f'<meta property="og:image:width" content="{w}">\n'
                  f'<meta property="og:image:height" content="{h}">\n'
                  f'<meta property="og:image:alt" content="{e(image["alt"])}">\n'
                  f'<meta name="twitter:card" content="summary_large_image">')
        verify = self.cfg.get("google_site_verification", "")
        out = self.layout.substitute(
            lang=self.cfg.get("language", "en"), title=e(title), description=e(description),
            canonical=canonical, og_type=og_type, og_image=og, site_name=e(self.cfg["site_name"]),
            verification=f'<meta name="google-site-verification" content="{e(verify)}">' if verify else "",
            root=root, head_extra=head_extra, content=content, disclaimer=e(self.cfg["disclaimer"]),
        )
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(out, encoding="utf-8", newline="\n")
        self.written.add(path)

    def entry(self, ent: dict) -> None:
        rel = f"entries/{ent['slug']}.html"
        url = self.base + rel
        t = title(ent)

        figures = []
        for n, img in enumerate(ent["images"]):
            w, h = img["size"]
            tw, _ = img["thumb_size"]
            src = f"../images/{e(img['file'])}"
            load = 'fetchpriority="high"' if n == 0 else 'loading="lazy"'
            figures.append(f"""  <figure>
    <a href="{src}"><img src="{src}" srcset="../images/thumbs/{e(img['file'])} {tw}w, {src} {w}w" sizes="(max-width: 860px) 100vw, 828px" width="{w}" height="{h}" alt="{e(img['alt'])}" {load} decoding="async"></a>
    <figcaption>{e(img['caption'])}</figcaption>
  </figure>""")

        body = "\n".join(f"  <p>{e(p)}</p>" for p in ent["body"])
        specs = ""
        if ent.get("specs"):
            rows = "".join(f"<tr><th scope=\"row\">{e(k)}</th><td>{e(v)}</td></tr>" for k, v in ent["specs"])
            specs = f'  <h2>Details shown</h2>\n  <table class="specs"><tbody>{rows}</tbody></table>'
        transcription = ""
        if ent.get("transcription"):
            transcription = f'  <h2>Printed text (transcribed)</h2>\n  <pre class="transcription">{e(ent["transcription"])}</pre>'
            if ent.get("transcription_notes"):
                transcription += f'\n  <p class="note">{e(ent["transcription_notes"])}</p>'
        sources = ""
        if ent.get("sources"):
            items = "".join(
                f'<li><a href="{e(s["url"])}" rel="noopener">{e(s["label"])}</a>'
                f'{" - " + e(s["note"]) if s.get("note") else ""}</li>' for s in ent["sources"])
            sources = f"  <h2>Official sources checked</h2>\n  <ul>{items}</ul>"

        meta = [f'<a href="../tags/{slugify(ent["brand"])}.html">{e(ent["brand"])}</a>']
        if ent.get("ids"):
            meta.append(e(ids_text(ent)))
        meta.append(e(ent["found_on"]))
        meta.append(f"Photographed {month(ent['photographed'])}")
        updated = ent.get("updated", ent["published"])

        content = self.entry_tpl.substitute(
            brand=e(ent["brand"]), brand_slug=slugify(ent["brand"]), h1=e(t), meta_line=" · ".join(meta),
            summary=e(ent["summary"]), brightness=brightness(ent), figures="\n".join(figures), body=body, specs=specs,
            transcription=transcription, sources=sources, tags=tag_links(ent, "../"),
            published=long_date(ent["published"]),
            updated_note=f" · Updated {long_date(updated)}" if updated != ent["published"] else "",
        )

        image_objs = [{
            "@type": "ImageObject",
            "contentUrl": f"{self.base}images/{img['file']}",
            "thumbnailUrl": f"{self.base}images/thumbs/{img['file']}",
            "caption": img["caption"], "description": img["alt"],
            "width": img["size"][0], "height": img["size"][1],
            "creditText": self.cfg["site_name"],
        } for img in ent["images"]]
        product = {"@type": "Product", "name": f"{ent['brand']} {ent['product']}",
                   "brand": {"@type": "Brand", "name": ent["brand"]}}
        for i in ent.get("ids", []):
            key = "sku" if i["label"].lower() in ("sku", "item", "item #") else "mpn"
            product.setdefault(key, i["value"])
        ld = json_ld({
            "@context": "https://schema.org", "@type": "WebPage", "name": t, "url": url,
            "description": ent["summary"], "datePublished": ent["published"], "dateModified": updated,
            "isPartOf": {"@type": "WebSite", "name": self.cfg["site_name"], "url": self.base},
            "primaryImageOfPage": image_objs[0], "image": image_objs, "about": product,
        })
        self.page(rel, title=t, description=ent["summary"], content=content, root="../",
                  og_type="article", image=ent["images"][0], head_extra=ld)

    def listing(self, rel: str, entries: list[dict], *, h1: str, intro: str, title: str, description: str,
                root: str, search: bool, head_extra: str = "") -> None:
        if entries:
            cards = "\n".join(card(x, root) for x in entries)
            listing = f'<ul class="cards" id="entries">\n{cards}\n</ul>'
        else:
            listing = "<p>No entries yet.</p>"
        box = ""
        if search and len(entries) > 1:
            box = ('<input class="search" id="q" type="search" placeholder="Filter by brand, product, SKU…" '
                   'aria-label="Filter entries" hidden>\n<p id="none" class="note" hidden>No matches.</p>\n'
                   "<script>(()=>{const q=document.getElementById('q'),n=document.getElementById('none'),"
                   "c=[...document.querySelectorAll('#entries .card')];q.hidden=false;q.addEventListener('input',()=>{"
                   "const t=q.value.trim().toLowerCase().split(/\\s+/);let shown=0;c.forEach(el=>{"
                   "const ok=t.every(w=>el.dataset.search.includes(w));el.hidden=!ok;shown+=ok});n.hidden=shown>0})})()</script>")
        content = f"<h1>{h1}</h1>\n<p class=\"intro\">{intro}</p>\n{box}\n{listing}"
        image = entries[0]["images"][0] if entries else None
        self.page(rel, title=title, description=description, content=content, root=root,
                  image=image, head_extra=head_extra)


def main() -> None:
    cfg = load_config()
    entries = load_entries()
    site = Site(cfg)
    name, base = cfg["site_name"], cfg["base_url"]

    for ent in entries:
        site.entry(ent)

    site.listing(
        "index.html", entries, h1=e(name),
        intro=f'{e(cfg["tagline"])} <a href="about.html">About this site</a>.',
        title=name, description=cfg["tagline"], root="", search=True,
        head_extra=json_ld({"@context": "https://schema.org", "@type": "WebSite", "name": name, "url": base,
                            "description": cfg["tagline"]}),
    )

    about = Template((TEMPLATES / "about-content.html").read_text(encoding="utf-8"))
    site.page("about.html", title=f"About - {name}",
              description=f"What {name} is: information found in person on packaging and labels that is missing online.",
              content=about.substitute(disclaimer=e(cfg["disclaimer"])), root="")

    tags: dict[str, tuple[str, list[dict]]] = {}
    for ent in entries:
        for t in all_tags(ent):
            tags.setdefault(slugify(t), (t, []))[1].append(ent)
    for slug, (label, items) in sorted(tags.items()):
        n = len(items)
        site.listing(
            f"tags/{slug}.html", items, h1=e(label), root="../", search=False,
            intro=f'{n} entr{"y" if n == 1 else "ies"} tagged {e(label)}. <a href="../">All entries</a>.',
            title=f"{label} - {name}",
            description=f"{label}: specs, diagrams, and labels found in person that aren't published online.",
        )

    # Remove pages left over from deleted/renamed entries or tags (generated files only).
    for folder in ("entries", "tags"):
        for p in (ROOT / folder).glob("*.html"):
            if p not in site.written:
                print(f"removed stale page {folder}/{p.name}")
                p.unlink()

    # sitemap.xml with image extension
    today = date.today().isoformat()
    newest = max((x.get("updated", x["published"]) for x in entries), default=today)
    urls = [(base, newest, []), (base + "about.html", None, [])]
    urls += [(f"{base}entries/{x['slug']}.html", x.get("updated", x["published"]),
              [f"{base}images/{i['file']}" for i in x["images"]]) for x in entries]
    urls += [(f"{base}tags/{s}.html", max(x.get("updated", x["published"]) for x in items), [])
             for s, (_, items) in sorted(tags.items())]
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
             'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">']
    for loc, mod, imgs in urls:
        lines.append(f"  <url><loc>{xml_escape(loc)}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "")
                     + "".join(f"<image:image><image:loc>{xml_escape(i)}</image:loc></image:image>" for i in imgs)
                     + "</url>")
    lines.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n",
                                     encoding="utf-8", newline="\n")

    print(f"Built {len(entries)} entr{'y' if len(entries) == 1 else 'ies'}, {len(tags)} tag pages, "
          f"index.html, about.html, sitemap.xml, robots.txt")


if __name__ == "__main__":
    main()
