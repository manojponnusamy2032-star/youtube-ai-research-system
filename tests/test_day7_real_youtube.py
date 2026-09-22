"""Day-7 tests: real YouTube publishing readiness and safety (fully offline).

Complements ``tests/test_day7_real_publish.py``.  This module exercises the
REAL ``YouTubeUploadService`` (with an offline fake Google API client, so no
network and no credentials are needed) behind ``YouTubePublisher``, and covers:

* credential configuration and malformed configuration
* OAuth initialization failure
* successful upload response handling (video id + URL extraction)
* unlisted privacy enforcement
* API / upload failure handling
* idempotency and publish gate rejection
* no secret leakage in errors or logs
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishStatus, PublishVisibility
from src.orchestration.youtube_publisher import YouTubePublisher
from src.services.youtube_upload_service import (
    OAuthCredentials,
    UploadRequest,
    YouTubeUploadError,
    YouTubeUploadService,
)

# Values that must never appear in errors or logs.
CLIENT_SECRET = "day7-client-secret-value"
REFRESH_TOKEN = "day7-refresh-token-value"
CLIENT_ID = "day7-client-id.apps.googleusercontent.com"

ENV_VARS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")


def _video(tmp_path) -> str:
    """Create a placeholder MP4 artifact."""
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fake video bytes")
    return str(path)


def _pass_qc(job_id: str = "job_001") -> QCReport:
    return QCReport(
        job_id=job_id, overall_status=QCStatus.PASS, publish_ready=True, checks=[]
    )


def _fail_qc(job_id: str = "job_001") -> QCReport:
    return QCReport(
        job_id=job_id, overall_status=QCStatus.FAIL, publish_ready=False, checks=[]
    )


def _job(job_id: str = "job_001", video_path: str | None = None) -> VideoJob:
    artifact = None
    if video_path:
        artifact = VideoArtifact(job_id=job_id, output_path=video_path)
    return VideoJob(
        job_id=job_id,
        topic="Day-7 verification topic",
        status=JobStatus.COMPLETED,
        artifact=artifact,
    )


def _credentials() -> OAuthCredentials:
    return OAuthCredentials(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        refresh_token=REFRESH_TOKEN,
    )


class _FakeInsert:
    """Fake resumable insert completing after two chunks."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls = 0

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        self.calls += 1
        if self.calls < 2:
            return (MagicMock(progress=lambda: 0.5), None)
        return (None, self.response)


class _FailingInsert:
    """Fake insert that raises the supplied error on first chunk."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        self.calls += 1
        raise self.error


def _client_with(insert: Any) -> MagicMock:
    client = MagicMock()
    client.videos.return_value.insert.return_value = insert
    return client


def _insert_body(client: MagicMock) -> dict[str, Any]:
    return client.videos.return_value.insert.call_args.kwargs["body"]


def _publisher_with_real_service(
    monkeypatch, insert: Any
) -> tuple[YouTubePublisher, MagicMock]:
    """Point the publisher at the REAL upload service using a fake client."""
    import src.orchestration.youtube_publisher as mod

    client = _client_with(insert)
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", REFRESH_TOKEN)
    monkeypatch.setattr(
        mod,
        "YouTubeUploadService",
        lambda credentials: YouTubeUploadService(
            credentials, client_factory=lambda: client
        ),
    )
    return YouTubePublisher(mock=False), client
class TestCredentialConfiguration:
    """Only the three OAuth variables are required; none are optional."""

    def test_blank_credentials_are_malformed_configuration(self):
        with pytest.raises(YouTubeUploadError) as exc:
            OAuthCredentials.from_env(
                {
                    "YOUTUBE_CLIENT_ID": "   ",
                    "YOUTUBE_CLIENT_SECRET": "",
                    "YOUTUBE_REFRESH_TOKEN": "\t",
                }
            )
        message = str(exc.value)
        for name in ENV_VARS:
            assert name in message

    def test_wrong_type_credentials_are_malformed_configuration(self):
        with pytest.raises(YouTubeUploadError):
            OAuthCredentials.from_env(
                {
                    "YOUTUBE_CLIENT_ID": None,
                    "YOUTUBE_CLIENT_SECRET": 0,
                    "YOUTUBE_REFRESH_TOKEN": False,
                }
            )

    def test_api_key_is_not_required(self):
        creds = OAuthCredentials.from_env(
            {
                "YOUTUBE_CLIENT_ID": CLIENT_ID,
                "YOUTUBE_CLIENT_SECRET": CLIENT_SECRET,
                "YOUTUBE_REFRESH_TOKEN": REFRESH_TOKEN,
            }
        )
        assert creds.client_id == CLIENT_ID
        assert creds.refresh_token == REFRESH_TOKEN

    def test_partial_credentials_fail_safely_without_upload(
        self, tmp_path, monkeypatch
    ):
        for var in ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", CLIENT_ID)  # partial config only
        video = _video(tmp_path)
        publisher = YouTubePublisher(mock=False)

        def _explode(*args, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("upload service must not be built without credentials")

        import src.orchestration.youtube_publisher as mod

        monkeypatch.setattr(mod, "YouTubeUploadService", _explode)
        result = publisher.publish(job_id="job_001", video_path=video, title="T")

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "credentials" in (result.error or "").lower()
        assert publisher.upload_called is False


class TestOAuthInitializationFailure:
    """Token/OAuth initialization problems become controlled failures."""

    def test_oauth_init_error_is_controlled_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        import src.orchestration.youtube_publisher as mod

        def _raise(cls, env=None):
            raise YouTubeUploadError("invalid_grant: token has been revoked")

        monkeypatch.setattr(mod.OAuthCredentials, "from_env", classmethod(_raise))
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(job_id="job_001", video_path=video, title="T")

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "credentials" in (result.error or "").lower()
        assert publisher.upload_called is False

    def test_oauth_init_failure_persists_nothing(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        import src.orchestration.youtube_publisher as mod

        def _raise(cls, env=None):
            raise YouTubeUploadError("invalid_grant: token has been revoked")

        monkeypatch.setattr(mod.OAuthCredentials, "from_env", classmethod(_raise))
        service = PublishService(
            publisher=YouTubePublisher(mock=False), output_dir=str(tmp_path)
        )
        gate, published = service.publish(_job(video_path=video), _pass_qc())

        assert gate.allowed is True
        assert published is not None
        assert published.status == PublishStatus.FAILED
        assert not (tmp_path / "job_001" / "publish_result.json").exists()

    def test_oauth_library_error_is_controlled_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        import src.orchestration.youtube_publisher as mod

        def _raise(cls, env=None):
            raise RuntimeError("google-auth import failed")

        monkeypatch.setattr(mod.OAuthCredentials, "from_env", classmethod(_raise))
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(job_id="job_001", video_path=video, title="T")

        assert result.status == PublishStatus.FAILED
        assert publisher.upload_called is False
class TestRealUploadServiceResponse:
    """The real upload service response is converted into a PublishedVideo."""

    def test_video_id_and_url_extracted(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FakeInsert(
            {"status": "completed", "id": "day7VID001", "privacyStatus": "unlisted"}
        )
        publisher, client = _publisher_with_real_service(monkeypatch, insert)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_001",
                video_path=video,
                title="YAIRS Day-7 verification upload",
                visibility="unlisted",
            )

        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "day7VID001"
        assert result.video_url == "https://www.youtube.com/watch?v=day7VID001"
        assert result.visibility == PublishVisibility.UNLISTED
        assert publisher.upload_called is True
        assert insert.calls == 2

    def test_unlisted_privacy_enforced_in_api_body(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "day7VID002"})
        publisher, client = _publisher_with_real_service(monkeypatch, insert)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            # No visibility passed at all: must default to unlisted, never public.
            result = publisher.publish(
                job_id="job_001",
                video_path=video,
                title="YAIRS Day-7 verification upload",
            )

        assert result.visibility == PublishVisibility.UNLISTED
        assert _insert_body(client)["status"]["privacyStatus"] == "unlisted"

    def test_public_request_is_forced_to_unlisted(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "day7VID003"})
        publisher, client = _publisher_with_real_service(monkeypatch, insert)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_001",
                video_path=video,
                title="YAIRS Day-7 verification upload",
                visibility="public",  # no allow_public opt-in
            )

        assert result.visibility == PublishVisibility.UNLISTED
        assert _insert_body(client)["status"]["privacyStatus"] == "unlisted"

    def test_request_metadata_forwarded(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "day7VID004"})
        publisher, client = _publisher_with_real_service(monkeypatch, insert)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_001",
                video_path=video,
                title="YAIRS Day-7 verification upload",
                description="Automated Day-7 verification upload.",
                tags=["yairs", "day7"],
                category_id="22",
            )

        body = _insert_body(client)
        assert result.title == "YAIRS Day-7 verification upload"
        assert body["snippet"]["title"] == "YAIRS Day-7 verification upload"
        assert body["snippet"]["description"] == "Automated Day-7 verification upload."
        assert body["snippet"]["categoryId"] == "22"
        assert body["snippet"]["tags"] == ["yairs", "day7"]

    def test_service_upload_result_maps_to_published_video(self, tmp_path, monkeypatch):
        """Direct service -> response mapping (real class, fake client)."""
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "day7VID005"})
        client = _client_with(insert)
        service = YouTubeUploadService(_credentials(), client_factory=lambda: client)
        request = UploadRequest(
            video_path=video,
            title="YAIRS Day-7 verification upload",
            privacy_status="unlisted",
        )

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            response = service.upload(request)

        assert response["video_id"] == "day7VID005"
        assert response["video_url"] == "https://www.youtube.com/watch?v=day7VID005"
        assert response["privacy_status"] == "unlisted"

class TestUploadFailureHandling:
    """API and upload failures are reported, never persisted as success."""

    def test_api_error_is_controlled_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FailingInsert(YouTubeUploadError("quotaExceeded: upload limit"))
        publisher, _ = _publisher_with_real_service(monkeypatch, insert)

        result = publisher.publish(
            job_id="job_001", video_path=video, title="T", visibility="unlisted"
        )

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "quota" in (result.error or "").lower()
        assert publisher.upload_called is False

    def test_unexpected_exception_is_controlled_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FailingInsert(RuntimeError("socket closed"))
        publisher, _ = _publisher_with_real_service(monkeypatch, insert)

        result = publisher.publish(job_id="job_001", video_path=video, title="T")

        assert result.status == PublishStatus.FAILED
        assert "socket closed" in (result.error or "")

    def test_failed_upload_persists_nothing(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FailingInsert(YouTubeUploadError("quotaExceeded"))
        publisher, _ = _publisher_with_real_service(monkeypatch, insert)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))

        gate, published = service.publish(_job(video_path=video), _pass_qc())

        assert gate.allowed is True
        assert published is not None
        assert published.status == PublishStatus.FAILED
        assert not (tmp_path / "job_001" / "publish_result.json").exists()


class TestIdempotencyAndGate:
    """One upload per job; the gate blocks non-publish-ready QC."""

    def test_second_publish_reuses_result_without_second_upload(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "day7VID006"})
        publisher, client = _publisher_with_real_service(monkeypatch, insert)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            _gate1, first = service.publish(_job(video_path=video), _pass_qc())
            _gate2, second = service.publish(_job(video_path=video), _pass_qc())

        assert first is not None and first.status == PublishStatus.COMPLETED
        assert second is not None and second.video_id == first.video_id
        assert second.status == PublishStatus.COMPLETED
        assert insert.calls == 2  # two chunks of a SINGLE insert = one upload
        assert (tmp_path / "job_001" / "publish_result.json").exists()

    def test_gate_rejection_never_calls_upload(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "shouldNotExist"})
        publisher, client = _publisher_with_real_service(monkeypatch, insert)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))

        gate, published = service.publish(_job(video_path=video), _fail_qc())

        assert gate.allowed is False
        assert published is None
        assert insert.calls == 0
        assert publisher.upload_called is False
        assert client.videos.return_value.insert.call_count == 0
        assert not (tmp_path / "job_001" / "publish_result.json").exists()

    def test_missing_video_artifact_is_blocked(self, tmp_path, monkeypatch):
        insert = _FakeInsert({"status": "completed", "id": "shouldNotExist"})
        publisher, _ = _publisher_with_real_service(monkeypatch, insert)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))

        gate, published = service.publish(_job(video_path=None), _pass_qc())

        assert gate.allowed is False
        assert published is None
        assert insert.calls == 0
        assert publisher.upload_called is False
class TestNoSecretLeakage:
    """Secrets never appear in failures, artifacts or logs."""

    def test_upload_failure_does_not_leak_secrets(self, tmp_path, monkeypatch, caplog):
        video = _video(tmp_path)
        insert = _FailingInsert(YouTubeUploadError("quotaExceeded"))
        publisher, _ = _publisher_with_real_service(monkeypatch, insert)

        with caplog.at_level(logging.DEBUG):
            result = publisher.publish(
                job_id="job_001", video_path=video, title="T", visibility="unlisted"
            )

        combined = f"{result.error or ''} {result.service_response} {caplog.text}"
        assert CLIENT_SECRET not in combined
        assert REFRESH_TOKEN not in combined

    def test_credential_failure_does_not_leak_secrets(
        self, tmp_path, monkeypatch, caplog
    ):
        video = _video(tmp_path)
        import src.orchestration.youtube_publisher as mod

        def _raise(cls, env=None):
            raise YouTubeUploadError(
                "Missing YouTube OAuth environment variables: "
                "YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN"
            )

        monkeypatch.setattr(mod.OAuthCredentials, "from_env", classmethod(_raise))
        publisher = YouTubePublisher(mock=False)

        with caplog.at_level(logging.DEBUG):
            result = publisher.publish(job_id="job_001", video_path=video, title="T")

        combined = f"{result.error or ''} {caplog.text}"
        assert CLIENT_SECRET not in combined
        assert REFRESH_TOKEN not in combined
        for name in ENV_VARS:
            assert name in combined  # only the variable NAMES are reported

    def test_persisted_artifact_contains_no_secrets(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        insert = _FakeInsert({"status": "completed", "id": "day7VID007"})
        publisher, _ = _publisher_with_real_service(monkeypatch, insert)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            service.publish(_job(video_path=video), _pass_qc())

        text = (tmp_path / "job_001" / "publish_result.json").read_text(
            encoding="utf-8"
        )
        assert CLIENT_SECRET not in text
        assert REFRESH_TOKEN not in text
        assert CLIENT_ID not in text
        assert "day7VID007" in text