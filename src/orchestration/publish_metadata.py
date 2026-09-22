"""Publish metadata generation from YAIRS outputs.

Derives YouTube upload metadata (title, description, tags, category) from the
existing orchestration artifacts: StrategyPackage, ScriptPackage, and
VideoArtifact.  No extra LLM calls — everything comes from what YAIRS already
produced.
"""

from __future__ import annotations

from typing import Any

from src.orchestration.schemas.publish import PublishVisibility
from src.orchestration.schemas.production import VideoArtifact
from src.orchestration.schemas.script import ScriptPackage
from src.orchestration.schemas.strategy import StrategyPackage


def generate_publish_metadata(
    *,
    strategy: StrategyPackage | None = None,
    script: ScriptPackage | None = None,
    artifact: VideoArtifact | None = None,
    topic: str = "",
    visibility: PublishVisibility = PublishVisibility.PRIVATE,
    category_id: str = "22",
) -> dict[str, Any]:
    """Build YouTube upload metadata from existing YAIRS artifacts.

    Priority for title:
        1. ScriptPackage.title (if available)
        2. StrategyPackage.best_title.content (if available)
        3. Topic as fallback

    Description is built from:
        - ScriptPackage.hook + first section narration + call_to_action
        - Falls back to topic summary if script unavailable

    Tags are derived from:
        - Topic keywords
        - StrategyPackage.key_messages (limited to 10 tags max per YouTube)
    """
    title = _derive_title(strategy, script, topic)
    description = _derive_description(strategy, script, topic)
    tags = _derive_tags(strategy, topic)

    return {
        "title": title,
        "description": description,
        "tags": tags[:10],  # YouTube limit: 500 chars total, ~10 tags safe
        "category_id": category_id,
        "visibility": visibility.value,
        "source": {
            "title_source": _title_source(strategy, script),
            "description_source": _description_source(strategy, script),
            "tags_source": "strategy.key_messages + topic keywords",
        },
    }


def _derive_title(
    strategy: StrategyPackage | None,
    script: ScriptPackage | None,
    topic: str,
) -> str:
    """Derive video title from strategy/script/topic."""
    # 1. Script title (most specific)
    if script is not None and script.title and script.title.strip():
        return script.title.strip()

    # 2. Strategy best_title
    if strategy is not None:
        best = getattr(strategy, "best_title", None)
        if best and isinstance(best, dict):
            content = best.get("content") or best.get("title") or ""
            if content and str(content).strip():
                return str(content).strip()

    # 3. Fallback to topic
    return topic.strip() or "Untitled Video"


def _derive_description(
    strategy: StrategyPackage | None,
    script: ScriptPackage | None,
    topic: str,
) -> str:
    """Derive video description from script/strategy."""
    parts: list[str] = []

    # Hook from script
    if script is not None and script.hook:
        parts.append(script.hook.strip())

    # First section narration (teaser)
    if script is not None and script.sections:
        first_narration = script.sections[0].narration.strip()
        if first_narration:
            # Take first 200 chars max for teaser
            parts.append(first_narration[:200])

    # Call to action
    if script is not None and script.call_to_action:
        cta = script.call_to_action.strip()
        if cta:
            parts.append(f"\n\n{cta}")

    # Fallback: strategy angle or topic
    if not parts:
        if strategy is not None and strategy.angle:
            parts.append(strategy.angle)
        if not parts:
            parts.append(topic.strip() or "Generated video content")

    return "\n\n".join(p for p in parts if p).strip()


def _derive_tags(
    strategy: StrategyPackage | None,
    topic: str,
) -> list[str]:
    """Derive tags from strategy key messages and topic."""
    tags: list[str] = []

    # Key messages from strategy (most relevant)
    if strategy is not None:
        for msg in strategy.key_messages[:5]:
            msg = str(msg).strip().lower()
            if msg and len(msg) <= 50:  # YouTube tag limit
                # Use first few words as tag
                words = msg.split()
                tag = "_".join(words[:3]) if len(words) > 1 else words[0]
                if tag and tag not in tags:
                    tags.append(tag)

    # Topic keywords (split and clean)
    topic_clean = topic.strip().lower()
    if topic_clean:
        # Remove common stop words
        stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "by"}
        topic_words = [w for w in topic_clean.split() if w not in stop_words and len(w) > 1]
        for word in topic_words[:3]:
            if word not in tags:
                tags.append(word)

    # Ensure we always have at least one tag
    if not tags:
        tags.append("video")

    return tags


def _title_source(
    strategy: StrategyPackage | None,
    script: ScriptPackage | None,
) -> str:
    """Report where the title came from."""
    if script is not None and script.title:
        return "script.title"
    if strategy is not None and getattr(strategy, "best_title", None):
        return "strategy.best_title"
    return "topic_fallback"


def _description_source(
    strategy: StrategyPackage | None,
    script: ScriptPackage | None,
) -> str:
    """Report where the description came from."""
    if script is not None:
        return "script.hook + sections + call_to_action"
    if strategy is not None:
        return "strategy.angle_fallback"
    return "topic_fallback"