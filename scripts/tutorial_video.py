#!/usr/bin/env python3
"""Make a narrated video from a Poetic Bytes tutorial page.

    python scripts/tutorial_video.py https://poetic-bytes.vercel.app/shopping-cart.html
    python scripts/tutorial_video.py my-page.html

What it does
  * reads the page (headings, paragraphs, bullet lists, callouts, tables, code snippets)
  * shows each code snippet being TYPED on a laptop screen (syntax-highlighted), then explains it with
    the explanation text under the laptop while the finished code stays in view
  * other parts become clean slides: text cards, tables; narration reads the explanation text, never the code
  * writes out/<slug>.mp4 and out/<slug>.description.txt (link + YouTube chapters)

Free: edge-tts voice + ffmpeg. Optional EXPLAIN_CODE=1 asks Cloudflare's free AI to add a
two-sentence spoken explanation to each code snippet (needs CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN).
"""
import asyncio
import html as htmllib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.token import Token

SCRIPT_VERSION = "2026-11-07-l"
W, H, FPS = 1280, 720, 25
VOICE = os.environ.get("TTS_VOICE", "en-PH-JamesNeural")
VOICE_FALLBACKS = ["en-PH-RosaNeural", "en-US-ChristopherNeural"]
RATE = os.environ.get("TTS_RATE", "+0%")
MAX_WORDS = int(os.environ.get("MAX_WORDS", "2500"))        # narration budget for the whole video
PAGE_LINES = int(os.environ.get("PAGE_LINES", "16"))        # code lines per slide
SLIDE_WORDS = int(os.environ.get("SLIDE_WORDS", "55"))      # longest paragraph shown on one slide
TYPE_CPS = float(os.environ.get("TYPE_CPS", "28"))             # typing speed on the laptop, characters per second
TYPE_FPS = int(os.environ.get("TYPE_FPS", "10"))               # animation frames per second while typing
FULL_LINES = int(os.environ.get("FULL_LINES", "60"))              # a code block longer than this is "the full source": not typed out
SPLIT_MINUTES = float(os.environ.get("SPLIT_MINUTES", "12"))    # auto-split pages whose video would be longer than this
SPLIT_MODE = os.environ.get("SPLIT", "auto")                  # auto = one video per topic when the page is too long for one video; 1 = always; 0 = never
LAPTOP_WORDS = int(os.environ.get("LAPTOP_WORDS", "26"))       # longest explanation shown under the laptop at once
EXPLAIN_CODE = os.environ.get("EXPLAIN_CODE", "0") == "1"
CF_ACCOUNT = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
CF_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
LLM_MODEL = os.environ.get("LLM_MODEL", "@cf/meta/llama-3.1-8b-instruct")
BRAND = os.environ.get("BRAND", "Poetic Bytes")
OUT_DIR = Path(os.environ.get("OUT_DIR", "out"))
TTS_FAKE = os.environ.get("TTS_FAKE") == "1"
MIN_CODE_BLOCKS = int(os.environ.get("MIN_CODE_BLOCKS", "0"))   # batch mode sets 1 so non-tutorial pages are skipped
UA = "tutorial-video-bot/1.0 (+https://poetic-bytes.vercel.app)"

BG1, BG2 = (11, 18, 28), (17, 32, 52)
PANEL, CODE_BG = (15, 28, 47), (10, 26, 36)
BLUE, BLUE_DEEP, BLUE_LT = (75, 139, 190), (48, 105, 152), (120, 185, 230)
GOLD, TEXT, MUTED = (255, 217, 102), (226, 232, 240), (139, 163, 191)
PADX = 90

SKIP_TAGS = {"script", "style", "button", "svg", "i", "nav", "form", "input", "textarea", "select", "iframe",
             "noscript", "canvas", "audio", "video", "footer", "header"}
SKIP_CLASS = re.compile(r"(^|\s)(tags|desc-meta|code-header|code-actions|section-label|hero|nav-bar|toc|ad-slot|"
                        r"quiz|runner|output|console|breadcrumb)(\s|$)")
SKIP_SECTION = re.compile(r"quiz|knowledge|question|comment|share|newsletter|subscribe|related|footer|follow|social|connect|\\btoc\\b|table of contents", re.I)
EMOJI = re.compile("[\U00010000-\U0010ffff\u2600-\u27bf\u2b00-\u2bff\u2190-\u21ff\ufe0f\u200d]")


def log(*a):
    print(*a, flush=True)


def run(cmd):
    p = subprocess.run(cmd, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed: {(p.stderr or b'').decode('utf-8', 'replace')[-800:]}")
    return p


# ---------------------------------------------------------------- text helpers
def screen_clean(t):
    t = EMOJI.sub("", t or "")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.;:!?)\]])", r"\1", t)
    return re.sub(r"([(\[])\s+", r"\1", t)


def speak_clean(t):
    t = screen_clean(t)
    t = t.replace("&", " and ").replace("\u2192", " to ").replace("\u2014", ", ").replace("\u2013", ", ")
    t = t.replace("\u00b7", ", ").replace("`", "").replace("()", "")
    t = re.sub(r"__(\w+?)__", r"dunder \1", t)             # __str__ -> dunder str
    t = re.sub(r"\.py\b", " dot py", t)                    # cart.py -> cart dot py
    t = re.sub(r"(?<=\w)_(?=\w)", " ", t)                 # place_order -> place order
    t = re.sub(r"@(\w+)", r"at \1", t)                    # @dataclass -> at dataclass
    t = re.sub(r"(?<![\w/])/(\w+)", r"slash \1", t)       # /docs -> slash docs
    t = re.sub(r"\s+", " ", t).strip()
    return re.sub(r"\s+([,.;:!?])", r"\1", t)


def el_text(el):
    return screen_clean(el.get_text(""))


def split_sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text, limit):
    out, cur, n = [], [], 0
    for s in split_sentences(text):
        w = len(s.split())
        if cur and n + w > limit:
            out.append(" ".join(cur))
            cur, n = [], 0
        cur.append(s)
        n += w
    if cur:
        out.append(" ".join(cur))
    return out


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")[:60] or "tutorial"


# ---------------------------------------------------------------- page -> scenes
def get_page(src):
    if re.match(r"https?://", src):
        r = requests.get(src, headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        return r.text, src
    return Path(src).read_text(encoding="utf-8", errors="replace"), ""


class Builder:
    def __init__(self, limit=None):
        self.limit = limit or MAX_WORDS
        self.scenes = []
        self.heading = ""
        self.spoken = ""            # last heading that was read aloud
        self.label = ""             # caption above the next code block, e.g. "Naive approach"
        self.words = 0
        self.cur = None             # the laptop currently on screen: explanation under the same heading is shown with it

    def room(self, speech):
        return self.words + len(speech.split()) <= self.limit

    def add(self, **sc):
        sp = sc.get("speech", "")
        if sp:
            if not self.room(sp):
                return False
            self.words += len(sp.split())
        self.scenes.append(sc)
        return True

    def lead(self, body_speech):
        """Read a new heading aloud once, before the first thing under it."""
        if self.heading and self.heading != self.spoken:
            self.spoken = self.heading
            return speak_clean(self.heading) + ". " + body_speech
        return body_speech

    # -- block handlers
    def paragraph(self, text):
        text = screen_clean(text)
        if len(text.split()) < 3 or text[:1] in "\u2014\u2013-":     # too short, or a quote attribution
            return
        if self.cur and self.cur["heading"] == self.heading:           # explaining the code that was just typed
            for chunk in chunk_text(text, LAPTOP_WORDS):
                self.add(kind="laptop_text", heading=self.heading, body=chunk, code=self.cur,
                         speech=speak_clean(chunk))
            return
        for chunk in chunk_text(text, SLIDE_WORDS):
            self.add(kind="text", heading=self.heading, body=chunk, speech=self.lead(speak_clean(chunk)))

    def bullets(self, items):
        items = [screen_clean(i) for i in items if len(screen_clean(i).split()) >= 2]
        if self.cur and self.cur["heading"] == self.heading:           # list explaining the code just typed
            for it in items:
                for chunk in chunk_text(it, LAPTOP_WORDS):
                    self.add(kind="laptop_text", heading=self.heading, body=chunk, code=self.cur,
                             speech=speak_clean(chunk))
            return
        group, n = [], 0
        for it in items + [None]:
            w = len(it.split()) if it else 0
            if group and (it is None or n + w > SLIDE_WORDS + 15):
                speech = ". ".join(speak_clean(g).rstrip(".") for g in group) + "."
                self.add(kind="text", heading=self.heading, items=group, speech=self.lead(speech))
                group, n = [], 0
            if it:
                group.append(it)
                n += w

    def code(self, code, is_full=False, lang="python"):
        code = textwrap.dedent(code.expandtabs(4)).strip("\n")
        code = "\n".join(l.rstrip() for l in code.split("\n"))
        if not code.strip():
            return
        if is_full:
            self.add(kind="text", heading=self.heading or "Full source code",
                     body="The complete source code is on the page. You can copy it, or run it in your browser.",
                     speech=self.lead("The complete source code is on the page. You can copy it, or run it right in your browser."))
            return
        pages = page_code(code.split("\n"))
        label, self.label = self.label, ""
        name = label or re.sub(r"^\d+(\.\d+)*\.?\s*", "", screen_clean(self.heading))
        fname = file_name(name, lang)
        self.spoken = self.heading
        for k, (lines, start) in enumerate(pages):
            if k == 0:
                if label:
                    speech = f"Let's look at the {speak_clean(label)}."
                else:
                    speech = f"Let's write the code for {speak_clean(name)}." if name else "Let's write this code."
            else:
                speech = "Now the next part."
            self.add(kind="code", heading=self.heading, name=name, fname=fname, lang=lang, lines=lines, start=start,
                     part=(k + 1, len(pages)), speech=speech, chapter=(name if k == 0 and not label else ""))
        lines, start = pages[-1]
        self.cur = {"heading": self.heading, "lines": lines, "start": start, "fname": fname, "lang": lang}
        if EXPLAIN_CODE:
            extra = explain_code(code, name)
            for chunk in chunk_text(extra, LAPTOP_WORDS) if extra else []:
                self.add(kind="laptop_text", heading=self.heading, body=chunk, code=self.cur, speech=chunk)

    def table(self, rows):
        rows = [[screen_clean(c) for c in r] for r in rows if any(screen_clean(c) for c in r)]
        if len(rows) < 2:
            return
        head, body = rows[0], rows[1:]
        for k in range(0, len(body), 6):
            part = body[k:k + 6]
            sp = ". ".join(", ".join(speak_clean(c) for c in r if c) for r in part) + "."
            intro = "Here is a quick reference. " if k == 0 else ""
            self.add(kind="table", heading=self.heading, head=head, rows=part, speech=self.lead(intro + sp))

    # -- walker
    def walk(self, node, first_h2):
        for ch in node.children:
            if not isinstance(ch, Tag):
                continue
            name = ch.name
            cls = " ".join(ch.get("class") or [])
            if name in SKIP_TAGS or SKIP_CLASS.search(cls):
                continue
            if name in ("h2", "h3", "h4"):
                if name != "h4" and ch is not first_h2:
                    self.heading = el_text(ch)
                continue
            if name in ("div", "span") and not ch.find(["p", "pre", "ul", "ol", "table", "h2", "h3", "h4", "div"]):
                nxt = ch.find_next_sibling()
                txt = screen_clean(ch.get_text(""))
                if nxt is not None and nxt.find("pre") is not None and 2 <= len(txt) <= 80:
                    self.label = txt
                    continue
            if name in ("div", "span") and not ch.find(["p", "pre", "ul", "ol", "table", "h2", "h3", "h4", "div", "section"]):
                self.paragraph(ch.get_text(""))        # e.g. a "💡 insight" box that holds plain text
                continue
            if name == "p":
                self.paragraph(ch.get_text(""))
            elif name in ("ul", "ol"):
                self.bullets([li.get_text("") for li in ch.find_all("li", recursive=False)])
            elif name == "pre":
                full = ch.get("id") == "fullSourcePre" or len(ch.get_text("").strip().splitlines()) > FULL_LINES
                self.code(ch.get_text(""), is_full=full, lang=detect_lang(ch))
            elif name == "table":
                self.table([[c.get_text("") for c in tr.find_all(["th", "td"])] for tr in ch.find_all("tr")])
            else:
                self.walk(ch, first_h2)


EXT = {"python": ".py", "javascript": ".js", "js": ".js", "typescript": ".ts", "html": ".html", "css": ".css",
       "bash": ".sh", "shell": ".sh", "sh": ".sh", "sql": ".sql", "json": ".json", "java": ".java", "c": ".c",
       "cpp": ".cpp", "csharp": ".cs", "php": ".php", "go": ".go", "rust": ".rs", "yaml": ".yml", "text": ".txt"}


LANG_LABEL = {"python": "Python", "javascript": "JavaScript", "js": "JavaScript", "typescript": "TypeScript", "html": "HTML",
              "css": "CSS", "sql": "SQL", "json": "JSON", "bash": "Bash", "shell": "Shell", "sh": "Shell", "java": "Java",
              "c": "C", "cpp": "C++", "csharp": "C#", "php": "PHP", "go": "Go", "rust": "Rust", "yaml": "YAML", "text": "Text"}


def detect_lang(pre):
    """The code's language: a language-xxx class, else the label in the code box header ('python'), else Python."""
    for el in [pre] + list(pre.find_all("code")) + [pre.parent]:
        for c in (el.get("class") or []) if hasattr(el, "get") else []:
            m = re.match(r"(?:language|lang)-(\w+)", c)
            if m:
                return m.group(1).lower()
    box = pre.find_parent(class_="code-container")
    if box is not None:
        hdr = box.select_one(".code-header span")
        if hdr is not None:
            word = screen_clean(hdr.get_text("")).lower()
            if word in EXT:
                return word
    return "python"


def file_name(name, lang="python"):
    """A believable file name for the editor tab, e.g. 'The Money Value Object' -> money_value_object.py"""
    base = re.sub(r"[^a-z0-9]+", "_", re.sub(r"\(.*?\)", "", (name or "").lower())).strip("_")
    base = re.sub(r"^(the|a|an)_", "", base)
    if len(base) > 22:
        base = base[:22].rsplit("_", 1)[0] if "_" in base[:22] else base[:22]
    return (base.rstrip("_") or "example") + EXT.get(lang, ".txt")


def page_code(lines):
    """Split a long snippet into slides of at most PAGE_LINES, preferring to cut at a blank line.
    Returns [(lines, first_line_number), ...]."""
    pages, cur, start, n = [], [], 1, 0
    for ln in lines:
        cur.append(ln)
        n += 1
        if len(cur) > PAGE_LINES:
            cut = max((i for i, x in enumerate(cur[:-1]) if not x.strip()), default=-1)
            if cut >= PAGE_LINES // 2:
                pages.append((cur[:cut], start))
                start += cut + 1
                cur = cur[cut + 1:]
            else:
                pages.append((cur[:-1], start))
                start += len(cur) - 1
                cur = cur[-1:]
    if any(x.strip() for x in cur):
        pages.append((cur, start))
    return pages or [(lines, 1)]


def explain_code(code, name):
    """Optional: two spoken sentences about what this snippet does (free Cloudflare model)."""
    if not (CF_ACCOUNT and CF_TOKEN):
        return ""
    try:
        r = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/run/{LLM_MODEL}",
            headers={"Authorization": f"Bearer {CF_TOKEN}"},
            json={"messages": [
                {"role": "system", "content": "You narrate a Python tutorial video. In at most two short plain sentences, "
                 "say what the code shown does and why it is written that way. Mention only what is visible in the code. "
                 "No code, no symbols, no bullet points."},
                {"role": "user", "content": f"Topic: {name}\n\n{code[:1800]}"}],
                "max_tokens": 110, "temperature": 0.2}, timeout=45)
        if not r.ok:
            return ""
        return speak_clean(str((r.json().get("result") or {}).get("response") or ""))[:400]
    except Exception as e:
        log(f"  code explanation skipped ({str(e)[:80]})")
        return ""


def heading_title(h1):
    """Text of an <h1> whose lines are split with <br>: 'Python Basics<br>Build a Solid Foundation' -> 'Python Basics: Build a Solid Foundation'."""
    parts = [screen_clean(BeautifulSoup(x, "html.parser").get_text(" ")) for x in re.split(r"<br\s*/?>", str(h1))]
    out = parts[0] if parts else ""
    for nxt in parts[1:]:
        if not nxt:
            continue
        joiner = " " if (out[-1:] in "\u2014\u2013-:\u00b7," or nxt[:1].islower()) else ": "
        out = out + joiner + nxt
    return out.rstrip(" .!:;")


def steps_after_code(scenes):
    """On many pages the 'Step 1, Step 2...' list comes BEFORE its code. For a tutorial the code should be typed first, then the
    steps explained under the laptop while the finished code stays in view: move such lists to just after the code."""
    out, i, n = [], 0, len(scenes)
    while i < n:
        j = i
        while j < n and scenes[j]["kind"] == "text" and scenes[j].get("items"):
            j += 1
        if j > i and j < n and scenes[j]["kind"] == "code" and scenes[j]["heading"] == scenes[i]["heading"]:
            pending = scenes[i:j]
            k = j
            while k < n and scenes[k]["kind"] == "code" and scenes[k]["heading"] == scenes[i]["heading"]:
                k += 1
            out.extend(scenes[j:k])
            last = scenes[k - 1]
            cur = {"heading": last["heading"], "lines": last["lines"], "start": last["start"],
                   "fname": last["fname"], "lang": last.get("lang", "python")}
            for sc in pending:
                for it in sc["items"]:
                    for chunk in chunk_text(it, LAPTOP_WORDS):
                        out.append({"kind": "laptop_text", "heading": last["heading"], "body": chunk, "code": cur,
                                    "speech": speak_clean(chunk)})
            i = k
        else:
            out.append(scenes[i])
            i += 1
    return out


def build_scenes(page_html, page_url, limit=None):
    soup = BeautifulSoup(page_html, "html.parser")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    h1 = soup.find("h1")
    title = heading_title(h1) if h1 else screen_clean((soup.title.string or "").split("|")[0] if soup.title else "Tutorial")
    title = title.rstrip(" .!:;")
    md = soup.find("meta", attrs={"name": "description"})
    desc = screen_clean(md["content"]) if md and md.get("content") else ""
    canon = soup.find("link", rel="canonical")
    link = (canon["href"] if canon and canon.get("href") else page_url) or ""
    author = soup.find("meta", attrs={"name": "author"})
    author = screen_clean(author["content"]) if author and author.get("content") else ""

    b = Builder(limit)
    b.add(kind="title", title=title, desc=desc, author=author,
          speech=speak_clean(title).rstrip(".") + ". " + speak_clean(desc))
    root = soup.find("main") or soup.body or soup
    sections = [s for s in root.find_all("section") if not s.find_parent("section")]
    for sec in sections:
        classes = " ".join(sec.get("class") or [])
        if "hero" in classes.split() or SKIP_SECTION.search(sec.get("id") or ""):
            continue
        h2 = sec.find("h2")
        if h2 is not None and SKIP_SECTION.search(el_text(h2)):
            continue
        lab = sec.select_one(".section-label")
        label = screen_clean(lab.get_text("")) if lab else ""
        stitle = el_text(h2) if h2 else ""
        if stitle:
            b.add(kind="section", label=label, title=stitle, speech=speak_clean(stitle), chapter=stitle)
            b.heading, b.spoken = stitle, stitle
            b.cur = None
        b.walk(sec, h2)
    b.add(kind="end", title="Try the code live", url=link or BRAND,
          speech=f"Try the live code on {BRAND}. The link is in the description.", chapter="Try it yourself")
    return steps_after_code(b.scenes), {"title": title, "desc": desc, "link": link}


# ---------------------------------------------------------------- drawing
def load_font(size, bold=False, mono=False):
    base = "DejaVuSansMono" if mono else "DejaVuSans"
    name = base + ("-Bold" if bold else "") + ".ttf"
    for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF",
              "/Library/Fonts", "C:\\Windows\\Fonts"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textlength(t, font=font) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def background():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=tuple(int(BG1[i] + (BG2[i] - BG1[i]) * t) for i in range(3)))
    return img


def chrome(img, d, idx, total, label=""):
    d.text((PADX, 30), (label or BRAND).upper(), font=load_font(18, True), fill=MUTED)
    bw = d.textlength(BRAND.upper(), font=load_font(16, True))
    d.text((W - PADX - bw, H - 44), BRAND.upper(), font=load_font(16, True), fill=MUTED)
    d.rectangle([0, H - 8, W, H], fill=(6, 12, 20))
    d.rectangle([0, H - 8, int(W * (idx + 1) / total), H], fill=BLUE_LT)


def draw_title(sc, idx, total):
    img = background()
    d = ImageDraw.Draw(img)
    chrome(img, d, idx, total, "Tutorial")
    f = load_font(58, True)
    lines = wrap(d, sc["title"], f, W - 2 * PADX)[:3]
    y = 150
    d.rectangle([PADX - 28, y, PADX - 22, y + len(lines) * 74 + 6], fill=GOLD)
    for ln in lines:
        d.text((PADX, y), ln, font=f, fill=TEXT)
        y += 74
    y += 26
    df = load_font(26)
    for ln in wrap(d, sc.get("desc", ""), df, W - 2 * PADX - 60)[:4]:
        d.text((PADX, y), ln, font=df, fill=MUTED)
        y += 38
    if sc.get("author"):
        d.text((PADX, H - 110), "By " + sc["author"], font=load_font(22, True), fill=BLUE_LT)
    return img


def draw_section(sc, idx, total):
    img = background()
    d = ImageDraw.Draw(img)
    chrome(img, d, idx, total, "Tutorial")
    if sc.get("label"):
        d.text((PADX, 250), sc["label"].upper(), font=load_font(26, True), fill=GOLD)
    f = load_font(54, True)
    y = 300
    for ln in wrap(d, sc["title"], f, W - 2 * PADX)[:3]:
        d.text((PADX, y), ln, font=f, fill=TEXT)
        y += 70
    d.rectangle([PADX, y + 14, PADX + 120, y + 18], fill=BLUE)
    return img


def draw_text(sc, idx, total):
    img = background()
    d = ImageDraw.Draw(img)
    chrome(img, d, idx, total)
    y = 78
    hf = load_font(34, True)
    for ln in wrap(d, sc.get("heading", ""), hf, W - 2 * PADX)[:2]:
        d.text((PADX, y), ln, font=hf, fill=GOLD)
        y += 46
    top, bottom = max(y + 24, 190), H - 80
    items = sc.get("items")
    bullet = bool(items)
    chunks = items or [sc.get("body", "")]
    maxw = W - 2 * PADX - (36 if bullet else 0)
    chosen = None
    for size in range(40, 21, -2):
        font = load_font(size)
        lh = int(size * 1.42)
        rows = [wrap(d, c, font, maxw) for c in chunks]
        total_h = sum(len(r) * lh for r in rows) + int(lh * 0.5) * (len(rows) - 1)
        chosen = (font, lh, rows)
        if total_h <= bottom - top:
            break
    font, lh, rows = chosen
    y0 = top
    d.rectangle([PADX - 28, top + 4, PADX - 24, min(bottom, top + sum(len(r) for r in rows) * lh)], fill=BLUE)
    for r in rows:
        for k, ln in enumerate(r):
            x = PADX + (36 if bullet else 0)
            if bullet and k == 0:
                d.ellipse([PADX + 6, y0 + lh // 2 - 7, PADX + 20, y0 + lh // 2 + 7], fill=BLUE_LT)
            d.text((x, y0), ln, font=font, fill=TEXT)
            y0 += lh
        y0 += int(lh * 0.5)
    return img


def tok_color(t):
    if t in Token.Comment:
        return (100, 132, 165)
    if t in Token.Literal.String:
        return (134, 239, 172)
    if t in Token.Literal.Number:
        return (251, 146, 60)
    if t in Token.Name.Decorator:
        return GOLD
    if t in Token.Name.Function or t in Token.Name.Class:
        return BLUE_LT
    if t in Token.Name.Builtin:
        return (45, 212, 191)
    if t in Token.Name.Tag:
        return BLUE_LT
    if t in Token.Keyword:
        return (192, 132, 252)
    return TEXT


def lex_lines(lines, lang="python"):
    out = [[]]
    try:
        lexer = get_lexer_by_name(lang)
    except Exception:
        lexer = TextLexer()
    for tt, val in lex("\n".join(lines), lexer):
        col = tok_color(tt)
        for k, part in enumerate(val.split("\n")):
            if k:
                out.append([])
            if part:
                out[-1].append((part, col))
    return (out + [[] for _ in lines])[:len(lines)]


_BG = [None]


def cached_bg():
    if _BG[0] is None:
        _BG[0] = background()
    return _BG[0].copy()


def laptop_setup(lines, fname, start, lang="python"):
    """Draw the empty laptop once; return everything needed to draw typed-in frames quickly."""
    img = cached_bg()
    d = ImageDraw.Draw(img)
    lx0, lx1, ly0, ly1 = 140, 1140, 16, 536
    d.ellipse([lx0 - 40, ly1 + 8, lx1 + 90, ly1 + 40], fill=(6, 10, 16))                       # shadow on the desk
    d.rounded_rectangle([lx0, ly0, lx1, ly1], radius=20, fill=(46, 53, 68), outline=(78, 88, 108), width=2)
    d.ellipse([(lx0 + lx1) // 2 - 3, ly0 + 5, (lx0 + lx1) // 2 + 3, ly0 + 11], fill=(20, 24, 32))   # camera
    sx0, sy0, sx1, sy1 = lx0 + 14, ly0 + 16, lx1 - 14, ly1 - 14
    d.rounded_rectangle([sx0, sy0, sx1, sy1], radius=6, fill=CODE_BG)
    d.rectangle([sx0, sy0, sx1, sy0 + 30], fill=PANEL)                                          # editor title bar
    for k, c in enumerate(((239, 68, 68), (245, 158, 11), (16, 185, 129))):
        d.ellipse([sx0 + 14 + k * 22, sy0 + 10, sx0 + 26 + k * 22, sy0 + 22], fill=c)
    tf = load_font(14)
    tw = int(d.textlength(fname, font=tf)) + 40
    d.rectangle([sx0 + 90, sy0 + 4, sx0 + 90 + tw, sy0 + 30], fill=CODE_BG)
    d.ellipse([sx0 + 102, sy0 + 13, sx0 + 110, sy0 + 21], fill=GOLD)
    d.text((sx0 + 120, sy0 + 8), fname, font=tf, fill=TEXT)
    d.rectangle([sx0, sy1 - 24, sx1, sy1], fill=(18, 52, 86))                                   # status bar
    sf = load_font(13)
    right = f"{LANG_LABEL.get(lang, lang.capitalize())}   UTF-8   Spaces: 4"
    d.text((sx1 - 14 - d.textlength(right, font=sf), sy1 - 20), right, font=sf, fill=(190, 215, 240))
    d.rounded_rectangle([90, ly1, 1190, ly1 + 18], radius=8, fill=(70, 79, 98))                 # laptop base
    d.rounded_rectangle([560, ly1, 720, ly1 + 7], radius=4, fill=(40, 46, 58))
    geo = {"sx0": sx0, "sy0": sy0, "sx1": sx1, "sy1": sy1, "code_top": sy0 + 40,
           "avail_h": (sy1 - 24) - (sy0 + 40) - 6, "code_w": sx1 - sx0 - 30}
    n = max(len(lines), 10)
    size = min(22, int(geo["avail_h"] / (n * 1.42)))
    longest = max((len(l) for l in lines), default=1)
    size = max(14, min(size, int((geo["code_w"] - 14) / ((longest + 3) * 0.603))))   # shrink so long lines fit
    font = load_font(size, mono=True)
    return {"base": img, "geo": geo, "font": font, "lh": int(size * 1.42), "cw": font.getlength("M"),
            "toks": lex_lines(lines, lang), "lines": lines, "start": start}


def laptop_frame(lp, nchars, caption, idx, total, cursor=True):
    img = lp["base"].copy()
    d = ImageDraw.Draw(img)
    g, font, lh, cw, toks, start = lp["geo"], lp["font"], lp["lh"], lp["cw"], lp["toks"], lp["start"]
    x0 = g["sx0"] + 16
    gutter = int(cw * 3) + 14
    # where is the cursor?
    rem, cur_n, cur_col = nchars, len(toks) - 1, None
    for n, lt in enumerate(toks):
        ln = sum(len(t) for t, _ in lt)
        if rem <= ln:
            cur_n, cur_col = n, rem
            break
        rem -= ln + 1
    if cur_col is None:
        cur_col = sum(len(t) for t, _ in toks[-1]) if toks else 0
    y = g["code_top"]
    for n, lt in enumerate(toks[:cur_n + 1]):
        if n == cur_n:
            d.rectangle([g["sx0"] + 4, y - 2, g["sx1"] - 4, y + lh - 3], fill=(16, 38, 54))
        d.text((x0, y), str(start + n).rjust(2), font=font, fill=(70, 100, 130))
        shown, limit = 0, (cur_col if n == cur_n else 10 ** 6)
        for text, colr in lt:
            if shown >= limit:
                break
            seg = text[:limit - shown]
            d.text((x0 + gutter + shown * cw, y), seg, font=font, fill=colr)
            shown += len(seg)
        if n == cur_n and cursor:
            cx = x0 + gutter + cur_col * cw
            d.rectangle([cx, y + 1, cx + 2, y + lh - 5], fill=BLUE_LT)
        y += lh
    sf = load_font(13)
    d.text((g["sx0"] + 14, g["sy1"] - 20), f"Ln {start + cur_n}, Col {cur_col + 1}", font=sf, fill=(190, 215, 240))
    # explanation panel under the laptop
    py0, py1 = 574, H - 16
    d.rounded_rectangle([60, py0, W - 60, py1], radius=14, fill=PANEL, outline=(31, 64, 96), width=2)
    d.rectangle([60, py0 + 14, 66, py1 - 14], fill=GOLD)
    cap = screen_clean(caption)
    for size in range(28, 19, -2):
        cf = load_font(size)
        rows = wrap(d, cap, cf, W - 2 * 60 - 60)
        clh = int(size * 1.35)
        if len(rows) * clh <= py1 - py0 - 20:
            break
    maxrows = max(1, (py1 - py0 - 20) // clh)
    if len(rows) > maxrows:
        rows = rows[:maxrows]
        rows[-1] = rows[-1].rstrip(" ,.;:") + "\u2026"
    y = py0 + (py1 - py0 - len(rows) * clh) // 2
    for ln in rows:
        d.text((90, y), ln, font=cf, fill=TEXT)
        y += clh
    d.rectangle([0, H - 8, W, H], fill=(6, 12, 20))
    d.rectangle([0, H - 8, int(W * (idx + 1) / total), H], fill=BLUE_LT)
    return img


def draw_laptop_text(sc, idx, total):
    c = sc["code"]
    lp = laptop_setup(c["lines"], c["fname"], c["start"], c.get("lang", "python"))
    return laptop_frame(lp, sum(len(l) + 1 for l in c["lines"]), sc["body"], idx, total, cursor=False)


def typing_clip(sc, idx, total, mp3, out, tmp):
    """The code appears character by character on the laptop while the lead-in is spoken."""
    lines = sc["lines"]
    lp = laptop_setup(lines, sc["fname"], sc["start"], sc.get("lang", "python"))
    nchars = max(1, sum(len(l) + 1 for l in lines) - 1)
    lead = probe_duration(mp3)
    secs = max(lead + 0.4, min(26.0, max(4.0, nchars / TYPE_CPS)))
    nframes = max(2, int(secs * TYPE_FPS))
    step = secs / nframes
    paths, last_n = [], -1
    for k in range(nframes):
        n = nchars if k == nframes - 1 else int(nchars * (k + 1) / nframes)
        if n == last_n and paths:
            paths.append(paths[-1])
            continue
        last_n = n
        pth = tmp / f"t{idx}_{k}.png"
        laptop_frame(lp, n, sc["speech"], idx, total, cursor=(k % 4 != 3 or k == nframes - 1)).save(pth)
        paths.append(pth)
    hold = 1.2
    listing = tmp / f"t{idx}.txt"
    with open(listing, "w", encoding="utf-8") as fh:
        for k, pth in enumerate(paths):
            fh.write(f"file '{pth}'\nduration {step + (hold if k == len(paths) - 1 else 0):.3f}\n")
        fh.write(f"file '{paths[-1]}'\n")
    dur = secs + hold
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(mp3),
         "-af", f"apad=whole_dur={dur:.2f}", "-t", f"{dur:.2f}", "-vf", f"fps={FPS},format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "64k", "-ar", "24000", "-ac", "1", str(out)])
    for pth in set(paths):
        pth.unlink(missing_ok=True)
    return dur


def draw_table(sc, idx, total):
    img = background()
    d = ImageDraw.Draw(img)
    chrome(img, d, idx, total)
    d.text((60, 70), screen_clean(sc.get("heading", ""))[:60], font=load_font(32, True), fill=GOLD)
    head, rows = sc["head"], sc["rows"]
    ncol = len(head)
    font, hfont = load_font(22), load_font(20, True)
    weights = [max(8, min(34, max(len(head[c]), *(len(r[c]) if c < len(r) else 0 for r in rows)))) for c in range(ncol)]
    tw = W - 2 * 60
    widths = [int(tw * w / sum(weights)) for w in weights]
    y = 150
    x = 60
    d.rectangle([60, y, 60 + tw, y + 48], fill=BLUE_DEEP)
    for c in range(ncol):
        d.text((x + 14, y + 12), head[c].upper()[:30], font=hfont, fill=TEXT)
        x += widths[c]
    y += 48
    for i, r in enumerate(rows):
        cells = [wrap(d, (r[c] if c < len(r) else ""), font, widths[c] - 28)[:3] for c in range(ncol)]
        rh = max(len(c) for c in cells) * 32 + 22
        d.rectangle([60, y, 60 + tw, y + rh], fill=PANEL if i % 2 == 0 else (13, 24, 40))
        x = 60
        for c in range(ncol):
            for k, ln in enumerate(cells[c]):
                d.text((x + 14, y + 11 + k * 32), ln, font=font, fill=BLUE_LT if c == 0 else TEXT)
            x += widths[c]
        y += rh
    return img


def draw_end(sc, idx, total):
    img = background()
    d = ImageDraw.Draw(img)
    chrome(img, d, idx, total, "Tutorial")
    f = load_font(56, True)
    w = d.textlength(sc["title"], font=f)
    d.text(((W - w) / 2, 250), sc["title"], font=f, fill=TEXT)
    uf = load_font(34, True)
    url = sc["url"].replace("https://", "").replace("http://", "")
    w = d.textlength(url, font=uf)
    d.text(((W - w) / 2, 350), url, font=uf, fill=GOLD)
    sf = load_font(24)
    t = "Run every example in your browser - no setup"
    w = d.textlength(t, font=sf)
    d.text(((W - w) / 2, 420), t, font=sf, fill=MUTED)
    return img


RENDER = {"title": draw_title, "section": draw_section, "text": draw_text, "laptop_text": draw_laptop_text,
          "table": draw_table, "end": draw_end}


# ---------------------------------------------------------------- audio / video
async def _edge(text, out, voice):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=RATE).save(out)


def probe_duration(path):
    p = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)])
    return float(p.stdout.decode().strip())


def silence(out, secs):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", f"{secs:.2f}",
         "-c:a", "libmp3lame", str(out)])


def synth(text, out):
    if not text.strip():
        silence(out, 0.3)
        return
    if TTS_FAKE:
        silence(out, max(1.5, len(text.split()) / 2.6))
        return
    voices = [VOICE] + [v for v in VOICE_FALLBACKS if v != VOICE]
    last = None
    for attempt in range(6):
        v = voices[min(attempt // 2, len(voices) - 1)]
        try:
            asyncio.run(_edge(text, str(out), v))
            if Path(out).exists() and Path(out).stat().st_size > 1000:
                return
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"narration failed: {last}")


def make_clip(png, mp3, out, pad):
    dur = probe_duration(mp3) + pad
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(png), "-i", str(mp3),
         "-af", f"apad=pad_dur={pad:.2f}", "-t", f"{dur:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "27", "-pix_fmt", "yuv420p",
         "-r", str(FPS), "-c:a", "aac", "-b:a", "64k", "-ar", "24000", "-ac", "1", str(out)])
    return dur


def stamp(secs):
    secs = int(secs)
    return f"{secs // 60}:{secs % 60:02d}"


def render_video(scenes, stem, title, desc, link):
    """Render one list of scenes to out/<stem>.mp4 plus out/<stem>.description.txt."""
    tmp = Path(tempfile.mkdtemp(prefix="tut_"))
    clips, t, chapters = [], 0.0, []
    try:
        for i, sc in enumerate(scenes):
            png, mp3, clip = tmp / f"s{i}.png", tmp / f"a{i}.mp3", tmp / f"c{i}.mp4"
            synth(sc.get("speech", ""), mp3)
            if sc.get("chapter"):
                chapters.append((t, sc["chapter"]))
            if sc["kind"] == "code":
                t += typing_clip(sc, i, len(scenes), mp3, clip, tmp)
            else:
                RENDER[sc["kind"]](sc, i, len(scenes)).save(png)
                t += make_clip(png, mp3, clip, sc.get("pad", 0.9))
            clips.append(clip)
            if (i + 1) % 10 == 0 or i + 1 == len(scenes):
                log(f"  slide {i + 1}/{len(scenes)} ready ({t / 60:.1f} min so far)")
        listing = tmp / "list.txt"
        listing.write_text("".join(f"file '{c}'\n" for c in clips), encoding="utf-8")
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        final = OUT_DIR / f"{stem}.mp4"
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
             "-c", "copy", "-movflags", "+faststart", str(final)])
        lines = [title, "", desc, ""]
        if link:
            lines += [f"Read the tutorial and run the code in your browser: {link}", ""]
        chapters = [(c_t, c) for c_t, c in chapters if c]
        if len(chapters) >= 2:
            lines += ["Chapters:"]
            if chapters[0][0] > 1:
                lines += ["0:00 Intro"]
            lines += [f"{stamp(c_t)} {c}" for c_t, c in chapters]
        (OUT_DIR / f"{stem}.description.txt").write_text("\n".join(lines), encoding="utf-8")
        log(f"  done: {final} ({final.stat().st_size / 1048576:.1f} MB, {t / 60:.1f} min)")
        return final
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def estimate_minutes(scenes):
    """Rough running time: narration at ~2.5 words a second plus the time spent typing code."""
    t = 0.0
    for sc in scenes:
        if sc["kind"] == "code":
            n = sum(len(l) + 1 for l in sc["lines"])
            t += max(4.0, min(26.0, n / TYPE_CPS)) + 1.2
        else:
            t += len(sc.get("speech", "").split()) / 2.5 + 0.9
    return t / 60


def split_videos(scenes, meta):
    """One video per topic (each <h2> section that contains code), plus an overview for the opening sections."""
    title_sc, end_sc, body = scenes[0], scenes[-1], scenes[1:-1]
    groups = []
    for sc in body:
        if sc["kind"] == "section" or not groups:
            groups.append([sc.get("title") or meta["title"], []])
        groups[-1][1].append(sc)
    overview, vids = [], []
    for gtitle, items in groups:
        if any(x["kind"] == "code" for x in items):
            vids.append({"title": gtitle, "scenes": items})
        elif not vids:
            overview += items
        else:
            vids[-1]["scenes"] += items          # closing remarks go with the last topic
    out = []
    if sum(len(x.get("speech", "").split()) for x in overview) >= 40:
        out.append(("overview", [title_sc] + overview + [end_sc]))
    for v in vids:
        items = v["scenes"][1:] if v["scenes"][0]["kind"] == "section" else v["scenes"]
        head = dict(title_sc, title=v["title"], desc=meta["title"], speech=speak_clean(v["title"]))
        out.append((slugify(v["title"])[:30], [head] + items + [end_sc]))
    return out


def main():
    src = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PAGE", "")).strip()
    if not src:
        log("Give the tutorial page: a URL or an .html file, e.g. python tutorial_video.py https://poetic-bytes.vercel.app/shopping-cart.html")
        return 1
    log(f"tutorial_video.py {SCRIPT_VERSION}  page: {src}")
    page_html, page_url = get_page(src)
    scenes, meta = build_scenes(page_html, page_url, limit=10 ** 9)
    kinds = {}
    for s_ in scenes:
        kinds[s_["kind"]] = kinds.get(s_["kind"], 0) + 1
    words = sum(len(s_.get("speech", "").split()) for s_ in scenes)
    est = estimate_minutes(scenes)
    log(f"  '{meta['title']}': {len(scenes)} slides {kinds}, {words} narrated words, about {est:.0f} min in one video")
    log("  outline of what will be made:")
    for i, s_ in enumerate(scenes):
        if s_["kind"] == "section":
            log(f"    section: {s_.get('title', '')[:60]}")
        elif s_["kind"] == "code" and s_["part"][0] == 1:
            log(f"      code:  {s_.get('name', '')[:50]}  ({s_['fname']}, {len(s_['lines'])}+ lines)")
    if os.environ.get("OUTLINE_ONLY") == "1":
        return 0
    if kinds.get("code", 0) < MIN_CODE_BLOCKS:
        log(f"  skipped: only {kinds.get('code', 0)} code block(s), so this does not look like a tutorial page")
        return 3

    base = os.environ.get("OUT_NAME") or slugify(meta["title"])
    if SPLIT_MODE == "1" or (SPLIT_MODE == "auto" and (est > SPLIT_MINUTES or words > MAX_WORDS)):
        vids = split_videos(scenes, meta)
        log(f"  long page: making {len(vids)} videos, one per topic")
        for n, (name, vscenes) in enumerate(vids, 1):
            title = meta["title"] if name == "overview" else next(x["title"] for x in vscenes if x["kind"] == "title")
            log(f"\
--- video {n}/{len(vids)}: {name}")
            render_video(vscenes, f"{base}--{n:02d}-{name}", title, meta["desc"], meta["link"])
    else:
        scenes, _ = build_scenes(page_html, page_url, limit=MAX_WORDS)
        render_video(scenes, base, meta["title"], meta["desc"], meta["link"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
