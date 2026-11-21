#!/usr/bin/env python3
"""
build_video.py - turn a Poetic Bytes lesson page into a narrated tutorial video.

  python build_video.py numbers.html --out out            # full video
  python build_video.py numbers.html --out out --only 3   # first 3 lessons (quick test)

Needs: ffmpeg, Pillow, pygments, beautifulsoup4 (+ lxml), and edge-tts for the neural voice.
Without edge-tts it still builds the video, but silent (timing placeholder) so you can check the layout.
Outputs in --out: tutorial.mp4, subtitles.srt, chapters.txt, youtube_description.txt, narration_script.txt
"""
import argparse, asyncio, os, re, subprocess, sys, textwrap, shutil
from pathlib import Path
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont
from pygments import lex
from pygments.lexers import PythonLexer
from pygments.token import Token
import importlib
N = importlib.import_module(os.environ.get("NARRATION", "narration"))   # narration.py (Numbers) or e.g. narration_operators.py

W, H = 1920, 1080
BG, PANEL, BORDER = "#0B121C", "#111B2A", "#22324A"
TXT, MUTED, BLUE, GOLD, GREEN = "#E6EDF3", "#8B9BB0", "#58A6FF", "#E3B341", "#3FB950"
TOK = {Token.Keyword: "#FF7B72", Token.Name.Builtin: "#79C0FF", Token.Literal.String: "#A5D6FF",
       Token.Literal.Number: "#79C0FF", Token.Comment: "#8B949E", Token.Operator: "#FF7B72",
       Token.Name.Function: "#D2A8FF", Token.Name.Namespace: "#FFA657"}

def find_font(names):
    for n in names:
        for d in ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/truetype/liberation"):
            p = Path(d) / n
            if p.exists(): return str(p)
    out = subprocess.run(["fc-match", "-f", "%{file}", names[0].split(".")[0]], capture_output=True, text=True).stdout
    return out or None
F_SANS = find_font(["DejaVuSans.ttf"]); F_BOLD = find_font(["DejaVuSans-Bold.ttf"]); F_MONO = find_font(["DejaVuSansMono.ttf"])
def font(path, size): return ImageFont.truetype(path, size)

# ---------- read the lessons from the HTML page ----------
def lesson_code(cc):
    """The program text. Uses data-code, but falls back to the visible code box when data-code is broken
    (for example, an unescaped quote inside the attribute cuts the program short)."""
    code = cc.get("data-code") or ""
    try:
        compile(code, "<lesson>", "exec")
        return code
    except SyntaxError:
        snip = cc.select_one(".code-snippet pre") or cc.select_one("pre")
        if snip:
            alt = snip.get_text()
            try:
                compile(alt, "<lesson>", "exec")
                print("NOTE: data-code was cut short; using the code shown on the page instead.")
                return alt
            except SyntaxError:
                pass
        return code

def read_lessons(html_path):
    soup = BeautifulSoup(open(html_path, encoding="utf-8").read(), "lxml")
    out = {}
    for b in soup.find_all(class_="oop-block"):
        h3, cc = b.find("h3"), b.find(class_="code-container")
        if not h3 or not cc: continue
        m = re.search(r"(\d+\.\d+)", h3.get_text())
        if not m: continue
        p = b.find("p")
        out[m.group(1)] = {
            "intro": p.get_text(" ", strip=True) if p else "",
            "steps": [re.sub(r"^Step \d+:\s*", "", li.get_text(" ", strip=True)) for li in b.select(".step-list li")],
            "code": lesson_code(cc),
        }
    return out

def run_code(code):
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=30)
    return (r.stdout if r.returncode == 0 else r.stdout + r.stderr).rstrip("\n")

# ---------- drawing ----------
def base(title_right, idx, total):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.text((80, 52), "POETIC BYTES", font=font(F_BOLD, 30), fill=BLUE)
    d.text((W - 80, 52), title_right, font=font(F_SANS, 28), fill=MUTED, anchor="ra")
    d.line((80, 112, W - 80, 112), fill=BORDER, width=2)
    d.rectangle((0, H - 10, W, H), fill=PANEL)
    d.rectangle((0, H - 10, int(W * idx / max(total, 1)), H), fill=BLUE)
    d.text((80, H - 62), "poetic-bytes.vercel.app", font=font(F_SANS, 24), fill=MUTED)
    return im, d

def wrap(d, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= width: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def slide_title(title, sub, bullets, idx, total):
    im, d = base("Python tutorial", idx, total)
    d.text((W // 2, 300), title, font=font(F_BOLD, 84), fill=TXT, anchor="mm")
    d.text((W // 2, 400), sub, font=font(F_SANS, 38), fill=GOLD, anchor="mm")
    y = 520
    for b in bullets:
        d.text((W // 2, y), b, font=font(F_SANS, 38), fill=MUTED, anchor="mm"); y += 66
    return im

def slide_concept(num, title, intro, steps, idx, total):
    im, d = base("Python Numbers", idx, total)
    d.rounded_rectangle((80, 160, 330, 220), 14, fill=PANEL, outline=BLUE, width=2)
    d.text((205, 190), f"Lesson {num}", font=font(F_BOLD, 30), fill=BLUE, anchor="mm")
    d.text((80, 250), title, font=font(F_BOLD, 74), fill=TXT)
    y = 360
    for ln in wrap(d, intro, font(F_SANS, 38), W - 160): d.text((80, y), ln, font=font(F_SANS, 38), fill=MUTED); y += 54
    y += 30
    d.text((80, y), "What you will do", font=font(F_BOLD, 34), fill=GOLD); y += 66
    for i, s in enumerate(steps, 1):
        lines = wrap(d, s, font(F_SANS, 36), W - 260)
        d.ellipse((80, y + 2, 130, y + 52), fill=PANEL, outline=BLUE, width=2)
        d.text((105, y + 27), str(i), font=font(F_BOLD, 28), fill=BLUE, anchor="mm")
        for ln in lines: d.text((160, y + 4), ln, font=font(F_SANS, 36), fill=TXT); y += 50
        y += 18
    return im

def slide_code(num, title, code, output, varies, idx, total):
    im, d = base(f"Lesson {num}  ·  {title}", idx, total)
    lines = code.split("\n")
    size = 34 if len(lines) <= 12 else 29 if len(lines) <= 16 else 25
    f = font(F_MONO, size); lh = int(size * 1.5)
    px, pw = 80, 1040
    ph = max(lh * len(lines) + 90, 420)
    d.rounded_rectangle((px, 150, px + pw, 150 + ph), 18, fill=PANEL, outline=BORDER, width=2)
    d.text((px + 28, 172), "python", font=font(F_SANS, 24), fill=MUTED)
    # syntax-highlight line by line
    y0 = 225; x = px + 28; y = y0; col = x
    for ttype, val in lex(code, PythonLexer()):
        color = TXT
        t = ttype
        while t is not Token and t not in TOK: t = t.parent
        color = TOK.get(t, TXT)
        for k, part in enumerate(val.split("\n")):
            if k > 0: y += lh; col = x
            if part:
                d.text((col, y), part, font=f, fill=color); col += d.textlength(part, font=f)
    ox, ow = px + pw + 40, W - 80 - (px + pw + 40)
    d.rounded_rectangle((ox, 150, ox + ow, 150 + ph), 18, fill="#0A0F18", outline=GREEN, width=2)
    d.text((ox + 28, 172), "Output", font=font(F_SANS, 24), fill=GREEN)
    fo = font(F_MONO, min(size, 30)); loh = int(min(size, 30) * 1.5); y = 225
    for ln in output.split("\n")[:15]:
        while d.textlength(ln, font=fo) > ow - 56 and len(ln) > 4: ln = ln[:-2]; trunc = True
        else: pass
        shown = ln
        d.text((ox + 28, y), shown, font=fo, fill="#C9F7D1"); y += loh
    if varies:
        d.text((ox + 28, 150 + ph - 46), "Random values: your output will differ.", font=font(F_SANS, 24), fill=GOLD)
    return im


# ---------- laptop scene: code is typed step by step while the narrator explains ----------
CW = 0.602  # DejaVu Sans Mono character width / font size

def line_tokens(code):
    lines, cur = [], []
    for ttype, val in lex(code, PythonLexer()):
        t = ttype
        while t is not Token and t not in TOK: t = t.parent
        color = TOK.get(t, TXT)
        for k, part in enumerate(val.split("\n")):
            if k > 0: lines.append(cur); cur = []
            if part: cur.append((part, color))
    lines.append(cur)
    return lines[:len(code.split("\n"))]

class Laptop:
    SX, SY, SW, SH = 130, 150, 1660, 785          # screen (outer)
    IX, IY, IW, IH = 160, 175, 1600, 735          # inner display
    def __init__(self, num, title, code, output, idx, total, nsteps):
        self.code_lines = code.split("\n"); self.tokens = line_tokens(code)
        self.out_lines = output.split("\n") if output else []
        n, ml = len(self.code_lines), max(len(l) for l in self.code_lines)
        best = None
        for ew in (880, 960, 1040, 1120):
            size = min(30, 650 / (n * 1.55), (ew - 120) / (CW * ml))
            if self.IW - ew >= 520 and (best is None or size > best[0] + 0.5): best = (size, ew)
        self.size, self.ew = int(best[0]), best[1]
        self.lh = int(self.size * 1.55)
        self.f = font(F_MONO, self.size)
        mo = max([len(l) for l in self.out_lines] + [10])
        tw = self.IW - self.ew
        self.fo = font(F_MONO, int(max(20, min(26, (tw - 60) / (CW * mo)))))
        self.loh = int(self.fo.size * 1.55)
        self.bg = self._background(num, title, idx, total, nsteps)

    def _background(self, num, title, idx, total, nsteps):
        im, d = base(f"Lesson {num}  ·  {title}", idx, total)
        # soft glow + desk shadow
        d.ellipse((120, 960, W - 120, 1010), fill="#070C14")
        # screen shell
        d.rounded_rectangle((self.SX, self.SY, self.SX + self.SW, self.SY + self.SH), 30, fill="#05080D", outline="#2F3B4E", width=4)
        d.ellipse((self.SX + self.SW // 2 - 5, self.SY + 8, self.SX + self.SW // 2 + 5, self.SY + 18), fill="#16202E")
        # base / keyboard deck
        d.polygon([(80, 935), (W - 80, 935), (W - 30, 985), (30, 985)], fill="#2A3342", outline="#3A475B")
        d.rounded_rectangle((W // 2 - 130, 935, W // 2 + 130, 952), 8, fill="#1E2632")
        # editor
        ix, iy, ew, ih = self.IX, self.IY, self.ew, self.IH
        d.rectangle((ix, iy, ix + self.IW, iy + ih), fill="#0A0F18")
        d.rectangle((ix, iy, ix + ew, iy + ih), fill="#0D1520")
        d.rectangle((ix, iy, ix + ew, iy + 44), fill="#142033")
        for k, c in enumerate(("#FF5F56", "#FFBD2E", "#27C93F")): d.ellipse((ix + 18 + 26 * k, iy + 14, ix + 32 + 26 * k, iy + 28), fill=c)
        d.text((ix + ew // 2, iy + 22), f"lesson_{num.replace('.', '_')}.py  —  Python 3.12", font=font(F_SANS, 22), fill=MUTED, anchor="mm")
        d.rectangle((ix, iy + 44, ix + 62, iy + ih), fill="#0B121C")
        # terminal
        tx = ix + ew
        d.rectangle((tx, iy, ix + self.IW, iy + 44), fill="#10202A")
        d.text((tx + 24, iy + 22), "Terminal", font=font(F_SANS, 22), fill=GREEN, anchor="lm")
        d.line((tx, iy, tx, iy + ih), fill=BORDER, width=2)
        d.text((tx + 24, iy + 64), "$ python lesson.py", font=font(F_MONO, 22), fill=MUTED)
        self.nsteps = nsteps
        return im

    def frame(self, typed, hl, outn, step, caret=None, blink=True):
        im = self.bg.copy(); d = ImageDraw.Draw(im)
        ix, iy = self.IX, self.IY
        top = iy + 62
        if hl:
            a, b = hl
            d.rectangle((ix + 62, top + (a - 1) * self.lh - 4, ix + self.ew - 6, top + b * self.lh - 2), fill="#16294A")
            d.rectangle((ix + 62, top + (a - 1) * self.lh - 4, ix + 68, top + b * self.lh - 2), fill=BLUE)
        for i, toks in enumerate(self.tokens):
            y = top + i * self.lh
            d.text((ix + 50, y), str(i + 1), font=font(F_MONO, max(14, self.size - 6)), fill=("#58A6FF" if hl and hl[0] <= i + 1 <= hl[1] else "#445168"), anchor="ra")
            n = typed[i]
            x = ix + 84
            for text, color in toks:
                if n <= 0: break
                seg = text[:n]; d.text((x, y), seg, font=self.f, fill=color)
                x += d.textlength(seg, font=self.f); n -= len(text)
            if caret == i and blink: d.rectangle((x + 2, y + 2, x + 2 + int(self.size * 0.5), y + self.lh - 8), fill=TXT)
        # terminal output
        ty = iy + 112
        for ln in self.out_lines[:outn]:
            tw = self.IW - self.ew - 48
            while d.textlength(ln, font=self.fo) > tw and len(ln) > 4: ln = ln[:-2] + "…" if not ln.endswith("…") else ln[:-2] + "…"
            d.text((ix + self.ew + 24, ty), ln, font=self.fo, fill="#C9F7D1"); ty += self.loh
        # step pill
        if step:
            d.rounded_rectangle((W - 80 - 250, 124, W - 80, 148), 12, fill=PANEL, outline=BLUE, width=2)
            d.text((W - 80 - 125, 136), f"Step {step} of {self.nsteps}", font=font(F_BOLD, 18), fill=BLUE, anchor="mm")
        return im

def build_code_scene(lesson, meta, code, output, idx, total, work, tag, voice, rate, have_tts):
    """Returns (clip_path, duration, [(start, end, sentence)], have_tts)."""
    sents = re.split(r"(?<=[.!?])\s+", lesson["walk"].strip())
    cues = N.CUES.get(lesson["id"], [])
    lap = Laptop(lesson["id"], lesson["title"], code, output, idx, total, max(len(cues), 1))
    nlines = len(lap.code_lines)
    typed = [0] * nlines
    typed_upto = 0
    frames, wavs, timeline, t = [], [], [], 0.0
    for k, s in enumerate(sents):
        mp3 = work / f"{tag}_{k:02d}.mp3"
        if have_tts and tts(s, mp3, voice, rate): pass
        else:
            if have_tts: print("NOTE: edge-tts not installed -> building a SILENT preview."); have_tts = False
            silence(mp3, max(1.5, len(s.split()) / 2.6))
        wav = work / f"{tag}_{k:02d}.wav"
        dur = duration(mp3) + 0.25
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3), "-af", "apad=pad_dur=0.25", "-t", f"{dur:.3f}",
                        "-ar", "44100", "-ac", "1", str(wav)], check=True)
        wavs.append(wav); timeline.append((t, t + dur - 0.25, s)); t += dur
        if k < len(cues):
            a, b, outn = cues[k]; step = k + 1; hl = (a, b)
            todo = [i for i in range(typed_upto, b) if typed[i] < len(lap.code_lines[i])]
            chars = sum(len(lap.code_lines[i]) - typed[i] for i in todo)
            tt = min(dur * 0.7, max(0.5, chars / 26.0)) if chars else 0.0
            nfr = max(1, int(round(tt * 5))) if chars else 0
            order = [(i, c) for i in todo for c in range(typed[i] + 1, len(lap.code_lines[i]) + 1)]
            for f in range(nfr):
                upto = int(len(order) * (f + 1) / nfr)
                cur = typed[:]
                for i, c in order[:upto]: cur[i] = max(cur[i], c)
                car = order[upto - 1][0] if upto else None
                frames.append((lap.frame(cur, hl, 0 if outn else 0, step, caret=car, blink=(f % 2 == 0)), tt / nfr))
            for i in todo: typed[i] = len(lap.code_lines[i])
            typed_upto = max(typed_upto, b)
            frames.append((lap.frame(typed, hl, outn, step), dur - (tt if chars else 0)))
        else:
            for i in range(nlines): typed[i] = len(lap.code_lines[i])
            frames.append((lap.frame(typed, None, len(lap.out_lines), None), dur))
    lst = work / f"{tag}_frames.txt"; parts = []
    for n, (img, dd) in enumerate(frames):
        p = work / f"{tag}_f{n:04d}.png"; img.save(p); parts.append(f"file '{p.resolve()}'\nduration {dd:.3f}\n")
    parts.append(f"file '{(work / f'{tag}_f{len(frames)-1:04d}.png').resolve()}'\n")
    lst.write_text("".join(parts))
    alst = work / f"{tag}_a.txt"; alst.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    scene_wav = work / f"{tag}.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(alst), "-c", "copy", str(scene_wav)], check=True)
    clip = work / f"{tag}.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(scene_wav),
                    "-vf", "fps=10,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-b:a", "160k",
                    "-ar", "44100", "-ac", "1", "-t", f"{t:.3f}", str(clip)], check=True)
    for p in work.glob(f"{tag}_f*.png"): p.unlink()
    return clip, t, timeline, have_tts

def slide_outro(bullets, idx, total):
    im, d = base("Python tutorial", idx, total)
    d.text((W // 2, 250), "You've mastered Python numbers", font=font(F_BOLD, 74), fill=TXT, anchor="mm")
    y = 380
    for b in bullets:
        d.text((W // 2 - 520, y), "✓", font=font(F_BOLD, 40), fill=GREEN)
        d.text((W // 2 - 460, y), b, font=font(F_SANS, 40), fill=TXT); y += 78
    d.text((W // 2, y + 70), "Practice every lesson free at poetic-bytes.vercel.app", font=font(F_SANS, 38), fill=GOLD, anchor="mm")
    return im

# ---------- audio ----------
FALLBACK_VOICES = ["en-US-AndrewNeural", "en-US-GuyNeural", "en-GB-RyanNeural", "en-US-AriaNeural"]

def _tts_once(text, path, voice, rate):
    import edge_tts
    async def go():
        await edge_tts.Communicate(text, voice, rate=rate).save(str(path))
    asyncio.run(go())
    if not Path(path).exists() or Path(path).stat().st_size < 500:
        raise RuntimeError("empty audio file")

def tts(text, path, voice, rate):
    """Speak `text` into an mp3. Long text is cut into sentence groups; each is retried, and other voices are tried if needed."""
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    import time
    voice = (voice or "").strip() or FALLBACK_VOICES[0]
    rate = (rate or "").strip()
    if not re.fullmatch(r"[+-]\d+%", rate): rate = "+0%"
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    groups, cur = [], ""
    for s_ in sents:
        if cur and len(cur) + len(s_) > 350: groups.append(cur); cur = s_
        else: cur = (cur + " " + s_).strip()
    if cur: groups.append(cur)
    voices = [voice] + [v for v in FALLBACK_VOICES if v != voice]
    parts = []
    for gi, g in enumerate(groups):
        part = Path(f"{path}.p{gi}.mp3"); ok = False; last = None
        for v in voices:
            for attempt in range(3):
                try:
                    _tts_once(g, part, v, rate); ok = True; break
                except Exception as e:
                    last = e; time.sleep(1.5 * (attempt + 1))
            if ok:
                if v != voice: print(f"NOTE: voice {voice} failed, used {v}")
                break
        if not ok:
            raise SystemExit(f"ERROR: the narrator voice failed on: {g[:80]!r}\nLast error: {last!r}\n"
                             "Try again in a few minutes, or run the workflow with another voice (en-US-GuyNeural).")
        parts.append(part)
    if len(parts) == 1:
        shutil.move(str(parts[0]), str(path))
    else:
        lst = Path(f"{path}.txt"); lst.write_text("".join(f"file '{Path(p).resolve()}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-c:a", "libmp3lame", "-b:a", "96k", str(path)], check=True)
        for p in parts: Path(p).unlink(missing_ok=True)
    return True

def silence(path, seconds):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", f"{seconds:.2f}", "-c:a", "libmp3lame", str(path)], check=True)

def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())

def make_clip(png, audio, out, pad=0.6):
    dur = duration(audio) + pad
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "5", "-i", str(png), "-i", str(audio),
                    "-filter_complex", f"[1:a]apad=pad_dur={pad}[a]", "-map", "0:v", "-map", "[a]",
                    "-t", f"{dur:.2f}", "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "10",
                    "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "1", str(out)], check=True)
    return dur

def srt_time(t):
    h, m = int(t // 3600), int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{int(s):02d},{int((s % 1) * 1000):03d}"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html"); ap.add_argument("--out", default="out"); ap.add_argument("--only", type=int, default=0)
    ap.add_argument("--voice", default=os.environ.get("VOICE", N.VOICE_DEFAULT))
    ap.add_argument("--rate", default=os.environ.get("RATE", "-4%"))
    a = ap.parse_args()
    out = Path(a.out); work = out / "work"; shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True, exist_ok=True)
    page = read_lessons(a.html)
    raw = open(a.html, encoding="utf-8", errors="replace").read()
    print(f"Lesson page: {a.html}  size={len(raw)} bytes  oop-block={raw.count('oop-block')}  code-container={raw.count('code-container')}  lessons found={sorted(page)}")
    if not page:
        sys.exit("ERROR: no lessons were found in this page. It must be the full python-numbers.html (about 127 KB, with 16 programs).\n"
                 f"This file is {len(raw)} bytes and starts with: {raw[:150]!r}")
    lessons = [l for l in N.LESSONS if l["id"] in page]
    if a.only: lessons = lessons[:a.only]
    missing = [l["id"] for l in N.LESSONS if l["id"] not in page]
    if missing: print("WARNING: lessons in narration but not in the page:", missing)

    total = 2 + 2 * len(lessons)
    IB = getattr(N, "INTRO_BULLETS", ["Integers  ·  Floats  ·  Complex numbers", "Arithmetic  ·  math module  ·  random",
                                      "Decimal & Fraction  ·  Number formatting"])
    OB = getattr(N, "OUTRO_BULLETS", ["Integers have unlimited size", "Floats are fast but approximate", "Complex numbers use j",
                                      "math and random extend Python", "Decimal and Fraction are exact", "Format specifiers control display"])
    scenes = [("intro", "Introduction", slide_title(N.TITLE, getattr(N, "SUBTITLE", "A professional, step-by-step guide"),
                IB, 1, total), " ".join(N.INTRO))]
    i = 2
    for l in lessons:
        p = page[l["id"]]
        outp = run_code(p["code"])
        varies = "import random" in p["code"] and "seed" not in p["code"]
        scenes.append((l["id"], f'{l["id"]} {l["title"]}', slide_concept(l["id"], l["title"], p["intro"], p["steps"], i, total), l["concept"])); i += 1
        scenes.append((None, None, ("code", l, p["code"], outp, i), l["walk"])); i += 1
    scenes.append(("outro", "Recap and next steps", slide_outro(
        OB, total, total), " ".join(N.OUTRO)))

    clips, t, chapters, srt, narr_txt = [], 0.0, [], [], []
    have_tts = True
    for n, (chap, label, img, text) in enumerate(scenes):
        clip = work / f"s{n:03d}.mp4"
        if isinstance(img, tuple) and img[0] == "code":
            _, les, code, outp, sidx = img
            clip, d, tl, have_tts = build_code_scene(les, None, code, outp, sidx, total, work, f"s{n:03d}", a.voice, a.rate, have_tts)
            for (s0, e0, x) in tl: srt.append((t + s0, t + e0, x))
            narr_txt.append((label or "") + "\n" + text + "\n")
            clips.append(clip); t += d
            print(f"  scene {n+1}/{len(scenes)}  {d:5.1f}s  (laptop)")
            continue
        png = work / f"s{n:03d}.png"; img.save(png)
        mp3 = work / f"s{n:03d}.mp3"
        if have_tts and tts(text, mp3, a.voice, a.rate):
            pass
        else:
            if have_tts: print("NOTE: edge-tts not installed -> building a SILENT preview."); have_tts = False
            silence(mp3, max(3.0, len(text.split()) / 2.5))
        d = make_clip(png, mp3, clip)
        if chap: chapters.append((t, label))
        sents = re.split(r"(?<=[.!?])\s+", text); tot = sum(len(s) for s in sents); tt = t
        for s in sents:
            dd = (d - 0.6) * len(s) / tot
            srt.append((tt, tt + dd, s)); tt += dd
        narr_txt.append((label or "") + "\n" + text + "\n")
        clips.append(clip); t += d
        print(f"  scene {n+1}/{len(scenes)}  {d:5.1f}s")

    lst = work / "list.txt"; lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                    "-movflags", "+faststart", str(out / "tutorial.mp4")], check=True)
    (out / "subtitles.srt").write_text("".join(f"{k}\n{srt_time(s)} --> {srt_time(e)}\n{x}\n\n" for k, (s, e, x) in enumerate(srt, 1)))
    ch = "\n".join(f"{int(s//60):02d}:{int(s%60):02d} {lab}" for s, lab in chapters)
    (out / "chapters.txt").write_text(ch + "\n")
    (out / "narration_script.txt").write_text("\n".join(narr_txt))
    (out / "youtube_description.txt").write_text(
        getattr(N, "DESCRIPTION", "Learn every numeric type in Python: integers, floats, complex numbers, arithmetic, the math module, random numbers, "
        "Decimal, Fraction, and number formatting. Every program is shown with its real output and explained step by step.") + "\n\n"
        "Chapters:\n" + ch + "\n\nFree interactive lesson with runnable code: " + getattr(N, "PAGE_URL", "https://poetic-bytes.vercel.app/python-numbers.html") + "\n"
        "#python #pythontutorial #learnpython #programming\n")
    print(f"DONE: {out/'tutorial.mp4'}  ({t/60:.1f} min)  voice={'edge-tts ' + a.voice if have_tts else 'SILENT preview'}")

if __name__ == "__main__":
    main()
