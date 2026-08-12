"""Final media orchestrator service.

Coordinates VideoAssembler, FFmpegAudioRenderer, and MediaMuxer to
produce a final video with audio. Uses dependency injection and respects
the execution configuration of each injected component.
"""

from __future__ import annotations

from typing import Any

from src.models.content_package import AudioRequest
from src.services.audio_renderer import AudioRenderRequest, AudioRenderer
from src.services.media_muxer import MediaMuxer
from src.services.video_assembler import VideoAssembler


class FinalMediaOrchestrator:
    """Orchestrates video assembly, audio rendering, and muxing.

    Coordinates existing services only. Does not force FFmpeg execution —
    it respects the execution configuration of each injected component.
    """

    def __init__(
        self,
        video_assembler: VideoAssembler | None = None,
        audio_renderer: AudioRenderer | None = None,
        media_muxer: MediaMuxer | None = None,
    ) -> None:
        """Initialize the final media orchestrator.

        Args:
            video_assembler: Optional VideoAssembler instance.
            audio_renderer: Optional AudioRenderer instance.
            media_muxer: Optional MediaMuxer instance.
        """
        self.video_assembler = video_assembler or VideoAssembler()
        self.audio_renderer = audio_renderer
        self.media_muxer = media_muxer or MediaMuxer()

    def create_final_media(
        self,
        render_outputs: list[dict[str, Any]],
        audio_requests: list[AudioRequest],
        output_path: str,
    ) -> dict[str, Any]:
        """Create a final video with audio from render outputs and audio requests.

        Args:
            render_outputs: List of render output records for VideoAssembler.
            audio_requests: List of AudioRequest objects. Must contain exactly
                one request for this first implementation.
            output_path: Full path for the final output file.

        Returns:
            Dictionary with the final mux result.

        Raises:
            ValueError: If inputs are invalid.
        """
        self._validate_inputs(render_outputs, audio_requests, output_path)

        # Stage 1 — Video assembly.
        video_result = self.video_assembler.assemble(render_outputs)
        if video_result.get("status") == "failed":
            return {
                "status": "failed",
                "stage": "video",
                "error": video_result.get("error", "Video assembly failed"),
            }
        video_reference = video_result.get("output_reference")
        if not video_reference:
            return {
                "status": "failed",
                "stage": "video",
                "error": "Video assembly produced no output reference",
            }

        # Stage 2 — Audio rendering.
        if self.audio_renderer is None:
            return {
                "status": "failed",
                "stage": "audio",
                "error": "No audio renderer configured",
            }

        audio_request = audio_requests[0]
        audio_render_request = AudioRenderRequest(
            audio_request=audio_request,
            job={},
        )
        audio_result = self.audio_renderer.render(audio_render_request)
        if audio_result.get("status") == "failed":
            return {
                "status": "failed",
                "stage": "audio",
                "error": audio_result.get("error", "Audio rendering failed"),
            }
        audio_reference = audio_result.get("audio_reference")
        if not audio_reference:
            return {
                "status": "failed",
                "stage": "audio",
                "error": "Audio rendering produced no audio reference",
            }

        # Stage 3 — Mux.
        mux_result = self.media_muxer.mux(video_reference, audio_reference, output_path)
        if mux_result.get("status") == "failed":
            return {
                "status": "failed",
                "stage": "mux",
                "error": mux_result.get("error", "Muxing failed"),
            }

        return mux_result

    def _validate_inputs(
        self,
        render_outputs: list[dict[str, Any]],
        audio_requests: list[AudioRequest],
        output_path: str,
    ) -> None:
        """Validate orchestrator inputs.

        Args:
            render_outputs: List of render output records.
            audio_requests: List of AudioRequest objects.
            output_path: Full path for the final output file.

        Raises:
            ValueError: If inputs are invalid.
        """
        if not isinstance(render_outputs, list):
            raise ValueError("render_outputs must be a list")
        if len(render_outputs) == 0:
            raise ValueError("render_outputs cannot be empty")

        if not isinstance(audio_requests, list):
            raise ValueError("audio_requests must be a list")
        if len(audio_requests) == 0:
            raise ValueError("audio_requests cannot be empty")
        if len(audio_requests) > 1:
            raise ValueError("audio_requests must contain exactly one request")

        if not output_path:
            raise ValueError("output_path cannot be empty")