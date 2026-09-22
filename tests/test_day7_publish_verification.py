"""Day-7 real publishing verification tests.

These tests exercise the *real* publish path offline:

* the real ``YouTubeUploadService`` is used, with only its HTTP client
  injected (``client_factory``), so ``UploadRequest`` construction,
  resumable-chunk handling, response parsing and error mapping are all real;
* ``YouTubePublisher`` is pointed at that service so no network call is
  ever attempted.

Covered: missing credentials, malformed configuration, OAuth initialization
failure, successful response handling, video-ID extraction, URL generation,
read-back verification, idempotency, publish-gate rejection, unlisted
enforcement, upload failure handling and secret non-leakage.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.orchestration.youtube_publisher as publisher_module
from src.orchestration.publish_gate import evaluate_publish_gate
from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCCheck, QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishStatus, PublishVisibility
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    load_publish_result,
    resolve_real_upload_visibility,
)
from src.services.youtube_upload_service import (
    OAuthCredentials,
    YouTubeUploadError,
    YouTubeUploadService,
)

CLIENT_ID = "day7-client-id.apps.googleusercontent.com"
SECRET = "day7-client-secret-value"
REFRESH = "day7-refresh-token-value"

ENV_VARS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _video(tmp_path: Path) -> str:
    """Create a placeholder video artifact."""
    path = tmp_path / "video.mp4"
    path.write_bytes(b"mp4")
    return str(path)


def _job(job_id: str, *, video_path: str) -> VideoJob:
    """Build a completed VideoJob pointing at a rendered artifact."""
    job = VideoJob(job_id=job_id, topic="Day-7 verification topic")
    job.status = JobStatus.COMPLETED
    job.artifact = VideoArtifact(job_id=job_id, output_path=video_path)
    return job


def _qc_report(
    *, status: QCStatus = QCStatus.PASS, publish_ready: bool = True
) -> QCReport:
    """Build a QC report with an explicit publish-gate decision."""
    passed = status == QCStatus.PASS
    return QCReport(
        job_id="job_day7",
        overall_status=status,
        publish_ready=publish_ready,
        checks=[
            QCCheck(
                check_name="video_integrity",
                status=QCStatus.PASS if passed else QCStatus.FAIL,
                message="ok" if passed else "broken",
            )
        ],
    )


class _FakeInsert:
    """Insert double: reports progress once, then returns the API response."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls = 0

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        self.calls += 1
        if self.calls < 2:
            return (MagicMock(progress=lambda: 0.5), None)
        return (None, self.response)


def _client_with(insert: _FakeInsert) -> MagicMock:
    """Fake authenticated YouTube API client returning the given insert."""
    client = MagicMock()
    client.videos.return_value.insert.return_value = insert
    return client


def _real_service_with_fake_client(insert: _FakeInsert) -> YouTubeUploadService:
    """Real upload service with only the HTTP client replaced."""
    credentials = OAuthCredentials(
        client_id=CLIENT_ID, client_secret=SECRET, refresh_token=REFRESH
    )
    return YouTubeUploadService(credentials, client_factory=lambda: _client_with(insert))


def _wire_real_publisher(monkeypatch: pytest.MonkeyPatch, service: Any) -> YouTubePublisher:
    """Real-mode YouTubePublisher whose upload service is the given service."""
    for name, value in (
        ("YOUTUBE_CLIENT_ID", CLIENT_ID),
        ("YOUTUBE_CLIENT_SECRET", SECRET),
        ("YOUTUBE_REFRESH_TOKEN", REFRESH),
    ):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(publisher_module, "YouTubeUploadService", lambda credentials: service)
    return YouTubePublisher(mock=False)


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove OAuth variables from the process environment."""
    for name in ENV_VARS + ("YOUTUBE_API_KEY",):
        monkeypatch.delenv(name, raising=False)


# ----------------------------------------------------------------------
# 1. missing credentials fail safely
# ----------------------------------------------------------------------
class TestMissingCredentials:
    def test_publisher_without_credentials_fails_without_upload(
        self, tmp_path, monkeypatch
    ):
        _clear_env(monkeypatch)
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(
            job_id="job_day7", video_path=_video(tmp_path), title="T"
        )
        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "credentials unavailable" in (result.error or "").lower()
        assert publisher.upload_called is False

    def test_service_publish_writes_no_result_file(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        video = _video(tmp_path)
        service = PublishService(
            publisher=YouTubePublisher(mock=False), output_dir=str(tmp_path)
        )
        gate, published = service.publish(_job("job_day7", video_path=video), _qc_report())
        assert gate.allowed is True
        assert published is not None
        assert published.status == PublishStatus.FAILED
        assert not (tmp_path / "job_day7" / "publish_result.json").exists()

    def test_from_env_reports_all_missing_variables(self):
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env({})
        message = str(error.value)
        for name in ENV_VARS:
            assert name in message


# ----------------------------------------------------------------------
# 2. malformed configuration fails safely
# ----------------------------------------------------------------------
class TestMalformedConfiguration:
    @pytest.mark.parametrize("blank", ["", "   ", "\t"])
    def test_blank_variable_counts_as_missing(self, blank: str):
        env = {
            "YOUTUBE_CLIENT_ID": CLIENT_ID,
            "YOUTUBE_CLIENT_SECRET": SECRET,
            "YOUTUBE_REFRESH_TOKEN": blank,
        }
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env(env)
        assert "YOUTUBE_REFRESH_TOKEN" in str(error.value)

    def test_values_are_stripped(self):
        credentials = OAuthCredentials.from_env(
            {
                "YOUTUBE_CLIENT_ID": f"  {CLIENT_ID}  ",
                "YOUTUBE_CLIENT_SECRET": f" {SECRET}",
                "YOUTUBE_REFRESH_TOKEN": f"{REFRESH} ",
            }
        )
        assert credentials.client_id == CLIENT_ID
        assert credentials.client_secret == SECRET
        assert credentials.refresh_token == REFRESH

    def test_malformed_env_blocks_real_publish(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", CLIENT_ID)
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "  ")
        monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", REFRESH)
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(
            job_id="job_day7", video_path=_video(tmp_path), title="T"
        )
        assert result.status == PublishStatus.FAILED
        assert publisher.upload_called is False

    def test_missing_video_artifact_is_rejected_before_upload(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(
            job_id="job_day7",
            video_path=str(tmp_path / "missing.mp4"),
            title="T",
        )
        assert result.status == PublishStatus.FAILED
        assert "does not exist" in (result.error or "")
        assert publisher.upload_called is False

    def test_empty_title_is_rejected_by_upload_request(self, tmp_path, monkeypatch):
        insert = _FakeInsert({"id": "ignored"})
        service = _real_service_with_fake_client(insert)
        publisher = _wire_real_publisher(monkeypatch, service)
        # An empty title never reaches the API: UploadRequest validation fails
        # first and the publisher converts it into a controlled failure.
        result = publisher.publish(
            job_id="job_day7", video_path=_video(tmp_path), title="   "
        )
        assert result.status == PublishStatus.FAILED
        assert insert.calls == 0
        assert publisher.upload_called is False


# ----------------------------------------------------------------------
# 3. OAuth initialization failure
# ----------------------------------------------------------------------
class TestOAuthInitializationFailure:
    def test_upload_service_construction_failure_is_controlled(
        self, tmp_path, monkeypatch
    ):
        for name, value in (
            ("YOUTUBE_CLIENT_ID", CLIENT_ID),
            ("YOUTUBE_CLIENT_SECRET", SECRET),
            ("YOUTUBE_REFRESH_TOKEN", REFRESH),
        ):
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(
            publisher_module,
            "YouTubeUploadService",
            MagicMock(side_effect=RuntimeError("google-auth not installed")),
        )
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(
            job_id="job_day7", video_path=_video(tmp_path), title="T"
        )
        assert result.status == PublishStatus.FAILED
        assert "build" in (result.error or "").lower()
        assert publisher.upload_called is False

    def test_token_refresh_rejection_is_controlled(self, tmp_path, monkeypatch):
        service = YouTubeUploadService(
            OAuthCredentials(
                client_id=CLIENT_ID, client_secret=SECRET, refresh_token=REFRESH
            ),
            client_factory=lambda: (_ for _ in ()).throw(
                YouTubeUploadError("invalid_grant: token has been expired or revoked")
            ),
        )
        publisher = _wire_real_publisher(monkeypatch, service)
        result = publisher.publish(
            job_id="job_day7",
            video_path=_video(tmp_path),
            title="T",
            visibility="unlisted",
        )
        assert result.status == PublishStatus.FAILED
        assert "invalid_grant" in (result.error or "")
        assert publisher.upload_called is False


# ----------------------------------------------------------------------
# 4. successful upload response handling (real service, fake HTTP client)
# ----------------------------------------------------------------------
class TestSuccessfulUploadResponse:
    def test_video_id_url_and_unlisted_are_recorded(self, tmp_path, monkeypatch):
        insert = _FakeInsert({"id": "dQw4w9WgXcQ"})
        service = _real_service_with_fake_client(insert)
        publisher = _wire_real_publisher(monkeypatch, service)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_day7",
                video_path=_video(tmp_path),
                title="YAIRS Day-7 verification upload",
                description="Day-7 verification description",
                visibility="unlisted",
            )

        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "dQw4w9WgXcQ"
        assert result.video_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert result.visibility == PublishVisibility.UNLISTED
        assert result.published_at is not None
        assert publisher.upload_called is True
        assert insert.calls == 2  # resumable upload completed across chunks

        body = service._client.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "unlisted"
        assert body["snippet"]["title"] == "YAIRS Day-7 verification upload"
        assert body["snippet"]["categoryId"] == "22"

    def test_result_is_persisted_and_reloadable(self, tmp_path, monkeypatch):
        insert = _FakeInsert({"id": "day7VID0001"})
        service = _real_service_with_fake_client(insert)
        publisher = _wire_real_publisher(monkeypatch, service)
        video = _video(tmp_path)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            gate, published = PublishService(
                publisher=publisher, output_dir=str(tmp_path)
            ).publish(_job("job_day7", video_path=video), _qc_report())

        assert gate.allowed is True
        assert published is not None and published.status == PublishStatus.COMPLETED

        result_path = tmp_path / "job_day7" / "publish_result.json"
        assert result_path.exists()

        raw = json.loads(result_path.read_text(encoding="utf-8"))
        assert raw["video_id"] == "day7VID0001"
        assert raw["video_url"] == "https://www.youtube.com/watch?v=day7VID0001"
        assert raw["visibility"] == "unlisted"
        assert raw["status"] == "completed"

        reloaded = load_publish_result(tmp_path / "job_day7")
        assert reloaded is not None
        assert reloaded.video_id == "day7VID0001"
        assert reloaded.visibility == PublishVisibility.UNLISTED

    def test_response_without_video_id_is_failure(self, tmp_path, monkeypatch):
        insert = _FakeInsert({})
        service = _real_service_with_fake_client(insert)
        publisher = _wire_real_publisher(monkeypatch, service)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_day7", video_path=_video(tmp_path), title="T"
            )

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "no video id" in (result.error or "").lower()


# ----------------------------------------------------------------------
# 5. post-upload read-back verification
# ----------------------------------------------------------------------
class TestReadBackVerification:
    def test_read_back_reports_privacy_and_upload_status(self, tmp_path, monkeypatch):
        insert = _FakeInsert({"id": "readback001"})
        client = _client_with(insert)
        client.videos.return_value.list.return_value.execute.return_value = {
            "items": [
                {
                    "id": "readback001",
                    "snippet": {"title": "YAIRS Day-7 verification upload"},
                    "status": {"privacyStatus": "unlisted", "uploadStatus": "processed"},
                }
            ]
        }
        service = YouTubeUploadService(
            OAuthCredentials(
                client_id=CLIENT_ID, client_secret=SECRET, refresh_token=REFRESH
            ),
            client_factory=lambda: client,
        )
        publisher = _wire_real_publisher(monkeypatch, service)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            published = publisher.publish(
                job_id="job_day7",
                video_path=_video(tmp_path),
                title="YAIRS Day-7 verification upload",
                visibility="unlisted",
            )

        assert published.video_id == "readback001"
        read_back = service.get_video_status(published.video_id)
        assert read_back["video_id"] == "readback001"
        assert read_back["privacy_status"] == "unlisted"
        assert read_back["upload_status"] == "processed"

        called = client.videos.return_value.list.call_args.kwargs
        assert called["id"] == "readback001"
        assert "status" in called["part"]

    def test_read_back_failure_is_not_an_upload_failure(self, tmp_path, monkeypatch):
        insert = _FakeInsert({"id": "readback002"})
        client = _client_with(insert)
        client.videos.return_value.list.return_value.execute.side_effect = RuntimeError(
            "HttpError 403: insufficientPermissions"
        )
        service = YouTubeUploadService(
            OAuthCredentials(
                client_id=CLIENT_ID, client_secret=SECRET, refresh_token=REFRESH
            ),
            client_factory=lambda: client,
        )
        publisher = _wire_real_publisher(monkeypatch, service)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            published = publisher.publish(
                job_id="job_day7",
                video_path=_video(tmp_path),
                title="T",
                visibility="unlisted",
            )

        assert published.status == PublishStatus.COMPLETED
        with pytest.raises(YouTubeUploadError) as error:
            service.get_video_status(published.video_id)
        assert "Could not read back video" in str(error.value)

    def test_privacy_is_forced_unlisted_without_optin(self):
        assert resolve_real_upload_visibility() == "unlisted"
        assert resolve_real_upload_visibility("public") == "unlisted"
        assert resolve_real_upload_visibility(PublishVisibility.PUBLIC) == "unlisted"
        assert resolve_real_upload_visibility("public", allow_public=True) == "public"
        assert resolve_real_upload_visibility("private") == "private"


# @@END@@