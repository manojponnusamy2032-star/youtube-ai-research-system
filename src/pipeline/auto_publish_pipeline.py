"""Auto-publish pipeline.

Turns a video plan (title, description, scenes) into a rendered MP4 with
narration and, optionally, uploads it to YouTube. Every stage runs locally
with FFmpeg and Piper, so a full run costs nothing beyond YouTube Data API
quota.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any

from src.models.content_package import (
    AudioRequest,
    Motion,
    MotionIntent,
    RenderConfig,
    RenderJobSpec,
    Transition,
    SUPPORTED_MOTION_TYPES,
    SUPPORTED_TRANSITION_TYPES,
)
from src.services.media_muxer import MediaMuxer
from src.services.piper_tts_service import PiperTTSService
from src.services.scene_video_renderer import (
    FORMATS,
    SHORTS_FORMAT,
    SceneVideoRenderer,
    VideoFormat,
)
from src.services.semantic_motion import SemanticMotionLowerer, SemanticMotionSpec
from src.services.semantic_transition import SemanticTransitionResolver
from src.services.stickman_renderer import StickmanRenderer
from src.services.tts_service import TTSRequest, TTSService
from src.services.video_assembler import VideoAssembler
from src.services.youtube_upload_service import (
    OAuthCredentials,
    UploadRequest,
    YouTubeUploadService,
)

logger = logging.getLogger(__name__)

SCENE_PADDING_SECONDS = 0.4
SEMANTIC_VISUALS_ENABLED = False
# V1.4-F: sequence-level visual planning (story/diversity/composition/camera/
# attention). Advisory only; requires the V1.3 semantic pipeline and never
# overrides explicit scene intent.
VISUAL_STORY_PLANNER_ENABLED = False


@dataclass
class VisualScene:
    """Visual intent for a scene, mapped to the existing rendering architecture."""

    # High-level scene role for motion intent
    scene_role: str = "general"
    # Primary visual focus
    primary_focus: str = "scene"
    # Camera pattern: hold, zoom_in, zoom_out, pan, tracking, follow
    camera_pattern: str = "hold"
    # Energy level: low, medium, high
    energy: str = "medium"

    # Optional structured motions (reuses existing Motion type)
    motions: list[Motion] = field(default_factory=list)

    # Optional transition to next scene
    transition: Transition | None = None

    # Legacy text instructions (used by StickmanRenderer's fallback logic)
    visual_prompt: str = ""
    animation_instructions: str = ""
    camera_instructions: str = ""

    # Character action (idle, walk, run, point, wave, jump, talk, surprised)
    character_action: str = "idle"

    # Background color (FFmpeg color string, e.g., "0x101820")
    background_color: str = "0x101820"

    # Optional background image path
    background_image: str | None = None

    # --- Structured visual composition (Visual Quality v1) ---
    # Characters: [{name, pose, emotion, x, y, scale, color}]
    characters: list[dict[str, Any]] = field(default_factory=list)
    # Objects: [{name, type, x, y, scale, rotation, opacity}]
    objects: list[dict[str, Any]] = field(default_factory=list)
    # Environment: {type, background_color, ground_color, ground_y}
    environment: dict[str, Any] = field(default_factory=dict)
    # Text elements: [{text, x, y, size, color, opacity, style, fade_in, fade_out}]
    text_elements: list[dict[str, Any]] = field(default_factory=list)
    # Visual effects: [{type, target, start, duration, parameters}]
    visual_effects: list[dict[str, Any]] = field(default_factory=list)
    # Camera spec: {pattern, focus_target, duration, easing}
    camera_spec: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize fields."""
        self.scene_role = str(self.scene_role).strip().lower() or "general"
        self.primary_focus = str(self.primary_focus).strip().lower() or "scene"
        self.camera_pattern = str(self.camera_pattern).strip().lower() or "hold"
        self.energy = str(self.energy).strip().lower() or "medium"
        if self.energy not in {"low", "medium", "high"}:
            self.energy = "medium"
        self.character_action = str(self.character_action).strip().lower() or "idle"
        supported_actions = {"idle", "walk", "run", "point", "wave", "jump", "talk", "surprised"}
        if self.character_action not in supported_actions:
            self.character_action = "idle"
        # Validate motions
        for motion in self.motions:
            if not isinstance(motion, Motion):
                raise ValueError("motions must be list of Motion objects")
            motion.validate(self.duration_seconds if hasattr(self, 'duration_seconds') else None, allow_overflow=True)

    @property
    def duration_seconds(self) -> float:
        """Estimated scene duration (needed for motion validation)."""
        # This will be set by the pipeline after TTS
        return getattr(self, '_duration_seconds', 0.0)

    @duration_seconds.setter
    def duration_seconds(self, value: float) -> None:
        self._duration_seconds = float(value)

    def to_motion_intent(self) -> MotionIntent:
        """Convert to MotionIntent for high-level guidance."""
        return MotionIntent(
            scene_role=self.scene_role,
            primary_focus=self.primary_focus,
            camera_pattern=self.camera_pattern,
            energy=self.energy,
        )

    def has_visual_intent(self) -> bool:
        """Check if this scene has meaningful visual intent beyond caption."""
        return (
            self.motions
            or self.transition is not None
            or self.visual_prompt.strip()
            or self.animation_instructions.strip()
            or self.camera_instructions.strip()
            or self.character_action != "idle"
            or self.camera_pattern != "hold"
            or self.background_image is not None
            or bool(self.characters)
            or bool(self.objects)
            or bool(self.environment)
            or bool(self.text_elements)
            or bool(self.visual_effects)
        )


@dataclass
class ScenePlan:
    """A single narrated scene of the video plan."""

    narration: str
    caption: str = ""
    background_image: str | None = None
    visual: VisualScene | None = None

    def __post_init__(self) -> None:
        """Validate the scene and default the caption to the narration."""
        if not self.narration.strip():
            raise ValueError("scene narration cannot be empty")
        if not self.caption.strip():
            self.caption = self.narration
        if self.visual is None:
            self.visual = VisualScene()

    @property
    def display_caption(self) -> str:
        """Return the caption drawn on screen."""
        return self.caption


@dataclass
class VideoPlan:
    """The full plan for one video to render and publish."""

    title: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    scenes: list[ScenePlan] = field(default_factory=list)
    video_format: str = SHORTS_FORMAT.name
    privacy_status: str = "public"
    category_id: str = "22"

    def __post_init__(self) -> None:
        """Validate the plan."""
        if not self.title.strip():
            raise ValueError("title cannot be empty")
        if not self.scenes:
            raise ValueError("plan must contain at least one scene")
        if self.video_format not in FORMATS:
            raise ValueError(f"video_format must be one of {sorted(FORMATS)}")

    @property
    def format(self) -> VideoFormat:
        """Return the geometry for the requested format."""
        return FORMATS[self.video_format]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "VideoPlan":
        """Build a plan from a JSON-style dictionary."""
        scenes = []
        for scene_data in payload.get("scenes", []):
            visual_data = scene_data.pop("visual", None)
            if visual_data:
                # Convert visual data to VisualScene object
                motions_data = visual_data.pop("motions", [])
                motions = []
                for m in motions_data:
                    # Handle object_name field - map to target_id
                    m_copy = dict(m)
                    if "object_name" in m_copy:
                        m_copy["target_id"] = m_copy.pop("object_name")

                    # Convert list-based from/to parameters to dict format for interpolate_value
                    params = m_copy.get("parameters", {})
                    if isinstance(params, dict):
                        for key in ("from", "to"):
                            if key in params and isinstance(params[key], list) and len(params[key]) == 2:
                                params[key] = {"x": params[key][0], "y": params[key][1]}
                        m_copy["parameters"] = params

                    # Map character action motion types to "emphasize" with action parameter
                    motion_type = m_copy.get("type", "").lower()
                    if motion_type in {"idle", "talk", "surprised", "walk", "run", "point", "wave", "jump"}:
                        action = m_copy.pop("type")
                        m_copy["type"] = "emphasize"
                        m_copy["parameters"] = {**m_copy.get("parameters", {}), "action": action}

                    motions.append(Motion(**m_copy))

                transition_data = visual_data.pop("transition", None)
                if transition_data:
                    transition = Transition(**transition_data)
                else:
                    transition = None

                visual = VisualScene(
                    motions=motions,
                    transition=transition,
                    **visual_data
                )
            else:
                visual = None

            scene = ScenePlan(visual=visual, **scene_data)
            scenes.append(scene)

        return cls(
            title=payload.get("title", ""),
            description=payload.get("description", ""),
            tags=list(payload.get("tags", [])),
            scenes=scenes,
            video_format=payload.get("video_format", SHORTS_FORMAT.name),
            privacy_status=payload.get("privacy_status", "public"),
            category_id=str(payload.get("category_id", "22")),
        )

    @classmethod
    def from_file(cls, path: str) -> "VideoPlan":
        """Load a plan from a JSON file."""
        with open(path, "r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))


class AutoPublishPipeline:
    """Renders a video plan and optionally publishes it to YouTube."""

    def __init__(
        self,
        output_directory: str = "output/publish",
        tts_service: TTSService | None = None,
        scene_renderer: SceneVideoRenderer | None = None,
        upload_service: YouTubeUploadService | None = None,
        muxer: MediaMuxer | None = None,
    ) -> None:
        """Initialize the pipeline.

        Args:
            output_directory: Working directory for scenes and final media.
            tts_service: Narration engine. Defaults to local Piper.
            scene_renderer: Scene clip renderer. Defaults to FFmpeg captions.
            upload_service: Upload backend. Built from env when uploading.
            muxer: Audio/video muxer. Defaults to an executing MediaMuxer.
        """
        self.output_directory = output_directory
        self.audio_directory = os.path.join(output_directory, "audio")
        self.scene_directory = os.path.join(output_directory, "scenes")
        self.tts_service = tts_service or PiperTTSService(
            output_directory=self.audio_directory
        )
        self.scene_renderer = scene_renderer or SceneVideoRenderer(
            output_directory=self.scene_directory
        )
        self.upload_service = upload_service
        self.muxer = muxer or MediaMuxer(execute_enabled=True)

    def run(self, plan: VideoPlan, upload: bool = False) -> dict[str, Any]:
        """Render the plan and optionally upload the result.

        Args:
            plan: The video plan to produce.
            upload: When True, publish the rendered video to YouTube.

        Returns:
            Dictionary describing the run: status, stage, final video path and
            upload result. ``status`` is ``failed`` when a stage fails.
        """
        os.makedirs(self.output_directory, exist_ok=True)

        narration = self._narrate(plan)
        if narration["status"] == "failed":
            return narration

        scenes = self._render_scenes(plan, narration["segments"])
        if scenes["status"] == "failed":
            return scenes
        visual_planning_ran = bool(scenes.get("visual_planning"))

        assembled = self._assemble(scenes["render_outputs"], plan.format)
        if assembled["status"] == "failed":
            return assembled

        audio_track = self._concat_audio(
            [segment["audio_reference"] for segment in narration["segments"]]
        )
        if audio_track["status"] == "failed":
            return audio_track

        final_path = os.path.join(self.output_directory, "final_with_audio.mp4")
        mux_result = self.muxer.mux(
            assembled["output_reference"], audio_track["audio_reference"], final_path
        )
        if mux_result.get("status") != "completed":
            return {
                "status": "failed",
                "stage": "mux",
                "error": mux_result.get("error", "Muxing failed"),
                "details": mux_result,
            }

        result: dict[str, Any] = {
            "status": "completed",
            "stage": "render",
            "video_path": final_path,
            "duration_seconds": round(
                sum(segment["duration_seconds"] for segment in narration["segments"]), 2
            ),
            "scene_count": len(plan.scenes),
        }
        if visual_planning_ran:
            result["visual_planning"] = True

        if upload:
            result["upload"] = self._upload(plan, final_path)
            result["stage"] = "upload"
            if result["upload"].get("status") != "completed":
                result["status"] = "failed"

        return result

    def _narrate(self, plan: VideoPlan) -> dict[str, Any]:
        """Synthesize narration audio for every scene."""
        segments: list[dict[str, Any]] = []
        for index, scene in enumerate(plan.scenes, start=1):
            generated = self.tts_service.generate(TTSRequest(text=scene.narration))
            if generated.get("status") != "completed" or not generated.get(
                "audio_reference"
            ):
                return {
                    "status": "failed",
                    "stage": "narration",
                    "error": generated.get("error", "TTS failed"),
                    "scene_number": index,
                }
            segments.append(
                {
                    "scene_number": index,
                    "audio_reference": generated["audio_reference"],
                    "duration_seconds": float(generated.get("duration_seconds", 0.0)),
                }
            )
        return {"status": "completed", "segments": segments}

    def _render_scenes(
        self, plan: VideoPlan, segments: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Render one clip per scene, matching its narration duration."""
        render_outputs: list[dict[str, Any]] = []

        # Initialize stickman renderer for visual scenes
        stickman_renderer = StickmanRenderer(execute_enabled=True)
        semantic_contexts: list[dict[str, Any]] = []
        planning_ran = False
        if SEMANTIC_VISUALS_ENABLED:
            # Beat and focus detection runs exactly once per planning phase
            # and is shared by the V1.3 semantic lowering and the V1.4
            # planning stack (V1.4-F, feature-flagged).
            beats = self._beat_inputs(plan)
            focus_results = self._focus_results(plan, beats)
            semantic_contexts = self._semantic_contexts(
                plan, beats=beats, focus_results=focus_results
            )
            if VISUAL_STORY_PLANNER_ENABLED:
                planning = self._plan_visual_story(
                    plan, beats=beats, focus_results=focus_results
                )
                self._merge_visual_planning(semantic_contexts, planning)
                planning_ran = True

        for index, (scene, segment) in enumerate(zip(plan.scenes, segments)):
            scene_number = segment["scene_number"]
            duration = segment["duration_seconds"] + SCENE_PADDING_SECONDS
            video_format = plan.format

            # Update visual scene with duration for motion validation
            if scene.visual:
                scene.visual.duration_seconds = duration

            # Determine rendering path: visual or caption-only
            if scene.visual and scene.visual.has_visual_intent():
                # Use StickmanRenderer for visual scenes
                record = self._render_visual_scene(
                    scene=scene,
                    segment=segment,
                    scene_number=scene_number,
                    duration=duration,
                    video_format=video_format,
                    stickman_renderer=stickman_renderer,
                    semantic_context=semantic_contexts[index] if semantic_contexts else None,
                    total_scenes=len(plan.scenes),
                )
            else:
                # Use SceneVideoRenderer for backward-compatible caption-only scenes
                record = self.scene_renderer.render_scene(
                    scene_number=scene_number,
                    text=scene.display_caption,
                    duration_seconds=duration,
                    video_format=video_format,
                    background_image=scene.background_image,
                )

            if record.get("status") != "completed":
                return {
                    "status": "failed",
                    "stage": "scene_render",
                    "error": record.get("error", "Scene render failed"),
                    "scene_number": scene_number,
                    "details": record,
                }
            render_outputs.append(record)
        stage_result: dict[str, Any] = {
            "status": "completed",
            "render_outputs": render_outputs,
        }
        if planning_ran:
            stage_result["visual_planning"] = True
            if any("visual_planning_application" in record for record in render_outputs):
                # V1.5: safe planning application actually ran and modified
                # staging inputs for at least one scene.
                stage_result["visual_planning_application"] = True
        if any("background_variation" in record for record in render_outputs):
            # V1.6-A: background variation ran for at least one scene.
            stage_result["background_variation"] = True
        return stage_result

    @staticmethod
    def _beat_inputs(plan: VideoPlan) -> list[Any]:
        """Detect narrative beats once per run for V1.3/V1.4 reuse (V1.4-F)."""
        from src.services.visual_beat_engine import VisualBeatEngine

        return VisualBeatEngine().detect_sequence(
            [
                {
                    "narration": scene.narration,
                    "scene_role": scene.visual.scene_role if scene.visual else "",
                }
                for scene in plan.scenes
            ]
        )

    @staticmethod
    def _focus_results(plan: VideoPlan, beats: list[Any]) -> dict[int, Any]:
        """Resolve per-scene focus once per run (scene index -> VisualFocus)."""
        from src.services.visual_focus import VisualFocusResolver

        resolver = VisualFocusResolver()
        results: dict[int, Any] = {}
        for index, (scene, beat) in enumerate(zip(plan.scenes, beats)):
            visual = scene.visual or VisualScene()
            results[index] = resolver.resolve(
                beat,
                characters=visual.characters,
                objects=visual.objects,
                text_elements=visual.text_elements,
                primary_focus=visual.primary_focus,
                focus_target=visual.camera_spec.get("focus_target"),
            )
        return results

    @staticmethod
    def _semantic_contexts(
        plan: VideoPlan,
        beats: list[Any] | None = None,
        focus_results: dict[int, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Build optional derived semantics without changing scene models.

        ``beats`` and ``focus_results`` may be supplied by callers that already
        computed them (V1.4-F) so beat detection and focus resolution run
        exactly once per planning phase.
        """
        if beats is None:
            beats = AutoPublishPipeline._beat_inputs(plan)
        if focus_results is None:
            focus_results = AutoPublishPipeline._focus_results(plan, beats)
        motion_lowerer = SemanticMotionLowerer()
        transition_resolver = SemanticTransitionResolver()
        contexts: list[dict[str, Any]] = []
        for index, (scene, beat) in enumerate(zip(plan.scenes, beats)):
            visual = scene.visual or VisualScene()
            focus = focus_results[index]
            subject = focus.emphasis_target or focus.primary or beat.subject
            intent = {
                "HOOK": "reveal",
                "PROBLEM": "reveal_decline",
                "CONTRAST": "compare",
                "SOLUTION": "emphasize_growth",
                "CTA": "emphasize",
                "EXPLANATION": "emphasize",
                "EXAMPLE": "reveal",
            }.get(beat.type, "")
            parameters: dict[str, Any] = {}
            if intent == "compare":
                parameters["subjects"] = [item for item in (focus.primary, focus.secondary) if item]
            motion_result = motion_lowerer.lower(
                SemanticMotionSpec(subject=subject, intent=intent, duration=1.0, parameters=parameters),
                characters=visual.characters,
                objects=visual.objects,
                text_elements=visual.text_elements,
                visual_focus=focus,
            ) if intent else None
            next_transition = None
            if index + 1 < len(beats) and visual.transition is None:
                next_transition = transition_resolver.resolve(beat, beats[index + 1])
            contexts.append({
                "beat": beat,
                "focus": focus,
                "motion_result": motion_result,
                "transition": next_transition,
            })
        return contexts

    @staticmethod
    def _plan_visual_story(
        plan: VideoPlan,
        *,
        beats: list[Any],
        focus_results: dict[int, Any],
    ) -> dict[str, Any]:
        """Run the V1.4-A..E planning stack once per planning phase.

        Advisory only: every planner is read-only and never mutates scenes,
        and explicit scene intent (motions, camera, transitions) always
        outranks recommendations -- that precedence is encoded inside each
        planner, so nothing here replaces an existing decision. Beat and
        focus results are consumed, never recomputed.

        Planner services are imported lazily (mirroring the existing
        _semantic_contexts convention) because they import ScenePlan from
        this module; module-level imports would create an import cycle.
        """
        from src.services.attention_planner import AttentionPlanner
        from src.services.camera_planner import CameraPlanner
        from src.services.composition_planner import CompositionPlanner
        from src.services.visual_diversity import VisualDiversityPolicy
        from src.services.visual_story_planner import VisualStoryPlanner

        scenes = list(plan.scenes or [])
        focus_list = [focus_results.get(index) for index in range(len(scenes))]
        story_plan = VisualStoryPlanner().plan(scenes, beats=beats, focuses=focus_list)
        diversity_report = VisualDiversityPolicy().analyze(scenes, story_plan=story_plan)
        composition_plan = CompositionPlanner().plan(
            scenes, story_plan=story_plan, diversity_report=diversity_report
        )
        camera_plan = CameraPlanner().plan(
            scenes,
            story_plan=story_plan,
            diversity_report=diversity_report,
            composition_plan=composition_plan,
        )
        attention_plan = AttentionPlanner().plan(
            scenes,
            story_plan=story_plan,
            diversity_report=diversity_report,
            composition_plan=composition_plan,
            camera_plan=camera_plan,
            focus_results=focus_results,
        )
        return {
            "story_plan": story_plan,
            "diversity_report": diversity_report,
            "composition_plan": composition_plan,
            "camera_plan": camera_plan,
            "attention_plan": attention_plan,
        }

    @staticmethod
    def _decision_maps(
        planning: dict[str, Any],
    ) -> dict[str, dict[int, dict[str, Any]]]:
        """Convert each plan's per-scene decisions into index -> dict maps."""
        def by_index(plan_obj: Any) -> dict[int, dict[str, Any]]:
            mapped: dict[int, dict[str, Any]] = {}
            for decision in getattr(plan_obj, "decisions", ()) or ():
                to_dict = getattr(decision, "to_dict", None)
                mapped[decision.scene_index] = (
                    to_dict() if callable(to_dict) else asdict(decision)
                )
            return mapped

        return {
            "story": by_index(planning["story_plan"]),
            "diversity": by_index(planning["diversity_report"]),
            "composition": by_index(planning["composition_plan"]),
            "camera": by_index(planning["camera_plan"]),
            "attention": by_index(planning["attention_plan"]),
        }

    @staticmethod
    def _merge_visual_planning(
        semantic_contexts: list[dict[str, Any]],
        planning: dict[str, Any],
    ) -> None:
        """Attach V1.4 planning metadata to semantic contexts additively.

        Only a new ``visual_planning`` key is added. Existing V1.3 semantic
        keys (beat, focus, motion_result, transition) are never replaced, and
        recommendations are recorded as advisory metadata -- never applied
        over explicit scene intent.
        """
        maps = AutoPublishPipeline._decision_maps(planning)
        for index, context in enumerate(semantic_contexts):
            story = maps["story"].get(index, {})
            context["visual_planning"] = {
                "scene_index": index,
                "treatment": story.get("treatment"),
                "recommended_motions": list(story.get("preferred_motion_types") or ()),
                "recommended_camera": story.get("camera_pattern"),
                "recommended_transition": story.get("transition_type"),
                "diversity": maps["diversity"].get(index),
                "composition": maps["composition"].get(index),
                "camera": maps["camera"].get(index),
                "attention": maps["attention"].get(index),
            }

    def _render_visual_scene(
        self,
        scene: ScenePlan,
        segment: dict[str, Any],
        scene_number: int,
        duration: float,
        video_format: VideoFormat,
        stickman_renderer: StickmanRenderer,
        semantic_context: dict[str, Any] | None = None,
        total_scenes: int = 0,
    ) -> dict[str, Any]:
        """Render a scene with visual intent using StickmanRenderer."""
        from src.models.content_package import AudioRequest, RenderConfig, RenderJobSpec

        visual = scene.visual

        # Build RenderConfig (StickmanRenderer uses hardcoded background; config params are for output path/sizing)
        config = RenderConfig(
            width=video_format.width,
            height=video_format.height,
            fps=video_format.fps,
            aspect_ratio="9:16" if video_format.is_vertical else "16:9",
            output_directory=self.scene_directory,
        )

        # Build AudioRequest from TTS segment
        audio_request = AudioRequest(
            scene_number=scene_number,
            duration_seconds=int(duration),
            narration_text=scene.narration,
            voice_reference=segment.get("audio_reference", ""),
            background_music_reference="",
            sound_effect_references=[],
            audio_format="aac",
        )

        # Build motions list from visual.motions (already parsed as Motion objects).
        # Structured scene fields are the canonical path. Only use legacy text-based
        # motion fallbacks when no structured composition is present.
        motions = visual.motions.copy()
        # V1.5: per-scene application decision (set only when the V1.5 layer runs).
        vpa_decision = None
        # V1.6-A: per-scene background variation decision (set only when the
        # V1.6 layer runs).
        bgv_decision = None
        if semantic_context and semantic_context.get("motion_result"):
            motions.extend(semantic_context["motion_result"].motions)
        structured_visual = (
            bool(getattr(visual, "characters", None))
            or bool(getattr(visual, "objects", None))
            or bool(getattr(visual, "environment", None))
            or bool(getattr(visual, "text_elements", None))
            or bool(getattr(visual, "visual_effects", None))
            or bool(getattr(visual, "camera_spec", None))
        )

        legacy_visual_prompt = visual.visual_prompt
        legacy_animation_instructions = visual.animation_instructions
        legacy_camera_instructions = visual.camera_instructions

        if structured_visual:
            legacy_visual_prompt = ""
            legacy_animation_instructions = ""
            legacy_camera_instructions = ""
        else:
            # Add legacy character action and camera motion only when structured
            # scene composition is not present, preserving backwards compatibility.
            if visual.character_action and visual.character_action != "idle":
                character_motion = Motion(
                    type="emphasize",
                    target="character",
                    start_time=0.0,
                    duration=duration,
                    easing="ease_in_out",
                    parameters={"action": visual.character_action},
                )
                motions.append(character_motion)

            if visual.camera_pattern and visual.camera_pattern not in {"hold", "static"}:
                camera_type = "zoom"
                camera_params = {"from": 1.0, "to": 1.5}
                if visual.camera_pattern in {"zoom_in", "zoom"}:
                    camera_type = "zoom"
                    camera_params = {"from": 1.0, "to": 1.5}
                elif visual.camera_pattern == "zoom_out":
                    camera_type = "zoom"
                    camera_params = {"from": 1.5, "to": 1.0}
                elif visual.camera_pattern in {"pan", "tracking", "follow"}:
                    camera_type = "pan"
                    camera_params = {"from": {"x": 0.0, "y": 0.0}, "to": {"x": 0.15, "y": 0.0}}

                camera_motion = Motion(
                    type=camera_type,
                    target="camera",
                    start_time=0.0,
                    duration=duration,
                    easing="ease_in_out",
                    parameters=camera_params,
                )
                motions.append(camera_motion)

        # Build transition
        transition_to_next = visual.transition
        if transition_to_next is None and semantic_context:
            transition_to_next = semantic_context.get("transition")
        if transition_to_next is None and visual.camera_pattern in {"pan", "tracking", "follow"}:
            transition_to_next = Transition(type="crossfade", duration=0.5)

        # Structured visual description consumed by StickmanRenderer.
        visual_description: dict[str, Any] | None = None
        if structured_visual:
            visual_description = self._stage_structured_visual(
                visual,
                duration,
                transition_to_next,
            )
            if semantic_context:
                motion_result = semantic_context.get("motion_result")
                visual_description["semantics"] = {
                    "beat": semantic_context["beat"].to_dict(),
                    "focus": semantic_context["focus"].to_dict(),
                    "motions": [motion.to_dict() for motion in motion_result.motions] if motion_result else [],
                    "transition": transition_to_next.to_dict() if transition_to_next else None,
                }
                from src.services.visual_qa import VisualQAService

                qa_report = VisualQAService().check_composition(visual_description, scene=f"scene_{scene_number:03d}")
                visual_description["qa_report"] = qa_report.to_dict()
                if semantic_context.get("visual_planning"):
                    # V1.4-F: advisory planning metadata reaches staging
                    # additively; explicit scene intent is never replaced.
                    visual_description["visual_planning"] = semantic_context["visual_planning"]
                    # V1.5: apply safe V1.4 recommendations to staging inputs
                    # (camera pattern/focus_target, composition metadata) before
                    # RenderJobSpec construction. Gated by the V1.5 flag AND by
                    # the presence of V1.4 planning metadata, so it never runs
                    # when V1.4 is disabled. Explicit scene intent always wins.
                    import src.services.visual_planning_application as vpa_mod

                    if vpa_mod.VISUAL_PLANNING_APPLICATION_ENABLED:
                        applied_desc, vpa_decision = vpa_mod.apply_visual_planning(
                            visual_description,
                            semantic_context["visual_planning"],
                            scene_index=int(
                                semantic_context["visual_planning"].get("scene_index") or 0
                            ),
                        )
                        visual_description = applied_desc
                        visual_description["visual_planning_application"] = vpa_decision.to_dict()

            # V1.6-A: deterministic background/environment variation. Scenes
            # without explicit environment intent stop falling back to the
            # identical outdoor default backdrop, and adjacent scenes never
            # share one. Gated by its own feature flag and independent of the
            # V1.3 semantic pipeline and the V1.4/V1.5 planning stack; explicit
            # environment intent is never overwritten.
            import src.services.background_variation as bgv_mod

            if bgv_mod.VISUAL_BACKGROUND_VARIATION_ENABLED:
                bgv_total = (
                    int(total_scenes)
                    if int(total_scenes) > 0
                    else max(int(scene_number), 1)
                )
                staged_desc, bgv_decision = bgv_mod.apply_background_variation(
                    visual_description,
                    scene_index=max(int(scene_number) - 1, 0),
                    total_scenes=bgv_total,
                )
                visual_description = staged_desc
                visual_description["background_variation"] = bgv_decision.to_dict()

        # Create RenderJobSpec
        job_spec = RenderJobSpec(
            job_id=f"scene_{scene_number:03d}",
            scene_number=scene_number,
            duration_seconds=int(duration),
            render_type="stickman_animation",
            character_ids=[],
            asset_ids=[],
            visual_prompt=legacy_visual_prompt,
            animation_instructions=legacy_animation_instructions,
            camera_instructions=legacy_camera_instructions,
            audio_requirements="",
            motions=motions,
            transition_to_next=transition_to_next,
            audio_request=audio_request,
            visual_description=visual_description,
        )

        # Render using StickmanRenderer via render_stickman_job function
        from src.services.stickman_renderer import render_stickman_job
        record = render_stickman_job(job_spec, config)
        if isinstance(record, dict):
            if "scene_number" not in record:
                record["scene_number"] = scene_number
            if "transition_to_next" not in record and job_spec.transition_to_next is not None:
                transition = job_spec.transition_to_next
                record["transition_to_next"] = transition.to_dict() if hasattr(transition, "to_dict") else dict(transition)
            if vpa_decision is not None:
                # V1.5: per-scene application decision surfaces on the render
                # record for pipeline-level observability and validation.
                record["visual_planning_application"] = vpa_decision.to_dict()
            if bgv_decision is not None:
                # V1.6-A: per-scene background variation decision surfaces on
                # the render record for pipeline-level observability.
                record["background_variation"] = bgv_decision.to_dict()
        return record

    @staticmethod
    def _stage_structured_visual(
        visual: VisualScene,
        duration: float,
        transition: Transition | None,
    ) -> dict[str, Any]:
        """Apply presentation staging before the structured render handoff."""
        characters: list[dict[str, Any]] = []
        for character in getattr(visual, "characters", []) or []:
            staged = character.to_dict() if hasattr(character, "to_dict") else dict(character)
            # V1.2: larger characters framed inside the central composition.
            staged["scale"] = min(3.0, float(staged.get("scale", 1.0)) * 1.25)
            staged["x"] = max(0.15, min(0.85, float(staged.get("x", 0.5))))
            staged["y"] = min(0.84, max(0.58, float(staged.get("y", 0.75)) - 0.06))
            characters.append(staged)

        objects = [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in (getattr(visual, "objects", []) or [])
        ]
        if visual.scene_role == "object_interaction" and characters and objects:
            target_x = float(objects[0].get("x", 0.5))
            # V1.2: approach the interacted object from whichever side the
            # character is already on, closing in without crossing behind it.
            offset = -0.20 if float(characters[0].get("x", 0.5)) <= target_x else 0.20
            characters[0]["x"] = max(0.15, min(0.85, target_x + offset))
            # Keep the focal object inside the central vertical band too.
            objects[0]["y"] = min(0.78, max(0.30, float(objects[0].get("y", 0.5))))

        # V1.2.1: large floor props (scale > 1.0, standing on the ground)
        # claim a footprint that characters may not stand inside -- this is
        # what previously let characters overlap desks/boards ("speed-line"
        # style clutter). Characters are pushed to the clearest side.
        claims = [
            (float(obj.get("x", 0.5)), 0.16 * float(obj.get("scale", 1.0)) + 0.02)
            for obj in objects
            if float(obj.get("scale", 1.0)) > 1.0
            and float(obj.get("y", 0.5)) >= 0.55
        ]
        if claims:
            gap = 0.09

            def _clearance(pos: float) -> float:
                return min(
                    (abs(pos - float(obj.get("x", 0.5))) for obj in objects),
                    default=1.0,
                )

            for staged in characters:
                cx = float(staged.get("x", 0.5))
                for claim in claims:
                    ox, half = claim
                    if not (ox - half <= cx <= ox + half):
                        continue
                    options = [
                        pos
                        for pos in (ox - half - gap, ox + half + gap)
                        if 0.05 <= pos <= 0.95
                        and all(
                            not (o - h - gap <= pos <= o + h + gap)
                            for o, h in claims
                            if (o, h) != claim
                        )
                    ]
                    if options:
                        cx = max(options, key=_clearance)
                    else:
                        cx = ox - half - gap if cx <= ox else ox + half + gap
                    staged["x"] = round(max(0.05, min(0.95, cx)), 4)
                    break

        text_elements: list[dict[str, Any]] = []
        fade_out = float(transition.duration) if transition and transition.type != "cut" else 0.0
        for text in getattr(visual, "text_elements", []) or []:
            staged = text.to_dict() if hasattr(text, "to_dict") else dict(text)
            if fade_out > 0.0:
                staged["duration"] = duration
                staged["fade_out"] = max(float(staged.get("fade_out", 0.0)), fade_out)
            text_elements.append(staged)

        return {
            "characters": characters,
            "objects": objects,
            "environment": dict(getattr(visual, "environment", {}) or {}),
            "text_elements": text_elements,
            "effects": [
                item.to_dict() if hasattr(item, "to_dict") else dict(item)
                for item in (getattr(visual, "visual_effects", []) or [])
            ],
            "camera": dict(getattr(visual, "camera_spec", {}) or {}),
        }

    def _assemble(
        self, render_outputs: list[dict[str, Any]], video_format: VideoFormat
    ) -> dict[str, Any]:
        """Concatenate scene clips into a single silent video."""
        config = RenderConfig(
            width=video_format.width,
            height=video_format.height,
            fps=video_format.fps,
            aspect_ratio="9:16" if video_format.is_vertical else "16:9",
            output_directory=self.output_directory,
        )
        assembler = VideoAssembler(config=config, execute_enabled=True)
        result = assembler.assemble(render_outputs)
        if result.get("status") != "completed":
            return {
                "status": "failed",
                "stage": "assembly",
                "error": result.get("error", "Video assembly failed"),
                "details": result,
            }
        return {"status": "completed", "output_reference": result["output_reference"]}

    def _concat_audio(self, audio_paths: list[str]) -> dict[str, Any]:
        """Concatenate narration segments into a single audio track."""
        output_path = os.path.join(self.output_directory, "narration.wav")
        if len(audio_paths) == 1:
            return {"status": "completed", "audio_reference": audio_paths[0]}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as handle:
            for path in audio_paths:
                escaped = os.path.abspath(path).replace("'", "\\'")
                handle.write(f"file '{escaped}'\n")
            concat_file = handle.name

        command = [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_file,
            "-c",
            "copy",
            output_path,
        ]
        try:
            result = subprocess.run(
                command, shell=False, capture_output=True, text=True, timeout=600
            )
        finally:
            os.unlink(concat_file)

        if result.returncode != 0 or not os.path.exists(output_path):
            return {
                "status": "failed",
                "stage": "audio_concat",
                "error": f"FFmpeg failed with return code {result.returncode}",
                "stderr": (result.stderr or "")[:500],
            }
        return {"status": "completed", "audio_reference": output_path}

    def _upload(self, plan: VideoPlan, video_path: str) -> dict[str, Any]:
        """Publish the rendered video to YouTube."""
        service = self.upload_service or YouTubeUploadService(
            credentials=OAuthCredentials.from_env()
        )
        request = UploadRequest(
            video_path=video_path,
            title=plan.title,
            description=plan.description,
            tags=plan.tags,
            category_id=plan.category_id,
            privacy_status=plan.privacy_status,
        )
        try:
            return service.upload(request)
        except Exception as error:  # noqa: BLE001 - reported in the run result
            logger.error(f"Upload failed: {error}")
            return {"status": "failed", "error": str(error)}
