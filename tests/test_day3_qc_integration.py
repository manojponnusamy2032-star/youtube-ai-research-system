"""Day-3 QC Integration tests.

Tests the full pipeline: generate -> render -> QC -> QCReport.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from src.adapters.renderer.base import RendererAdapter
from src.orchestration.qc import run_qc, QCRequest, QCStatus
from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import PipelineSpec
from src.orchestration.schemas.job import JobStatus
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.visual import VisualPlan, VisualScenePlan


def _tiny_script(topic: str) -> ScriptPackage:
    sections = [
        ScriptSection(
            heading="Section one",
            narration="Day three pipeline check part one.",
            duration_seconds=1,
        ),
        ScriptSection(
            heading="Section two",
            narration="Day three pipeline check part two.",
            duration_seconds=1,
        ),
    ]
    return ScriptPackage(
        topic=topic,
        title=topic,
        hook="Hook.",
        sections=sections,
        call_to_action="CTA.",
        total_duration_seconds=2,
    )


def _tiny_plan(topic: str) -> VisualPlan:
    scenes = [
        VisualScenePlan(
            scene_number=1,
            duration_seconds=1,
            narration="Day three pipeline check part one.",
            visual_prompt="A stickman scene.",
            camera_instructions="static",
            character_action="talk",
            motions=[{"type": "enter"}],
            visual_description={"environment": {"type": "desk"}},
        ),
        VisualScenePlan(
            scene_number=2,
            duration_seconds=1,
            narration="Day three pipeline check part two.",
            visual_prompt="Another stickman scene.",
            camera_instructions="zoom",
            character_action="point",
            motions=[{"type": "exit"}],
            visual_description={"environment": {"type": "desk"}},
        ),
    ]
    return VisualPlan(
        topic=topic,
        title=topic,
        scenes=scenes,
        render_job_plan={
            "total_jobs": 2,
            "jobs": [{"job_id": "scene-01"}, {"job_id": "scene-02"}],
            "total_duration_seconds": 2,
        },
        total_duration_seconds=2,
    )


class _StubRenderer(RendererAdapter):
    """Deterministic stub renderer that writes a fake MP4 file."""

    def run(self, request: ProductionRequest) -> VideoArtifact:
        output_path = Path(request.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mp4-content")
        return VideoArtifact(
            job_id=request.job_id,
            status="completed",
            output_path=str(output_path),
            mp4_exists=True,
            file_size_bytes=output_path.stat().st_size,
            scene_count=len(request.visual_plan.scenes),
            total_duration_seconds=request.visual_plan.total_duration_seconds,
        )


class TestQCIntegration:
    def test_qc_on_mock_pipeline_output(self, tmp_path: Path):
        """Test QC against mock pipeline output (no real render)."""
        spec = PipelineSpec.default(renderer_adapter=_StubRenderer())
        orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path))
        job = orch.execute("Test Topic")

        assert job.status == JobStatus.COMPLETED

        # Run QC on the job output.
        artifact = VideoArtifact(
            job_id=job.job_id,
            status="completed",
            output_path="",
            mp4_exists=False,
            file_size_bytes=0,
            scene_count=len(job.visual_plan.scenes),
            total_duration_seconds=job.visual_plan.total_duration_seconds,
        )
        request = QCRequest(
            job_id=job.job_id,
            script=job.script,
            visual_plan=job.visual_plan,
            artifact=artifact,
        )
        report = run_qc(request)

        assert report.job_id == job.job_id
        # Should FAIL because no MP4 exists.
        assert report.overall_status == QCStatus.FAIL
        assert report.publish_ready is False
        assert len(report.errors) > 0

    def test_qc_on_real_render(self, tmp_path: Path):
        """Test QC against a real rendered MP4."""
        pytest.importorskip("PIL")
        if shutil.which("ffmpeg") is None:
            pytest.skip("ffmpeg not available")

        topic = "Why Most People Quit Learning a Skill Too Early"
        spec = PipelineSpec.default()
        orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path))
        orch.render_config = {"width": 320, "height": 240, "fps": 12}

        # Build a tiny script and plan.
        from src.orchestration.agents.research.mock import MockResearchAgent
        from src.orchestration.agents.strategy.mock import MockStrategyAgent
        from src.orchestration.agents.visual.mock import MockVisualPlannerAgent
        from src.orchestration.schemas.research import ResearchRequest

        research = MockResearchAgent().run(ResearchRequest(topic=topic))
        strategy = MockStrategyAgent().run(research)
        script = _tiny_script(topic)
        plan = MockVisualPlannerAgent().run(script)
        # Keep scenes aligned with the script's 2 sections.
        plan.scenes = plan.scenes[:2]
        for s in plan.scenes:
            s.duration_seconds = 1
        plan.total_duration_seconds = 2
        plan.render_job_plan["total_jobs"] = 2
        plan.render_job_plan["jobs"] = plan.render_job_plan["jobs"][:2]

        job = orch.create_job(topic)
        job.research = research
        job.strategy = strategy
        job.script = script
        job.visual_plan = plan

        from src.orchestration.schemas.production import ProductionRequest
        renderer = spec.registry.get("render")
        artifact = renderer.run(ProductionRequest(
            job_id=job.job_id,
            visual_plan=plan,
            output_path=str(tmp_path / job.job_id / "video.mp4"),
            render_config={"width": 320, "height": 240, "fps": 12},
        ))

        assert artifact.status == "completed", artifact.details
        assert Path(artifact.output_path).exists()

        # Run QC on the real output.
        request = QCRequest(
            job_id=job.job_id,
            script=script,
            visual_plan=plan,
            artifact=artifact,
            render_config={"width": 320, "height": 240, "fps": 12, "video_codec": "libx264", "audio_format": "aac"},
        )
        report = run_qc(request)

        assert report.job_id == job.job_id
        assert report.overall_status == QCStatus.PASS
        assert report.publish_ready is True
        assert report.metrics["failed"] == 0

        # Verify QC report JSON can be serialized.
        report_json = report.model_dump_json(indent=2)
        assert "overall_status" in report_json
        assert "publish_ready" in report_json
        assert "checks" in report_json

    def test_orchestrator_runs_qc_after_render(self, tmp_path: Path):
        """Pipeline-integrated QC: render → QC → qc_report.json + job.qc_status."""
        spec = PipelineSpec.default(renderer_adapter=_StubRenderer())
        assert "qc" in spec.stages
        orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path),
                                         stages=list(spec.stages))
        job = orch.execute("Test Topic")

        assert job.status == JobStatus.COMPLETED
        # QC gate ran after render and produced a report.
        assert job.qc_status is not None
        assert job.qc_report_path is not None
        report_path = Path(job.qc_report_path)
        assert report_path.exists()
        assert report_path.name == "qc_report.json"
        # The job directory is self-describing.
        assert (tmp_path / job.job_id / "qc_report.json").exists()

    def test_orchestrator_qc_gate_blocks_failed_render(self, tmp_path: Path):
        """No QC report when the render stage fails (pipeline stops earlier)."""
        from src.adapters.renderer.base import RendererAdapter

        class _FailRenderer(RendererAdapter):
            def run(self, request: ProductionRequest) -> VideoArtifact:
                return VideoArtifact(
                    job_id=request.job_id,
                    status="failed",
                    details={"error": "render exploded"},
                )

        spec = PipelineSpec.default(renderer_adapter=_FailRenderer())
        orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path),
                                         stages=list(spec.stages))
        job = orch.execute("Test Topic")
        assert job.status == JobStatus.FAILED
        # QC never ran for a failed render.
        from src.orchestration.schemas.job import QCJobStatus
        assert job.qc_status == QCJobStatus.NOT_RUN
        assert job.qc_report_path is None
