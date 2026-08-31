"""Composition Decision Layer (V1.4-C).

Deterministic, pure, standalone planning service that decides how each scene
should be visually composed based on existing scene structure, V1.4-A story
decisions, and V1.4-B diversity analysis.

This is an advisory-only planning layer that does not modify any inputs,
invoke the production pipeline, or make any external calls.

It builds on V1.4-A `VisualStoryPlanner` and V1.4-B `VisualDiversityPolicy`
and reuses the existing beat/treatment/focus vocabularies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS
from src.models.content_package import SUPPORTED_MOTION_TYPES, SUPPORTED_TRANSITION_TYPES
from src.services.visual_beat_engine import SUPPORTED_BEAT_TYPES
from src.pipeline.auto_publish_pipeline import ScenePlan, VisualScene
from src.services.visual_story_planner import VisualStoryPlan, SUPPORTED_TREATMENTS
from src.services.visual_diversity import VisualDiversityReport


# Re-export for test convenience
__all__ = [
    "CompositionDecision",
    "CompositionPlan",
    "CompositionPlanner",
    "SUPPORTED_COMPOSITION_TYPES",
    "SUPPORTED_REGIONS",
    "SUPPORTED_SCALES",
    "SUPPORTED_ALIGNMENTS",
]


# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------

SUPPORTED_COMPOSITION_TYPES = {
    "single_subject",
    "subject_support",
    "comparison",
    "text_led",
    "object_led",
    "problem_focus",
    "solution_result",
}

SUPPORTED_REGIONS = {
    "center",
    "left",
    "right",
    "upper",
    "lower",
    "left_center",
    "right_center",
    "upper_left",
    "upper_right",
    "lower_left",
    "lower_right",
}

SUPPORTED_SCALES = {
    "small",
    "medium",
    "large",
}

SUPPORTED_ALIGNMENTS = {
    "center",
    "left",
    "right",
}


# ---------------------------------------------------------------------------
# Deterministic composition rules
# ---------------------------------------------------------------------------

# Beat/treatment -> preferred composition type
_BEAT_COMPOSITION: dict[str, str] = {
    "HOOK": "single_subject",
    "PROBLEM": "problem_focus",
    "CONTRAST": "comparison",
    "EXPLANATION": "subject_support",
    "EXAMPLE": "object_led",
    "SOLUTION": "solution_result",
    "CTA": "text_led",
}

_TREATMENT_COMPOSITION: dict[str, str] = {
    "establish": "single_subject",
    "problem_focus": "problem_focus",
    "compare": "comparison",
    "explain": "subject_support",
    "proof": "object_led",
    "solution_growth": "solution_result",
    "cta": "text_led",
}

# Composition type -> (primary_region, secondary_region, text_region)
_COMPOSITION_LAYOUT: dict[str, tuple[str, str | None, str | None]] = {
    "single_subject": ("center", None, None),
    "subject_support": ("center", "lower", None),
    "comparison": ("left_center", "right_center", None),
    "text_led": ("center", None, "upper"),
    "object_led": ("center", None, None),
    "problem_focus": ("center", None, None),
    "solution_result": ("center", "upper", None),
}

# Alternative layouts for diversity (when repetition detected)
_COMPOSITION_ALTERNATIVE_LAYOUT: dict[str, tuple[str, str | None, str | None]] = {
    "single_subject": ("upper", None, None),
    "subject_support": ("left_center", "right_center", None),
    "comparison": ("right_center", "left_center", None),
    "text_led": ("center", None, "lower"),
    "object_led": ("upper", None, None),
    "problem_focus": ("left_center", None, None),
    "solution_result": ("center", "lower", None),
}

# Composition type -> recommended scale
_COMPOSITION_SCALE: dict[str, str] = {
    "single_subject": "large",
    "subject_support": "medium",
    "comparison": "medium",
    "text_led": "large",
    "object_led": "large",
    "problem_focus": "medium",
    "solution_result": "large",
}

# Composition type -> recommended alignment
_COMPOSITION_ALIGNMENT: dict[str, str] = {
    "single_subject": "center",
    "subject_support": "center",
    "comparison": "center",
    "text_led": "center",
    "object_led": "center",
    "problem_focus": "center",
    "solution_result": "center",
}


def _normalize(value: str) -> str:
    """Normalize a string for comparison (lowercase, strip)."""
    return str(value or "").strip().lower()


def _count_subjects(scene: ScenePlan) -> dict[str, int]:
    """Count visual subjects in a scene (characters, objects, text)."""
    counts = {"character": 0, "object": 0, "text": 0}
    visual = scene.visual
    if visual is None:
        return counts
    
    counts["character"] = len(getattr(visual, "characters", []) or [])
    counts["object"] = len(getattr(visual, "objects", []) or [])
    counts["text"] = len(getattr(visual, "text_elements", []) or [])
    return counts


def _has_explicit_positioning(scene: ScenePlan) -> bool:
    """Check if scene has explicit positioning intent."""
    visual = scene.visual
    if visual is None:
        return False
    
    # Check for explicit character positions
    characters = getattr(visual, "characters", []) or []
    for char in characters:
        if isinstance(char, dict):
            if char.get("x") is not None or char.get("y") is not None:
                return True
        else:
            if getattr(char, "x", None) is not None or getattr(char, "y", None) is not None:
                return True
    
    # Check for explicit object positions
    objects = getattr(visual, "objects", []) or []
    for obj in objects:
        if isinstance(obj, dict):
            if obj.get("x") is not None or obj.get("y") is not None:
                return True
        else:
            if getattr(obj, "x", None) is not None or getattr(obj, "y", None) is not None:
                return True
    
    # Check for explicit text positions
    text_elements = getattr(visual, "text_elements", []) or []
    for text in text_elements:
        if isinstance(text, dict):
            if text.get("x") is not None or text.get("y") is not None:
                return True
        else:
            if getattr(text, "x", None) is not None or getattr(text, "y", None) is not None:
                return True
    
    return False


def _get_beat_type(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract beat type from scene role or story decision."""
    visual = scene.visual
    if visual is not None:
        role = getattr(visual, "scene_role", "")
        if role:
            role_to_beat = {
                "hook": "HOOK",
                "problem": "PROBLEM",
                "contrast": "CONTRAST",
                "explanation": "EXPLANATION",
                "example": "EXAMPLE",
                "solution": "SOLUTION",
                "cta": "CTA",
            }
            normalized = _normalize(role)
            if normalized in role_to_beat:
                return role_to_beat[normalized]
    if story_decision is not None:
        beat = getattr(story_decision, "beat_type", "")
        if beat:
            return beat
    return ""


def _get_treatment(scene: ScenePlan, story_decision: Any | None) -> str:
    """Extract treatment from story decision or infer from beat."""
    if story_decision is not None:
        treatment = getattr(story_decision, "treatment", "")
        if treatment:
            return _normalize(treatment)
    return ""


def _classify_composition(
    scene: ScenePlan,
    beat_type: str,
    treatment: str,
    subject_counts: dict[str, int],
) -> str:
    """Classify the composition type based on scene content and story context."""
    total_subjects = subject_counts["character"] + subject_counts["object"]
    has_text = subject_counts["text"] > 0
    
    # Priority: treatment > beat > content-based classification
    
    # If treatment is available, use it
    if treatment and treatment in _TREATMENT_COMPOSITION:
        return _TREATMENT_COMPOSITION[treatment]
    
    # If beat type is available, use it
    if beat_type and beat_type in _BEAT_COMPOSITION:
        return _BEAT_COMPOSITION[beat_type]
    
    # Content-based fallback classification
    if total_subjects == 0 and has_text:
        return "text_led"
    if total_subjects == 1:
        return "single_subject"
    if total_subjects >= 2:
        return "subject_support"
    
    # Safe fallback
    return "single_subject"


def _get_layout(
    composition_type: str,
    previous_composition: str,
    run_count: int,
) -> tuple[str, str | None, str | None]:
    """Get the layout regions for a composition type.
    
    If repetition is detected (run_count >= 2), use alternative layout.
    """
    if run_count >= 2 and composition_type in _COMPOSITION_ALTERNATIVE_LAYOUT:
        return _COMPOSITION_ALTERNATIVE_LAYOUT[composition_type]
    return _COMPOSITION_LAYOUT.get(composition_type, ("center", None, None))


def _get_scale(composition_type: str) -> str:
    """Get the recommended scale for a composition type."""
    return _COMPOSITION_SCALE.get(composition_type, "medium")


def _get_alignment(composition_type: str) -> str:
    """Get the recommended alignment for a composition type."""
    return _COMPOSITION_ALIGNMENT.get(composition_type, "center")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompositionDecision:
    """Analysis and recommendations for a single scene's visual composition."""

    scene_index: int
    composition_type: str
    primary_region: str
    secondary_region: str | None
    text_region: str | None
    subject_regions: tuple[str, ...]
    recommended_scale: str
    recommended_alignment: str
    repeated_with_previous: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class CompositionPlan:
    """Immutable sequence-level composition planning report."""

    decisions: tuple[CompositionDecision, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "decisions": [decision.to_dict() for decision in self.decisions],
            "warnings": list(self.warnings),
        }


# ---------------------------------------------------------------------------
# Main planner class
# ---------------------------------------------------------------------------


class CompositionPlanner:
    """Deterministic composition planning for scene sequences.
    
    Analyzes a sequence of scenes (and optionally a VisualStoryPlan and
    VisualDiversityReport) to recommend how each scene should be visually
    composed using only supported vocabulary values.
    
    This service is pure and read-only - it never mutates inputs.
    """

    def plan(
        self,
        scenes: list[ScenePlan],
        *,
        story_plan: VisualStoryPlan | None = None,
        diversity_report: VisualDiversityReport | None = None,
    ) -> CompositionPlan:
        """Analyze a sequence of scenes for composition planning.
        
        Args:
            scenes: List of ScenePlan objects to analyze.
            story_plan: Optional VisualStoryPlan from V1.4-A for derived values.
            diversity_report: Optional VisualDiversityReport from V1.4-B.
        
        Returns:
            CompositionPlan with per-scene decisions and sequence warnings.
        """
        if not scenes:
            return CompositionPlan(decisions=(), warnings=())
        
        # Build lookup dictionaries
        story_decisions: dict[int, Any] = {}
        if story_plan is not None:
            for decision in story_plan.decisions:
                story_decisions[decision.scene_index] = decision
        
        diversity_decisions: dict[int, Any] = {}
        if diversity_report is not None:
            for decision in diversity_report.decisions:
                diversity_decisions[decision.scene_index] = decision
        
        decisions: list[CompositionDecision] = []
        sequence_warnings: list[str] = []
        
        # Track composition runs for repetition detection
        composition_run: dict[str, int] = {}
        prev_composition = ""
        
        for i, scene in enumerate(scenes):
            story_decision = story_decisions.get(i)
            
            # Extract context
            beat_type = _get_beat_type(scene, story_decision)
            treatment = _get_treatment(scene, story_decision)
            subject_counts = _count_subjects(scene)
            has_explicit = _has_explicit_positioning(scene)
            
            # Classify composition
            composition_type = _classify_composition(
                scene, beat_type, treatment, subject_counts
            )
            
            # Update run counter
            if composition_type:
                composition_run[composition_type] = composition_run.get(composition_type, 0) + 1
                for k in list(composition_run.keys()):
                    if k != composition_type:
                        composition_run[k] = 0
            else:
                composition_run.clear()
            
            # Detect repetition
            repeated_with_previous = (
                composition_type == prev_composition and composition_type != ""
            )
            run_count = composition_run.get(composition_type, 0)
            
            # Get layout (with diversity awareness)
            primary_region, secondary_region, text_region = _get_layout(
                composition_type, prev_composition, run_count
            )
            
            # Build subject regions
            subject_regions_list: list[str] = []
            if subject_counts["character"] > 0:
                subject_regions_list.append("character")
            if subject_counts["object"] > 0:
                subject_regions_list.append("object")
            if subject_counts["text"] > 0:
                subject_regions_list.append("text")
            
            # Build warnings
            warnings: list[str] = []
            
            if has_explicit:
                warnings.append("explicit_composition_preserved")
            
            if repeated_with_previous:
                warnings.append(f"repeated_composition:{composition_type}")
            
            if run_count >= 3:
                warnings.append(f"composition_run:{composition_type}:{run_count}")
            
            # Get scale and alignment
            recommended_scale = _get_scale(composition_type)
            recommended_alignment = _get_alignment(composition_type)
            
            decision = CompositionDecision(
                scene_index=i,
                composition_type=composition_type,
                primary_region=primary_region,
                secondary_region=secondary_region,
                text_region=text_region,
                subject_regions=tuple(subject_regions_list),
                recommended_scale=recommended_scale,
                recommended_alignment=recommended_alignment,
                repeated_with_previous=repeated_with_previous,
                warnings=tuple(warnings),
            )
            decisions.append(decision)
            
            prev_composition = composition_type
        
        # Sequence-level warnings
        if len(scenes) >= 3:
            compositions_used = {d.composition_type for d in decisions if d.composition_type}
            if len(compositions_used) <= 1:
                sequence_warnings.append("low_composition_diversity")
        
        return CompositionPlan(
            decisions=tuple(decisions),
            warnings=tuple(sequence_warnings),
        )