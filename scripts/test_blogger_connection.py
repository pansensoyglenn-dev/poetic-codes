#!/usr/bin/env python3
"""Checks that your Blogger credentials work. Reads BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET,
BLOGGER_REFRESH_TOKEN and BLOGGER_BLOG_ID from the environment (GitHub secrets). Changes nothing."""
import os
import sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def test_connection():
    names = ("BLOGGER_CLIENT_ID", "BLOGGER_CLIENT_SECRET", "BLOGGER_REFRESH_TOKEN", "BLOGGER_BLOG_ID")
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        print("Missing secret(s): " + ", ".join(missing), file=sys.stderr)
        sys.exit(1)
    try:
        creds = Credentials(None, refresh_token=os.environ["BLOGGER_REFRESH_TOKEN"].strip(),
                            client_id=os.environ["BLOGGER_CLIENT_ID"].strip(),
                            client_secret=os.environ["BLOGGER_CLIENT_SECRET"].strip(),
                            token_uri="https://oauth2.googleapis.com/token")
        service = build("blogger", "v3", credentials=creds)
        blog_id = os.environ["BLOGGER_BLOG_ID"].strip()
        blog = service.blogs().get(blogId=blog_id).execute()
        print(f"Connected to blog: {blog.get('name')} ({blog.get('url')})")
        items = service.posts().list(blogId=blog_id, maxResults=5).execute().get("items", [])
        print(f"Found {len(items)} recent live post(s):")
        for p in items:
            print(" -", p.get("title"))
        print("Credential test passed.")
    except Exception as e:
        print(f"Connection failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    test_connection()
