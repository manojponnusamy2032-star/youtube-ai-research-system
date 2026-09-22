"""Day-7 tests: real publisher path safety (offline, no credentials)."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishStatus, PublishVisibility
from src.orchestration.youtube_publisher import (
    YouTubePublisher,
    resolve_real_upload_visibility,
)
from src.services.youtube_upload_service import (
    OAuthCredentials,
    YouTubeUploadError,
    YouTubeUploadService,
)


def _video(tmp_path: Path) -> str:
    p = tmp_path / "video.mp4"
    p.write_bytes(b"fake video bytes")
    return str(p)


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
        job_id=job_id, topic="Day-7 topic", status=JobStatus.COMPLETED,
        artifact=artifact,
    )


class TestRequiredCredentials:
    def test_only_three_oauth_vars_required(self):
        creds = OAuthCredentials.from_env(
            {
                "YOUTUBE_CLIENT_ID": "id",
                "YOUTUBE_CLIENT_SECRET": "secret",
                "YOUTUBE_REFRESH_TOKEN": "refresh",
                "YOUTUBE_API_KEY": "",
            }
        )
        assert creds.client_id == "id"

    def test_missing_credentials_listed(self):
        with pytest.raises(YouTubeUploadError) as exc:
            OAuthCredentials.from_env({})
        msg = str(exc.value)
        assert "YOUTUBE_CLIENT_ID" in msg
        assert "YOUTUBE_CLIENT_SECRET" in msg
        assert "YOUTUBE_REFRESH_TOKEN" in msg


class TestMissingCredentialsFailSafely:
    def test_real_publish_without_credentials_returns_failed(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        for var in (
            "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN",
        ):
            monkeypatch.delenv(var, raising=False)
        publisher = YouTubePublisher(mock=False)
        result = publisher.publish(job_id="job_001", video_path=video, title="T")
        assert result.status == PublishStatus.FAILED
        assert result.video_id is None
        assert "credentials" in (result.error or "").lower()
        assert publisher.upload_called is False

    def test_service_never_writes_result_on_credential_failure(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        for var in (
            "YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN",
        ):
            monkeypatch.delenv(var, raising=False)
        service = PublishService(
            publisher=YouTubePublisher(mock=False), output_dir=str(tmp_path)
        )
        gate, published = service.publish(_job(video_path=video), _pass_qc())
        assert gate.allowed is True
        assert published is not None
        assert published.status == PublishStatus.FAILED
        assert not (tmp_path / "job_001" / "publish_result.json").exists()


class TestServiceInitFailure:
    def test_upload_service_construction_failure_returns_failed(self, tmp_path):
        video = _video(tmp_path)
        creds = OAuthCredentials(
            client_id="id", client_secret="secret", refresh_token="refresh"
        )
        publisher = YouTubePublisher(mock=False, credentials=creds)
        with patch.object(
            YouTubeUploadService, "__init__",
            side_effect=RuntimeError("oauth lib missing"),
        ):
            result = publisher.publish(job_id="job_001", video_path=video, title="T")
        assert result.status == PublishStatus.FAILED
        assert "build" in (result.error or "").lower()


class _FakeUploadService:
    """Minimal offline fake of YouTubeUploadService."""

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.seen_requests = []

    def upload(self, request):
        self.seen_requests.append(request)
        if self.error is not None:
            raise self.error
        return self.response


def _real_publisher_with_fake(tmp_path, fake, monkeypatch):
    import src.orchestration.youtube_publisher as mod

    monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
    monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
    monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")
    monkeypatch.setattr(mod, "YouTubeUploadService", lambda credentials: fake)
    return YouTubePublisher(mock=False)


class TestRealUploadResponseHandling:
    def test_success_extracts_id_and_url_and_unlisted(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        fake = _FakeUploadService(
            response={
                "status": "completed",
                "video_id": "realVIDEO01",
                "video_url": "https://www.youtube.com/watch?v=realVIDEO01",
                "privacy_status": "unlisted",
            }
        )
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(
            job_id="job_001", video_path=video,
            title="YAIRS Day-7 verification upload",
            visibility="unlisted",
        )
        assert result.status == PublishStatus.COMPLETED
        assert result.video_id == "realVIDEO01"
        assert result.video_url == "https://www.youtube.com/watch?v=realVIDEO01"
        assert result.visibility == PublishVisibility.UNLISTED
        assert fake.seen_requests[0].privacy_status == "unlisted"
        assert len(fake.seen_requests) == 1

    def test_missing_video_id_is_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        fake = _FakeUploadService(response={"status": "completed"})
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(job_id="job_001", video_path=video, title="T")
        assert result.status == PublishStatus.FAILED
        assert "no video id" in (result.error or "").lower()

    def test_api_error_is_controlled_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        fake = _FakeUploadService(error=YouTubeUploadError("quota exceeded"))
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(job_id="job_001", video_path=video, title="T")
        assert result.status == PublishStatus.FAILED
        assert "quota" in (result.error or "").lower()


class TestUnlistedEnforcement:
    def test_default_resolver_is_unlisted(self):
        assert resolve_real_upload_visibility() == "unlisted"

    def test_public_without_optin_forced_unlisted(self):
        assert resolve_real_upload_visibility("public") == "unlisted"
        assert resolve_real_upload_visibility(PublishVisibility.PUBLIC) == "unlisted"

    def test_public_with_optin_allowed(self):
        assert resolve_real_upload_visibility("public", allow_public=True) == "public"

    def test_private_honoured(self):
        assert resolve_real_upload_visibility("private") == "private"

    def test_real_upload_forces_unlisted_when_public_requested(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        fake = _FakeUploadService(
            response={
                "status": "completed",
                "video_id": "vid12345678",
                "video_url": "https://www.youtube.com/watch?v=vid12345678",
                "privacy_status": "unlisted",
            }
        )
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(
            job_id="job_001", video_path=video, title="T", visibility="public",
        )
        assert fake.seen_requests[0].privacy_status == "unlisted"
        assert result.visibility == PublishVisibility.UNLISTED

    def test_explicit_public_optin_reaches_api(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        fake = _FakeUploadService(
            response={
                "status": "completed",
                "video_id": "vid12345678",
                "video_url": "https://www.youtube.com/watch?v=vid12345678",
                "privacy_status": "public",
            }
        )
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(
            job_id="job_001", video_path=video, title="T",
            visibility="public", allow_public=True,
        )
        assert fake.seen_requests[0].privacy_status == "public"
        assert result.visibility == PublishVisibility.PUBLIC

    def test_cli_offers_no_public_choice(self):
        import run_pipeline as rp

        src = Path(rp.__file__).read_text(encoding="utf-8")
        assert 'choices=["unlisted", "private"]' in src


class TestGateAndIdempotency:
    def test_qc_fail_never_calls_real_upload(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        fake = _FakeUploadService(
            response={
                "status": "completed",
                "video_id": "vid12345678",
                "video_url": "https://www.youtube.com/watch?v=vid12345678",
                "privacy_status": "unlisted",
            }
        )
        import src.orchestration.youtube_publisher as mod

        monkeypatch.setattr(mod, "YouTubeUploadService", lambda credentials: fake)
        publisher = YouTubePublisher(
            mock=False,
            credentials=OAuthCredentials(
                client_id="id", client_secret="s", refresh_token="r"
            ),
        )
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))
        gate, published = service.publish(_job(video_path=video), _fail_qc())
        assert gate.allowed is False
        assert published is None
        assert fake.seen_requests == []
        assert publisher.upload_called is False

    def test_success_persists_and_second_call_is_idempotent(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        fake = _FakeUploadService(
            response={
                "status": "completed",
                "video_id": "vid12345678",
                "video_url": "https://www.youtube.com/watch?v=vid12345678",
                "privacy_status": "unlisted",
            }
        )
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))
        gate1, first = service.publish(_job(video_path=video), _pass_qc())
        assert first is not None and first.status == PublishStatus.COMPLETED
        assert (tmp_path / "job_001" / "publish_result.json").exists()
        gate2, second = service.publish(_job(video_path=video), _pass_qc())
        assert second is not None
        assert second.video_id == first.video_id
        assert len(fake.seen_requests) == 1


class TestNoSecretLeakage:
    def test_errors_do_not_contain_secrets(
        self, tmp_path, monkeypatch, caplog
    ):
        video = _video(tmp_path)
        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "super-id")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "super-secret")
        monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "super-refresh")
        fake = _FakeUploadService(error=YouTubeUploadError("upload blew up"))
        import src.orchestration.youtube_publisher as mod

        monkeypatch.setattr(mod, "YouTubeUploadService", lambda credentials: fake)
        publisher = YouTubePublisher(mock=False)
        with caplog.at_level(logging.WARNING):
            result = publisher.publish(job_id="job_001", video_path=video, title="T")
        blob = json.dumps(
            {
                "error": result.error,
                "service_response": result.service_response,
                "logs": [r.getMessage() for r in caplog.records],
            },
            default=str,
        )
        assert "super-secret" not in blob
        assert "super-refresh" not in blob




class TestMalformedConfiguration:
    """Malformed / partial configuration must fail safely (no network)."""

    def test_blank_values_are_treated_as_missing(self):
        with pytest.raises(YouTubeUploadError) as error:
            OAuthCredentials.from_env(
                {
                    "YOUTUBE_CLIENT_ID": "   ",
                    "YOUTUBE_CLIENT_SECRET": "secret",
                    "YOUTUBE_REFRESH_TOKEN": "refresh",
                }
            )
        assert "YOUTUBE_CLIENT_ID" in str(error.value)

    def test_values_are_stripped(self):
        creds = OAuthCredentials.from_env(
            {
                "YOUTUBE_CLIENT_ID": " id ",
                "YOUTUBE_CLIENT_SECRET": " secret ",
                "YOUTUBE_REFRESH_TOKEN": " refresh ",
            }
        )
        assert creds.client_id == "id"
        assert creds.client_secret == "secret"
        assert creds.refresh_token == "refresh"

    def test_missing_video_file_is_controlled_failure(self, tmp_path, monkeypatch):
        fake = _FakeUploadService(
            response={
                "status": "completed",
                "video_id": "vid12345678",
                "video_url": "https://www.youtube.com/watch?v=vid12345678",
                "privacy_status": "unlisted",
            }
        )
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(
            job_id="job_001",
            video_path=str(tmp_path / "missing.mp4"),
            title="T",
        )
        assert result.status == PublishStatus.FAILED
        assert "does not exist" in (result.error or "")
        assert fake.seen_requests == []

    def test_oversized_title_is_controlled_failure(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        fake = _FakeUploadService(response={"video_id": "vid12345678"})
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(
            job_id="job_001", video_path=video, title="T" * 101
        )
        assert result.status == PublishStatus.FAILED
        assert "invalid publish request" in (result.error or "").lower()
        assert fake.seen_requests == []

    def test_unknown_visibility_is_rejected_before_api(self, tmp_path, monkeypatch):
        video = _video(tmp_path)
        fake = _FakeUploadService(response={"video_id": "vid12345678"})
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        result = publisher.publish(
            job_id="job_001", video_path=video, title="T", visibility="secret",
        )
        assert result.status == PublishStatus.FAILED
        assert "invalid publish request" in (result.error or "").lower()
        assert fake.seen_requests == []

def _write_existing_job(
    root: Path,
    job_id: str = "day7_job",
    *,
    qc_status: QCStatus = QCStatus.PASS,
    publish_ready: bool = True,
) -> Path:
    """Write a minimal rendered job dir (job.json / qc_report.json / video.mp4)."""
    job_dir = root / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    video = job_dir / "video.mp4"
    video.write_bytes(b"fake mp4 bytes")
    job = _job(job_id=job_id, video_path=str(video))
    job.qc_report_path = str(job_dir / "qc_report.json")
    (job_dir / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    qc = QCReport(
        job_id=job_id,
        overall_status=qc_status,
        publish_ready=publish_ready,
        checks=[],
    )
    (job_dir / "qc_report.json").write_text(
        qc.model_dump_json(indent=2), encoding="utf-8"
    )
    return job_dir


class TestPublishExistingCli:
    """Day-7 CLI entry point: publish an existing artifact, no re-render."""

    def _no_credentials(self, monkeypatch):
        for name in (
            "YOUTUBE_CLIENT_ID",
            "YOUTUBE_CLIENT_SECRET",
            "YOUTUBE_REFRESH_TOKEN",
        ):
            monkeypatch.delenv(name, raising=False)

    def test_mock_publish_existing_writes_result_and_no_network(
        self, tmp_path, monkeypatch, capsys
    ):
        import run_pipeline as rp

        self._no_credentials(monkeypatch)
        job_dir = _write_existing_job(tmp_path)

        rc = rp.main(
            [
                "--publish-existing", "day7_job",
                "--mock-publish",
                "--output-dir", str(tmp_path),
            ]
        )

        out = capsys.readouterr().out
        assert rc == 0, out
        assert "[OK] Publish mock" in out
        result_file = job_dir / "publish_result.json"
        assert result_file.exists()
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        assert payload["status"] == "completed"
        assert payload["video_id"]
        assert payload["video_url"].startswith("https://www.youtube.com/watch?v=")
        assert payload["visibility"] == "unlisted"

    def test_second_run_is_idempotent(self, tmp_path, monkeypatch, capsys):
        import run_pipeline as rp
        import src.orchestration.youtube_publisher as yp

        self._no_credentials(monkeypatch)
        job_dir = _write_existing_job(tmp_path)

        calls = {"n": 0}
        real_publish = yp.YouTubePublisher.publish

        def _counting_publish(self, *args, **kwargs):
            calls["n"] += 1
            return real_publish(self, *args, **kwargs)

        monkeypatch.setattr(yp.YouTubePublisher, "publish", _counting_publish)

        assert rp.main(
            ["--publish-existing", "day7_job", "--mock-publish",
             "--output-dir", str(tmp_path)]
        ) == 0
        first = json.loads(
            (job_dir / "publish_result.json").read_text(encoding="utf-8")
        )
        capsys.readouterr()

        assert rp.main(
            ["--publish-existing", "day7_job", "--mock-publish",
             "--output-dir", str(tmp_path)]
        ) == 0
        second = json.loads(
            (job_dir / "publish_result.json").read_text(encoding="utf-8")
        )
        out = capsys.readouterr().out

        assert calls["n"] == 1
        assert "idempotent" in out
        assert second["video_id"] == first["video_id"]

    def test_requires_publish_flag(self, tmp_path):
        import run_pipeline as rp

        _write_existing_job(tmp_path)
        with pytest.raises(SystemExit) as error:
            rp.main(["--publish-existing", "day7_job", "--output-dir", str(tmp_path)])
        assert error.value.code == 2

    def test_missing_job_directory_returns_failure(self, tmp_path, capsys):
        import run_pipeline as rp

        rc = rp.main(
            ["--publish-existing", "nope", "--mock-publish",
             "--output-dir", str(tmp_path)]
        )
        out = capsys.readouterr().out
        assert rc == 1
        assert "missing artifact" in out

    def test_real_publish_without_credentials_fails_safely(
        self, tmp_path, monkeypatch, capsys
    ):
        import run_pipeline as rp

        self._no_credentials(monkeypatch)
        job_dir = _write_existing_job(tmp_path)

        rc = rp.main(
            ["--publish-existing", "day7_job", "--publish",
             "--output-dir", str(tmp_path)]
        )
        out = capsys.readouterr().out

        assert rc == 1
        assert "Status: failed" in out
        assert "OAuth credentials unavailable" in out
        assert not (job_dir / "publish_result.json").exists()

    def test_qc_fail_blocks_real_upload_entirely(
        self, tmp_path, monkeypatch, capsys
    ):
        """QC FAIL + --publish => the upload service is never invoked."""
        import run_pipeline as rp
        import src.orchestration.youtube_publisher as yp

        monkeypatch.setenv("YOUTUBE_CLIENT_ID", "id")
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET", "secret")
        monkeypatch.setenv("YOUTUBE_REFRESH_TOKEN", "refresh")

        called = {"uploads": 0}

        class _ExplodingUploadService:
            def __init__(self, *args, **kwargs):
                pass

            def upload(self, request):  # pragma: no cover - must never run
                called["uploads"] += 1
                raise AssertionError("upload must not be called after QC FAIL")

        monkeypatch.setattr(yp, "YouTubeUploadService", _ExplodingUploadService)

        job_dir = _write_existing_job(
            tmp_path, qc_status=QCStatus.FAIL, publish_ready=False
        )

        rc = rp.main(
            ["--publish-existing", "day7_job", "--publish",
             "--output-dir", str(tmp_path)]
        )
        out = capsys.readouterr().out

        assert rc == 1
        assert called["uploads"] == 0
        assert "Publish blocked" in out
        assert not (job_dir / "publish_result.json").exists()

    def test_publish_title_and_description_overrides_reach_metadata(
        self, tmp_path, monkeypatch, capsys
    ):
        import run_pipeline as rp

        self._no_credentials(monkeypatch)
        job_dir = _write_existing_job(tmp_path)

        rc = rp.main(
            [
                "--publish-existing", "day7_job",
                "--mock-publish",
                "--publish-title", "YAIRS Day-7 verification upload",
                "--publish-description", "Controlled verification upload.",
                "--output-dir", str(tmp_path),
            ]
        )
        assert rc == 0, capsys.readouterr().out

        payload = json.loads((job_dir / "publish_result.json").read_text(encoding="utf-8"))
        assert payload["title"] == "YAIRS Day-7 verification upload"
        assert payload["description"] == "Controlled verification upload."


class TestRealUploadFailureIsolation:
    """A failing real upload must never be persisted as a success."""

    def test_failed_real_upload_is_not_persisted(
        self, tmp_path, monkeypatch
    ):
        video = _video(tmp_path)
        fake = _FakeUploadService(error=YouTubeUploadError("quota exceeded"))
        publisher = _real_publisher_with_fake(tmp_path, fake, monkeypatch)
        service = PublishService(publisher=publisher, output_dir=str(tmp_path))

        gate, published = service.publish(_job(video_path=video), _pass_qc())

        assert gate.allowed is True
        assert published is not None
        assert published.status == PublishStatus.FAILED
        assert not (tmp_path / "job_001" / "publish_result.json").exists()
        assert len(fake.seen_requests) == 1