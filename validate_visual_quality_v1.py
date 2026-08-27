"""Validate the rendered Visual Quality v1 output with ffprobe."""

from __future__ import annotations

import glob
import json
import os
import subprocess
import sys

base = r"d:\youtube-ai-research-system\youtube-ai-research-system\output\visual_quality_v1"


def probe(path: str, query: str) -> str:
    result = subprocess.run(
        ["ffprobe", "-v", "error", *query.split(), str(path)],
        shell=False, capture_output=True, text=True, check=False,
    )
    return result.stdout.strip()


report: dict[str, object] = {"ok": True, "checks": []}


def check(name: str, passed: bool, detail: str = "") -> None:
    report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})  # type: ignore[attr-defined]
    if not passed:
        report["ok"] = False  # type: ignore[attr-defined]
    print(f"{'PASS' if passed else 'FAIL'}  {name}  {detail}")


final = os.path.join(base, "final_with_audio.mp4")
scene_glob = glob.glob(os.path.join(base, "scenes", "scene_*.mp4"))
scene_glob = [p for p in scene_glob if ".temp_video" not in p]

if os.path.exists(final):
    vcodec = probe(final, "-select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1")
    w = probe(final, "-select_streams v:0 -show_entries stream=width -of default=noprint_wrappers=1:nokey=1")
    h = probe(final, "-select_streams v:0 -show_entries stream=height -of default=noprint_wrappers=1:nokey=1")
    fps = probe(final, "-select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1")
    acodec = probe(final, "-select_streams a:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1")
    dur = probe(final, "-show_entries format=duration -of default=noprint_wrappers=1:nokey=1")
    check("video codec h264", vcodec == "h264", vcodec)
    check("resolution 1080x1920", w == "1080" and h == "1920", f"{w}x{h}")
    check("fps 30", fps.startswith("30"), fps)
    check("audio codec aac", acodec == "aac", acodec)
    check("has duration", float(dur) > 0, dur)

check("scene count == 10", len(scene_glob) == 10, str(len(scene_glob)))

order_ok = True
prev = 0
for p in sorted(scene_glob):
    name = os.path.basename(p)
    try:
        num = int(name.split("_")[1].split(".")[0])
    except Exception:
        num = -1
    if num <= prev:
        order_ok = False
    prev = num
check("scenes in ascending order", order_ok, ", ".join(os.path.basename(p) for p in sorted(scene_glob)))

for p in sorted(scene_glob):
    vcodec = probe(p, "-select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1")
    w = probe(p, "-select_streams v:0 -show_entries stream=width -of default=noprint_wrappers=1:nokey=1")
    h = probe(p, "-select_streams v:0 -show_entries stream=height -of default=noprint_wrappers=1:nokey=1")
    fps = probe(p, "-select_streams v:0 -show_entries stream=r_frame_rate -of default=noprint_wrappers=1:nokey=1")
    check(f"scene {os.path.basename(p)} streams",
          vcodec == "h264" and w == "1080" and h == "1920" and fps.startswith("30"),
          f"{vcodec} {w}x{h} {fps}")

audio_dir = os.path.join(base, "audio")
wavs = glob.glob(os.path.join(audio_dir, "*.wav"))
check("narration segments == 10", len(wavs) == 10, str(len(wavs)))

with open(os.path.join(base, "validation_report.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)
print("\nREPORT:", "ALL PASS" if report["ok"] else "FAILURES PRESENT")