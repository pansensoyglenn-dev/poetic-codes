

import asyncio
import glob
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

W, H, FPS = 1280, 720, 25
BGW, BGH = 2560, 1440
CROPW, CROPH = 2000, 1125
MIN_SECONDS = int(os.environ.get("MIN_SECONDS", "600"))
WPM = 155.0

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "video-jobs"))
DONE_DIR = JOBS_DIR / "done"
SITE_URL = os.environ.get("SITE_URL", "https://poetic-codes.pages.dev")
ARTICLES_API = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
UPLOAD_API = os.environ.get("UPLOAD_API", "https://poetic-codes.pages.dev/api/upload")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
VOICE = os.environ.get("TTS_VOICE", "en-US-ChristopherNeural")
RATE = os.environ.get("TTS_RATE", "-5%")
MAX_WORDS = int(os.environ.get("MAX_WORDS", "6000"))
MAX_JOBS_PER_RUN = int(os.environ.get("MAX_JOBS_PER_RUN", "5"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"
TTS_FAKE = os.environ.get("TTS_FAKE") == "1"

BG1, BG2 = (11, 15, 23), (22, 40, 66)
ACCENT, TEXT, MUTED = (116, 185, 232), (238, 244, 255), (170, 196, 230)

FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/dejavu",
    "/usr/share/fonts/TTF",
    "/Library/Fonts",
    "C:\\Windows\\Fonts",
]


def log(*a):
    print(*a, flush=True)


def run(cmd, input_bytes=None):
    p = subprocess.run(cmd, input=input_bytes, capture_output=True)
    if p.returncode != 0:
        tail = (p.stderr or b"").decode("utf-8", "replace")[-1200:]
        raise RuntimeError(f"{cmd[0]} failed: {tail}")
    return p


def load_font(size, bold=False, serif=True):
    base = "DejaVuSerif" if serif else "DejaVuSans"
    name = base + ("-Bold" if bold else "") + ".ttf"
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def clean_text(raw):
    s = raw or ""
    s = re.sub(r"(?is)<(script|style|audio|video|iframe|noscript)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)</(p|div|h[1-6]|li|blockquote)>|<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"https?://\S+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def split_sentences(text):
    parts = re.split(r"(?<=[.!?\u2026])\s+(?=[A-Z0-9\"\u201c\u2018(])", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def slugify(s):
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())) or "article"


def build_chunks(sentences, max_words):
    chunks, cur, cw, total = [], [], 0, 0
    for s in sentences:
        words = s.split()
        w = len(words)
        if w < 4:
            continue
        if w > 70:
            s = " ".join(words[:65]).rstrip(",;:") + "\u2026"
            w = 66
        if total + w > max_words:
            break
        if cur and cw + w > 75:
            chunks.append(" ".join(cur))
            cur, cw = [], 0
        cur.append(s)
        cw += w
        total += w
        if cw >= 45:
            chunks.append(" ".join(cur))
            cur, cw = [], 0
    if cur:
        chunks.append(" ".join(cur))
    return chunks[:150]


def build_segments(job):
    title = clean_text(job.get("title")) or "Untitled"
    excerpt = clean_text(job.get("excerpt"))
    body = clean_text(job.get("body"))
    category = clean_text(job.get("category"))
    author = clean_text(job.get("author")) or "Glenn Junsay Pansensoy"
    sub = f"{category}  \u00b7  {author}" if category else author

    speech = title.rstrip(".!?") + "."
    if excerpt:
        speech += " " + excerpt
    segs = [{"kind": "title", "title": title, "sub": sub, "speech": speech}]

    sentences = split_sentences(body)
    if sentences and excerpt and sentences[0][:40].lower() == excerpt[:40].lower():
        sentences = sentences[1:]
    for chunk in build_chunks(sentences, MAX_WORDS):
        segs.append({"kind": "body", "text": chunk, "speech": chunk})

    segs.append({
        "kind": "end",
        "title": "Read the full essay",
        "sub": "The Commonplace",
        "url": SITE_URL.replace("https://", "").replace("http://", "").rstrip("/"),
        "speech": "Read the full essay on The Commonplace.",
    })
    return segs


def gradient_bg():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        c = tuple(int(BG1[i] + (BG2[i] - BG1[i]) * t) for i in range(3))
        d.line([(0, y), (W, y)], fill=c)
    return img


def cover_bg(cover, blur, alpha):
    img = ImageOps.fit(cover, (W, H), Image.LANCZOS)
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    return Image.blend(img, Image.new("RGB", (W, H), (8, 12, 20)), alpha)


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_text(draw, text, max_w, max_h, sizes, bold=False):
    last = None
    for size in sizes:
        font = load_font(size, bold)
        lines = wrap(draw, text, font, max_w)
        lh = int(size * 1.35)
        last = (font, lines, lh)
        if len(lines) * lh <= max_h:
            return font, lines, lh
    font, lines, lh = last
    keep = max(1, max_h // lh)
    if len(lines) > keep:
        lines = lines[:keep]
        lines[-1] = lines[-1].rstrip(" ,.;:") + "\u2026"
    return font, lines, lh


def draw_lines(d, lines, font, lh, x, y, fill):
    for ln in lines:
        d.text((x + 2, y + 2), ln, font=font, fill=(0, 0, 0))
        d.text((x, y), ln, font=font, fill=fill)
        y += lh
    return y


def render_layers(seg, idx, total, cover):
    if cover is not None:
        bg = ImageOps.fit(cover, (BGW, BGH), Image.LANCZOS)
    else:
        bg = gradient_bg().resize((BGW, BGH), Image.BICUBIC)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    pad = 90
    max_w = W - 2 * pad
    kind = seg["kind"]

    d.rectangle([0, 0, W, H], fill=(6, 10, 18, 70 if kind == "title" else 40))
    d.rectangle([0, 0, 10, H], fill=ACCENT + (255,))
    d.text((pad, 40), "THE COMMONPLACE", font=load_font(20, True, serif=False), fill=ACCENT + (255,))

    if kind == "title":
        font, lines, lh = fit_text(d, seg["title"], max_w, 330, range(66, 33, -4), bold=True)
        sub_font = load_font(28, False, serif=False)
        block = len(lines) * lh + 30 + 40
        y = (H - block) // 2 + 10
        d.rectangle([pad - 30, y - 24, W - pad + 30, y + block + 20], fill=(6, 10, 18, 150))
        y = draw_lines(d, lines, font, lh, pad, y, TEXT + (255,))
        d.rectangle([pad, y + 12, pad + 120, y + 15], fill=ACCENT + (255,))
        d.text((pad, y + 30), seg["sub"], font=sub_font, fill=MUTED + (255,))

    elif kind == "body":
        font, lines, lh = fit_text(d, seg["text"], max_w, H - 240, range(44, 25, -2))
        y = (H - len(lines) * lh) // 2
        d.rectangle([pad - 30, y - 26, W - pad + 30, y + len(lines) * lh + 20], fill=(6, 10, 18, 165))
        draw_lines(d, lines, font, lh, pad, y, TEXT + (255,))

    else:
        big = load_font(58, True)
        url_font = load_font(40, True, serif=False)
        sub_font = load_font(28, False, serif=False)
        y = (H - 190) // 2
        d.rectangle([pad - 30, y - 24, W - pad + 30, y + 215], fill=(6, 10, 18, 150))
        d.text((pad + 2, y + 2), seg["title"], font=big, fill=(0, 0, 0, 255))
        d.text((pad, y), seg["title"], font=big, fill=TEXT + (255,))
        d.rectangle([pad, y + 82, pad + 120, y + 85], fill=ACCENT + (255,))
        d.text((pad, y + 105), seg["url"], font=url_font, fill=ACCENT + (255,))
        d.text((pad, y + 160), seg["sub"], font=sub_font, fill=MUTED + (255,))

    d.rectangle([0, H - 8, int(W * (idx + 1) / total), H], fill=ACCENT + (255,))
    return bg, ov


async def _edge_synth(text, out):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(out)


def pick_rate(segs):
    words = sum(len(g["speech"].split()) for g in segs)
    if TTS_FAKE or words == 0:
        return RATE
    base = float(RATE.strip("%")) if RATE.endswith("%") else -5.0
    est = words / (WPM * (1 + base / 100.0)) + len(segs) * 0.7
    if est >= MIN_SECONDS:
        return RATE
    need = (words / max(MIN_SECONDS - len(segs) * 0.7, 60)) / WPM
    pct = max(-20, min(base, round((need - 1) * 100)))
    return f"{int(pct)}%"


def synth(text, out_mp3):
    """Narrate text to out_mp3. Returns the engine name used."""
    if TTS_FAKE:
        dur = max(1.5, len(text.split()) / 2.6)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", f"{dur:.2f}", "-c:a", "libmp3lame", out_mp3])
        return "fake"

    last = None
    for attempt in range(3):
        try:
            asyncio.run(_edge_synth(text, out_mp3))
            if os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 1000:
                return "edge-tts"
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    log(f"  edge-tts failed ({last}); falling back to espeak-ng")
    wav = out_mp3 + ".wav"
    run(["espeak-ng", "-v", "en-us+m3", "-s", "150", "-w", wav, "--stdin"],
        input_bytes=text.encode("utf-8"))
    run(["ffmpeg", "-y", "-i", wav, "-c:a", "libmp3lame", "-q:a", "4", out_mp3])
    return "espeak-ng"


def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(p.stdout.decode().strip())


MOTIONS = [(0.0, 1.0, 0.0, 1.0), (1.0, 0.0, 1.0, 0.0), (1.0, 0.0, 0.0, 1.0), (0.0, 1.0, 1.0, 0.0)]


def make_clip(bg_png, ov_png, mp3, out, motion=0, pad=0.7):
    dur = probe_duration(mp3) + pad
    rx, ry = BGW - CROPW, BGH - CROPH
    x0, x1, y0, y1 = MOTIONS[motion % len(MOTIONS)]
    xe = f"{x0 * rx:.1f}+({(x1 - x0) * rx:.1f})*t/{dur:.2f}"
    ye = f"{y0 * ry:.1f}+({(y1 - y0) * ry:.1f})*t/{dur:.2f}"
    fc = (f"[0:v]crop={CROPW}:{CROPH}:x='{xe}':y='{ye}',scale={W}:{H}:flags=bicubic,setsar=1[bg];"
          f"[bg][1:v]overlay=format=auto,fade=t=in:st=0:d=0.35,"
          f"fade=t=out:st={max(dur - 0.35, 0):.2f}:d=0.35,format=yuv420p[v]")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(bg_png),
         "-loop", "1", "-framerate", str(FPS), "-i", str(ov_png), "-i", str(mp3),
         "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", f"{dur:.2f}",
         "-af", f"apad=pad_dur={pad}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "29",
         "-maxrate", "900k", "-bufsize", "1800k", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "64k", "-ar", "44100", "-ac", "1", str(out)])
    return dur


def load_cover(url):
    if not url or not str(url).startswith("http"):
        return None
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        log(f"  cover image not usable ({e}); using gradient background")
        return None


def build_video(job):
    global RATE
    segs = build_segments(job)
    RATE = pick_rate(segs)
    log(f"  {len(segs)} slides, narration rate {RATE}")
    tmp = Path(tempfile.mkdtemp(prefix="vid_"))
    cover = load_cover(job.get("coverUrl"))
    clips, engines, total_dur = [], set(), 0.0
    for i, seg in enumerate(segs):
        bgp, ovp = tmp / f"b{i}.png", tmp / f"o{i}.png"
        mp3, clip = tmp / f"a{i}.mp3", tmp / f"c{i}.mp4"
        bg_img, ov_img = render_layers(seg, i, len(segs), cover)
        bg_img.save(bgp)
        ov_img.save(ovp)
        engines.add(synth(seg["speech"], str(mp3)))
        total_dur += make_clip(bgp, ovp, mp3, clip, i)
        clips.append(clip)
        bgp.unlink()
        if (i + 1) % 10 == 0 or i + 1 == len(segs):
            log(f"  slide {i + 1}/{len(segs)} ready")

    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    final = tmp / "final.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-movflags", "+faststart", str(final)])
    return final, total_dur, ",".join(sorted(engines))


def _upload_endpoints():
    out = [UPLOAD_API]
    for extra in (
        "https://poetic-codes.pages.dev/api/upload",
        "https://rhythmic.pansensoyglenn150.workers.dev/api/upload",
        "https://poetic-codes.vercel.app/api/upload",
    ):
        if extra not in out:
            out.append(extra)
    return out


def upload_to_endpoints(path, filename):
    errors = []
    for endpoint in _upload_endpoints():
        try:
            with open(path, "rb") as fh:
                r = requests.post(
                    endpoint,
                    params={"filename": filename, "contentType": "video/mp4"},
                    headers={
                        "X-Admin-Key": ADMIN_KEY,
                        "Content-Type": "video/mp4",
                        "Origin": SITE_URL,
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) article-video-bot",
                    },
                    data=fh, timeout=900, allow_redirects=False,
                )
        except Exception as e:
            errors.append(f"{endpoint}: {e}")
            print(f"  upload via {endpoint} -> network error: {e}")
            continue
        print(f"  upload via {endpoint} -> HTTP {r.status_code} {r.headers.get('location', '')}")
        if r.status_code == 401:
            raise RuntimeError("Upload rejected (401): the ADMIN_KEY secret is wrong or missing.")
        if not r.ok:
            body = (r.text or "")[:200].replace("\n", " ")
            errors.append(f"{endpoint}: HTTP {r.status_code} {body}")
            print(f"    response: {body}")
            continue
        try:
            d = r.json()
        except Exception:
            errors.append(f"{endpoint}: not JSON")
            continue
        url = d.get("url") or d.get("publicUrl") or d.get("location")
        if url:
            return url
        errors.append(f"{endpoint}: no URL in response")
    raise RuntimeError("All upload endpoints failed: " + " | ".join(errors))


def _git(*args, check=True):
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def publish_to_repo(path, filename):
    """Fallback: commit the MP4 into the repo under videos/ so the site serves it."""
    size_mb = os.path.getsize(path) / 1048576
    if size_mb > 90:
        raise RuntimeError(f"Video is {size_mb:.0f} MB, too big to store in the repo.")
    Path("videos").mkdir(exist_ok=True)
    dest = Path("videos") / filename
    dest.write_bytes(Path(path).read_bytes())
    _git("config", "user.name", "article-video-bot")
    _git("config", "user.email", "article-video-bot@users.noreply.github.com")
    _git("add", str(dest))
    _git("commit", "-m", f"Add article video {filename}")
    last = None
    for _ in range(3):
        _git("pull", "--rebase", "origin", "main", check=False)
        r = _git("push", "origin", "HEAD:main", check=False)
        if r.returncode == 0:
            return SITE_URL.rstrip("/") + "/videos/" + filename
        last = r.stderr.strip()[-200:]
        time.sleep(3)
    raise RuntimeError("Could not push the video to the repo: " + str(last))


def upload_video(path, filename):
    try:
        return upload_to_endpoints(path, filename)
    except RuntimeError as e:
        if "401" in str(e)[:60]:
            raise
        print(f"  upload endpoints failed, saving the video in the repo instead ({str(e)[:120]})")
        return publish_to_repo(path, filename)


def fetch_articles():
    r = requests.get(ARTICLES_API, headers={"Accept": "application/json"}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict):
        data = data.get("articles") or data.get("results") or data.get("data") or []
    return data


def _num(v):
    try:
        return int(v)
    except Exception:
        return 0


def find_article(job, rows):
    aid = job.get("articleId")
    if aid not in (None, ""):
        for r in rows:
            if str(r.get("id")) == str(aid):
                return r
    t = (job.get("title") or "").strip().lower()
    cands = [r for r in rows if (r.get("title") or "").strip().lower() == t]
    cands.sort(key=lambda r: _num(r.get("id")), reverse=True)
    return cands[0] if cands else None


def existing_video(row):
    return row.get("video_url") or row.get("videoUrl") or ""


def attach_video(row, video_url):
    tags = row.get("tags") or []
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = [t.strip() for t in tags.split(",") if t.strip()]
    body = row.get("content")
    if body is None:
        body = row.get("body", "")
    payload = {
        "title": row.get("title"),
        "category": row.get("category"),
        "date": str(row.get("date") or "")[:10],
        "contentType": row.get("content_type") or row.get("contentType") or "html",
        "body": body,
        "summary": row.get("excerpt") or row.get("summary") or "",
        "tags": tags if isinstance(tags, list) else [],
        "photoUrl": row.get("photo_url") or row.get("photoUrl") or None,
        "videoUrl": video_url,
    }
    r = requests.put(
        ARTICLES_API, params={"id": row["id"]},
        headers={"X-Admin-Key": ADMIN_KEY, "Content-Type": "application/json"},
        json=payload, timeout=60,
    )
    if r.status_code == 401:
        raise RuntimeError("Update rejected (401): the ADMIN_KEY secret is wrong or missing.")
    r.raise_for_status()


def read_marker(name):
    p = DONE_DIR / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def write_marker(name, data):
    DONE_DIR.mkdir(parents=True, exist_ok=True)
    (DONE_DIR / name).write_text(json.dumps(data, indent=2), encoding="utf-8")


def needs_work(job, marker):
    if not marker:
        return True
    if marker.get("jobId") != job.get("jobId"):
        return True
    return marker.get("status") == "failed" and marker.get("attempts", 1) < 3


def process_job(path):
    name = path.name
    job = json.loads(path.read_text(encoding="utf-8"))
    marker = read_marker(name)
    if not DRY_RUN and not needs_work(job, marker):
        return None

    title = job.get("title", name)
    log(f"\n=== {title} ({name})")
    attempts = (marker.get("attempts", 0) if marker and marker.get("jobId") == job.get("jobId") else 0) + 1

    try:
        row = None
        if not DRY_RUN:
            row = find_article(job, fetch_articles())
            if row is None:
                log("  article not found on The Commonplace; the video will be made but not attached")
            elif existing_video(row) and not job.get("force"):
                log("  article already has a video; leaving it alone")
                write_marker(name, {"jobId": job.get("jobId"), "status": "skipped",
                                    "reason": "article already has a video", "title": title})
                return "skipped"

        final, dur, engine = build_video(job)
        log(f"  video built: {dur:.0f}s, voice engine: {engine}")

        if DRY_RUN:
            out = Path("out")
            out.mkdir(exist_ok=True)
            dest = out / f"{slugify(title)}.mp4"
            dest.write_bytes(Path(final).read_bytes())
            log(f"  DRY RUN: saved {dest}")
            return "dry"

        fname = f"{slugify(title)[:60]}-video-{str(job.get('jobId', ''))[-6:]}.mp4"
        url = upload_video(final, fname)
        log(f"  uploaded: {url}")
        attached = False
        if row is not None:
            attach_video(row, url)
            attached = True
            log(f"  attached to article #{row['id']}")
        write_marker(name, {"jobId": job.get("jobId"), "status": "done", "title": title,
                            "videoUrl": url, "attached": attached, "engine": engine,
                            "seconds": round(dur)})
        return "done"

    except Exception as e:
        log(f"  FAILED: {e}")
        if not DRY_RUN:
            write_marker(name, {"jobId": job.get("jobId"), "status": "failed",
                                "attempts": attempts, "error": str(e)[:400], "title": title})
        return "failed"


def main():
    if not DRY_RUN and not ADMIN_KEY:
        log("ADMIN_KEY is not set. Add it under Settings > Secrets and variables > Actions.")
        return 1
    files = sorted(Path(p) for p in glob.glob(str(JOBS_DIR / "*.json")))
    if not files:
        log("No video jobs found.")
        return 0
    results, done_count = [], 0
    for f in files:
        if done_count >= MAX_JOBS_PER_RUN:
            log("Job limit for this run reached; the rest will be picked up next time.")
            break
        res = process_job(f)
        if res:
            results.append(res)
            done_count += 1
    log("\nSummary:", {r: results.count(r) for r in set(results)} or "nothing to do")
    return 1 if "failed" in results else 0


if __name__ == "__main__":
    sys.exit(main())
