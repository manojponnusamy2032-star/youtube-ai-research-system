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
from dataclasses import dataclass, field
from typing import Any

from src.models.content_package import RenderConfig
from src.services.media_muxer import MediaMuxer
from src.services.piper_tts_service import PiperTTSService
from src.services.scene_video_renderer import (
    FORMATS,
    SHORTS_FORMAT,
    SceneVideoRenderer,
    VideoFormat,
)
from src.services.tts_service import TTSRequest, TTSService
from src.services.video_assembler import VideoAssembler
from src.services.youtube_upload_service import (
    OAuthCredentials,
    UploadRequest,
    YouTubeUploadService,
)

logger = logging.getLogger(__name__)

SCENE_PADDING_SECONDS = 0.4


@dataclass
class ScenePlan:
    """A single narrated scene of the video plan."""

    narration: str
    caption: str = ""
    background_image: str | None = None

    def __post_init__(self) -> None:
        """Validate the scene and default the caption to the narration."""
        if not self.narration.strip():
            raise ValueError("scene narration cannot be empty")
        if not self.caption.strip():
            self.caption = self.narration

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
        scenes = [ScenePlan(**scene) for scene in payload.get("scenes", [])]
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
        for scene, segment in zip(plan.scenes, segments):
            record = self.scene_renderer.render_scene(
                scene_number=segment["scene_number"],
                text=scene.display_caption,
                duration_seconds=segment["duration_seconds"] + SCENE_PADDING_SECONDS,
                video_format=plan.format,
                background_image=scene.background_image,
            )
            if record.get("status") != "completed":
                return {
                    "status": "failed",
                    "stage": "scene_render",
                    "error": record.get("error", "Scene render failed"),
                    "scene_number": segment["scene_number"],
                    "details": record,
                }
            render_outputs.append(record)
        return {"status": "completed", "render_outputs": render_outputs}

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
