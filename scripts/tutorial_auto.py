SCRIPT_VERSION = "2026-11-28-tutorial-auto-v2"
import html as htmllib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

WORKER = os.environ.get("WORKER", "https://poetic-codes.pansensoyglenn150.workers.dev").rstrip("/")
KEY = os.environ.get("ADMIN_KEY", "").strip()
WANT_TITLE = os.environ.get("TITLE", "").strip()
PAGE = os.environ.get("PAGE", "").strip()
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", "1"))
FORCE = os.environ.get("FORCE", "0") == "1"
MIN_CODE = int(os.environ.get("MIN_CODE_BLOCKS", "1"))
WEB_LIMIT = int(os.environ.get("WEB_LIMIT", "45000000"))
OUT = Path(os.environ.get("OUT", "out"))
VIDEO_SCRIPT = os.environ.get("TUTORIAL_SCRIPT", str(Path(__file__).with_name("tutorial_video.py")))


def log(*a):
    print(*a, flush=True)


def norm(x):
    return re.sub(r"[^a-z0-9]+", " ", (x or "").lower()).strip()


def call(method, path, data=None, headers=None, quiet=False):
    h = {"X-Admin-Key": KEY, "User-Agent": "tutorial-video-bot/2.0"}
    h.update(headers or {})
    req = urllib.request.Request(WORKER + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        if not quiet:
            log(f"  Worker said HTTP {e.code} for {method} {path.split('?')[0]}: {body}")
            if e.code == 401:
                log("  401 means the ADMIN_KEY secret in GitHub is not the same as the Worker's ADMIN_KEY.")
            if e.code == 404:
                log("  404 means the Worker has no such route yet: deploy the newest worker.js.")
        return None


def get_articles():
    rows = call("GET", "/api/articles")
    if rows is None:
        return []
    rows = rows.get("articles", rows) if isinstance(rows, dict) else rows
    return [r for r in rows if isinstance(r, dict)]


def has_video(r):
    return any(r.get(k) for k in ("video_url", "videoUrl", "video"))


def code_blocks(body):
    return len(re.findall(r"<pre", body or "", re.I))


def pick(rows):
    if WANT_TITLE:
        want = norm(WANT_TITLE)
        exact = [r for r in rows if norm(r.get("title")) == want]
        close = [r for r in rows if want and want in norm(r.get("title"))]
        return (exact or close)[:1]
    todo = [r for r in rows if code_blocks(r.get("body")) >= MIN_CODE and (FORCE or not has_video(r))]
    todo.sort(key=lambda r: int(r.get("id") or 0), reverse=True)
    return todo[:MAX_ARTICLES]


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "tutorial"


def wrap_html(title, summary, body):
    return ("<!DOCTYPE html><html><head><meta charset=\"utf-8\"><title>" + htmllib.escape(title) + "</title>"
            "<meta name=\"description\" content=\"" + htmllib.escape(summary or "", quote=True) + "\"></head><body><main>"
            + body + "</main></body></html>")


def run_video(job):
    d = OUT / job["slug"]
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    page = d / "page.html"
    page.write_text(job["html"], encoding="utf-8")
    env = dict(os.environ, TITLE=job["title"], DESC=job.get("summary") or "", OUT_DIR=str(d / "render"),
               OUT_NAME="tutorial", SPLIT="0", MAX_WORDS=os.environ.get("MAX_WORDS", "9000"), AUTO_PREVIOUS="0",
               LINK=job.get("link") or "")
    p = subprocess.run([sys.executable, VIDEO_SCRIPT, str(page)], env=env)
    mp4 = d / "render" / "tutorial.mp4"
    if p.returncode != 0 or not mp4.exists():
        return None
    return d / "render"


def web_copy(src, dst):
    plans = [(1280, (700, 520, 400, 300)), (960, (300, 220, 160, 110, 80))]
    for width, rates in plans:
        for mr in rates:
            cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-vf", f"scale={width}:-2", "-c:v", "libx264",
                   "-preset", "medium", "-crf", "29", "-maxrate", f"{mr}k", "-bufsize", f"{mr * 2}k", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "48k", "-ac", "1", "-movflags", "+faststart", str(dst)]
            if subprocess.run(cmd).returncode != 0:
                continue
            size = Path(dst).stat().st_size
            log(f"  web copy {width}px maxrate {mr}k -> {size / 1048576:.1f} MiB")
            if size <= WEB_LIMIT:
                return True
    return False


def attach(row, mp4, vname):
    raw = Path(mp4).read_bytes()
    q = urllib.parse.urlencode({"contentType": "video/mp4", "filename": vname})
    up = call("POST", "/api/upload?" + q, raw, {"Content-Type": "video/mp4", "Content-Length": str(len(raw))})
    if not up or not up.get("url"):
        log("  upload failed; the video is not attached")
        return False
    url = up["url"]
    log("  video is live at", url)
    if not row:
        return True
    payload = {"title": row["title"], "category": row.get("category"), "date": str(row.get("date") or "")[:10],
               "contentType": row.get("content_type") or "html", "body": row["body"], "summary": row.get("summary") or "",
               "tags": row.get("tags") or [], "photoUrl": row.get("photo_url"), "videoUrl": url}
    res = call("PUT", "/api/articles?id=" + str(row["id"]), json.dumps(payload).encode(), {"Content-Type": "application/json"})
    if res is None:
        return False
    log(f"  attached to article #{row['id']}")
    return True


def build_jobs():
    if PAGE:
        req = urllib.request.Request(PAGE, headers={"User-Agent": "tutorial-video-bot/2.0"})
        html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
        title = WANT_TITLE or (htmllib.unescape(re.sub(r"\s+", " ", m.group(1))).split("|")[0].strip() if m else "Tutorial")
        rows = get_articles() if KEY else []
        row = next((r for r in rows if norm(r.get("title")) == norm(title)), None)
        return [{"slug": slugify(title), "title": title, "summary": "", "html": html, "row": row, "link": PAGE}]
    rows = get_articles()
    jobs = []
    for r in pick(rows):
        jobs.append({"slug": slugify(r.get("title")) + "-" + str(r.get("id")), "title": r.get("title") or "Tutorial",
                     "summary": r.get("summary") or "", "html": wrap_html(r.get("title") or "Tutorial", r.get("summary"), r.get("body") or ""),
                     "row": r, "link": r.get("url") or r.get("link") or ""})
    return jobs


def main():
    log(f"tutorial_auto.py {SCRIPT_VERSION}")
    if not KEY and not PAGE:
        log("The ADMIN_KEY secret is not set, so the articles cannot be read.")
        return 1
    jobs = build_jobs()
    check = "--check" in sys.argv
    out_file = os.environ.get("GITHUB_OUTPUT")
    if check:
        log(f"  {len(jobs)} article(s) need a video: " + ", ".join(j["title"] for j in jobs))
        if out_file:
            with open(out_file, "a", encoding="utf-8") as fh:
                fh.write(f"work={'1' if jobs else '0'}\n")
        return 0
    if not jobs:
        log("  nothing to do: every tutorial article already has a video")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    done, failed = [], 0
    for job in jobs:
        log(f"=== {job['title']}")
        render = run_video(job)
        if render is None:
            log("  the video could not be made for this article")
            failed += 1
            continue
        web = render / "tutorial-web.mp4"
        if not web_copy(render / "tutorial.mp4", web):
            log("  could not make a web copy small enough; the full video is still in the download")
        else:
            attach(job["row"], web, job["slug"] + ".mp4")
        name = job["slug"]
        shutil.copy(render / "tutorial.mp4", OUT / f"{name}-for-youtube.mp4")
        for src, dst in (("tutorial.srt", f"{name}.srt"), ("tutorial.chapters.txt", f"{name}.chapters.txt"),
                         ("tutorial.description.txt", f"{name}.youtube_description.txt"), ("tutorial.script.txt", f"{name}.script.txt")):
            if (render / src).exists():
                shutil.copy(render / src, OUT / dst)
        done.append(name)
    (OUT / "jobs.txt").write_text("\n".join(done), encoding="utf-8")
    return 1 if failed and not done else 0


if __name__ == "__main__":
    sys.exit(main())
