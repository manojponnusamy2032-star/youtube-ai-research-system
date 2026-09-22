"""Day-7 tests: real publisher path, config safety, and ``--publish-existing``.

Everything here runs fully offline.  Network access is replaced by fake
``googleapiclient`` request objects injected through the existing
``YouTubeUploadService`` seams (``_build_client`` / ``_build_media``), so the
real publisher code path (OAuthCredentials -> UploadRequest -> UploadService ->
PublishedVideo) is exercised without credentials or network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import run_pipeline
from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishStatus, PublishVisibility
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    load_publish_result,
)
from src.services.youtube_upload_service import (
    OAuthCredentials,
    YouTubeUploadError,
    YouTubeUploadService,
)

OAUTH_VARS = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
SECRET_VALUE = "super-secret-client-secret-value"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


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


def _fake_client(insert: _FakeInsert, readback: dict[str, Any] | None = None) -> MagicMock:
    """Fake YouTube API client serving both insert and read-back calls."""
    client = MagicMock()
    client.videos.return_value.insert.return_value = insert
    client.videos.return_value.list.return_value.execute.return_value = readback or {}
    return client


def _set_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "day7-client-id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", SECRET_VALUE)
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "day7-refresh-token")


def _clear_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in OAUTH_VARS:
        monkeypatch.delenv(name, raising=False)


def _video(tmp_path: Path) -> str:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"day7 video bytes")
    return str(path)


def _make_job(job_id: str = "job_001", video_path: str | None = None) -> VideoJob:
    artifact = VideoArtifact(job_id=job_id, output_path=video_path) if video_path else None
    return VideoJob(
        job_id=job_id,
        topic="Day-7 verification topic",
        status=JobStatus.COMPLETED,
        artifact=artifact,
    )


def _pass_qc(job_id: str = "job_001") -> QCReport:
    return QCReport(
        job_id=job_id, overall_status=QCStatus.PASS, publish_ready=True, checks=[]
    )


def _fail_qc(job_id: str = "job_001") -> QCReport:
    return QCReport(
        job_id=job_id, overall_status=QCStatus.FAIL, publish_ready=False, checks=[]
    )


def _write_job_dir(
    root: Path,
    job_id: str = "job_001",
    *,
    with_video: bool = True,
    qc_status: QCStatus = QCStatus.PASS,
    publish_ready: bool = True,
) -> Path:
    """Materialize an on-disk job directory exactly like the orchestrator does."""
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    video_path = job_dir / "video.mp4"
    if with_video:
        video_path.write_bytes(b"day7 existing artifact bytes")

    job = _make_job(job_id, str(video_path) if with_video else None)
    (job_dir / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    qc = QCReport(
        job_id=job_id, overall_status=qc_status, publish_ready=publish_ready, checks=[]
    )
    (job_dir / "qc_report.json").write_text(qc.model_dump_json(indent=2), encoding="utf-8")
    return job_dir


# ---------------------------------------------------------------------------
# Step 2/3 - credential configuration safety
# ---------------------------------------------------------------------------


class TestCredentialConfigurationSafety:
    def test_missing_credentials_reported_together(self) -> None:
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env({})
        message = str(error.value)
        for name in OAUTH_VARS:
            assert name in message

    def test_whitespace_only_config_is_malformed(self) -> None:
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env(
                {
                    "YOUTUBE_CLIENT_ID": "   ",
                    "YOUTUBE_CLIENT_SECRET": "\t",
                    "YOUTUBE_REFRESH_TOKEN": "refresh",
                }
            )
        assert "YOUTUBE_CLIENT_ID" in str(error.value)
        assert "YOUTUBE_CLIENT_SECRET" in str(error.value)

    def test_values_are_stripped(self) -> None:
        creds = OAuthCredentials.from_env(
            {
                "YOUTUBE_CLIENT_ID": " id ",
                "YOUTUBE_CLIENT_SECRET": " secret\n",
                "YOUTUBE_REFRESH_TOKEN": " refresh ",
            }
        )
        assert creds.client_id == "id"
        assert creds.client_secret == "secret"
        assert creds.refresh_token == "refresh"

    def test_error_never_leaks_present_secret_values(self) -> None:
        """A missing-variable error must not echo values that ARE configured."""
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env(
                {"YOUTUBE_CLIENT_ID": "id", "YOUTUBE_CLIENT_SECRET": SECRET_VALUE}
            )
        message = str(error.value)
        assert "YOUTUBE_REFRESH_TOKEN" in message
        assert SECRET_VALUE not in message

    def test_publisher_real_mode_fails_safely_without_credentials(
        self, tmp_path, monkeypatch
    ) -> None:
        _clear_credentials(monkeypatch)
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(
            job_id="job_001",
            video_path=_video(tmp_path),
            title="Day-7 verification",
            visibility="unlisted",
        )
        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert result.video_url is None
        assert "credentials unavailable" in (result.error or "").lower()
# ---------------------------------------------------------------------------
# Step 4 - real publisher path (offline, full stack)
# ---------------------------------------------------------------------------


class TestRealPublisherPathOffline:
    def _publish(self, tmp_path, monkeypatch, *, insert, visibility="unlisted", title="T"):
        _set_credentials(monkeypatch)
        client = _fake_client(insert)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            publisher = YouTubePublisher(mock=False)
            result = publisher.publish(
                job_id="job_001",
                video_path=_video(tmp_path),
                title=title,
                visibility=visibility,
                description="Controlled Day-7 verification upload.",
            )
        return result, client

    def test_successful_upload_response_handling(self, tmp_path, monkeypatch) -> None:
        insert = _FakeInsert({"id": "day7Video01"})
        result, client = self._publish(
            tmp_path, monkeypatch, insert=insert, title="YAIRS Day-7 verification upload"
        )
        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "day7Video01"
        assert result.video_url == "https://www.youtube.com/watch?v=day7Video01"
        assert result.visibility == PublishVisibility.UNLISTED
        assert result.error is None
        assert insert.calls == 2

        body = client.videos.return_value.insert.call_args.kwargs["body"]
        assert body["snippet"]["title"] == "YAIRS Day-7 verification upload"
        assert body["snippet"]["description"] == "Controlled Day-7 verification upload."
        assert body["status"]["privacyStatus"] == "unlisted"

    def test_url_is_generated_from_returned_video_id(self, tmp_path, monkeypatch) -> None:
        insert = _FakeInsert({"id": "abcDEF12345"})
        result, _ = self._publish(tmp_path, monkeypatch, insert=insert)
        assert result.video_url == "https://www.youtube.com/watch?v=abcDEF12345"

    def test_missing_video_id_is_controlled_failure(self, tmp_path, monkeypatch) -> None:
        insert = _FakeInsert({})
        result, _ = self._publish(tmp_path, monkeypatch, insert=insert)
        assert result.status == PublishStatus.FAILED
        assert "no video id" in (result.error or "").lower()

    def test_oauth_initialization_failure_is_controlled(self, tmp_path, monkeypatch) -> None:
        _set_credentials(monkeypatch)

        def boom(self):
            raise RuntimeError("oauth transport unavailable")

        # _build_media is patched too: upload() builds media before the client,
        # and the real _build_media would fail on the missing googleapiclient
        # import before the patched OAuth client builder is ever reached.
        with patch.object(YouTubeUploadService, "_build_client", boom), patch.object(
            YouTubeUploadService, "_build_media", lambda self, path: "media"
        ):
            publisher = YouTubePublisher(mock=False)
            result = publisher.publish(
                job_id="job_001",
                video_path=_video(tmp_path),
                title="T",
                visibility="unlisted",
            )
        assert result.status == PublishStatus.FAILED
        assert "oauth transport unavailable" in (result.error or "")
        assert SECRET_VALUE not in (result.error or "")

    def test_api_failure_is_controlled_and_hides_secrets(
        self, tmp_path, monkeypatch
    ) -> None:
        _set_credentials(monkeypatch)

        def boom(self, path):
            raise YouTubeUploadError("quota exceeded while uploading")

        with patch.object(YouTubeUploadService, "_build_media", boom):
            publisher = YouTubePublisher(mock=False)
            result = publisher.publish(
                job_id="job_001",
                video_path=_video(tmp_path),
                title="T",
                visibility="unlisted",
            )
        assert result.status == PublishStatus.FAILED
        assert "quota exceeded" in (result.error or "")
        assert SECRET_VALUE not in json.dumps(result.service_response or {})

    def test_readback_confirms_unlisted(self, tmp_path, monkeypatch) -> None:
        client = _fake_client(
            _FakeInsert({"id": "day7Video02"}),
            readback={
                "items": [
                    {
                        "id": "day7Video02",
                        "snippet": {"title": "YAIRS Day-7 verification upload"},
                        "status": {
                            "privacyStatus": "unlisted",
                            "uploadStatus": "processed",
                        },
                    }
                ]
            },
        )
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            service = YouTubeUploadService(
                OAuthCredentials.from_env(
                    {
                        "YOUTUBE_CLIENT_ID": "id",
                        "YOUTUBE_CLIENT_SECRET": SECRET_VALUE,
                        "YOUTUBE_REFRESH_TOKEN": "refresh",
                    }
                )
            )
            status = service.get_video_status("day7Video02")

        assert status["video_id"] == "day7Video02"
        assert status["privacy_status"] == "unlisted"
# ---------------------------------------------------------------------------
# Step 3 - unlisted enforcement + gate rejection through the service
# ---------------------------------------------------------------------------


class TestUnlistedAndGateEnforcement:
    def test_public_request_is_downgraded_to_unlisted(self, tmp_path, monkeypatch) -> None:
        _set_credentials(monkeypatch)
        insert = _FakeInsert({"id": "day7Video03"})
        client = _fake_client(insert)
        video = _video(tmp_path)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            service = PublishService(mock=False, output_dir=str(tmp_path), visibility="public")
            gate, published = service.publish(_make_job(video_path=video), _pass_qc())
        assert gate.allowed is True
        assert published is not None
        assert published.visibility == PublishVisibility.UNLISTED
        body = client.videos.return_value.insert.call_args.kwargs["body"]
        assert body["status"]["privacyStatus"] == "unlisted"

    def test_fail_qc_blocks_real_upload(self, tmp_path, monkeypatch) -> None:
        _set_credentials(monkeypatch)
        insert = _FakeInsert({"id": "shouldNotHappen"})
        client = _fake_client(insert)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            service = PublishService(mock=False, output_dir=str(tmp_path))
            gate, published = service.publish(
                _make_job(video_path=_video(tmp_path)), _fail_qc()
            )
        assert gate.allowed is False
        assert published is None
        assert insert.calls == 0
        assert not (tmp_path / "job_001" / "publish_result.json").exists()

    def test_missing_video_artifact_blocks_real_upload(self, tmp_path, monkeypatch) -> None:
        _set_credentials(monkeypatch)
        insert = _FakeInsert({"id": "shouldNotHappen"})
        client = _fake_client(insert)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            service = PublishService(mock=False, output_dir=str(tmp_path))
            gate, published = service.publish(_make_job(video_path=None), _pass_qc())
        assert gate.allowed is False
        assert published is None
        assert insert.calls == 0

    def test_idempotency_prevents_second_real_upload(self, tmp_path, monkeypatch) -> None:
        _set_credentials(monkeypatch)
        insert = _FakeInsert({"id": "day7Video04"})
        client = _fake_client(insert)
        video = _video(tmp_path)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            service = PublishService(mock=False, output_dir=str(tmp_path))
            gate1, first = service.publish(_make_job(video_path=video), _pass_qc())
            gate2, second = service.publish(_make_job(video_path=video), _pass_qc())
        assert first is not None and first.status == PublishStatus.COMPLETED
        assert gate2.allowed is True
        assert second is not None and second.video_id == "day7Video04"
        assert insert.calls == 2  # a single upload (two resumable chunks)
# ---------------------------------------------------------------------------
# Step 3/6 - ``--publish-existing`` CLI entry point (no re-render, no network)
# ---------------------------------------------------------------------------


class TestPublishExistingCli:
    def test_mock_publish_existing_writes_result(self, tmp_path, monkeypatch, capsys) -> None:
        _clear_credentials(monkeypatch)
        _write_job_dir(tmp_path)
        rc = run_pipeline.main(
            [
                "--publish-existing", "job_001", "--mock-publish",
                "--output-dir", str(tmp_path),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 0
        assert "mock publish" in out.lower()

        result_path = tmp_path / "job_001" / "publish_result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data["status"] == "completed"
        assert data["video_id"]
        assert data["video_url"].startswith("https://www.youtube.com/watch?v=")

    def test_real_publish_existing_without_credentials_fails_safely(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        _clear_credentials(monkeypatch)
        _write_job_dir(tmp_path)
        rc = run_pipeline.main(
            [
                "--publish-existing", "job_001", "--publish",
                "--publish-visibility", "unlisted",
                "--publish-title", "YAIRS Day-7 verification upload",
                "--output-dir", str(tmp_path),
            ]
        )
        out = capsys.readouterr().out
        assert rc == 1
        assert "Status: failed" in out
        assert "credentials unavailable" in out.lower()
        assert not (tmp_path / "job_001" / "publish_result.json").exists()

    def test_publish_existing_requires_a_publish_flag(self, tmp_path) -> None:
        _write_job_dir(tmp_path)
        with pytest.raises(SystemExit) as error:
            run_pipeline.main(
                ["--publish-existing", "job_001", "--output-dir", str(tmp_path)]
            )
        assert error.value.code == 2

    def test_publish_existing_fail_qc_never_uploads(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        _set_credentials(monkeypatch)
        _write_job_dir(tmp_path, qc_status=QCStatus.FAIL, publish_ready=False)
        insert = _FakeInsert({"id": "shouldNotHappen"})
        client = _fake_client(insert)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            rc = run_pipeline.main(
                [
                    "--publish-existing", "job_001", "--publish",
                    "--output-dir", str(tmp_path),
                ]
            )
        out = capsys.readouterr().out
        assert rc == 1
        assert insert.calls == 0
        assert "blocked" in out.lower()
        assert not (tmp_path / "job_001" / "publish_result.json").exists()

    def test_publish_existing_without_video_never_uploads(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        _set_credentials(monkeypatch)
        _write_job_dir(tmp_path, with_video=False)
        insert = _FakeInsert({"id": "shouldNotHappen"})
        client = _fake_client(insert)
        with patch.object(
            YouTubeUploadService, "_build_client", lambda self: client
        ), patch.object(YouTubeUploadService, "_build_media", lambda self, path: "media"):
            rc = run_pipeline.main(
                [
                    "--publish-existing", "job_001", "--publish",
                    "--output-dir", str(tmp_path),
                ]
            )
        out = capsys.readouterr().out
        assert rc == 1
        assert insert.calls == 0
        assert "blocked" in out.lower()

    def test_publish_existing_missing_job_dir_reports_cleanly(
        self, tmp_path, capsys
    ) -> None:
        rc = run_pipeline.main(
            ["--publish-existing", "nope", "--mock-publish", "--output-dir", str(tmp_path)]
        )
        out = capsys.readouterr().out
        assert rc == 1
        assert "missing artifact" in out.lower()

    def test_second_mock_publish_existing_is_idempotent(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        _clear_credentials(monkeypatch)
        _write_job_dir(tmp_path)
        args = [
            "--publish-existing", "job_001", "--mock-publish",
            "--output-dir", str(tmp_path),
        ]
        assert run_pipeline.main(args) == 0
        first = (tmp_path / "job_001" / "publish_result.json").read_text(encoding="utf-8")
        capsys.readouterr()

        assert run_pipeline.main(args) == 0
        out = capsys.readouterr().out
        second = (tmp_path / "job_001" / "publish_result.json").read_text(encoding="utf-8")

        assert "idempotent" in out.lower()
        assert json.loads(first)["video_id"] == json.loads(second)["video_id"]

    def test_mock_publish_existing_result_round_trips(
        self, tmp_path, monkeypatch
    ) -> None:
        _clear_credentials(monkeypatch)
        job_dir = _write_job_dir(tmp_path)
        assert run_pipeline.main(
            [
                "--publish-existing", "job_001", "--mock-publish",
                "--output-dir", str(tmp_path),
            ]
        ) == 0
        loaded = load_publish_result(job_dir)
        assert loaded is not None
        assert loaded.status == PublishStatus.COMPLETED
        assert loaded.video_id
        assert loaded.visibility == PublishVisibility.UNLISTED
        assert SECRET_VALUE not in json.dumps(loaded.service_response or {})
        assert SECRET_VALUE not in json.dumps(json.loads(
            (job_dir / "publish_result.json").read_text(encoding="utf-8")
        ))


class TestSecretHygiene:
    def test_credentials_repr_never_leaks_secrets(self) -> None:
        creds = OAuthCredentials(
            client_id="cid", client_secret=SECRET_VALUE, refresh_token="rt"
        )
        text = repr(creds)
        assert SECRET_VALUE not in text
        assert "rt" != text  # sanity
        assert "refresh_token=***" in text
        assert "client_secret=***" in text
        # str() falls back to repr for dataclasses without __str__
        assert SECRET_VALUE not in str(creds)

    def test_malformed_blank_env_variables_fail_with_names_only(self, monkeypatch) -> None:
        """Whitespace-only credentials are rejected; the error lists names only."""
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "   ")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", SECRET_VALUE)
        monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "rt")
        with pytest.raises(YouTubeUploadError) as err:
            OAuthCredentials.from_env()
        assert "YOUTUBE_CLIENT_ID" in str(err.value)
        assert SECRET_VALUE not in str(err.value)