#!/usr/bin/env python3
"""
blogger_inject_ads.py - puts your AdSense units into EXISTING Blogger posts: one in the middle and one at
the bottom of the essay text (none at the top). Safe to run again: old units are removed first, so a post
never ends up with two.

  python blogger_inject_ads.py                      preview only: shows which posts would change
  python blogger_inject_ads.py --apply              rewrites the posts (a copy of each old body is saved first)
  python blogger_inject_ads.py --only "kansi"       only posts whose title contains this text
  python blogger_inject_ads.py --limit 5            at most 5 posts

New posts made with portal.html already get the units. This script is for the posts you published before.
The AdSense loader script does NOT go in posts: put it once in your Blogger theme <head>.

Secrets (environment variables): GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN, and
BLOG_URL (e.g. https://poetic-bytes.blogspot.com) or BLOG_ID. Same ones blogger_cleanup.py uses.
Only the standard library is used.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://www.googleapis.com/blogger/v3"
PUB = "ca-pub-6428799122405621"
SLOT_MIDDLE = "9585168014"
SLOT_BOTTOM = "1982565389"

OPEN = re.compile(r'<div class="pc-article"[^>]*>', re.I)
CLOSE = re.compile(r'</div>\s*<hr style="border:none;border-top:1px solid rgba\(139,94,52,0\.25\);margin:2\.5rem 0;">', re.I)


def ad(slot):
    return ('<div class="ad-slot" style="margin:1.6rem 0;text-align:center;">'
            f'<ins class="adsbygoogle" style="display:block" data-ad-client="{PUB}" data-ad-slot="{slot}" '
            'data-ad-format="auto" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')


def strip_ads(h):
    h = re.sub(r"<script[^>]*adsbygoogle\.js[^>]*>\s*</script>", "", h, flags=re.I)
    h = re.sub(r'<div class="ad-slot"[^>]*>\s*<ins class="adsbygoogle"[\s\S]*?</ins>\s*(?:<script>[\s\S]*?</script>\s*)?</div>', "", h, flags=re.I)
    h = re.sub(r'<ins class="adsbygoogle"[\s\S]*?</ins>\s*(?:<script>\s*\(adsbygoogle[\s\S]*?</script>)?', "", h, flags=re.I)
    return h


def inject(body):
    """Return the body with one middle and one bottom unit inside the essay text, or None if the post has no
    recognisable essay area (older posts made another way are left alone)."""
    o = OPEN.search(body)
    if not o:
        return None
    c = CLOSE.search(body, o.end())
    if not c:
        return None
    inner = strip_ads(body[o.end():c.start()])
    parts = re.split(r"(?<=</p>)\s*(?=<p)", inner)
    if len(parts) >= 2:
        mid = max(0, len(parts) // 2 - 1)
        parts[mid] += ad(SLOT_MIDDLE)
        inner = "\n".join(parts)
    else:
        inner += ad(SLOT_MIDDLE)
    inner += ad(SLOT_BOTTOM)
    head = strip_ads(body[:o.start()])
    return head + body[o.start():o.end()] + inner + strip_ads(body[c.start():])


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "ignore")
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")[:300]}


def access_token():
    miss = [k for k in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN") if not os.environ.get(k)]
    if miss:
        sys.exit("Missing secret(s): " + ", ".join(miss))
    body = urllib.parse.urlencode({"client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
                                   "refresh_token": os.environ["GOOGLE_REFRESH_TOKEN"], "grant_type": "refresh_token"}).encode()
    st, js = http("POST", "https://oauth2.googleapis.com/token", body, {"Content-Type": "application/x-www-form-urlencoded"})
    if st != 200 or "access_token" not in js:
        sys.exit(f"Could not sign in (HTTP {st}): {js}. Check the three secrets.")
    return js["access_token"]


def blog_id(tok):
    if os.environ.get("BLOG_ID"):
        return os.environ["BLOG_ID"]
    url = os.environ.get("BLOG_URL", "").strip()
    if not url:
        sys.exit("Set BLOG_URL (for example https://poetic-bytes.blogspot.com) or BLOG_ID.")
    st, js = http("GET", f"{API}/blogs/byurl?url={urllib.parse.quote(url, safe='')}", headers={"Authorization": "Bearer " + tok})
    if st != 200 or "id" not in js:
        sys.exit(f"Blog not found (HTTP {st}): {js}")
    return js["id"]


def all_posts(tok, bid):
    posts, page = [], None
    while True:
        q = {"maxResults": "50", "fetchBodies": "true", "status": "live"}
        if page:
            q["pageToken"] = page
        st, js = http("GET", f"{API}/blogs/{bid}/posts?{urllib.parse.urlencode(q)}", headers={"Authorization": "Bearer " + tok})
        if st != 200:
            sys.exit(f"Could not list posts (HTTP {st}): {js}")
        posts += js.get("items", [])
        page = js.get("nextPageToken")
        if not page:
            return posts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--backup-dir", default="blogger-backups")
    a = ap.parse_args()
    tok = access_token()
    bid = blog_id(tok)
    posts = all_posts(tok, bid)
    if a.only:
        posts = [p for p in posts if a.only.lower() in (p.get("title") or "").lower()]
    print(f"{len(posts)} post(s) to look at.")
    changed = skipped = nochange = failed = 0
    for p in posts:
        if a.limit and changed >= a.limit:
            break
        old = p.get("content", "")
        new = inject(old)
        if new is None:
            skipped += 1
            print(f"skip (no essay area found): {p.get('title')}")
            continue
        if new == old:
            nochange += 1
            continue
        had = len(re.findall(r'<ins class="adsbygoogle"', old))
        print(f"{'UPDATE' if a.apply else 'would update'}: {p.get('title')}  (units before: {had}, after: 2)")
        changed += 1
        if not a.apply:
            continue
        os.makedirs(a.backup_dir, exist_ok=True)
        with open(os.path.join(a.backup_dir, f"{p['id']}.html"), "w", encoding="utf-8") as f:
            f.write(old)
        st, js = http("PATCH", f"{API}/blogs/{bid}/posts/{p['id']}", json.dumps({"content": new}).encode(),
                      {"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        if st != 200:
            failed += 1
            print(f"  FAILED ({st}): {js}")
    print(f"\n{changed} {'updated' if a.apply else 'to update'}, {nochange} already correct, {skipped} skipped, {failed} failed.")
    if not a.apply and changed:
        print("Preview only. Add --apply to write the changes.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
