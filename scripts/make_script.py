#!/usr/bin/env python3
"""Generate documentary_script.md (Sections 1-3) from beats.py, with computed timestamps."""
from beats import BEATS, STYLE, SECTION_AUDIO

WPS = 2.33  # ~140 wpm


def mmss(t):
    return f"{int(t // 60)}:{int(t % 60):02d}"


out = ["# England's Conquest and the Rise of the British Empire: Documentary Package\n"]

# ---- timing
t, timed = 0.0, []
for i, b in enumerate(BEATS, 1):
    words = len(b["narr"].split())
    dur = max(5.0, words / WPS)
    timed.append((i, t, t + dur, words, dur))
    t += dur + b["pause"]
total = t

out.append(f"**{len(BEATS)} beats, about {total/60:.1f} minutes at ~140 wpm.** Timestamps below are estimates; "
           "`build_video.py` recomputes them from your real audio.\n")
out.append("## SECTION 1: BEAT-BY-BEAT SCRIPT & EXACT VISUALS\n")
out.append(f"*Global style line appended to every AI prompt:* {STYLE}\n")

last = None
for (i, s, e, words, dur), b in zip(timed, BEATS):
    if b["sec"] != last:
        out.append(f"\n### {b['sec'].upper()}\n")
        last = b["sec"]
    out.append(f"**[{mmss(s)}-{mmss(e)} / Beat {i:02d}]** ({words} words, ~{dur:.0f}s)\n")
    out.append(f"- **NARRATION:** {b['narr']}")
    out.append(f"- **ON-SCREEN VISUAL:** {b['vis']} Camera: slow {b['motion']}. "
               + (f"Callout: \"{b['callout']}\"." if b["callout"] else "No callout."))
    out.append(f"- **AI / STOCK VISUAL PROMPT:** {b['prompt']}\n")

# ---- Section 2
out.append("\n## SECTION 2: AUDIO & PACING GUIDE\n")
out.append("| Section | Beats | Narration tone | Music / ambience |")
out.append("|---|---|---|---|")
secs = []
for i, b in enumerate(BEATS, 1):
    if not secs or secs[-1][0] != b["sec"]:
        secs.append([b["sec"], i, i])
    else:
        secs[-1][2] = i
for name, a, z in secs:
    tone, music, _ = SECTION_AUDIO[name]
    out.append(f"| {name} | {a:02d}-{z:02d} | {tone} | {music} |")

out.append("\n**Pause markers** (silence after the line, in seconds; built into `pause` in beats.py):\n")
for i, b in enumerate(BEATS, 1):
    if b["pause"] >= 1.2:
        out.append(f"- Beat {i:02d}: hold {b['pause']}s. \"{b['narr'][:60]}...\"")

out.append("""
**General rules**
- Keep music about 10% under narration; drop it fully for the slavery, Indigenous-loss and terra nullius beats (silence carries the weight).
- Narration: calm, unhurried, about 140 wpm. Lower the pitch slightly on dispossession and slavery beats; slow down, don't dramatize.
- Opening lines (beats 01-02) are warm and personal; from beat 03 move to an authoritative documentary voice.
- Use real archival images or clearly-labelled illustrations for treaties and documents where possible (public-domain scans of the Treaty of Nanjing, Treaty of Waitangi, Brookes slave-ship plan, etc.). AI images are best for atmosphere, not for documents that need to be exact.
- Ask Aboriginal, Māori and Native American cultural advisers (or use licensed music from those communities) before using traditional instruments.
""")

# ---- Section 3
out.append("\n## SECTION 3: VIDEO GENERATION / ASSEMBLY INSTRUCTIONS\n")
out.append("""**Workflow**
1. Generate one image per beat from the AI prompts (append the style line) at 16:9, save as `assets/beat_01.png`, `beat_02.png`...
2. Record or synthesize narration one file per beat: `audio/beat_01.wav`...
3. Optional: `music/bed.mp3`.
4. Run `python3 build_video.py`. It measures each audio file, adds the pause, applies the beat's camera motion, burns in the map/date callout, and joins everything. Output: `documentary.mp4` + `documentary.srt` (subtitles synced to the audio).

**Map beats:** the callout text is burned in automatically. For animated maps (routes, shaded territories), render a short map image or clip per beat (QGIS, Mapshaper, or an HTML canvas export) and save it as that beat's `assets/beat_NN.png`; the same pipeline works.

**build_video.py**

```python
""")
with open("build_video.py", encoding="utf-8") as f:
    out.append(f.read())
out.append("```\n")

with open("documentary_script.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(len(BEATS), "beats", round(total / 60, 1), "min")
