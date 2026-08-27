"""Pure semantic fallback resolution for adjacent visual beats."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.models.content_package import SUPPORTED_TRANSITION_TYPES, Transition
from src.services.visual_beat_engine import SUPPORTED_BEAT_TYPES


@dataclass(frozen=True)
class SemanticTransitionInput:
    """Serializable pair of adjacent beats used for transition resolution."""

    left_beat: Any
    right_beat: Any

    def to_dict(self) -> dict[str, Any]:
        def serialize(value: Any) -> Any:
            if hasattr(value, "to_dict"):
                return value.to_dict()
            if hasattr(value, "__dataclass_fields__"):
                return asdict(value)
            return value

        return {"left_beat": serialize(self.left_beat), "right_beat": serialize(self.right_beat)}


class SemanticTransitionResolver:
    """Resolve only confident relationships into existing transitions."""

    def resolve(self, left_beat: Any, right_beat: Any) -> Transition | None:
        left_type = self._beat_type(left_beat)
        right_type = self._beat_type(right_beat)
        if left_type not in SUPPORTED_BEAT_TYPES or right_type not in SUPPORTED_BEAT_TYPES:
            return None

        relationship = self._relationship(left_beat, right_beat)
        if relationship in {"continuation", "same", "same_beat"}:
            return self._cut()
        if relationship in {"contrast", "comparison"}:
            return self._slide("slide_left")
        if relationship in {"cause_effect", "cause_to_effect", "cause->effect"}:
            return self._crossfade("smooth")
        if relationship in {"before_after", "before->after"}:
            return self._crossfade("smooth")
        if relationship == "reveal":
            return self._fade()
        if relationship == "escalation":
            return self._slide("slide_up")

        if left_type == "CONTRAST" or right_type == "CONTRAST":
            return self._slide("slide_left")
        if left_type == right_type:
            return self._cut()
        if left_type == "PROBLEM" and right_type == "SOLUTION":
            return self._slide("slide_up")
        if left_type == "EXPLANATION" and right_type == "EXAMPLE":
            return self._crossfade("soft")
        return None

    @staticmethod
    def _beat_type(beat: Any) -> str:
        if beat is None:
            return ""
        value = beat.get("type") if isinstance(beat, dict) else getattr(beat, "type", "")
        return str(value or "").strip().upper()

    @classmethod
    def _relationship(cls, left: Any, right: Any) -> str:
        for beat in (right, left):
            value = cls._metadata_value(beat)
            if value:
                return cls._normalize(value)
        return ""

    @staticmethod
    def _metadata_value(beat: Any) -> str:
        if beat is None:
            return ""
        keys = ("semantic_relationship", "relationship", "relation", "transition_relationship")
        if isinstance(beat, dict):
            for key in keys:
                value = beat.get(key)
                if value:
                    return str(value)
            metadata = beat.get("metadata")
        else:
            for key in keys:
                value = getattr(beat, key, None)
                if value:
                    return str(value)
            metadata = getattr(beat, "metadata", None)
        if isinstance(metadata, dict):
            for key in keys:
                value = metadata.get(key)
                if value:
                    return str(value)
        return ""

    @staticmethod
    def _normalize(value: str) -> str:
        return "_".join(str(value).strip().lower().replace("->", " -> ").split()).replace("_->_", "->")

    @staticmethod
    def _cut() -> Transition:
        return Transition(type="cut", duration=0.0, parameters={})

    @staticmethod
    def _crossfade(curve: str) -> Transition:
        return Transition(type="crossfade", duration=0.25, parameters={"curve": curve})

    @staticmethod
    def _fade() -> Transition:
        return Transition(type="fade", duration=0.25, parameters={"from": "scene", "to": "scene"})

    @staticmethod
    def _slide(transition_type: str) -> Transition:
        if transition_type not in SUPPORTED_TRANSITION_TYPES:
            return SemanticTransitionResolver._cut()
        return Transition(type=transition_type, duration=0.35, parameters={"distance": 0.15})
