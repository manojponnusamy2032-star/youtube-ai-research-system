"""Attention Continuity Planner (V1.4-E).

Deterministic, pure, standalone planning service that plans *visual attention
continuity* across a complete scene sequence:

    What should the viewer be looking at, scene by scene, and how does that
    attention flow from one scene into the next?

The planner determines the primary/secondary attention target per scene,
tracks retention / shift / introduction / return / loss of targets across
adjacent scenes, flags abrupt transitions, and emits deterministic warnings
when continuity is weak.

This is an advisory-only planning layer. It does NOT modify any inputs,
invoke the production pipeline, make external calls, or render anything.

It builds on V1.3-B `VisualFocusResolver` results (when supplied) and the
V1.4-A/B/C/D planning outputs, and it never invents a target identifier:
every resolved target must trace back to an existing scene element or the
safe scene-level fallback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.pipeline.auto_publish_pipeline import ScenePlan
from src.services.visual_focus import VisualFocus
from src.services.visual_story_planner import VisualStoryPlan, SUPPORTED_TREATMENTS
from src.services.visual_diversity import VisualDiversityReport
from src.services.composition_planner import CompositionPlan, SUPPORTED_COMPOSITION_TYPES


# Re-export for test convenience
__all__ = [
    "AttentionDecision",
    "AttentionPlan",
    "AttentionPlanner",
    "SUPPORTED_TARGET_KINDS",
    "SUPPORTED_HANDOFF_STATES",
    "SUPPORTED_TREATMENTS",
    "SUPPORTED_COMPOSITION_TYPES",
]


# ---------------------------------------------------------------------------
# Vocabulary constants
# ---------------------------------------------------------------------------

SUPPORTED_TARGET_KINDS = {
    "character",
    "object",
    "text",
    "scene",
}

SUPPORTED_HANDOFF_STATES = {
    "established",
    "retained",
    "shifted",
    "introduced",
    "returned",
    "lost",
    "fallback",
}

# Safe scene-level fallback target (a category, not an invented identifier).
_SCENE_TARGET = "scene"

# VisualScene default primary_focus value == no explicit intent.
_NO_INTENT_FOCUS = "scene"


# ---------------------------------------------------------------------------
# Treatment-aware kind preference (V1.4-A). Ordered most-to-least preferred.
# ---------------------------------------------------------------------------

_TREATMENT_PREFERRED_KINDS: dict[str, tuple[str, ...]] = {
    "establish": ("character", "object", "text"),
    "problem_focus": ("character", "object", "text"),
    "compare": ("character", "object", "text"),
    "explain": ("object", "text", "character"),
    "proof": ("object", "text", "character"),
    "solution_growth": ("object", "character", "text"),
    "cta": ("text", "character", "object"),
}


# ---------------------------------------------------------------------------
# Composition-aware kind preference (V1.4-C). Ordered most-to-least preferred.
# ---------------------------------------------------------------------------

_COMPOSITION_PREFERRED_KINDS: dict[str, tuple[str, ...]] = {
    "single_subject": ("character", "object", "text"),
    "subject_support": ("character", "object", "text"),
    "comparison": ("character", "object", "text"),
    "text_led": ("text", "character", "object"),
    "object_led": ("object", "character", "text"),
    "problem_focus": ("character", "object", "text"),
    "solution_result": ("object", "character", "text"),
}

# Compositions that legitimately carry a primary + secondary target.
_DUAL_TARGET_COMPOSITIONS = {"comparison", "subject_support"}

# V1.4-D camera focus patterns restrict the target kind.
_CAMERA_PATTERN_KIND: dict[str, str] = {
    "focus_on_character": "character",
    "focus_on_object": "object",
}
# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _normalize(value: str) -> str:
    """Normalize a string for comparison (lowercase, strip)."""
    return str(value or "").strip().lower()


def _field(elem: Any, name: str) -> Any:
    """Read a field from a dict or a dataclass attribute."""
    if isinstance(elem, dict):
        return elem.get(name)
    return getattr(elem, name, None)


def _element_name(elem: Any, field: str) -> str:
    """Extract the display identifier of a scene element."""
    value = _field(elem, field)
    return str(value or "").strip()


def _gather_ordered_subjects(scene: ScenePlan) -> list[tuple[str, str]]:
    """Return (name, kind) for characters, then objects, then text elements.

    This is the "existing scene subject ordering" used as a deterministic
    tie-breaker. Names are canonical (they already exist on the scene).
    """
    ordered: list[tuple[str, str]] = []
    visual = scene.visual
    if visual is None:
        return ordered
    for elem in getattr(visual, "characters", []) or []:
        name = _element_name(elem, "name")
        if name:
            ordered.append((name, "character"))
    for elem in getattr(visual, "objects", []) or []:
        name = _element_name(elem, "name")
        if name:
            ordered.append((name, "object"))
    for elem in getattr(visual, "text_elements", []) or []:
        name = _element_name(elem, "text")
        if name:
            ordered.append((name, "text"))
    return ordered


def _first_matching(
    ordered: list[tuple[str, str]],
    query: str,
) -> tuple[str | None, str | None]:
    """Return (canonical name, kind) of the first element matching ``query``.

    Matching mirrors ``VisualFocusResolver`` (substring in both directions on
    normalized text) and always returns an *existing* element name - a query
    that names nothing returns ``(None, None)`` and is never invented.
    """
    q = _normalize(query)
    if not q:
        return None, None
    for name, kind in ordered:
        h = _normalize(name)
        if h and (q in h or h in q):
            return name, kind
    return None, None


def _first_of_kind(
    ordered: list[tuple[str, str]],
    kind: str,
) -> tuple[str | None, str | None]:
    """Return the first element of the given kind, or ``(None, None)``."""
    for name, elem_kind in ordered:
        if elem_kind == kind:
            return name, elem_kind
    return None, None


def _first_preferred_kind(
    ordered: list[tuple[str, str]],
    preferred: tuple[str, ...],
) -> tuple[str | None, str | None]:
    """Pick the first element whose kind appears earliest in ``preferred``."""
    for kind in preferred:
        target = _first_of_kind(ordered, kind)
        if target[0] is not None:
            return target
    return None, None


def _explicit_focus_target(scene: ScenePlan) -> str | None:
    """Extract explicit focus intent from the scene.

    The VisualScene default ``primary_focus="scene"`` is a no-intent value
    and is not treated as explicit. A ``camera_spec.focus_target`` is also
    explicit.
    """
    visual = scene.visual
    if visual is None:
        return None
    focus = _normalize(getattr(visual, "primary_focus", ""))
    if focus and focus != _NO_INTENT_FOCUS:
        return focus
    camera_spec = getattr(visual, "camera_spec", None) or {}
    target = camera_spec.get("focus_target") if isinstance(camera_spec, dict) else None
    if target:
        return _normalize(target)
    return None


def _scene_level_fallback(scene: ScenePlan) -> tuple[str | None, str | None]:
    """Safe scene-level fallback target.

    Only emitted when the scene carries visual intent but has no named
    subjects; otherwise no target exists.
    """
    visual = scene.visual
    if visual is not None and visual.has_visual_intent():
        return _SCENE_TARGET, "scene"
    return None, None


def _handoff_from(
    prev_target: str | None,
    current_target: str | None,
    seen: set[str],
) -> str:
    """Determine how attention flows from the previous scene into this one.

    ``seen`` holds the normalized targets of scenes strictly before the
    current scene. State order of checks is fixed so the result is
    deterministic.
    """
    if current_target is None:
        return "fallback"
    current_norm = _normalize(current_target)
    if prev_target is not None and current_norm == _normalize(prev_target):
        return "retained"
    if current_norm in {_normalize(t) for t in seen}:
        return "returned"
    if prev_target is None:
        return "established" if not seen else "introduced"
    return "shifted"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttentionDecision:
    """Attention analysis and recommendation for a single scene."""

    scene_index: int
    primary_target: str | None
    secondary_target: str | None
    target_kind: str | None
    handoff_from_previous: str
    handoff_to_next: str
    retained_from_previous: bool
    target_changed: bool
    explicit_focus_preserved: bool
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(frozen=True)
class AttentionPlan:
    """Immutable sequence-level attention continuity report."""

    decisions: tuple[AttentionDecision, ...]
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


class AttentionPlanner:
    """Deterministic attention continuity planning for scene sequences.

    Resolves a primary (and optional secondary) attention target per scene
    using strict precedence and tracks how attention flows between adjacent
    scenes. The planner is pure/read-only: it never mutates any input and
    never invents a target identifier.

    All optional V1.4 inputs are consumed in-place (never rerun).
    """

    # -- Public API ---------------------------------------------------------

    def plan(
        self,
        scenes: list[ScenePlan],
        *,
        story_plan: VisualStoryPlan | None = None,
        diversity_report: VisualDiversityReport | None = None,
        composition_plan: CompositionPlan | None = None,
        camera_plan: Any | None = None,
        focus_results: dict[int, VisualFocus] | None = None,
    ) -> AttentionPlan:
        """Analyze a sequence of scenes for attention continuity.

        Args:
            scenes: List of ScenePlan objects to analyze.
            story_plan: Optional V1.4-A VisualStoryPlan for treatments.
            diversity_report: Optional V1.4-B VisualDiversityReport.
            composition_plan: Optional V1.4-C CompositionPlan.
            camera_plan: Optional V1.4-D CameraPlan (duck-typed).
            focus_results: Optional mapping scene_index -> VisualFocus from
                the V1.3-B VisualFocusResolver (consumed, never rerun).

        Returns:
            AttentionPlan with per-scene decisions and sequence warnings.
        """
        if not scenes:
            return AttentionPlan(decisions=(), warnings=())

        # Build per-index lookup dictionaries (consumed, never rerun).
        story_decisions: dict[int, Any] = {}
        if story_plan is not None:
            for decision in story_plan.decisions:
                story_decisions[decision.scene_index] = decision

        diversity_decisions: dict[int, Any] = {}
        if diversity_report is not None:
            for decision in diversity_report.decisions:
                diversity_decisions[decision.scene_index] = decision

        composition_decisions: dict[int, Any] = {}
        if composition_plan is not None:
            for decision in composition_plan.decisions:
                composition_decisions[decision.scene_index] = decision

        camera_decisions: dict[int, Any] = {}
        if camera_plan is not None:
            for decision in camera_plan.decisions:
                camera_decisions[decision.scene_index] = decision

        focus_lookup: dict[int, VisualFocus] = dict(focus_results or {})

        # Phase 1: resolve per-scene primary/secondary targets. Nothing is
        # mutated; only existing elements (or the scene-level fallback) can
        # become targets.
        resolved: list[dict[str, Any]] = []
        for i, scene in enumerate(scenes):
            decision_info = self._resolve_scene(
                scene=scene,
                index=i,
                story_decision=story_decisions.get(i),
                diversity_decision=diversity_decisions.get(i),
                composition_decision=composition_decisions.get(i),
                camera_decision=camera_decisions.get(i),
                focus_result=focus_lookup.get(i),
            )
            resolved.append(decision_info)

        # Phase 2: derive handoffs, retention, change flags, and warnings.
        targets = [info["primary_target"] for info in resolved]
        seen_prefixes: list[set[str]] = []
        for i in range(len(targets)):
            seen_prefixes.append({_normalize(t) for t in targets[:i]})

        decisions: list[AttentionDecision] = []
        attention_run: dict[str, int] = {}

        for i, info in enumerate(resolved):
            primary = info["primary_target"]
            prev_target = targets[i - 1] if i > 0 else None
            handoff_from = _handoff_from(prev_target, primary, seen_prefixes[i])

            # Run tracking for diversity diagnostics.
            run_key = _normalize(primary)
            if run_key:
                attention_run[run_key] = attention_run.get(run_key, 0) + 1
                for k in list(attention_run):
                    if k != run_key:
                        attention_run[k] = 0
            else:
                attention_run.clear()
            run_count = attention_run.get(run_key, 0) if run_key else 0
            secondary = info["secondary_target"]
            retained = (
                prev_target is not None
                and primary is not None
                and _normalize(primary) == _normalize(prev_target)
            )
            changed = (
                prev_target is not None
                and primary is not None
                and _normalize(primary) != _normalize(prev_target)
            )

            warnings: list[str] = []
            if info["explicit_focus_preserved"]:
                warnings.append("explicit_focus_preserved")
                if retained:
                    warnings.append("explicit_focus_repetition")
            elif info["has_explicit_focus"]:
                warnings.append("explicit_focus_unresolved")

            if handoff_from == "retained":
                warnings.append(f"repeated_attention:{primary}")
            if run_count >= 3:
                warnings.append(f"extended_attention_run:{primary}:{run_count}")
            if handoff_from == "returned":
                warnings.append(f"attention_returned:{primary}")

            if info["scene_level_fallback"]:
                warnings.append("scene_level_fallback")
            if primary is None:
                warnings.append("no_target_found")
            if info["dual_targets"]:
                warnings.append("comparison_dual_targets")

            # Diversity-aware diagnostic: a legitimate secondary target exists
            # and story/composition intent permits a switch - but we NEVER
            # change the target; we only report the option.
            if (
                run_count >= 3
                and secondary is not None
                and info["diversity_permits_switch"]
            ):
                warnings.append(f"attention_diversity_recommendation:{secondary}")

            # V1.4-B cross-signal: diversity flagged a repeated focus pattern
            # and attention is currently retained on the same target.
            if info["diversity_repeated_focus"] and retained:
                warnings.append("diversity_confirms_focus_repetition")

            decisions.append(
                AttentionDecision(
                    scene_index=i,
                    primary_target=primary,
                    secondary_target=secondary,
                    target_kind=info["target_kind"],
                    handoff_from_previous=handoff_from,
                    handoff_to_next="established",  # patched below
                    retained_from_previous=retained,
                    target_changed=changed,
                    explicit_focus_preserved=info["explicit_focus_preserved"],
                    warnings=tuple(warnings),
                )
            )

        # handoff_to_next mirrors the next scene's handoff_from_previous
        # (deterministic; final scene has no next transition).
        for i in range(len(decisions)):
            if i < len(decisions) - 1:
                nxt = decisions[i + 1]
                decisions[i] = AttentionDecision(
                    scene_index=decisions[i].scene_index,
                    primary_target=decisions[i].primary_target,
                    secondary_target=decisions[i].secondary_target,
                    target_kind=decisions[i].target_kind,
                    handoff_from_previous=decisions[i].handoff_from_previous,
                    handoff_to_next=nxt.handoff_from_previous,
                    retained_from_previous=decisions[i].retained_from_previous,
                    target_changed=decisions[i].target_changed,
                    explicit_focus_preserved=decisions[i].explicit_focus_preserved,
                    warnings=decisions[i].warnings,
                )

        # Sequence-level warnings.
        sequence_warnings: list[str] = []
        if len(scenes) >= 3:
            distinct_targets = {
                _normalize(t) for t in targets if t is not None
            }
            if len(distinct_targets) <= 1:
                sequence_warnings.append("low_attention_diversity")

        return AttentionPlan(
            decisions=tuple(decisions),
            warnings=tuple(sequence_warnings),
        )

    # -- Per-scene resolution (Phase 1) --------------------------------------

    def _resolve_scene(
        self,
        scene: ScenePlan,
        *,
        index: int,
        story_decision: Any | None = None,
        diversity_decision: Any | None = None,
        composition_decision: Any | None = None,
        camera_decision: Any | None = None,
        focus_result: VisualFocus | None = None,
    ) -> dict[str, Any]:
        """Resolve the attention targets of a single scene (Phase 1).

        ``index`` is the scene position (kept for symmetry with the planning
        loop). Strict precedence - a target is adopted from the first level
        that yields a *real* scene element; nothing is ever invented:

          1. Explicit scene focus intent (always wins; never replaced)
          2. Existing VisualFocusResolver result (V1.3-B)
          3. Explicit camera focus target (V1.4-D)
          4. V1.4-C composition primary subject
          5. V1.4-A story treatment / beat
          6. Existing scene subject ordering
          7. Safe scene-level fallback
        """
        ordered = _gather_ordered_subjects(scene)
        explicit = _explicit_focus_target(scene)

        primary: str | None = None
        kind: str | None = None
        explicit_focus_preserved = False
        scene_level_fallback = False

        def _adopt(
            match: tuple[str | None, str | None],
            *,
            preserved: bool = False,
            fallback: bool = False,
        ) -> None:
            nonlocal primary, kind, explicit_focus_preserved, scene_level_fallback
            if match[0] is None or primary is not None:
                return
            primary, kind = match
            explicit_focus_preserved = preserved
            scene_level_fallback = fallback

        # 1. Explicit scene focus intent - preserved, never replaced.
        if explicit:
            _adopt(_first_matching(ordered, explicit), preserved=True)

        # 2. Existing V1.3-B VisualFocusResolver result (consumed, not rerun).
        if primary is None and focus_result is not None:
            _adopt(_first_matching(ordered, getattr(focus_result, "primary", "") or ""))

        # 3. Explicit camera focus target (V1.4-D), subordinate to explicit
        #    scene focus. A scene-level camera target is not an element name
        #    and is handled by the final fallback instead.
        if primary is None and camera_decision is not None:
            camera_target = getattr(camera_decision, "focus_target", None) or ""
            if _normalize(camera_target) != _SCENE_TARGET:
                _adopt(_first_matching(ordered, camera_target))

        # 4. V1.4-C composition primary subject (kind preference, then
        #    subject regions).
        if primary is None and composition_decision is not None:
            comp_type = _normalize(getattr(composition_decision, "composition_type", ""))
            preferred = _COMPOSITION_PREFERRED_KINDS.get(comp_type, ())
            if not preferred:
                regions = getattr(composition_decision, "subject_regions", ()) or ()
                preferred = tuple(
                    region
                    for region in (_normalize(str(item)) for item in regions)
                    if region in SUPPORTED_TARGET_KINDS
                )
            if preferred:
                _adopt(_first_preferred_kind(ordered, preferred))

        # 5. V1.4-A story treatment / beat (kind preference), then the story
        #    focus target when it names a real element.
        if primary is None and story_decision is not None:
            treatment = _normalize(getattr(story_decision, "treatment", ""))
            preferred = _TREATMENT_PREFERRED_KINDS.get(treatment, ())
            if preferred:
                _adopt(_first_preferred_kind(ordered, preferred))
            if primary is None:
                _adopt(
                    _first_matching(
                        ordered, getattr(story_decision, "focus_target", "") or ""
                    )
                )

        # 6. Existing scene subject ordering (characters, objects, text).
        if primary is None:
            _adopt(_first_preferred_kind(ordered, ("character", "object", "text")))

        # 7. Safe scene-level fallback (only when the scene carries visual
        #    intent but has no named subjects).
        if primary is None:
            _adopt(_scene_level_fallback(scene), fallback=True)

        repeated_focus = False
        repeated_prev = False
        if diversity_decision is not None:
            repeated_focus = bool(
                getattr(diversity_decision, "repeated_focus_pattern", False)
            )
            repeated_prev = bool(
                getattr(diversity_decision, "repeated_with_previous", False)
            )

        secondary, secondary_kind, dual_targets = self._resolve_secondary(
            scene,
            primary,
            focus_result=focus_result,
            composition_decision=composition_decision,
        )

        return {
            "primary_target": primary,
            "secondary_target": secondary,
            "secondary_kind": secondary_kind,
            "target_kind": kind,
            "explicit_focus_preserved": explicit_focus_preserved,
            "has_explicit_focus": explicit is not None,
            "scene_level_fallback": scene_level_fallback,
            "dual_targets": dual_targets,
            "diversity_permits_switch": secondary is not None
            and (repeated_focus or repeated_prev),
            "diversity_repeated_focus": repeated_focus,
        }

    def _resolve_secondary(
        self,
        scene: ScenePlan,
        primary: str | None,
        *,
        focus_result: VisualFocus | None = None,
        composition_decision: Any | None = None,
    ) -> tuple[str | None, str | None, bool]:
        """Resolve a secondary attention target (Phase 1 helper).

        Returns ``(secondary_target, secondary_kind, dual_targets)``. A
        secondary target exists only when the scene data legitimately
        supports one: a dual-subject composition (V1.4-C) or an existing
        VisualFocus secondary (V1.3-B). The primary target is never returned
        again and no target is ever invented.
        """
        ordered = _gather_ordered_subjects(scene)
        primary_norm = _normalize(primary or "")

        def _distinct(name: str | None) -> str | None:
            if not name:
                return None
            if primary_norm and _normalize(name) == primary_norm:
                return None
            return name

        # Dual-subject compositions (V1.4-C) legitimately carry a
        # primary + secondary subject pair. A comparison with only one valid
        # subject is not collapsed into a fake pair.
        comp_type = ""
        if composition_decision is not None:
            comp_type = _normalize(getattr(composition_decision, "composition_type", ""))
        if comp_type in _DUAL_TARGET_COMPOSITIONS:
            for name, kind in ordered:
                distinct = _distinct(name)
                if distinct is not None:
                    return distinct, kind, True

        # V1.3-B VisualFocus secondary, when it names a real distinct element.
        if focus_result is not None:
            name, kind = _first_matching(
                ordered, getattr(focus_result, "secondary", "") or ""
            )
            distinct = _distinct(name)
            if distinct is not None:
                return distinct, kind, False

        return None, None, False
