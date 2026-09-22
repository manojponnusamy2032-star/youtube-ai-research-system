"""Inspect the day12 canonical plan structure for the instrumented driver."""
from __future__ import annotations
import json, hashlib
from pathlib import Path
from src.orchestration.schemas.visual import VisualPlan

plan_bytes = Path('output/day12_profiling/jobs/job_001/visual_plan.json').read_bytes()
print('plan sha', hashlib.sha256(plan_bytes).hexdigest())
plan = VisualPlan.model_validate_json(plan_bytes)
rjp = plan.render_job_plan
print('rjp type', type(rjp).__name__)
if isinstance(rjp, dict):
    print('rjp keys', list(rjp.keys()))
    jobs = rjp['jobs']
else:
    jobs = getattr(rjp, 'jobs', None)
print('n jobs', len(jobs) if jobs else None)
for i, j in enumerate(jobs or []):
    is_dict = isinstance(j, dict)
    job_id = j.get('job_id') if is_dict else getattr(j, 'job_id', None)
    dur = j.get('duration_seconds') if is_dict else getattr(j, 'duration_seconds', None)
    vd = j.get('visual_description') if is_dict else getattr(j, 'visual_description', None)
    specs = (vd or {}).get('text_specs', []) if isinstance(vd, dict) else []
    if isinstance(vd, str):
        try:
            vd = json.loads(vd)
            specs = (vd or {}).get('text_specs', [])
        except Exception:
            pass
    motions = j.get('motions') if is_dict else getattr(j, 'motions', [])
    print(f'job[{i}] id={job_id} dur={dur} text_specs={len(specs)} motions={len(motions) or 0}')
print('render_config', (rjp.get('render_config') if isinstance(rjp, dict) else getattr(rjp, 'render_config', None)))
