"""Turn the workflow-dispatch inputs into video-jobs/*.json files (one per article).

TITLE can be:
  * one article title                                  Pancit Molo
  * several, one per line or separated by ;;           Pancit Molo ;; La Paz Batchoy ;; Kadyos Baboy at Langka
      each may carry its own place:  Title | Location | Details
  * * (or "all")                                       every article on the site that has no video yet,
                                                       newest first, at most MAX_VIDEOS of them

The job holds only the title plus optional location/characters. The article text, excerpt and category are
read from the article on the site (matched by title) when the video is made.
LOCATION / LOCATION_DETAILS / CHARACTERS are used for every job that has no place of its own. A character only
appears in the pictures where the narration mentions its name or one of its words, so one cast is safe to share."""
import json
import os
import re
from pathlib import Path

import requests

ARTICLES_API = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
raw_title = os.environ.get("TITLE", "").strip()
location = os.environ.get("LOCATION", "").strip()
details = os.environ.get("LOCATION_DETAILS", "").strip()
chars = os.environ.get("CHARACTERS", "").strip()
try:
    max_videos = max(1, int(os.environ.get("MAX_VIDEOS", "10") or 10))
except ValueError:
    max_videos = 10

if not raw_title:
    raise SystemExit("title is required (an article title, several separated by ;;, or * for every article without a video)")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "job"


# Characters: "name | description | word,word,word", one per line or separated by ;;
character_list = []
for line in re.split(r"\n|;;", chars):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        continue
    character_list.append({
        "id": slug(parts[0]),
        "name": parts[0],
        "description": parts[1],
        "appearsIn": [w.strip() for w in (parts[2].split(",") if len(parts) > 2 else []) if w.strip()],
        "referenceImages": [],
    })

# Which articles?
entries = []  # (title, location, details, force)
if raw_title.lower() in ("*", "all"):
    r = requests.get(ARTICLES_API, headers={"Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("articles") or data.get("results") or data.get("data") or []
    todo = [a for a in data if a.get("title") and not (a.get("video_url") or a.get("videoUrl"))]
    todo.sort(key=lambda a: int(a.get("id") or 0), reverse=True)
    print(f"{len(todo)} article(s) have no video yet; making {min(len(todo), max_videos)}")
    entries = [(a["title"].strip(), "", "", False) for a in todo[:max_videos]]
else:
    for chunk in re.split(r"\n|;;", raw_title):
        chunk = chunk.strip()
        if not chunk:
            continue
        p = [x.strip() for x in chunk.split("|")]
        # you asked for these by name, so rebuild even if the article already has a video
        entries.append((p[0], p[1] if len(p) > 1 else "", p[2] if len(p) > 2 else "", True))

def _flag(found):
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"found={found}\n")


if not entries:
    msg = "nothing to do: every article already has a video" if raw_title.lower() in ("*", "all") else "no titles found"
    if os.environ.get("QUIET_WHEN_EMPTY") == "1":      # the scheduled run: nothing to do is a normal, green result
        print(msg)
        _flag(0)
        raise SystemExit(0)
    raise SystemExit(msg)
_flag(1)

Path("video-jobs").mkdir(exist_ok=True)
seen = set()
for n, (title, loc, det, force) in enumerate(entries):
    if slug(title) in seen:
        continue
    seen.add(slug(title))
    loc = loc or location
    det = det or details
    job = {"jobId": f"{os.environ.get('GITHUB_RUN_ID', 'local')}-{n + 1}", "title": title}
    if force:
        job["force"] = True
    if loc or det:
        job["location"] = {"name": loc, "description": det}
    if character_list:
        job["characters"] = character_list
    out = Path("video-jobs") / f"{slug(title)}.json"
    out.write_text(json.dumps(job, indent=2), encoding="utf-8")
    print(f"wrote {out}")
