"""Tests for content generation manager and workflow integration."""

from __future__ import annotations

from src.agents.content_generation_manager import ContentGenerationManager
from src.agents.hook_generator_agent import HookGeneratorAgent
from src.agents.script_generator_agent import ScriptGeneratorAgent
from src.agents.seo_generator_agent import SeoGeneratorAgent
from src.agents.thumbnail_generator_agent import ThumbnailGeneratorAgent
from src.agents.workflow_manager_agent import WorkflowManagerAgent
from src.core.agent_result import AgentResult
from src.core.context import WorkflowContext
from src.database.database_service import DatabaseService
from src.services.content_generation_service import ContentGenerationService


def _context() -> WorkflowContext:
    return WorkflowContext(
        {
            "topic": "AI Research Automation",
            "audience": "small creators",
            "niche": "education",
            "pattern_report": {"hooks": {"Open Loop": 43.0}, "emotions": {"Curiosity": 55.0}},
            "knowledge_entries": [{"pattern": "Open Loop", "frequency": 62.0, "confidence": 91.0}],
            "generated_titles": [{"title": "AI Research Pipeline That Retains Viewers", "confidence": 89.0, "estimated_ctr": 8.9}],
        }
    )


def _build_content_manager(service: ContentGenerationService) -> ContentGenerationManager:
    return ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
    )


def test_content_generation_manager_builds_package_and_updates_context(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "manager.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    manager = _build_content_manager(service)
    context = _context()

    result = manager.run(context)

    assert result.success is True
    assert result.data["count"] == 1
    assert context.get("generated_hook")["hook_type"]
    assert context.get("generated_thumbnail")["image_prompt"]
    assert context.get("generated_script")["sections"]
    assert context.get("generated_seo")["keywords"]
    assert context.get("content_package")["confidence"] > 0
    assert db.get_content_package_count() == 1
    db.disconnect()


class CollectorStub:
    def run(self, keyword: str, max_results: int = 50):
        return (5, 0)


class TranscriptStub:
    def run(self, limit: int = 50):
        return (4, 0, 0, 0)


class AnalysisStub:
    def run(self, limit: int = 50, force_reanalyze: bool = False):
        return (4, 0, 0)


class PatternStub:
    def run(self, context: WorkflowContext) -> AgentResult:
        context.set("pattern_report", {"hooks": {"Open Loop": 43.0}, "emotions": {"Curiosity": 55.0}})
        return AgentResult.ok(report=context.get("pattern_report"))


class KnowledgeStub:
    def run(self, context: WorkflowContext) -> AgentResult:
        context.set("knowledge_entries", [{"pattern": "Open Loop", "frequency": 62.0, "confidence": 91.0}])
        context.set("knowledge_entries_saved", 1)
        return AgentResult.ok(saved_entries=1)


class TitleStub:
    def run(self, context: WorkflowContext) -> AgentResult:
        context.set("generated_titles", [{"title": "AI Research Pipeline That Retains Viewers", "confidence": 89.0, "estimated_ctr": 8.9}])
        context.set("generated_titles_count", 1)
        return AgentResult.ok(count=1, titles=context.get("generated_titles"))


def test_workflow_manager_runs_content_generation_stage_when_enabled(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "workflow.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    content_manager = _build_content_manager(service)
    workflow_manager = WorkflowManagerAgent(
        collector_agent=CollectorStub(),
        transcript_agent=TranscriptStub(),
        analysis_agent=AnalysisStub(),
        pattern_extractor_agent=PatternStub(),
        knowledge_base_agent=KnowledgeStub(),
        title_generator_agent=TitleStub(),
        content_generation_manager=content_manager,
    )
    context = WorkflowContext({"keyword": "ai", "topic": "AI Research Automation", "run_content_generation": True})

    result = workflow_manager.run(context)
    report = result.data["report"]

    assert result.success is True
    assert report["title"]["success"] is True
    assert report["content_generation"]["success"] is True
    assert report["metrics"]["content_packages_generated"] == 1
    assert context.get("content_package")["topic"] == "AI Research Automation"
    db.disconnect()


def test_workflow_manager_skips_content_generation_when_disabled(tmp_path) -> None:
    db = DatabaseService(str(tmp_path / "workflow.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    content_manager = _build_content_manager(service)
    workflow_manager = WorkflowManagerAgent(
        collector_agent=CollectorStub(),
        transcript_agent=TranscriptStub(),
        analysis_agent=AnalysisStub(),
        pattern_extractor_agent=PatternStub(),
        knowledge_base_agent=KnowledgeStub(),
        title_generator_agent=TitleStub(),
        content_generation_manager=content_manager,
    )
    context = WorkflowContext({"keyword": "ai", "topic": "AI Research Automation"})

    result = workflow_manager.run(context)
    report = result.data["report"]

    assert result.success is True
    assert report["content_generation"]["success"] is False
    assert report["metrics"]["content_packages_generated"] == 0
    assert context.get("content_package") is None
    db.disconnect()


def test_content_generation_manager_runs_render_job_manager_when_enabled(tmp_path) -> None:
    """Test that render job manager is called when enabled in context."""
    from src.agents.render_job_manager import RenderJobManager
    
    db = DatabaseService(str(tmp_path / "render_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    render_job_manager = RenderJobManager()
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_job_manager=render_job_manager,
    )
    context = _context()
    context.set("run_render_job_management", True)

    result = content_manager.run(context)

    assert result.success is True
    assert context.has("render_jobs")
    assert context.get("render_jobs") is not None
    db.disconnect()


def test_content_generation_manager_skips_render_job_manager_when_disabled(tmp_path) -> None:
    """Test that render job manager is not called when disabled in context."""
    from src.agents.render_job_manager import RenderJobManager
    
    db = DatabaseService(str(tmp_path / "render_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    render_job_manager = RenderJobManager()
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_job_manager=render_job_manager,
    )
    context = _context()
    context.set("run_render_job_management", False)

    result = content_manager.run(context)

    assert result.success is True
    assert not context.has("render_jobs")
    db.disconnect()


def test_content_generation_manager_runs_render_pipeline_orchestrator_when_enabled(tmp_path) -> None:
    """Test that render pipeline orchestrator is called when enabled in context."""
    from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
    from src.agents.render_job_manager import RenderJobManager
    from src.agents.render_job_executor import RenderJobExecutor
    from src.agents.render_output_manager import RenderOutputManager
    
    db = DatabaseService(str(tmp_path / "render_pipeline_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    
    # Create the full render pipeline orchestrator
    render_job_manager = RenderJobManager()
    render_job_executor = RenderJobExecutor()
    render_output_manager = RenderOutputManager()
    render_pipeline_orchestrator = RenderPipelineOrchestrator(
        render_job_manager=render_job_manager,
        render_job_executor=render_job_executor,
        render_output_manager=render_output_manager,
    )
    
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_pipeline_orchestrator=render_pipeline_orchestrator,
    )
    context = _context()
    context.set("run_render_job_management", True)

    result = content_manager.run(context)

    assert result.success is True
    assert context.has("render_outputs")
    assert context.get("render_outputs") is not None
    assert len(context.get("render_outputs")) > 0
    db.disconnect()


def test_content_generation_manager_skips_render_pipeline_when_disabled(tmp_path) -> None:
    """Test that render pipeline orchestrator is not called when disabled in context."""
    from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
    from src.agents.render_job_manager import RenderJobManager
    from src.agents.render_job_executor import RenderJobExecutor
    from src.agents.render_output_manager import RenderOutputManager
    
    db = DatabaseService(str(tmp_path / "render_pipeline_disabled_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    
    render_pipeline_orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_pipeline_orchestrator=render_pipeline_orchestrator,
    )
    context = _context()
    context.set("run_render_job_management", False)

    result = content_manager.run(context)

    assert result.success is True
    assert not context.has("render_outputs")
    db.disconnect()


def test_content_generation_manager_render_pipeline_failure_does_not_corrupt_content_result(tmp_path) -> None:
    """Test that render pipeline failure does not corrupt the content generation result."""
    from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
    from src.agents.render_job_manager import RenderJobManager
    from src.agents.render_job_executor import RenderJobExecutor
    from src.agents.render_output_manager import RenderOutputManager
    
    class FailingRenderJobManager(RenderJobManager):
        def run(self, context: WorkflowContext) -> AgentResult:
            return AgentResult.fail("Render pipeline failed")
    
    db = DatabaseService(str(tmp_path / "render_pipeline_failure_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    
    render_pipeline_orchestrator = RenderPipelineOrchestrator(
        render_job_manager=FailingRenderJobManager(),
        render_job_executor=RenderJobExecutor(),
        render_output_manager=RenderOutputManager(),
    )
    
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_pipeline_orchestrator=render_pipeline_orchestrator,
    )
    context = _context()
    context.set("run_render_job_management", True)

    result = content_manager.run(context)

    # The overall result should be a failure from the render pipeline
    assert result.success is False
    assert "Render pipeline failed" in result.message
    
    # But the content package should still be in context
    assert context.has("content_package")
    assert context.get("content_package")["topic"] == "AI Research Automation"
    db.disconnect()


def test_content_generation_manager_populates_render_jobs_in_context(tmp_path) -> None:
    """Test that render_jobs is correctly populated from render_job_plan in context."""
    db = DatabaseService(str(tmp_path / "pop_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    
    # We use a mock orchestrator to observe the context just before it's run
    class MockOrchestrator:
        def __init__(self):
            self.observed_context = None
        def run(self, context: WorkflowContext) -> AgentResult:
            self.observed_context = context
            return AgentResult.ok()

    mock_orch = MockOrchestrator()
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_pipeline_orchestrator=mock_orch,
    )
    context = _context()
    context.set("run_render_job_management", True)

    result = content_manager.run(context)
    
    assert result.success is True
    assert mock_orch.observed_context.has("render_job_plan")
    assert mock_orch.observed_context.has("render_jobs")
    assert isinstance(mock_orch.observed_context.get("render_jobs"), list)
    db.disconnect()


def test_content_generation_manager_handshake_with_render_job_executor(tmp_path) -> None:
    """Test that RenderJobExecutor finds render_jobs and does not fail early."""
    from src.agents.render_job_executor import RenderJobExecutor
    
    db = DatabaseService(str(tmp_path / "handshake_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)
    
    render_job_executor = RenderJobExecutor()
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_job_manager=render_job_executor,
    )
    context = _context()
    context.set("run_render_job_management", True)

    result = content_manager.run(context)
    
    # If the handshake failed, it would say "render_jobs not found"
    assert "render_jobs not found" not in str(result.message)
    assert context.has("render_results")
    db.disconnect()


def test_e2e_pipeline_to_final_media(tmp_path) -> None:
    """Test full e2e handshake from generation down to FinalMediaOrchestrator."""
    from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
    from src.agents.render_job_manager import RenderJobManager
    from src.agents.render_job_executor import RenderJobExecutor, MockRenderer
    from src.agents.render_output_manager import RenderOutputManager
    from src.services.final_media_orchestrator import FinalMediaOrchestrator
    from src.services.tts_service import MockTTSService
    from src.services.tts_audio_renderer import TTSAudioRenderer
    from src.services.media_muxer import MediaMuxer
    from src.services.video_assembler import VideoAssembler
    from src.models.content_package import AudioRequest

    db = DatabaseService(str(tmp_path / "e2e_test.db"))
    db.connect()
    db.create_tables()
    service = ContentGenerationService(db)

    # Configure audio and job executor
    tts_service = MockTTSService()
    audio_renderer = TTSAudioRenderer(tts_service=tts_service)

    render_job_executor = RenderJobExecutor(
        renderer=MockRenderer(),
        audio_renderer=audio_renderer
    )
    
    render_pipeline_orchestrator = RenderPipelineOrchestrator(
        render_job_manager=RenderJobManager(),
        render_job_executor=render_job_executor,
        render_output_manager=RenderOutputManager(),
    )
    
    content_manager = ContentGenerationManager(
        hook_generator_agent=HookGeneratorAgent(service),
        thumbnail_generator_agent=ThumbnailGeneratorAgent(service),
        script_generator_agent=ScriptGeneratorAgent(service),
        seo_generator_agent=SeoGeneratorAgent(service),
        content_generation_service=service,
        render_pipeline_orchestrator=render_pipeline_orchestrator,
    )
    
    context = _context()
    context.set("run_render_job_management", True)

    result = content_manager.run(context)
    assert result.success is True
    
    render_outputs = context.get("render_outputs")
    assert render_outputs is not None
    assert len(render_outputs) > 0
    
    render_jobs = context.get("render_jobs")
    audio_requests = []
    for job in render_jobs:
        if "audio_request" in job and job["audio_request"]:
            if isinstance(job["audio_request"], dict):
                audio_requests.append(AudioRequest(**job["audio_request"]))
            else:
                audio_requests.append(job["audio_request"])
            
    if not audio_requests:
        audio_requests = [AudioRequest(scene_number=1, narration_text="Test", voice_reference="Test", audio_format="aac")]
    
    class MockVideoAssembler(VideoAssembler):
        def assemble(self, render_outputs):
            return {"status": "completed", "output_reference": "mock_video.mp4"}
            
    class MockMediaMuxer(MediaMuxer):
        def mux(self, video_ref, audio_ref, output_path):
            return {"status": "completed", "output_path": output_path}

    final_orchestrator = FinalMediaOrchestrator(
        video_assembler=MockVideoAssembler(),
        audio_renderer=audio_renderer,
        media_muxer=MockMediaMuxer(),
    )
    
    output_path = str(tmp_path / "final_output.mp4")
    final_result = final_orchestrator.create_final_media(
        render_outputs=render_outputs,
        audio_requests=audio_requests,
        output_path=output_path
    )
    
    assert final_result["status"] == "completed"
    assert final_result["output_path"] == output_path
    db.disconnect()
