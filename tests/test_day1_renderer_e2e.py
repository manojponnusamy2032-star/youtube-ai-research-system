"""Day-1 E2E: mock stages -> REAL YAIRS renderer -> real MP4.

Renders one tiny scene (1s, 320x240) through the real StickmanRenderer +
VideoAssembler -> FinalMedia -> MediaMuxer path.  Marked ``integration``
because it shells out to FFmpeg.
"""
from __future__ import annotations
import pytest
from src.orchestration.agents.research.mock import MockResearchAgent
from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import PipelineSpec
from src.orchestration.schemas.job import JobStatus
from src.orchestration.schemas.research import ResearchRequest
from src.orchestration.schemas.script import ScriptPackage, ScriptSection


def _tiny_script(topic: str) -> ScriptPackage:
    section = ScriptSection(
        heading="Tiny check",
        narration="Day one pipeline check.",
        duration_seconds=1,
    )
    return ScriptPackage(topic=topic, title=topic, sections=[section],
                         total_duration_seconds=1)


def test_day1_e2e_mock_to_real_render_produces_mp4(tmp_path):
    pytest.importorskip("PIL")
    import shutil
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not available")
    topic = "Why Most People Quit Learning a Skill Too Early"
    spec = PipelineSpec.default()
    orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path))
    orch.render_config = {"width": 320, "height": 240, "fps": 12}
    # Build the real VisualPlan from the normal mock chain, then shrink to 1s.
    research = MockResearchAgent().run(ResearchRequest(topic=topic))
    from src.orchestration.agents.strategy.mock import MockStrategyAgent
    from src.orchestration.agents.script.mock import MockScriptAgent
    from src.orchestration.agents.visual.mock import MockVisualPlannerAgent
    strategy = MockStrategyAgent().run(research)
    script = MockScriptAgent().run(strategy)
    script.sections = script.sections[:1]
    script.sections[0].duration_seconds = 1
    script.total_duration_seconds = 1
    plan = MockVisualPlannerAgent().run(script)
    job = orch.create_job(topic)
    job.research = research
    job.strategy = strategy
    job.script = script
    job.visual_plan = plan
    from src.orchestration.schemas.production import ProductionRequest
    renderer = spec.registry.get("render")
    artifact = renderer.run(ProductionRequest(
        job_id=job.job_id, visual_plan=plan,
        output_path=str(tmp_path / job.job_id / "video.mp4"),
        render_config={"width": 320, "height": 240, "fps": 12}))
    assert artifact.status == "completed", artifact.details
    from pathlib import Path
    assert Path(artifact.output_path).exists()
    assert Path(artifact.output_path).stat().st_size > 0
    assert artifact.scene_count == 1
    assert job.status == JobStatus.PENDING  # direct adapter call; no orchestrator run
