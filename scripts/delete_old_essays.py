#!/usr/bin/env python3
"""
delete_old_essays.py - removes old essay pages from the repo, safely.

Two ways to choose what to delete:
  --list delete-list.txt     one slug (or full address) per line; '#' starts a comment
  --older-than 365           pages in articles/ whose published date is older than N days

It always shows what it would do first. Nothing is deleted unless you add --apply.
For every deleted page it also:
  * removes the page's entry from sitemap.xml and from RSS/feed files
  * removes video-jobs/done/<slug>.json (so the video job can be redone later)
  * keeps a copy in deleted-essays/ (unless --no-backup), so you can bring a page back

  python delete_old_essays.py --root . --list delete-list.txt            (preview)
  python delete_old_essays.py --root . --list delete-list.txt --apply    (delete)
  python delete_old_essays.py --root . --older-than 730 --keep 20 --apply

--keep N  never deletes the N newest essays, even if they match.
Note: this only touches the website files. Copies in The Commonplace, Firebase and Blogger are separate.
"""
import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path


def slug_of(s: str) -> str:
    s = s.strip().split("#")[0].strip()
    s = s.rstrip("/").split("/")[-1]
    return re.sub(r"\.html$", "", s)


def published(p: Path):
    t = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'article:published_time"\s+content="(\d{4}-\d{2}-\d{2})', t) or re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', t)
    if m:
        return dt.date.fromisoformat(m.group(1))
    return dt.date.fromtimestamp(p.stat().st_mtime)


def drop_from_sitemap(path: Path, slug: str) -> bool:
    if not path.exists():
        return False
    t = path.read_text(encoding="utf-8")
    new = re.sub(r"\s*<url>\s*<loc>[^<]*/articles/" + re.escape(slug) + r"\.html</loc>[\s\S]*?</url>", "", t)
    if new != t:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def drop_from_feed(path: Path, slug: str) -> bool:
    t = path.read_text(encoding="utf-8", errors="ignore")
    new = re.sub(r"\s*<item>(?:(?!</item>)[\s\S])*?/articles/" + re.escape(slug) + r"\.html[\s\S]*?</item>", "", t)
    new = re.sub(r"\s*<entry>(?:(?!</entry>)[\s\S])*?/articles/" + re.escape(slug) + r"\.html[\s\S]*?</entry>", "", new)
    if new != t:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--list")
    ap.add_argument("--older-than", type=int)
    ap.add_argument("--keep", type=int, default=10)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    a = ap.parse_args()
    if not a.list and not a.older_than:
        print("Give --list FILE or --older-than DAYS.")
        return 2
    root = Path(a.root).resolve()
    art = root / "articles"
    pages = {p.stem: p for p in art.glob("*.html")} if art.is_dir() else {}
    if not pages:
        print("No pages found in articles/.")
        return 1

    chosen = {}
    if a.list:
        lf = Path(a.list) if Path(a.list).is_absolute() else root / a.list
        if not lf.exists():
            print(f"List file not found: {lf}")
            return 1
        for line in lf.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            sl = slug_of(line)
            if sl in pages:
                chosen[sl] = "listed"
            else:
                print(f"not found (skipped): {sl}")
    if a.older_than:
        cutoff = dt.date.today() - dt.timedelta(days=a.older_than)
        dated = sorted(((published(p), s) for s, p in pages.items()), reverse=True)
        protected = {s for _, s in dated[: max(a.keep, 0)]}
        for d, s in dated:
            if d < cutoff and s not in protected:
                chosen.setdefault(s, f"published {d}")

    if not chosen:
        print("Nothing to delete.")
        return 0
    newest = sorted(((published(p), s) for s, p in pages.items()), reverse=True)[: max(a.keep, 0)]
    keep_set = {s for _, s in newest}
    for s in list(chosen):
        if s in keep_set and a.list:
            print(f"warning: {s} is one of your {a.keep} newest essays")

    print(f"{'DELETING' if a.apply else 'Would delete'} {len(chosen)} page(s):")
    backup = root / "deleted-essays"
    feeds = [p for n in ("rss.xml", "feed.xml", "atom.xml", "feed.rss") for p in [root / n] if p.exists()]
    for s, why in sorted(chosen.items()):
        print(f"  - articles/{s}.html ({why})")
        if not a.apply:
            continue
        src = pages[s]
        if not a.no_backup:
            backup.mkdir(exist_ok=True)
            shutil.copy2(src, backup / src.name)
        src.unlink()
        drop_from_sitemap(root / "sitemap.xml", s)
        for f in feeds:
            drop_from_feed(f, s)
        marker = root / "video-jobs" / "done" / f"{s}.json"
        if marker.exists():
            marker.unlink()
    if not a.apply:
        print("\nPreview only. Add --apply (or choose 'apply' in the workflow) to delete.")
    else:
        print(f"\nDone. Backups are in deleted-essays/ ({'skipped' if a.no_backup else 'kept'}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
