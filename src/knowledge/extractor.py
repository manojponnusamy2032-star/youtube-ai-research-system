"""Automatic knowledge extraction from structured research/analysis output."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from src.knowledge.deduplicator import Deduplicator
from src.knowledge.knowledge_service import KnowledgeService
from src.knowledge.models import KnowledgeNote, NoteType, RelationshipType, slugify, normalize_title


class KnowledgeExtractor:
    """Extract structured knowledge entities from research/analysis output.

    This service inspects structured data produced by the existing research
    pipeline and identifies reusable knowledge worth persisting in the
    Obsidian vault. It is deliberately conservative - it only extracts
    entities that are meaningful and reusable, not raw LLM text.
    """

    # Mapping from source field names to knowledge note types
    ENTITY_TYPE_KEYWORDS: dict[NoteType, list[str]] = {
        NoteType.CONCEPT: ["concept", "topic", "term", "technique", "framework", "principle"],
        NoteType.RESEARCH: ["research", "finding", "study", "analysis", "report", "observation"],
        NoteType.INSIGHT: ["insight", "pattern", "hook", "strategy", "recommendation", "lesson"],
        NoteType.DECISION: ["decision", "choice", "resolution"],
        NoteType.LESSON: ["lesson", "mistake", "failure", "issue", "problem", "error"],
        NoteType.PROJECT: ["project", "workflow", "pipeline", "system"],
        NoteType.SOURCE: ["source", "reference", "article", "video", "url"],
    }

    # Confidence bands
    HIGH_CONFIDENCE = 0.90
    MEDIUM_CONFIDENCE = 0.70

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        deduplicator: Deduplicator | None = None,
    ) -> None:
        """Initialize extractor with knowledge service and optional deduplicator."""
        self.knowledge_service = knowledge_service
        self.deduplicator = deduplicator or Deduplicator(knowledge_service.repository)

    def extract_from_analysis_batch(
        self,
        analyses: list[dict[str, Any]],
        *,
        project: str | None = None,
        source_type: str = "research_analysis",
        batch_id: str | None = None,
        generated_by: str = "KnowledgeExtractor",
    ) -> dict[str, Any]:
        """Extract knowledge from a batch of structured analysis results.

        This processes structured analysis data (from the existing pipeline),
        not raw transcripts. It identifies reusable knowledge entities and
        persists them to the vault with deduplication and provenance.

        Args:
            analyses: List of analysis dicts from the research pipeline.
            project: Optional project name to associate notes with.
            source_type: Type label for provenance tracking.
            batch_id: Optional source batch ID.
            generated_by: Generator label for provenance.

        Returns:
            Summary dict with created, updated, skipped counts.
        """
        created = 0
        updated = 0
        skipped = 0
        notes_out: list[dict[str, Any]] = []

        if not analyses:
            return {"created": 0, "updated": 0, "skipped": 0, "notes": []}

        # Extract source video IDs from analyses
        source_video_ids = self._collect_source_video_ids(analyses)
        source_id = batch_id or f"batch-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

        for analysis in analyses:
            entities = self._extract_entities_from_analysis(analysis)
            for entity in entities:
                outcome = self._persist_entity(
                    entity=entity,
                    project=project,
                    source_type=source_type,
                    source_id=source_id,
                    source_video_ids=source_video_ids,
                    generated_by=generated_by,
                )
                if outcome == "created":
                    created += 1
                elif outcome == "updated":
                    updated += 1
                else:
                    skipped += 1
                notes_out.append(outcome)

        # Auto-link extracted notes to the project note
        if project:
            self._link_to_project(project, analyses)

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "notes": notes_out,
        }

    def _extract_entities_from_analysis(self, analysis: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract candidate knowledge entities from a single analysis.

        This is intentionally conservative. It looks for well-structured fields
        that represent reusable knowledge, not free-form LLM text.
        """
        entities: list[dict[str, Any]] = []

        # 1. Topic/concept extraction from main_topic
        topic = analysis.get("main_topic") or analysis.get("topic")
        if topic and isinstance(topic, str) and len(topic) > 2:
            entities.append({
                "title": self._title_case(topic),
                "type": NoteType.CONCEPT,
                "content": self._build_concept_content(analysis),
                "tags": ["concept", "extracted"],
                "confidence": self._analysis_confidence(analysis),
                "aliases": self._generate_aliases(topic),
                "source_key": "main_topic",
            })

        # 2. Hook pattern insight
        hook_type = analysis.get("hook_type")
        if hook_type and isinstance(hook_type, str) and len(hook_type) > 2:
            confidence = self._analysis_confidence(analysis)
            title = f"{self._title_case(hook_type)} Hook Pattern"
            entities.append({
                "title": title,
                "type": NoteType.INSIGHT,
                "content": self._build_hook_content(analysis),
                "tags": ["viral-pattern", "hook", "extracted"],
                "confidence": confidence,
                "aliases": [hook_type, f"{hook_type} hook"],
                "source_key": "hook_type",
            })

        # 3. Retention technique insight
        retention = analysis.get("retention_techniques") or analysis.get("retention_technique")
        if retention:
            techniques = self._as_list(retention)
            for technique in techniques:
                if isinstance(technique, str) and len(technique) > 2:
                    entities.append({
                        "title": f"Retention: {self._title_case(technique)}",
                        "type": NoteType.INSIGHT,
                        "content": self._build_retention_content(analysis, technique),
                        "tags": ["retention", "viral-pattern", "extracted"],
                        "confidence": self._analysis_confidence(analysis),
                        "aliases": [technique],
                        "source_key": "retention_techniques",
                    })

        # 4. Emotion trigger insight
        emotion = analysis.get("emotion") or analysis.get("emotional_trigger")
        if emotion and isinstance(emotion, str) and len(emotion) > 2:
            entities.append({
                "title": f"Emotional Trigger: {self._title_case(emotion)}",
                "type": NoteType.INSIGHT,
                "content": self._build_emotion_content(analysis, emotion),
                "tags": ["emotion", "viral-pattern", "extracted"],
                "confidence": self._analysis_confidence(analysis),
                "aliases": [emotion],
                "source_key": "emotion",
            })

        # 5. Story structure insight
        story = analysis.get("story_structure")
        if story and isinstance(story, str) and len(story) > 2:
            entities.append({
                "title": f"Story Structure: {self._title_case(story)}",
                "type": NoteType.INSIGHT,
                "content": self._build_story_content(analysis, story),
                "tags": ["story", "viral-pattern", "extracted"],
                "confidence": self._analysis_confidence(analysis),
                "aliases": [story],
                "source_key": "story_structure",
            })

        # 6. Title formula insight
        title_formula = analysis.get("title_formula")
        if title_formula and isinstance(title_formula, str) and len(title_formula) > 2:
            entities.append({
                "title": f"Title Formula: {self._title_case(title_formula)}",
                "type": NoteType.INSIGHT,
                "content": self._build_title_content(analysis, title_formula),
                "tags": ["title", "viral-pattern", "extracted"],
                "confidence": self._analysis_confidence(analysis),
                "aliases": [title_formula],
                "source_key": "title_formula",
            })

        return entities

    def _persist_entity(
        self,
        entity: dict[str, Any],
        *,
        project: str | None,
        source_type: str,
        source_id: str,
        source_video_ids: list[str],
        generated_by: str,
    ) -> str:
        """Persist an entity to the vault with deduplication.

        Returns one of: "created", "updated", "skipped".
        """
        title = str(entity["title"])

        # Build a candidate note for dedup matching
        candidate = KnowledgeNote(
            id="",
            type=entity["type"],
            title=title,
            content=str(entity.get("content", "")),
            tags=entity.get("tags", []),
            confidence=entity.get("confidence"),
            aliases=entity.get("aliases", []),
        )

        existing = self.deduplicator.find_match(candidate)

        if existing:
            # Update existing note with new evidence
            existing_content = existing.content
            content = str(entity.get("content", ""))

            # Append evidence if meaningful
            if content and content not in existing_content:
                evidence_marker = self._evidence_marker(source_id, source_video_ids)
                if evidence_marker not in existing_content:
                    existing.content = f"{existing_content}\n\n{content}\n\n{evidence_marker}"

            # Update confidence (take max - optimistic but preserves history)
            new_conf = entity.get("confidence")
            if new_conf is not None:
                if existing.confidence is None or new_conf > existing.confidence:
                    existing.confidence = new_conf

            # Merge tags
            existing.tags = list(set(existing.tags) | set(entity.get("tags", [])))

            # Merge aliases
            existing.aliases = list(set(existing.aliases) | set(entity.get("aliases", [])))

            # Update provenance
            existing.source_type = source_type
            existing.source_id = existing.source_id or source_id
            existing.source_video_ids = list(set(existing.source_video_ids) | set(source_video_ids))
            existing.generated_by = generated_by
            existing.project = project or existing.project
            existing.updated_at = datetime.now(timezone.utc).isoformat()

            self.knowledge_service.repository.save_note(existing)
            return "updated"

        # Create new note
        self.knowledge_service.create_note(
            title=title,
            note_type=entity["type"],
            content=str(entity.get("content", "")),
            tags=entity.get("tags", []),
            confidence=entity.get("confidence"),
            project=project,
            aliases=entity.get("aliases", []),
            source_type=source_type,
            source_id=source_id,
            source_video_ids=source_video_ids,
            generated_by=generated_by,
        )
        return "created"

    def _link_to_project(self, project: str, analyses: list[dict[str, Any]]) -> None:
        """Link extracted knowledge to the project note."""
        project_note = self.knowledge_service.get_note_by_title(project)
        if not project_note:
            return

        related_titles = []
        for analysis in analyses:
            topic = analysis.get("main_topic") or analysis.get("topic")
            if topic:
                related_titles.append(self._title_case(topic) if isinstance(topic, str) else str(topic))
            hook = analysis.get("hook_type")
            if hook:
                related_titles.append(f"{self._title_case(hook)} Hook Pattern")
            emotion = analysis.get("emotion")
            if emotion:
                related_titles.append(f"Emotional Trigger: {self._title_case(emotion)}")

        if related_titles:
            self.knowledge_service.link_notes(project, related_titles)

    # ------------------------------------------------------------------
    # Content builders
    # ------------------------------------------------------------------

    def _build_concept_content(self, analysis: dict[str, Any]) -> str:
        """Build concept note content from analysis."""
        parts = ["## Definition", ""]
        opening = analysis.get("opening_summary") or analysis.get("summary") or ""
        if opening:
            parts.append(str(opening))
        else:
            parts.append("(No definition available)")
        topic = analysis.get("main_topic") or analysis.get("topic")
        if topic:
            video_ids = self._collect_source_video_ids([analysis])
            if video_ids:
                parts.extend(["", "## Observed In", ""])
                for vid in video_ids[:10]:
                    parts.append(f"- Source video: {vid}")
        return "\n".join(parts)

    def _build_hook_content(self, analysis: dict[str, Any]) -> str:
        """Build hook pattern content."""
        hook = analysis.get("hook_type", "")
        opening = analysis.get("opening_summary", "")
        parts = [
            "## Pattern",
            "",
            f"{hook} hooks are used to capture attention.",
        ]
        if opening:
            parts.extend(["", "## Example Opening", "", str(opening)])
        return "\n".join(parts)

    def _build_retention_content(self, analysis: dict[str, Any], technique: str) -> str:
        """Build retention technique content."""
        return (
            f"## Technique\n\n{technique}\n\n"
            f"## Evidence\n\nObserved as an effective retention technique in analyzed videos."
        )

    def _build_emotion_content(self, analysis: dict[str, Any], emotion: str) -> str:
        """Build emotional trigger content."""
        return (
            f"## Emotional Trigger\n\n{emotion}\n\n"
            f"## Evidence\n\nObserved as a psychological trigger in analyzed videos."
        )

    def _build_story_content(self, analysis: dict[str, Any], story: str) -> str:
        """Build story structure content."""
        return (
            f"## Story Structure\n\n{story}\n\n"
            f"## Evidence\n\nObserved as an effective narrative structure in analyzed videos."
        )

    def _build_title_content(self, analysis: dict[str, Any], formula: str) -> str:
        """Build title formula content."""
        return (
            f"## Title Formula\n\n{formula}\n\n"
            f"## Evidence\n\nObserved as an effective title pattern in analyzed videos."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _analysis_confidence(self, analysis: dict[str, Any]) -> float | None:
        """Extract confidence from analysis data."""
        raw = analysis.get("confidence_score") or analysis.get("confidence")
        try:
            value = float(raw) if raw is not None else 0.5
        except (TypeError, ValueError):
            return 0.5
        return max(0.0, min(1.0, value))

    def _collect_source_video_ids(self, analyses: list[dict[str, Any]]) -> list[str]:
        """Collect source video IDs from a list of analyses."""
        video_ids: list[str] = []
        for analysis in analyses:
            vid = analysis.get("video_id")
            if vid and isinstance(vid, str) and vid not in video_ids:
                video_ids.append(vid)
        return video_ids

    def _title_case(self, text: str) -> str:
        """Convert a raw title to title case."""
        words = text.split()
        title_words = []
        skip = {"a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of"}
        for i, word in enumerate(words):
            if i == 0 or word.lower() not in skip:
                title_words.append(word[:1].upper() + word[1:] if word else word)
            else:
                title_words.append(word)
        return " ".join(title_words)

    def _generate_aliases(self, title: str) -> list[str]:
        """Generate conservative aliases for a title.

        Only generates aliases that are near-certain variations:
        - Lowercase version
        - Lowercase version with hyphens replaced by spaces
        """
        aliases = []
        lowered = title.lower().strip()
        if lowered != title:
            aliases.append(lowered)
        hyphenated = re.sub(r"\s+", "-", lowered)
        if hyphenated != lowered and hyphenated != title:
            aliases.append(hyphenated)
        return list(set(aliases))

    def _as_list(self, value: Any) -> list[Any]:
        """Convert scalar or list to a list."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                import ast
                parsed = ast.literal_eval(value)
                if isinstance(parsed, list):
                    return parsed
            except (ValueError, SyntaxError):
                pass
            return [item.strip() for item in value.split(",") if item.strip()]
        return [value] if value is not None else []

    def _evidence_marker(self, source_id: str, source_video_ids: list[str]) -> str:
        """Build a compact evidence block for provenance."""
        lines = ["> **Evidence source:**"]
        vid_line = ",".join(source_video_ids[:5]) if source_video_ids else "unknown"
        lines.append(f"> - Batch: `{source_id}` | Videos: `{vid_line}`")
        return "\n".join(lines)