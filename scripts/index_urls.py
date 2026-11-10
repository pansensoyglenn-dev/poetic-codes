import os
import json
import requests
import xml.etree.ElementTree as ET
from google.oauth2 import service_account
import google.auth.transport.requests

ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SCOPES = ["https://www.googleapis.com/auth/indexing"]
MAX_DAILY_QUOTA = 200  # Safeguard for Google Indexing API daily limit

def get_authenticated_session():
    """Authenticates using the Service Account JSON stored in a GitHub secret."""
    service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    credentials = service_account.Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    request = google.auth.transport.requests.Request()
    credentials.refresh(request)
    return credentials

def fetch_urls_from_sitemap(sitemap_url):
    """Downloads and parses the XML sitemap to extract all URL locations."""
    print(f"Fetching sitemap from: {sitemap_url}")
    try:
        response = requests.get(sitemap_url, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching sitemap: {e}")
        return []

    urls = []
    try:
        root = ET.fromstring(response.content)
        
        # Handle standard sitemap XML namespaces (e.g., xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
        namespace = ""
        if root.tag.startswith("{"):
            namespace = root.tag.split("}")[0] + "}"

        url_tag = f"{namespace}url"
        loc_tag = f"{namespace}loc"

        for url_elem in root.findall(url_tag):
            loc_elem = url_elem.find(loc_tag)
            if loc_elem is not None and loc_elem.text:
                urls.append(loc_elem.text.strip())
                
    except Exception as e:
        print(f"Error parsing XML sitemap: {e}")

    return urls

def submit_url(credentials, url, action="URL_UPDATED"):
    """Submits a single URL to the Google Indexing API."""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {credentials.token}"
    }
    payload = {
        "url": url,
        "type": action  # Options: URL_UPDATED or URL_DELETED
    }
    
    response = requests.post(ENDPOINT, headers=headers, json=payload)
    if response.status_code == 200:
        print(f"Successfully indexed: {url}")
        return True
    else:
        print(f"Failed to index {url}: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    # Pull base domain from environment variables
    base_url = os.environ.get("SITE_BASE_URL", "https://poetic-codes.pages.dev")
    sitemap_url = f"{base_url.rstrip('/')}/sitemap.xml"

    print("Authenticating with Google Indexing API...")
    creds = get_authenticated_session()

    # Automatically fetch and parse URLs from sitemap
    urls = fetch_urls_from_sitemap(sitemap_url)
    print(f"Discovered {len(urls)} URLs in sitemap.")

    submitted_count = 0
    for url in urls:
        if submitted_count >= MAX_DAILY_QUOTA:
            print(f"Reached maximum daily quota safeguard ({MAX_DAILY_QUOTA} URLs). Stopping submission.")
            break
        
        print(f"[{submitted_count + 1}/{len(urls)}] Submitting: {url}")
        success = submit_url(creds, url)
        if success:
            submitted_count += 1
