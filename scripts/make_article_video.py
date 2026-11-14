import asyncio
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Shapes used throughout: a job file / article row, and one slide of the video.
Job = dict[str, Any]
Seg = dict[str, Any]

SCRIPT_VERSION = "2026-11-06-z3"
W, H, FPS = 1280, 720, 25
BGW, BGH = 2560, 1440
IMGH = 540
BANDH = H - IMGH
CROPW, CROPH = 2000, 844
ZOOM = float(os.environ.get("ZOOM", "0.18"))
GRAIN = int(os.environ.get("GRAIN", "2"))
VIGNETTE = os.environ.get("VIGNETTE", "1") != "0"
CAP_WORDS = int(os.environ.get("CAP_WORDS", "20"))
MAX_MB = float(os.environ.get("MAX_MB", "45"))
MIN_SECONDS = int(os.environ.get("MIN_SECONDS", "0"))
WPM = 155.0

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "video-jobs"))
DONE_DIR = JOBS_DIR / "done"
SITE_URL = os.environ.get("SITE_URL", "https://poetic-codes.pages.dev")
ARTICLES_API = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
VIDEO_URL_API = os.environ.get("VIDEO_URL_API", "https://poetic-codes.vercel.app/api/video-upload-url")
UPLOAD_API = os.environ.get("UPLOAD_API", "https://poetic-codes.pages.dev/api/upload")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")
AI_IMAGES = os.environ.get("AI_IMAGES", "1") != "0"
AI_IMAGE_MAX = int(os.environ.get("AI_IMAGE_MAX", "60"))  # each picture covers a stretch of narration; lower to save free quota
# Same names as your GitHub secrets. strip() removes a stray space or newline pasted along with a secret.
# strip() removes a stray space or newline pasted along with the secret.
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
VOICE = os.environ.get("TTS_VOICE", "en-PH-JamesNeural")   # Philippine English; en-PH-RosaNeural is the female voice
VOICE_FALLBACKS = ["en-PH-RosaNeural", "en-US-ChristopherNeural"]
RATE = os.environ.get("TTS_RATE", "+10%")
MAX_WORDS = int(os.environ.get("MAX_WORDS", "6000"))
SLIDE_WORDS = int(os.environ.get("SLIDE_WORDS", "45"))  # one picture per slide, so shorter slides keep each picture close to its words
INTRO_TITLE = os.environ.get("INTRO_TITLE", "0") != "0"  # off: video starts straight on the content
# The narration opens with this greeting, then the topic (the article title), then the essay itself.
# Set NARRATION_GREETING to an empty string in the workflow to switch it off.
NARRATION_GREETING = os.environ.get("NARRATION_GREETING", "Hello everyone, welcome back to Poetic Codes. This is an educational video that tackles topics on AI, economy, and history. This video is about").strip()


NARRATION_CLOSER = os.environ.get(
    "NARRATION_CLOSER",
    "Along the way, we will look at the background, the key ideas, and what they mean for us today. "
    "So please settle in, and let's begin.").strip()


def narration_greeting(title: str, excerpt: str = "") -> str:
    topic = (title or "").strip().rstrip(".!?:;, ")
    if not NARRATION_GREETING or not topic or topic.lower() == "untitled":
        return ""
    parts = [f"{NARRATION_GREETING} {topic}."]
    ex = (excerpt or "").strip()
    if ex:
        parts.append(ex if ex[-1] in ".!?" else ex + ".")
    if NARRATION_CLOSER:
        parts.append(NARRATION_CLOSER)
    return " ".join(parts)

SPEAK_HEADINGS = os.environ.get("SPEAK_HEADINGS", "0") != "0"  # off: section headings are not read or shown
ONLY_JOB = os.environ.get("ONLY_JOB", "").strip().lower()
MAX_JOBS_PER_RUN = int(os.environ.get("MAX_JOBS_PER_RUN", "5"))
RUN_START = time.time()
RUN_BUDGET = float(os.environ.get("MAX_RUN_MINUTES", "100")) * 60
IMG_BUDGET = float(os.environ.get("IMG_BUDGET_SECONDS", "1500"))
# When Cloudflare's free daily allowance is used up (or has no keys), pictures come from free backup generators instead of
# photos that do not match: Hugging Face (optional free HF_TOKEN) and Pollinations (no key). FALLBACK_IMAGES=0 turns this off.
FALLBACK_IMAGES = os.environ.get("FALLBACK_IMAGES", "1") != "0"
HF_TOKEN = os.environ.get("HF_TOKEN", "").strip()
HF_MODEL = os.environ.get("HF_MODEL", "black-forest-labs/FLUX.1-schnell")
POLLINATIONS_URL = os.environ.get(
    "POLLINATIONS_URL",
    "https://image.pollinations.ai/prompt/{prompt}?width=1280&height=720&model=flux&nologo=true&seed={seed}")
FALLBACK_PAUSE = float(os.environ.get("FALLBACK_PAUSE", "4"))   # seconds between backup requests (they are rate limited)
WIKI_IMAGES = os.environ.get("WIKI_IMAGES", "1") != "0"
WIKI_MAX = int(os.environ.get("WIKI_MAX", "12"))
UA = "article-video-bot/1.0 (https://poetic-codes.pages.dev; GitHub Actions)"
CREDITS = []
CREDIT_ROWS = []
QUOTA_HIT = [False]
IMG_FAIL_LIMIT = int(os.environ.get("IMG_FAIL_LIMIT", "4"))
DRY_RUN = os.environ.get("DRY_RUN") == "1"
FORCE_REDO = os.environ.get("FORCE_REDO") == "1"  # ignore finished-job markers and the "article already has a video" check
TTS_FAKE = os.environ.get("TTS_FAKE") == "1"

# Kling image-to-video (real character motion). Off by default — needs API key + budget.
KLING_ENABLED = os.environ.get("KLING_ENABLED", "0") == "1"
KLING_API_KEY = os.environ.get("KLING_API_KEY", "") or os.environ.get("FAL_KEY", "") or os.environ.get("PIAPI_API_KEY", "")
KLING_PROVIDER = os.environ.get("KLING_PROVIDER", "fal").strip().lower()  # fal | piapi | aimlapi
KLING_MAX_CLIPS = int(os.environ.get("KLING_MAX_CLIPS", "12"))
KLING_DURATION = int(os.environ.get("KLING_DURATION", "5"))  # 5-10 typical
KLING_MODEL = os.environ.get("KLING_MODEL", "")  # provider-specific override
KLING_BUDGET = float(os.environ.get("KLING_BUDGET_SECONDS", "600"))  # max wall time on Kling calls
KLING_NEG = os.environ.get(
    "KLING_NEG",
    "still photo, frozen pose, static image, text, watermark, logo, cartoon, illustration, low quality",
)

# Free moving people: real stock footage from Pexels (free key from pexels.com/api). Off unless STOCK_VIDEO=1.
STOCK_VIDEO = os.environ.get("STOCK_VIDEO", "0") == "1"
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "").strip()
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
STOCK_MAX_CLIPS = int(os.environ.get("STOCK_MAX_CLIPS", "8"))
STOCK_MAX_MB = float(os.environ.get("STOCK_MAX_MB", "25"))

# Real archival footage (public domain / Creative Commons) for stories set before 2000: Wikimedia Commons + Internet Archive.
# No key needed. Only used when the article is about a past era; falls back to the stock sites above.
ARCHIVE_VIDEO = os.environ.get("ARCHIVE_VIDEO", "0") == "1"
ARCHIVE_ANY_ERA = os.environ.get("ARCHIVE_ANY_ERA", "0") == "1"   # 1 = real archive footage for every article, not only pre-2000 stories
ARCHIVE_MAX_MB = float(os.environ.get("ARCHIVE_MAX_MB", "120"))
ARCHIVE_CLIP_SEC = float(os.environ.get("ARCHIVE_CLIP_SEC", "12"))
# Real footage is OPT-IN per article: STOCK_VIDEO / ARCHIVE_VIDEO only take effect for a job file that has
# "footage": true, unless FOOTAGE_ALL=1. History/culture essays rarely have footage of their exact subject,
# so by default every new article gets AI pictures matched to its narration instead of a guessed clip.
FOOTAGE_ALL = os.environ.get("FOOTAGE_ALL", "0") == "1"
_ARCHIVE_ENV, _STOCK_ENV = ARCHIVE_VIDEO, STOCK_VIDEO

# Real photographs matched to each slide's own narration (Unsplash + Pixabay photos + Wikimedia Commons).
SLIDE_PHOTOS = os.environ.get("SLIDE_PHOTOS", "0") == "1"   # stock photos are matched by keyword only and often miss the meaning; off by default
UNSPLASH_ACCESS_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "").strip()
PHOTO_MAX_SEARCHES = int(os.environ.get("PHOTO_MAX_SEARCHES", "30"))   # per video; Unsplash demo keys allow 50 requests/hour
# On Philippine stories a stock clip must itself mention the Philippines/a Philippine place, else the slide keeps a better-matched photo.
# A small free AI text model (Cloudflare Workers AI) writes each slide's search words + "must not show" words and judges candidates.
LLM_PLAN = os.environ.get("LLM_PLAN", "1") != "0"
LLM_MODEL = os.environ.get("LLM_MODEL", "@cf/meta/llama-3.1-8b-instruct")
LLM_MAX_CALLS = int(os.environ.get("LLM_MAX_CALLS", "400"))
# Strict matching: a body slide shows only a picture that matched ITS narration (or an AI image of it). Never a loosely related photo.
STRICT_MATCH = os.environ.get("STRICT_MATCH", "1") != "0"
WIKI_GENERIC = os.environ.get("WIKI_GENERIC", "0") == "1"   # 1 = also pull photos by the article title alone (they often do not match a slide)
CREDITS_CARD = os.environ.get("CREDITS_CARD", "0") == "1"   # 1 = also speak/show a credits card in the video (credits are always in the description)
STOCK_REQUIRE_REGION = os.environ.get("STOCK_REQUIRE_REGION", "1") != "0"

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


def clean_text(raw: str | None) -> str:
    s = raw or ""
    s = re.sub(r"(?is)<(script|style|audio|video|iframe|noscript)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)</(p|div|h[1-6]|li|blockquote)>|<br\s*/?>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"https?://\S+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def extract_main(raw: str | None) -> str:
    s = raw or ""
    s = re.sub(r"(?m)^\s*```[a-zA-Z]*\s*$", " ", s)
    m = re.search(r"(?is)<main\b[^>]*>(.*)</main\s*>", s)
    if m:
        s = m.group(1)
    else:
        b = re.search(r"(?is)<body\b[^>]*>(.*)</body\s*>", s)
        if b:
            s = b.group(1)
        s = re.sub(r"(?is)<head\b.*?</head>", " ", s)
        for tag in ("header", "footer", "nav", "aside"):
            s = re.sub(rf"(?is)<{tag}\b.*?</{tag}>", " ", s)
        s = re.sub(r"(?is)<(div|section)\b[^>]*class=[\"'][^\"']*(ad-slot|footer|header|sidebar|nav)[^\"']*[\"'][^>]*>.*?</\1>", " ", s)

    s = re.sub(r"(?is)<ins\b.*?</ins>", " ", s)
    s = re.sub(r"(?is)<(header|footer|nav|aside)\b.*?</\1>", " ", s)
    s = re.sub(r"(?is)<div\b[^>]*class=[\"'][^\"']*ad-slot[^\"']*[\"'][^>]*>.*?</div>", " ", s)
    return s


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?\u2026])\s+(?=[A-Z0-9\"\u201c\u2018(])", text)
    return [p.strip() for p in parts if len(p.strip()) > 2]


def slugify(s: str | None) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())) or "article"


def build_chunks(sentences: list[str], budget: int, target: int | None = None) -> tuple[list[str], int]:
    target = target or SLIDE_WORDS
    hard = int(target * 1.6)
    chunks, cur, cw, total = [], [], 0, 0
    for s in sentences:
        words = s.split()
        w = len(words)
        if w < 4:
            continue
        if w > 70:
            s = " ".join(words[:65]).rstrip(",;:") + "\u2026"
            w = 66
        if total + w > budget:
            break
        if cur and cw + w > hard:
            chunks.append(" ".join(cur))
            cur, cw = [], 0
        cur.append(s)
        cw += w
        total += w
        if cw >= target:
            chunks.append(" ".join(cur))
            cur, cw = [], 0
    if cur:
        chunks.append(" ".join(cur))
    return chunks, total


def strip_flat_page_chrome(text: str, title: str, author: str) -> str:
    """If a whole web page was flattened to plain text, drop the title + byline at the start and the
    copyright footer at the end, so narration begins with the story itself."""
    t = " ".join((text or "").split())
    if title and t.lower().startswith(title.lower()):
        t = t[len(title):].lstrip(" :-\u2013\u2014")
    if author:
        email = r"[\w.+-]+@[\w-]+\.[\w.]*\w"
        m = re.match(r"By\s+" + re.escape(author) + r"\b.{0,260}?" + email + r"\s*", t, re.I)
        if m:
            t = t[m.end():]
        k = t.rfind("\u00a9")
        if k != -1 and len(t) - k < 400:
            t = t[:k]
    return t.strip()


def build_segments(job: Job) -> list[Seg]:
    title = clean_text(job.get("title")) or "Untitled"
    excerpt = clean_text(job.get("excerpt"))
    category = clean_text(job.get("category"))
    author = clean_text(job.get("author")) or "Glenn Junsay Pansensoy"
    sub = f"{category}  \u00b7  {author}" if category else author

    speech = title.rstrip(".!?") + "."
    if excerpt:
        speech += " " + excerpt
    segs = [{"kind": "title", "title": title, "sub": sub, "speech": speech}]

    raw_body = job.get("body") or ""
    if not re.search(r"<[a-zA-Z/!][^>]*>", raw_body):  # plain text from the portal
        raw_body = strip_flat_page_chrome(raw_body, title, author)
    main_html = extract_main(raw_body)
    if not excerpt:   # no excerpt written: use the article's own first sentence so the intro always has one
        for s0 in split_sentences(clean_text(main_html))[:6]:
            if 6 <= len(s0.split()) <= 40:
                excerpt = s0
                break
    parts = re.split(r"(?is)(<h[1-3]\b[^>]*>.*?</h[1-3]>)", main_html)
    budget, heading, first = MAX_WORDS, "", True
    for part in parts:
        if budget <= 0:
            break
        if re.match(r"(?is)<h[1-3]\b", part or ""):
            h = clean_text(part)
            if h and h.lower().rstrip(".!?") != title.lower().rstrip(".!?"):
                heading = h
                n = len(h.split())
                if SPEAK_HEADINGS and n >= 2 and n <= budget:
                    segs.append({"kind": "body", "text": h, "speech": h.rstrip(".!?:;,") + ".",
                                 "heading": h, "is_heading": True})
                    budget -= n
            continue
        sentences = split_sentences(clean_text(part))
        if first and sentences:
            if excerpt and sentences[0][:40].lower() == excerpt[:40].lower():
                sentences = sentences[1:]
            first = False
        chunks, used = build_chunks(sentences, budget)
        budget -= used
        for chunk in chunks:
            segs.append({"kind": "body", "text": chunk, "speech": chunk, "heading": heading})
        if len(segs) > 400:
            break

    custom_intro = clean_text(job.get("intro"))  # per-article opening written in the portal
    greeting = custom_intro or narration_greeting(title, excerpt)
    if greeting and (custom_intro or not any(str(s.get("speech", "")).lower().startswith(NARRATION_GREETING.lower()) for s in segs)):
        if INTRO_TITLE:
            # the title card is spoken: greeting replaces the bare title, excerpt still follows
            segs[0]["speech"] = greeting
            segs[0]["kind"] = "intro"
        else:
            # the title card is dropped, so the greeting becomes the first thing said (and shown as a caption)
            segs.insert(1, {"kind": "intro", "title": title, "text": greeting, "speech": greeting, "heading": ""})
    if not INTRO_TITLE and len(segs) > 1:
        segs = segs[1:]
    segs.append({
        "kind": "end",
        "title": "Read the full essay",
        "sub": "The Commonplace",
        "url": SITE_URL.rstrip("/"),
        "speech": "Read the full essay on The Commonplace, at poetic codes dot pages dot dev.",
        "caption": "Read the full essay on The Commonplace: " + SITE_URL.rstrip("/"),
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


BAND_H = int(BGW * IMGH / W) // 2 * 2      # the part of the 2560x1440 canvas that is actually shown (2560x1080)
MAX_CROP = 0.18                            # a photo may lose at most this much to fill the picture area


def fit_band(img):
    """Put the WHOLE photo in the picture area. If its shape is close, it is cropped by at most MAX_CROP;
    otherwise it is shown complete with a soft blurred copy of itself on the sides (never a hard crop)."""
    from PIL import ImageFilter
    w, h = img.size
    s_cover = max(BGW / w, BAND_H / h)
    s_contain = min(BGW / w, BAND_H / h)
    sc = max(s_contain, s_cover * (1 - MAX_CROP))
    nw, nh = max(1, int(w * sc)), max(1, int(h * sc))
    canvas = ImageOps.fit(img, (BGW, BGH), Image.LANCZOS)
    if nw >= BGW and nh >= BAND_H:
        pass
    else:
        canvas = canvas.resize((BGW // 8, BGH // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6)).resize((BGW, BGH), Image.BICUBIC)
        canvas = Image.eval(canvas, lambda v: int(v * 0.7))
    pic = img.resize((nw, nh), Image.LANCZOS)
    canvas.paste(pic, ((BGW - nw) // 2, (BGH - nh) // 2))
    return canvas


PROFILE = [None]   # the round profile picture shown while the introduction is narrated


USER_CLIPS = []   # short video clips supplied with the job (portal "Extra video clips"), downloaded for this run


def load_user_clips(job, tmp):
    """Download the author's own short clips (direct .mp4 links) so they can play under the narration."""
    USER_CLIPS.clear()
    urls = [str(u).strip() for u in (job.get("clips") or []) if u and str(u).strip().startswith("http")][:12]
    for n, u in enumerate(urls):
        dest = Path(tmp) / f"user_clip_{n}.mp4"
        try:
            with requests.get(u, stream=True, timeout=120, headers={"User-Agent": UA}) as r:
                r.raise_for_status()
                size = 0
                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        size += len(chunk)
                        if size > 80 * 1024 * 1024:
                            raise ValueError("clip larger than 80 MB")
                        fh.write(chunk)
            if probe_duration(dest) > 0.5:
                USER_CLIPS.append(str(dest))
            else:
                log(f"  clip {n + 1} is not a playable video; skipped")
        except Exception as e:
            log(f"  clip {n + 1} not usable ({str(e)[:80]})")
    if urls:
        log(f"  {len(USER_CLIPS)} of {len(urls)} supplied video clip(s) ready")


def load_profile(job):
    """Profile picture for the intro slide: job "profileUrl", env PROFILE_IMAGE_URL, or a file in the repo."""
    for u in (job.get("profileUrl"), os.environ.get("PROFILE_IMAGE_URL", "").strip()):
        if u and str(u).startswith("http"):
            img = load_cover(u)
            if img is not None:
                return img
    for name in ("profile.jpg", "profile.jpeg", "profile.png", "assets/profile.jpg", "assets/profile.png", "images/profile.jpg", "images/profile.png"):
        try:
            if Path(name).exists():
                return Image.open(name).convert("RGB")
        except Exception as e:
            log(f"  profile picture not usable ({str(e)[:80]})")
    return None


def draw_intro_card(ov, d, seg, has_cover=False):
    """Round profile picture, channel name and essay title in the picture area."""
    if os.environ.get("INTRO_TEXT", "0") != "1":
        return   # introduction = the cover picture only: no words on top, only the caption bar below
    prof = None if has_cover else PROFILE[0]
    y = 36
    if has_cover:
        d.rectangle([0, 0, W, IMGH], fill=(6, 10, 18, 150))   # darken the article's cover so the words read
        y = 150
    if prof is not None:
        D = 250
        s = min(prof.width, prof.height)
        sq = prof.crop(((prof.width - s) // 2, (prof.height - s) // 2, (prof.width + s) // 2, (prof.height + s) // 2)).resize((D, D), Image.LANCZOS).convert("RGBA")
        mask = Image.new("L", (D, D), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, D - 1, D - 1], fill=255)
        x = (W - D) // 2
        d.ellipse([x - 7, y - 7, x + D + 7, y + D + 7], fill=ACCENT + (255,))
        ov.paste(sq, (x, y), mask)
        y += D + 22
    elif not has_cover:
        y = 120
    name = "Poetic Codes"
    f = load_font(46, True)
    w = d.textlength(name, font=f)
    d.text(((W - w) / 2 + 2, y + 2), name, font=f, fill=(0, 0, 0, 255))
    d.text(((W - w) / 2, y), name, font=f, fill=ACCENT + (255,))
    y += 66
    title = seg.get("title", "")
    if title:
        font, lines, lh = fit_text(d, title, W - 160, max(60, IMGH - y - 16), range(40, 23, -2), True)
        for ln in lines:
            w = d.textlength(ln, font=font)
            d.text(((W - w) / 2 + 2, y + 2), ln, font=font, fill=(0, 0, 0, 255))
            d.text(((W - w) / 2, y), ln, font=font, fill=TEXT + (255,))
            y += lh


def render_layers(seg, idx, total, cover):
    if cover is not None:
        bg = fit_band(cover.convert("RGB"))
    else:
        bg = gradient_bg().resize((BGW, BGH), Image.BICUBIC)
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([0, IMGH, W, H], fill=(6, 10, 18, 255))
    d.rectangle([0, IMGH, W, IMGH + 3], fill=ACCENT + (255,))
    d.rectangle([0, H - 8, int(W * (idx + 1) / total), H], fill=ACCENT + (255,))
    if seg.get("kind") == "intro":
        draw_intro_card(ov, d, seg, cover is not None)
    if seg.get("kind") == "end" and os.environ.get("END_CARD_TEXT", "1") == "1":
        # End card: darken the picture and show the link on screen.
        d.rectangle([0, 0, W, IMGH], fill=(6, 10, 18, 175))
        rows = [(seg.get("title", ""), load_font(54, True), TEXT),
                (seg.get("sub", ""), load_font(34), ACCENT),
                (seg.get("url", ""), load_font(40, True), TEXT)]
        gap = 26
        heights = [int(f.size * 1.3) for _, f, _ in rows]
        y = (IMGH - (sum(heights) + gap * (len(rows) - 1))) // 2
        for (txt, f, col), hh in zip(rows, heights):
            if txt:
                w = d.textlength(txt, font=f)
                d.text(((W - w) / 2 + 2, y + 2), txt, font=f, fill=(0, 0, 0, 255))
                d.text(((W - w) / 2, y), txt, font=f, fill=col + (255,))
            y += hh + gap
    return bg, ov


def split_captions(text: str, max_words: int = CAP_WORDS) -> list[str]:
    pieces = []
    for sent in split_sentences(text) or [text]:
        words = sent.split()
        if len(words) <= max_words:
            pieces.append(sent)
            continue
        cur = []
        for w in words:
            cur.append(w)
            if (len(cur) >= max_words // 2 and w.endswith((",", ";", ":"))) or len(cur) >= max_words:
                pieces.append(" ".join(cur))
                cur = []
        if cur:
            if pieces and len(cur) < 4:
                pieces[-1] += " " + " ".join(cur)
            else:
                pieces.append(" ".join(cur))
    return [p for p in pieces if p.strip()]


def render_caption(text):
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    pad = 70
    font, lines, lh = fit_text(d, text, W - 2 * pad, BANDH - 36, range(32, 21, -2))
    y = IMGH + 3 + (BANDH - 3 - len(lines) * lh) // 2 - 4
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=TEXT + (255,))
        y += lh
    return ov


def caption_timings(speech: str, dur: float) -> list[tuple[str, float, float]]:
    pieces = split_captions(speech)
    weights = [max(1, len(p.split())) for p in pieces]
    total = float(sum(weights))
    out, t = [], 0.0
    for p, w in zip(pieces, weights):
        span = dur * w / total
        out.append((p, t, t + span))
        t += span
    return out


ACTIVE_VOICE = [None]      # set per article from the job file (portal "Narration voice"); None = the default VOICE
_VOICE_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$")


def set_job_voice(job: Job) -> None:
    v = clean_text(job.get("voice"))
    ACTIVE_VOICE[0] = v if _VOICE_RE.match(v or "") else None


async def _edge_synth(text, out, voice=None):
    import edge_tts
    await edge_tts.Communicate(text, voice or ACTIVE_VOICE[0] or VOICE, rate=RATE).save(out)


def pick_rate(segs: list[Seg]) -> str:
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
    if TTS_FAKE:
        dur = max(1.5, len(text.split()) / 2.6)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
             "-t", f"{dur:.2f}", "-c:a", "libmp3lame", out_mp3])
        return "fake"

    last = None
    first = ACTIVE_VOICE[0] or VOICE
    voices = [first] + [v for v in [VOICE] + VOICE_FALLBACKS if v != first]
    for attempt in range(4):
        v = voices[min(attempt // 2, len(voices) - 1)]    # two tries per voice, then the next voice
        try:
            asyncio.run(_edge_synth(text, out_mp3, v))
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


def probe_duration(path: str | Path) -> float:
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(p.stdout.decode().strip())


MOTIONS = [
    (0.0, 1.0, 0.0, 1.0),
    (1.0, 0.0, 1.0, 0.0),
    (1.0, 0.0, 0.0, 1.0),
    (0.0, 1.0, 1.0, 0.0),
    (0.0, 1.0, 0.5, 0.5),
    (1.0, 0.0, 0.5, 0.5),
    (0.25, 0.75, 0.0, 1.0),
    (0.75, 0.25, 1.0, 0.0),
]


def make_clip(bg_png, ov_png, mp3, out, caps, motion=0, pad=0.7, vkbps=900, bg2_png=None):
    """Animate a still (or pair of stills) so the picture feels alive while narration plays.
    When bg2_png is set, crossfade between two related frames to imply character movement."""
    dur = probe_duration(mp3) + pad
    x0, x1, y0, y1 = MOTIONS[motion % len(MOTIONS)]
    ow, oh = (960, 540) if vkbps < 450 else (W, H)
    nfr = max(int(dur * FPS), 1)
    zin = motion % 2 == 0
    z_amt = max(ZOOM, 0.12)
    zexpr = f"1+{z_amt}*on/{nfr}" if zin else f"1+{z_amt}*(1-on/{nfr})"
    px = f"on/{nfr}" if x1 > x0 else f"(1-on/{nfr})"
    wide_h = int(BGW * IMGH / W) // 2 * 2
    vr = BGH - wide_h
    ye2 = f"{0.5 * vr:.1f}"      # always the middle band: the whole photo is placed there, so no vertical panning

    def pic_chain(inp, label):
        chain = (
            f"[{inp}:v]crop={BGW}:{wide_h}:x=0:y='{ye2}',"
            f"zoompan=z='{zexpr}':x='(iw-iw/zoom)*{px}':y='(ih-ih/zoom)*0.5':d=1:s={W}x{IMGH}:fps={FPS}"
        )
        if VIGNETTE:
            chain += ",vignette=PI/5"
        if GRAIN > 0:
            chain += f",noise=alls={GRAIN}:allf=t"
        chain += f"[{label}]"
        return chain

    inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(bg_png)]
    if bg2_png:
        inputs += ["-loop", "1", "-framerate", str(FPS), "-i", str(bg2_png)]
        ov_idx = 2
        mp3_idx = 3
        cap_base = 4
        # Crossfade in the middle third so characters appear to shift/move.
        # Clamp so offset + fade length always fits inside the clip (short clips).
        fade_dur = min(1.2, max(0.6, dur * 0.28), dur * 0.5)
        fade_off = max(0.0, min(dur * 0.32, dur - fade_dur - 0.1))
        fc = (
            pic_chain(0, "p0") + ";" +
            pic_chain(1, "p1") + ";" +
            f"[p0][p1]xfade=transition=fade:duration={fade_dur:.2f}:"
            f"offset={fade_off:.2f},"
            f"pad={W}:{H}:0:0:color=black,setsar=1[v0];"
        )
    else:
        ov_idx = 1
        mp3_idx = 2
        cap_base = 3
        fc = (
            pic_chain(0, "p0") + ";" +
            f"[p0]"
            f"pad={W}:{H}:0:0:color=black,setsar=1[v0];"
        )

    fc += f"[v0][{ov_idx}:v]overlay=format=auto[v1];"
    last = "v1"
    for k, (_, t0, t1) in enumerate(caps):
        t1 = dur + 1 if k == len(caps) - 1 else t1
        nxt = f"v{k + 2}"
        fc += (
            f"[{last}][{cap_base + k}:v]overlay=format=auto:"
            f"enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}];"
        )
        last = nxt
    fc += f"[{last}]scale={ow}:{oh}:flags=bicubic,format=yuv420p[v]"

    cmd = ["ffmpeg", "-y"] + inputs
    cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(ov_png), "-i", str(mp3)]
    for png, _, _ in caps:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(png)]
    cmd += [
        "-filter_complex", fc,
        "-map", "[v]", "-map", f"{mp3_idx}:a",
        "-t", f"{dur:.2f}",
        "-af", f"apad=pad_dur={pad}",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{vkbps}k",
        "-maxrate", f"{int(vkbps * 1.25)}k", "-bufsize", f"{vkbps * 2}k", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "40k", "-ar", "24000", "-ac", "1", str(out),
    ]
    run(cmd)
    return dur


def load_cover(url):
    if not url or not str(url).startswith("http"):
        return None
    try:
        r = requests.get(url, timeout=60, headers={"User-Agent": UA})
        r.raise_for_status()
        return Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        log(f"  image not usable ({str(e)[:80]})")
        return None


USER_PHOTOS = []   # extra pictures supplied with the job (portal 'Extra images')


def load_photos(job):
    urls = []
    for u in [job.get("coverUrl")] + list(job.get("images") or []):
        if u and str(u).startswith("http") and u not in urls:
            urls.append(u)
    photos = []
    USER_PHOTOS.clear()
    mine = {str(u) for u in (job.get("images") or []) if u}
    for u in urls[:21]:
        img = load_cover(u)
        if img is not None and img.width >= 400 and img.height >= 250:
            photos.append(img)
            if str(u) in mine:
                USER_PHOTOS.append(img)   # pictures the author supplied in the portal: shown across the content slides
    log(f"  {len(photos)} photograph(s) available for the background ({len(USER_PHOTOS)} supplied by you)")
    return photos


_SKIP_TITLE = re.compile(r"logo|flag|coat of arms|icon|signature|seal of|locator|stub|banner|diagram|chart|graph|screenshot|thumbnail|youtube|poster|cover|meme|infographic|slide|presentation|committee|hearing|congress|senate|session|conference|press|portrait|headshot|official", re.I)


_CAP_STOP = {"The", "This", "That", "These", "Those", "When", "Where", "While", "With", "Without", "Many", "Some",
             "Most", "Their", "There", "They", "Then", "Than", "What", "Which", "Who", "How", "Why", "Because", "Although",
             "However", "Also", "Even", "Each", "Every", "From", "Into", "Over", "After", "Before", "During", "Between",
             "Such", "Both", "Other", "Another", "Today", "Still", "Yet", "And", "But", "For", "Not", "Its", "Our", "Your"}


def wiki_queries(job):
    title = clean_text(job.get("title"))
    main = re.split(r"[:\u2013\u2014(]", title)[0].strip() or title
    stop = {"the", "a", "an", "of", "in", "on", "and", "to", "for", "with", "is", "are", "how", "why", "what"}
    key = [w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", main) if w.lower() not in stop][:6]
    cat = clean_text(job.get("category"))
    body = clean_text(extract_main(job.get("body")))
    counts = {}
    for w in re.findall(r"\b[A-Z][a-z]{3,}\b", body):
        if w not in _CAP_STOP:
            counts[w] = counts.get(w, 0) + 1
    nouns = [w for w, c in sorted(counts.items(), key=lambda x: -x[1]) if c >= 3][:4]
    qs = []
    ph = bool(re.search(r"philippin|iloilo|zamboanga|visayas|mindanao|ilonggo|cebu|manila|panay|negros|sibugay",
                        (title + " " + body[:6000] + " " + clean_text((job.get("location") or {}).get("name"))).lower()))
    anchor = " Philippines" if ph else ""      # a bare word like "Talon" or "Estancia" matches places all over the world
    loc_name = clean_text(((job.get("location") or {}).get("name") or "").split(",")[0])
    if loc_name:
        qs.append(loc_name)
    # Prefer searches that return people in action, not maps/flags
    if key:
        qs.append(" ".join(key[:4]) + " people")
        qs.append(" ".join(key[:3]))
    if len(key) > 2:
        qs.append(" ".join(key[:2]) + " workers")
    for n in nouns[:3]:
        qs.append(n + anchor)
    if len(nouns) >= 2:
        qs.append(f"{nouns[0]} {nouns[1]}{anchor}")
    if cat and key:
        qs.append(f"{key[0]} {cat}")
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:6]


def wiki_search(query, limit=20):
    r = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={"action": "query", "format": "json", "generator": "search", "gsrsearch": query,
                "gsrnamespace": 6, "gsrlimit": limit, "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600},
        headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    pages = (r.json().get("query") or {}).get("pages") or {}
    out = []
    for p in sorted(pages.values(), key=lambda x: x.get("index", 0)):
        info = (p.get("imageinfo") or [{}])[0]
        if info.get("mime") not in ("image/jpeg", "image/png"):
            continue
        if info.get("width", 0) < 1000 or info.get("height", 0) < 500:
            continue
        title = p.get("title", "")
        if _SKIP_TITLE.search(title):
            continue
        meta = info.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        artist = clean_text((meta.get("Artist") or {}).get("value", ""))[:80]
        out.append({"url": info.get("thumburl") or info.get("url"), "title": title,
                    "license": lic, "artist": artist, "page": info.get("descriptionurl", "")})
    return out


def load_wiki_photos(job, have):
    if not WIKI_IMAGES or WIKI_MAX <= 0:
        return []
    found, seen = [], set()
    for q in wiki_queries(job):
        try:
            got = wiki_search(q)
            log(f"  Wikimedia search '{q}': {len(got)} usable result(s)")
            for item in got:
                if item["url"] and item["url"] not in seen:
                    seen.add(item["url"])
                    found.append(item)
        except Exception as e:
            log(f"  Wikimedia search failed for '{q}' ({str(e)[:80]})")
        if len(found) >= WIKI_MAX * 2:
            break
    photos = []
    for item in found:
        if len(photos) >= WIKI_MAX:
            break
        img = load_cover(item["url"])
        if img is not None and img.width >= 800 and img.height >= 400:
            photos.append(img)
            CREDITS.append(f'{item["title"].replace("File:", "")} - {item["artist"] or "unknown"} '
                           f'({item["license"] or "see page"}) {item["page"]}')
            CREDIT_ROWS.append((item["artist"], item["license"]))
    log(f"  {len(photos)} photograph(s) added from Wikimedia Commons (searched: {', '.join(wiki_queries(job))})")
    return photos


def make_variants(img, n=5):
    w, h = img.size
    out = []
    spots = _SPOTS
    for i in range(n):
        fx, fy = spots[i % len(spots)]
        cw, ch = int(w * 0.84), int(h * 0.84)
        x0, y0 = int((w - cw) * fx), int((h - ch) * fy)
        crop = img.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.LANCZOS)
        out.append(crop)
    return out


STYLE_BASE = (
    "photorealistic documentary still from a cinematic film, 35mm lens, natural light, "
    "realistic textures, sharp focus, high detail, not an illustration, not a painting, "
    "not a cartoon, no text, no letters, no watermark, no logos"
)
STYLE_PEOPLE = (
    "people in mid-action, hands and bodies in natural motion, not a posed studio portrait"
)
_PEOPLE_RE = re.compile(
    r"\b(he|she|they|people|man|men|woman|women|worker|workers|farmer|farmers|child|children|family|crowd|"
    r"villager|villagers|trader|traders|soldier|soldiers|fisherman|fishermen|sailor|sailors|"
    r"laborer|laborers|owner|owners|settler|settlers)\b", re.I)

MOTION_HINTS = (
    "walking", "working", "carrying", "reaching", "talking", "gesturing", "looking",
    "fishing", "cooking", "planting", "harvesting", "loading", "sailing", "rowing",
    "market", "crowd", "street", "hands", "labor", "procession", "ceremony"
)


def visual_focus(text: str | None) -> str:
    """Pull the concrete people, places and actions the narrator is describing."""
    t = (text or "").strip()
    if not t:
        return "people in a real historical scene, mid-action"
    # Prefer clauses with people/action verbs
    sentences = re.split(r"(?<=[.!?])\s+", t)
    best = sentences[0] if sentences else t
    for s in sentences:
        sl = s.lower()
        if any(h in sl for h in MOTION_HINTS) or re.search(
            r"\b(man|men|woman|women|child|children|people|worker|farmers?|fishermen|"
            r"traders?|soldiers?|family|crowd|villagers?)\b", sl
        ):
            best = s
            break
    # Keep it short and visual
    words = best.split()
    if len(words) > 36:
        best = " ".join(words[:36])
    return best.rstrip(" ,.;:")


PROMPT_WORDS = int(os.environ.get("PROMPT_WORDS", "115"))  # scene words; with style + setting the whole prompt stays near 170 words


def _words(text: str, n: int) -> str:
    return " ".join(str(text or "").split()[:n]).rstrip(" ,.;:")


def story_context(job: Job, speech: str) -> tuple[str, str, str]:
    """From the job file: the characters in this stretch of narration, the place/era/palette, and the look.
    A character is included when its name or one of its 'appearsIn' words is in the narration."""
    loc = job.get("location") or {}
    place = ", ".join(x for x in (_words(loc.get("name"), 10), _words(loc.get("era"), 6)) if x)
    details = _words(loc.get("description") or loc.get("details"), 28)
    palette = _words(loc.get("palette"), 12)
    setting = "; ".join(x for x in (place, details, palette and f"palette {palette}") if x)
    cast = []
    for c in job.get("characters") or []:
        keys = [c.get("name", "")] + list(c.get("appearsIn") or [])
        if any(k and re.search(r"\b" + re.escape(k) + r"\b", speech, re.I) for k in keys):
            cast.append(f"{c.get('name', '')}: {_words(c.get('description'), 24)}")
    look = _words((job.get("style") or {}).get("look"), 18)
    return "; ".join(cast[:2]), setting, look


_SCENE_CACHE: dict = {}


def llm_scene(speech: str, heading: str, job: Job, cast: str) -> str:
    """A film director's one-scene description of what this narration means, written by the free AI model.
    Abstract ideas (inequality, migration, tension) become a concrete, filmable moment in the right place and era."""
    if speech in _SCENE_CACHE:
        return _SCENE_CACHE[speech]
    loc = job.get("location") or {}
    ctx = f"Article: {clean_text(job.get('title'))}. Place: {clean_text(loc.get('name'))}. Era: {clean_text(loc.get('era'))}."
    if clean_text(loc.get("description")):
        ctx += f" Typical scenery: {clean_text(loc.get('description'))[:200]}."
    if cast:
        ctx += f" Recurring people: {cast}."
    out = llm_text(
        "You direct a documentary. Read the narration and describe ONE concrete scene a camera could film that shows "
        "what is being said. Rules: real people doing a specific action in a specific kind of place; turn abstract ideas "
        "(policy, inequality, migration, supply chains) into one visible moment. Follow the era given: if it says present day, "
        "show modern settings (factories, labs, offices, ports, classrooms, data centers) and NEVER a 1950s or rural scene; "
        "if it is historical, use no modern objects (example for a historical sugar essay: 'a barefoot cane cutter resting beside a hand cart'). "
        "Show only what the narration or typical scenery supports: do not add farmers, looms, markets, rice fields or foreign "
        "nationalities unless the narration mentions them. No text, signs, maps, charts, flags or logos; never mention the "
        "narration or the camera. Reply with the description only, 25 to 45 words.",
        f"{ctx}\nSection: {heading}\nNarration: {speech[:900]}", max_tokens=130)
    scene = ""
    if out:
        scene = clean_text(out).strip().strip('"')
        scene = re.sub(r"^(scene|description|image)\s*:\s*", "", scene, flags=re.I)
        scene = " ".join(scene.split()[:55]).rstrip(" ,;:")
        if len(scene.split()) < 6:
            scene = ""
    _SCENE_CACHE[speech] = scene
    return scene


def scene_prompt(seg: Seg, job: Job) -> str:
    """Describe EVERY sentence the picture sits under, shortened to its concrete part.
    The image model ignores the end of a long prompt, so the style words go first and the
    scene follows; if there are too many sentences they are thinned evenly, never cut off.
    Characters, place, era and look come from the job file when it has them."""
    title = clean_text(job.get("title")) or ""
    category = clean_text(job.get("category")) or ""
    heading = clean_text(seg.get("heading") or "")
    speech = clean_text(seg.get("speech") or seg.get("text") or "")
    cast, setting, look = story_context(job, speech)
    director = llm_scene(speech, heading, job, cast)
    if director:       # the scene comes FIRST: that is the part the picture must get right
        has_people = bool(_PEOPLE_RE.search(director)) or bool(cast)
        style = (look + ", " if look else "") + STYLE_BASE + (", " + STYLE_PEOPLE if has_people else "")
        parts = [f"Photograph of: {director}.", f"Place: {setting}." if setting else "",
                 f"Characters: {cast}." if cast else "", style + "."]
        return " ".join(p for p in parts if p).strip()[:1900]

    def short(x, n=16):
        w = re.sub(r"\s+([,.;:])", r"\1", visual_focus(x)).split()
        if len(w) > n:
            w = w[:n]
            for k in range(len(w) - 1, 7, -1):  # cut at a comma instead of mid-phrase
                if w[k].endswith(","):
                    w = w[:k + 1]
                    break
        return " ".join(w).rstrip(" ,.;:")

    sents = [x.strip() for x in re.split(r"(?<=[.!?])\s+", speech) if len(x.split()) >= 4] or [speech]
    per = [x for x in (short(x) for x in sents) if x]
    # characters/setting use part of the word budget, so the scene sentences are thinned to fit
    extra = len((cast + " " + setting).split())
    budget = max(45, PROMPT_WORDS - extra)
    while per and sum(len(x.split()) for x in per) > budget and len(per) > 1:
        per.pop(len(per) // 2)
    focus = "; ".join(per)
    has_people = bool(_PEOPLE_RE.search(focus)) or bool(cast)
    style = (look + ", " if look else "") + STYLE_BASE + (", " + STYLE_PEOPLE if has_people else "")
    scene = ("people actively moving through the scene, caught mid-movement." if has_people
             else "the places, objects and landscape described, people only if they fit naturally.")
    where = heading or title
    ctx = f"Setting: {title}" + (f", {category}" if category else "") + "."
    parts = [style + ".", f"{where}." if where else "", "Show: " + focus + ".",
             f"Characters: {cast}." if cast else "", f"Place: {setting}." if setting else "", scene, ctx]
    return " ".join(p for p in parts if p).strip()[:1900]


def _from_bytes(data):
    img = Image.open(BytesIO(data)).convert("RGB")
    if img.width < 400 or img.height < 250:
        return None
    return img


def gen_image_cloudflare(prompt):
    if not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN):
        return None
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell",
        headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
        json={"prompt": prompt[:1900], "steps": 4}, timeout=60,
    )
    if not r.ok:
        low = (r.text or "").lower()
        # Only a message about the daily allowance means "out of quota". A bare 429 is a short rate limit: retry it.
        if any(k in low for k in ("neurons", "quota", "daily", "used up", "4006")):
            QUOTA_HIT[0] = True
        err = RuntimeError(f"Cloudflare HTTP {r.status_code}: {(r.text or '')[:250]}")
        err.rate_limited = r.status_code == 429
        raise err
    import base64
    data = r.json()
    if not data.get("success", True) or not (data.get("result") or {}).get("image"):
        raise RuntimeError(f"Cloudflare gave no image: {str(data)[:250]}")
    return _from_bytes(base64.b64decode(data["result"]["image"]))


LAST_IMG_ERROR = [""]
FALLBACK_STATE = {"fails": 0, "dead": False, "used": 0, "last": 0.0}


def gen_image_hf(prompt):
    if not HF_TOKEN:
        return None
    r = requests.post(f"https://router.huggingface.co/hf-inference/models/{HF_MODEL}",
                      headers={"Authorization": f"Bearer {HF_TOKEN}"},
                      json={"inputs": prompt[:900]}, timeout=120)
    if not r.ok:
        raise RuntimeError(f"Hugging Face HTTP {r.status_code}: {(r.text or '')[:150]}")
    return _from_bytes(r.content)


def gen_image_pollinations(prompt):
    from urllib.parse import quote
    url = POLLINATIONS_URL.format(prompt=quote(prompt[:700], safe=""), seed=int(time.time()) % 100000)
    r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
    if not r.ok or "image" not in (r.headers.get("content-type") or ""):
        raise RuntimeError(f"Pollinations HTTP {r.status_code}: {(r.text or '')[:150]}")
    return _from_bytes(r.content)


def gen_image_fallback(prompt):
    """Free backup pictures made from the same prompt. Gives up for the rest of the run after 3 failures in a row."""
    if not FALLBACK_IMAGES or FALLBACK_STATE["dead"]:
        return None
    wait = FALLBACK_PAUSE - (time.time() - FALLBACK_STATE["last"])
    if wait > 0:
        time.sleep(wait)
    img = None
    for fn in (gen_image_hf, gen_image_pollinations):
        try:
            img = fn(prompt)
        except Exception as e:
            LAST_IMG_ERROR[0] = str(e)[:300]
            img = None
        if img is not None:
            break
    FALLBACK_STATE["last"] = time.time()
    if img is None:
        FALLBACK_STATE["fails"] += 1
        if FALLBACK_STATE["fails"] >= 3:
            FALLBACK_STATE["dead"] = True
            log(f"  backup picture generators failed 3 times in a row; stopping them ({LAST_IMG_ERROR[0]})")
        return None
    FALLBACK_STATE["fails"] = 0
    FALLBACK_STATE["used"] += 1
    return img


def gen_image(prompt):
    img = gen_image_cloudflare_retry(prompt) if (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN) else None
    if img is None:
        img = gen_image_fallback(prompt)
    return img


def gen_image_cloudflare_retry(prompt):
    waits = [2, 4]                       # ordinary errors: two quick retries
    attempt = 0
    while True:
        if QUOTA_HIT[0]:
            return None
        rate_limited = False
        try:
            img = gen_image_cloudflare(prompt)
            if img is not None:
                return img
        except Exception as e:
            LAST_IMG_ERROR[0] = str(e)[:300]
            rate_limited = bool(getattr(e, "rate_limited", False))
        if rate_limited:
            waits = [8, 20, 40]          # a rate limit passes after a short wait
        if attempt >= len(waits):
            return None
        time.sleep(waits[attempt])
        attempt += 1


_SPOTS = [(0.5, 0.5), (0.25, 0.5), (0.75, 0.5), (0.5, 0.3), (0.5, 0.7)]


def framing(img, k):
    if k <= 0 or img is None:
        return img
    w, h = img.size
    frac = 0.90 if k % 2 else 0.82
    cw, ch = int(w * frac), int(h * frac)
    fx, fy = _SPOTS[(k - 1) % len(_SPOTS)]
    x0, y0 = int((w - cw) * fx), int((h - ch) * fy)
    return img.crop((x0, y0, x0 + cw, y0 + ch)).resize((w, h), Image.LANCZOS)


def motion_pair(img):
    """Two slightly different crops of the same scene so a crossfade feels like movement."""
    if img is None:
        return None, None
    a = framing(img, 0)
    b = framing(img, 1)
    return a, b


def make_ai_images(segs, job):
    """One image per body slide, prompt locked to that slide's spoken words."""
    if not AI_IMAGES:
        return []
    if not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN) and not FALLBACK_IMAGES:
        log("  no Cloudflare keys (CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN): skipping generated pictures, using your photos")
        return []
    body_idx = [i for i, g in enumerate(segs) if g["kind"] == "body"]
    if not body_idx:
        return []
    # Prefer 1:1 with body slides; cap by AI_IMAGE_MAX
    k = min(len(body_idx), AI_IMAGE_MAX)
    out, fails, t_start = [], 0, time.time()
    for j in range(k):
        # Same mapping build_video uses: picture j sits under every body slide n with n*k//total == j.
        # Build its prompt from ALL of that narration, not just one slide.
        total_body = len(body_idx)
        members = [segs[body_idx[n]] for n in range(total_body) if n * k // total_body == j] or [segs[body_idx[j * total_body // k]]]
        narr = [m for m in members if not m.get("is_heading")] or members
        seg = {
            "heading": next((m.get("heading") for m in members if m.get("heading")), ""),
            "speech": " ".join(m["speech"] for m in narr),
        }
        prompt = scene_prompt(seg, job)
        log(f"  picture {j + 1}/{k}: {prompt[:170]}")
        if QUOTA_HIT[0] and FALLBACK_IMAGES and not FALLBACK_STATE["dead"] and not FALLBACK_STATE.get("announced"):
            FALLBACK_STATE["announced"] = True
            log(f"  Cloudflare free quota reached at {j}/{k}; continuing with the free backup generators")
        if QUOTA_HIT[0] and (not FALLBACK_IMAGES or FALLBACK_STATE["dead"]):
            log(f"  Cloudflare free quota reached at {j}/{k}; the remaining slides keep the last picture (no further calls)")
            if LAST_IMG_ERROR[0]:
                log(f"  Cloudflare said: {LAST_IMG_ERROR[0]}")
            out.extend([None] * (k - j))
            break
        if time.time() - t_start > IMG_BUDGET or fails >= IMG_FAIL_LIMIT:
            log(f"  picture generation stopped at {j}/{k} "
                f"({'time budget' if fails < IMG_FAIL_LIMIT else 'too many failures'}); keeping the last picture for the rest")
            if LAST_IMG_ERROR[0]:
                log(f"  last picture error: {LAST_IMG_ERROR[0]}")
            out.extend([None] * (k - j))
            break
        img = gen_image(prompt)
        fails = 0 if img is not None else fails + 1
        out.append(img)
        if (j + 1) % 6 == 0 or j + 1 == k:
            log(f"  generated pictures {j + 1}/{k}")
    got = sum(1 for x in out if x is not None)
    log(f"  {got} of {k} generated pictures usable (matched to narration); {FALLBACK_STATE['used']} came from the free backup generators")
    return out


def pick_bitrate(total_dur: float) -> int:
    total_kbits = MAX_MB * 8192 * 0.92
    return int(max(120, min(1200, total_kbits / max(total_dur, 1.0) - 40)))


def motion_prompt(seg, job):
    """Short physical action line for Kling image-to-video, derived from narration."""
    speech = clean_text(seg.get("speech") or seg.get("text") or "")
    focus = visual_focus(speech)
    title = clean_text(job.get("title") or "")
    heading = clean_text(seg.get("heading") or "")
    place = heading or title
    # Prefer action verbs; keep under ~80 words for Kling
    line = focus
    if place and place.lower() not in line.lower():
        line = f"{place}: {line}"
    extras = (
        "natural body motion, people moving through the scene, documentary camera, "
        "realistic physics, continuous movement, no freeze frame"
    )
    prompt = f"{line}. {extras}"
    words = prompt.split()
    if len(words) > 90:
        prompt = " ".join(words[:90])
    return prompt


def _image_to_data_uri(img, max_side=1280):
    """Encode a PIL image as a JPEG data URI for APIs that accept base64."""
    import base64
    from io import BytesIO as _B
    im = img.convert("RGB")
    w, h = im.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = _B()
    im.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


LAST_KLING_ERROR = [""]


def _kling_fal(image_uri, prompt, duration, out_mp4):
    """fal.ai Kling image-to-video (v2.1 / v3 standard)."""
    model = KLING_MODEL or "fal-ai/kling-video/v2.1/standard/image-to-video"
    # Prefer official fal client when installed; otherwise HTTP queue API
    try:
        import fal_client
        args = {
            "prompt": prompt[:2500],
            "image_url": image_uri,
            "duration": str(min(10, max(5, duration))) if "v2.1" in model else min(10, max(5, duration)),
            "negative_prompt": KLING_NEG,
        }
        result = fal_client.subscribe(model, arguments=args, with_logs=False)
        url = (result.get("video") or {}).get("url") or result.get("video_url")
        if not url:
            raise RuntimeError(f"fal returned no video url: {str(result)[:300]}")
        r = requests.get(url, timeout=180, headers={"User-Agent": UA})
        r.raise_for_status()
        Path(out_mp4).write_bytes(r.content)
        return out_mp4
    except ImportError:
        pass
    # HTTP fallback using fal queue
    headers = {"Authorization": f"Key {KLING_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt[:2500],
        "image_url": image_uri,
        "duration": str(min(10, max(5, int(duration)))),
        "negative_prompt": KLING_NEG,
    }
    sub = requests.post(
        f"https://queue.fal.run/{model}",
        headers=headers, json=payload, timeout=60,
    )
    if not sub.ok:
        raise RuntimeError(f"fal submit HTTP {sub.status_code}: {(sub.text or '')[:300]}")
    data = sub.json()
    req_id = data.get("request_id") or data.get("requestId")
    status_url = data.get("status_url") or (f"https://queue.fal.run/{model}/requests/{req_id}/status" if req_id else None)
    result_url = data.get("response_url") or (f"https://queue.fal.run/{model}/requests/{req_id}" if req_id else None)
    if not status_url:
        raise RuntimeError(f"fal submit missing status: {str(data)[:300]}")
    for _ in range(90):
        time.sleep(3)
        st = requests.get(status_url, headers=headers, timeout=30)
        if not st.ok:
            continue
        body = st.json()
        status = (body.get("status") or "").upper()
        if status in ("COMPLETED", "OK", "SUCCESS"):
            res = requests.get(result_url, headers=headers, timeout=60) if result_url else st
            res.raise_for_status()
            result = res.json()
            url = (result.get("video") or {}).get("url") or result.get("video_url")
            if not url:
                raise RuntimeError(f"fal done but no url: {str(result)[:300]}")
            r = requests.get(url, timeout=180, headers={"User-Agent": UA})
            r.raise_for_status()
            Path(out_mp4).write_bytes(r.content)
            return out_mp4
        if status in ("FAILED", "ERROR", "CANCELLED"):
            raise RuntimeError(f"fal failed: {str(body)[:400]}")
    raise RuntimeError("fal timed out waiting for Kling video")


def _kling_piapi(image_uri, prompt, duration, out_mp4):
    """PiAPI Kling image-to-video task + poll."""
    headers = {"x-api-key": KLING_API_KEY, "Content-Type": "application/json"}
    version = KLING_MODEL or "2.6"
    payload = {
        "model": "kling",
        "task_type": "video_generation",
        "input": {
            "prompt": prompt[:2500],
            "negative_prompt": KLING_NEG,
            "image_url": image_uri,
            "duration": int(min(10, max(5, duration))),
            "aspect_ratio": "16:9",
            "mode": "std",
            "version": version,
        },
    }
    sub = requests.post("https://api.piapi.ai/api/v1/task", headers=headers, json=payload, timeout=60)
    if not sub.ok:
        raise RuntimeError(f"piapi submit HTTP {sub.status_code}: {(sub.text or '')[:300]}")
    data = sub.json()
    task_id = (data.get("data") or {}).get("task_id") or data.get("task_id")
    if not task_id:
        raise RuntimeError(f"piapi no task_id: {str(data)[:300]}")
    for _ in range(90):
        time.sleep(3)
        st = requests.get(f"https://api.piapi.ai/api/v1/task/{task_id}", headers=headers, timeout=30)
        if not st.ok:
            continue
        body = st.json()
        info = body.get("data") or body
        status = (info.get("status") or "").lower()
        if status in ("completed", "success", "succeeded"):
            out = info.get("output") or info.get("result") or {}
            if isinstance(out, dict):
                url = out.get("video_url") or out.get("url") or (out.get("works") or [{}])[0].get("video") or (out.get("works") or [{}])[0].get("url")
            else:
                url = None
            if not url and isinstance(info.get("output"), str):
                url = info["output"]
            if not url:
                raise RuntimeError(f"piapi done but no url: {str(info)[:400]}")
            r = requests.get(url, timeout=180, headers={"User-Agent": UA})
            r.raise_for_status()
            Path(out_mp4).write_bytes(r.content)
            return out_mp4
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"piapi failed: {str(info)[:400]}")
    raise RuntimeError("piapi timed out waiting for Kling video")


def _kling_aimlapi(image_uri, prompt, duration, out_mp4):
    """AIMLAPI Kling image-to-video."""
    headers = {"Authorization": f"Bearer {KLING_API_KEY}", "Content-Type": "application/json"}
    model = KLING_MODEL or "kling-video/v4/image-to-video"
    payload = {
        "model": model,
        "prompt": prompt[:2500],
        "image_url": image_uri,
        "duration": int(min(15, max(3, duration))),
    }
    sub = requests.post("https://api.aimlapi.com/v2/video/generations", headers=headers, json=payload, timeout=60)
    if not sub.ok:
        raise RuntimeError(f"aimlapi submit HTTP {sub.status_code}: {(sub.text or '')[:300]}")
    data = sub.json()
    # Some responses are sync with URL; others return an id to poll
    url = None
    if isinstance(data.get("video"), dict):
        url = data["video"].get("url")
    url = url or data.get("video_url") or data.get("url")
    gen_id = data.get("id") or data.get("generation_id")
    if not url and gen_id:
        for _ in range(90):
            time.sleep(3)
            st = requests.get(f"https://api.aimlapi.com/v2/video/generations/{gen_id}", headers=headers, timeout=30)
            if not st.ok:
                continue
            body = st.json()
            status = (body.get("status") or "").lower()
            if status in ("completed", "succeeded", "success"):
                url = (body.get("video") or {}).get("url") or body.get("video_url") or body.get("url")
                break
            if status in ("failed", "error"):
                raise RuntimeError(f"aimlapi failed: {str(body)[:400]}")
    if not url:
        raise RuntimeError(f"aimlapi no video url: {str(data)[:400]}")
    r = requests.get(url, timeout=180, headers={"User-Agent": UA})
    r.raise_for_status()
    Path(out_mp4).write_bytes(r.content)
    return out_mp4


def gen_kling_clip(img, prompt, duration, out_mp4):
    """Animate a still with Kling image-to-video. Returns out_mp4 path or None on failure."""
    if not KLING_ENABLED or not KLING_API_KEY:
        return None
    if img is None:
        return None
    # fal and piapi both need at least 5s, so clamp here to match what you'll be billed for
    duration = int(min(10, max(5, duration or KLING_DURATION)))
    image_uri = _image_to_data_uri(img)
    providers = {
        "fal": _kling_fal,
        "piapi": _kling_piapi,
        "aimlapi": _kling_aimlapi,
    }
    fn = providers.get(KLING_PROVIDER)
    if not fn:
        LAST_KLING_ERROR[0] = f"unknown KLING_PROVIDER={KLING_PROVIDER!r} (use fal|piapi|aimlapi)"
        log(f"  Kling skipped: {LAST_KLING_ERROR[0]}")
        return None
    try:
        return fn(image_uri, prompt, duration, str(out_mp4))
    except Exception as e:
        LAST_KLING_ERROR[0] = str(e)[:400]
        log(f"  Kling failed ({KLING_PROVIDER}): {LAST_KLING_ERROR[0][:160]}")
        return None


def probe_size(path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        w, h = (int(x) for x in r.stdout.strip().split(",")[:2])
        return max(w, 2), max(h, 2)
    except Exception:
        return W, IMGH


def make_clip_from_video(video_mp4, ov_png, mp3, out, caps, pad=0.7, vkbps=900):
    """Composite a Kling (or other) video under the caption band + TTS narration."""
    spoken = probe_duration(mp3)
    dur = spoken + pad
    vid_dur = probe_duration(video_mp4)
    ow, oh = (960, 540) if vkbps < 450 else (W, H)
    # Scale the clip into the picture area (W x IMGH). A Kling clip is ~5 s but a slide lasts much longer, so a
    # short clip is played forward then backward, over and over ("ping-pong"): the people keep moving the whole
    # slide instead of freezing after 5 seconds.
    vw, vh = probe_size(video_mp4)
    sc = max(min(W / vw, IMGH / vh), max(W / vw, IMGH / vh) * (1 - MAX_CROP))   # show the whole frame; crop at most MAX_CROP
    fw, fh = max(2, int(vw * sc) // 2 * 2), max(2, int(vh * sc) // 2 * 2)
    base = (f"[0:v]fps={FPS},split[va][vb];"
            f"[va]scale={W}:{IMGH}:force_original_aspect_ratio=increase,crop={W}:{IMGH},boxblur=24:3,eq=brightness=-0.12[vbg];"
            f"[vb]scale={fw}:{fh}[vfg];[vbg][vfg]overlay=(W-w)/2:(H-h)/2:shortest=1,crop={W}:{IMGH}")
    if vid_dur + 0.05 < dur:
        frames = max(2, int(vid_dur * FPS) * 2)
        vchain = (
            f"{base},split[fw][bw];[bw]reverse[rv];[fw][rv]concat=n=2:v=1[pp];"
            f"[pp]loop=loop=-1:size={frames}:start=0,trim=duration={dur:.2f},setpts=PTS-STARTPTS,"
            f"pad={W}:{H}:0:0:color=black,setsar=1[v0];"
        )
    else:
        vchain = (
            f"{base},trim=duration={dur:.2f},"
            f"pad={W}:{H}:0:0:color=black,setsar=1[v0];"
        )
    fc = vchain + "[v0][1:v]overlay=format=auto[v1];"
    last = "v1"
    for k, (_, t0, t1) in enumerate(caps):
        t1 = dur + 1 if k == len(caps) - 1 else t1
        nxt = f"v{k + 2}"
        fc += (
            f"[{last}][{k + 3}:v]overlay=format=auto:"
            f"enable='between(t,{t0:.2f},{t1:.2f})'[{nxt}];"
        )
        last = nxt
    fc += f"[{last}]scale={ow}:{oh}:flags=bicubic,format=yuv420p[v]"
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_mp4),
        "-loop", "1", "-framerate", str(FPS), "-i", str(ov_png),
        "-i", str(mp3),
    ]
    for png, _, _ in caps:
        cmd += ["-loop", "1", "-framerate", str(FPS), "-i", str(png)]
    cmd += [
        "-filter_complex", fc,
        "-map", "[v]", "-map", "2:a",
        "-t", f"{dur:.2f}",
        "-af", f"apad=pad_dur={pad}",
        "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{vkbps}k",
        "-maxrate", f"{int(vkbps * 1.25)}k", "-bufsize", f"{vkbps * 2}k", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "40k", "-ar", "24000", "-ac", "1",
        str(out),
    ]
    run(cmd)
    return dur


_STOCK_STOP = {"that", "this", "with", "from", "were", "have", "been", "their", "there", "which", "would", "about",
               "into", "than", "then", "them", "they", "these", "those", "also", "while", "when", "where", "what",
               "more", "most", "some", "many", "such", "only", "over", "under", "after", "before", "because"}
# concrete things a stock-video site can find; people and actions come first in the query
_STOCK_PEOPLE = ["fisherman", "fishermen", "fishers", "fisherfolk", "farmer", "farmers", "workers", "children", "family", "crowd", "villagers",
                 "vendor", "vendors", "women", "men", "soldiers", "priest", "students", "traders", "sailors", "cook", "chef"]
_STOCK_THINGS = ["market", "boat", "boats", "fishing", "harvest", "rice", "sugarcane", "cooking", "street", "village",
                 "church", "procession", "festival", "sea", "ocean", "port", "harbor", "ship", "farm", "field", "mill",
                 "noodles", "soup", "dumplings", "kitchen", "fish", "river", "island", "city", "school", "road", "mountain",
                 "coconut", "mango", "tractor", "factory", "bridge", "beach", "storm", "rain", "wedding", "dance", "music"]


def stock_queries(seg: Seg, job: Job) -> list[str]:
    """Search phrases for a stock-video site, most specific first, built from this slide's narration."""
    speech = clean_text(seg.get("speech") or seg.get("text") or "").lower()
    words = re.findall(r"[a-z]+", speech)
    people = [w for w in dict.fromkeys(words) if w in _STOCK_PEOPLE]
    things = [w for w in dict.fromkeys(words) if w in _STOCK_THINGS]
    place_text = (clean_text(job.get("title")) + " " + clean_text((job.get("location") or {}).get("name"))).lower()
    ph = any(k in place_text or k in speech for k in ("philippin", "iloilo", "zamboanga", "visayas", "mindanao", "ilonggo", "panay", "manila", "cebu"))
    core = (people[:1] + things[:2]) or things[:2] or people[:2]
    if not core:
        # nothing concrete in this sentence: use what the whole article is about
        wide = re.findall(r"[a-z]+", (place_text + " " + clean_text((job.get("location") or {}).get("description")).lower()))
        core = ([w for w in dict.fromkeys(wide) if w in _STOCK_PEOPLE][:1] + [w for w in dict.fromkeys(wide) if w in _STOCK_THINGS][:2])
    if not core:
        return []          # nothing concrete to search for: keep the still picture rather than a random clip
    out = []
    if ph:
        out.append("philippines " + " ".join(core[:2]))
    out.append(" ".join(core[:2]))
    if len(core) > 1:
        out.append(core[0])
    return list(dict.fromkeys(out))


def _pexels_search(query: str) -> list[Job]:
    r = requests.get("https://api.pexels.com/videos/search",
                     params={"query": query, "per_page": 15, "orientation": "landscape", "size": "medium"},
                     headers={"Authorization": PEXELS_API_KEY, "User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json().get("videos") or []


def _pick_file(video: Job) -> Job | None:
    """The mp4 closest to 1280 px wide (sharp enough, not huge)."""
    files = [f for f in video.get("video_files") or []
             if f.get("file_type") == "video/mp4" and f.get("link") and 800 <= int(f.get("width") or 0) <= 1920
             and int(f.get("width") or 0) >= int(f.get("height") or 0)]
    return min(files, key=lambda f: abs(int(f["width"]) - 1280)) if files else None


_STOCK_BLOCK = {"jet", "jets", "airplane", "aircraft", "fighter", "helicopter", "drone", "skyscraper", "laptop", "smartphone",
                "spaceship", "rocket", "tank", "missile", "cartoon", "animation", "3d"}


def stock_relevant(text: str, query: str) -> bool:
    """A free stock site matches loosely, so check the clip's own tags/title: it must mention a concrete word from
    the search and nothing that clearly does not belong in a story about people and places.
    A candidate with NO description is rejected under STRICT_MATCH: nothing proves it matches."""
    t = clean_text(text).lower()
    if not t:
        return not STRICT_MATCH
    if any(b in re.findall(r"[a-z0-9]+", t) for b in _STOCK_BLOCK):
        return False
    return _words_match(t, query)


def _pixabay_search(query: str) -> list[Job]:
    r = requests.get("https://pixabay.com/api/videos/",
                     params={"key": PIXABAY_API_KEY, "q": query, "per_page": 15, "safesearch": "true"},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits") or []:
        vids = h.get("videos") or {}
        # small = ~1280x720 (plenty); medium/large are 1080p/4K files that are far too big
        f = next((vids[k] for k in ("small", "tiny", "medium") if (vids.get(k) or {}).get("url")
                  and int(vids[k].get("width") or 0) >= int(vids[k].get("height") or 0)), None)
        if f:
            out.append({"id": "px%s" % h.get("id"), "duration": h.get("duration"), "link": f["url"], "size": int(f.get("size") or 0),
                        "who": h.get("user"), "page": h.get("pageURL", ""),
                        "text": f"{h.get('tags', '')} {(h.get('pageURL') or '').rstrip('/').rsplit('/', 1)[-1].replace('-', ' ')}"})
    return out


def _pexels_candidates(query: str) -> list[Job]:
    out = []
    for v in _pexels_search(query):
        f = _pick_file(v)
        if f:
            out.append({"id": v.get("id"), "duration": v.get("duration"), "link": f["link"],
                        "who": (v.get("user") or {}).get("name"), "page": v.get("url", ""),
                        "text": (v.get("url") or "").rstrip("/").rsplit("/", 1)[-1].replace("-", " ")})
    return out


def stock_sources() -> list:
    src = []
    if PEXELS_API_KEY:
        src.append(("Pexels", _pexels_candidates))
    if PIXABAY_API_KEY:
        src.append(("Pixabay", _pixabay_search))
    return src


def fetch_stock_clip(seg: Seg, job: Job, used: set, out_mp4: Path) -> str | None:
    """Download one free stock clip that matches this slide, or None (the slide then keeps its still picture)."""
    if not STOCK_VIDEO:
        return None
    sources = stock_sources()
    for q in plan_queries(seg, job, stock_queries(seg, job)):
        for name, search in sources:
            try:
                for v in search(q):
                    if v["id"] in used or not (3 <= float(v.get("duration") or 0) <= 60):
                        continue
                    if not stock_relevant(v.get("text", ""), q):
                        continue
                    if conflict_mismatch(v.get("text", ""), seg.get("speech") or "", job) or plan_rejects(v.get("text", ""), seg, job):
                        continue
                    if STOCK_REQUIRE_REGION and _is_ph_job(job) and not _mentions_ph(v.get("text", "")):
                        continue              # generic non-Filipino footage would contradict the narration
                    if v.get("size") and v["size"] > STOCK_MAX_MB * 1048576:
                        continue              # too big: skip before downloading anything
                    with requests.get(v["link"], stream=True, timeout=120, headers={"User-Agent": UA}) as r:
                        r.raise_for_status()
                        size = 0
                        with open(out_mp4, "wb") as fh:
                            for chunk in r.iter_content(1 << 20):
                                size += len(chunk)
                                if size > STOCK_MAX_MB * 1048576:
                                    raise RuntimeError("clip too large")
                                fh.write(chunk)
                    used.add(v["id"])
                    CREDITS.append(f"Stock video '{q}' - {v.get('who') or 'unknown'} via {name} {v.get('page', '')}")
                    return str(out_mp4)
            except Exception as e:
                log(f"  stock video '{q}' ({name}) not used ({str(e)[:90]})")
    return None


_YEAR_RE = re.compile(r"\b(1[5-9]\d\d)s?\b")
_OK_LICENSE = ("publicdomain", "creativecommons.org/publicdomain", "creativecommons.org/licenses/by", "cc0")


_CONFLICT_WORDS = {"coast", "guard", "navy", "naval", "military", "army", "shoal", "collision", "cannon", "attack", "clash", "clashes",
                   "standoff", "blockade", "warship", "troops", "protest", "riot", "china", "chinese", "pla", "resupply", "mission",
                   "disaster", "typhoon", "earthquake", "fire",
                   "committee", "congress", "senate", "hearing", "session", "representatives", "politician", "president", "mayor",
                   "election", "campaign", "conference", "interview", "news", "broadcast", "youtube", "thumbnail", "screenshot",
                   "poster", "logo", "text", "cartoon", "meme", "infographic", "slide", "diagram", "map", "flag", "religion",
                   "bible", "symbol", "doctrine", "church", "ceremony"}

# Words that signal footage of some other migration/place (Ellis Island, Atlantic crossings, ...). A candidate that
# mentions one of these, or any place in _WORLD_PLACES, is rejected unless the article itself mentions it.
_FOREIGN_HINTS = ["ellis island", "ellis", "european", "europeans", "emigrants", "immigrants", "immigrant", "steerage",
                  "atlantic", "transatlantic", "pilgrims", "pioneers", "wagon", "covered wagon", "gold rush", "prairie",
                  "irish", "italian", "german", "polish", "jewish", "victorian", "medieval", "viking"]


def _norm_words(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z]+", clean_text(text).lower())) + " "


def foreign_mismatch(text: str, job: Job) -> bool:
    """True when the candidate's own description names a foreign place/migration the article never mentions."""
    t = _norm_words(text)
    article = _norm_words((job.get("title") or "") + " " + clean_text(extract_main(job.get("body")))[:30000])
    for p in _WORLD_PLACES + _FOREIGN_HINTS:
        key = _norm_words(p)
        if key in t and key not in article:
            return True
    return False


def conflict_mismatch(text: str, speech: str, job: Job | None = None) -> bool:
    """True when a clip/photo's own description is about a confrontation, military or disaster event that the narration
    and article are not about (e.g. a modern coast-guard clash shown under a sentence about crew size), or is dated after
    the era of a historical story, or names a foreign place/migration the article never mentions."""
    t = set(re.findall(r"[a-z]+", clean_text(text).lower()))
    ctx = set(re.findall(r"[a-z]+", clean_text(speech).lower()))
    if job is not None:
        ctx |= set(re.findall(r"[a-z]+", clean_text((job.get("title") or "") + " " + (job.get("body") or "")[:3000]).lower()))
    if (t & _CONFLICT_WORDS) - ctx:
        return True
    if job is not None and foreign_mismatch(text, job):
        return True
    if job is not None and is_historical({}, job):
        years = [int(y) for y in re.findall(r"\b(20\d\d)\b", clean_text(text))]
        if years:
            return True
    return False


# ---------- AI planner / judge (free Cloudflare text model) ----------
_LLM_CALLS = [0]
_LLM_DEAD = [False]
_PLAN_CACHE: dict = {}


def llm_text(system: str, user: str, max_tokens: int = 160) -> str | None:
    if not LLM_PLAN or _LLM_DEAD[0] or not (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN) or _LLM_CALLS[0] >= LLM_MAX_CALLS:
        return None
    _LLM_CALLS[0] += 1
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/ai/run/{LLM_MODEL}",
            headers={"Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}"},
            json={"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                  "max_tokens": max_tokens, "temperature": 0.1}, timeout=45)
        if not r.ok:
            low = (r.text or "").lower()
            if r.status_code != 429 or any(k in low for k in ("neurons", "quota", "daily", "4006")):
                _LLM_DEAD[0] = True
                log(f"  AI planner off for this run (HTTP {r.status_code}); using built-in rules")
            return None
        return str((r.json().get("result") or {}).get("response") or "")
    except Exception as e:
        log(f"  AI planner call failed ({str(e)[:80]})")
        return None


def slide_plan(seg: Seg, job: Job) -> Job:
    """{'queries': [...], 'avoid': [...]} for this slide's narration, or {} when the AI planner is unavailable."""
    speech = clean_text(seg.get("speech") or seg.get("text") or "")
    if speech in _PLAN_CACHE:
        return _PLAN_CACHE[speech]
    loc = job.get("location") or {}
    ctx = f"Article: {clean_text(job.get('title'))}. Place: {clean_text(loc.get('name'))}. Era: {clean_text(loc.get('era'))}."
    out = llm_text(
        "You choose stock photo/video search terms for a narrated documentary. Reply with JSON only: "
        '{"queries": [2 to 3 short searches of 2-5 plain words describing exactly what the camera should show, '
        'naming the people (e.g. Filipino fishermen) and place when relevant], '
        '"avoid": [up to 8 single words for things that must NOT appear, e.g. military, jet, skyline, cartoon]}. '
        "If the sentence is abstract, describe the article's everyday scene instead.",
        f"{ctx}\nNarration: {speech[:400]}")
    plan: Job = {}
    if out:
        m = re.search(r"\{.*\}", out, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
            qs = [clean_text(q).lower() for q in (d.get("queries") or []) if isinstance(q, str) and 2 <= len(q.split()) <= 7][:3]
            av = [w for a in (d.get("avoid") or []) if isinstance(a, str) for w in re.findall(r"[a-z]{3,}", a.lower())][:10]
            if qs:
                plan = {"queries": qs, "avoid": av}
        except Exception:
            plan = {}
    _PLAN_CACHE[speech] = plan
    return plan


def plan_queries(seg: Seg, job: Job, rules: list[str]) -> list[str]:
    return list(dict.fromkeys(slide_plan(seg, job).get("queries", []) + rules))[:5]


def plan_rejects(text: str, seg: Seg, job: Job) -> bool:
    """True when the candidate's own words hit this slide's 'avoid' list, or the AI judge does not clearly say YES."""
    plan = slide_plan(seg, job)
    words = set(re.findall(r"[a-z]+", clean_text(text).lower()))
    if words & set(plan.get("avoid", [])):
        return True
    if not plan or not clean_text(text):
        return False
    ans = llm_text("Answer only YES or NO.",
                   f"Narration: {clean_text(seg.get('speech') or '')[:300]}\nArticle: {clean_text(job.get('title'))}\n"
                   f"Candidate picture description: {clean_text(text)[:300]}\n"
                   "Does this picture clearly show what the narration describes, in the right country and era? "
                   "Answer NO if it shows a different country, culture, era or event, or if you are unsure.",
                   max_tokens=4)
    if ans is None:
        return False            # judge unavailable: the stricter word and place checks above have already decided
    return not ans.strip().upper().startswith("YES")   # only a clear YES passes


def is_historical(seg: Seg, job: Job) -> bool:
    """True when the story is set before 2000 (a year or decade in the title, place details or this sentence)."""
    loc = job.get("location") or {}
    text = " ".join(clean_text(x) for x in (job.get("title"), loc.get("name"), loc.get("era"), loc.get("description"),
                                             seg.get("speech") or seg.get("text") or ""))
    return any(int(y) < 2000 for y in _YEAR_RE.findall(text))


def _mentions_ph(text: str) -> bool:
    """Strict: only unambiguous Philippine words count (see _PH_MATCH_PLACES; no 'Antique', 'Naga', 'Roxas', ...)."""
    places = "|".join(re.escape(p) for p in _PH_MATCH_PLACES)
    return bool(re.search(r"philippin|filipino|pilipin|\b(" + places + r")\b", clean_text(text), re.I))


def _is_ph_job(job: Job) -> bool:
    loc = job.get("location") or {}
    return _mentions_ph(" ".join(clean_text(x) for x in (job.get("title"), loc.get("name"), (job.get("body") or "")[:4000])))


def archive_queries(seg: Seg, job: Job) -> list[str]:
    """Plain search words for an archive: this slide's concrete things, with the country added for Philippine stories."""
    ph = _is_ph_job(job)
    out = []
    for q in plan_queries(seg, job, stock_queries(seg, job)):
        q = q.replace("philippines", "").strip()
        if q:
            if ph:
                out.append(f"philippines {q}")
            out.append(q)
    if not out and ph:
        out = ["philippines"]
    return list(dict.fromkeys(out))[:3]


def _words_match(text: str, query: str) -> bool:
    """The clip's own title/description must mention at least one concrete word from the query."""
    t = clean_text(text).lower()
    keys = [w for w in re.findall(r"[a-z]+", query.lower()) if w != "philippines" and len(w) > 3]
    if not keys:
        return True
    hits = sum(1 for k in keys if k[:4] in t)   # 4-letter stems: fisher/fishing, boat/boats
    return hits >= (2 if (STRICT_MATCH and len(keys) >= 2) else 1)


def _commons_video_search(query: str) -> list[Job]:
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=30, params={
        "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6, "gsrlimit": 10,
        "gsrsearch": f"{query} filetype:video", "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata"})
    r.raise_for_status()
    out = []
    for pg in ((r.json().get("query") or {}).get("pages") or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}
        lic = (meta.get("LicenseShortName") or {}).get("value", "")
        if not ii.get("url") or not lic or not (lic.lower().startswith(("cc", "public domain", "pd"))):
            continue
        desc = (meta.get("ImageDescription") or {}).get("value", "")
        out.append({"id": f"commons:{pg.get('pageid')}", "link": ii["url"], "size": ii.get("size") or 0,
                    "text": f"{pg.get('title', '')} {desc}", "who": clean_text((meta.get("Artist") or {}).get("value", "")) or "unknown",
                    "lic": lic, "page": ii.get("descriptionurl", "")})
    return out


def _ia_video_search(query: str) -> list[Job]:
    q = (f'({query}) AND mediatype:movies AND (licenseurl:*publicdomain* OR licenseurl:*creativecommons* '
         f'OR collection:prelinger)')
    r = requests.get("https://archive.org/advancedsearch.php", headers={"User-Agent": UA}, timeout=30, params={
        "q": q, "fl[]": ["identifier", "title", "description", "creator", "licenseurl"], "rows": 8, "output": "json"})
    r.raise_for_status()
    out = []
    for d in (r.json().get("response") or {}).get("docs") or []:
        ident = d.get("identifier")
        if not ident:
            continue
        m = requests.get(f"https://archive.org/metadata/{ident}", headers={"User-Agent": UA}, timeout=30)
        m.raise_for_status()
        files = [f for f in (m.json().get("files") or [])
                 if str(f.get("name", "")).lower().endswith((".mp4", ".ogv", ".webm")) and int(f.get("size") or 0) > 0]
        if not files:
            continue
        f = min(files, key=lambda f: int(f["size"]))          # the smallest copy is plenty for a few seconds
        lic = d.get("licenseurl") or "no known copyright restrictions (Prelinger Archives)"
        if isinstance(lic, list):
            lic = lic[0]
        desc = d.get("description") or ""
        out.append({"id": f"ia:{ident}", "link": f"https://archive.org/download/{ident}/{f['name']}", "size": int(f["size"]),
                    "text": f"{d.get('title', '')} {' '.join(desc) if isinstance(desc, list) else desc}",
                    "who": d.get("creator") if isinstance(d.get("creator"), str) else "Internet Archive",
                    "lic": lic, "page": f"https://archive.org/details/{ident}"})
    return out


def _cut_clip(src: Path, out_mp4: Path) -> bool:
    """A short, small, silent mp4 from the middle-ish of a long old film (skips title cards at the start)."""
    total = probe_duration(src)
    if total < 3:
        return False
    length = min(ARCHIVE_CLIP_SEC, total)
    start = max(0.0, min(total * 0.15, total - length))
    run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", str(src), "-an",
         "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p",
         str(out_mp4)])
    return out_mp4.exists() and out_mp4.stat().st_size > 5000


def fetch_archive_clip(seg: Seg, job: Job, used: set, out_mp4: Path) -> str | None:
    """A few seconds of real archival film that matches this slide, or None."""
    if not (ARCHIVE_VIDEO and (ARCHIVE_ANY_ERA or is_historical(seg, job))):
        return None
    ph_job = _is_ph_job(job)
    for q in archive_queries(seg, job):
        for name, search in (("Wikimedia Commons", _commons_video_search), ("Internet Archive", _ia_video_search)):
            try:
                for v in search(q):
                    if v["id"] in used or not stock_relevant(v["text"], q):
                        continue
                    if conflict_mismatch(v["text"], seg.get("speech") or "", job) or plan_rejects(v["text"], seg, job):
                        continue
                    if ph_job and not _mentions_ph(v["text"]):
                        continue          # a Philippine story needs footage that says it is from the Philippines
                    if v["size"] and v["size"] > ARCHIVE_MAX_MB * 1048576:
                        continue
                    raw = out_mp4.with_suffix(".raw")
                    with requests.get(v["link"], stream=True, timeout=180, headers={"User-Agent": UA}) as r:
                        r.raise_for_status()
                        size = 0
                        with open(raw, "wb") as fh:
                            for chunk in r.iter_content(1 << 20):
                                size += len(chunk)
                                if size > ARCHIVE_MAX_MB * 1048576:
                                    raise RuntimeError("file too large")
                                fh.write(chunk)
                    ok = _cut_clip(raw, out_mp4)
                    raw.unlink(missing_ok=True)
                    if not ok:
                        continue
                    used.add(v["id"])
                    CREDITS.append(f"Archival film - {clean_text(v.get('who')) or 'unknown'} ({v.get('lic')}) via {name} {v.get('page', '')}")
                    return str(out_mp4)
            except Exception as e:
                log(f"  archival film '{q}' ({name}) not used ({str(e)[:90]})")
    return None


# ---------- per-slide real photographs ----------
_PH_TERMS = {"fisherman": "filipino fisherman", "fishermen": "filipino fishermen", "fishers": "filipino fishermen",
             "fisherfolk": "filipino fishermen", "boat": "bangka outrigger boat", "boats": "bangka outrigger boats",
             "fishing": "filipino fishing boat", "village": "coastal fishing village", "farmer": "filipino farmer",
             "farmers": "filipino farmers", "market": "filipino market", "church": "filipino church",
             "festival": "filipino festival", "children": "filipino children", "vendor": "filipino vendor",
             "vendors": "filipino vendors", "harbor": "philippine port", "port": "philippine port", "sea": "philippine sea coast",
             "island": "philippine island", "rice": "philippine rice field", "sugarcane": "philippine sugarcane"}
_PHOTO_CACHE: dict = {}
_PHOTO_CALLS = [0]
STORYBOARD: list = []


def photo_queries(seg: Seg, job: Job) -> list[str]:
    base = stock_queries(seg, job)
    if not base:
        return []
    out = []
    if _is_ph_job(job):
        speech = clean_text(seg.get("speech") or seg.get("text") or "").lower()
        words = re.findall(r"[a-z]+", speech)
        for w in dict.fromkeys(words):
            if w in _PH_TERMS:
                out.append(_PH_TERMS[w])
            if len(out) >= 2:
                break
    out += [q for q in base if q]
    return list(dict.fromkeys(out))[:4]


def _unsplash_photos(query: str) -> list[Job]:
    if not UNSPLASH_ACCESS_KEY:
        return []
    r = requests.get("https://api.unsplash.com/search/photos",
                     params={"query": query, "per_page": 10, "orientation": "landscape", "content_filter": "high"},
                     headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}", "Accept-Version": "v1", "User-Agent": UA}, timeout=30)
    r.raise_for_status()
    out = []
    for h in r.json().get("results") or []:
        u = (h.get("urls") or {}).get("regular")
        if not u:
            continue
        tags = " ".join(t.get("title", "") for t in (h.get("tags") or []) if isinstance(t, dict))
        loc = (h.get("location") or {}) if isinstance(h.get("location"), dict) else {}
        out.append({"id": "us" + str(h.get("id")), "url": u,
                    "text": f"{h.get('description') or ''} {h.get('alt_description') or ''} {tags} {loc.get('name') or ''}",
                    "who": (h.get("user") or {}).get("name") or "unknown", "src": "Unsplash",
                    "page": (h.get("links") or {}).get("html", ""),
                    "track": (h.get("links") or {}).get("download_location", "")})
    return out


def _pixabay_photos(query: str) -> list[Job]:
    if not PIXABAY_API_KEY:
        return []
    r = requests.get("https://pixabay.com/api/",
                     params={"key": PIXABAY_API_KEY, "q": query, "per_page": 12, "image_type": "photo",
                             "orientation": "horizontal", "safesearch": "true", "min_width": 1000},
                     headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    out = []
    for h in r.json().get("hits") or []:
        u = h.get("largeImageURL") or h.get("webformatURL")
        if u:
            out.append({"id": "pp%s" % h.get("id"), "url": u, "who": h.get("user") or "unknown", "src": "Pixabay",
                        "page": h.get("pageURL", ""), "track": "",
                        "text": f"{h.get('tags', '')} {(h.get('pageURL') or '').rstrip('/').rsplit('/', 1)[-1].replace('-', ' ')}"})
    return out


def _commons_photos(query: str) -> list[Job]:
    out = []
    for it in wiki_search(query, 10):
        out.append({"id": "wc" + it["url"], "url": it["url"], "who": it["artist"] or "unknown", "src": "Wikimedia Commons",
                    "page": it["page"], "track": "", "text": it["title"].replace("File:", "").replace("_", " ")})
    return out


def fetch_slide_photo(seg: Seg, job: Job, used: set):
    """A real photograph whose own title/tags mention what THIS slide's narration describes, or None.
    On Philippine stories EVERY source (Unsplash, Pixabay, Commons) must name the Philippines or a Philippine place."""
    if not SLIDE_PHOTOS:
        return None
    ph = _is_ph_job(job)
    for q in plan_queries(seg, job, photo_queries(seg, job)):
        for fn in (_unsplash_photos, _pixabay_photos, _commons_photos):
            key = (fn.__name__, q)
            if key not in _PHOTO_CACHE:
                if _PHOTO_CALLS[0] >= PHOTO_MAX_SEARCHES:
                    continue
                _PHOTO_CALLS[0] += 1
                try:
                    _PHOTO_CACHE[key] = fn(q)
                except Exception as e:
                    log(f"  photo search '{q}' ({fn.__name__.strip('_')}) failed ({str(e)[:80]})")
                    _PHOTO_CACHE[key] = []
            for c in _PHOTO_CACHE[key]:
                if c["id"] in used or not stock_relevant(c["text"], q) or conflict_mismatch(c["text"], seg.get("speech") or "", job) or plan_rejects(c["text"], seg, job):
                    continue
                if ph and not _mentions_ph(c["text"] + " " + c["page"]):
                    continue
                img = load_cover(c["url"])
                if img is None or img.width < 800 or img.height < 450:
                    continue
                if c.get("track"):
                    try:       # Unsplash guideline: register the download
                        requests.get(c["track"], headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}", "User-Agent": UA}, timeout=20)
                    except Exception:
                        pass
                used.add(c["id"])
                CREDITS.append(f"Photo by {c['who']} via {c['src']} {c['page']}")
                return img, f"{c['src']}: {q}"
    return None


def pick_kling_slides(segs: list[Seg], n: int) -> set[int]:
    """Choose up to n body slides to animate, spread across the whole video.
    Slides whose narration mentions people come first, because that is where movement shows."""
    body = [i for i, g in enumerate(segs) if g["kind"] == "body" and not g.get("is_heading")]
    if n <= 0 or not body:
        return set()
    people = [i for i in body if _PEOPLE_RE.search(segs[i].get("speech", ""))]
    pool = sorted(people if len(people) >= n else people + [i for i in body if i not in people][: n - len(people)])
    if len(pool) <= n:
        return set(pool)
    return {pool[round(k * (len(pool) - 1) / (n - 1))] if n > 1 else pool[len(pool) // 2] for k in range(n)}


def build_video(job):
    global RATE, ARCHIVE_VIDEO, STOCK_VIDEO
    # Real footage is opt-in per article ("footage": true in the job file) unless FOOTAGE_ALL=1.
    footage_ok = bool(job.get("footage")) or FOOTAGE_ALL
    ARCHIVE_VIDEO = _ARCHIVE_ENV and footage_ok
    STOCK_VIDEO = _STOCK_ENV and footage_ok
    if (_ARCHIVE_ENV or _STOCK_ENV) and not footage_ok:
        log("  real footage skipped for this article (add \"footage\": true to its job file to allow it)")
    segs = build_segments(job)
    RATE = pick_rate(segs)
    log(f"  {len(segs)} slides, narration rate {RATE}")
    tmp = Path(tempfile.mkdtemp(prefix="vid_"))
    CREDITS.clear()
    CREDIT_ROWS.clear()
    QUOTA_HIT[0] = False
    FALLBACK_STATE.update(fails=0, dead=False, used=0, announced=False)
    photos = load_photos(job)
    PROFILE[0] = load_profile(job)
    load_user_clips(job, tmp)
    log("  profile picture for the introduction: " + ("found" if PROFILE[0] is not None else "not found (put profile.jpg in the repo root)"))
    if WIKI_GENERIC:
        photos += load_wiki_photos(job, len(photos))
    if CREDIT_ROWS and CREDITS_CARD:
        # Visible attribution for CC-BY / CC-BY-SA images: a short spoken and captioned card before the end card.
        seen, bits = set(), []
        for artist, lic in CREDIT_ROWS:
            who = re.sub(r"\s+", " ", artist or "").strip()[:40] or "unknown author"
            key = (who.lower(), lic)
            if key in seen:
                continue
            seen.add(key)
            bits.append(f"{who}, {lic}" if lic else who)
            if len(bits) >= 8:
                break
        credit_speech = ("Photographs courtesy of Wikimedia Commons. Credits: " + "; ".join(bits)
                         + ". Full credits are in the video description.")
        segs.insert(len(segs) - 1, {"kind": "credits", "speech": credit_speech})
    if photos and len(photos) < 4:
        log(f"  only {len(photos)} different picture(s) found; adding different framings of the first one")
        photos = photos + make_variants(photos[0], 6)
    ai = make_ai_images(segs, job)
    body_total = sum(1 for g in segs if g["kind"] == "body")

    engines, mp3s, est = set(), [], 0.0
    for i, seg in enumerate(segs):
        mp3 = tmp / f"a{i}.mp3"
        engines.add(synth(seg["speech"], str(mp3)))
        mp3s.append(mp3)
        est += probe_duration(mp3) + 0.7
    vkbps = pick_bitrate(est)
    log(f"  narration {est:.0f}s; video bitrate {vkbps} kbps to stay near {MAX_MB:.0f} MB")

    if LLM_PLAN:
        log("  AI planner on (" + LLM_MODEL + ")" if (CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN) else "  AI planner off: no Cloudflare secrets")
    photo_used = set()
    if SLIDE_PHOTOS:
        log("  slide photos on (" + " + ".join(n for n, k in (("Unsplash", UNSPLASH_ACCESS_KEY), ("Pixabay", PIXABAY_API_KEY), ("Wikimedia", True)) if k)
            + f"), up to {PHOTO_MAX_SEARCHES} searches")
    clips, total_dur, body_seen, ai_used = [], 0.0, 0, {}
    last_pic = None
    kling_used, kling_t0 = 0, time.time()
    kling_slides = pick_kling_slides(segs, KLING_MAX_CLIPS) if (KLING_ENABLED and KLING_API_KEY) else set()
    stock_slides, stock_used, stock_count = set(), set(), 0
    if ARCHIVE_VIDEO:
        stock_slides = pick_kling_slides(segs, STOCK_MAX_CLIPS)
        log("  archival film on (Wikimedia Commons + Internet Archive) for slides set before 2000")
    if STOCK_VIDEO:
        names = [n for n, _ in stock_sources()]
        if not names:
            log("  STOCK_VIDEO is on but there is no PEXELS_API_KEY or PIXABAY_API_KEY secret - using still pictures")
        else:
            stock_slides = stock_slides or pick_kling_slides(segs, STOCK_MAX_CLIPS)
            log(f"  free stock footage on ({' + '.join(names)}): up to {len(stock_slides)} moving slides")
    if KLING_ENABLED:
        if not KLING_API_KEY:
            log("  KLING_ENABLED but no KLING_API_KEY / FAL_KEY / PIAPI_API_KEY — using still motion only")
        else:
            log(f"  Kling image-to-video on ({KLING_PROVIDER}), max {KLING_MAX_CLIPS} clips")

    for i, seg in enumerate(segs):
        bgp, ovp, clip = tmp / f"b{i}.png", tmp / f"o{i}.png", tmp / f"c{i}.mp4"
        bgp2 = tmp / f"b{i}b.png"
        kling_mp4 = tmp / f"k{i}.mp4"
        cover = framing(photos[i % len(photos)], i // len(photos)) if photos else None
        if seg["kind"] == "body":
            if STRICT_MATCH:
                cover = None          # no loosely related photo: only an AI image of this slide or a photo that matched it
            if ai:
                gi = body_seen * len(ai) // max(body_total, 1)
                pic = ai[gi] if gi < len(ai) else None
                if pic is None:
                    pic = last_pic          # quota or a failure: keep the previous picture rather than a blank card
                if pic is not None:
                    last_pic = pic
                    cover = pic
                    ai_used[gi] = ai_used.get(gi, 0) + 1
            if USER_PHOTOS:
                # the author's own pictures win over generated ones: cycle through them, each reuse in a new framing
                cover = framing(USER_PHOTOS[body_seen % len(USER_PHOTOS)], body_seen // len(USER_PHOTOS))
            body_seen += 1
            src_note = "AI image" if (ai and cover is not None) else ("generic photo" if cover is not None else "no picture matched: text card")
            sp = fetch_slide_photo(seg, job, photo_used)
            if sp:
                cover, src_note = sp
            STORYBOARD.append((i, src_note, clean_text(seg.get("speech") or "")[:90]))
            _pl = slide_plan(seg, job)
            log(f"  storyboard slide {i}: [{src_note}] {clean_text(seg.get('speech') or '')[:90]}"
                + (f" | AI search: {', '.join(_pl.get('queries', [])[:2])} | avoid: {', '.join(_pl.get('avoid', [])[:5])}" if _pl else ""))
        elif seg.get("kind") == "intro":
            cover = photos[0] if photos else (PROFILE[0].convert("RGB") if PROFILE[0] is not None else None)   # the article's cover image (profile picture if none); no words on it
        elif photos:
            cover = photos[0]

        frame_a, frame_b = motion_pair(cover) if cover is not None else (None, None)
        if frame_a is None and cover is not None:
            frame_a = cover
        bg_img, ov_img = render_layers(seg, i, len(segs), frame_a)
        bg_img.save(bgp)
        ov_img.save(ovp)

        spoken = probe_duration(mp3s[i])
        caps = []
        no_caps = seg.get("kind") == "intro" and os.environ.get("INTRO_CAPTIONS", "0") != "1"   # opening: cover picture + narration only, no text
        for k, (txt, t0, t1) in enumerate([] if no_caps else caption_timings(seg.get("caption") or seg["speech"], spoken)):
            cp = tmp / f"cap{i}_{k}.png"
            render_caption(txt).save(cp)
            caps.append((cp, t0, t1))

        used_kling = False
        if (
            KLING_ENABLED and KLING_API_KEY
            and i in kling_slides
            and cover is not None
            and (time.time() - kling_t0) < KLING_BUDGET
        ):
            mprompt = motion_prompt(seg, job)
            # Match clip length to narration (clamped)
            kdur = int(min(10, max(5, round(spoken) or KLING_DURATION)))
            got = gen_kling_clip(cover, mprompt, kdur, kling_mp4)
            if got and Path(got).exists() and Path(got).stat().st_size > 5000:
                total_dur += make_clip_from_video(got, ovp, mp3s[i], clip, caps, vkbps=vkbps)
                used_kling = True
                kling_used += 1
                Path(got).unlink(missing_ok=True)

        if not used_kling and USER_CLIPS and seg.get("kind") == "body" and (not USER_PHOTOS or (body_seen - 1) % 2 == 0):
            # the author's own short clips: cycle through them under the narration (short clips ping-pong)
            ucl = USER_CLIPS[((body_seen - 1) // (2 if USER_PHOTOS else 1)) % len(USER_CLIPS)]
            try:
                total_dur += make_clip_from_video(ucl, ovp, mp3s[i], clip, caps, vkbps=vkbps)
                used_kling = True
            except Exception as e:
                log(f"  supplied clip failed on slide {i} ({str(e)[:80]}); using a still picture")

        if not used_kling and i in stock_slides:
            got = fetch_archive_clip(seg, job, stock_used, tmp / f"s{i}.mp4") or fetch_stock_clip(seg, job, stock_used, tmp / f"s{i}.mp4")
            if got and Path(got).exists() and Path(got).stat().st_size > 5000:
                total_dur += make_clip_from_video(got, ovp, mp3s[i], clip, caps, vkbps=vkbps)
                used_kling = True
                stock_count += 1
                Path(got).unlink(missing_ok=True)

        if not used_kling:
            bg2_path = None
            if frame_b is not None and frame_a is not frame_b:
                bg2 = fit_band(frame_b.convert("RGB"))
                bg2.save(bgp2)
                bg2_path = bgp2
            total_dur += make_clip(bgp, ovp, mp3s[i], clip, caps, i, vkbps=vkbps, bg2_png=bg2_path)
            if bg2_path and Path(bg2_path).exists():
                Path(bg2_path).unlink(missing_ok=True)

        clips.append(clip)
        bgp.unlink(missing_ok=True)
        if (i + 1) % 10 == 0 or i + 1 == len(segs):
            log(f"  slide {i + 1}/{len(segs)} ready"
                + (f" (Kling clips so far: {kling_used})" if kling_used else ""))

    if kling_used:
        log(f"  Kling animated {kling_used} slide(s)")
    if stock_count:
        log(f"  moving footage (archival or stock) used on {stock_count} slide(s)")
        log(f"  stock footage used on {stock_count} slide(s)")

    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
    final = tmp / "final.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
         "-c", "copy", "-movflags", "+faststart", str(final)])
    log(f"  final file {final.stat().st_size / 1048576:.1f} MB")
    return final, total_dur, ",".join(sorted(engines))


def _upload_endpoints():
    out = [UPLOAD_API]
    # Extra fallbacks: UPLOAD_FALLBACKS="https://a/api/upload,https://b/api/upload" replaces the built-in list.
    env = [u.strip() for u in os.environ.get("UPLOAD_FALLBACKS", "").split(",") if u.strip()]
    extras = env or [
        "https://poetic-codes.pages.dev/api/upload",
        "https://rhythmic.pansensoyglenn150.workers.dev/api/upload",
        "https://poetic-codes.vercel.app/api/upload",
    ]
    for extra in extras:
        if extra not in out:
            out.append(extra)
    return out


def upload_via_supabase(path, filename):
    r = requests.post(
        VIDEO_URL_API, params={"filename": filename},
        headers={"X-Admin-Key": ADMIN_KEY}, timeout=60,
    )
    if r.status_code == 401:
        raise RuntimeError("Upload rejected (401): the ADMIN_KEY secret is wrong or missing.")
    if not r.ok:
        raise RuntimeError(f"video-upload-url: HTTP {r.status_code} {(r.text or '')[:400]}")
    info = r.json()
    with open(path, "rb") as fh:
        put = requests.put(
            info["uploadUrl"], data=fh, timeout=1800,
            headers={"Content-Type": "video/mp4", "x-upsert": "false"},
        )
    if not put.ok:
        raise RuntimeError(f"Supabase upload: HTTP {put.status_code} {(put.text or '')[:200]}")
    return info["url"]


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
    size_mb = os.path.getsize(path) / 1048576
    if size_mb > 95:
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


# YouTube auto-upload (optional). Turns on only when all three secrets exist; uses plain requests, no new packages.
YT_CLIENT_ID = os.environ.get("YT_CLIENT_ID", "").strip()
YT_CLIENT_SECRET = os.environ.get("YT_CLIENT_SECRET", "").strip()
YT_REFRESH_TOKEN = os.environ.get("YT_REFRESH_TOKEN", "").strip()
YT_PRIVACY = os.environ.get("YT_PRIVACY", "private").strip().lower()   # private | unlisted | public
YT_CATEGORY = os.environ.get("YT_CATEGORY", "27")                      # 27 = Education
YT_ENABLED = bool(YT_CLIENT_ID and YT_CLIENT_SECRET and YT_REFRESH_TOKEN) and os.environ.get("YT_UPLOAD", "1") != "0"


def youtube_seo(job, title, desc, row_tags=None):
    """Search-friendly YouTube title, description with hashtags, and tags. Uses the free Cloudflare AI when
    available, otherwise simple rules from the article's own title, category and tags. Never invents facts."""
    body = clean_text(extract_main(job.get("body")))[:3000]
    category = clean_text(job.get("category"))
    base_tags = [clean_text(t) for t in (row_tags or []) if clean_text(t)]
    ai = {}
    raw = llm_text(
        "You write YouTube metadata for a documentary-style essay video. Use ONLY facts in the text. Reply with JSON only: "
        '{"title": "clear search-friendly title, max 90 characters, main keyword first, no clickbait, no all caps", '
        '"summary": "2-3 sentence description of what the video covers", '
        '"tags": ["10-15 search phrases people would type, 1-3 words each"], '
        '"hashtags": ["3-5 relevant single-word or CamelCase hashtags without the # sign"]}',
        f"Title: {title}\nCategory: {category}\nText: {body}", max_tokens=420)
    if raw:
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            ai = json.loads(m.group(0)) if m else {}
        except Exception:
            ai = {}
    yt_title = clean_text(ai.get("title")) if isinstance(ai.get("title"), str) else ""
    if not (10 <= len(yt_title) <= 100):
        yt_title = title
    summary = clean_text(ai.get("summary")) if isinstance(ai.get("summary"), str) else ""
    tags = [clean_text(t) for t in (ai.get("tags") or []) if isinstance(t, str)] + base_tags + [category, "Poetic Codes", "essay", "documentary"]
    seen, out, total = set(), [], 0
    for t in tags:
        t = re.sub(r"[<>,]", "", t).strip()
        if t and t.lower() not in seen and total + len(t) + 1 <= 450:
            seen.add(t.lower()); out.append(t); total += len(t) + 1
    hs = []
    for h in (ai.get("hashtags") or []) + [category, "PoeticCodes"]:
        if isinstance(h, str):
            h = re.sub(r"[^A-Za-z0-9]", "", "".join(w[:1].upper() + w[1:] for w in clean_text(h).split()))
            if h and h.lower() not in [x.lower() for x in hs]:
                hs.append(h)
    hs = hs[:5]
    tagline = " ".join("#" + h for h in hs)
    new_desc = (summary + "\n\n" if summary else "") + desc + ("\n\n" + tagline if tagline else "")
    return yt_title, new_desc, out


def upload_to_youtube(path, title, description, tags=None):
    """Upload the finished video to YouTube. Returns the video id. Raises on failure (caller logs and carries on)."""
    tok = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": YT_CLIENT_ID, "client_secret": YT_CLIENT_SECRET,
        "refresh_token": YT_REFRESH_TOKEN, "grant_type": "refresh_token"}, timeout=60)
    if not tok.ok:
        raise RuntimeError(f"YouTube sign-in failed ({tok.status_code}): {tok.text[:200]}")
    access = tok.json()["access_token"]
    privacy = YT_PRIVACY if YT_PRIVACY in ("private", "unlisted", "public") else "private"
    clean = lambda s, n: re.sub(r"[<>]", "", s or "").strip()[:n]
    meta = {
        "snippet": {"title": clean(title, 100) or "Poetic Codes", "description": clean(description, 4900),
                    "tags": [clean(t, 30) for t in (tags or []) if clean(t, 30)][:15], "categoryId": YT_CATEGORY},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    size = os.path.getsize(path)
    start = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": "Bearer " + access, "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
        json=meta, timeout=60)
    if not start.ok:
        raise RuntimeError(f"YouTube refused the upload ({start.status_code}): {start.text[:300]}")
    with open(path, "rb") as fh:
        up = requests.put(start.headers["Location"], data=fh,
                          headers={"Content-Type": "video/mp4", "Content-Length": str(size)}, timeout=900)
    if not up.ok:
        raise RuntimeError(f"YouTube upload failed ({up.status_code}): {up.text[:300]}")
    return up.json()["id"]


def upload_video(path, filename):
    try:
        try:
            url = upload_via_supabase(path, filename)
            print("  uploaded to Supabase storage")
            return url
        except RuntimeError as e:
            if "401" in str(e)[:60]:
                raise
            print(f"  Supabase route unavailable ({str(e)[:450]}); trying the other upload addresses")
        except Exception as e:
            print(f"  Supabase route failed ({str(e)[:450]}); trying the other upload addresses")
        return upload_to_endpoints(path, filename)
    except RuntimeError as e:
        if "401" in str(e)[:60]:
            raise
        print(f"  upload endpoints failed, saving the video in the repo instead ({str(e)[:120]})")
        return publish_to_repo(path, filename)


_ARTICLES_CACHE = []


def fetch_articles():
    """The article list, fetched once per run (not once per job)."""
    if not _ARTICLES_CACHE:
        _ARTICLES_CACHE.append(_fetch_articles_uncached())
    return _ARTICLES_CACHE[0]


def _fetch_articles_uncached():
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


def find_article(job: Job, rows: list[Job]) -> Job | None:
    aid = job.get("articleId")
    if aid not in (None, ""):
        for r in rows:
            if str(r.get("id")) == str(aid):
                return r
    t = (job.get("title") or "").strip().lower()
    cands = [r for r in rows if (r.get("title") or "").strip().lower() == t]
    cands.sort(key=lambda r: _num(r.get("id")), reverse=True)
    return cands[0] if cands else None


def article_slug(title: str | None) -> str:
    # Same as slugify() in the portal
    return re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")


def article_page_url(job: Job, row: Job | None = None) -> str:
    """The public static page the portal publishes: https://poetic-codes.pages.dev/articles/<slug>.html"""
    slug = (job.get("slug") or "").strip() or article_slug((row or {}).get("title") or job.get("title"))
    return f"{SITE_URL.rstrip('/')}/articles/{slug}.html" if slug else ""


def add_to_index_list(article_url):
    """Keep a plain list of article URLs to paste into Search Console > URL Inspection > Request indexing."""
    if not article_url:
        return
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    f = JOBS_DIR / "to-index.txt"
    have = f.read_text(encoding="utf-8").split() if f.exists() else []
    if article_url not in have:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(article_url + "\n")


_PH_PLACES = ["Iloilo", "Zamboanga", "Sibugay", "Talon-Talon", "Naga", "Estancia", "Panay", "Negros", "Guimaras", "Cebu",
              "Manila", "Mindanao", "Visayas", "Luzon", "Davao", "Bacolod", "Antique", "Capiz", "Aklan", "Cotabato", "Sulu",
              "Basilan", "Dumaguete", "Bohol", "Leyte", "Samar", "Palawan", "Batangas", "Pampanga", "Bicol", "Cagayan",
              "Dipolog", "Pagadian", "Ipil", "Diplahan", "Roxas", "Jaro", "Molo", "Arevalo", "Lapuz", "Kalibo", "Tacloban",
              "Ormoc", "Iligan", "Marawi", "Sipalay", "Guimbal", "Miagao", "Oton"]
# Used only to PROVE a clip/photo is Philippine. Names that also exist elsewhere (Antique, Naga, Roxas, Molo, Jaro,
# Oton, Arevalo, Lapuz, Estancia, Sulu, Samar, Ipil, Roxas, Talon-Talon) are left out on purpose.
_PH_MATCH_PLACES = ["Iloilo", "Zamboanga", "Sibugay", "Panay", "Negros", "Guimaras", "Cebu", "Mindanao", "Visayas", "Luzon",
                    "Davao", "Bacolod", "Capiz", "Aklan", "Cotabato", "Basilan", "Dumaguete", "Bohol", "Leyte", "Palawan",
                    "Batangas", "Pampanga", "Bicol", "Cagayan", "Dipolog", "Pagadian", "Diplahan", "Kalibo", "Tacloban",
                    "Ormoc", "Iligan", "Marawi", "Sipalay", "Guimbal", "Miagao", "General Santos", "Sarangani", "Kidapawan",
                    "Tacurong", "Sultan Kudarat", "Manila"]
_WORLD_PLACES = [
    # Europe
    "Europe", "France", "Paris", "Brittany", "Normandy", "Provence", "Italy", "Rome", "Venice", "Florence", "Naples", "Sicily",
    "Tuscany", "Spain", "Madrid", "Barcelona", "Seville", "Portugal", "Lisbon", "Germany", "Berlin", "Bavaria", "Austria", "Vienna",
    "Switzerland", "Netherlands", "Amsterdam", "Belgium", "Britain", "England", "London", "Scotland", "Wales", "Ireland", "Dublin",
    "Greece", "Athens", "Poland", "Prague", "Hungary", "Budapest", "Sweden", "Norway", "Denmark", "Finland", "Iceland", "Russia", "Moscow",
    # Asia, Middle East, Africa, Americas, Oceania
    "Japan", "Tokyo", "Kyoto", "China", "Beijing", "Shanghai", "Hong Kong", "Korea", "Seoul", "India", "Delhi", "Mumbai", "Vietnam", "Hanoi",
    "Thailand", "Bangkok", "Indonesia", "Java", "Bali", "Malaysia", "Singapore", "Turkey", "Istanbul", "Egypt", "Cairo", "Israel", "Jerusalem",
    "Africa", "Nigeria", "Kenya", "Morocco", "South Africa", "Mexico", "Brazil", "Peru", "Argentina", "Cuba", "Canada", "America",
    "United States", "New York", "California", "Texas", "Hawaii", "Australia", "Sydney", "New Zealand",
]
_VISUALS = [
    (r"basnigan", "wooden basnigan fishing boats with lamps at night"),
    (r"bulad|dried fish|daing|tuyo", "fish drying on racks in the sun"),
    (r"fisher|fishing|fisherfolk|\bcatch\b", "fishermen with nets by the sea"),
    (r"\bnipa\b", "nipa huts"),
    (r"market|palengke|vendor", "busy wet market stalls"),
    (r"sugarcane|sugar cane|\bcane\b|\bmill\b", "sugarcane fields and a sugar mill"),
    (r"\brice\b|palay|paddy", "rice paddies and farmers"),
    (r"coconut|copra", "coconut groves"),
    (r"church|cathedral|simbahan", "an old stone church"),
    (r"fiesta|festival|procession", "a festival procession"),
    (r"jeepney", "colorful jeepneys on a street"),
    (r"\bport\b|\bpier\b|wharf|harbou?r|steamer|\bship", "a wooden pier and ships in the harbor"),
    (r"river|creek", "a river and its banks"),
    (r"school|classroom|students", "school children in a classroom"),
    (r"kitchen|noodle|soup|pancit|dumpling|\bcook", "a home kitchen with cooking"),
    (r"weaving|\bloom\b|hablon|textile", "a hand weaving loom"),
    (r"migrat|voyage|sailed|sailing|\bjourney", "families travelling on a wooden boat"),
]


_TECH_VISUALS = [
    (r"semiconductor|\bchips?\b|wafer|fabricat", "technicians in white cleanroom suits at a semiconductor plant"),
    (r"\bai\b|artificial intelligence|data.?cent", "rows of server racks in a modern data center"),
    (r"supply chain|logistic|shipping|container|\bports?\b", "container ships and cranes at a modern port"),
    (r"electric|energy|power grid|renewable|solar", "power transmission lines and solar panels"),
    (r"invest|econom|industrial|manufactur|factory|factories", "a clean modern factory floor with engineers"),
    (r"engineer|technician|training|universit|school|students", "engineering students and trainers in a modern lab"),
    (r"minister|government|policy|coalition|agreement|diplomat", "officials at a conference table in a modern meeting room"),
    (r"new clark|industrial zone|economic security zone", "a planned modern industrial park with new buildings"),
]


def infer_location(job: Job) -> Job:
    """Work out place, era and visual details from the article itself, so no form needs filling in.
    Anything the job already has (e.g. typed in the portal or the Actions form) is kept as it is."""
    title = clean_text(job.get("title"))
    body = clean_text(extract_main(job.get("body"))) if job.get("body") else ""
    text = f"{title}. {title}. {title}. {body}"
    counts = {p: len(re.findall(r"(?<![A-Za-z])" + re.escape(p) + r"(?![A-Za-z])", text)) for p in _PH_PLACES + _WORLD_PLACES}
    top = [p for p, c in sorted(counts.items(), key=lambda x: -x[1]) if c > 0][:3]
    in_ph = any(p in _PH_PLACES for p in top)
    name = (", ".join(top) + (", Philippines" if in_ph else "")) if top else ""

    years = [int(y) for y in re.findall(r"\b(1[5-9]\d\d|20[0-2]\d)\b", text)]
    old = [y for y in years if y < 2000]
    era = ""
    if old and len(old) >= max(2, 0.4 * len(years)):
        decs = sorted({d for d, _ in __import__("collections").Counter(y // 10 * 10 for y in old).most_common(2)})
        era = f"{decs[0]}s" if len(decs) == 1 else f"{decs[0]}s to {decs[-1]}s"

    low = text.lower()
    # Modern technology / economy / policy articles: show today's settings, never market stalls or looms picked up from a stray word.
    tech_hits = sum(len(re.findall(rx, low)) for rx, _ in _TECH_VISUALS)
    modern = (not era) and (tech_hits >= 12 or (years and sum(y >= 2015 for y in years) >= 0.6 * len(years)))
    if modern:
        era = "present day"
        scored = sorted(((len(re.findall(rx, low)), phrase) for rx, phrase in _TECH_VISUALS), reverse=True)
        phrases = [ph for c, ph in scored if c > 0][:6] or ["modern offices and industrial buildings"]
        if in_ph:
            phrases.append("modern Philippine setting")
    else:
        scored = sorted(((len(re.findall(rx, low)), phrase) for rx, phrase in _VISUALS), reverse=True)
        phrases = [ph for c, ph in scored if c > 0][:6]
        if in_ph and phrases:
            phrases.append("tropical Philippine setting")
    out = {"name": name, "era": era, "description": ", ".join(phrases)}
    ai = llm_text(
        "You prepare a documentary video from an article. Reply with JSON only: "
        '{"name": "main place, region, country", "era": "time period such as 1950s, or present day when the article is about current events", '
        '"description": "6-10 concrete visual details of the scenes the article describes, in the right era, comma-separated, '
        'e.g. for a history essay: wooden outrigger fishing boats, nipa huts; for a technology essay: semiconductor cleanroom, container port, server racks", '
        '"palette": "3-5 colour words", "characters": [{"name": "...", "description": "age, clothing, look", '
        '"appearsIn": ["words in the text where they appear"]}]} . Use only what the article says. Max 3 characters.',
        f"Title: {title}\nText: {body[:3500]}", max_tokens=420)
    if ai:
        m = re.search(r"\{.*\}", ai, re.S)
        try:
            d = json.loads(m.group(0)) if m else {}
            for k in ("name", "era", "description", "palette"):
                if isinstance(d.get(k), str) and len(d[k].strip()) > 2:
                    out[k] = d[k].strip()[:300]
            chars = [{"name": clean_text(c.get("name")), "description": clean_text(c.get("description")),
                      "appearsIn": [clean_text(a) for a in (c.get("appearsIn") or []) if isinstance(a, str)][:4]}
                     for c in (d.get("characters") or []) if isinstance(c, dict) and clean_text(c.get("name"))][:3]
            if chars and not job.get("characters"):
                job["characters"] = chars
        except Exception:
            log("  AI location planner gave no usable answer; using built-in rules")
    else:
        log("  AI location planner unavailable; using built-in rules")
    have = {k: v for k, v in (job.get("location") or {}).items() if clean_text(str(v))}
    return {**{k: v for k, v in out.items() if v}, **have}


def fill_job_from_article(job: Job, row: Job) -> None:
    """A job file may hold only a title (+ location/characters). Take the text from the article on the site."""
    for key, names in (("body", ("content", "body")), ("excerpt", ("excerpt", "summary")), ("category", ("category",))):
        if not str(job.get(key) or "").strip():
            for n in names:
                if str(row.get(n) or "").strip():
                    job[key] = row[n]
                    break
    if job.get("articleId") in (None, "") and row.get("id") is not None:
        job["articleId"] = row["id"]


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


def looks_like_tutorial(job: Job) -> bool:
    """Poetic Bytes lesson pages (code blocks, 'Copy Run' buttons) belong to the tutorial video workflow, not this one.
    Put "essay": true in a job file to override."""
    body = str(job.get("body") or "")
    title = clean_text(job.get("title"))
    return (len(re.findall(r"<pre\b", body)) >= 3
            or len(re.findall(r"\bCopy\s+Run\b", clean_text(body))) >= 3
            or bool(re.search(r"\|\s*Poetic Bytes\s*$", title)))


def needs_work(job: Job, marker: Job | None) -> bool:
    if FORCE_REDO:
        return True
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

    if not job.get("jobId"):  # forms that leave it empty would otherwise be "done" forever after the first run
        job["jobId"] = str(int(path.stat().st_mtime))
    title = job.get("title", name)
    log(f"\n=== {title} ({name})")
    attempts = (marker.get("attempts", 0) if marker and marker.get("jobId") == job.get("jobId") else 0) + 1

    final = None
    try:
        row = None
        if not DRY_RUN:
            row = find_article(job, fetch_articles())
            if row is None:
                log("  article not found on The Commonplace; the video will be made but not attached")
            elif existing_video(row) and not (job.get("force") or FORCE_REDO):
                log("  article already has a video; leaving it alone")
                write_marker(name, {"jobId": job.get("jobId"), "status": "skipped",
                                    "reason": "article already has a video", "title": title})
                return "skipped"

        if row is not None:
            fill_job_from_article(job, row)
        if not clean_text(job.get("body")):
            raise RuntimeError("this job has no article text and the article was not found on the site "
                               "(the title must match exactly), so there is nothing to narrate")
        if looks_like_tutorial(job) and not job.get("essay"):
            log("  this is a Poetic Bytes tutorial page (code lessons), so it is skipped here: "
                "make it with the 'Tutorial video' workflow, which shows the code typed on a laptop")
            if not DRY_RUN:
                write_marker(name, {"jobId": job.get("jobId"), "status": "skipped",
                                    "reason": "tutorial page: use the Tutorial video workflow", "title": title})
            return "skipped"
        set_job_voice(job)
        loc0 = dict(job.get("location") or {})
        job["location"] = infer_location(job)
        auto = {k: v for k, v in job["location"].items() if k not in loc0}
        if auto:
            log(f"  worked out from the article: {auto}")
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
        Path("out").mkdir(exist_ok=True)
        shutil.copy(final, Path("out") / fname)
        if CREDITS:
            (Path("out") / (fname + ".credits.txt")).write_text("\n".join(CREDITS), encoding="utf-8")
        article_url = article_page_url(job, row)
        desc = (f"Read the full essay: {article_url}\n" if article_url else "") + \
               f"More on The Commonplace: {SITE_URL.rstrip('/')}"
        if CREDITS:
            desc += "\n\nCredits (Wikimedia Commons photos, Pexels stock video):\n" + "\n".join(CREDITS)
        (Path("out") / (fname + ".description.txt")).write_text(desc, encoding="utf-8")
        url = upload_video(final, fname)
        log(f"  uploaded: {url}")
        attached = False
        if row is not None:
            attach_video(row, url)
            attached = True
            log(f"  attached to article #{row['id']}")
            add_to_index_list(article_url)
            log(f"  article page (request indexing in Search Console): {article_url}")
        yt_id = ""
        if YT_ENABLED and not (marker and marker.get("jobId") == job.get("jobId") and marker.get("youtubeId")):
            try:
                tags = row.get("tags") if row else None
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                yt_title, yt_desc, yt_tags = youtube_seo(job, title, desc, tags if isinstance(tags, list) else [])
                yt_id = upload_to_youtube(final, yt_title, yt_desc, yt_tags)
                log(f"  uploaded to YouTube ({YT_PRIVACY}): https://youtu.be/{yt_id}")
            except Exception as e:
                log(f"  YouTube upload skipped ({str(e)[:300]})")   # never fails the job
        write_marker(name, {"jobId": job.get("jobId"), "status": "done", "title": title, "youtubeId": yt_id,
                            "videoUrl": url, "articleUrl": article_url, "attached": attached, "engine": engine, "credits": CREDITS[:30],
                            "seconds": round(dur)})
        return "done"

    except Exception as e:
        log(f"  FAILED: {e}")
        if not DRY_RUN:
            write_marker(name, {"jobId": job.get("jobId"), "status": "failed",
                                "attempts": attempts, "error": str(e)[:400], "title": title})
        return "failed"

    finally:
        # free the scratch folder (pictures, audio, clips) so many jobs don't fill the runner's disk
        if final is not None and Path(final).parent.name.startswith("vid_"):
            shutil.rmtree(Path(final).parent, ignore_errors=True)


def main():
    log(f"article_video.py {SCRIPT_VERSION} | INTRO_TITLE={int(INTRO_TITLE)} SPEAK_HEADINGS={int(SPEAK_HEADINGS)} "
        f"SLIDE_WORDS={SLIDE_WORDS} AI_IMAGE_MAX={AI_IMAGE_MAX} FORCE_REDO={int(FORCE_REDO)}")
    if not DRY_RUN and not ADMIN_KEY:
        log("ADMIN_KEY is not set. Add it under Settings > Secrets and variables > Actions.")
        return 1
    files = sorted(Path(p) for p in glob.glob(str(JOBS_DIR / "*.json")))
    if ONLY_JOB:
        files = [f for f in files if ONLY_JOB in f.name.lower()]
        log(f"Only making jobs whose file name contains '{ONLY_JOB}': {[f.name for f in files] or 'none found'}")
    if not files:
        log("No video jobs found.")
        return 0
    results, done_count, longest = [], 0, 0.0
    for f in files:
        if done_count >= MAX_JOBS_PER_RUN:
            log("Job limit for this run reached; the rest will be picked up next time.")
            break
        elapsed = time.time() - RUN_START
        if longest and elapsed + longest * 1.15 > RUN_BUDGET:
            log(f"Not enough time left for another job ({elapsed / 60:.0f} min used); it will run next time.")
            break
        t0 = time.time()
        res = process_job(f)
        if res in ("done", "failed", "dry"):
            longest = max(longest, time.time() - t0)
        if res:
            results.append(res)
            done_count += 1
    log("\nSummary:", {r: results.count(r) for r in set(results)} or "nothing to do")
    return 1 if "failed" in results else 0


if __name__ == "__main__":
    sys.exit(main())
