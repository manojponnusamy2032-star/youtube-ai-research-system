import sys
sys.path.insert(0, '.')
from src.pipeline.auto_publish_pipeline import VideoPlan

plan = VideoPlan.from_file('d:\\youtube-ai-research-system\\youtube-ai-research-system\\examples\\plan_visual_example.json')
print('Plan loaded:', plan.title)
print('Scenes:', len(plan.scenes))
for i, s in enumerate(plan.scenes):
    print(f'  Scene {i+1}: visual={s.visual is not None}, has_intent={s.visual.has_visual_intent() if s.visual else False}')