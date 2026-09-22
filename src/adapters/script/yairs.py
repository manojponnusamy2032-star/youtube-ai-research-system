"""Real script adapter — thin wrapper over existing YAIRS content generation service.

Converts StrategyPackage → ScriptPackage using existing YAIRS services:

    StrategyPackage
        ↓
    RealScriptAgent
        ↓
    ContentGenerationService.generate_script()
        ↓
    ScriptPackage
"""

from __future__ import annotations

from typing import Any

from src.orchestration.agents.script.base import ScriptAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.script import ScriptPackage, ScriptSection
from src.orchestration.schemas.strategy import StrategyPackage


def _duration_from_narration(narration: str, words_per_second: float = 2.5) -> int:
    """Estimate scene duration from narration word count."""
    word_count = len(narration.split()) if narration.strip() else 0
    return max(1, int(word_count / words_per_second))


class RealScriptAgent(ScriptAgent):
    """Adapter that wraps ContentGenerationService for script generation.

    Converts StrategyPackage → ScriptPackage using existing YAIRS services
    without duplicating script generation logic.
    """

    stage: str = "script"

    def __init__(
        self,
        content_generation_service: Any | None = None,
    ) -> None:
        self._content_generation_service = content_generation_service

    @property
    def content_generation_service(self) -> Any:
        if self._content_generation_service is None:
            raise PipelineStageError(stage=self.stage, message="content_generation_service required.")
        return self._content_generation_service

    @content_generation_service.setter
    def content_generation_service(self, value: Any) -> None:
        self._content_generation_service = value

    def run(self, request: StrategyPackage) -> ScriptPackage:
        service = self.content_generation_service

        topic = request.topic.strip()
        title = str((request.best_title or {}).get("title", topic)).strip() or topic
        hook_script = str((request.hook or {}).get("script", request.hook_idea or "")).strip()

        try:
            script_data = service.generate_script(
                topic=topic,
                audience=request.target_audience or "general",
                niche="",
                pattern_report=request.pattern_report or {},
                generated_titles=request.generated_titles or None,
                knowledge_base=request.knowledge_base or None,
                trend_info=getattr(request, "trend_info", None),
                best_title=request.best_title,
                hook=request.hook,
            )
        except Exception as exc:
            raise PipelineStageError(
                stage=self.stage,
                message=f"ContentGenerationService.generate_script() failed: {exc}",
                details={"topic": topic, "original_error": str(exc)},
            ) from exc

        if not script_data or not isinstance(script_data, dict):
            raise PipelineStageError(
                stage=self.stage,
                message=f"generate_script() returned invalid result: {script_data!r}",
                details={"topic": topic, "result_type": type(script_data).__name__ if script_data else None},
            )

        # Build ScriptSections from service output
        sections: list[ScriptSection] = []
        raw_sections = script_data.get("sections", [])
        for idx, sec in enumerate(raw_sections):
            if not isinstance(sec, dict):
                continue
            heading = str(sec.get("heading", f"Section {idx + 1}")).strip()
            narration = str(sec.get("content", sec.get("narration", sec.get("script", "")))).strip()
            duration = int(sec.get("duration_seconds", _duration_from_narration(narration)))
            if heading and narration:
                sections.append(ScriptSection(heading=heading, narration=narration, duration_seconds=max(1, duration)))

        if not sections:
            raise PipelineStageError(
                stage=self.stage,
                message=f"generate_script() produced no valid sections for '{topic}'.",
                details={"topic": topic, "raw_sections_count": len(raw_sections)},
            )

        total_duration = sum(s.duration_seconds for s in sections)
        call_to_action = str(script_data.get("cta", request.call_to_action or "")).strip()

        return ScriptPackage(
            topic=topic,
            title=title,
            hook=hook_script,
            sections=sections,
            call_to_action=call_to_action,
            total_duration_seconds=total_duration,
            intro=str(script_data.get("intro", "")).strip(),
            section_payloads=raw_sections if isinstance(raw_sections, list) else [],
            scene_payloads=script_data.get("scenes", []) if isinstance(script_data.get("scenes"), list) else [],
            estimated_duration_minutes=int(script_data.get("estimated_duration_minutes", 0)),
        )
