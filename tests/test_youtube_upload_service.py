"""Tests for the YouTube upload service."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.services.youtube_upload_service import (
    OAuthCredentials,
    UploadRequest,
    YouTubeUploadError,
    YouTubeUploadService,
)


def _video_file(tmp_path) -> str:
    """Create a placeholder video file."""
    path = tmp_path / "video.mp4"
    path.write_bytes(b"mp4")
    return str(path)


def _credentials() -> OAuthCredentials:
    """Build dummy OAuth credentials."""
    return OAuthCredentials(
        client_id="id", client_secret="secret", refresh_token="refresh"
    )


class _FakeInsert:
    """Fake resumable insert request completing after two chunks."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls = 0

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        self.calls += 1
        if self.calls < 2:
            return (MagicMock(progress=lambda: 0.5), None)
        return (None, self.response)


def _client_with(insert: _FakeInsert) -> MagicMock:
    """Build a fake YouTube API client returning the given insert request."""
    client = MagicMock()
    client.videos.return_value.insert.return_value = insert
    return client


def test_upload_request_validates_metadata(tmp_path) -> None:
    """Invalid metadata is rejected before any API call."""
    video = _video_file(tmp_path)

    with pytest.raises(ValueError):
        UploadRequest(video_path="/missing.mp4", title="Title")
    with pytest.raises(ValueError):
        UploadRequest(video_path=video, title="  ")
    with pytest.raises(ValueError):
        UploadRequest(video_path=video, title="x" * 101)
    with pytest.raises(ValueError):
        UploadRequest(video_path=video, title="Title", description="x" * 5001)
    with pytest.raises(ValueError):
        UploadRequest(video_path=video, title="Title", privacy_status="secret")


def test_credentials_from_env_requires_all_variables() -> None:
    """Missing OAuth variables are reported together."""
    with pytest.raises(YouTubeUploadError) as error:
        OAuthCredentials.from_env({"YOUTUBE_CLIENT_ID": "id"})

    assert "YOUTUBE_CLIENT_SECRET" in str(error.value)
    assert "YOUTUBE_REFRESH_TOKEN" in str(error.value)


def test_credentials_from_env_reads_all_variables() -> None:
    """All three variables are read from the supplied environment."""
    credentials = OAuthCredentials.from_env(
        {
            "YOUTUBE_CLIENT_ID": "id",
            "YOUTUBE_CLIENT_SECRET": "secret",
            "YOUTUBE_REFRESH_TOKEN": "refresh",
        }
    )

    assert credentials.client_id == "id"
    assert credentials.refresh_token == "refresh"


def test_upload_sends_public_metadata_and_returns_url(tmp_path) -> None:
    """Upload posts the snippet/status body and returns the watch URL."""
    insert = _FakeInsert({"id": "abc123"})
    client = _client_with(insert)
    service = YouTubeUploadService(_credentials(), client_factory=lambda: client)
    request = UploadRequest(
        video_path=_video_file(tmp_path),
        title="My Short",
        description="Body",
        tags=["ai"],
        privacy_status="public",
    )

    with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
        result = service.upload(request)

    assert result == {
        "status": "completed",
        "video_id": "abc123",
        "video_url": "https://www.youtube.com/watch?v=abc123",
        "privacy_status": "public",
    }
    assert insert.calls == 2
    body = client.videos.return_value.insert.call_args.kwargs["body"]
    assert body["snippet"]["title"] == "My Short"
    assert body["status"]["privacyStatus"] == "public"


def test_upload_raises_without_video_id(tmp_path) -> None:
    """A response without an id is treated as a failure."""
    service = YouTubeUploadService(
        _credentials(), client_factory=lambda: _client_with(_FakeInsert({}))
    )
    request = UploadRequest(video_path=_video_file(tmp_path), title="Title")

    with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
        with pytest.raises(YouTubeUploadError):
            service.upload(request)


def test_thumbnail_failure_does_not_fail_upload(tmp_path) -> None:
    """A thumbnail error is reported without failing the upload."""
    thumbnail = tmp_path / "thumb.jpg"
    thumbnail.write_bytes(b"jpg")
    client = _client_with(_FakeInsert({"id": "abc123"}))
    client.thumbnails.return_value.set.return_value.execute.side_effect = RuntimeError(
        "not enabled"
    )
    service = YouTubeUploadService(_credentials(), client_factory=lambda: client)
    request = UploadRequest(
        video_path=_video_file(tmp_path),
        title="Title",
        thumbnail_path=str(thumbnail),
    )

    with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
        result = service.upload(request)

    assert result["status"] == "completed"
    assert result["thumbnail"]["status"] == "failed"


def test_client_is_cached() -> None:
    """The client factory runs only once."""
    factory = MagicMock(return_value=MagicMock())
    service = YouTubeUploadService(_credentials(), client_factory=factory)

    service.client()
    service.client()

    factory.assert_called_once()
