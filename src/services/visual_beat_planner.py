"""Day 4: VisualBeatPlanner — converts StoryBeats into VisualBeats.

Maps story beat types to character action/emotion/pose, camera patterns,
environments, objects, and transitions.  Implements:

- **Visual state progression**: scene-to-scene tracking ensuring each new
  scene changes at least one meaningful visual dimension.
- **Anti-static-sequence guarantee**: if no natural change occurs, the
  planner forces an action or emotion change.
- **Emphasis-based camera framing**: high-importance beats get active
  cameras; low-importance beats get static framing.
- **Transition logic**: beat-pair-aware transitions with fade-to-black
  on the final scene.

All mappings use existing vocabularies from ``scene_composition`` and
``visual_beat_engine``.  Fully deterministic — no randomness.
"""

from __future__ import annotations

from src.orchestration.schemas.story_beat import StoryBeatPlan
from src.orchestration.schemas.visual_beat import (
    VisualBeat,
    VisualBeatPlan,
    VisualState,
)
from src.services.scene_composition import SUPPORTED_CAMERA_PATTERNS


# ---------------------------------------------------------------------------
# Beat-type -> character mapping (defaults; emphasis may override)
# ---------------------------------------------------------------------------

_BEAT_ACTION: dict[str, str] = {
    "HOOK": "wave",
    "PROBLEM": "point",
    "CONTRAST": "walk",
    "EXPLANATION": "talk",
    "EXAMPLE": "point",
    "INSIGHT": "surprised",
    "ACTION": "run",
    "CONCLUSION": "wave",
    "SOLUTION": "wave",
    "CTA": "wave",
}

_BEAT_EMOTION: dict[str, str] = {
    "HOOK": "happy",
    "PROBLEM": "frustrated",
    "CONTRAST": "neutral",
    "EXPLANATION": "focused",
    "EXAMPLE": "focused",
    "INSIGHT": "surprised",
    "ACTION": "excited",
    "CONCLUSION": "happy",
    "SOLUTION": "excited",
    "CTA": "happy",
}

_BEAT_POSE: dict[str, str] = {
    "HOOK": "wave",
    "PROBLEM": "point",
    "CONTRAST": "walk",
    "EXPLANATION": "talk",
    "EXAMPLE": "point",
    "INSIGHT": "surprised",
    "ACTION": "run",
    "CONCLUSION": "wave",
    "SOLUTION": "wave",
    "CTA": "wave",
}

# ---------------------------------------------------------------------------
# Camera mapping with emphasis influence
# ---------------------------------------------------------------------------

_BEAT_CAMERA_DEFAULT: dict[str, str] = {
    "HOOK": "slow_zoom_in",
    "PROBLEM": "focus_on_character",
    "CONTRAST": "pan_left",
    "EXPLANATION": "static",
    "EXAMPLE": "pan_right",
    "INSIGHT": "slow_zoom_in",
    "ACTION": "pan_right",
    "CONCLUSION": "slow_zoom_out",
    "SOLUTION": "slow_zoom_in",
    "CTA": "slow_zoom_out",
}

_EMPHASIS_CAMERA_CANDIDATES: dict[str, list[str]] = {
    "high": ["slow_zoom_in", "focus_on_character", "zoom_then_pan"],
    "medium": ["slow_zoom_in", "slow_zoom_out", "pan_right", "pan_left"],
    "low": ["static"],
}

# ---------------------------------------------------------------------------
# Emphasis-based action intensity
# ---------------------------------------------------------------------------

_EMPHASIS_ACTIONS: dict[str, list[str]] = {
    "high": ["jump", "wave", "run", "point"],
    "medium": ["talk", "point", "wave", "walk"],
    "low": ["idle", "walk", "talk"],
}

# ---------------------------------------------------------------------------
# Environment cycle
# ---------------------------------------------------------------------------

_ENVIRONMENT_CYCLE = [
    "study_desk",
    "abstract_info_space",
    "workspace",
    "classroom",
    "office",
]

# ---------------------------------------------------------------------------
# Scene purpose per beat type
# ---------------------------------------------------------------------------

_BEAT_PURPOSE: dict[str, str] = {
    "HOOK": "Establish attention with a curiosity-driven opening hook.",
    "PROBLEM": "Expose the core frustration or problem the audience faces.",
    "CONTRAST": "Highlight the gap between expectation and reality.",
    "EXPLANATION": "Explain the key concept or insight clearly.",
    "EXAMPLE": "Provide a concrete example to illustrate the point.",
    "INSIGHT": "Deliver the key realization that reframes the problem.",
    "ACTION": "Show the concrete practice or system to apply next.",
    "CONCLUSION": "Close the arc with a distinct, memorable ending.",
    "SOLUTION": "Present the actionable solution or path forward.",
    "CTA": "Drive the viewer to take a specific next step.",
}

# ---------------------------------------------------------------------------
# Text overlay per beat type
# ---------------------------------------------------------------------------

_BEAT_TEXT_OVERLAY: dict[str, str] = {
    "HOOK": "Did you know?",
    "PROBLEM": "The Problem",
    "CONTRAST": "But Wait...",
    "EXPLANATION": "Here's Why",
    "EXAMPLE": "For Example",
    "INSIGHT": "The Real Problem",
    "ACTION": "Do This Next",
    "CONCLUSION": "Remember This",
    "SOLUTION": "The Solution",
    "CTA": "Take Action Now",
}
# ---------------------------------------------------------------------------
# Transition rules by beat-pair
# ---------------------------------------------------------------------------

_BEAT_TRANSITIONS: dict[tuple[str, str], str] = {
    ("HOOK", "PROBLEM"): "crossfade",
    ("HOOK", "CONTRAST"): "slide_left",
    ("PROBLEM", "EXPLANATION"): "crossfade",
    ("PROBLEM", "CONTRAST"): "crossfade",
    ("PROBLEM", "SOLUTION"): "slide_up",
    ("PROBLEM", "INSIGHT"): "fade",
    ("CONTRAST", "EXAMPLE"): "slide_left",
    ("CONTRAST", "SOLUTION"): "crossfade",
    ("CONTRAST", "INSIGHT"): "slide_left",
    ("EXPLANATION", "EXAMPLE"): "crossfade",
    ("EXPLANATION", "SOLUTION"): "crossfade",
    ("EXPLANATION", "INSIGHT"): "fade",
    ("EXAMPLE", "SOLUTION"): "crossfade",
    ("EXAMPLE", "INSIGHT"): "crossfade",
    ("EXAMPLE", "CONCLUSION"): "fade",
    ("INSIGHT", "ACTION"): "slide_up",
    ("INSIGHT", "SOLUTION"): "crossfade",
    ("ACTION", "CONCLUSION"): "fade",
    ("ACTION", "CTA"): "fade",
    ("SOLUTION", "CTA"): "crossfade",
    ("SOLUTION", "CONCLUSION"): "fade",
    ("CONCLUSION", "CTA"): "fade",
}

# ---------------------------------------------------------------------------
# Duration multiplier by emphasis
# ---------------------------------------------------------------------------

_DURATION_MULTIPLIER: dict[str, float] = {
    "high": 1.15,
    "medium": 1.0,
    "low": 0.85,
}

# ---------------------------------------------------------------------------
# Objects per beat type
# ---------------------------------------------------------------------------

_BEAT_OBJECTS: dict[str, list[str]] = {
    "HOOK": ["light_bulb"],
    "PROBLEM": ["cross_mark"],
    "CONTRAST": ["arrow"],
    "EXPLANATION": ["book"],
    "EXAMPLE": ["stack_of_books"],
    "INSIGHT": ["brain"],
    "ACTION": ["timer"],
    "CONCLUSION": ["check_mark"],
    "SOLUTION": ["check_mark"],
    "CTA": ["calendar"],
}

# Action / emotion rotation used by the anti-static guarantee

_ACTION_ROTATION = ["idle", "talk", "point", "wave", "walk"]
_EMOTION_ROTATION = ["neutral", "happy", "focused", "surprised", "excited"]
# ---------------------------------------------------------------------------
# VisualBeatPlanner
# ---------------------------------------------------------------------------


class VisualBeatPlanner:
    """Convert a ``StoryBeatPlan`` into a ``VisualBeatPlan``.

    Each story beat maps to one or more visual beats with character state,
    camera intent, environment, objects, text overlay, transitions, and
    emphasis scoring.  State progression is tracked scene-to-scene to
    guarantee visual change.
    """

    def plan(self, story_plan: StoryBeatPlan) -> VisualBeatPlan:
        """Produce a ``VisualBeatPlan`` from the story beat plan."""
        if not story_plan.beats:
            return VisualBeatPlan(
                beats=[],
                total_duration_seconds=0,
                state_progression=[],
                warnings=["No story beats — empty visual plan."],
            )

        beats: list[VisualBeat] = []
        state_progression: list[list[str]] = []
        warnings: list[str] = []
        prev_state = VisualState()

        scene_num = 0
        for i, sb in enumerate(story_plan.beats):
            action = _BEAT_ACTION.get(sb.beat_type, "talk")
            emotion = _BEAT_EMOTION.get(sb.beat_type, "neutral")
            pose = _BEAT_POSE.get(sb.beat_type, "talk")
            camera = _pick_camera(
                sb.beat_type, sb.emphasis, prev_state.camera_pattern,
            )
            environment = _ENVIRONMENT_CYCLE[i % len(_ENVIRONMENT_CYCLE)]
            objects = _BEAT_OBJECTS.get(sb.beat_type, [])
            text_overlay = _BEAT_TEXT_OVERLAY.get(sb.beat_type, sb.heading or "")
            scene_purpose = _BEAT_PURPOSE.get(sb.beat_type, sb.key_message)

            # Scale durations by emphasis
            scaled = _scale_durations(
                sb.duration_seconds, sb.scene_count, sb.emphasis,
            )
            # Split narration across sub-scenes for multi-scene beats so each
            # scene keeps a distinct, renderable narration slice.
            narration_slices = _split_narration(sb.narration, sb.scene_count)

            for sub_idx in range(sb.scene_count):
                scene_num += 1
                # Sub-scene action variation for multi-scene beats
                if sub_idx > 0 and sb.scene_count > 1:
                    action = _rotate_action(action)
                    if sub_idx % 2 == 0:
                        emotion = _rotate_emotion(emotion)

                new_state = VisualState(
                    character_action=action,
                    character_emotion=emotion,
                    character_pose=pose,
                    camera_pattern=camera,
                    environment=environment,
                    objects=objects,
                )

                # Anti-static: detect zero-change
                natural_changes = _compute_changes(prev_state, new_state)
                changes = list(natural_changes)
                if not natural_changes and scene_num > 1:
                    action, emotion = _force_changes(
                        prev_state, action, emotion,
                    )
                    new_state.character_action = action
                    new_state.character_emotion = emotion
                    changes = _compute_changes(prev_state, new_state)
                    warnings.append(
                        f"Scene {scene_num}: forced state change to "
                        "avoid static sequence.",
                    )

                # Transition
                is_last = (
                    i == len(story_plan.beats) - 1
                    and sub_idx == sb.scene_count - 1
                )
                if is_last:
                    transition_type = "fade_to_black"
                    transition_dur = 1.0
                else:
                    next_type = (
                        story_plan.beats[i + 1].beat_type
                        if i + 1 < len(story_plan.beats)
                        else sb.beat_type
                    )
                    transition_type, transition_dur = _recommend_transition(
                        sb.beat_type, next_type, sb.emphasis,
                    )

                beats.append(VisualBeat(
                    beat_id=f"vb-{scene_num:02d}",
                    story_beat_id=sb.beat_id,
                    scene_number=scene_num,
                    scene_purpose=scene_purpose,
                    narration_text=(narration_slices[sub_idx]
                                    if sub_idx < len(narration_slices)
                                    else sb.narration),
                    character_action=action,
                    character_emotion=emotion,
                    character_pose=pose,
                    camera_pattern=camera,
                    environment=environment,
                    objects=objects,
                    text_overlay=text_overlay,
                    emphasis_score=sb.importance,
                    emphasis_label=sb.emphasis,
                    transition_type=transition_type,
                    transition_duration=transition_dur,
                    state_changed=changes,
                    duration_seconds=scaled[sub_idx],
                ))
                state_progression.append(changes)
                prev_state = new_state

        return VisualBeatPlan(
            beats=beats,
            total_duration_seconds=sum(b.duration_seconds for b in beats),
            state_progression=state_progression,
            warnings=warnings,
        )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _pick_camera(beat_type: str, emphasis: str, prev_camera: str) -> str:
    """Pick a camera pattern that differs from the previous one."""
    default = _BEAT_CAMERA_DEFAULT.get(beat_type, "static")
    pool = list(_EMPHASIS_CAMERA_CANDIDATES.get(emphasis, [default]))
    if default not in pool:
        pool.insert(0, default)
    for cam in pool:
        if cam != prev_camera:
            return cam
    for cam in SUPPORTED_CAMERA_PATTERNS:
        if cam != prev_camera:
            return cam
    return default


def _recommend_transition(
    from_type: str, to_type: str, emphasis: str,
) -> tuple[str, float]:
    """Deterministic transition for a beat pair."""
    if emphasis == "low":
        return "cut", 0.3
    key = (from_type, to_type)
    base = _BEAT_TRANSITIONS.get(key, "crossfade")
    duration = 0.8 if emphasis == "high" else 0.5
    return base, duration


def _compute_changes(prev: VisualState, new: VisualState) -> list[str]:
    """Return list of visual dimensions that changed."""
    changes: list[str] = []
    if new.character_action != prev.character_action:
        changes.append("action")
    if new.character_emotion != prev.character_emotion:
        changes.append("emotion")
    if new.character_pose != prev.character_pose:
        changes.append("pose")
    if new.camera_pattern != prev.camera_pattern:
        changes.append("camera")
    if new.environment != prev.environment:
        changes.append("environment")
    if new.objects != prev.objects:
        changes.append("objects")
    return changes
def _force_changes(
    prev: VisualState, action: str, emotion: str,
) -> tuple[str, str]:
    """Force at least one change when the scene would be static."""
    for a in _ACTION_ROTATION:
        if a != prev.character_action:
            action = a
            break
    for e in _EMOTION_ROTATION:
        if e != prev.character_emotion:
            emotion = e
            break
    return action, emotion


def _scale_durations(
    total: int, count: int, emphasis: str,
) -> list[int]:
    """Split *total* into *count* sub-durations scaled by emphasis."""
    mult = _DURATION_MULTIPLIER.get(emphasis, 1.0)
    base_each = max(3, int(round(total * mult / count)))
    result = [base_each] * count
    diff = total - sum(result)
    idx = 0
    while diff != 0 and idx < len(result) * 5:
        slot = idx % len(result)
        candidate = result[slot] + (1 if diff > 0 else -1)
        if candidate >= 3:
            result[slot] = candidate
            diff += -1 if diff > 0 else 1
        idx += 1
    return result


def _rotate_action(current: str) -> str:
    """Return the next action in the rotation that differs from current."""
    for a in _ACTION_ROTATION:
        if a != current:
            return a
    return current


def _rotate_emotion(current: str) -> str:
    """Return the next emotion in the rotation that differs from current."""
    for e in _EMOTION_ROTATION:
        if e != current:
            return e
    return current


def _split_narration(narration: str, count: int) -> list[str]:
    """Split narration into *count* non-empty slices for sub-scenes."""
    text = (narration or "").strip()
    if count <= 1 or not text:
        return [text] if text else [""]
    import re as _re
    sentences = _re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if len(sentences) >= count:
        chunks: list[list[str]] = [[] for _ in range(count)]
        for idx, sent in enumerate(sentences):
            chunks[idx % count].append(sent)
        return [" ".join(c).strip() for c in chunks]
    words = text.split()
    per = max(1, len(words) // count)
    slices: list[str] = []
    for idx in range(count):
        start = idx * per
        end = (idx + 1) * per if idx < count - 1 else len(words)
        part = " ".join(words[start:end]).strip()
        slices.append(part or text)
    return slices