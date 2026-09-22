"""Day-7 tests: real publisher path driven through the REAL YouTubeUploadService.

Unlike ``tests/test_day7_real_publish.py`` (which fakes the whole upload
service), these tests inject a fake *YouTube API client* into the real
``YouTubeUploadService`` and drive it through ``YouTubePublisher``.  That proves
the real adapter:

* loads credentials from the environment,
* constructs a genuine ``UploadRequest``,
* calls the real ``YouTubeUploadService.upload`` signature,
* converts the real result dict into ``PublishedVideo``,
* derives the watch URL from the extracted video id,
* enforces unlisted privacy,
* propagates controlled failures, and
* never leaks secret material into errors or persisted artifacts.

No network access and no credentials are required.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishStatus, PublishVisibility
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    load_publish_result,
    write_publish_result,
)
from src.services.youtube_upload_service import (
    OAuthCredentials,
    YouTubeUploadError,
    YouTubeUploadService,
)


def _video(tmp_path) -> str:
    """Create a placeholder rendered video artifact."""
    path = tmp_path / "video.mp4"
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
    return str(path)


def _job(job_id: str, video_path: str) -> VideoJob:
    """Minimal completed VideoJob carrying a video artifact."""
    return VideoJob(
        job_id=job_id,
        topic="Day-7 verification topic",
        status=JobStatus.COMPLETED,
        artifact=VideoArtifact(job_id=job_id, output_path=video_path),
    )


def _pass_qc() -> QCReport:
    """A passing, publish-ready QC report."""
    return QCReport(
        job_id="job_001",
        overall_status=QCStatus.PASS,
        publish_ready=True,
        checks=[],
    )


class _FakeInsert:
    """Fake resumable insert request (completes on the second chunk)."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls = 0

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        self.calls += 1
        if self.calls < 2:
            return (MagicMock(progress=lambda: 0.5), None)
        return (None, self.response)


def _client_raising(error: Exception) -> MagicMock:
    """Fake API client whose insert raises ``error`` on the first chunk."""
    insert = MagicMock()
    insert.next_chunk.side_effect = error
    client = MagicMock()
    client.videos.return_value.insert.return_value = insert
    return client


def _publisher_with_fake_client(
    client: MagicMock, monkeypatch, *, credentials: OAuthCredentials | None = None
) -> YouTubePublisher:
    """Real YouTubePublisher wired to the real service with a fake API client."""
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "test-client-secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "test-refresh-token")
    creds = credentials or OAuthCredentials.from_env()
    service = YouTubeUploadService(creds, client_factory=lambda: client)
    monkeypatch.setattr(
        "src.orchestration.youtube_publisher.YouTubeUploadService",
        lambda credentials: service,
    )
    return YouTubePublisher(mock=False)
class TestRealPathThroughUploadService:
    def test_real_upload_request_and_result_conversion(self, tmp_path, monkeypatch):
        """The real service receives a real UploadRequest and its result converts."""
        video = _video(tmp_path)
        insert = _FakeInsert({"id": "REALVID12345"})
        client = MagicMock()
        client.videos.return_value.insert.return_value = insert
        publisher = _publisher_with_fake_client(client, monkeypatch)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_real_1",
                video_path=video,
                title="YAIRS Day-7 verification upload",
                description="Day-7 controlled verification upload (unlisted).",
                tags=["yairs", "day7"],
                visibility="unlisted",
            )

        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "REALVID12345"
        assert result.video_url == "https://www.youtube.com/watch?v=REALVID12345"
        assert result.visibility == PublishVisibility.UNLISTED
        assert insert.calls == 2

        body = client.videos.return_value.insert.call_args.kwargs["body"]
        assert body["snippet"]["title"] == "YAIRS Day-7 verification upload"
        assert body["snippet"]["tags"] == ["yairs", "day7"]
        assert body["status"]["privacyStatus"] == "unlisted"

    def test_url_is_derived_from_returned_video_id(self, tmp_path, monkeypatch):
        """The watch URL is generated from the real video id extraction."""
        video = _video(tmp_path)
        insert = _FakeInsert({"id": "DerivedID99"})
        client = MagicMock()
        client.videos.return_value.insert.return_value = insert
        publisher = _publisher_with_fake_client(client, monkeypatch)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_real_2", video_path=video, title="T", visibility="unlisted"
            )

        assert result.video_id == "DerivedID99"
        assert result.video_url.endswith("v=DerivedID99")
        assert result.service_response["privacy_status"] == "unlisted"

    def test_unlisted_forced_even_if_public_requested(self, tmp_path, monkeypatch):
        """Day-7 safety: a public request becomes unlisted without opt-in."""
        video = _video(tmp_path)
        insert = _FakeInsert({"id": "NotPublicID"})
        client = MagicMock()
        client.videos.return_value.insert.return_value = insert
        publisher = _publisher_with_fake_client(client, monkeypatch)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_real_3", video_path=video, title="T", visibility="public"
            )

        body = client.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "unlisted"
        assert result.visibility == PublishVisibility.UNLISTED

    def test_private_is_honoured(self, tmp_path, monkeypatch):
        """``private`` remains selectable."""
        video = _video(tmp_path)
        insert = _FakeInsert({"id": "PrivateID123"})
        client = MagicMock()
        client.videos.return_value.insert.return_value = insert
        publisher = _publisher_with_fake_client(client, monkeypatch)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_real_4", video_path=video, title="T", visibility="private"
            )

        assert result.visibility == PublishVisibility.PRIVATE
        body = client.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "private"
class TestRealPathFailureHandling:
    def test_http_error_becomes_controlled_failure(self, tmp_path, monkeypatch):
        """An API HttpError surfaces as a FAILED PublishedVideo, not a crash."""
        from googleapiclient.errors import HttpError

        video = _video(tmp_path)
        error = HttpError(
            resp=MagicMock(status=403, reason="Forbidden"), content=b"quota"
        )
        publisher = _publisher_with_fake_client(_client_raising(error), monkeypatch)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_fail_1", video_path=video, title="T", visibility="unlisted"
            )

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert result.error

    def test_upload_error_becomes_controlled_failure(self, tmp_path, monkeypatch):
        """A YouTubeUploadError from the service is converted, not re-raised."""
        video = _video(tmp_path)
        publisher = _publisher_with_fake_client(
            _client_raising(YouTubeUploadError("quota exceeded")), monkeypatch
        )

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_fail_2", video_path=video, title="T", visibility="unlisted"
            )

        assert result.status == PublishStatus.FAILED
        assert "quota" in (result.error or "").lower()

    def test_missing_credentials_fail_safely(self, tmp_path, monkeypatch):
        """With no credentials the real path fails without touching the network."""
        for name in (
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_REFRESH_TOKEN",
        ):
            monkeypatch.delenv(name, raising=False)

        called: list[int] = []
        monkeypatch.setattr(
            "src.orchestration.youtube_publisher.YouTubeUploadService",
            lambda credentials: called.append(1),
        )

        result = YouTubePublisher(mock=False, credentials=None).publish(
            job_id="job_nocreds", video_path=_video(tmp_path), title="T"
        )

        assert result.status == PublishStatus.FAILED
        assert "credentials" in (result.error or "").lower()
        assert called == []

    def test_malformed_credentials_fail_safely(self, tmp_path, monkeypatch):
        """Blank/whitespace-only OAuth variables are treated as missing."""
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "   ")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "")
        monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "token")

        called: list[int] = []
        monkeypatch.setattr(
            "src.orchestration.youtube_publisher.YouTubeUploadService",
            lambda credentials: called.append(1),
        )

        result = YouTubePublisher(mock=False, credentials=None).publish(
            job_id="job_badcreds", video_path=_video(tmp_path), title="T"
        )

        assert result.status == PublishStatus.FAILED
        assert "credentials" in (result.error or "").lower()
        assert called == []

    def test_oauth_error_does_not_leak_secret_in_message(self):
        """Credential-loading messages name variables, never their values."""
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env(
                {
                    "YOUTUBE_CLIENT_ID": "super-secret-client-id",
                    "YOUTUBE_CLIENT_SECRET": "super-secret-value",
                }
            )

        message = str(error.value)
        assert "YOUTUBE_REFRESH_TOKEN" in message
        assert "super-secret-value" not in message
        assert "super-secret-client-id" not in message

    def test_upload_failure_error_contains_no_secret(self, tmp_path, monkeypatch):
        """A failed real upload never embeds secret material in the error."""
        video = _video(tmp_path)
        publisher = _publisher_with_fake_client(
            _client_raising(YouTubeUploadError("auth failed")), monkeypatch
        )

class TestRealPathPersistenceAndIdempotency:
    def test_failed_upload_writes_no_publish_result(self, tmp_path, monkeypatch):
        """Failures never persist a publish_result.json."""
        job_dir = tmp_path / "job_persist_fail"
        job_dir.mkdir()
        (job_dir / "video.mp4").write_bytes(b"mp4")
        video = str(job_dir / "video.mp4")

        publisher = _publisher_with_fake_client(
            _client_raising(YouTubeUploadError("boom")), monkeypatch
        )
        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_persist_fail",
                video_path=video,
                title="T",
                visibility="unlisted",
            )

        assert result.status == PublishStatus.FAILED
        assert not (job_dir / "publish_result.json").exists()
        assert load_publish_result(job_dir) is None

    def test_successful_real_result_round_trips_unlisted(self, tmp_path, monkeypatch):
        """A successful real result persists and reloads with unlisted privacy."""
        job_dir = tmp_path / "job_persist_ok"
        job_dir.mkdir()
        (job_dir / "video.mp4").write_bytes(b"mp4")
        video = str(job_dir / "video.mp4")

        insert = _FakeInsert({"id": "PersistedID1"})
        client = MagicMock()
        client.videos.return_value.insert.return_value = insert
        publisher = _publisher_with_fake_client(client, monkeypatch)

        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_persist_ok",
                video_path=video,
                title="T",
                visibility="unlisted",
            )

        path = write_publish_result(result, job_dir)
        assert path.exists()
        reloaded = load_publish_result(job_dir)
        assert reloaded is not None
        assert reloaded.video_id == "PersistedID1"
        assert reloaded.video_url == "https://www.youtube.com/watch?v=PersistedID1"
        assert reloaded.visibility == PublishVisibility.UNLISTED
        assert reloaded.status == PublishStatus.COMPLETED

    def test_real_upload_happens_once_under_idempotency(self, tmp_path, monkeypatch):
        """A completed publish_result.json short-circuits a second upload."""
        job_dir = tmp_path / "job_001"
        job_dir.mkdir()
        (job_dir / "video.mp4").write_bytes(b"mp4")
        video = str(job_dir / "video.mp4")

        insert = _FakeInsert({"id": "OnceOnlyID1"})
        client = MagicMock()
        client.videos.return_value.insert.return_value = insert
        publisher = _publisher_with_fake_client(client, monkeypatch)
        service = PublishService(publisher=publisher, output_dir=tmp_path)

        job = _job("job_001", video)
        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            _gate1, first = service.publish(job, _pass_qc())
            _gate2, second = service.publish(job, _pass_qc())

        assert insert.calls == 2  # one upload = two resumable chunks
        assert first is not None and second is not None
        assert first.video_id == second.video_id == "OnceOnlyID1"
        assert first.video_url == second.video_url
        assert client.videos.return_value.insert.call_count == 1

    def test_gate_rejection_never_uploads(self, tmp_path, monkeypatch):
        """A failing QC report blocks the upload before the service is used."""
        job_dir = tmp_path / "job_001"
        job_dir.mkdir()
        (job_dir / "video.mp4").write_bytes(b"mp4")
        video = str(job_dir / "video.mp4")

        called: list[int] = []
        client = MagicMock()
        client.videos.return_value.insert.side_effect = lambda **kw: called.append(1)
        publisher = _publisher_with_fake_client(client, monkeypatch)
        service = PublishService(publisher=publisher, output_dir=tmp_path)

        failing = QCReport(
            job_id="job_001",
            overall_status=QCStatus.FAIL,
            publish_ready=False,
            checks=[],
        )
        gate, published = service.publish(_job("job_001", video), failing)

        assert gate.allowed is False
        assert published is None
        assert called == []
        assert not (job_dir / "publish_result.json").exists()
        with patch.object(YouTubeUploadService, "_build_media", return_value="media"):
            result = publisher.publish(
                job_id="job_noleak", video_path=video, title="T", visibility="unlisted"
            )

        blob = json.dumps(
            {"error": result.error, "service_response": result.service_response},
            default=str,
        )
        assert "test-client-secret" not in blob
        assert "test-refresh-token" not in blob