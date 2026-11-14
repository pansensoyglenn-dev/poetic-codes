import os
import html
import xml.etree.ElementTree as ET
import urllib.request
import google.auth.transport.requests
import google.oauth2.credentials
from googleapiclient.discovery import build

# Environment variables from GitHub Secrets
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN")
BLOG_ID = os.environ.get("BLOG_ID")
YOUTUBE_CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID")  # must start with "UC", not the @handle

# AdSense Configuration
ADSENSE_PUBLISHER = 'ca-pub-6428799122405621'
ADSENSE_SLOT_MIDDLE = '9585168014'
ADSENSE_SLOT_BOTTOM = '1982565389'

# Safety cap so a first run cannot publish the whole feed at once
MAX_NEW_POSTS = 5

POST_LABELS = ['Music Video', 'YouTube', 'Poetic Bytes']


def ad_block(slot):
    # Only the <ins> unit and its push call. The adsbygoogle.js loader belongs once in the
    # Blogger theme <head>, not in every post. {{}} is how an f-string writes a literal {}.
    return (
        f'<div class="ad-slot" style="margin:1.6rem 0;text-align:center;">'
        f'<ins class="adsbygoogle" style="display:block" data-ad-client="{ADSENSE_PUBLISHER}" '
        f'data-ad-slot="{slot}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
        f'<script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script>'
        f'</div>'
    )


def get_youtube_videos():
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={YOUTUBE_CHANNEL_ID}"
    with urllib.request.urlopen(rss_url, timeout=30) as req:
        xml_data = req.read()

    root = ET.fromstring(xml_data)
    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'yt': 'http://www.youtube.com/xml/schemas/2015',
        'media': 'http://search.yahoo.com/mrss/',
    }

    videos = []
    for entry in root.findall('atom:entry', ns):
        desc_el = entry.find('media:group/media:description', ns)
        videos.append({
            'video_id': entry.find('yt:videoId', ns).text,
            'title': entry.find('atom:title', ns).text,
            'link': entry.find('atom:link', ns).attrib['href'],
            'published': entry.find('atom:published', ns).text,
            'description': (desc_el.text or '').strip() if desc_el is not None else '',
        })
    return videos


def get_existing_titles(service):
    """Titles of every video post already on the blog (all pages, not just the first 10)."""
    titles = set()
    page_token = None
    while True:
        resp = service.posts().list(
            blogId=BLOG_ID,
            labels='YouTube',
            maxResults=100,
            fetchBodies=False,
            status=['live', 'draft'],
            pageToken=page_token,
        ).execute()
        for item in resp.get('items', []):
            titles.add(item['title'])
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return titles


def build_post_content(vid):
    embed_html = (
        f'<div style="position:relative;padding-bottom:56.25%;height:0;overflow:hidden;border-radius:12px;margin:1.5rem 0;">'
        f'<iframe src="https://www.youtube.com/embed/{vid["video_id"]}" '
        f'style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;" allowfullscreen></iframe>'
        f'</div>'
    )
    intro = (
        f'<p>Watch the latest episode from Poetic Bytes: '
        f'<a href="{html.escape(vid["link"])}" target="_blank" rel="noopener">Watch on YouTube</a></p>'
    )
    # Real text between the ad units, so the page is not just a video and ads
    description = ''
    if vid['description']:
        description = '<p>' + html.escape(vid['description']).replace('\n', '<br>') + '</p>'

    return intro + embed_html + ad_block(ADSENSE_SLOT_MIDDLE) + description + ad_block(ADSENSE_SLOT_BOTTOM)


def main():
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, BLOG_ID, YOUTUBE_CHANNEL_ID]):
        print("Missing required environment variables.")
        return

    # Authenticate with Blogger API
    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )
    creds.refresh(google.auth.transport.requests.Request())
    service = build('blogger', 'v3', credentials=creds)

    existing_titles = get_existing_titles(service)
    videos = get_youtube_videos()

    posted = 0
    for vid in reversed(videos):  # oldest first, so the newest ends up on top
        if vid['title'] in existing_titles:
            print(f"Skipping already posted: {vid['title']}")
            continue
        if posted >= MAX_NEW_POSTS:
            print(f"Reached the cap of {MAX_NEW_POSTS} new posts; the rest will go out next run.")
            break

        print(f"Publishing new video to Blogger: {vid['title']}")
        post_body = {
            'title': vid['title'],
            'content': build_post_content(vid),
            'labels': POST_LABELS,
        }
        service.posts().insert(blogId=BLOG_ID, body=post_body).execute()
        posted += 1
        print(f"Successfully posted: {vid['title']}")


if __name__ == '__main__':
    main()
