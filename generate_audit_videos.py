"""Generate 3 complete real videos for Quality Audit using the YAIRS production pipeline."""
import sys
import os
import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from src.core.context import WorkflowContext
from src.core.agent_result import AgentResult
from src.api.dependencies import get_container

class DeterministicMockAnalysisProvider:
    """Mock analysis provider to bypass Ollama and guarantee clean production metadata."""
    def __init__(self, style_mode="educational"):
        self.style_mode = style_mode

    def get_model_name(self) -> str:
        return "mock-audit-provider"

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        if self.style_mode == "explainer":
            return json.dumps({
                "hook_type": "question",
                "opening_summary": "How do you animate stickmen step-by-step?",
                "main_topic": "explainer stickman animation tutorial",
                "target_audience": "beginners",
                "emotion": "curiosity",
                "story_structure": "step-by-step",
                "title_formula": "The Ultimate Stickman Guide",
                "thumbnail_pattern": "Bright text on dark ground",
                "cta_type": "subscribe",
                "value_proposition": "Master keyframe drawing in 30 seconds",
                "estimated_video_style": "educational",
                "summary": "Step by step stickman tutorial",
                "confidence_score": 0.95,
                "sub_topics": ["keyframes", "timings", "transitions"],
                "retention_techniques": ["pacing", "dynamic text"],
                "keywords": ["tutorial", "animation", "stickman"],
                "psychological_triggers": ["achievement", "curiosity"],
                "difficulty_level": "beginner"
            })
        elif self.style_mode == "storytelling":
            return json.dumps({
                "hook_type": "story",
                "opening_summary": "The untold story of Alan Becker's rise.",
                "main_topic": "alan becker storyteller documentary",
                "target_audience": "animation enthusiasts",
                "emotion": "inspiration",
                "story_structure": "hero journey",
                "title_formula": "How One Line Changed Animation",
                "thumbnail_pattern": "Historical photo collage",
                "cta_type": "like",
                "value_proposition": "The struggle and triumph of a legendary creator",
                "estimated_video_style": "documentary",
                "summary": "In-depth Alan Becker story",
                "confidence_score": 0.90,
                "sub_topics": ["origins", "viral hits", "animation vs animator"],
                "retention_techniques": ["climax", "tension"],
                "keywords": ["alan becker", "story", "documentary"],
                "psychological_triggers": ["empathy", "inspiration"],
                "difficulty_level": "intermediate"
            })
        else: # ranking
            return json.dumps({
                "hook_type": "open_loop",
                "opening_summary": "Top 3 stickman animators ranked by skill.",
                "main_topic": "ranking stickman animators list",
                "target_audience": "general audience",
                "emotion": "excitement",
                "story_structure": "countdown",
                "title_formula": "Top 3 Legendary Stickman Animators Ranked",
                "thumbnail_pattern": "Gold, silver, bronze medals",
                "cta_type": "comment",
                "value_proposition": "Who is the absolute best stickman animator?",
                "estimated_video_style": "ranking",
                "summary": "Ranking top stickman creators",
                "confidence_score": 0.88,
                "sub_topics": ["hyun", "alan becker", "terkoiz"],
                "retention_techniques": ["visual counter", "pattern interrupt"],
                "keywords": ["ranking", "top 3", "animators"],
                "psychological_triggers": ["opinion clash", "status"],
                "difficulty_level": "beginner"
            })


def generate_video(topic: str, duration_sec: int, style: str, output_filename: str):
    print("\n" + "="*60)
    print(f"GENERATING VIDEO: {topic} ({duration_sec}s, {style})")
    print("="*60)

    container = get_container()

    # Inject mock analysis provider matching the style mode
    from src.services.analysis_service import AnalysisService
    from src.agents.analysis_agent import AnalysisAgent
    mock_provider = DeterministicMockAnalysisProvider(style_mode=style)
    mock_analysis_service = AnalysisService(
        llm_provider=mock_provider,
        database_service=container.database_service,
    )
    container.workflow_manager_agent.analysis_agent = AnalysisAgent(mock_analysis_service, container.database_service)

    # Inject real renderer
    from src.services.stickman_renderer import StickmanRenderer
    orchestrator = container.content_generation_manager.render_pipeline_orchestrator
    if orchestrator is not None and orchestrator.render_job_executor is not None:
        orchestrator.render_job_executor.renderer = StickmanRenderer(execute_enabled=True)

    final_output = str(PROJECT_ROOT / "output" / output_filename)
    os.makedirs(os.path.dirname(final_output), exist_ok=True)
    # The FinalMediaOrchestrator writes to VideoAssembler's default
    # output/final_video.mp4. We copy that to the requested audit filename.
    assembled_output = str(PROJECT_ROOT / "output" / "final_video.mp4")
    if os.path.exists(assembled_output):
        try:
            os.remove(assembled_output)
        except OSError:
            pass

    # Configure a realistic payload targeting the desired duration/scenes
    num_scenes = max(2, int(duration_sec / 15))  # Explainer: 2 scenes (15s each), Storytelling: 3 scenes (15s each), Ranking: 4 scenes (15s each)
    
    # We will dynamically override the duration generated in ContentGenerationService if needed,
    # but the content generation service will automatically structure the scenes.
    # Let's intercept ContentGenerationService to enforce specific durations per scene for the audit.
    old_generate_content_package = container.content_generation_manager.content_generation_service.generate_content_package

    def custom_generate_content_package(*args, **kwargs):
        package = old_generate_content_package(*args, **kwargs)
        # Modify render_job_plan to match desired overall duration split across scenes
        if package.render_job_plan:
            jobs = package.render_job_plan.get("jobs", [])
            sec_per_scene = int(duration_sec / len(jobs)) if jobs else 15
            for idx, job in enumerate(jobs):
                job["duration_seconds"] = sec_per_scene
                if job.get("audio_request"):
                    job["audio_request"]["duration_seconds"] = sec_per_scene
            package.render_job_plan["total_duration_seconds"] = len(jobs) * sec_per_scene
        return package

    container.content_generation_manager.content_generation_service.generate_content_package = custom_generate_content_package

    payload = {
        "keyword": topic,
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
    result = container.workflow_manager_agent.run(context)

    # The FinalMediaOrchestrator only supports a single audio request, but
    # multi-scene videos have one per scene. Use the VideoAssembler directly
    # (which already preserves audio via concat/acrossfade) to produce the
    # final audit video from the rendered scene outputs.
    render_outputs = context.get("render_outputs", [])
    # Populate scene_number and transition_to_next from the render_job_plan
    # jobs, since RenderOutputManager does not carry them.
    render_job_plan = context.get("render_job_plan") or {}
    job_map = {}
    if isinstance(render_job_plan, dict):
        for job in render_job_plan.get("jobs", []):
            if isinstance(job, dict) and job.get("job_id"):
                job_map[str(job["job_id"])] = job
    for output in render_outputs:
        job = job_map.get(str(output.get("job_id")))
        if job is not None:
            if output.get("scene_number") is None:
                output["scene_number"] = job.get("scene_number")
            if "transition_to_next" not in output and job.get("transition_to_next"):
                output["transition_to_next"] = job["transition_to_next"]
    if render_outputs:
        from src.services.video_assembler import VideoAssembler
        assembler = VideoAssembler(execute_enabled=True)
        assembly_result = assembler.assemble(render_outputs)
        if assembly_result.get("status") == "completed":
            assembled_output = assembly_result.get("output_reference", assembled_output)
        else:
            print(f"[WARN] Assembly failed: {assembly_result.get('error', 'unknown')}")

    # Copy the assembled final video to the requested audit filename.
    if os.path.exists(assembled_output):
        try:
            import shutil
            shutil.copy2(assembled_output, final_output)
        except OSError as e:
            print(f"[WARN] Could not copy final video: {e}")

    if os.path.exists(final_output):
        print(f"[OK] Success! Generated output video saved to: {final_output}")
    else:
        print(f"[FAIL] Failed to generate video at: {final_output}")


if __name__ == "__main__":
    # Generate 3 distinct real videos using the actual production pipeline.
    # Optional CLI args select which videos to (re)generate by 1-based index,
    # e.g. `python generate_audit_videos.py 1 3` regenerates explainer+ranking.
    audits = [
        {
            "topic": "simple stickman animation tutorial",
            "duration_sec": 30,
            "style": "explainer",
            "output_filename": "audit_explainer.mp4",
        },
        {
            "topic": "the untold story of stickman fight animations",
            "duration_sec": 45,
            "style": "storytelling",
            "output_filename": "audit_storytelling.mp4",
        },
        {
            "topic": "top 3 legend stickman animators ranked",
            "duration_sec": 60,
            "style": "ranking",
            "output_filename": "audit_ranking.mp4",
        },
    ]
    selected = sys.argv[1:]
    if selected:
        picks = set()
        for token in selected:
            if token.isdigit() and 1 <= int(token) <= len(audits):
                picks.add(int(token) - 1)
        audits = [audits[i] for i in sorted(picks)] or audits
    for spec in audits:
        generate_video(**spec)
