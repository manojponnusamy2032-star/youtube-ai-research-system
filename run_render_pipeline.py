"""Run a complete render-only pipeline from research through final MP4.

This script runs the full research pipeline with content generation and
rendering enabled, producing a final MP4. It does NOT enable YouTube uploading.
Uses a mock analysis provider to avoid Ollama dependency.
"""
import sys
import os
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file before importing anything that reads env vars
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

# Ensure YOUTUBE_API_KEY is set in environment (strip any whitespace)
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if key:
                os.environ[key] = value

from src.core.context import WorkflowContext
from src.core.agent_result import AgentResult
from src.api.dependencies import get_container, get_workflow_store, ResearchWorkflowExecutor


class MockAnalysisProvider:
    """Mock analysis provider that returns deterministic results without Ollama."""

    def __init__(self, base_url: str = "", model: str = "mock"):
        self.base_url = base_url
        self.model = model

    def get_model_name(self) -> str:
        """Get the model name."""
        return self.model

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        """Return a deterministic mock analysis response."""
        return json.dumps({
            "hook_type": "question",
            "opening_summary": "This video opens with a compelling question.",
            "main_topic": "stickman animation",
            "target_audience": "content creators",
            "emotion": "curiosity",
            "story_structure": "problem-solution",
            "title_formula": "How to [achieve result]",
            "thumbnail_pattern": "bold text on contrasting background",
            "cta_type": "subscribe",
            "value_proposition": "Learn stickman animation techniques",
            "estimated_video_style": "tutorial",
            "summary": "A comprehensive guide to stickman animation.",
            "confidence_score": 0.85,
            "sub_topics": ["animation basics", "character design", "motion"],
            "retention_techniques": ["pattern interrupt", "storytelling"],
            "keywords": ["stickman", "animation", "tutorial"],
            "psychological_triggers": ["curiosity", "desire to learn"],
            "difficulty_level": "beginner"
        })


def main():
    print("=" * 80)
    print("YAIRS Complete Render-Only Pipeline")
    print("=" * 80)

    # Get the container
    container = get_container()
    print(f"\n[Stage 0] Container initialized")
    print(f"  - YouTube API key: {'configured' if container.settings.youtube_api_key else 'MISSING'}")
    print(f"  - Database: {container.settings.database_path}")

    # Replace the analysis service with a mock provider
    from src.services.analysis_service import AnalysisService
    from src.agents.analysis_agent import AnalysisAgent

    mock_provider = MockAnalysisProvider()
    mock_analysis_service = AnalysisService(
        llm_provider=mock_provider,
        database_service=container.database_service,
    )
    mock_analysis_agent = AnalysisAgent(mock_analysis_service, container.database_service)

    # Replace the analysis agent in the workflow manager
    container.workflow_manager_agent.analysis_agent = mock_analysis_agent

    # Replace the MockRenderer with the real StickmanRenderer
    from src.services.stickman_renderer import StickmanRenderer
    from src.agents.render_job_executor import RenderJobExecutor

    # Get the render pipeline orchestrator and replace its executor's renderer
    orchestrator = container.content_generation_manager.render_pipeline_orchestrator
    if orchestrator is not None:
        real_renderer = StickmanRenderer(execute_enabled=True)
        # Replace the renderer in the executor
        executor = orchestrator.render_job_executor
        if executor is not None:
            executor.renderer = real_renderer
            print(f"  - Replaced MockRenderer with StickmanRenderer")

    # Build the workflow context
    final_output = str(PROJECT_ROOT / "data" / "output" / "final_render_pipeline.mp4")
    os.makedirs(os.path.dirname(final_output), exist_ok=True)

    payload = {
        "keyword": "stickman animation tutorial",
        "max_results": 3,
        "limit": 3,
        "run_title_generation": True,
        "run_content_generation": True,
        "run_render_job_management": True,
        "run_final_media_generation": True,
        "final_media_output_path": final_output,
        "continue_on_error": False,
    }

    context = WorkflowContext(payload)

    # Run the workflow manager
    workflow_manager = container.workflow_manager_agent
    print(f"\n[Stage 1] Starting workflow manager...")
    start_time = time.time()

    result = workflow_manager.run(context)

    elapsed = time.time() - start_time
    print(f"\n[Stage 2] Workflow completed in {elapsed:.2f}s")

    if isinstance(result, AgentResult):
        print(f"  - Success: {result.success}")
        if result.message:
            print(f"  - Message: {result.message}")
        if result.data:
            # Print report summary
            report = result.data.get("report", {})
            if report:
                print(f"\n  Workflow Report:")
                print(f"    Duration: {report.get('duration_seconds', 'N/A')}s")
                metrics = report.get("metrics", {})
                if metrics:
                    print(f"    Videos collected: {metrics.get('videos_collected', 0)}")
                    print(f"    Transcripts downloaded: {metrics.get('transcripts_downloaded', 0)}")
                    print(f"    Analyses completed: {metrics.get('analyses_completed', 0)}")
                    print(f"    Patterns extracted: {metrics.get('patterns_extracted', 0)}")
                    print(f"    Knowledge entries: {metrics.get('knowledge_entries_created', 0)}")
                    print(f"    Content packages: {metrics.get('content_packages_generated', 0)}")

                # Print stage reports
                for stage_name in ["collector", "transcript", "analysis", "pattern", "knowledge", "title", "content_generation"]:
                    stage = report.get(stage_name, {})
                    if stage:
                        print(f"    {stage_name}: success={stage.get('success', 'N/A')}, duration={stage.get('duration', 'N/A')}s")

    # Check for final media result
    final_media_result = context.get("final_media_result")
    if final_media_result:
        print(f"\n[Stage 3] Final Media Result:")
        print(f"  - Status: {final_media_result.get('status', 'N/A')}")
        print(f"  - Output: {final_media_result.get('output_reference', 'N/A')}")
        if final_media_result.get("error"):
            print(f"  - Error: {final_media_result['error']}")

    # Check render outputs
    render_outputs = context.get("render_outputs", [])
    if render_outputs:
        print(f"\n[Stage 4] Render Outputs ({len(render_outputs)}):")
        for output in render_outputs:
            print(f"  - {output.get('job_id', 'N/A')}: status={output.get('status', 'N/A')}, output={output.get('output_reference', 'N/A')}")

    # Check if final MP4 exists
    if os.path.exists(final_output):
        file_size = os.path.getsize(final_output)
        print(f"\n[Stage 5] Final MP4 verified:")
        print(f"  - Path: {final_output}")
        print(f"  - Size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")
        print(f"\n✅ PIPELINE COMPLETE: Final MP4 produced successfully")
        return 0
    else:
        print(f"\n❌ PIPELINE FAILED: Final MP4 not found at {final_output}")
        return 1


if __name__ == "__main__":
    sys.exit(main())