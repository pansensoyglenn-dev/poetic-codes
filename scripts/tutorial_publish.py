#!/usr/bin/env python3
"""Publish a finished tutorial video so readers see it on the website.

    python scripts/tutorial_publish.py <page url> <name>      (name = the OUT_NAME the videos were made with)

  1. joins the topic videos out/<name>*.mp4 into one lesson video (a page that was not split stays as it is)
  2. uploads it to the same public video storage your essay videos use
  3. finds the matching article on Poetic Codes (by the page's <title>) and sets its video, using the same call as the essay videos

The Poetic Bytes lesson page then shows it with the small player snippet (lesson-video-snippet.html).
Needs the ADMIN_KEY secret. Without it, or when no matching article exists, it says so and exits 0 (the videos are still on the release).
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ARTICLES_API = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
VIDEO_URL_API = os.environ.get("VIDEO_URL_API", "https://poetic-codes.vercel.app/api/video-upload-url")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "").strip()
OUT = Path(os.environ.get("OUT_DIR", "out"))
UA = "tutorial-video-bot/1.0"


def log(*a):
    print(*a, flush=True)


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def join_videos(files, dest):
    if len(files) == 1:
        return files[0]
    dest.parent.mkdir(parents=True, exist_ok=True)
    listing = dest.with_suffix(".txt")
    listing.write_text("".join(f"file '{f.resolve()}'\n" for f in files), encoding="utf-8")
    p = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                        "-movflags", "+faststart", str(dest)], capture_output=True)
    listing.unlink(missing_ok=True)
    if p.returncode != 0:
        raise RuntimeError("could not join the videos: " + (p.stderr or b"").decode("utf-8", "replace")[-400:])
    return dest


def upload(path, filename):
    r = requests.post(VIDEO_URL_API, params={"filename": filename}, headers={"X-Admin-Key": ADMIN_KEY}, timeout=60)
    if r.status_code == 401:
        raise RuntimeError("upload rejected (401): the ADMIN_KEY secret is wrong or missing")
    if not r.ok:
        raise RuntimeError(f"video-upload-url: HTTP {r.status_code} {(r.text or '')[:300]}")
    info = r.json()
    with open(path, "rb") as fh:
        put = requests.put(info["uploadUrl"], data=fh, timeout=1800,
                           headers={"Content-Type": "video/mp4", "x-upsert": "false"})
    if not put.ok:
        raise RuntimeError(f"video storage: HTTP {put.status_code} {(put.text or '')[:200]}")
    return info["url"]


def page_title(url):
    html = requests.get(url, headers={"User-Agent": UA}, timeout=60).text
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def find_article(rows, title, url):
    want = norm(title)
    for r in rows:
        if norm(r.get("title")) == want:
            return r
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    if slug:
        for r in rows:
            if slug in str(r.get("content") or r.get("body") or "")[:200000] and "poetic bytes" in norm(r.get("title")):
                return r
    return None


def attach(row, video_url):
    tags = row.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [t.strip() for t in tags.split(",") if t.strip()]
    body = row.get("content")
    if body is None:
        body = row.get("body", "")
    payload = {"title": row.get("title"), "category": row.get("category"), "date": str(row.get("date") or "")[:10],
               "contentType": row.get("content_type") or row.get("contentType") or "html", "body": body,
               "summary": row.get("excerpt") or row.get("summary") or "", "tags": tags if isinstance(tags, list) else [],
               "photoUrl": row.get("photo_url") or row.get("photoUrl") or None, "videoUrl": video_url}
    r = requests.put(ARTICLES_API, params={"id": row["id"]},
                     headers={"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"}, json=payload, timeout=60)
    if r.status_code == 401:
        raise RuntimeError("update rejected (401): the ADMIN_KEY secret is wrong or missing")
    r.raise_for_status()


def main():
    url = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PAGE", "")).strip()
    name = (sys.argv[2] if len(sys.argv) > 2 else os.environ.get("OUT_NAME", "")).strip()
    if not url:
        log("usage: tutorial_publish.py <page url> [name]")
        return 1
    if not ADMIN_KEY:
        log("publish skipped: ADMIN_KEY is not set, so the video is not attached to the website (it is still on the release).")
        return 0
    files = sorted(f for f in OUT.glob(f"{name}*.mp4")) if name else sorted(OUT.glob("*.mp4"))
    files = [f for f in files if f.parent == OUT]
    if not files:
        log("publish skipped: no .mp4 found in", OUT)
        return 0
    title = page_title(url)
    r = requests.get(ARTICLES_API, headers={"Accept": "application/json", "User-Agent": UA}, timeout=60)
    r.raise_for_status()
    data = r.json()
    rows = data.get("articles") or data.get("results") or data.get("data") or [] if isinstance(data, dict) else data
    row = find_article(rows, os.environ.get("ARTICLE_TITLE") or title, url)
    if row is None:
        log(f"publish skipped: no article titled '{title}' on Poetic Codes, so there is nothing to attach the video to.")
        return 0
    log(f"article: '{row.get('title')}' (id {row.get('id')}); joining {len(files)} video(s)")
    joined = join_videos(files, OUT / "publish" / f"{name or 'lesson'}-lesson.mp4")
    log(f"  lesson video {joined.stat().st_size / 1048576:.1f} MB")
    video_url = upload(joined, f"{name or 'lesson'}-lesson-{int(time.time())}.mp4")
    attach(row, video_url)
    log(f"  attached to the article: {video_url}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("publish FAILED:", str(e)[:400])
        sys.exit(0)      # never fail the whole run: the videos are already on the release
