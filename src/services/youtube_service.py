"""
YouTube service for YouTube AI Research System.

This module handles all interactions with the YouTube Data API v3,
including video search and metadata retrieval.
"""

import logging
import time
from typing import List, Optional, Dict, Any

import requests

from src.models.video import Video

logger = logging.getLogger(__name__)


class YouTubeAPIError(Exception):
    """Custom exception for YouTube API errors."""
    pass


class YouTubeService:
    """
    Service for interacting with YouTube Data API v3.
    
    Handles video search and metadata retrieval with proper error handling,
    rate limiting, and retry logic.
    
    Attributes:
        api_key: YouTube Data API v3 key
        base_url: YouTube API base URL
        session: Requests session for connection pooling
    """
    
    BASE_URL = "https://www.googleapis.com/youtube/v3"
    
    def __init__(self, api_key: str) -> None:
        """
        Initialize the YouTube service.
        
        Args:
            api_key: YouTube Data API v3 key
            
        Raises:
            ValueError: If API key is empty or invalid
        """
        if not api_key or not api_key.strip():
            raise ValueError("API key cannot be empty")
        
        self.api_key = api_key.strip()
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
        logger.info("YouTube service initialized")
    
    def _make_request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make a request to YouTube API with retry logic.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            JSON response as dictionary
            
        Raises:
            YouTubeAPIError: If API request fails after all retries
        """
        url = f"{self.BASE_URL}/{endpoint}"
        params["key"] = self.api_key
        
        max_retries = 3
        retry_delay = 2
        
        for attempt in range(1, max_retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()
                
                data = response.json()
                
                # Check for API errors in response
                if "error" in data:
                    error_info = data["error"]
                    error_msg = error_info.get("message", "Unknown API error")
                    logger.error(f"YouTube API error: {error_msg}")
                    raise YouTubeAPIError(error_msg)
                
                return data
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.error(f"Request failed after {max_retries} attempts")
                    raise YouTubeAPIError(f"Request failed: {e}") from e
            except ValueError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                raise YouTubeAPIError(f"Invalid JSON response: {e}") from e
    
    def search_videos(
        self,
        keyword: str,
        max_results: int = 50,
        language: str = "en",
        region_code: str = "US"
    ) -> List[Dict[str, Any]]:
        """
        Search for videos on YouTube.
        
        Args:
            keyword: Search keyword
            max_results: Maximum number of results (1-50, default: 50)
            language: Language code (default: en)
            region_code: Region code (default: US)
            
        Returns:
            List of video search result items
            
        Raises:
            ValueError: If parameters are invalid
            YouTubeAPIError: If API request fails
        """
        if not keyword or not keyword.strip():
            raise ValueError("Search keyword cannot be empty")
        
        if not 1 <= max_results <= 50:
            raise ValueError("max_results must be between 1 and 50")
        
        logger.info(f"Searching YouTube for keyword: '{keyword}' (max_results={max_results})")
        
        params = {
            "part": "snippet",
            "q": keyword.strip(),
            "type": "video",
            "maxResults": min(max_results, 50),
            "order": "relevance",
            "relevanceLanguage": language,
            "regionCode": region_code,
            "safeSearch": "moderate"
        }
        
        data = self._make_request("search", params)
        items = data.get("items", [])
        
        logger.info(f"Found {len(items)} videos for keyword '{keyword}'")
        return items
    
    def get_video_details(self, video_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Get detailed metadata for videos.
        
        Args:
            video_ids: List of YouTube video IDs (max 50 per request)
            
        Returns:
            List of video detail items
            
        Raises:
            ValueError: If video_ids is empty or too large
            YouTubeAPIError: If API request fails
        """
        if not video_ids:
            raise ValueError("video_ids cannot be empty")
        
        if len(video_ids) > 50:
            raise ValueError("Cannot fetch more than 50 videos at once")
        
        logger.info(f"Fetching details for {len(video_ids)} videos")
        
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids)
        }
        
        data = self._make_request("videos", params)
        items = data.get("items", [])
        
        logger.info(f"Retrieved details for {len(items)} videos")
        return items
    
    def search_and_get_details(
        self,
        keyword: str,
        max_results: int = 50,
        min_views: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search for videos and retrieve their full metadata.
        
        This is a convenience method that combines search and detail retrieval.
        
        Args:
            keyword: Search keyword
            max_results: Maximum number of results
            min_views: Minimum view count filter (default: 0)
            
        Returns:
            List of video items with full metadata
        """
        search_results = self.search_videos(keyword, max_results)
        
        if not search_results:
            return []
        
        # Extract video IDs
        video_ids = [item["id"]["videoId"] for item in search_results]
        
        # Get detailed metadata
        detailed_videos = self.get_video_details(video_ids)
        
        # Filter by minimum views if specified
        if min_views > 0:
            filtered_videos = []
            for video in detailed_videos:
                statistics = video.get("statistics", {})
                view_count = int(statistics.get("viewCount", 0))
                if view_count >= min_views:
                    filtered_videos.append(video)
            
            logger.info(f"Filtered to {len(filtered_videos)} videos with >= {min_views:,} views")
            return filtered_videos
        
        return detailed_videos
    
    def parse_video_item(self, item: Dict[str, Any], search_keyword: str) -> Video:
        """
        Parse a YouTube API video item into a Video model.
        
        Args:
            item: YouTube API video item
            search_keyword: Keyword used to find this video
            
        Returns:
            Video model instance
            
        Raises:
            ValueError: If required fields are missing
        """
        try:
            video_id = item["id"]
            snippet = item["snippet"]
            statistics = item.get("statistics", {})
            content_details = item.get("contentDetails", {})
            
            # Parse published_at timestamp
            published_at_str = snippet["publishedAt"]
            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
            
            # Build video URL
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            # Build thumbnail URL (use medium quality as default)
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = thumbnails.get("medium", {}).get("url", "")
            if not thumbnail_url and "default" in thumbnails:
                thumbnail_url = thumbnails["default"]["url"]
            
            # Extract view count for logging
            view_count = int(statistics.get("viewCount", 0))
            
            video = Video(
                video_id=video_id,
                title=snippet["title"],
                description=snippet.get("description", ""),
                channel=snippet["channelTitle"],
                channel_id=snippet["channelId"],
                published_at=published_at,
                duration=content_details.get("duration", ""),
                view_count=view_count,
                like_count=int(statistics.get("likeCount", 0)),
                comment_count=int(statistics.get("commentCount", 0)),
                thumbnail_url=thumbnail_url,
                video_url=video_url,
                search_keyword=search_keyword
            )
            
            logger.debug(f"Parsed video: {video_id} - {view_count:,} views")
            return video
            
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse video item: {e}")
            raise YouTubeAPIError(f"Invalid video data: {e}")
    
    def close(self) -> None:
        """Close the requests session."""
        if self.session:
            self.session.close()
            logger.info("YouTube service session closed")
    
    def __enter__(self) -> "YouTubeService":
        """Context manager entry point."""
        return self
    
    def __exit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> None:
        """Context manager exit point."""
        self.close()


# Import datetime here to avoid circular imports
from datetime import datetime