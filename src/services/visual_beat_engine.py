"""Visual Beat Engine (V1.3-A).

Transforms narration plus available semantic signals into a deterministic
sequence of :class:`VisualBeat` values that future V1.3 layers (Visual Focus,
Semantic Motion, Semantic Transitions, Visual QA) can consume.

This is a *pure semantic service*.  It must stay independent of rendering:

- It does NOT import StickmanRenderer, FFmpeg, or any render model.
- It does NOT mutate VisualScene / RenderJobSpec / MotionIntent / Transition /
  SceneComposition.
- It performs no LLM calls, network calls, or randomness.

The same inputs always produce the same beats (deterministic first).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


# ---------------------------------------------------------------------------
# Vocabulary constants (mirrors the uppercase-set style used across the repo)
# ---------------------------------------------------------------------------

SUPPORTED_BEAT_TYPES = {
    "HOOK",
    "PROBLEM",
    "CONTRAST",
    "EXPLANATION",
    "EXAMPLE",
    "SOLUTION",
    "CTA",
}

# Importance in 0..1 and an emphasis label for every supported beat.
BEAT_IMPORTANCE: dict[str, float] = {
    "HOOK": 0.95,
    "PROBLEM": 0.9,
    "CONTRAST": 0.85,
    "SOLUTION": 0.85,
    "CTA": 0.9,
    "EXPLANATION": 0.6,
    "EXAMPLE": 0.5,
}

BEAT_EMPHASIS: dict[str, str] = {
    "HOOK": "high",
    "PROBLEM": "high",
    "CONTRAST": "high",
    "SOLUTION": "high",
    "CTA": "high",
    "EXPLANATION": "medium",
    "EXAMPLE": "low",
}

# Existing VisualScene.scene_role (lowercase) -> canonical beat type.
# Roles with no clear semantic mapping (e.g. "general", "object_interaction",
# "character_action", "camera_focus") fall through to position/keyword rules.

# Curated, high-signal keyword tuples (deliberately small to avoid uncontrolled
# accumulation -- the same philosophy as ContentGenerationService intents).
_HOOK_KEYWORDS = (
    "did you know", "what if", "opening", "intro", "hook",
    "start here", "the truth", "imagine this", "imagine you",
)
_PROBLEM_KEYWORDS = (
    "problem", "issue", "trouble", "fails", "struggle", "difficulty",
    "downside", "hurts", "warning",
)
_CONTRAST_KEYWORDS = (
    "but", "however", "versus", " vs ", "compared", "unlike", "whereas",
    "on the other hand", "doesn't mean", "does not mean", "isn't the same",
    "is not the same", "does not equal",
)
_EXAMPLE_KEYWORDS = (
    "for example", "for instance", "such as", "example", "case study",
    "imagine if", "imagine a", "picture this",
)
_SOLUTION_KEYWORDS = (
    "solution", "solve", "fix", "answer", "instead", "tip", "step",
    "try this", "strategy",
)
_CTA_KEYWORDS = (
    "subscribe", "comment", "like this", "share", "follow",
    "try it today", "start today", "call to action",
)
_EXPLANATION_KEYWORDS = (
    "because", "this means", "that's why", "the reason", "in other words",
    "works because", "here's how", "mechanism",
)

# Keyword-stage precedence: earlier beats win when several match.
_KEYWORD_PRIORITY: list[tuple[str, tuple[str, ...]]] = [
    ("HOOK", _HOOK_KEYWORDS),
    ("CTA", _CTA_KEYWORDS),
    ("PROBLEM", _PROBLEM_KEYWORDS),
    ("SOLUTION", _SOLUTION_KEYWORDS),
    ("CONTRAST", _CONTRAST_KEYWORDS),
    ("EXAMPLE", _EXAMPLE_KEYWORDS),
    ("EXPLANATION", _EXPLANATION_KEYWORDS),
]

# Analysis.story_structure hints used only when narration is weak/empty.
_STORY_STRUCTURE_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("HOOK", ("hook", "opening", "intrigue", "teaser")),
    ("PROBLEM", ("problem", "issue", "conflict", "challenge")),
    ("SOLUTION", ("solution", "resolution", "answer", "fix")),
    ("CONTRAST", ("contrast", "comparison", "compare", "before", "after")),
    ("EXAMPLE", ("example", "case", "story")),
    ("CTA", ("cta", "call to action", "subscribe", "closing")),
]

_SUBJECT_STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "you", "your", "more", "it", "that",
    "this", "when", "with", "than", "from", "and", "but", "how", "what", "why",
}

# Small domain map for recall-style topics (kept minimal; otherwise the word is
# used verbatim as the topic token).
_TOPIC_SYNONYMS = {
    "remember": "memory",
    "remembering": "memory",
    "recall": "memory",
    "studying": "study",
    "learning": "learning",
}


@dataclass
class VisualBeat:
    """A single deterministic visual beat.

    Independent of rendering.  ``importance`` is a score in ``0..1`` and
    ``emphasis`` is a low/medium/high label (matching the project's energy
    string convention).  ``subject`` is the best-effort focal subject or ``""``
    when it cannot be extracted confidently (never hallucinated).
    """

    type: str
    subject: str = ""
    importance: float = 0.5
    emphasis: str = "medium"

    def __post_init__(self) -> None:
        self.type = str(self.type).strip().upper()
        if self.type not in SUPPORTED_BEAT_TYPES:
            raise ValueError(f"unknown beat type: {self.type}")
        self.subject = str(self.subject or "").strip()
        self.importance = max(0.0, min(1.0, float(self.importance)))
        self.emphasis = str(self.emphasis).strip().lower() or "medium"
        if self.emphasis not in {"low", "medium", "high"}:
            raise ValueError(f"invalid emphasis: {self.emphasis}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)

SCENE_ROLE_BEATS: dict[str, str] = {
    "hook": "HOOK",
    "problem": "PROBLEM",
    "contrast": "CONTRAST",
    "comparison": "CONTRAST",
    "explanation": "EXPLANATION",
    "example": "EXAMPLE",
    "solution": "SOLUTION",
    "method": "SOLUTION",
    "cta": "CTA",
    "proof": "CONTRAST",   # proof scenes surface measurable contrast/change
    "b_roll": "EXAMPLE",   # b-roll/example footage illustrates the point
}

class VisualBeatEngine:
    """Deterministic narration -> VisualBeat detector.

    Detection priority (in order):
      1. Explicit ``scene_role`` metadata
      2. Scene position (first -> HOOK, last -> CTA)
      3. Strong semantic keywords in narration
      4. ``Analysis.story_structure`` (only when narration is weak/empty)
      5. Fallback EXPLANATION
    """

    # -- Public API ---------------------------------------------------------

    def detect(
        self,
        narration: str = "",
        *,
        scene_index: int = 0,
        total_scenes: int = 1,
        scene_role: str = "",
        analysis: Any = None,
    ) -> VisualBeat:
        """Return a single :class:`VisualBeat` for one scene.

        ``analysis`` may be an ``Analysis`` dataclass, a dict, or ``None``.
        Every optional field is guarded so malformed/missing data degrades
        gracefully to narration-only operation.
        """
        text = " ".join((narration or "").split())
        low = text.lower()
        role = (scene_role or "").strip().lower()

        beat_type: str | None = None

        # 1. Explicit scene_role metadata wins over everything.
        if role:
            beat_type = SCENE_ROLE_BEATS.get(role)

        # 2. Scene position fallback.
        if beat_type is None:
            if scene_index <= 0:
                beat_type = "HOOK"
            elif scene_index >= total_scenes - 1:
                beat_type = "CTA"

        # 3. Strong semantic keywords (only when narration is present).
        if beat_type is None and low:
            beat_type = self._match_keywords(low)

        # 4. Analysis.story_structure -- only when narration offered no beat.
        if beat_type is None:
            story = self._analysis_field(analysis, "story_structure")
            beat_type = self._match_story_structure(story)

        # 5. Deterministic fallback.
        if beat_type is None:
            beat_type = "EXPLANATION"

        subject = self._extract_subject(text, low, beat_type, analysis)

        return VisualBeat(
            type=beat_type,
            subject=subject,
            importance=BEAT_IMPORTANCE[beat_type],
            emphasis=BEAT_EMPHASIS[beat_type],
        )

    def detect_sequence(
        self,
        scenes: list[Any],
        *,
        analysis: Any = None,
    ) -> list[VisualBeat]:
        """Detect beats for an ordered list of scenes.

        Each item may be a ``str`` (narration only) or a dict with ``narration``
        and/or ``scene_role`` fields.  ``analysis`` may be a single value applied
        to every scene, or a list aligned with ``scenes``.
        """
        total = len(scenes)
        analysis_list = analysis if isinstance(analysis, list) else None
        results: list[VisualBeat] = []
        for i, scene in enumerate(scenes):
            if isinstance(scene, dict):
                narration = str(scene.get("narration", "") or "")
                role = str(scene.get("scene_role", "") or "")
            else:
                narration = str(scene or "")
                role = ""
            scene_analysis = (
                analysis_list[i] if analysis_list is not None else analysis
            )
            results.append(
                self.detect(
                    narration,
                    scene_index=i,
                    total_scenes=total,
                    scene_role=role,
                    analysis=scene_analysis,
                )
            )
        return results


    # -- Detection helpers --------------------------------------------------

    @staticmethod
    def _analysis_field(analysis: Any, name: str) -> str:
        """Read an optional field from an Analysis/dict/None safely."""
        if analysis is None:
            return ""
        if isinstance(analysis, dict):
            value = analysis.get(name, "")
        else:
            value = getattr(analysis, name, "")
        return "" if value is None else str(value)

    @staticmethod
    def _match_keywords(low: str) -> str | None:
        for beat_type, keywords in _KEYWORD_PRIORITY:
            if any(kw in low for kw in keywords):
                return beat_type
        return None

    @staticmethod
    def _match_story_structure(story: str) -> str | None:
        story = " ".join(story.split()).lower()
        if not story:
            return None
        for beat_type, hints in _STORY_STRUCTURE_HINTS:
            if any(h in story for h in hints):
                return beat_type
        return None

    # -- Subject extraction --------------------------------------------------

    def _extract_subject(
        self,
        text: str,
        low: str,
        beat_type: str,
        analysis: Any,
    ) -> str:
        """Best-effort, conservative subject extraction (never hallucinated)."""
        subject = ""
        if beat_type == "CONTRAST":
            subject = self._contrast_subject(text, low)
        elif beat_type in {"PROBLEM", "SOLUTION"}:
            subject = self._clause_subject(low)
        if not subject:
            topic = self._analysis_field(analysis, "main_topic")
            if topic:
                subject = self._words(topic, 5)
        return subject

    @staticmethod
    def _words(phrase: str, limit: int) -> str:
        tokens = [t.strip(".,;:!?()\"'") for t in phrase.split()]
        tokens = [t for t in tokens if t]
        return " ".join(tokens[:limit])

    def _contrast_subject(self, text: str, low: str) -> str:
        # Explicit "A vs B" / "A versus B".
        m = re.search(
            r"\b([a-z0-9][\w ]{1,20}?)\s+vs\.?\s+([a-z0-9][\w ]{1,20}?)(?:[.,\s]|$)",
            low,
        )
        if m:
            a = self._topic_token(m.group(1))
            b = self._topic_token(m.group(2))
            if a and b:
                return f"{a} vs {b}"

        # "Studying longer doesn't mean you remember more."
        m = re.search(
            r"([a-z0-9][\w ]{1,24}?)\s+(?:doesn't|does not|isn't|is not|won't)"
            r"\s+(?:mean|equal|the same as)\s+"
            r"([a-z0-9][\w ]{1,40}?)(?:[.!?;]|$)",
            low,
        )
        if m:
            a = self._topic_token(m.group(1))
            b = self._topic_token(m.group(2))
            if a and b:
                return f"{a} vs {b}"
        return ""

    def _clause_subject(self, low: str) -> str:
        # "The problem is that focus drops ..." -> "focus".
        m = re.search(
            r"(?:the\s+)?(?:main\s+)?(?:problem|issue|trouble|solution|answer)"
            r"\s+is\s+(?:that\s+)?([a-z][\w ]{1,6}?)"
            r"(?:\s+(?:drops|falls|is|are|gets|increases|rises|means|starts)"
            r"|\s+(?:after|when|with|by|that|in)\b|[,.])",
            low,
        )
        if m:
            return self._words(m.group(1), 3)
        # "problem with focus", "issue of attention".
        m = re.search(
            r"\b(?:problem|issue|trouble)\s+(?:with|of|in)\s+"
            r"([a-z][\w ]{1,6}?)(?:\s[a-z]+(?:[,.$]|\b)?|[,.])",
            low,
        )
        if m:
            return self._words(m.group(1), 3)
        return ""

    @classmethod
    def _topic_token(cls, phrase: str) -> str:
        """Reduce a noun phrase to its most salient single topic token."""
        tokens = [
            t.strip(".,;:!?()\"'")
            for t in phrase.split()
            if t.strip(".,;:!?()\"'")
        ]
        core = [t for t in tokens if t not in _SUBJECT_STOPWORDS] or tokens
        if not core:
            return ""
        word = core[0].lower()
        word = _TOPIC_SYNONYMS.get(word, word)
        if word.endswith("ing") and len(word) > 5:
            word = word[:-3]
        return word

