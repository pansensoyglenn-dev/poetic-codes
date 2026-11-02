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
