"""Render the 10-scene Visual Quality v1 demo end to end.

Uses a deterministic silent-WAV TTS stub (real .wav files written via the
``wave`` stdlib module) so the complete AutoPublishPipeline runs locally
without Piper. Scene visuals are the new VisualScene composition fields.
"""

from __future__ import annotations

import math
import os
import sys
import wave
from typing import Any

PROJECT_ROOT = r"d:\youtube-ai-research-system\youtube-ai-research-system"
sys.path.insert(0, PROJECT_ROOT)

from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, VideoPlan
from src.services.tts_service import TTSRequest, TTSService

CHARS_PER_SECOND = 13.0
SAMPLE_RATE = 16000


class SilentWavTTSService(TTSService):
    """Deterministic local TTS stub that writes real silent WAV files."""

    def __init__(self, output_directory: str) -> None:
        self.output_directory = output_directory

    def generate(self, request: TTSRequest) -> dict[str, Any]:
        os.makedirs(self.output_directory, exist_ok=True)
        idx = len(os.listdir(self.output_directory))
        out_path = os.path.join(self.output_directory, f"nar_{idx:03d}.wav")
        duration = max(1.0, len(request.text) / CHARS_PER_SECOND)
        frames = int(duration * SAMPLE_RATE)
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"\x00\x00" * frames)
        return {
            "status": "completed",
            "audio_reference": os.path.abspath(out_path),
            "duration_seconds": round(duration, 2),
        }


def main() -> None:
    plan_path = os.path.join(PROJECT_ROOT, "examples", "plan_visual_quality_v1.json")
    out_dir = os.path.join(PROJECT_ROOT, "output", "visual_quality_v1")
    audio_dir = os.path.join(out_dir, "audio")

    plan = VideoPlan.from_file(plan_path)
    print(f"Loaded plan: {len(plan.scenes)} scenes, format={plan.video_format}")

    tts = SilentWavTTSService(audio_dir)
    pipeline = AutoPublishPipeline(output_directory=out_dir, tts_service=tts)
    result = pipeline.run(plan, upload=False)

    print("\n=== PIPELINE RESULT ===")
    for key in ("status", "stage", "video_path", "duration_seconds", "scene_count"):
        if key in result:
            print(f"  {key}: {result[key]}")
    if result.get("status") != "completed":
        print("Details:", result)
        sys.exit(1)

    final = result["video_path"]
    if os.path.exists(final):
        size_mb = os.path.getsize(final) / (1024 * 1024)
        print(f"  final size: {size_mb:.2f} MB")
    else:
        print("  WARNING: final video file not found")
    print("\nDONE")


if __name__ == "__main__":
    main()