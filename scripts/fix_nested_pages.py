#!/usr/bin/env python3
"""
fix_nested_pages.py - repairs essay pages that have a whole web page pasted inside them.

Those pages carry a second <html>, a second <title>, and a second canonical link that points to the home
page, which tells Google "this page is a copy of the home page" so it never indexes it.

For each page in articles/ that has more than one <html>:
  * keeps the outer page (its head, its correct canonical, its footer, tags, comments)
  * replaces the nested page with just its article text (headings, paragraphs, lists, quotes)
  * removes the old ad units and scripts of the nested page
  * puts AdSense back the way the portal does it: one loader in <head>, one ad in the middle, one at the bottom

  python fix_nested_pages.py --root . --dry-run     (only report)
  python fix_nested_pages.py --root .               (rewrite the broken pages)
"""
import argparse
import re
import sys
from pathlib import Path

PUB = "ca-pub-6428799122405621"
SLOT_MIDDLE = "9585168014"
SLOT_BOTTOM = "1982565389"


def ad(slot: str) -> str:
    return ('<div class="ad-slot" style="margin:1.6rem 0;text-align:center;">'
            f'<ins class="adsbygoogle" style="display:block" data-ad-client="{PUB}" data-ad-slot="{slot}" '
            'data-ad-format="auto" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')


def clean_nested(nested: str) -> str:
    """Take the article text out of the nested page."""
    m = re.search(r"<main\b[^>]*>([\s\S]*?)</main>", nested, re.I) or re.search(r"<article\b[^>]*>([\s\S]*?)</article>", nested, re.I)
    if m:
        inner = m.group(1)
    else:
        b = re.search(r"<body\b[^>]*>([\s\S]*)</body>", nested, re.I)
        inner = b.group(1) if b else nested
    inner = re.sub(r"</?(?:article|main)\b[^>]*>", "", inner, flags=re.I)
    for pat in (r"<script\b[\s\S]*?</script>", r"<style\b[\s\S]*?</style>", r"<noscript\b[\s\S]*?</noscript>",
                r"<header\b[\s\S]*?</header>", r"<footer\b[\s\S]*?</footer>", r"<nav\b[\s\S]*?</nav>",
                r"<div class=\"ad-container\"[\s\S]*?</div>", r"<div class=\"ad-slot\"[\s\S]*?</div>",
                r"<ins class=\"adsbygoogle\"[\s\S]*?</ins>", r"<h1\b[\s\S]*?</h1>", r"<!--[\s\S]*?-->"):
        inner = re.sub(pat, "", inner, flags=re.I)
    return re.sub(r"\n\s*\n+", "\n", inner).strip()


def add_ads(content: str) -> str:
    parts = re.split(r"(?<=</p>)\s*(?=<p)", content)
    if len(parts) >= 2:
        mid = max(0, len(parts) // 2 - 1)
        parts[mid] = parts[mid] + ad(SLOT_MIDDLE)
        body = "\n".join(parts)
    else:
        body = content + ad(SLOT_MIDDLE)
    return body + ad(SLOT_BOTTOM)


def words(html: str) -> int:
    return len(re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)\b[\s\S]*?</\1>", "", html, flags=re.I)).split())


def strip_ads(html: str) -> str:
    """Remove ad units that sit outside the nested page, so the rebuilt page has exactly one middle and one bottom."""
    html = re.sub(r'<div class="ad-slot"[^>]*>\s*<ins class="adsbygoogle"[\s\S]*?</ins>\s*(?:<script>[\s\S]*?</script>\s*)?</div>', "", html, flags=re.I)
    html = re.sub(r'<ins class="adsbygoogle"[\s\S]*?</ins>\s*(?:<script>\s*\(adsbygoogle[\s\S]*?</script>)?', "", html, flags=re.I)
    return html


def fix(txt: str):
    starts = [m.start() for m in re.finditer(r"<html[\s>]", txt, re.I)]
    if len(starts) < 2:
        return None
    s = starts[1]
    e = txt.lower().find("</html>", s)
    if e < 0:
        return None
    e += len("</html>")
    nested = txt[s:e]
    new = strip_ads(txt[:s]) + add_ads(clean_nested(nested)) + strip_ads(txt[e:])
    # outer </body></html> that followed the nested page's </html> is kept; make sure the head has the loader
    if "adsbygoogle.js" not in new[:new.lower().find("</head>")]:
        loader = (f'<meta name="google-adsense-account" content="{PUB}">\n'
                  f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={PUB}" '
                  'crossorigin="anonymous"></script>\n')
        new = re.sub(r"</head>", loader + "</head>", new, count=1, flags=re.I)
    # the whole page keeps only the first (outer) canonical and title
    return new



OLD_HOSTS = ("https://poetic-codes.pansensoyglenn150.workers.dev",)
NEW_HOST = "https://poetic-codes.pages.dev"
STUB_DIRS = ("ai", "culinary", "culture", "economy", "global-politics", "history", "music-video", "philosophy", "programming")


SKIP_DIRS = {".git", ".github", "node_modules", "scripts", "deleted-essays", "video-jobs"}


def fix_old_hosts(root: Path, dry: bool):
    """Replace the old workers.dev address with poetic-codes.pages.dev everywhere it appears in the
    site's pages (canonical, og:url, links, JSON-LD), sitemap and feeds. Script files (.js) are left
    alone because the publishing API still lives at that address."""
    n = 0
    files = [p for ext in ("*.html", "*.xml", "*.txt") for p in root.rglob(ext)]
    for p in sorted(set(files)):
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        t = p.read_text(encoding="utf-8", errors="ignore")
        new = t
        for old in OLD_HOSTS:
            new = new.replace(old, NEW_HOST)
        if new != t:
            print(f"{'would change' if dry else 'changed'} old address in {p.relative_to(root).as_posix()}")
            n += 1
            if not dry:
                p.write_text(new, encoding="utf-8")
    return n


def fix_stubs(root: Path, dry: bool):
    """Old redirect stub pages in the category folders: point their canonical at the real /articles/ page."""
    n = 0
    for d in STUB_DIRS:
        for p in sorted((root / d).glob("*.html")) if (root / d).is_dir() else []:
            t = p.read_text(encoding="utf-8")
            if "location.replace(" not in t:
                continue
            slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p.stem)
            target = root / "articles" / f"{slug}.html"
            if not target.exists():
                continue
            url = f"{NEW_HOST}/articles/{slug}.html"
            new = re.sub(r'(<link[^>]+rel=["\']canonical["\'][^>]*href=["\'])[^"\']*', r"\g<1>" + url, t, count=1, flags=re.I)
            new = re.sub(r'(<meta[^>]+property=["\']og:url["\'][^>]*content=["\'])[^"\']*', r"\g<1>" + url, new, count=1, flags=re.I)
            if new != t:
                print(f"{'would point' if dry else 'pointed'} {d}/{p.name} at articles/{slug}.html")
                n += 1
                if not dry:
                    p.write_text(new, encoding="utf-8")
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--dir", default="articles")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    folder = Path(a.root) / a.dir
    fixed = skipped = 0
    for p in sorted(folder.glob("*.html")):
        txt = p.read_text(encoding="utf-8")
        new = fix(txt)
        if new is None:
            continue
        before, after = words(txt), words(new)
        if after < before * 0.6:
            print(f"SKIPPED {p.name}: too much text would be lost ({before} -> {after} words); fix by hand")
            skipped += 1
            continue
        print(f"{'would fix' if a.dry_run else 'fixed'} {p.name}: {before} -> {after} words, "
              f"canonicals {len(re.findall(r'rel=.canonical.', txt, re.I))} -> {len(re.findall(r'rel=.canonical.', new, re.I))}")
        if not a.dry_run:
            p.write_text(new, encoding="utf-8")
        fixed += 1
    print(f"\n{fixed} page(s) {'to fix' if a.dry_run else 'fixed'}, {skipped} skipped.")
    h = fix_old_hosts(Path(a.root), a.dry_run)
    st = fix_stubs(Path(a.root), a.dry_run)
    print(f"{h} page(s) with the old workers.dev address, {st} redirect stub(s) re-pointed.")


if __name__ == "__main__":
    sys.exit(main())
