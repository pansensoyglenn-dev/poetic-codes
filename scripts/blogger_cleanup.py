#!/usr/bin/env python3
"""
blogger_cleanup.py - finds and deletes duplicate posts on a Blogger blog (Blogger API v3).

  python blogger_cleanup.py                       preview: lists duplicate groups, deletes nothing
  python blogger_cleanup.py --apply               deletes the extra copies
  python blogger_cleanup.py --titles delete-titles.txt            also delete every post whose title is listed (one per line)
  python blogger_cleanup.py --keep newest|oldest  which copy of a duplicate to keep (default oldest = the original address)

Two posts are duplicates when their titles are the same after ignoring capitals, spaces and punctuation.

Needs three secrets (environment variables). Deleting through the API is PERMANENT (there is no Trash),
so always run the preview first.
  GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN   (OAuth, scope https://www.googleapis.com/auth/blogger)
  BLOG_URL   e.g. https://poetic-bytes.blogspot.com   (or BLOG_ID)
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


def http(method, url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode("utf-8", "ignore")
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", "ignore")[:300]}


def access_token():
    need = ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GOOGLE_REFRESH_TOKEN")
    missing = [k for k in need if not os.environ.get(k)]
    if missing:
        sys.exit("Missing secret(s): " + ", ".join(missing))
    body = urllib.parse.urlencode({
        "client_id": os.environ["GOOGLE_CLIENT_ID"], "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
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
        q = {"maxResults": "500", "fetchBodies": "false", "status": "live", "orderBy": "published"}
        if page:
            q["pageToken"] = page
        st, js = http("GET", f"{API}/blogs/{bid}/posts?{urllib.parse.urlencode(q)}", headers={"Authorization": "Bearer " + tok})
        if st != 200:
            sys.exit(f"Could not list posts (HTTP {st}): {js}")
        posts += js.get("items", [])
        page = js.get("nextPageToken")
        if not page:
            return posts


def norm(t):
    return re.sub(r"[^a-z0-9]+", "", (t or "").lower())


def pick_deletions(posts, keep="oldest", titles=()):
    """Return (list of (post, reason)) to delete."""
    out, seen = [], set()
    groups = {}
    for p in posts:
        groups.setdefault(norm(p.get("title")), []).append(p)
    for key, g in groups.items():
        if len(g) < 2:
            continue
        g = sorted(g, key=lambda p: p.get("published", ""))
        keeper = g[0] if keep == "oldest" else g[-1]
        for p in g:
            if p["id"] != keeper["id"]:
                out.append((p, f"duplicate of {keeper.get('url')}"))
                seen.add(p["id"])
    wanted = {norm(t) for t in titles if t.strip() and not t.strip().startswith("#")}
    for p in posts:
        if norm(p.get("title")) in wanted and p["id"] not in seen:
            out.append((p, "listed in titles file"))
            seen.add(p["id"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep", choices=["oldest", "newest"], default="oldest")
    ap.add_argument("--titles")
    a = ap.parse_args()
    titles = []
    if a.titles:
        titles = open(a.titles, encoding="utf-8").read().splitlines()
    tok = access_token()
    bid = blog_id(tok)
    posts = all_posts(tok, bid)
    print(f"{len(posts)} live post(s) on the blog.")
    dels = pick_deletions(posts, a.keep, titles)
    if not dels:
        print("No duplicates found.")
        return 0
    print(f"{'DELETING' if a.apply else 'Would delete'} {len(dels)} post(s):")
    for p, why in dels:
        print(f"  - {p.get('title')}  [{p.get('published','')[:10]}]  {p.get('url')}  ({why})")
    if not a.apply:
        print("\nPreview only. Nothing was deleted. Add --apply to delete (this is permanent).")
        return 0
    bad = 0
    for p, _ in dels:
        st, js = http("DELETE", f"{API}/blogs/{bid}/posts/{p['id']}", headers={"Authorization": "Bearer " + tok})
        if st in (200, 204):
            print(f"deleted {p.get('url')}")
        else:
            bad += 1
            print(f"FAILED ({st}) {p.get('url')}: {js}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
