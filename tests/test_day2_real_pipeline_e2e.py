"""Day-2 E2E: validates the complete real orchestration path.

Uses dependency-controlled/fake external research services to prove:
Research → Strategy → Script → Visual → Production are connected correctly.
"""
from __future__ import annotations
import pytest
from src.orchestration.orchestrator import VideoPipelineOrchestrator
from src.orchestration.pipeline import PipelineRegistry
from src.orchestration.schemas.job import JobStatus
from src.orchestration.agents.factory import build_stage_agents


class FakeTrendingResearchService:
    def research(self, keywords=None, region_code="US", per_keyword=10, limit=10, include_trending=True):
        return [type("Cand", (), {
            "topic": "Test", "source_video_id": "vid1", "source_title": "Title",
            "channel": "Ch", "view_count": 100000, "like_count": 1000,
            "comment_count": 100, "published_at": "2024-01-01T00:00:00Z",
            "views_per_day": 1000.0, "engagement_rate": 0.05, "score": 500.0,
            "keywords": ["ai", "learning"],
        })()]


class FakeTitleService:
    def generate_titles(self, topic, niche=None, audience=None, trend_data=None, count=20):
        return [{"title": "Test Title", "confidence": 80.0, "pattern_used": "Curiosity"}]

    def select_best_title(self, titles, topic):
        return titles[0] if titles else {"title": "Default", "confidence": 80.0}


class FakeContentService:
    def generate_script(self, **kwargs):
        return {
            "intro": "Intro text",
            "sections": [
                {"heading": "S1", "content": "Section 1 content narration.", "duration_seconds": 10},
                {"heading": "S2", "content": "Section 2 content narration.", "duration_seconds": 15},
            ],
            "cta": "Subscribe.",
            "estimated_duration_minutes": 5,
            "scenes": [{"scene_number": 1}],
        }

    def generate_hook(self, **kwargs):
        return {"script": "Hook text", "hook_type": "Curiosity", "retention_score": 75.0}


def _build_registry() -> PipelineRegistry:
    agents = build_stage_agents(
        mode="real",
        trending_research_service=FakeTrendingResearchService(),
        title_generation_service=FakeTitleService(),
        content_generation_service=FakeContentService(),
    )
    registry = PipelineRegistry()
    for stage, agent in agents.items():
        registry.register(agent, stage=stage)
    return registry


def test_full_pipeline_completes(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("AI Learning Strategies")
    assert job.status == JobStatus.COMPLETED
    assert job.research is not None
    assert job.strategy is not None
    assert job.script is not None
    assert job.visual_plan is not None


def test_research_stage_produces_package(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    assert job.research is not None
    assert job.research.topic == "Test Topic"


def test_strategy_stage_produces_package(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    assert job.strategy is not None
    assert job.strategy.topic == "Test Topic"


def test_script_stage_produces_package(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    assert job.script is not None
    assert len(job.script.sections) > 0


def test_visual_stage_produces_plan(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    assert job.visual_plan is not None
    assert len(job.visual_plan.scenes) > 0
    assert job.visual_plan.render_job_plan["total_jobs"] > 0


def test_scene_count_matches_sections(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    assert len(job.visual_plan.scenes) == len(job.script.sections)


def test_scene_numbering_ordered(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    numbers = [s.scene_number for s in job.visual_plan.scenes]
    assert numbers == list(range(1, len(numbers) + 1))


def test_total_duration_consistent(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    assert job.visual_plan.total_duration_seconds == job.script.total_duration_seconds


def test_render_job_plan_has_required_fields(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    plan = job.visual_plan.render_job_plan
    assert "total_jobs" in plan
    assert "jobs" in plan
    assert "total_duration_seconds" in plan
    for j in plan["jobs"]:
        assert "job_id" in j
        assert "scene_number" in j
        assert "duration_seconds" in j


def test_artifacts_persisted(tmp_path):
    registry = _build_registry()
    orch = VideoPipelineOrchestrator(registry=registry, output_dir=str(tmp_path))
    job = orch.execute("Test Topic")
    job_dir = tmp_path / job.job_id
    assert (job_dir / "research.json").exists()
    assert (job_dir / "strategy.json").exists()
    assert (job_dir / "script.json").exists()
    assert (job_dir / "visual_plan.json").exists()
    assert (job_dir / "job.json").exists()
