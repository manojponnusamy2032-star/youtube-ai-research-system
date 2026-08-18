"""YouTube upload service.

Publishes rendered videos with the YouTube Data API v3 using an OAuth
refresh token, so unattended runs never need an interactive browser sign-in.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

UPLOAD_SCOPES = ("https://www.googleapis.com/auth/youtube.upload",)
TOKEN_URI = "https://oauth2.googleapis.com/token"
VALID_PRIVACY_STATUSES = ("public", "unlisted", "private")


class YouTubeUploadError(Exception):
    """Raised when a video upload cannot be completed."""


@dataclass
class UploadRequest:
    """Metadata for a single video upload."""

    video_path: str
    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    category_id: str = "22"
    privacy_status: str = "public"
    made_for_kids: bool = False
    thumbnail_path: str | None = None

    def __post_init__(self) -> None:
        """Validate upload metadata against YouTube's limits."""
        if not self.video_path or not os.path.exists(self.video_path):
            raise ValueError(f"video_path does not exist: {self.video_path}")
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if len(self.title) > 100:
            raise ValueError("title cannot exceed 100 characters")
        if len(self.description) > 5000:
            raise ValueError("description cannot exceed 5000 characters")
        if self.privacy_status not in VALID_PRIVACY_STATUSES:
            raise ValueError(f"privacy_status must be one of {VALID_PRIVACY_STATUSES}")


@dataclass
class OAuthCredentials:
    """Installed-app OAuth credentials for the uploading channel."""

    client_id: str
    client_secret: str
    refresh_token: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "OAuthCredentials":
        """Build credentials from environment variables.

        Reads ``YOUTUBE_CLIENT_ID``, ``YOUTUBE_CLIENT_SECRET`` and
        ``YOUTUBE_REFRESH_TOKEN``.

        Raises:
            YouTubeUploadError: If any variable is missing.
        """
        source = env if env is not None else dict(os.environ)
        missing = [
            name
            for name in (
                "YOUTUBE_CLIENT_ID",
                "YOUTUBE_CLIENT_SECRET",
                "YOUTUBE_REFRESH_TOKEN",
            )
            if not source.get(name)
        ]
        if missing:
            raise YouTubeUploadError(
                f"Missing YouTube OAuth environment variables: {', '.join(missing)}"
            )
        return cls(
            client_id=source["YOUTUBE_CLIENT_ID"],
            client_secret=source["YOUTUBE_CLIENT_SECRET"],
            refresh_token=source["YOUTUBE_REFRESH_TOKEN"],
        )


class YouTubeUploadService:
    """Uploads videos to YouTube with resumable uploads."""

    def __init__(
        self,
        credentials: OAuthCredentials,
        client_factory: Any | None = None,
        chunk_size: int = 4 * 1024 * 1024,
    ) -> None:
        """Initialize the upload service.

        Args:
            credentials: OAuth credentials for the target channel.
            client_factory: Optional callable returning an authenticated
                YouTube API client. Injected in tests; built from the
                credentials when omitted.
            chunk_size: Resumable upload chunk size in bytes.
        """
        self.credentials = credentials
        self.client_factory = client_factory
        self.chunk_size = chunk_size
        self._client: Any | None = None

    def client(self) -> Any:
        """Return a cached authenticated YouTube API client."""
        if self._client is None:
            factory = self.client_factory or self._build_client
            self._client = factory()
        return self._client

    def upload(self, request: UploadRequest) -> dict[str, Any]:
        """Upload a video and optionally set its thumbnail.

        Args:
            request: Upload metadata and local file paths.

        Returns:
            Dictionary with status, video_id and video_url.

        Raises:
            YouTubeUploadError: If the API reports no uploaded video.
        """
        body = {
            "snippet": {
                "title": request.title,
                "description": request.description,
                "tags": request.tags,
                "categoryId": request.category_id,
            },
            "status": {
                "privacyStatus": request.privacy_status,
                "selfDeclaredMadeForKids": request.made_for_kids,
            },
        }

        media = self._build_media(request.video_path)
        insert = (
            self.client()
            .videos()
            .insert(part="snippet,status", body=body, media_body=media)
        )
        response = self._resumable_execute(insert)

        video_id = (response or {}).get("id")
        if not video_id:
            raise YouTubeUploadError(f"Upload returned no video id: {response}")

        result: dict[str, Any] = {
            "status": "completed",
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "privacy_status": request.privacy_status,
        }

        if request.thumbnail_path:
            result["thumbnail"] = self._set_thumbnail(video_id, request.thumbnail_path)

        logger.info(f"Uploaded video {video_id} ({request.privacy_status})")
        return result

    def _set_thumbnail(self, video_id: str, thumbnail_path: str) -> dict[str, Any]:
        """Attach a custom thumbnail, tolerating channels without the feature."""
        if not os.path.exists(thumbnail_path):
            return {"status": "skipped", "reason": "thumbnail file not found"}
        try:
            self.client().thumbnails().set(
                videoId=video_id, media_body=self._build_media(thumbnail_path)
            ).execute()
            return {"status": "completed"}
        except Exception as error:  # noqa: BLE001 - thumbnail is best effort
            logger.warning(f"Thumbnail upload failed for {video_id}: {error}")
            return {"status": "failed", "error": str(error)}

    def _resumable_execute(self, insert_request: Any) -> dict[str, Any]:
        """Drive a resumable upload to completion."""
        response = None
        while response is None:
            _, response = insert_request.next_chunk()
        return response

    def _build_media(self, path: str) -> Any:
        """Build a resumable media upload body for a local file."""
        from googleapiclient.http import MediaFileUpload

        return MediaFileUpload(path, chunksize=self.chunk_size, resumable=True)

    def _build_client(self) -> Any:
        """Build an authenticated YouTube API client from the refresh token."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        credentials = Credentials(
            token=None,
            refresh_token=self.credentials.refresh_token,
            client_id=self.credentials.client_id,
            client_secret=self.credentials.client_secret,
            token_uri=TOKEN_URI,
            scopes=list(UPLOAD_SCOPES),
        )
        return build("youtube", "v3", credentials=credentials, cache_discovery=False)
