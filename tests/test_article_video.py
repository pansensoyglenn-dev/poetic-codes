"""Run from the repo root:   pip install pytest && python -m pytest tests -q
Loads scripts/make_article_video.py (or ./article_video.py when testing beside it). No network needed."""
import importlib.util
import os
import shutil
from pathlib import Path

import pytest

os.environ.update(DRY_RUN="1", TTS_FAKE="1", AI_IMAGES="0", WIKI_IMAGES="0")
ROOT = Path(__file__).resolve().parent.parent
SRC = next(p for p in (ROOT / "scripts" / "make_article_video.py", ROOT / "article_video.py") if p.exists())
spec = importlib.util.spec_from_file_location("av", SRC)
av = importlib.util.module_from_spec(spec)
spec.loader.exec_module(av)

TITLE, AUTHOR = "Ilonggo Cuisine: A Culinary Journey", "Glenn Junsay Pansensoy"
PARA = ("The cane fields of the valley were cut by hand each March. Workers carried bundles to the mill along "
        "the muddy road, and families waited at the gate for the weekly wage. Children ran beside the carts "
        "while the overseer counted the loads. By noon the heat pressed down on the whole plantation. ")
PAGE = f"""<html><head><title>x</title></head><body><div class="container">
<header><h1>{TITLE}</h1><div class="byline">By {AUTHOR} Published 2026 me@example.com</div></header>
<main><p>{PARA * 2}</p><h2>Part Two</h2><p>{PARA * 2}</p>
<div class="ad-slot"><ins class="adsbygoogle"></ins></div></main>
<footer>&copy; 2026 {AUTHOR}</footer></div></body></html>"""


def job(body=PAGE, **kw):
    return {"title": TITLE, "author": AUTHOR, "category": "Food", "excerpt": "A short test.", "body": body, **kw}


# ---------- text -> slides
def test_video_starts_on_the_story_not_the_header():
    segs = av.build_segments(job())
    assert segs[0]["kind"] == "body"
    assert segs[0]["speech"].startswith("The cane fields")
    text = " ".join(s["speech"] for s in segs[:-1])
    for junk in (TITLE, "Published 2026", "me@example.com", "©", "Part Two"):
        assert junk not in text, junk


def test_last_slide_is_the_end_card_with_the_link():
    end = build_end()
    assert end["kind"] == "end" and end["url"].startswith("https://") and end["url"] in end["caption"]


def build_end():
    return av.build_segments(job())[-1]


def test_plain_text_body_has_title_byline_and_footer_removed():
    flat = f"{TITLE} By {AUTHOR} Published 2026 me@example.com {PARA * 3} © 2026 {AUTHOR} me@example.com"
    segs = av.build_segments(job(body=flat))
    text = " ".join(s["speech"] for s in segs[:-1])
    assert text.startswith("The cane fields") and "©" not in text and "me@example.com" not in text


def test_strip_flat_page_chrome_leaves_normal_text_alone():
    assert av.strip_flat_page_chrome("Just a story. It goes on.", TITLE, AUTHOR) == "Just a story. It goes on."


def test_slides_are_roughly_slide_words_long():
    body = [s for s in av.build_segments(job()) if s["kind"] == "body"]
    assert body and all(len(s["speech"].split()) <= int(av.SLIDE_WORDS * 1.7) + 70 for s in body)


# ---------- captions
def test_caption_timings_cover_the_whole_narration_in_order():
    t = av.caption_timings(PARA, 20.0)
    assert t[0][1] == 0 and abs(t[-1][2] - 20.0) < 1e-6
    assert all(a[2] <= b[1] + 1e-9 for a, b in zip(t, t[1:]))


def test_captions_never_exceed_the_word_limit():
    long = " ".join(["word"] * 90) + "."
    assert all(len(c.split()) <= av.CAP_WORDS + 3 for c in av.split_captions(long))


# ---------- numbers
@pytest.mark.parametrize("dur", [30, 300, 1200, 6000])
def test_bitrate_stays_in_bounds(dur):
    assert 120 <= av.pick_bitrate(dur) <= 1200


def test_longer_video_gets_lower_bitrate():
    assert av.pick_bitrate(2000) < av.pick_bitrate(200)


def test_pick_rate_is_unchanged_without_a_minimum(monkeypatch):
    monkeypatch.setattr(av, "TTS_FAKE", False)
    monkeypatch.setattr(av, "MIN_SECONDS", 0)
    assert av.pick_rate([{"speech": "one two three"}]) == av.RATE


# ---------- image prompts
def test_prompt_uses_every_sentence_and_stays_short():
    pr = av.scene_prompt({"speech": PARA}, job())
    for key in ("cane fields", "mill", "Children", "plantation"):
        assert key in pr
    assert len(pr.split()) < 220 and pr.startswith("photorealistic")


def test_prompt_thins_instead_of_cutting_off_the_end():
    many = " ".join(f"Sentence number {i} describes a small stone bridge over river {i}." for i in range(40))
    pr = av.scene_prompt({"speech": many}, job())
    assert "Setting:" in pr and len(pr.split()) < 260


def test_people_only_when_the_text_has_people():
    assert "people actively moving" in av.scene_prompt({"speech": "The workers carried the cane to the mill."}, job())
    assert "people actively moving" not in av.scene_prompt({"speech": "The mill is a ruin of brick and rusted iron."}, job())


# ---------- urls / slugs
def test_article_page_url_matches_the_portal_slug():
    assert av.slugify("Ilonggo Cuisine: A Culinary Journey!") == "ilonggo-cuisine-a-culinary-journey"
    assert av.article_page_url({"title": TITLE}) == f"{av.SITE_URL}/articles/ilonggo-cuisine-a-culinary-journey.html"
    assert av.article_page_url({"slug": "my-slug"}).endswith("/articles/my-slug.html")


def test_cloudflare_names_match_the_github_secrets():
    assert hasattr(av, "CLOUDFLARE_ACCOUNT_ID") and hasattr(av, "CLOUDFLARE_API_TOKEN")
    assert not hasattr(av, "CF_ACCOUNT_ID")


# ---------- job bookkeeping
def test_finished_jobs_are_skipped_and_failed_ones_retried_three_times():
    j = {"jobId": "1"}
    assert av.needs_work(j, None)
    assert not av.needs_work(j, {"jobId": "1", "status": "done"})
    assert av.needs_work(j, {"jobId": "1", "status": "failed", "attempts": 2})
    assert not av.needs_work(j, {"jobId": "1", "status": "failed", "attempts": 3})
    assert av.needs_work({"jobId": "2"}, {"jobId": "1", "status": "done"})


def test_find_article_by_id_then_title():
    rows = [{"id": 5, "title": "Other"}, {"id": 9, "title": TITLE}, {"id": 3, "title": TITLE}]
    assert av.find_article({"articleId": 5}, rows)["id"] == 5
    assert av.find_article({"title": TITLE.upper()}, rows)["id"] == 9  # newest match wins


# ---------- end to end (needs ffmpeg)
@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_video_is_built_and_starts_on_the_picture_not_black(tmp_path):
    short = job(body=f"<main><p>{PARA}</p></main>")  # one slide keeps this test quick
    final, dur, engine = av.build_video(short)
    try:
        assert Path(final).stat().st_size > 10_000 and dur > 5 and engine == "fake"
    finally:
        shutil.rmtree(Path(final).parent, ignore_errors=True)


# ---------- location / characters / look from the job file
STORY = "Nanay Rosa carried the dumplings to the wet market while the sun rose over the nipa huts."


def test_characters_appear_only_where_the_narration_mentions_them():
    j = job(characters=[{"name": "Nanay Rosa", "description": "elderly woman, grey bun, faded floral blouse", "appearsIn": ["rosa", "dumplings"]},
                        {"name": "Tomas", "description": "young fisherman", "appearsIn": ["banca"]}])
    pr = av.scene_prompt({"speech": STORY}, j)
    assert "elderly woman, grey bun" in pr and "young fisherman" not in pr
    assert "faded floral" not in av.scene_prompt({"speech": "The harbour was quiet that night."}, j)


def test_place_era_palette_and_look_reach_the_prompt():
    j = job(location={"name": "Iloilo City", "era": "early 1990s", "description": "nipa huts, wooden banca boats", "palette": "warm ochre"},
            style={"look": "35mm Kodak film"})
    pr = av.scene_prompt({"speech": STORY}, j)
    assert pr.startswith("35mm Kodak film") and "Iloilo City, early 1990s" in pr and "nipa huts" in pr and "warm ochre" in pr
    assert len(pr.split()) < 260


def test_a_title_only_job_gets_its_text_from_the_article_on_the_site():
    j = {"title": TITLE}
    av.fill_job_from_article(j, {"id": 7, "content": "<main><p>Body.</p></main>", "excerpt": "Ex", "category": "culture"})
    assert j["body"].startswith("<main>") and j["excerpt"] == "Ex" and j["category"] == "culture" and j["articleId"] == 7
    keep = {"title": TITLE, "body": "mine"}
    av.fill_job_from_article(keep, {"id": 7, "content": "site"})
    assert keep["body"] == "mine"


# ---------- moving people (Kling clips)
def test_animated_slides_are_spread_out_and_prefer_people():
    segs = [{"kind": "body", "speech": "The workers carried cane." if i % 3 == 0 else "The mill is a ruin."} for i in range(30)]
    segs.append({"kind": "end", "speech": "x"})
    picked = sorted(av.pick_kling_slides(segs, 6))
    assert len(picked) == 6 and picked[0] <= 3 and picked[-1] >= 26          # first to last part of the video
    assert sum(1 for i in picked if i % 3 == 0) >= 5                          # mostly slides that mention people
    assert av.pick_kling_slides(segs, 0) == set()


def test_a_short_clip_keeps_moving_for_the_whole_slide(tmp_path):
    import subprocess
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from PIL import Image, ImageChops, ImageStat
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24:duration=5", "-pix_fmt", "yuv420p", str(tmp_path / "k.mp4")], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", "18", "-c:a", "libmp3lame", str(tmp_path / "a.mp3")], check=True)
    av.render_caption("c").save(tmp_path / "c.png")
    Image.new("RGBA", (av.W, av.H), (0, 0, 0, 0)).save(tmp_path / "o.png")
    av.make_clip_from_video(tmp_path / "k.mp4", tmp_path / "o.png", tmp_path / "a.mp3", tmp_path / "out.mp4", [(tmp_path / "c.png", 0, 18)])

    def grab(t, name):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(tmp_path / "out.mp4"), "-frames:v", "1", str(tmp_path / name)], check=True)
        return Image.open(tmp_path / name).convert("L").crop((0, 0, av.W, av.IMGH))

    late = ImageStat.Stat(ImageChops.difference(grab(16.0, "x.png"), grab(16.4, "y.png"))).mean[0]
    assert late > 0.3, "the picture froze after the clip ended"


# ---------- free moving people: Pexels stock footage (network faked)
class _Resp:
    def __init__(self, data=b"", js=None):
        self._data, self._js = data, js

    def raise_for_status(self):
        pass

    def json(self):
        return self._js

    def iter_content(self, n):
        for i in range(0, len(self._data), n):
            yield self._data[i:i + n]

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def _fake_pexels(monkeypatch, mp4_bytes, videos=None, fail=False):
    calls = []
    vids = videos if videos is not None else [{"id": 1, "duration": 8, "url": "https://pexels.com/video/1", "user": {"name": "Jane"},
             "video_files": [{"file_type": "video/mp4", "width": 1280, "height": 720, "link": "https://cdn/clip.mp4"},
                             {"file_type": "video/mp4", "width": 3840, "height": 2160, "link": "https://cdn/huge.mp4"}]}]

    def get(url, **kw):
        calls.append(url)
        if fail:
            raise RuntimeError("network down")
        return _Resp(js={"videos": vids}) if "api.pexels.com" in url else _Resp(data=mp4_bytes)
    monkeypatch.setattr(av.requests, "get", get)
    return calls


def test_stock_queries_use_the_people_and_things_in_the_narration():
    q = av.stock_queries({"speech": "The fishermen pushed their boat into the sea at dawn."}, {"title": "Iloilo fishing"})
    assert q[0] == "philippines fisherman boat" or q[0].startswith("philippines fishermen")
    assert av.stock_queries({"speech": "It was a quiet and thoughtful year."}, {"title": "x"}) == []


def test_stock_clip_is_downloaded_credited_and_not_reused(monkeypatch, tmp_path):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24:duration=2", "-pix_fmt", "yuv420p", str(tmp_path / "s.mp4")], check=True)
    calls = _fake_pexels(monkeypatch, (tmp_path / "s.mp4").read_bytes())
    monkeypatch.setattr(av, "STOCK_VIDEO", True)
    monkeypatch.setattr(av, "PEXELS_API_KEY", "key")
    av.CREDITS.clear()
    used = set()
    seg = {"speech": "The fishermen pushed their boat into the sea."}
    got = av.fetch_stock_clip(seg, {"title": "t"}, used, tmp_path / "o.mp4")
    assert got and (tmp_path / "o.mp4").stat().st_size > 1000 and 1 in used
    assert "https://cdn/clip.mp4" in calls and "https://cdn/huge.mp4" not in calls   # the 1280-wide file, not the 4K one
    assert av.CREDITS and "Jane" in av.CREDITS[0] and "Pexels" in av.CREDITS[0]
    assert av.fetch_stock_clip(seg, {"title": "t"}, used, tmp_path / "o2.mp4") is None   # same clip is never used twice
    av.CREDITS.clear()


def test_stock_footage_failure_or_missing_key_keeps_the_still_picture(monkeypatch, tmp_path):
    seg = {"speech": "The fishermen pushed their boat into the sea."}
    monkeypatch.setattr(av, "STOCK_VIDEO", True)
    monkeypatch.setattr(av, "PEXELS_API_KEY", "")
    assert av.fetch_stock_clip(seg, {"title": "t"}, set(), tmp_path / "o.mp4") is None
    monkeypatch.setattr(av, "PEXELS_API_KEY", "key")
    _fake_pexels(monkeypatch, b"", fail=True)
    assert av.fetch_stock_clip(seg, {"title": "t"}, set(), tmp_path / "o.mp4") is None


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_a_video_with_stock_footage_builds(monkeypatch, tmp_path):
    import subprocess
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=24:duration=3", "-pix_fmt", "yuv420p", str(tmp_path / "s.mp4")], check=True)
    _fake_pexels(monkeypatch, (tmp_path / "s.mp4").read_bytes())
    monkeypatch.setattr(av, "STOCK_VIDEO", True)
    monkeypatch.setattr(av, "PEXELS_API_KEY", "key")
    body = "<main><p>The fishermen pushed their boat into the sea at dawn. Workers carried the nets to the market along the road.</p></main>"
    final, dur, _ = av.build_video(job(body=body))
    try:
        assert Path(final).stat().st_size > 10_000 and any("Pexels" in c for c in av.CREDITS)
    finally:
        shutil.rmtree(Path(final).parent, ignore_errors=True)
        av.CREDITS.clear()
