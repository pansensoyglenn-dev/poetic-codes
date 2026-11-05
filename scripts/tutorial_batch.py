#!/usr/bin/env python3
"""Make videos for every Poetic Bytes tutorial page that does not have one yet.

Where the page list comes from (first that applies):
  1. PAGES            links separated by spaces / commas / new lines (the workflow input)
  2. tutorial-urls.txt one link per line in the repo root ("#" starts a comment)
  3. the site's sitemap.xml
  4. the links found on the site's home page

Finished videos are uploaded to a GitHub Release (tag "tutorial-videos") as <page-name>.mp4 plus a
<page-name>.description.txt. A page that already has its .mp4 there is skipped, so you can run this
again and again and it only works on new pages.
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urldefrag, urlparse

import requests
from bs4 import BeautifulSoup

SITE = os.environ.get("SITE_URL", "https://poetic-bytes.vercel.app").rstrip("/")
SITEMAP = os.environ.get("SITEMAP_URL", SITE + "/sitemap.xml")
URL_FILE = Path(os.environ.get("URL_FILE", "tutorial-urls.txt"))
EXCLUDE = re.compile(os.environ.get(
    "EXCLUDE", r"/(index|about|contact|privacy|terms|404|sitemap|search|offline|tutorials?|courses?|blog)(\.html)?/?$"), re.I)
INCLUDE = os.environ.get("INCLUDE", "").strip()
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "3"))
MAX_MINUTES = float(os.environ.get("MAX_MINUTES", "100"))
TAG = os.environ.get("RELEASE_TAG", "tutorial-videos")
VIDEO_SCRIPT = Path(__file__).with_name("tutorial_video.py")
UA = "tutorial-video-bot/1.0"
OUT = Path("out")


def log(*a):
    print(*a, flush=True)


def clean(url):
    url, _ = urldefrag(url.strip())
    url = url.split("?")[0]
    u = urlparse(url)
    if u.netloc != urlparse(SITE).netloc:
        return ""
    path = u.path or "/"
    if path == "/":
        return ""
    last = path.rsplit("/", 1)[-1]
    if "." in last and not last.lower().endswith((".html", ".htm")):
        return ""                       # an image, script, pdf, ...
    return f"{u.scheme}://{u.netloc}{path}"


def keep(url):
    if not url or EXCLUDE.search(url):
        return False
    return not INCLUDE or re.search(INCLUDE, url) is not None


def slug_for(url):
    path = urlparse(url).path.strip("/")
    path = re.sub(r"\.html?$", "", path)
    return re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "page"


def from_sitemap():
    r = requests.get(SITEMAP, headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
    # a sitemap index points to other sitemaps
    out = []
    for loc in locs:
        if loc.lower().endswith(".xml"):
            try:
                rr = requests.get(loc, headers={"User-Agent": UA}, timeout=60)
                out += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", rr.text)
            except Exception:
                pass
        else:
            out.append(loc)
    return out


def from_homepage():
    r = requests.get(SITE + "/", headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        h = a["href"]
        if h.startswith("/"):
            h = SITE + h
        elif not h.startswith("http"):
            h = SITE + "/" + h.lstrip("./")
        out.append(h)
    return out


def page_list():
    raw = os.environ.get("PAGES", "").strip()
    if raw:
        return [u for u in re.split(r"[\s,]+", raw) if u], "the PAGES input"
    if URL_FILE.exists():
        lines = [l.split("#")[0].strip() for l in URL_FILE.read_text(encoding="utf-8").splitlines()]
        return [l for l in lines if l], str(URL_FILE)
    try:
        urls = from_sitemap()
        if urls:
            return urls, "the sitemap"
    except Exception as e:
        log(f"  no usable sitemap ({str(e)[:80]}); trying the home page")
    return from_homepage(), "the home page links"


def gh(*args, check=False):
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=check)


def existing_videos():
    r = gh("release", "view", TAG, "--json", "assets", "-q", ".assets[].name")
    if r.returncode != 0:
        c = gh("release", "create", TAG, "--title", "Tutorial videos",
               "--notes", "Narrated videos made from the Poetic Bytes tutorial pages.")
        if c.returncode != 0:
            raise RuntimeError("could not create the release: " + (c.stderr or "")[-300:])
        return set()
    return {n[:-4] for n in r.stdout.split() if n.endswith(".mp4")}


def main():
    raw_urls, source = page_list()
    seen, urls = set(), []
    for u in raw_urls:
        c = clean(u)
        if c and keep(c) and c not in seen:
            seen.add(c)
            urls.append(c)
    log(f"{len(urls)} candidate page(s) from {source}")
    if os.environ.get("LIST_ONLY") == "1":
        for u in urls:
            print(slug_for(u), u)
        return 0
    if not urls:
        log("No pages found. Add links to tutorial-urls.txt (one per line) or paste them into the workflow.")
        return 1

    done = existing_videos()
    pending = [u for u in urls if slug_for(u) not in done]
    log(f"{len(done)} already have a video; {len(pending)} still need one (up to {MAX_PER_RUN} this run)")
    start, made, failed, skipped = time.time(), 0, [], []
    OUT.mkdir(exist_ok=True)
    for url in pending:
        if made >= MAX_PER_RUN:
            break
        if (time.time() - start) / 60 > MAX_MINUTES * 0.8:
            log("Time budget nearly used; the rest will be made next run.")
            break
        slug = slug_for(url)
        log(f"\n=== {url}  ->  {slug}.mp4")
        env = {**os.environ, "OUT_DIR": str(OUT), "OUT_NAME": slug, "MIN_CODE_BLOCKS": "1"}
        r = subprocess.run([sys.executable, str(VIDEO_SCRIPT), url], env=env)
        if r.returncode == 3:
            skipped.append(url)
            continue
        mp4, desc = OUT / f"{slug}.mp4", OUT / f"{slug}.description.txt"
        if r.returncode != 0 or not mp4.exists():
            failed.append(url)
            continue
        up = gh("release", "upload", TAG, str(mp4), str(desc), "--clobber")
        if up.returncode != 0:
            log("  upload failed: " + (up.stderr or "")[-300:])
            failed.append(url)
            continue
        made += 1
        log(f"  uploaded {slug}.mp4 to release '{TAG}'")
        mp4.unlink(missing_ok=True)
        desc.unlink(missing_ok=True)
    log(f"\nSummary: {made} made, {len(skipped)} skipped (not tutorials), {len(failed)} failed")
    for u in skipped:
        log("  skipped:", u)
    for u in failed:
        log("  FAILED:", u)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
