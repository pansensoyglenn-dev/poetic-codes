#!/usr/bin/env python3
"""
cleanup_supabase.py - delete old files from a Supabase Storage bucket.

Settings come from environment variables (set them as GitHub Secrets / inputs):
  SUPABASE_URL                e.g. https://abcdxyz.supabase.co
  SUPABASE_SERVICE_ROLE_KEY   service_role key (keep it secret, never put it in code)
  SUPABASE_BUCKET             bucket name, e.g. "videos"
  MAX_AGE_DAYS                delete files older than this many days (default 30)
  PREFIX                      only look inside this folder (default: whole bucket)
  DRY_RUN                     "true" (default) only lists; "false" really deletes
  KEEP_NEWEST                 always keep this many newest files (default 0)

Uses only the Python standard library, so nothing needs installing.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = os.environ.get("SUPABASE_BUCKET", "")
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS") or 30)
PREFIX = (os.environ.get("PREFIX") or "").strip("/")
DRY_RUN = (os.environ.get("DRY_RUN") or "true").strip().lower() != "false"
KEEP_NEWEST = int(os.environ.get("KEEP_NEWEST") or 0)
PAGE = 100
BATCH = 100


def call(method, path, body=None):
    req = urllib.request.Request(
        f"{URL}/storage/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Authorization": f"Bearer {KEY}", "apikey": KEY,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"Supabase error {e.code} on {method} {path}: {e.read().decode()[:300]}")


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def walk(prefix):
    """Yield (path, created_at, size) for every file under prefix."""
    offset = 0
    while True:
        items = call("POST", f"object/list/{BUCKET}", {
            "prefix": prefix, "limit": PAGE, "offset": offset,
            "sortBy": {"column": "name", "order": "asc"}}) or []
        for it in items:
            path = f"{prefix}/{it['name']}" if prefix else it["name"]
            if it.get("id") is None:          # a folder
                yield from walk(path)
            else:
                size = (it.get("metadata") or {}).get("size", 0)
                yield path, parse(it.get("created_at") or it["updated_at"]), size
        if len(items) < PAGE:
            break
        offset += PAGE


def main():
    if not (URL and KEY and BUCKET):
        sys.exit("Set SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY and SUPABASE_BUCKET.")
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    files = sorted(walk(PREFIX), key=lambda f: f[1], reverse=True)   # newest first
    print(f"Bucket '{BUCKET}': {len(files)} files found. Cutoff: older than {MAX_AGE_DAYS} days ({cutoff:%Y-%m-%d}).")
    candidates = [f for f in files[KEEP_NEWEST:] if f[1] < cutoff]
    total = sum(f[2] for f in candidates)
    for path, created, size in candidates:
        print(f"  {'WOULD DELETE' if DRY_RUN else 'DELETE'}  {path}  ({created:%Y-%m-%d}, {size/1e6:.1f} MB)")
    print(f"{len(candidates)} files, {total/1e6:.1f} MB to free.")
    if DRY_RUN:
        print("DRY RUN: nothing deleted. Set DRY_RUN=false to delete for real.")
        return
    paths = [f[0] for f in candidates]
    for i in range(0, len(paths), BATCH):
        call("DELETE", f"object/{BUCKET}", {"prefixes": paths[i:i + BATCH]})
    print("Done.")


if __name__ == "__main__":
    main()
