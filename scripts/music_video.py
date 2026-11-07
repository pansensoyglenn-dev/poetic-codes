#!/usr/bin/env python3
"""Make a lyric music video: a picture for what each part of the song is about, changing on the right line, with the lyrics shown.

    python scripts/music_video.py my-song          (reads music/my-song.mp3 + music/my-song.txt, optional music/my-song.json)

Or give a song PAGE instead:  python scripts/music_video.py https://your-site/song.html   (or a saved .html file)
                   Title, lyrics (headings like "Chorus" become labels, each line / <br> is a lyric line) and the audio link
                   (an <audio> tag or a link to an .mp3) are read from the page. If the page has no audio link, set AUDIO_URL.

music/<song>.mp3   the song (.wav/.m4a also work)
music/<song>.txt   the lyrics. Section labels like [Verse 1] / [Chorus] on their own line. A repeated chorus reuses its pictures.
                   Optional times: put [0:42] at the start of any line (or before a label: [0:42] [Chorus]). Lines without a
                   time get one in between. With no times at all, the song is listened to (Whisper) to find them, and if that
                   cannot work the lines are spread evenly over the song.
music/<song>.json  optional: {"title": "", "artist": "", "about": "what the song is about", "look": "visual style", "people": "who is shown, e.g. Filipino / Caucasian American",
                   "place": "where it happens", "characters": [{"name": "", "description": ""}], "language": "tl"}

Uses the same free picture generators as the essay videos (scripts/essay_video.py): Cloudflare first, then the free backups.
"""
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import essay_video as ev  # noqa: E402  (picture + AI-text helpers shared with the essay videos)

MUSIC_DIR = Path(os.environ.get("MUSIC_DIR", "music"))
OUT_DIR = Path(os.environ.get("OUT_DIR", "out"))
MAX_PICS = int(os.environ.get("MAX_PICS", "18"))             # most different pictures per song (Cloudflare free allowance)
MIN_SHOT = float(os.environ.get("MIN_SHOT", "7"))            # shortest time one picture stays
FADE = float(os.environ.get("FADE", "0.9"))                  # crossfade between pictures
FPS = 25
W, H = 1280, 720
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
USE_WHISPER = os.environ.get("WHISPER", "auto")              # auto | 1 | 0
DEFAULT_LOOK = "cinematic music video still, moody natural lighting, shallow depth of field, 35mm film grain, wide 16:9 composition"
log = ev.log


# ---------------------------------------------------------------- lyrics
TS = re.compile(r"^\[\s*(\d+):(\d{2})(?:[.:](\d{1,3}))?\s*\]\s*")
LABEL = re.compile(r"^\[([^\]\d][^\]]*)\]$|^\(([^)]+)\)$")


def parse_lyrics(text):
    """-> (lines, sections). lines: [{'text', 'time' (seconds or None), 'section': index}]; sections: [label]."""
    lines, sections = [], ["Song"]
    cur = 0
    for raw in text.replace("\r", "").split("\n"):
        s = raw.strip()
        if not s:
            continue
        t = None
        m = TS.match(s)
        if m:
            frac = m.group(3) or "0"
            t = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))
            s = s[m.end():].strip()
        lab = LABEL.match(s)
        if lab:
            sections.append((lab.group(1) or lab.group(2)).strip())
            cur = len(sections) - 1
            if t is not None:
                lines.append({"text": "", "time": t, "section": cur, "label_only": True})
            continue
        if s:
            lines.append({"text": s, "time": t, "section": cur})
    # a time put on a label belongs to the next lyric line
    out, carry = [], None
    for ln in lines:
        if ln.get("label_only"):
            carry = ln["time"] if carry is None else carry
            continue
        if ln["time"] is None and carry is not None:
            ln["time"], carry = carry, None
        else:
            carry = None
        out.append(ln)
    return out, sections


def wnorm(s):
    return re.sub(r"[^a-z0-9']+", "", s.lower())


def whisper_words(audio, lang):
    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        log(f"  Whisper is not installed ({str(e)[:60]}); lines will be timed without listening to the song")
        return []
    try:
        log(f"  listening to the song with Whisper '{WHISPER_MODEL}' to find when each line is sung ...")
        model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        segs, _ = model.transcribe(str(audio), word_timestamps=True, language=lang or None, vad_filter=False,
                                   condition_on_previous_text=False)
        words = [(wnorm(w.word), w.start, w.end) for s in segs for w in (s.words or []) if wnorm(w.word)]
        log(f"  heard {len(words)} word(s)")
        return words
    except Exception as e:
        log(f"  Whisper failed ({str(e)[:100]}); lines will be timed without listening to the song")
        return []


def align(lines, heard):
    """Give every line without a time one, from where its words were heard. Returns how many lines were really matched."""
    flat = [(wnorm(w), i) for i, ln in enumerate(lines) for w in ln["text"].split() if wnorm(w)]
    a = [w for w, _ in flat]
    b = [w for w, _, _ in heard]
    matched = {}
    if a and b:
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                li = flat[blk.a + k][1]
                matched.setdefault(li, heard[blk.b + k][1])
    n = 0
    for i, ln in enumerate(lines):
        if ln["time"] is None and i in matched:
            ln["time"] = matched[i]
            n += 1
    return n


def fill_times(lines, dur):
    """Fill the remaining gaps by spreading lines between the known times (by number of words), then make times increase."""
    n = len(lines)
    if not n:
        return
    if all(ln["time"] is None for ln in lines):
        lo, hi = dur * 0.06, dur * 0.94
        total = sum(max(1, len(ln["text"].split())) for ln in lines)
        t = lo
        for ln in lines:
            ln["time"] = t
            t += (hi - lo) * max(1, len(ln["text"].split())) / total
        return
    known = [i for i, ln in enumerate(lines) if ln["time"] is not None]
    if known[0] > 0:
        lines[0]["time"] = max(0.0, lines[known[0]]["time"] - 3.5 * known[0])
        known = [0] + known
    last_i = known[-1]
    if last_i < n - 1:
        lines[n - 1]["time"] = min(dur - 1.0, lines[last_i]["time"] + 3.5 * (n - 1 - last_i))
        known.append(n - 1)
    for a_i, b_i in zip(known, known[1:]):
        if b_i - a_i > 1:
            w = [max(1, len(lines[k]["text"].split())) for k in range(a_i, b_i)]
            span = lines[b_i]["time"] - lines[a_i]["time"]
            acc = 0
            for k in range(a_i + 1, b_i):
                acc += w[k - 1 - a_i]
                lines[k]["time"] = lines[a_i]["time"] + span * acc / sum(w)
    prev = -1.0
    for ln in lines:
        ln["time"] = max(ln["time"], prev + 0.4)
        prev = ln["time"]


# ---------------------------------------------------------------- song page (HTML)
SECTION_WORD = re.compile(r"^(intro|verse|pre[- ]?chorus|chorus|hook|refrain|bridge|outro|interlude|instrumental|solo|coda|"
                          r"tag|ending|break|rap)\b", re.I)
AUDIO_EXT = re.compile(r"\.(mp3|wav|m4a|ogg|flac)(\?.*)?$", re.I)


def _clean(t):
    return re.sub(r"\s+", " ", (t or "").replace("\xa0", " ")).strip()


def read_song_page(src):
    """A song page (link or .html file) -> (lyrics text in the lyrics-file format, meta dict, audio link or '').
    If the page's own HTML holds no lyrics (the page is filled in by JavaScript), the article is read from the Poetic Codes API."""
    if re.match(r"https?://", src):
        r = requests.get(src, headers={"User-Agent": ev.UA}, timeout=60)
        r.raise_for_status()
        html, base = r.text, src
    else:
        html, base = Path(src).read_text(encoding="utf-8", errors="replace"), ""
    text, meta, audio = _parse_song(html, base, src)
    if len([x for x in text.split("\n") if x and not x.startswith("[")]) < 4 and base:
        try:
            api = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
            rows = requests.get(api, headers={"Accept": "application/json", "User-Agent": ev.UA}, timeout=60).json()
            if isinstance(rows, dict):
                rows = rows.get("articles") or rows.get("results") or rows.get("data") or []
            slug = base.rstrip("/").rsplit("/", 1)[-1].rsplit(".", 1)[0]
            hit = next((r for r in rows if re.sub(r"[^a-z0-9]+", "-", str(r.get("title") or "").lower()).strip("-") == slug), None)
            if hit is None:
                hit = next((r for r in rows if slug.startswith(re.sub(r"[^a-z0-9]+", "-", str(r.get("title") or "").lower()).strip("-")[:40])), None)
            if hit is not None:
                body = str(hit.get("content") or hit.get("body") or "")
                if (hit.get("content_type") or hit.get("contentType") or "html") != "html" and "<" not in body[:200]:
                    body = "".join(f"<p>{ln}</p>" for ln in body.split("\n") if ln.strip())
                t2, m2, a2 = _parse_song(f"<html><body><main><h1>{hit.get('title') or ''}</h1>{body}</main></body></html>", base, src)
                if len([x for x in t2.split("\n") if x and not x.startswith("[")]) >= 4:
                    log("  the page has no lyrics in its HTML; read them from the article on the site instead")
                    return t2, {**m2, **{k: v for k, v in meta.items() if v}}, audio or a2
        except Exception as e:
            log(f"  could not read the article from the site API ({str(e)[:80]})")
    return text, meta, audio


def song_from_row(row):
    body = str(row.get("content") or row.get("body") or "")
    if (row.get("content_type") or row.get("contentType") or "html") != "html" and "<" not in body[:300]:
        body = "".join(f"<p>{ln}</p>" for ln in body.split("\n") if ln.strip())
    return _parse_song(f"<html><body><main><h1>{row.get('title') or ''}</h1>{body}</main></body></html>", "", "")


def pick_song_article():
    """The newest song / lyrics article on the site that has no video yet."""
    import essay_jobs as ej
    api = os.environ.get("ARTICLES_API", "https://poetic-codes.vercel.app/api/articles")
    rows = requests.get(api, headers={"Accept": "application/json", "User-Agent": ev.UA}, timeout=60).json()
    if isinstance(rows, dict):
        rows = rows.get("articles") or rows.get("results") or rows.get("data") or []
    todo = [r for r in rows if r.get("title") and ej.is_song(r) and not (r.get("video_url") or r.get("videoUrl"))]
    todo.sort(key=lambda r: ej.num(r.get("id")), reverse=True)
    return todo[0] if todo else None


def _parse_song(html, base, src):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "nav", "footer", "form", "button", "svg", "iframe"]):
        t.decompose()
    h1 = soup.find("h1")
    title = _clean(h1.get_text(" ")) if h1 else _clean((soup.title.string or "").split("|")[0] if soup.title else "")
    md = soup.find("meta", attrs={"name": "description"})
    about = _clean(md["content"]) if md and md.get("content") else ""
    meta = {"title": title, "about": about}
    audio = ""
    for tag in soup.find_all(["audio", "source", "a"]):
        link = tag.get("src") or tag.get("href") or ""
        if link and AUDIO_EXT.search(link):
            audio = urljoin(base, link) if base else str(Path(src).parent / link)
            break
    root = soup.find("main") or soup.find("article") or soup.body or soup
    out = []

    def add_label(t):
        t = _clean(t).strip(":").strip()
        if t:
            out.append(f"[{t}]")

    def add_text(el):
        for chunk in el.get_text("\n").split("\n"):
            ln = _clean(chunk)
            if not ln:
                continue
            m = re.match(r"^\[?\(?((?:intro|verse|pre[- ]?chorus|chorus|hook|refrain|bridge|outro|interlude|instrumental|solo|coda|rap)"
                         r"[^\]\):]{0,12})[\]\):]?$", ln, re.I)
            if m:
                add_label(m.group(1))
            elif ln.startswith("[") and ln.endswith("]") and len(ln) < 30:
                out.append(ln)
            else:
                out.append(ln)

    def walk(node):
        for ch in node.children:
            name = getattr(ch, "name", None)
            if not name:
                continue
            if name in ("h2", "h3", "h4", "h5", "h6"):
                add_label(ch.get_text(" "))
            elif name in ("p", "li", "pre", "blockquote", "span") and not ch.find(["p", "li", "pre", "div", "ul", "ol"]):
                add_text(ch)
            elif name in ("div", "section", "article", "ul", "ol", "main", "figure"):
                if not ch.find(["p", "li", "pre", "div", "h2", "h3", "h4", "ul", "ol", "section"]):
                    add_text(ch)
                else:
                    walk(ch)
            elif name == "br":
                continue
            else:
                walk(ch)

    walk(root)
    lines = [ln for ln in out if ln != "[]"]
    # drop page chrome that is not lyrics: the page's own title line, and long prose paragraphs
    keep = []
    for ln in lines:
        if ln.lower() == title.lower() or ln.lower() == about.lower():
            continue
        if not ln.startswith("[") and len(ln.split()) > 22:
            continue
        keep.append(ln)
    return "\n".join(keep), meta, audio


def fetch_audio(url, dest_dir):
    r = requests.get(url, headers={"User-Agent": ev.UA}, timeout=300)
    r.raise_for_status()
    ext = (AUDIO_EXT.search(url).group(1) if AUDIO_EXT.search(url) else "mp3").lower()
    p = Path(dest_dir) / f"song.{ext}"
    p.write_bytes(r.content)
    return p


# ---------------------------------------------------------------- shots (one picture each)
def build_shots(lines, sections, dur):
    """Group lines into shots. A section is split into shots of at least MIN_SHOT seconds; the same words give the same picture."""
    target = max(MIN_SHOT, dur / MAX_PICS)
    for _ in range(6):
        shots, cur = [], None
        for i, ln in enumerate(lines):
            end = lines[i + 1]["time"] if i + 1 < len(lines) else dur
            if cur is None or ln["section"] != cur["section"] or cur["end"] - cur["start"] >= target:
                cur = {"section": ln["section"], "start": ln["time"], "end": end, "lines": []}
                shots.append(cur)
            cur["lines"].append(ln["text"])
            cur["end"] = end
        for s in shots:
            s["key"] = " ".join(wnorm(x) for x in s["lines"])
        if len({s["key"] for s in shots}) <= MAX_PICS:
            break
        target *= 1.3
    # the first picture also covers any intro, the last one the outro
    shots[0]["start"] = 0.0
    shots[-1]["end"] = dur
    for a, b in zip(shots, shots[1:]):
        a["end"] = b["start"]
    # absorb shots that are too short into their neighbour
    merged = []
    for s in shots:
        if merged and (s["end"] - s["start"] < max(3.0, FADE * 2.5)):
            merged[-1]["end"] = s["end"]
            merged[-1]["lines"] += s["lines"]
            merged[-1]["key"] = " ".join(wnorm(x) for x in merged[-1]["lines"])
        else:
            merged.append(s)
    return merged


PH_WORDS = {"ang", "ng", "mga", "sa", "ko", "mo", "ikaw", "ako", "ka", "kita", "imo", "akon", "gid", "nga", "kag", "kay",
            "wala", "sang", "ini", "siya", "namin", "natin", "hindi", "pero", "lang", "naman", "ba", "po", "yan", "ito", "iyong"}


def looks_filipino(lines):
    words = [wnorm(w) for ln in lines for w in ln["text"].split() if wnorm(w)]
    return bool(words) and sum(w in PH_WORDS for w in words) / len(words) >= 0.12


def cast_text(meta):
    """Who the pictures must show, e.g. 'Filipino people in the Philippines'."""
    people, place = (meta.get("people") or "").strip(), (meta.get("place") or "").strip()
    if not people:
        return ""
    return f"The people shown are {people}" + (f", in {place}" if place else "") + ", with matching faces, skin tones, clothing and surroundings"


SHOT_TYPES = ["wide establishing shot", "medium shot", "close-up on hands or an object", "over-the-shoulder shot",
              "low-angle shot", "profile close-up", "high wide shot", "detail shot of the surroundings"]


def describe(shot, section, meta, prev=None, idx=0):
    ctx = []
    if cast_text(meta):
        ctx.append(cast_text(meta) + ".")
    if meta.get("title"):
        ctx.append(f"Song: {meta['title']}.")
    if meta.get("about"):
        ctx.append(f"About: {meta['about']}.")
    if meta.get("place"):
        ctx.append(f"Place: {meta['place']}.")
    chars = "; ".join(f"{c.get('name', '')}: {c.get('description', '')}" for c in (meta.get("characters") or []))
    if chars:
        ctx.append(f"Recurring people (show the same person each time): {chars}.")
    lyric = " / ".join(shot["lines"])
    out = ev.llm_text(
        "You direct a music video. Read the lyric lines and describe ONE concrete scene a camera could film that shows what "
        "they mean. Rules: turn metaphors into a literal, visible moment (a person, an action, a place, the weather); keep the "
        "same people and mood across the song, but CHANGE the place, the action and the time of day from shot to shot so the "
        "video tells a story; do not begin with 'A woman stands alone'; if the singer speaks to or about someone, show that "
        "relationship (two people, a gesture, an object that belongs to them); no text, signs, subtitles, logos or maps; never "
        "mention the lyrics or the camera. Reply with the description only, 25 to 45 words.",
        " ".join(ctx) + f"\nSection: {section}\nLyrics: {lyric[:700]}"
        + (("\nEarlier shots (do not repeat their place or pose): " + " | ".join(prev[-4:])) if prev else ""), max_tokens=130)
    scene = ""
    if out:
        scene = ev.clean_text(out).strip().strip('"')
        scene = re.sub(r"^(scene|description|image)\s*:\s*", "", scene, flags=re.I)
        scene = " ".join(scene.split()[:55]).rstrip(" ,;:")
        if len(scene.split()) < 6:
            scene = ""
    if not scene:       # the AI helper is unavailable: describe the lyric words themselves
        scene = "a scene that shows: " + " ".join(lyric.split()[:30])
    if prev is not None:
        prev.append(" ".join(scene.split()[:14]))
    look = meta.get("look") or DEFAULT_LOOK
    scene = f"{SHOT_TYPES[idx % len(SHOT_TYPES)]}: {scene}"
    who = f" {chars}." if chars else ""
    place = f" Place: {meta['place']}." if meta.get("place") else ""
    cast = (cast_text(meta) + ". ") if cast_text(meta) else ""
    return f"Photograph of: {scene}. {cast}{place}{who} {look}, no text, no letters, no watermark."[:1900]


def to_frame(img):
    """Fill a 16:9 frame: crop to the right shape, never stretch."""
    img = img.convert("RGB")
    w, h = img.size
    tw, th = 1920, 1080
    s = max(tw / w, th / h)
    img = img.resize((int(w * s) + 1, int(h * s) + 1), Image.LANCZOS)
    x, y = (img.width - tw) // 2, (img.height - th) // 2
    return img.crop((x, y, x + tw, y + th))


def placeholder(i):
    """A soft dark gradient, used only when a picture cannot be made at all."""
    base = Image.new("RGB", (64, 36))
    px = base.load()
    for yy in range(36):
        for xx in range(64):
            px[xx, yy] = (14 + yy, 20 + (xx + i * 9) % 30, 40 + yy * 2)
    return base.resize((1920, 1080), Image.BICUBIC).filter(ImageFilter.GaussianBlur(8))


# ---------------------------------------------------------------- captions + video
def ass_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def write_ass(path, lines, dur, meta):
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1280\nPlayResY: 720\nWrapStyle: 0\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Lyric,DejaVu Sans,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,70,70,64,1\n"
            "Style: Title,DejaVu Sans,34,&H00F0F0F0,&H00F0F0F0,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,2,1,8,70,70,40,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    ev_lines = []
    card = " - ".join(x for x in (meta.get("title"), meta.get("artist")) if x)
    first = lines[0]["time"] if lines else dur
    if card:
        ev_lines.append(f"Dialogue: 0,{ass_time(0.6)},{ass_time(min(5.0, max(2.5, first - 0.3)))},Title,,0,0,0,,{{\\fad(500,500)}}{card}")
    for i, ln in enumerate(lines):
        end = lines[i + 1]["time"] if i + 1 < len(lines) else dur
        end = min(end - 0.05, ln["time"] + 9.0)
        if end - ln["time"] < 0.6:
            end = ln["time"] + 0.6
        text = ln["text"].replace("{", "(").replace("}", ")")
        ev_lines.append(f"Dialogue: 0,{ass_time(ln['time'])},{ass_time(end)},Lyric,,0,0,0,,{{\\fad(150,150)}}{text}")
    Path(path).write_text(head + "\n".join(ev_lines) + "\n", encoding="utf-8")


def parse_duration(v):
    v = (v or "").strip()
    m = re.match(r"^(\d+):(\d{1,2})(?:\.\d+)?$", v)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    try:
        return float(v)
    except ValueError:
        return 0.0


def srt_time(t):
    t = max(0.0, t)
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{int(t % 60):02d},{int(round((t % 1) * 1000)) % 1000:03d}"


def write_srt(path, lines, dur):
    rows = []
    for i, ln in enumerate(lines):
        end = lines[i + 1]["time"] if i + 1 < len(lines) else dur
        end = min(end - 0.05, ln["time"] + 9.0)
        rows.append(f"{i + 1}\n{srt_time(ln['time'])} --> {srt_time(max(end, ln['time'] + 0.6))}\n{ln['text']}\n")
    Path(path).write_text("\n".join(rows), encoding="utf-8")


def narrate(lines, work):
    """No song: read the lyrics aloud with the free voice, and use the exact moments each line is spoken as the timing."""
    work = Path(work)
    gap_line, gap_section = 0.55, 1.1
    parts, t, prev_section = [], 1.0, None
    for i, ln in enumerate(lines):
        mp3 = work / f"n{i}.mp3"
        text = re.sub(r"\s+", " ", ln["text"].replace("&", " and ")).strip()
        ev.synth(text, str(mp3))
        d = probe(mp3)
        if prev_section is not None and ln["section"] != prev_section:
            t += gap_section - gap_line
        ln["time"] = t
        parts.append((mp3, d))
        t += d + gap_line
        prev_section = ln["section"]
    # build with explicit silences so the spoken moments match the times above
    cmd = ["ffmpeg", "-y"]
    fc, labels, cursor = [], [], 0.0
    for i, (mp3, d) in enumerate(parts):
        cmd += ["-i", str(mp3)]
        start = lines[i]["time"]
        fc.append(f"[{i}:a]adelay={int(start * 1000)}|{int(start * 1000)},apad[a{i}]")
        labels.append(f"[a{i}]")
    total = lines[-1]["time"] + parts[-1][1] + 1.5
    fc.append("".join(labels) + f"amix=inputs={len(parts)}:duration=longest:normalize=0,atrim=0:{total:.2f}[out]")
    out = work / "narration.mp3"
    cmd += ["-filter_complex", ";".join(fc), "-map", "[out]", "-ar", "24000", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "96k", str(out)]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("could not build the narration: " + (p.stderr or b"").decode("utf-8", "replace")[-600:])
    return out


def probe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True)
    return float(p.stdout.strip())


def render(shots, frames, audio, ass, dur, out):
    n = len(shots)
    cmd = ["ffmpeg", "-y"]
    segs = [s["end"] - s["start"] for s in shots]
    for i, s in enumerate(shots):
        length = segs[i] + (FADE if i < n - 1 else 0)
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{length:.2f}", "-i", str(frames[i])]
    if audio is not None:
        cmd += ["-i", str(audio)]
    fc = []
    for i in range(n):
        nfr = max(2, int((segs[i] + (FADE if i < n - 1 else 0)) * FPS))
        zin = i % 2 == 0
        zexpr = f"1+0.10*on/{nfr}" if zin else f"1.10-0.10*on/{nfr}"
        px = (0.3, 0.7, 0.5, 0.2, 0.8)[i % 5]
        fc.append(f"[{i}:v]zoompan=z='{zexpr}':x='(iw-iw/zoom)*{px}':y='(ih-ih/zoom)*0.5':d=1:s={W}x{H}:fps={FPS},setsar=1[p{i}]")
    last, acc = "p0", 0.0
    for i in range(1, n):
        acc += segs[i - 1]
        fc.append(f"[{last}][p{i}]xfade=transition=fade:duration={FADE}:offset={acc:.2f}[x{i}]")
        last = f"x{i}"
    if ass is not None:
        ass_path = str(ass).replace("\\", "/").replace(":", "\\:")
        fc.append(f"[{last}]ass='{ass_path}',format=yuv420p[v]")
    else:
        fc.append(f"[{last}]format=yuv420p[v]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[v]"]
    cmd += ["-map", f"{n}:a", "-c:a", "aac", "-b:a", "160k"] if audio is not None else ["-an"]
    cmd += ["-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-r", str(FPS),
            "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + (p.stderr or b"").decode("utf-8", "replace")[-900:])


def publish_to_article(page, video, row=None):
    """When made from a song page link or a site article: upload the video and attach it to that article (needs ADMIN_KEY)."""
    if (not page and row is None) or not os.environ.get("ADMIN_KEY", "").strip():
        return
    try:
        import tutorial_publish as tp
        if row is None:
            title = tp.page_title(page)
            r = requests.get(tp.ARTICLES_API, headers={"Accept": "application/json", "User-Agent": ev.UA}, timeout=60)
            r.raise_for_status()
            data = r.json()
            rows = (data.get("articles") or data.get("results") or data.get("data") or []) if isinstance(data, dict) else data
            row = tp.find_article(rows, title, page)
        else:
            title = row.get("title")
        if row is None:
            log(f"  not attached: no article titled '{title}' on Poetic Codes (the video is still on the release).")
            return
        url = tp.upload(video, f"{video.stem}-{int(time.time())}.mp4")
        tp.attach(row, url)
        log(f"  attached to the article '{row.get('title')}' (id {row.get('id')}): {url}")
    except Exception as e:
        log("  could not attach the video to the article: " + str(e)[:300])


def main():
    name = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("SONG", "")).strip()
    auto_row = None
    if not name:
        auto_row = pick_song_article()
        if auto_row is None:
            log("Every song / lyrics article on the site already has a video; nothing to do. "
                "(To redo one, type its page link in the 'song' box.)")
            return 0
        name = "article:" + str(auto_row.get("id"))
        log(f"  no song given: making the newest song article without a video: '{auto_row.get('title')}' (id {auto_row.get('id')})")
    log(f"music_video.py music-v2  song: {name}")
    meta, work = {}, Path(tempfile.mkdtemp(prefix="mvsrc_"))
    src_page = name if re.match(r"https?://", name) else ""
    if auto_row is not None:
        lyr_text, meta, link = song_from_row(auto_row)
        link = os.environ.get("AUDIO_URL", "").strip() or link
        slug = re.sub(r"[^a-z0-9]+", "-", (auto_row.get("title") or "song").lower()).strip("-")[:50] or "song"
        local = next((p for ext in ("mp3", "wav", "m4a", "ogg", "flac") for p in [MUSIC_DIR / f"{slug}.{ext}"] if p.exists()), None)
        audio = (fetch_audio(link, work) if re.match(r"https?://", link or "") else None) or local
        name = slug
    elif re.match(r"https?://(www\.)?github\.com/[^/]+/[^/]+/?(tree|blob)?", name):
        log("That is a GitHub repository link, not a song page. Enter either the link of the web page that shows the lyrics "
            "(for example https://your-site/my-song.html), or just the file name of a song in the music/ folder "
            "(for example my-song, for music/my-song.mp3 and music/my-song.txt).")
        return 1
    elif re.match(r"https?://", name) or name.lower().endswith((".html", ".htm")):
        lyr_text, meta, link = read_song_page(name)
        link = os.environ.get("AUDIO_URL", "").strip() or link
        slug = re.sub(r"[^a-z0-9]+", "-", (meta.get("title") or "song").lower()).strip("-")[:50] or "song"
        local = next((p for ext in ("mp3", "wav", "m4a", "ogg", "flac") for p in [MUSIC_DIR / f"{slug}.{ext}"] if p.exists()), None)
        if link:
            log(f"  song page: '{meta.get('title')}'; getting the audio ...")
            audio = fetch_audio(link, work) if re.match(r"https?://", link) else Path(link)
            if not audio.exists():
                log(f"The audio file '{link}' was not found. Put the song's link in the 'audio' box.")
                return 1
        elif local is not None:
            audio = local
        else:
            audio = None        # no song anywhere: the lyrics are read aloud instead
        name = slug
    else:
        audio = next((p for ext in ("mp3", "wav", "m4a", "ogg", "flac") for p in [MUSIC_DIR / f"{name}.{ext}"] if p.exists()), None)
        lyr = MUSIC_DIR / f"{name}.txt"
        if not lyr.exists():
            log(f"Missing file: music/{name}.txt (the words). The song file music/{name}.mp3 is optional: without it the words are read aloud.")
            return 1
        lyr_text = lyr.read_text(encoding="utf-8")
    mp = MUSIC_DIR / f"{name}.json"
    if mp.exists():
        meta.update(json.loads(mp.read_text(encoding="utf-8")))
    meta.setdefault("title", name.replace("-", " ").replace("_", " ").title())
    if os.environ.get("LOOK"):
        meta["look"] = os.environ["LOOK"]
    if os.environ.get("PEOPLE", "").strip():
        meta["people"] = os.environ["PEOPLE"].strip()
    if os.environ.get("PLACE", "").strip():
        meta["place"] = os.environ["PLACE"].strip()
    lines, sections = parse_lyrics(lyr_text)
    if not lines:
        log("The lyrics file has no lyric lines.")
        return 1
    silent = os.environ.get("SILENT", "0") == "1"
    narrated = (not silent) and (audio is None or os.environ.get("NARRATE") == "1")
    if narrated:
        log("  no song file: reading the words aloud with the free voice, one picture for each part")
        for ln in lines:
            ln["time"] = None
        audio = narrate(lines, work)
    if silent:
        want = parse_duration(os.environ.get("DURATION", ""))
        timed = [ln["time"] for ln in lines if ln["time"] is not None]
        if audio is not None:
            dur = probe(audio)
            log("  silent video: the song file is used only to find the timing; it is not put in the video")
        elif want > 0:
            dur = want
        elif timed:
            dur = max(timed) + 8.0
        else:
            dur = max(30.0, len(lines) * 4.0)
        log(f"  silent video of {dur / 60:.1f} min" + ("" if (audio is not None or want > 0 or timed) else
            " (a guess: enter the song's length in the 'duration' box, like 3:30, so the pictures change on time)"))
    else:
        dur = probe(audio)
    if not meta.get("people") and looks_filipino(lines):
        meta["people"] = "Filipino"
        meta.setdefault("place", "the Philippines")
        log("  the lyrics are in a Philippine language, so the pictures will show Filipino people in the Philippines")
    if meta.get("people"):
        log(f"  people shown: {meta['people']}" + (f" ({meta['place']})" if meta.get("place") else ""))
    log(f"  {len(lines)} lyric line(s) in {len(sections) - 1 or 1} section(s); song is {dur / 60:.1f} min")

    given = sum(ln["time"] is not None for ln in lines)
    if narrated:
        pass
    elif silent and audio is None:
        if given:
            log(f"  using the {given} time(s) you wrote in the lyrics file")
        else:
            log("  no times in the lyrics and no song file: lines are spread evenly over the length. For pictures that change "
                "exactly on your song, add [m:ss] at the start of lines (at least for each verse and chorus).")
    elif given:
        log(f"  using the {given} time(s) you wrote in the lyrics file")
    elif USE_WHISPER != "0":
        heard = whisper_words(audio, meta.get("language"))
        got = align(lines, heard) if heard else 0
        if got < max(3, len(lines) * 0.3):
            log(f"  only {got} of {len(lines)} lines could be matched to the singing; timing is approximate. "
                "For exact timing add [m:ss] at the start of lines in the lyrics file.")
            for ln in lines:
                ln["time"] = None
        else:
            log(f"  matched {got} of {len(lines)} lines to the singing")
    fill_times(lines, dur)

    shots = build_shots(lines, sections, dur)
    uniq = {}
    for s in shots:
        uniq.setdefault(s["key"], len(uniq))
    log(f"  {len(shots)} shot(s), {len(uniq)} different picture(s) needed")
    tmp = Path(tempfile.mkdtemp(prefix="mv_"))
    made, frames, prev_scenes = {}, [], []
    t0 = time.time()
    for i, s in enumerate(shots):
        k = s["key"]
        if k not in made:
            prompt = describe(s, sections[s["section"]] if s["section"] < len(sections) else "", meta, prev_scenes, len(made))
            log(f"  picture {len(made) + 1}/{len(uniq)} ({s['start']:.0f}s): {prompt[:170]}")
            img = ev.gen_image(prompt) if ev.AI_IMAGES else None
            if img is None:
                prev = next((made[x] for x in reversed(list(made)) if made[x] is not None), None)
                img = prev if prev is not None else placeholder(len(made))
                log("    no picture could be made for this part; keeping the previous one")
            made[k] = img
        pth = tmp / f"f{i}.png"
        to_frame(made[k]).save(pth)
        frames.append(pth)
    log(f"  pictures ready in {(time.time() - t0) / 60:.1f} min ({ev.FALLBACK_STATE['used']} from the free backup generators)")

    captions = (os.environ.get("CAPTIONS") or ("0" if silent else "1")) == "1"
    ass = tmp / "lyrics.ass" if captions else None
    if ass is not None:
        write_ass(ass, lines, dur, meta)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{name}-music-video.mp4"
    log("  building the video ...")
    render(shots, frames, None if silent else audio, ass, dur, out)
    write_srt(OUT_DIR / f"{name}-lyrics.srt", lines, dur)
    (OUT_DIR / f"{name}-music-video.timing.txt").write_text(
        "\n".join(f"{int(ln['time'] // 60)}:{ln['time'] % 60:05.2f}  {ln['text']}" for ln in lines), encoding="utf-8")
    log(f"  done: {out} ({out.stat().st_size / 1048576:.1f} MB, {dur / 60:.1f} min)")
    publish_to_article(src_page, out, auto_row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
