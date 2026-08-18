"""Single Job Renderer.

Provides a simple API to render a single RenderJobSpec to a real MP4 file
using the existing FFmpegRenderer pipeline.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from src.agents.render_job_executor import RenderRequest
from src.models.content_package import AudioRequest, RenderConfig, RenderJobSpec
from src.services.ffmpeg_renderer import FFmpegRenderer


def render_single_job(
    job_spec: RenderJobSpec,
    config: RenderConfig | None = None,
) -> dict[str, Any]:
    """Render a single RenderJobSpec to a real MP4 file.

    Args:
        job_spec: The render job specification
        config: Optional render configuration. If not provided, uses defaults.

    Returns:
        Dictionary with render result information including:
        - job_id: The job identifier
        - status: "completed" or "failed"
        - output_reference: Path to the generated MP4 file
        - duration_seconds: Duration of the rendered video
        - error: Error message if failed
    """
    # Use default config if not provided
    if config is None:
        config = RenderConfig()

    # Convert RenderJobSpec to the format expected by FFmpegRenderer
    job_dict = job_spec.to_dict()

    # Create a temporary output directory if not specified in config
    # The FFmpegRenderer will use config.output_directory
    output_dir = config.output_directory
    os.makedirs(output_dir, exist_ok=True)

    # Create FFmpegRenderer with execution enabled
    renderer = FFmpegRenderer(execute_enabled=True)

    # Create RenderRequest
    request = RenderRequest(
        job=job_dict,
        render_config=config,
        resolved_assets=[],  # No assets for simple test
        resolved_characters=[],  # No characters for simple test
    )

    # Execute the render
    result = renderer.render(request)

    return result


def render_single_job_to_temp(
    job_spec: RenderJobSpec,
    config: RenderConfig | None = None,
) -> dict[str, Any]:
    """Render a single RenderJobSpec to a temporary MP4 file.

    This is a convenience function that creates a temporary directory
    for the output and cleans it up after rendering.

    Args:
        job_spec: The render job specification
        config: Optional render configuration. If not provided, uses defaults.

    Returns:
        Dictionary with render result information including:
        - job_id: The job identifier
        - status: "completed" or "failed"
        - output_reference: Path to the generated MP4 file
        - duration_seconds: Duration of the rendered video
        - error: Error message if failed
    """
    # Create a temporary directory for output
    with tempfile.TemporaryDirectory() as tmpdir:
        # Use provided config or create a new one with temp directory
        if config is None:
            temp_config = RenderConfig(output_directory=tmpdir)
        else:
            # Create a copy with the temp directory
            temp_config = RenderConfig(
                width=config.width,
                height=config.height,
                fps=config.fps,
                aspect_ratio=config.aspect_ratio,
                video_format=config.video_format,
                video_codec=config.video_codec,
                audio_format=config.audio_format,
                output_directory=tmpdir,
                filename_template=config.filename_template,
            )

        # Render the job
        result = render_single_job(job_spec, temp_config)

        # If successful, copy the output to a more permanent location
        # For now, we return the result with the temp path
        # The caller can copy it if needed
        return result