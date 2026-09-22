"""Print key Day-20 benchmark metrics from a raw day17_render_profile.json.

Usage: python scripts/day20_profile_summary.py <profile.json> [label]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    profile_path = Path(sys.argv[1])
    label = sys.argv[2] if len(sys.argv) > 2 else profile_path.parent.name
    data = json.loads(profile_path.read_text(encoding='utf-8'))

    print(f'[{label}]')
    print(f'  total_render_wall_s      : {data["total_wall_seconds"]:.3f}')
    print(f'  frame_generation_s       : {data["frame_generation_seconds"]:.3f}')
    print(f'  instrumentation_gap_s    : {data["instrumentation_gap_seconds"]:.3f}')
    print(f'  generated/decoded frames : {data["generated_frame_count"]}/{data["frame_count"]}')
    line_method = data['methods']['StickmanRenderer._draw_line']
    line_avg_ms = line_method['exclusive'] / line_method['calls'] * 1000.0
    print(f'  _draw_line exclusive s   : {line_method["exclusive"]:.3f}')
    print(f'  _draw_line calls         : {line_method["calls"]}')
    print(f'  _draw_line avg ms/call   : {line_avg_ms:.3f}')
    breakdown = data['breakdown']
    for name in ('lines', 'text', 'ellipses', 'rectangles', 'image_copies', 'other'):
        value = breakdown.get(name)
        if value is not None:
            print(f'  breakdown.{name:<13}  : {value:.3f}')
    primitive = data.get('primitive_calls') or {}
    if primitive:
        print(f'  primitive_calls          : {json.dumps(primitive, sort_keys=True)}')
    scenes = data.get('per_scene') or data.get('scenes') or []
    for scene in scenes:
        name = scene.get('scene', scene.get('index', scene.get('name')))
        lines_time = scene.get('lines')
        total = scene.get('frame_generation_seconds', scene.get('total'))
        extra = {k: round(v, 3) for k, v in scene.items()
                 if k not in ('scene', 'index', 'name', 'lines',
                              'frame_generation_seconds', 'total')
                 and isinstance(v, (int, float))}
        print(f'  scene {name}: lines={lines_time} frame_gen={total} {extra}')
    print(f'  verifier_exit_code       : {data.get("verifier_exit_code")}')
    print(f'  render_status            : {data.get("render_status")}')
    comparison = data.get('day20_comparison_vs_baseline')
    if comparison:
        print('  comparison_vs_baseline   :')
        for key, values in comparison.items():
            print(f'    {key}: {json.dumps(values)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
