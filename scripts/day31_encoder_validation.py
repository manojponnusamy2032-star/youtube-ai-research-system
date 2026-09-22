"""Day 31 - controlled H.264 encoder preset validation.

Encodes an IDENTICAL raw-frame stream (decoded once from the canonical Day-19
render) through libx264 at several presets with every other parameter fixed.

Nothing here is production code. This script only measures and reports.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "output" / "day19_profiling" / "work" / "output" / "final_video.mp4"
OUTDIR = REPO / "output" / "day31_profiling"

WIDTH = 1920
HEIGHT = 1080
FPS = 30
CRF = "23"
PIX_FMT = "yuv420p"

# "fast" is the ACTUAL current production preset (stickman_renderer.py:996).
PRESETS = ["medium", "fast", "faster", "veryfast"]
BASELINE_PRESET = "fast"

# Representative frame indices across the 1860-frame canonical source.
SAMPLE_FRAMES = [0, 200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800]


def run(cmd, stdin=None):
    """Run a command, return (returncode, stdout_bytes, stderr_text, wall_seconds)."""
    start = time.perf_counter()
    proc = subprocess.Popen(
        cmd, stdin=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    out, err = proc.communicate()
    wall = time.perf_counter() - start
    return proc.returncode, out, (err or b"").decode("utf-8", "replace"), wall


def decode_cmd():
    return [
        "ffmpeg", "-v", "error", "-i", str(SOURCE),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]


def encode_cmd(preset, output):
    return [
        "ffmpeg", "-y", "-v", "info", "-benchmark",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
        "-i", "-",
        "-c:v", "libx264",
        "-preset", preset,
        "-crf", CRF,
        "-pix_fmt", PIX_FMT,
        "-movflags", "+faststart",
        output,
    ]


def null_cmd():
    """Sink encoder: measures the constant decode+pipe cost with no x264 work."""
    return [
        "ffmpeg", "-y", "-v", "info", "-benchmark",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{WIDTH}x{HEIGHT}", "-r", str(FPS),
        "-i", "-", "-f", "null", "-",
    ]


def decode_only_cmd():
    """Decode the source with no pipe and no encoding: pure decode cost."""
    return [
        "ffmpeg", "-v", "info", "-benchmark", "-i", str(SOURCE), "-f", "null", "-",
    ]


def parse_bench(stderr):
    """Extract ffmpeg's own bench line (utime/stime/rtime) if present.

    ffmpeg prints values with a trailing 's' (e.g. ``rtime=1.345000s``), so the
    suffix is stripped before conversion.  CPU time (utime+stime) is the metric
    that is independent of stdin pipe starvation, which matters here because the
    rawvideo pipe can otherwise mask real encoder cost differences.
    """
    for line in stderr.splitlines():
        if line.startswith("bench:"):
            fields = {}
            for token in line.split()[1:]:
                if "=" in token:
                    key, value = token.split("=", 1)
                    cleaned = value.rstrip("s")
                    try:
                        fields[key] = float(cleaned)
                    except ValueError:
                        fields[key] = value
            if "utime" in fields and "stime" in fields:
                try:
                    fields["cpu_time_s"] = round(
                        float(fields["utime"]) + float(fields["stime"]), 3
                    )
                except (TypeError, ValueError):
                    pass
            return fields
    return {}


def parse_stats(stderr):
    """Extract the final ffmpeg progress line (frame count / fps / speed)."""
    stats = {}
    for line in stderr.splitlines():
        if line.startswith("frame=") and "fps=" in line:
            for token in line.split():
                if "=" in token:
                    key, value = token.split("=", 1)
                    stats[key] = value
    return stats


def probe(path):
    rc, out, _, _ = run([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,"
        "nb_frames,duration,sample_rate,channels:format=format_name,duration,size",
        "-of", "json", str(path),
    ])
    if rc != 0 or not out:
        return {"error": "ffprobe_failed"}
    return json.loads(out.decode("utf-8", "replace"))


def extract_frame(path, index):
    rc, out, _, _ = run([
        "ffmpeg", "-v", "error", "-i", str(path),
        "-vf", f"select=eq(n\\,{index})", "-vsync", "0",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ])
    if rc != 0:
        return b""
    return out


def compare_frames(a, b):
    if not a or not b:
        return {"comparable": False}
    if len(a) != len(b):
        return {"comparable": False, "reason": f"length mismatch {len(a)} vs {len(b)}"}
    import numpy as np

    arr_a = np.frombuffer(a, dtype=np.uint8).astype(np.int16)
    arr_b = np.frombuffer(b, dtype=np.uint8).astype(np.int16)
    diff = np.abs(arr_a - arr_b)
    pixels_changed = int((diff.reshape(-1, 3).max(axis=1) > 0).sum())
    total_pixels = arr_a.size // 3
    return {
        "comparable": True,
        "mean_abs_diff": round(float(diff.mean()), 6),
        "max_channel_diff": int(diff.max()),
        "changed_pixels": pixels_changed,
        "total_pixels": total_pixels,
        "changed_pixels_pct": round(pixels_changed / total_pixels * 100.0, 4),
        "sha256": hashlib.sha256(a).hexdigest(),
        "byte_identical_to_baseline": a == b,
    }


def chain(decode_args, encode_args):
    """Pipe decode stdout into encode stdin; measure encode-side wall time.

    Both processes see the EXACT same rawvideo byte stream, so any timing
    difference between presets is attributable to the encoder, not the source.
    """
    decoder = subprocess.Popen(
        decode_args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    start = time.perf_counter()
    encoder = subprocess.Popen(
        encode_args, stdin=decoder.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    decoder.stdout.close()
    out, err = encoder.communicate()
    wall = time.perf_counter() - start
    decoder.wait()
    return encoder.returncode, err.decode("utf-8", "replace"), wall


def quality_vs_source(encoded, source):
    """Global PSNR + SSIM of an encoded file against the source video."""
    result = {}
    for label, flt in (("psnr", "psnr"), ("ssim", "ssim")):
        rc, out, err, _ = run([
            "ffmpeg", "-v", "info", "-i", str(encoded), "-i", str(source),
            "-lavfi", f"[0:v][1:v]{flt}", "-f", "null", "-",
        ])
        text = err or ""
        if label == "psnr":
            for line in text.splitlines():
                if line.startswith("PSNR") and "average:" in line:
                    token = line.split("average:")[1].split()[0]
                    result["psnr_avg_db"] = None if token == "inf" else float(token)
        else:
            for line in text.splitlines():
                if "All:" in line:
                    token = line.split("All:")[1].split()[0]
                    result["ssim_all"] = None if token == "inf" else float(token)
    return result


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def host_facts():
    import os

    rc, out, _, _ = run(["ffmpeg", "-version"])
    first = (out.decode("utf-8", "replace").splitlines() or [""])[0]
    return {
        "cpu_logical": os.cpu_count(),
        "ffmpeg_version_line": first,
    }


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    facts = host_facts()
    print(f"[day31] {facts['ffmpeg_version_line']}", flush=True)
    print(f"[day31] logical cpus = {facts['cpu_logical']}", flush=True)
    print(f"[day31] source = {SOURCE} ({SOURCE.stat().st_size} bytes)", flush=True)

    src_probe = probe(SOURCE)
    src_frames = None
    for stream in src_probe.get("streams", []):
        if stream.get("codec_type") == "video":
            src_frames = stream.get("nb_frames")
            print(
                f"[day31] source video: {stream.get('codec_name')} "
                f"{stream.get('width')}x{stream.get('height')} "
                f"{stream.get('pix_fmt')} frames={src_frames}",
                flush=True,
            )

    # --- Reference point 1: decode + pipe with NO x264 work at all. ---------
    rc, err, wall = chain(decode_cmd(), null_cmd())
    baseline_null = {
        "returncode": rc,
        "wall_s": round(wall, 3),
        "bench": parse_bench(err),
        "stats": parse_stats(err),
        "meaning": "decode source + pipe rawvideo into a null sink (no encoding)",
    }
    print(f"[day31] null sink wall = {wall:.3f}s rc={rc}", flush=True)

    # --- Reference point 0: pure decode, no pipe, no encode. ---------------
    rc_d, out_d, err_d, wall_d = run(decode_only_cmd())
    decode_only = {
        "returncode": rc_d,
        "wall_s": round(wall_d, 3),
        "bench": parse_bench(err_d),
        "stats": parse_stats(err_d),
        "meaning": "decode source into a null sink; no rawvideo pipe, no encoder",
    }
    print(f"[day31] decode-only wall = {wall_d:.3f}s rc={rc_d}", flush=True)

    # --- Reference point 2: re-encode the identical stream per preset. ------
    per_preset = {}
    for preset in PRESETS:
        out_path = OUTDIR / f"encoded_{preset}.mp4"
        rc, err, wall = chain(decode_cmd(), encode_cmd(preset, str(out_path)))
        bench = parse_bench(err)
        entry = {
            "returncode": rc,
            "wall_s": round(wall, 3),
            "bench": bench,
            "stats": parse_stats(err),
            "encode_only_s": bench.get("rtime"),
            "encoder_cpu_s": bench.get("cpu_time_s"),
            "output_bytes": out_path.stat().st_size if out_path.exists() else None,
            "output_sha256": file_sha256(out_path) if out_path.exists() else None,
            "probe": probe(out_path) if out_path.exists() else {},
        }
        # Constant overhead (decode+pipe) comes from the null-sink measurement.
        entry["net_of_decode_s"] = round(max(wall - baseline_null["wall_s"], 0.0), 3)
        # CPU time attributable to x264 itself (subtract the pipe floor's CPU).
        null_cpu = baseline_null["bench"].get("cpu_time_s")
        cpu = entry["encoder_cpu_s"]
        if cpu is not None and null_cpu is not None:
            entry["x264_cpu_s"] = round(max(cpu - null_cpu, 0.0), 3)
        per_preset[preset] = entry
        print(
            f"[day31] preset={preset:9s} wall={wall:8.3f}s "
            f"net_of_decode={entry['net_of_decode_s']:8.3f}s "
            f"x264_cpu={entry.get('x264_cpu_s')}s "
            f"size={entry['output_bytes']} rc={rc}",
            flush=True,
        )

    # --- Frame-level deviation of each preset vs the production baseline. ---
    baseline_path = OUTDIR / f"encoded_{BASELINE_PRESET}.mp4"
    baseline_frames = {}
    for idx in SAMPLE_FRAMES:
        baseline_frames[idx] = extract_frame(str(baseline_path), idx)

    deviation = {}
    for preset in PRESETS:
        if preset == BASELINE_PRESET:
            continue
        path = OUTDIR / f"encoded_{preset}.mp4"
        per_frame = {}
        for idx in SAMPLE_FRAMES:
            per_frame[str(idx)] = compare_frames(
                extract_frame(str(path), idx), baseline_frames[idx]
            )
        deviation[preset] = {
            "vs_preset": BASELINE_PRESET,
            "frames": per_frame,
            "quality_vs_source": quality_vs_source(path, SOURCE),
        }
        print(
            f"[day31] deviation {BASELINE_PRESET}->{preset}: "
            f"psnr={deviation[preset]['quality_vs_source'].get('psnr_avg_db')} "
            f"ssim={deviation[preset]['quality_vs_source'].get('ssim_all')}",
            flush=True,
        )

    baseline_quality = quality_vs_source(baseline_path, SOURCE)

    payload = {
        "day": 31,
        "kind": "controlled libx264 preset validation on an identical raw-frame stream",
        "generated_date_utc": "2026-09-18",
        "provenance": {
            "script": "scripts/day31_encoder_validation.py",
            "script_sha256": file_sha256(__file__),
            "source_video": str(SOURCE.relative_to(REPO)),
            "source_video_sha256": file_sha256(SOURCE),
            "source_video_bytes": SOURCE.stat().st_size,
            "source_frames": src_frames,
            "production_preset": BASELINE_PRESET,
            "production_crf": CRF,
            "production_sites": {
                "src/services/stickman_renderer.py": 996,
                "src/services/ffmpeg_renderer.py": [68, 293, 311, 330],
            },
            "note": (
                "The Day-29/30 narrative that production used preset=medium / crf=18 "
                "is contradicted by the source: all five encoder sites use fast / 23."
            ),
        },
        "host": facts,
        "config": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "crf": CRF,
            "pix_fmt": PIX_FMT,
            "presets": PRESETS,
            "baseline_preset": BASELINE_PRESET,
            "sample_frames": SAMPLE_FRAMES,
        },
        "no_encode_reference": baseline_null,
        "decode_only_reference": decode_only,
        "per_preset": per_preset,
        "baseline_quality_vs_source": baseline_quality,
        "deviation_vs_baseline": deviation,
    }

    json_path = OUTDIR / "day31_encoder_validation.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"[day31] wrote {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
