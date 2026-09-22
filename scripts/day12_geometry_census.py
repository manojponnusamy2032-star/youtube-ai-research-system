"""Diagnostic geometry census: replay real frame state, never raster/encode.

Counts Bresenham center steps and thickness candidates using production inputs.
Not a speed benchmark and does not replace the full six-scene render.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src.services.stickman_renderer import StickmanRenderer
from src.services.scene_composition import SceneComposition
from src.models.content_package import Motion


def line_counts(x0, y0, x1, y1, thickness, width, height):
    dx, dy = abs(x1 - x0), abs(y1 - y0)
    sx, sy = (1 if x0 < x1 else -1), (1 if y0 < y1 else -1)
    err = dx - dy
    lo, hi = -thickness // 2, thickness // 2
    centers = outside = 0
    while True:
        centers += 1
        if x0 + hi < 0 or x0 + lo >= width or y0 + hi < 0 or y0 + lo >= height:
            outside += 1
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return centers, outside, (hi - lo + 1) ** 2


def main():
    source = ROOT / 'output/day11_optimization/benchmark/jobs/job_001/visual_plan.json'
    jobs = json.loads(source.read_text())['render_job_plan']['jobs']
    renderer = StickmanRenderer(False)
    results = []
    for job in jobs:
        duration = int(job['duration_seconds'])
        comp = SceneComposition.from_visual_description(job.get('visual_description'))
        motions = [Motion(**m) for m in job.get('motions', [])]
        action = renderer._detect_action(job)
        totals = {'frames': 0, 'primary_line_calls': 0, 'center_steps': 0,
                  'fully_offscreen_center_steps': 0, 'thickness_candidates': 0,
                  'fully_offscreen_thickness_candidates': 0}
        for i in range(duration * 30):
            t = i / 30
            state = renderer._evaluate_motion_state(motions, t, duration, 1920, 1080, action, composition=comp)
            renderer._resolve_named_characters(state, t, duration, 1920, 1080)
            pose = renderer._compute_pose(action, t, duration, 1920, 1080,
                                          camera_instructions=job.get('camera_instructions', ''), motion_state=state)
            if state.get('suppress_primary_character'):
                pose.stickman_x = pose.stickman_y = -10000
            def tx(x):
                return int((x - 960) * pose.camera_zoom + 960 + pose.camera_pan_x)
            def ty(y):
                return int((y - 540) * pose.camera_zoom + 540 + pose.camera_pan_y)
            segments = [(pose.stickman_x, pose.neck_y, pose.stickman_x, pose.hip_y),
                        (pose.stickman_x, pose.shoulder_y, pose.left_arm_x, pose.left_arm_y),
                        (pose.stickman_x, pose.shoulder_y, pose.right_arm_x, pose.right_arm_y),
                        (pose.stickman_x, pose.hip_y, pose.left_leg_x, pose.left_leg_y),
                        (pose.stickman_x, pose.hip_y, pose.right_leg_x, pose.right_leg_y)]
            totals['frames'] += 1
            for x0, y0, x1, y1 in segments:
                centers, outside, area = line_counts(tx(x0), ty(y0), tx(x1), ty(y1), pose.line_thickness, 1920, 1080)
                totals['primary_line_calls'] += 1
                totals['center_steps'] += centers
                totals['fully_offscreen_center_steps'] += outside
                totals['thickness_candidates'] += centers * area
                totals['fully_offscreen_thickness_candidates'] += outside * area
        results.append({'scene_id': job['job_id'], **totals})
    out = ROOT / 'output/day12_profiling/geometry_census.json'
    out.write_text(json.dumps({'method': 'Deterministic production motion/pose replay plus exact Bresenham center recurrence. Counts, not pipeline timings.', 'scenes': results}, indent=2))
    print(out)


if __name__ == '__main__':
    main()
