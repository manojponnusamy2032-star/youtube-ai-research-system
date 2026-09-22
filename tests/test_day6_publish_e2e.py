"""Day-6 e2e (mock)."""
import json
from pathlib import Path

from src.orchestration.publish_service import PublishService
from src.orchestration.qc.models import QCReport, QCStatus
from src.orchestration.schemas.job import JobStatus, VideoJob
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.publish import PublishStatus
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage
from src.orchestration.youtube_publisher import YouTubePublisher, load_publish_result


def _make_strategy() -> StrategyPackage:
    return StrategyPackage(
        topic="E2E Topic",
        angle="Test angle",
        narrative_outline=["beat1", "beat2"],
        key_messages=["msg1"],
        emotional_triggers=["curiosity"],
        hook_idea="hook",
        call_to_action="subscribe",
        target_audience="general",
    )


def _make_script() -> ScriptPackage:
    from src.orchestration.schemas.script import ScriptSection

    return ScriptPackage(
        topic="E2E Topic",
        title="E2E Test Video Title",
        hook="hook text",
        sections=[
            ScriptSection(heading="Intro", narration="Welcome to the test.", duration_seconds=4),
            ScriptSection(heading="Main", narration="This is the body.", duration_seconds=4),
        ],
        call_to_action="Subscribe!",
        total_duration_seconds=8,
    )


def _build_job(job_id: str, job_dir: Path) -> VideoJob:
    video = job_dir / "video.mp4"
    video.write_bytes(b"fake e2e video bytes")
    artifact = VideoArtifact(job_id=job_id, output_path=str(video))
    return VideoJob(
        job_id=job_id,
        topic="E2E Topic",
        status=JobStatus.COMPLETED,
        artifact=artifact,
        strategy=_make_strategy(),
        script=_make_script(),
    )


def _pass_qc(job_id: str) -> QCReport:
    return QCReport(
        job_id=job_id, overall_status=QCStatus.PASS, publish_ready=True, checks=[]
    )


def _fail_qc(job_id: str) -> QCReport:
    return QCReport(
        job_id=job_id, overall_status=QCStatus.FAIL, publish_ready=False, checks=[]
    )


class TestMockE2E:
    def test_full_mock_e2e_filesystem_and_idempotency(self, tmp_path):
        job_id = "e2e_job_001"
        output_dir = tmp_path / "output"
        job_dir = output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        job = _build_job(job_id, job_dir)
        qc = _pass_qc(job_id)

        # Persist qc_report.json like the real orchestration does.
        qc_path = job_dir / "qc_report.json"
        qc_path.write_text(qc.model_dump_json(indent=2), encoding="utf-8")
        job.qc_report_path = str(qc_path)

        publisher = YouTubePublisher(mock=True)
        service = PublishService(publisher=publisher, output_dir=output_dir)

        gate_result, published = service.publish(job, qc)

        assert gate_result.allowed is True
        assert published is not None
        assert published.status == PublishStatus.COMPLETED

        # Verify actual filesystem.
        video_path = job_dir / "video.mp4"
        assert video_path.exists()
        assert qc_path.exists()
        result_path = job_dir / "publish_result.json"
        assert result_path.exists()

        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data.get("video_id")
        assert published.video_id == data["video_id"]
        assert published.video_url is not None
        assert "youtube.com/watch?v=" in published.video_url
        assert data.get("video_url") == published.video_url

        # load_publish_result round-trip.
        loaded = load_publish_result(job_dir)
        assert loaded is not None
        assert loaded.video_id == published.video_id

        first_attempts = len(publisher._upload_attempts)
        assert first_attempts == 1

        # Publish same job again -> idempotent, mock upload occurs only once.
        gate2, published2 = service.publish(job, qc)
        assert published2 is not None
        assert published2.video_id == published.video_id
        assert len(publisher._upload_attempts) == 1
        assert publisher.upload_called is True


class TestQCFailSafety:
    def test_qc_fail_blocks_publish_at_service_level(self, tmp_path):
        job_id = "e2e_job_fail"
        output_dir = tmp_path / "output"
        job_dir = output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        job = _build_job(job_id, job_dir)
        qc = _fail_qc(job_id)

        publisher = YouTubePublisher(mock=True)
        service = PublishService(publisher=publisher, output_dir=output_dir)

        gate_result, published = service.publish(job, qc)

        assert gate_result.allowed is False
        assert published is None
        assert publisher.upload_called is False
        assert len(publisher._upload_attempts) == 0
        assert not (job_dir / "publish_result.json").exists()

