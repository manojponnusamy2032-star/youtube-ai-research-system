"""Real strategy adapter — thin wrapper over existing YAIRS title/hook services.

Converts ResearchPackage → StrategyPackage using existing YAIRS services:

    ResearchPackage
        ↓
    RealStrategyAgent
        ↓
    TitleGenerationService + ContentGenerationService.generate_hook()
        ↓
    StrategyPackage

This adapter does NOT generate the full script — that's the Script stage's job.
It only decides: title, angle, hook, key messages, emotional direction, CTA direction.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.agents.strategy.base import StrategyAgent
from src.orchestration.base import PipelineStageError
from src.orchestration.schemas.research import ResearchPackage
from src.orchestration.schemas.strategy import StrategyPackage


def _normalize_confidence(score: float, max_score: float = 100.0) -> float:
    """Normalize a raw score (0-100 scale) to a 0-1 confidence value."""
    return max(0.0, min(1.0, score / max_score))


def _build_angle_from_title_and_hook(title: str, hook: str, topic: str) -> str:
    """Derive a creative angle from the selected title and hook.

    Uses actual content from the title and hook rather than inventing
    generic strategy language.
    """
    title_lower = title.lower()
    hook_lower = hook.lower()
    topic_lower = topic.lower()

    # Determine angle based on title patterns
    if "vs" in title_lower or "comparison" in title_lower or "vs" in hook_lower:
        angle = (
            f"Comparative analysis angle: exploring how {topic} stacks up against "
            f"alternatives, using evidence-based comparisons rather than hype."
        )
    elif "how to" in title_lower or "guide" in title_lower or "step by step" in title_lower:
        angle = (
            f"Practical tutorial angle: actionable steps for {topic} that viewers "
            f"can implement immediately, avoiding theoretical fluff."
        )
    elif "mistake" in title_lower or "wrong" in title_lower or "stop" in title_lower:
        angle = (
            f"Warning/prevention angle: exposing common {topic} pitfalls and how "
            f"to avoid them before they cost time or money."
        )
    elif "secret" in title_lower or "hidden" in title_lower or "nobody" in title_lower:
        angle = (
            f"Insider knowledge angle: revealing underappreciated {topic} insights "
            f"that most people miss because they're focused on the obvious."
        )
    elif "story" in title_lower or "my" in title_lower or "i " in hook_lower:
        angle = (
            f"Personal narrative angle: using real {topic} experiences and lessons "
            f"learned to make abstract concepts concrete and relatable."
        )
    elif "why" in title_lower or "reason" in title_lower or "because" in hook_lower:
        angle = (
            f"Explanation/understanding angle: going beyond surface-level {topic} "
            f"advice to explain the 'why' behind what works."
        )
    elif "best" in title_lower or "top" in title_lower or "ranking" in title_lower:
        angle = (
            f"Curated recommendations angle: cutting through {topic} noise with "
            f"ranked, tested options based on real outcomes."
        )
    elif "transform" in title_lower or "change" in title_lower or "result" in hook_lower:
        angle = (
            f"Transformation/outcome angle: focused on the tangible results and "
            f"life/effects changes that {topic} can deliver."
        )
    else:
        # Default: derive angle from topic + hook combination
        angle = (
            f"Practical {topic} strategy angle: combining proven approaches with "
            f"actionable insights that viewers can apply to their own situation."
        )

    return angle


def _extract_emotional_triggers_from_hook(hook: dict[str, Any]) -> list[str]:
    """Extract emotional triggers from hook metadata if available."""
    if not hook:
        return []

    triggers: list[str] = []
    hook_type = hook.get("hook_type", "")
    if hook_type:
        triggers.append(hook_type.lower())

    emotional_trigger = hook.get("emotional_trigger", "")
    if emotional_trigger:
        if isinstance(emotional_trigger, str):
            triggers.append(emotional_trigger.lower())
        elif isinstance(emotional_trigger, list):
            triggers.extend([t.lower() for t in emotional_trigger if isinstance(t, str)])

    seen: set[str] = set()
    unique_triggers: list[str] = []
    for t in triggers:
        key = t.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique_triggers.append(key)

    return unique_triggers[:5]


def _build_narrative_outline_from_titles(
    generated_titles: list[dict[str, Any]],
    hook_text: str,
    topic: str,
) -> list[str]:
    """Build a minimal narrative outline from title analysis."""
    if not generated_titles:
        return [
            f"Open with hook: {hook_text[:80]}...",
            f"Introduce {topic} topic and why it matters now",
            "Develop main argument with supporting points",
            f"Conclude with key takeaway for {topic}",
        ]

    patterns: list[str] = []
    for title_data in generated_titles[:3]:
        if isinstance(title_data, dict):
            pattern = title_data.get("pattern_used", "")
            if pattern:
                patterns.append(pattern)

    if patterns:
        unique_patterns = list(dict.fromkeys(patterns))
        outline = [
            f"Hook/Opening: {hook_text[:80]}...",
            f"Credibility setup: why {topic} matters based on trend analysis",
        ]

        if "Story" in unique_patterns or "Curiosity" in unique_patterns:
            outline.append("Open with engaging story or intriguing question")
        if "Mistake" in unique_patterns or "Shock" in unique_patterns:
            outline.append("Reveal common mistakes or misconceptions")
        if "Tutorial" in unique_patterns or "How" in unique_patterns:
            outline.append("Provide step-by-step practical guidance")
        if "Transformation" in unique_patterns or "Before/After" in unique_patterns:
            outline.append("Show transformation or before/after contrast")
        if "Comparison" in unique_patterns or "vs" in unique_patterns:
            outline.append("Compare options or approaches with evidence")
        if "Listicle" in unique_patterns or "Ranking" in unique_patterns:
            outline.append("Present ranked list or key points")

        outline.extend([
            f"Deep dive: key insights about {topic}",
            f"Actionable takeaways for {topic}",
            f"Conclusion: wrap up and next steps",
        ])

        return outline

    return [
        f"Hook: {hook_text[:80]}...",
        f"Introduction to {topic}: context and relevance",
        "Main content: key points and analysis",
        f"Conclusion: summary and actionable next steps",
    ]


def _derive_key_messages(
    title: str,
    hook: str,
    narrative_outline: list[str],
    research: ResearchPackage,
) -> list[str]:
    """Derive key messages from strategy decisions and research context."""
    messages: list[str] = []

    if hook:
        messages.append(f"Core hook: {hook[:100]}...")

    for beat in narrative_outline[:3]:
        if beat and len(messages) < 4:
            messages.append(beat[:80] + ("..." if len(beat) > 80 else ""))

    if research.sub_topics:
        for subtopic in research.sub_topics[:2]:
            messages.append(f"Subtopic to explore: {subtopic}")

    if research.key_facts:
        for fact in research.key_facts[:2]:
            messages.append(f"Supporting fact: {fact}")

    if not messages:
        messages.append(f"Key insight about {title}")
        messages.append(f"Practical application for {title}")
        messages.append(f"Why this matters for the audience")

    return messages[:5]


def _derive_call_to_action(
    hook: dict[str, Any],
    audience: str,
    topic: str,
) -> str:
    """Derive a CTA from hook metadata or use a sensible default."""
    if hook and hook.get("cta"):
        return str(hook["cta"])

    hook_type = (hook or {}).get("hook_type", "").lower()
    if "transformation" in hook_type:
        return f"Start your {topic} transformation today with one small step"
    elif "challenge" in hook_type:
        return f"Take the {topic} challenge and see what changes"
    elif "mistake" in hook_type:
        return f"Audit your {topic} approach and fix the biggest mistake first"
    elif "secret" in hook_type:
        return f"Apply this {topic} insight and measure the difference"
    elif "story" in hook_type:
        return f"Share your {topic} story and join the conversation"
    elif "comparison" in hook_type or "vs" in hook_type:
        return f"Test which {topic} approach works best for you"
    elif "tutorial" in hook_type or "how to" in hook_type:
        return f"Try the {topic} steps covered and report your results"

    if audience and audience.lower() != "general":
        return f"Apply these {topic} insights to your {audience} context today"
    else:
        return f"Take one action on {topic} today based on what you learned"


class RealStrategyAgent(StrategyAgent):
    """Adapter that wraps TitleGenerationService + ContentGenerationService for strategy."""

    stage: str = "strategy"

    def __init__(
        self,
        title_generation_service: Any | None = None,
        content_generation_service: Any | None = None,
        confidence_max_score: float = 100.0,
    ) -> None:
        self._title_generation_service = title_generation_service
        self._content_generation_service = content_generation_service
        self._confidence_max_score = confidence_max_score

    @property
    def title_generation_service(self) -> Any:
        if self._title_generation_service is None:
            raise PipelineStageError(stage=self.stage, message="title_generation_service required.")
        return self._title_generation_service

    @title_generation_service.setter
    def title_generation_service(self, value: Any) -> None:
        self._title_generation_service = value

    @property
    def content_generation_service(self) -> Any:
        if self._content_generation_service is None:
            raise PipelineStageError(stage=self.stage, message="content_generation_service required.")
        return self._content_generation_service

    @content_generation_service.setter
    def content_generation_service(self, value: Any) -> None:
        self._content_generation_service = value

    def run(self, request: ResearchPackage) -> StrategyPackage:
        title_service = self.title_generation_service
        content_service = self.content_generation_service

        topic = request.topic.strip()
        audience = request.target_audience or "general"
        niche = getattr(request, "niche", "") or ""
        trend_info = getattr(request, "trend_info", None)
        trend_data = self._extract_trend_data(trend_info) if trend_info else None

        try:
            generated_titles = title_service.generate_titles(
                topic=topic, niche=niche or None, audience=audience,
                trend_data=trend_data, count=20,
            )
        except Exception as exc:
            raise PipelineStageError(
                stage=self.stage,
                message=f"TitleGenerationService.generate_titles() failed: {exc}",
                details={"topic": topic, "original_error": str(exc)},
            ) from exc

        if not generated_titles:
            raise PipelineStageError(
                stage=self.stage,
                message=f"TitleGenerationService returned no titles for '{topic}'.",
                details={"topic": topic},
            )

        generated_titles_dicts: list[dict[str, Any]] = []
        for tc in generated_titles:
            if hasattr(tc, "to_dict"):
                generated_titles_dicts.append(tc.to_dict())
            elif isinstance(tc, dict):
                generated_titles_dicts.append(tc)
            else:
                try:
                    generated_titles_dicts.append(dict(tc))
                except (TypeError, ValueError):
                    raise PipelineStageError(
                        stage=self.stage, message=f"Malformed title candidate: {tc!r}",
                    )

        try:
            best_title = title_service.select_best_title(titles=generated_titles_dicts, topic=topic)
        except Exception as exc:
            raise PipelineStageError(
                stage=self.stage,
                message=f"TitleGenerationService.select_best_title() failed: {exc}",
                details={"topic": topic, "original_error": str(exc)},
            ) from exc

        if not best_title or not isinstance(best_title, dict):
            raise PipelineStageError(
                stage=self.stage, message=f"select_best_title() returned invalid: {best_title!r}",
            )

        best_title_text = str(best_title.get("title", "")).strip()
        if not best_title_text:
            raise PipelineStageError(
                stage=self.stage, message=f"Selected best title has no text: {best_title!r}",
            )

        try:
            hook_inputs = self._build_hook_inputs(request, best_title_text, generated_titles_dicts)
            hook_result = content_service.generate_hook(**hook_inputs)
        except Exception as exc:
            raise PipelineStageError(
                stage=self.stage,
                message=f"ContentGenerationService.generate_hook() failed: {exc}",
                details={"topic": topic, "original_error": str(exc)},
            ) from exc

        if not hook_result or not isinstance(hook_result, dict):
            raise PipelineStageError(
                stage=self.stage, message=f"generate_hook() returned invalid: {hook_result!r}",
            )

        hook_text = str(hook_result.get("script", "")).strip()
        if not hook_text:
            for field in ("hook", "text", "content", "narration"):
                if hook_result.get(field):
                    hook_text = str(hook_result[field]).strip()
                    break

        if not hook_text:
            raise PipelineStageError(
                stage=self.stage, message=f"Generated hook has no text: {hook_result!r}",
            )

        angle = _build_angle_from_title_and_hook(best_title_text, hook_text, topic)
        narrative_outline = _build_narrative_outline_from_titles(generated_titles_dicts, hook_text, topic)
        emotional_triggers = _extract_emotional_triggers_from_hook(hook_result)
        key_messages = _derive_key_messages(best_title_text, hook_text, narrative_outline, request)
        call_to_action = _derive_call_to_action(hook_result, audience, topic)

        title_confidence = float(best_title.get("confidence", 50.0))
        hook_retention = float(hook_result.get("retention_score", 50.0))
        combined_score = (title_confidence + hook_retention) / 2.0
        confidence = _normalize_confidence(combined_score, self._confidence_max_score)

        hook_dict: dict[str, Any] = {
            "script": hook_text,
            "hook_type": hook_result.get("hook_type", ""),
            "retention_score": hook_result.get("retention_score", 0.0),
        }
        for key in ("emotional_trigger", "cta", "structure", "pattern"):
            if key in hook_result:
                hook_dict[key] = hook_result[key]

        return StrategyPackage(
            topic=topic, angle=angle, narrative_outline=narrative_outline,
            key_messages=key_messages, emotional_triggers=emotional_triggers,
            hook_idea=hook_text, call_to_action=call_to_action,
            target_audience=audience, confidence=confidence,
            best_title=best_title, hook=hook_dict,
            generated_titles=generated_titles_dicts,
            pattern_report=getattr(request, "pattern_report", {}) or {},
            knowledge_base=getattr(request, "knowledge_base", []) or [],
        )

    def _extract_trend_data(self, trend_info: dict[str, Any] | None) -> Any:
        if not trend_info or not isinstance(trend_info, dict):
            return None
        for field in ("trend_terms", "trends", "keywords", "trend_info"):
            terms = trend_info.get(field)
            if terms and isinstance(terms, list):
                return terms
        top = trend_info.get("top_candidate", {})
        if isinstance(top, dict):
            for field in ("keywords", "tags"):
                terms = top.get(field)
                if terms and isinstance(terms, list):
                    return terms
        return None

    def _build_hook_inputs(self, request: ResearchPackage, best_title: str,
                           generated_titles: list[dict[str, Any]]) -> dict[str, Any]:
        inputs: dict[str, Any] = {
            "topic": request.topic,
            "niche": getattr(request, "niche", "") or None,
            "audience": request.target_audience or "general",
        }
        trend_info = getattr(request, "trend_info", None)
        if trend_info:
            trend_data = self._extract_trend_data(trend_info)
            if trend_data:
                inputs["trend_data"] = trend_data
        pattern_report = getattr(request, "pattern_report", None)
        if pattern_report:
            inputs["pattern_report"] = pattern_report
        knowledge_base = getattr(request, "knowledge_base", None)
        if knowledge_base:
            inputs["knowledge_base"] = knowledge_base
        if generated_titles:
            inputs["generated_titles"] = generated_titles
        return inputs