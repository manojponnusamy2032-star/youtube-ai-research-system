"""Verify the YouTube API key works for real research."""
import sys
import os

# Ensure we can import from src
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.services.youtube_service import YouTubeService
from src.utils.config import get_config

def main():
    cfg = get_config()
    api_key = cfg.YOUTUBE_API_KEY
    print(f"API key present: {bool(api_key)}")
    if not api_key:
        print("FAIL: No API key found in .env")
        return 1
    
    print(f"API key (first 8 chars): {api_key[:8]}...")
    
    svc = YouTubeService(api_key)
    try:
        results = svc.search_videos("python programming", max_results=3)
        print(f"Search returned {len(results)} results")
        if results:
            video_id = results[0]["id"]["videoId"]
            print(f"First video ID: {video_id}")
            print(f"First video title: {results[0]['snippet']['title']}")
            
            # Get video details
            details = svc.get_video_details([video_id])
            print(f"Video details returned: {len(details)} items")
            if details:
                stats = details[0].get("statistics", {})
                print(f"View count: {stats.get('viewCount', 'N/A')}")
            
            print("SUCCESS: YouTube API key works for real research")
            return 0
        else:
            print("FAIL: No results returned from search")
            return 1
    except Exception as e:
        print(f"FAIL: YouTube API error: {e}")
        return 1
    finally:
        svc.close()

if __name__ == "__main__":
    sys.exit(main())