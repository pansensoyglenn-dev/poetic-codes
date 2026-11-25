#!/usr/bin/env python3
"""Assemble the documentary from beats.py.

Folder layout expected next to this file:
  assets/beat_01.png ... beat_NN.png   (one image per beat, generated from the AI prompts)
  audio/beat_01.wav  ... beat_NN.wav   (one narration file per beat: your own voice or any TTS)
  music/bed.mp3                        (optional, looped under the narration)

Run:  python3 build_video.py
Output: documentary.mp4 and documentary.srt
Requires: ffmpeg + ffprobe on PATH.
"""
import os
import subprocess
import tempfile

from beats import BEATS

W, H, FPS = 1920, 1080, 30
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
WORDS_PER_SEC = 2.33  # fallback length when no audio file exists


def run(cmd):
    subprocess.run(cmd, check=True)


def audio_len(path, fallback):
    if not os.path.exists(path):
        return fallback
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", path])
    return float(out.strip())


def motion_filter(kind, frames):
    # zoompan on a 2x-upscaled still gives smooth Ken Burns movement
    centre = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if kind == "out":
        z = f"z='max(1.15-0.15*on/{frames},1.0)'"
        return f"{z}:{centre}"
    if kind == "left":
        return f"z=1.12:x='(iw-iw/zoom)*(1-on/{frames})':y='ih/2-(ih/zoom/2)'"
    if kind == "right":
        return f"z=1.12:x='(iw-iw/zoom)*(on/{frames})':y='ih/2-(ih/zoom/2)'"
    return f"z='min(1.0+0.15*on/{frames},1.15)':{centre}"  # "in"


def srt_time(t):
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int((s % 1) * 1000):03d}"


def main():
    tmp = tempfile.mkdtemp(prefix="doc_")
    clips, srt, t = [], [], 0.0

    for i, b in enumerate(BEATS, 1):
        n = f"{i:02d}"
        img = f"assets/beat_{n}.png"
        wav = f"audio/beat_{n}.wav"
        est = max(5.0, len(b["narr"].split()) / WORDS_PER_SEC)
        a_len = audio_len(wav, est)
        dur = a_len + b["pause"]          # pause marker = silence after the line
        frames = int(dur * FPS)
        clip = os.path.join(tmp, f"clip_{n}.mp4")

        # callout text goes in a file so quotes/colons never break the filter
        txt = os.path.join(tmp, f"callout_{n}.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write(b["callout"])

        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan={motion_filter(b['motion'], frames)}:d={frames}:s={W}x{H}:fps={FPS},"
              f"fade=t=in:st=0:d=0.3,fade=t=out:st={dur-0.3:.2f}:d=0.3")
        if b["callout"]:
            vf += (f",drawtext=fontfile={FONT}:textfile={txt}:fontsize=44:fontcolor=white:"
                   f"box=1:boxcolor=black@0.55:boxborderw=18:x=(w-text_w)/2:y=h-170:"
                   f"enable='between(t,0.5,{dur-0.5:.2f})'")

        cmd = ["ffmpeg", "-y", "-loglevel", "error"]
        if os.path.exists(img):
            cmd += ["-i", img]
        else:  # placeholder card so the build still runs before images exist
            cmd += ["-f", "lavfi", "-i", f"color=c=0x1e2b3a:s={W}x{H}:d=1"]
        if os.path.exists(wav):
            cmd += ["-i", wav, "-af", f"apad=pad_dur={b['pause']}"]
        else:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-vf", vf, "-t", f"{dur:.2f}", "-r", str(FPS),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", clip]
        run(cmd)
        clips.append(clip)

        srt.append(f"{i}\n{srt_time(t)} --> {srt_time(t + a_len)}\n{b['narr']}\n")
        t += dur

    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{c}'\n" for c in clips)
    joined = os.path.join(tmp, "joined.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", joined])

    if os.path.exists("music/bed.mp3"):   # quiet music bed under narration
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", joined,
             "-stream_loop", "-1", "-i", "music/bed.mp3",
             "-filter_complex",
             "[1:a]volume=0.10[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
             "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "documentary.mp4"])
    else:
        os.replace(joined, "documentary.mp4")

    with open("documentary.srt", "w", encoding="utf-8") as f:
        f.write("\n".join(srt))
    print(f"Done: documentary.mp4 ({t/60:.1f} min) + documentary.srt")


if __name__ == "__main__":
    main()
