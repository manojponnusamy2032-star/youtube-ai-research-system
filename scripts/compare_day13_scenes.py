"""Compare per-scene exclusive breakdowns between two profiler runs."""
import json
import sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
keys = ['render_seconds', 'frame_generation_seconds', 'rendered_fps']
for sa, sb in zip(a['scenes'], b['scenes']):
    name = sa.get('scene_id', sa.get('scene'))[-8:]
    print(f"--- {name} ---")
    for k in keys:
        va, vb = sa.get(k, 0), sb.get(k, 0)
        print(f'  {k:24s} A={va:9.3f} B={vb:9.3f} B/A={vb / va if va else 0:6.3f}')
    ea, eb = sa.get('exclusive', {}), sb.get('exclusive', {})
    for k in sorted(set(ea) | set(eb)):
        va, vb = ea.get(k, 0), eb.get(k, 0)
        print(f'    {k:22s} A={va:8.3f} B={vb:8.3f} B/A={vb / va if va else 0:6.3f}')
