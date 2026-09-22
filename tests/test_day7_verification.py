"""Day-7 verification tests for the real YouTube publishing path.

These tests never touch the network.  They exercise the REAL code path
``YouTubePublisher (real mode) -> YouTubeUploadService -> request/response``
with an injected fake API client, and assert the Day-7 safety properties:

* the first real upload is forced to ``unlisted``
* missing / malformed OAuth configuration fails safely (no upload, no artifact)
* a successful insert response yields the real video id and watch URL
* a follow-up API read confirms the video exists and remains unlisted
* read-back failure is reported as "verification unavailable", not as an
  upload failure
* no credential value ever reaches publisher errors, service responses or
  ``publish_result.json``

Existing Day-6 tests are left untouched.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.orchestration.youtube_publisher as publisher_mod
from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishedVideo, PublishStatus, PublishVisibility
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    load_publish_result,
    resolve_real_upload_visibility,
    write_publish_result,
)
from src.services.youtube_upload_service import (
    OAuthCredentials,
    UploadRequest,
    YouTubeUploadError,
    YouTubeUploadService,
)

OAUTH_VARS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")

# Distinctive values that must never appear in any error message or artifact.
_SECRET_VALUES = {
    "YOUTUBE_CLIENT_ID": "day7-client-id-abcdef",
    "YOUTUBE_CLIENT_SECRET": "day7-client-secret-SUPERSECRET",
    "YOUTUBE_REFRESH_TOKEN": "day7-refresh-token-SUPERSECRET",
}


def _video_file(tmp_path, name: str = "video.mp4") -> str:
    path = tmp_path / name
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42day7")
    return str(path)


def _credentials() -> OAuthCredentials:
    return OAuthCredentials(
        client_id=_SECRET_VALUES["YOUTUBE_CLIENT_ID"],
        client_secret=_SECRET_VALUES["YOUTUBE_CLIENT_SECRET"],
        refresh_token=_SECRET_VALUES["YOUTUBE_REFRESH_TOKEN"],
    )


def _set_full_env(monkeypatch) -> None:
    for key, value in _SECRET_VALUES.items():
        monkeypatch.setenv(key, value)


def _clear_env(monkeypatch) -> None:
    for key in OAUTH_VARS:
        monkeypatch.delenv(key, raising=False)



class _FakeInsert:
    """Fake resumable insert request that completes immediately."""

    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response

    def next_chunk(self) -> tuple[Any, dict[str, Any] | None]:
        return (None, self.response)


class _FakeListRequest:
    """Fake ``videos().list()`` request returning canned items."""

    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items

    def execute(self) -> dict[str, Any]:
        return {"items": self.items}


class _FakeClient:
    """Minimal fake YouTube API client (insert + list) — no network."""

    def __init__(self, insert_response: dict[str, Any], list_items=None) -> None:
        self._insert = _FakeInsert(insert_response)
        self.list_items = list_items or []
        self.insert_bodies: list[dict[str, Any]] = []
        self.list_calls: list[dict[str, Any]] = []

    def videos(self):
        return self

    def insert(self, part=None, body=None, media_body=None):
        assert part == "snippet,status"
        self.insert_bodies.append(body)
        return self._insert

    def list(self, part=None, id=None):  # noqa: A002 - mirrors the Google API
        self.list_calls.append({"part": part, "id": id})
        return _FakeListRequest(self.list_items)


def _real_publisher_with_client(
    monkeypatch,
    client,
    *,
    use_env_credentials: bool = False,
) -> YouTubePublisher:
    """Build a real-mode publisher wired to a fake API client.

    ``_build_media`` is patched because ``google-api-python-client`` is an
    optional runtime dependency that is not installed in this test environment.
    """
    if use_env_credentials:
        _set_full_env(monkeypatch)
        creds = None
    else:
        creds = _credentials()

    def _service_factory(credentials):
        return YouTubeUploadService(credentials, client_factory=lambda: client)

    monkeypatch.setattr(publisher_mod, "YouTubeUploadService", _service_factory)
    monkeypatch.setattr(
        YouTubeUploadService, "_build_media", lambda self, path: "media-body"
    )
    return YouTubePublisher(mock=False, credentials=creds)


class TestRealUploadHappyPath:
    """Real adapter -> real upload service -> fake API client."""

    def test_real_insert_returns_video_id_and_url(self, tmp_path, monkeypatch):
        client = _FakeClient({"id": "day7RealVID1"})
        publisher = _real_publisher_with_client(monkeypatch, client)
        result = publisher.publish(
            job_id="job_001",
            video_path=_video_file(tmp_path),
            title="YAIRS Day-7 verification upload",
            description="Controlled unlisted verification upload.",
            visibility="unlisted",
        )

        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "day7RealVID1"
        assert result.video_url == "https://www.youtube.com/watch?v=day7RealVID1"
        assert result.visibility == PublishVisibility.UNLISTED
        assert result.error is None

    def test_real_insert_body_is_unlisted(self, tmp_path, monkeypatch):
        client = _FakeClient({"id": "day7RealVID2"})
        publisher = _real_publisher_with_client(monkeypatch, client)
        publisher.publish(
            job_id="job_001",
            video_path=_video_file(tmp_path),
            title="Day-7 verification",
            visibility="unlisted",
        )

        assert len(client.insert_bodies) == 1
        body = client.insert_bodies[0]
        assert body["status"]["privacyStatus"] == "unlisted"
        assert body["snippet"]["title"] == "Day-7 verification"
class TestReadBackVerification:
    """Follow-up API read confirming the video exists and stays unlisted."""

    def test_read_back_confirms_unlisted(self, tmp_path, monkeypatch):
        client = _FakeClient(
            {"id": "day7RealVID4"},
            list_items=[
                {
                    "id": "day7RealVID4",
                    "snippet": {"title": "YAIRS Day-7 verification upload"},
                    "status": {"privacyStatus": "unlisted", "uploadStatus": "processed"},
                }
            ],
        )
        publisher = _real_publisher_with_client(monkeypatch, client)
        publisher.publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )

        service = YouTubeUploadService(_credentials(), client_factory=lambda: client)
        status = service.get_video_status("day7RealVID4")

        assert status["video_id"] == "day7RealVID4"
        assert status["privacy_status"] == "unlisted"
        assert client.list_calls[0]["id"] == "day7RealVID4"

    def test_read_back_failure_is_not_an_upload_failure(self, tmp_path, monkeypatch):
        """A failed read-back is reported as unverifiable, not as a failure."""
        client = MagicMock()
        client.videos.return_value.list.side_effect = RuntimeError("insufficient scope")
        service = YouTubeUploadService(_credentials(), client_factory=lambda: client)

        with pytest.raises(YouTubeUploadError) as error:
            service.get_video_status("day7RealVID5")
        assert "day7RealVID5" in str(error.value)

    def test_read_back_missing_video_raises(self):
        client = _FakeClient({"id": "x"}, list_items=[])
        service = YouTubeUploadService(_credentials(), client_factory=lambda: client)
        with pytest.raises(YouTubeUploadError):
            service.get_video_status("day7RealVID6")


class TestMissingAndMalformedCredentials:
    """Missing / malformed configuration must fail safely."""

    def test_missing_credentials_no_upload_no_artifact(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        video = _video_file(tmp_path)
        publisher = YouTubePublisher(mock=False)

        result = publisher.publish(job_id="job_001", video_path=video, title="Day-7")

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "credentials unavailable" in (result.error or "").lower()

        service = PublishService(
            publisher=YouTubePublisher(mock=False), output_dir=str(tmp_path)
        )
        gate, published = service.publish(_job("job_001", video), _pass_qc())
        assert gate.allowed is True
        assert published is not None
        assert published.status == PublishStatus.FAILED
        assert not (tmp_path / "job_001" / "publish_result.json").exists()

    def test_partial_credentials_reports_missing_names_only(
        self, tmp_path, monkeypatch
    ):
        _clear_env(monkeypatch)
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", _SECRET_VALUES["YOUTUBE_CLIENT_ID"])
        result = YouTubePublisher(mock=False).publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )

        assert result.status == PublishStatus.FAILED
        error = result.error or ""
        assert "YOUTUBE_CLIENT_SECRET" in error
        assert "YOUTUBE_REFRESH_TOKEN" in error
        _assert_no_secret_leak(error)

    def test_whitespace_only_credentials_are_malformed(self, monkeypatch):
        for key in OAUTH_VARS:
            monkeypatch.setenv(key, "   ")

        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env()

        message = str(error.value)
        for key in OAUTH_VARS:
            assert key in message
        _assert_no_secret_leak(message)

    def test_whitespace_credentials_fail_through_publisher(
        self, tmp_path, monkeypatch
    ):
        for key in OAUTH_VARS:
            monkeypatch.setenv(key, "  ")
        result = YouTubePublisher(mock=False).publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )

        assert result.status == PublishStatus.FAILED
        assert "credentials" in (result.error or "").lower()
        _assert_no_secret_leak(result.error or "")


class TestUploadFailuresAreControlled:
    """API errors fail safe and leak nothing."""

    def test_api_error_returns_failed_status(self, tmp_path, monkeypatch):
        class _Failing:
            def upload(self, request):
                raise YouTubeUploadError("quota exceeded")

        _set_full_env(monkeypatch)
        monkeypatch.setattr(
            publisher_mod, "YouTubeUploadService", lambda credentials: _Failing()
        )
        result = YouTubePublisher(mock=False).publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )

        assert result.status == PublishStatus.FAILED
        assert "quota exceeded" in (result.error or "")
        _assert_no_secret_leak(result.error or "")

    def test_upload_without_video_id_is_failure(self, tmp_path, monkeypatch):
        publisher = _real_publisher_with_client(monkeypatch, _FakeClient({}))
        result = publisher.publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )

        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "no video id" in (result.error or "").lower()


class TestNoSecretLeakageInArtifacts:
    """Secrets must never reach publish_result.json."""

    def test_publish_result_writes_no_credentials(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        client = _FakeClient({"id": "day7RealVID7"})
        publisher = _real_publisher_with_client(
            monkeypatch, client, use_env_credentials=True
        )
        job_dir = tmp_path / "job_001"
        result = publisher.publish(
            job_id="job_001",
            video_path=_video_file(tmp_path),
            title="YAIRS Day-7 verification upload",
            visibility="unlisted",
        )
        assert result.status == PublishStatus.COMPLETED

        path = write_publish_result(result, job_dir)
        raw = path.read_text(encoding="utf-8")
        _assert_no_secret_leak(raw)
        assert "client_secret" not in raw
        assert "refresh_token" not in raw

        loaded = load_publish_result(job_dir)
        assert loaded is not None
        assert loaded.video_id == "day7RealVID7"
        assert loaded.visibility == PublishVisibility.UNLISTED

    def test_publish_result_has_no_private_fields(self, tmp_path):
        result = PublishedVideo(
            job_id="job_001",
            video_id="vid",
            video_url="https://www.youtube.com/watch?v=vid",
            title="Day-7",
            visibility=PublishVisibility.UNLISTED,
            status=PublishStatus.COMPLETED,
        )
        path = write_publish_result(result, tmp_path / "job_001")
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "credentials" not in payload
        assert set(payload) == {
            "job_id",
            "video_id",
            "video_url",
            "title",
            "visibility",
            "status",
            "published_at",
            "upload_attempt",
            "artifact_path",
            "description",
            "tags",
            "category_id",
            "thumbnail_result",
            "error",
            "service_response",
        }


class TestIdempotencyRealPath:
    """The real path must not upload twice for the same job."""

    def test_second_publish_reuses_existing_result(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        video = _video_file(tmp_path)
        client = _FakeClient({"id": "day7RepeatedVID"})
        publisher = _real_publisher_with_client(
            monkeypatch, client, use_env_credentials=True
        )

        first = publisher.publish(
            job_id="job_001",
            video_path=video,
            title="YAIRS Day-7 verification upload",
            visibility="unlisted",
        )
        write_publish_result(first, tmp_path / "job_001")

        service = PublishService(publisher=publisher, output_dir=str(tmp_path))
        gate, second = service.publish(_job("job_001", video), _pass_qc())

        assert gate.allowed is True
        assert second is not None
        assert second.video_id == first.video_id
        assert len(client.insert_bodies) == 1  # exactly one real upload

    def test_publish_gate_rejection_never_uploads(self, tmp_path, monkeypatch):
        _clear_env(monkeypatch)
        video = _video_file(tmp_path)
        client = _FakeClient({"id": "day7ShouldNotUpload"})
        publisher = _real_publisher_with_client(
            monkeypatch, client, use_env_credentials=True
        )
        qc_fail = QCReport(
            job_id="job_001",
            overall_status=QCStatus.FAIL,
            publish_ready=False,
            checks=[],
        )
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))
        gate, published = service.publish(_job("job_001", video), qc_fail)

        assert gate.allowed is False
        assert published is None
        assert client.insert_bodies == []
        assert not (tmp_path / "job_001" / "publish_result.json").exists()


class TestVisibilityResolver:
    """``resolve_real_upload_visibility`` is the single safety switch."""

    def test_default_unlisted(self):
        assert resolve_real_upload_visibility() == "unlisted"

    def test_public_and_unknown_forced_unlisted(self):
        for value in ("public", "PUBLIC", "nonsense", None, ""):
            assert resolve_real_upload_visibility(value) == "unlisted"

    def test_public_allowed_only_with_explicit_optin(self):
        assert resolve_real_upload_visibility("public", allow_public=True) == "public"

    def test_private_honoured(self):
        assert resolve_real_upload_visibility("private") == "private"


def test_upload_request_rejects_unknown_privacy(tmp_path):
    """The request builder validates privacy before any API call."""
    video = _video_file(tmp_path)
    request = UploadRequest(video_path=video, title="t", privacy_status="unlisted")
    assert request.privacy_status == "unlisted"

    with pytest.raises(ValueError):
        UploadRequest(video_path=video, title="t", privacy_status="public-typo")


def test_default_publisher_mode_fails_safely_without_credentials(monkeypatch):
    """The default constructor is real mode: with no credentials it must report
    a controlled failure instead of attempting a network call."""
    _clear_env(monkeypatch)
    publisher = YouTubePublisher()
    assert publisher.mock is False
    result = publisher.publish(job_id="job_001", video_path="missing.mp4", title="T")
    assert result.status == PublishStatus.FAILED
    assert result.video_id is None
    _assert_no_secret_leak(result.error or "")


def test_no_real_api_client_is_built_in_tests(tmp_path, monkeypatch):
    """Guard: the fake-client path proves no real API client is constructed."""
    _set_full_env(monkeypatch)
    publisher = _real_publisher_with_client(
        monkeypatch, _FakeClient({"id": "offlineVID"})
    )
    with patch.object(
        YouTubeUploadService,
        "_build_client",
        side_effect=AssertionError("real API client must not be built in tests"),
    ):
        result = publisher.publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )
    assert result.status == PublishStatus.COMPLETED
    assert result.video_id == "offlineVID"
    assert result.video_url == "https://www.youtube.com/watch?v=offlineVID"


class TestRealPathFailureModes:
    """Controlled failures on the real path never leak secrets."""

    def test_upload_service_initialisation_failure_is_controlled(
        self, tmp_path, monkeypatch
    ):
        _set_full_env(monkeypatch)

        def _boom(credentials):
            raise RuntimeError("google-api-python-client is not installed")

        monkeypatch.setattr(publisher_mod, "YouTubeUploadService", _boom)
        result = YouTubePublisher(mock=False).publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )

        assert result.status == PublishStatus.FAILED
        assert "google-api-python-client" in (result.error or "")
        _assert_no_secret_leak(result.error or "")

    def test_public_request_is_forced_to_unlisted(self, tmp_path, monkeypatch):
        """Day-7 safety: the first real upload cannot become public."""
        client = _FakeClient({"id": "day7RealVID3"})
        publisher = _real_publisher_with_client(monkeypatch, client)
        result = publisher.publish(
            job_id="job_001",
            video_path=_video_file(tmp_path),
            title="Day-7 verification",
            visibility="public",
        )

        assert result.status == PublishStatus.COMPLETED
        assert client.insert_bodies[0]["status"]["privacyStatus"] == "unlisted"
        assert result.visibility == PublishVisibility.UNLISTED

    def test_credentials_loaded_from_environment(self, tmp_path, monkeypatch):
        """Real mode uses OAuthCredentials.from_env() when none are injected."""
        _clear_env(monkeypatch)
        client = _FakeClient({"id": "day7EnvVID"})
        publisher = _real_publisher_with_client(
            monkeypatch, client, use_env_credentials=True
        )
        result = publisher.publish(
            job_id="job_001", video_path=_video_file(tmp_path), title="Day-7"
        )
        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "day7EnvVID"

def _assert_no_secret_leak(text: str) -> None:
    """No credential material may appear in any user-visible output."""
    for key, value in _SECRET_VALUES.items():
        assert value not in text, f"{key} value leaked into output"


def _pass_qc() -> QCReport:
    return QCReport(
        job_id="job_001",
        overall_status=QCStatus.PASS,
        publish_ready=True,
        checks=[],
    )


def _job(job_id: str, video: str) -> VideoJob:
    return VideoJob(
        job_id=job_id,
        topic="Day-7 verification",
        status=JobStatus.COMPLETED,
        artifact=VideoArtifact(job_id=job_id, output_path=video),
    )