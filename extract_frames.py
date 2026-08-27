"""Extract representative frames from each rendered scene for visual inspection."""
import glob
import os
import subprocess
import sys

base = r"d:\youtube-ai-research-system\youtube-ai-research-system\output\visual_quality_v1"
out_dir = os.path.join(base, "inspection_frames")
os.makedirs(out_dir, exist_ok=True)

mp4s = sorted(glob.glob(os.path.join(base, "scenes", "scene_*.mp4")))
if not mp4s:
    print("No scene MP4s found")
    sys.exit(0)

for path in mp4s[:10]:
    name = os.path.splitext(os.path.basename(path))[0]
    # extract frames at 30%, 60%, 95% of each clip
    for pct, ts in (("mid", "1.8"), ("late", "4.5")):
        out = os.path.join(out_dir, f"{name}_{pct}.png")
        cmd = [
            "ffmpeg", "-y", "-ss", ts, "-i", path, "-frames:v", "1",
            str(out),
        ]
        subprocess.run(cmd, capture_output=True, check=False)
        if os.path.exists(out):
            print("wrote", os.path.basename(out), os.path.getsize(out))
        else:
            print("FAILED", name, out)

print("DONE")