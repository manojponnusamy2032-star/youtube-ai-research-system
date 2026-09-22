"""Day-6 CLI tests part 1."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import (
    PublishGateResult,
    PublishedVideo,
    PublishStatus,
    PublishVisibility,
)


def _make_job(tmp_path, job_id: str = "job_001"):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"fake")
    artifact = VideoArtifact(job_id=job_id, output_path=str(video))
    return VideoJob(
        job_id=job_id, topic="T", status=JobStatus.COMPLETED, artifact=artifact
    )


def _pass_report() -> QCReport:
    return QCReport(
        job_id="job_001", overall_status=QCStatus.PASS,
        publish_ready=True, checks=[],
    )


def _fail_report() -> QCReport:
    return QCReport(
        job_id="job_001", overall_status=QCStatus.FAIL,
        publish_ready=False, checks=[],
    )


def _published() -> PublishedVideo:
    return PublishedVideo(
        job_id="job_001", video_id="mockvid12345",
        video_url="https://www.youtube.com/watch?v=mockvid12345",
        title="T", visibility=PublishVisibility.PRIVATE,
        status=PublishStatus.COMPLETED,
    )


class TestNormalRun:
    def test_normal_run_does_not_publish(self, tmp_path):
        import run_pipeline as rp
        job = _make_job(tmp_path)
        qc = _pass_report()
        with patch.object(rp, "_build_orchestrator") as mb:
            orch = MagicMock()
            orch.execute.return_value = job
            orch.run_qc.return_value = qc
            mb.return_value = orch
            with patch.object(rp, "PublishService") as cls:
                out = tmp_path / "out"
                out.mkdir(exist_ok=True)
                result = rp.run_pipeline(
                    "T", mode="mock", output_dir=out,
                    max_corrections=0, disable_corrections=True,
                    include_qc=True, publish=False, mock_publish=False,
                )
                assert result == (job, None, None, None)
                cls.assert_not_called()


class TestMockPublish:
    def test_mock_publish_invokes_mock(self, tmp_path):
        import run_pipeline as rp
        job = _make_job(tmp_path)
        qc = _pass_report()
        gate = PublishGateResult(
            job_id=job.job_id, allowed=True, publish_ready=True,
            qc_status="pass", reason="ok",
        )
        published = _published()
        with patch.object(rp, "_build_orchestrator") as mb:
            orch = MagicMock()
            orch.execute.return_value = job
            orch.run_qc.return_value = qc
            mb.return_value = orch
            svc = MagicMock()
            svc.get_existing_publish.return_value = None
            svc.publish.return_value = (gate, published)
            with patch.object(rp, "PublishService", return_value=svc) as cls:
                out = tmp_path / "o1"
                out.mkdir(exist_ok=True)
                _j, _c, got_gate, got_pub = rp.run_pipeline(
                    "T", mode="mock", output_dir=out,
                    max_corrections=0, disable_corrections=True,
                    include_qc=True, publish=False, mock_publish=True,
                )
                cls.assert_called_once()
                assert cls.call_args[1].get("mock") is True
                assert got_gate is gate
                assert got_pub is published


class TestRealPublish:
    def test_real_publish_path(self, tmp_path):
        import run_pipeline as rp
        job = _make_job(tmp_path)
        qc = _pass_report()
        gate = PublishGateResult(
            job_id=job.job_id, allowed=True, publish_ready=True,
            qc_status="pass", reason="ok",
        )
        with patch.object(rp, "_build_orchestrator") as mb:
            orch = MagicMock()
            orch.execute.return_value = job
            orch.run_qc.return_value = qc
            mb.return_value = orch
            svc = MagicMock()
            svc.get_existing_publish.return_value = None
            svc.publish.return_value = (gate, _published())
            with patch.object(rp, "PublishService", return_value=svc) as cls:
                out = tmp_path / "o2"
                out.mkdir(exist_ok=True)
                rp.run_pipeline(
                    "T", mode="mock", output_dir=out,
                    max_corrections=0, disable_corrections=True,
                    include_qc=True, publish=True, mock_publish=False,
                )
                cls.assert_called_once()
                assert cls.call_args[1].get("mock") is False


class TestQCFailSafety:
    def test_qc_fail_never_calls_publisher(self, tmp_path):
        import run_pipeline as rp
        from src.orchestration.repair.models import CorrectionReport
        job = _make_job(tmp_path)
        qc = _fail_report()
        with patch.object(rp, "_build_orchestrator") as mb:
            orch = MagicMock()
            orch.execute.return_value = job
            orch.run_qc.return_value = qc
            mb.return_value = orch
            loop = MagicMock()
            rep = CorrectionReport(
                job_id=job.job_id, initial_qc_status="fail",
                final_qc_status="fail", attempt_count=0,
                final_outcome="EXHAUSTED", terminal_reason="fail",
            )
            loop.run.return_value = (job, rep)
            with patch.object(rp, "CorrectionLoop", return_value=loop):
                with patch.object(rp, "PublishService") as cls:
                    out = tmp_path / "o3"
                    out.mkdir(exist_ok=True)
                    rp.run_pipeline(
                        "T", mode="mock", output_dir=out,
                        max_corrections=0, disable_corrections=False,
                        include_qc=True, publish=True, mock_publish=False,
                    )
                    cls.assert_not_called()
                    assert loop.run.call_count == 1

