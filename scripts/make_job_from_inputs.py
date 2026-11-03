"""Turn the workflow-dispatch inputs into a single video-jobs/*.json file.

The job holds only the title plus optional location/characters. The article text, excerpt and
category are read from the article on the site (matched by title) when the video is made."""
import json
import os
import re
from pathlib import Path

title = os.environ.get("TITLE", "").strip()
location = os.environ.get("LOCATION", "").strip()
details = os.environ.get("LOCATION_DETAILS", "").strip()
chars = os.environ.get("CHARACTERS", "").strip()

if not title:
    raise SystemExit("title is required")

# Characters: one per line, "name | description | word,word,word". A one-line field on a phone can also use ";;"
# between characters, because GitHub's run form has no multi-line box.
character_list = []
for line in re.split(r"\n|;;", chars):
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        continue
    character_list.append({
        "id": re.sub(r"[^a-z0-9]+", "-", parts[0].lower()).strip("-"),
        "name": parts[0],
        "description": parts[1],
        "appearsIn": [w.strip() for w in (parts[2].split(",") if len(parts) > 2 else []) if w.strip()],
        "referenceImages": [],
    })

job = {
    "jobId": os.environ.get("GITHUB_RUN_ID", "local"),
    "title": title,
    "force": True,  # you asked for this video on purpose, so rebuild even if the article already has one
}
if location or details:
    job["location"] = {"name": location, "description": details}
if character_list:
    job["characters"] = character_list

Path("video-jobs").mkdir(exist_ok=True)
out = Path("video-jobs") / f"{re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')}.json"
out.write_text(json.dumps(job, indent=2), encoding="utf-8")
print(f"wrote {out}")
