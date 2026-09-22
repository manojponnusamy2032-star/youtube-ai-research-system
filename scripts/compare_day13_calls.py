"""Compare primitive call counts and per-method times between two runs."""
import json
import sys

a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
pa, pb = a['primitive_calls'], b['primitive_calls']
print(f"{'primitive':26s} {'run A':>14s} {'run B':>14s} {'B/A':>7s}")
for k in sorted(set(pa) | set(pb)):
    ra = pa.get(k, 0)
    rb = pb.get(k, 0)
    print(f'{k:26s} {ra:>14} {rb:>14} {(rb / ra if ra else 0):>7.3f}')
ma, mb = a.get('methods', {}), b.get('methods', {})
print(f"\n{'method':26s} {'runA_s':>10s} {'runB_s':>10s} {'B/A':>7s}")
for k in sorted(set(ma) | set(mb)):
    ra = ma.get(k, {}).get('seconds', 0)
    rb = mb.get(k, {}).get('seconds', 0)
    print(f'{k:26s} {ra:>10.3f} {rb:>10.3f} {(rb / ra if ra else 0):>7.3f}')
