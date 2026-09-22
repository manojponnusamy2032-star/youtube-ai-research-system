"""YairsRendererAdapter — thin adapter over the EXISTING YAIRS render pipeline.

Entry point:

    VisualPlan (orchestration)
        -> YairsRendererAdapter
        -> RenderPipelineOrchestrator (existing)
        -> StickmanRenderer (existing, real procedural renderer)
        -> FinalMediaOrchestrator -> VideoAssembler + MediaMuxer (existing)
        -> MP4 (VideoArtifact)

The wiring below mirrors the production wiring in ``src/api/dependencies.py``
(RenderJobManager -> RenderJobExecutor(StickmanRenderer, TTSAudioRenderer) ->
RenderOutputManager -> FinalMediaOrchestrator(VideoAssembler, TTS, MediaMuxer))
so the adapter calls the same production path without duplicating the
renderer implementations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.adapters.renderer.base import RendererAdapter
from src.core.context import WorkflowContext
from src.models.content_package import AudioRequest
from src.orchestration.schemas.production import ProductionRequest, VideoArtifact

_RENDER_CONFIG_KEYS = ("width", "height", "fps", "aspect_ratio", "video_format", "video_codec", "audio_format")


def _render_config_dict(request: ProductionRequest) -> dict[str, Any]:
    """Return only the RenderConfig-compatible keys for the WorkflowContext."""
    return {key: value for key, value in request.render_config.items() if key in _RENDER_CONFIG_KEYS}
class YairsRendererAdapter(RendererAdapter):
    """Calls the existing YAIRS rendering path to produce a real MP4."""

    def __init__(
        self,
        render_pipeline_orchestrator: Any | None = None,
        tts_service: Any | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            render_pipeline_orchestrator: Optional pre-wired
                ``RenderPipelineOrchestrator`` (used by tests to inject a mock).
            tts_service: Optional TTS service.  Defaults to the production TTS
                wiring (Windows System.Speech when usable, mock otherwise).
        """
        if render_pipeline_orchestrator is None:
            from src.agents.render_job_executor import RenderJobExecutor
            from src.agents.render_job_manager import RenderJobManager
            from src.agents.render_output_manager import RenderOutputManager
            from src.agents.render_pipeline_orchestrator import RenderPipelineOrchestrator
            from src.services.final_media_orchestrator import FinalMediaOrchestrator
            from src.services.media_muxer import MediaMuxer
            from src.services.stickman_renderer import StickmanRenderer
            from src.services.system_speech_tts_service import SystemSpeechTTSService
            from src.services.tts_audio_renderer import TTSAudioRenderer
            from src.services.tts_service import MockTTSService
            from src.services.video_assembler import VideoAssembler

            if tts_service is None:
                system_tts = SystemSpeechTTSService(output_directory="output/audio")
                tts_service = system_tts if system_tts.is_available() else MockTTSService(output_directory="output/audio")

            tts_audio_renderer = TTSAudioRenderer(tts_service=tts_service)
            final_media_orchestrator = FinalMediaOrchestrator(
                video_assembler=VideoAssembler(execute_enabled=True),
                audio_renderer=tts_audio_renderer,
                media_muxer=MediaMuxer(execute_enabled=True),
            )
            render_pipeline_orchestrator = RenderPipelineOrchestrator(
                render_job_manager=RenderJobManager(),
                render_job_executor=RenderJobExecutor(
                    renderer=StickmanRenderer(execute_enabled=True),
                    audio_renderer=tts_audio_renderer,
                ),
                render_output_manager=RenderOutputManager(),
                final_media_orchestrator=final_media_orchestrator,
            )
        self.render_pipeline_orchestrator = render_pipeline_orchestrator
        self.tts_service = tts_service

    # -- interface -----------------------------------------------------------

    def run(self, request: ProductionRequest) -> VideoArtifact:
        """Render a VisualPlan through the existing YAIRS pipeline."""
        output_path = Path(request.output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        context = WorkflowContext()
        context.set("render_job_plan", request.visual_plan.render_job_plan)
        context.set("render_config", _render_config_dict(request))
        context.set("run_final_media_generation", True)
        context.set("final_media_output_path", str(output_path))

        # The existing FinalMediaOrchestrator muxes the assembled video with a
        # single narration track (audio_requests[0]) and FFmpeg -shortest.
        # Provide the combined narration for the whole video through the
        # pipeline's context-level ``audio_requests`` override so the final MP4
        # spans every scene instead of being trimmed to scene 1's narration.
        combined = self._combined_final_audio_request(request.visual_plan)
        if combined is not None:
            context.set("audio_requests", [combined])

        result = self.render_pipeline_orchestrator.run(context)

        final_media = context.get("final_media_result") or {}
        scene_count = len(request.visual_plan.scenes)
        if (
            getattr(result, "success", False)
            and final_media.get("status") == "completed"
            and output_path.exists()
        ):
            return VideoArtifact(
                job_id=request.job_id,
                status="completed",
                output_path=str(output_path),
                mp4_exists=True,
                file_size_bytes=output_path.stat().st_size,
                scene_count=scene_count,
                total_duration_seconds=request.visual_plan.total_duration_seconds,
                details={
                    "final_media": final_media,
                    "render_outputs": context.get("render_outputs", []),
                    "adapter": self.__class__.__name__,
                },
            )

        error = final_media.get("error") if isinstance(final_media, dict) else None
        if not error and isinstance(result, dict):
            error = result.get("error")
        return VideoArtifact(
            job_id=request.job_id,
            status="failed",
            output_path=str(output_path),
            mp4_exists=output_path.exists(),
            scene_count=scene_count,
            total_duration_seconds=request.visual_plan.total_duration_seconds,
            details={
                "error": error or "render pipeline did not complete",
                "final_media": final_media,
                "adapter": self.__class__.__name__,
            },
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _combined_final_audio_request(visual_plan: Any) -> AudioRequest | None:
        """Build one AudioRequest covering all scene narrations.

        Returns ``None`` when no scene carries narration, leaving the pipeline's
        default audio-request extraction untouched.
        """
        narrations = [
            str(scene.narration).strip()
            for scene in visual_plan.scenes
            if str(getattr(scene, "narration", "")).strip()
        ]
        if not narrations:
            return None
        return AudioRequest(
            scene_number=1,
            duration_seconds=int(visual_plan.total_duration_seconds),
            narration_text=" ".join(narrations),
            voice_reference="default",
            background_music_reference="",
            sound_effect_references=[],
            audio_format="aac",
        )