"""Audit launcher: runs the REAL YAIRS production pipeline (research -> content gen
-> render -> assembly) for a single 30-60s video, reusing generate_audit_videos
exactly. The ONLY deviation from the production default is a runtime RenderConfig
patch (720p @ 24fps) to keep the pure-Python stickman frame generator tractable;
this is a launcher-level adjustment, not a source modification.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

# --- Tractable runtime render config (no source files modified) ---
from dataclasses import dataclass
import src.models.content_package as cp
import src.agents.render_job_executor as rje


@dataclass
class AuditRenderConfig(cp.RenderConfig):
    """720p @ 24fps -- a realistic faceless-video resolution that the pure-Python
    frame generator can complete in bounded time while still exposing real
    composition / animation / transition behaviour."""
    width: int = 1280
    height: int = 720
    fps: int = 24


rje.RenderConfig = AuditRenderConfig

# Verify the patch took effect (read by the executor's _get_render_config fallback).
_rc = rje.RenderConfig()
print(f"[audit-launcher] RenderConfig patched -> {_rc.width}x{_rc.height}@{_rc.fps}fps "
      f"codec={_rc.video_codec} fmt={_rc.video_format}", flush=True)

if __name__ == "__main__":
    from generate_audit_videos import generate_video

    # Storytelling, 45s -> ~3 scenes (15s each), 2 transitions: a strong audit sample.
    generate_video(
        topic="the untold story of stickman fight animations",
        duration_sec=45,
        style="storytelling",
        output_filename="audit_storytelling.mp4",
    )
