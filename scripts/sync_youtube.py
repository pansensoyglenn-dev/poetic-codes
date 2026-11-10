import os
import googleapiclient.discovery

# Setup YouTube API client (requires a user OAuth token or API key for public data)
API_KEY = os.environ.get("YOUTUBE_API_KEY")
CHANNEL_ID = os.environ.get("YOUTUBE_CHANNEL_ID")

def get_latest_videos(channel_id, api_key, max_results=5):
    """Fetches the latest videos from a specific YouTube channel ID."""
    youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=api_key)
    
    # 1. Get the uploads playlist ID for the channel
    channel_response = youtube.channels().list(
        id=channel_id,
        part="contentDetails"
    ).execute()
    
    uploads_list_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    
    # 2. Fetch items from the uploads playlist
    playlist_response = youtube.playlistItems().list(
        playlistId=uploads_list_id,
        part="snippet",
        maxResults=max_results
    ).execute()
    
    videos = []
    for item in playlist_response.get("items", []):
        snippet = item["snippet"]
        videos.append({
            "title": snippet["title"],
            "description": snippet["description"],
            "published_at": snippet["publishedAt"],
            "video_id": snippet["resourceId"]["videoId"],
            "url": f"https://www.youtube.com/watch?v={snippet['resourceId']['videoId']}"
        })
        
    return videos

if __name__ == "__main__":
    if not API_KEY or not CHANNEL_ID:
        print("Please set YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID environment variables.")
    else:
        latest_videos = get_latest_videos(CHANNEL_ID, API_KEY)
        for v in latest_videos:
            print(f"- {v['title']} ({v['url']})")
