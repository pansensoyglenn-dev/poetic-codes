"""Share each newly finished article on a Facebook Page and/or a Telegram channel (official APIs only).
Reads video-jobs/done/*.json (written by the video script), skips anything already in video-jobs/social-posted.txt.
First run only records what already exists, so your old articles are not posted all at once."""
import json, os, sys, time
from pathlib import Path
import requests

DONE = Path(os.environ.get("JOBS_DIR", "video-jobs")) / "done"
STATE = Path(os.environ.get("JOBS_DIR", "video-jobs")) / "social-posted.txt"
FB_PAGE_ID = os.environ.get("FB_PAGE_ID", "").strip()
FB_PAGE_TOKEN = os.environ.get("FB_PAGE_TOKEN", "").strip()
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()      # e.g. @yourchannel
MAX_POSTS = int(os.environ.get("SOCIAL_MAX_POSTS", "3"))
DRY = os.environ.get("DRY_RUN") == "1"


def hashtags(title):
    return "#PoeticCodes #Essay"


def post_facebook(title, url):
    r = requests.post(f"https://graph.facebook.com/v21.0/{FB_PAGE_ID}/feed",
                      data={"message": f"{title}\n\nRead the full essay and watch the video: {url}\n\n{hashtags(title)}",
                            "link": url, "access_token": FB_PAGE_TOKEN}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Facebook {r.status_code}: {r.text[:250]}")


def post_telegram(title, url):
    r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT_ID, "text": f"{title}\n\n{url}", "disable_web_page_preview": False}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Telegram {r.status_code}: {r.text[:250]}")


def main():
    if not ((FB_PAGE_ID and FB_PAGE_TOKEN) or (TG_BOT_TOKEN and TG_CHAT_ID)):
        print("No Facebook or Telegram secrets set; nothing to do.")
        return 0
    items = []
    for f in sorted(DONE.glob("*.json")) if DONE.exists() else []:
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("status") == "done" and m.get("articleUrl"):
            items.append((f.name, m.get("title") or f.stem, m["articleUrl"]))
    first_run = not STATE.exists()
    posted = set(STATE.read_text(encoding="utf-8").split()) if not first_run else set()
    if first_run:
        STATE.write_text("\n".join(n for n, _, _ in items) + ("\n" if items else ""), encoding="utf-8")
        print(f"First run: recorded {len(items)} existing article(s) without posting them.")
        return 0
    sent = 0
    for name, title, url in items:
        if name in posted:
            continue
        if sent >= MAX_POSTS:
            print("Post limit reached; the rest go out next run.")
            break
        ok = True
        for label, enabled, fn in (("Facebook", FB_PAGE_ID and FB_PAGE_TOKEN, post_facebook),
                                   ("Telegram", TG_BOT_TOKEN and TG_CHAT_ID, post_telegram)):
            if not enabled:
                continue
            try:
                if DRY:
                    print(f"DRY {label}: {title} {url}")
                else:
                    fn(title, url)
                    print(f"{label}: posted {title}")
                time.sleep(2)
            except Exception as e:
                print(f"{label} failed for {title}: {str(e)[:250]}")
                ok = False
        if ok and not DRY:
            with open(STATE, "a", encoding="utf-8") as fh:
                fh.write(name + "\n")
            sent += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
