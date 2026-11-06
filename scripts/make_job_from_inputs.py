"""Create video job files in video-jobs/ from workflow inputs.

TITLE            "*" = every article on the site that has no video yet (newest first).
                 Otherwise one or more exact titles separated by ;;
LOCATION         optional, e.g. "Iloilo City, early 1990s"
LOCATION_DETAILS optional visual details, e.g. "nipa huts, wet market"
CHARACTERS       optional, "name | description | words it appears with ;; next character"
MAX_VIDEOS       when TITLE is "*", how many articles to queue (default 10)
QUIET_WHEN_EMPTY "1" = print one short line when there is nothing to do

Writes video-jobs/<slug>-<id>.json and sets the step output  found=<number of jobs queued>.
The job only needs a title and articleId: article_video.py fetches the text and works out place, era,
scenes and characters from the article itself.
"""
import json
import os
import re
import sys
from pathlib import Path

import requests

ARTICLES_API = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
JOBS_DIR = Path(os.environ.get("JOBS_DIR", "video-jobs"))
DONE_DIR = JOBS_DIR / "done"
UA = "article-video-bot/1.0"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "article"


def set_output(name, value):
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{name}={value}\n")


def fetch_articles():
    r = requests.get(ARTICLES_API, headers={"Accept": "application/json", "User-Agent": UA}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("articles") or data.get("results") or data.get("data") or []
    return data


def has_video(row):
    return bool(row.get("video_url") or row.get("videoUrl"))


def is_tutorial(row):
    """Poetic Bytes lesson pages live in the same article list; they are made by the Tutorial video workflow."""
    title = str(row.get("title") or "")
    body = str(row.get("body") or row.get("content") or "")
    return (bool(re.search(r"\|\s*Poetic Bytes\s*$", title.strip()))
            or len(re.findall(r"<pre\b", body)) >= 3
            or len(re.findall(r"\bCopy\s+Run\b", body)) >= 3)


def num(v):
    try:
        return int(v)
    except Exception:
        return 0


def finished(fname):
    """True when a marker says this job is done/skipped, or failed three times already."""
    p = DONE_DIR / fname
    if not p.exists():
        return False
    try:
        m = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    if m.get("status") in ("done", "skipped"):
        return True
    return m.get("status") == "failed" and m.get("attempts", 1) >= 3


def parse_characters(raw):
    out = []
    for part in (raw or "").split(";;"):
        bits = [b.strip() for b in part.split("|")]
        if bits and bits[0]:
            out.append({"name": bits[0], "description": bits[1] if len(bits) > 1 else "",
                        "appearsIn": [w.strip() for w in re.split(r"[,/]", bits[2]) if w.strip()] if len(bits) > 2 else []})
    return out


def write_job(row, title, extra):
    aid = row.get("id") if row else None
    fname = f"{slug(title)}-{aid}.json" if aid is not None else f"{slug(title)}.json"
    if finished(fname):
        return None
    job = {"title": title, "jobId": str(aid) if aid is not None else slug(title)}
    if aid is not None:
        job["articleId"] = aid
    job.update(extra)
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    (JOBS_DIR / fname).write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
    return fname


def main():
    title_in = (os.environ.get("TITLE") or "").strip()
    quiet = os.environ.get("QUIET_WHEN_EMPTY") == "1"
    try:
        limit = max(1, int(os.environ.get("MAX_VIDEOS") or 10))
    except ValueError:
        limit = 10

    extra = {}
    loc, det = (os.environ.get("LOCATION") or "").strip(), (os.environ.get("LOCATION_DETAILS") or "").strip()
    if loc or det:
        extra["location"] = {k: v for k, v in (("name", loc), ("description", det)) if v}
    chars = parse_characters(os.environ.get("CHARACTERS"))
    if chars:
        extra["characters"] = chars

    if not title_in:
        print("TITLE is empty: type an article title, several separated by ;; or * for every article without a video.")
        set_output("found", 0)
        return 1

    rows = fetch_articles()
    made = []
    if title_in == "*":
        todo = [r for r in rows if r.get("title") and not has_video(r) and not is_tutorial(r)]
        todo.sort(key=lambda r: num(r.get("id")), reverse=True)
        # a per-article location only makes sense for a single article, so it is not applied to a "*" run
        bulk_extra = {}
        for r in todo:
            if len(made) >= limit:
                break
            f = write_job(r, r["title"].strip(), bulk_extra)
            if f:
                made.append(f)
    else:
        for t in [x.strip() for x in title_in.split(";;") if x.strip()]:
            matches = [r for r in rows if (r.get("title") or "").strip().lower() == t.lower()]
            matches.sort(key=lambda r: num(r.get("id")), reverse=True)
            row = matches[0] if matches else None
            if row is None:
                print(f"No article titled '{t}' found on the site; check the spelling.")
                continue
            # a title typed by hand is a request to make that video, even if an old marker says done
            fname = f"{slug(row['title'])}-{row.get('id')}.json"
            marker = DONE_DIR / fname
            if marker.exists():
                marker.unlink()
            f = write_job(row, row["title"].strip(), {**extra, "force": True})
            if f:
                made.append(f)

    if made:
        print(f"Queued {len(made)} video job(s): " + ", ".join(made))
    elif quiet:
        print("Every article already has a video; nothing to do.")
    else:
        print("Nothing queued (every matching article already has a video or a finished marker).")
    set_output("found", len(made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
