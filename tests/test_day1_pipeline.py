"""Day-1 pipeline tests (no FFmpeg): schemas, mocks, orchestrator, adapter."""
from __future__ import annotations
import pytest
from pydantic import ValidationError
from src.adapters.renderer.base import RendererAdapter
from src.orchestration.agents.research.mock import MockResearchAgent
from src.orchestration.agents.script.mock import MockScriptAgent
from src.orchestration.agents.strategy.mock import MockStrategyAgent
from src.orchestration.agents.visual.mock import MockVisualPlannerAgent
from src.orchestration.base import PipelineStageError, StageAgent
from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import PIPELINE_STAGES, STAGE_RENDER, STAGE_SCRIPT, STAGE_VISUAL_PLAN, STAGE_RESEARCH, STAGE_STRATEGY, PipelineSpec
from src.orchestration.schemas.job import JobStatus, StageStatus, VideoJob
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact
from src.orchestration.schemas.research import ResearchPackage, ResearchRequest
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage
from src.orchestration.schemas.visual import VisualPlan
DEFAULT_TOPIC = "Why Most People Quit Learning a Skill Too Early"
class _StubRenderer(RendererAdapter):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
    def run(self, request: ProductionRequest) -> VideoArtifact:
        if self.fail:
            return VideoArtifact(job_id=request.job_id, status="failed", output_path=request.output_path, details={"error": "boom"})
        return VideoArtifact(job_id=request.job_id, status="completed", output_path=request.output_path, mp4_exists=True, file_size_bytes=42, scene_count=len(request.visual_plan.scenes), total_duration_seconds=request.visual_plan.total_duration_seconds)
def _orch(tmp_path, renderer=None) -> VideoPipelineOrchestrator:
    spec = PipelineSpec.default(renderer_adapter=renderer or _StubRenderer())
    return VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path))
def _valid_plan() -> VisualPlan:
    r = MockResearchAgent().run(ResearchRequest(topic=DEFAULT_TOPIC))
    s = MockStrategyAgent().run(r)
    sc = MockScriptAgent().run(s)
    return MockVisualPlannerAgent().run(sc)
def test_schemas_reject_bad_input():
    with pytest.raises(ValidationError):
        ResearchRequest(topic="x")
    with pytest.raises(ValidationError):
        VideoArtifact(job_id="j", status="almost-done")
@pytest.mark.parametrize("cls", [MockResearchAgent, MockScriptAgent, MockStrategyAgent, MockVisualPlannerAgent, _StubRenderer])
def test_agents_use_common_interface(cls):
    assert issubclass(cls, StageAgent)
    assert getattr(cls, "stage", "") in PIPELINE_STAGES
def test_mock_chain_valid():
    r = MockResearchAgent().run(ResearchRequest(topic=DEFAULT_TOPIC))
    assert isinstance(r, ResearchPackage) and r.key_facts
    s = MockStrategyAgent().run(r)
    assert isinstance(s, StrategyPackage) and s.narrative_outline
    sc = MockScriptAgent().run(s)
    assert isinstance(sc, ScriptPackage) and len(sc.sections) == 6
    plan = MockVisualPlannerAgent().run(sc)
    assert isinstance(plan, VisualPlan) and len(plan.scenes) == 6
    assert plan.render_job_plan["total_jobs"] == 6
    assert len(plan.render_job_plan["jobs"]) == 6
def test_orchestrator_full_run_and_artifacts(tmp_path):
    orch = _orch(tmp_path)
    job = orch.execute(DEFAULT_TOPIC)
    assert job.status == JobStatus.COMPLETED
    assert job.artifact is not None and job.artifact.status == "completed"
    assert all(v.status == StageStatus.SUCCEEDED for v in job.stages.values())
    d = tmp_path / job.job_id
    for stage in (STAGE_RESEARCH, STAGE_STRATEGY, STAGE_SCRIPT, STAGE_VISUAL_PLAN):
        assert (d / f"{stage}.json").exists()
    saved = VideoJob.model_validate_json((tmp_path / "jobs" / f"{job.job_id}.json").read_text(encoding="utf-8"))
    assert saved.job_id == job.job_id
class _BoomScript(MockScriptAgent):
    stage = STAGE_SCRIPT
    def run(self, request):
        raise PipelineStageError(STAGE_SCRIPT, "script exploded")
def test_orchestrator_failure_propagation(tmp_path):
    spec = PipelineSpec.default(renderer_adapter=_StubRenderer())
    spec.registry._agents[STAGE_SCRIPT] = _BoomScript()
    orch = VideoPipelineOrchestrator(registry=spec.registry, output_dir=str(tmp_path))
    job = orch.execute(DEFAULT_TOPIC)
    assert job.status == JobStatus.FAILED
    assert job.current_stage == STAGE_SCRIPT
    assert job.stages[STAGE_SCRIPT].status == StageStatus.FAILED
    assert job.stages[STAGE_VISUAL_PLAN].status == StageStatus.PENDING
    assert job.stages[STAGE_RENDER].status == StageStatus.PENDING
def test_orchestrator_failed_render(tmp_path):
    job = _orch(tmp_path, renderer=_StubRenderer(fail=True)).execute(DEFAULT_TOPIC)
    assert job.status == JobStatus.FAILED
    assert job.current_stage == STAGE_RENDER
    assert "boom" in (job.error or "")
def test_renderer_adapter_success(tmp_path):
    from src.adapters.renderer.yairs import YairsRendererAdapter
    from src.core.agent_result import AgentResult
    class _Fake:
        def run(self, context):
            from pathlib import Path
            out = Path(context.get("final_media_output_path"))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"fake-mp4")
            context.set("final_media_result", {"status": "completed"})
            context.set("render_outputs", [{"job_id": "x"}])
            return AgentResult.ok()
    plan = _valid_plan()
    art = YairsRendererAdapter(render_pipeline_orchestrator=_Fake()).run(ProductionRequest(job_id="job_001", visual_plan=plan, output_path=str(tmp_path / "video.mp4")))
    assert art.status == "completed" and art.mp4_exists
    assert art.scene_count == len(plan.scenes)
def test_renderer_adapter_failure(tmp_path):
    from src.adapters.renderer.yairs import YairsRendererAdapter
    from src.core.agent_result import AgentResult
    class _Fail:
        def run(self, context):
            context.set("final_media_result", {"status": "failed", "error": "no ffmpeg"})
            return AgentResult.fail("no ffmpeg")
    art = YairsRendererAdapter(render_pipeline_orchestrator=_Fail()).run(ProductionRequest(job_id="job_001", visual_plan=_valid_plan(), output_path=str(tmp_path / "video.mp4")))
    assert art.status == "failed"
    assert "no ffmpeg" in str(art.details.get("error"))
def test_mock_script_paces_narration_to_scene_length():
    """Narration must fit its scene (renderer muxes audio with -shortest)."""
    import math
    research = MockResearchAgent().run(ResearchRequest(topic=DEFAULT_TOPIC))
    strategy = MockStrategyAgent().run(research)
    script = MockScriptAgent().run(strategy)
    for section in script.sections:
        needed = math.ceil(len(section.narration.split()) / 2.5)
        assert section.duration_seconds >= needed
def test_renderer_adapter_builds_combined_final_audio_request():
    from src.adapters.renderer.yairs import YairsRendererAdapter
    plan = _valid_plan()
    combined = YairsRendererAdapter._combined_final_audio_request(plan)
    assert combined is not None
    assert combined.duration_seconds == plan.total_duration_seconds
    for scene in plan.scenes:
        assert scene.narration in combined.narration_text
def test_renderer_adapter_combined_audio_none_without_narration():
    from src.adapters.renderer.yairs import YairsRendererAdapter
    plan = _valid_plan()
    for scene in plan.scenes:
        scene.narration = ""
    assert YairsRendererAdapter._combined_final_audio_request(plan) is None
def test_render_job_executor_backfills_scene_number_from_job():
    """Regression: renderers that omit scene_number (e.g. StickmanRenderer)
    must not break RenderOutputManager / VideoAssembler scene ordering."""
    from src.agents.render_job_executor import RenderJobExecutor, Renderer, RenderRequest
    from src.core.context import WorkflowContext

    class _ScenelessRenderer(Renderer):
        def render(self, request: RenderRequest):
            return {"job_id": str(request.job["job_id"]), "status": "completed", "output_reference": "mock://x", "duration_seconds": 2}

    executor = RenderJobExecutor(renderer=_ScenelessRenderer())
    context = WorkflowContext()
    context.set("render_jobs", [
        {"job_id": "job-1", "scene_number": 1, "duration_seconds": 2},
        {"job_id": "job-2", "scene_number": 2, "duration_seconds": 2},
    ])
    result = executor.run(context)
    assert result.success is True
    scene_numbers = [r["scene_number"] for r in context.get("render_results")]
    assert scene_numbers == [1, 2]




