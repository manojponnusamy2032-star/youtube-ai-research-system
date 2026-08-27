"""Complete the visual pipeline: assemble + concat audio + mux from existing scene files."""
import sys
import os
import json
sys.path.insert(0, r'd:\youtube-ai-research-system\youtube-ai-research-system')
os.chdir(r'd:\youtube-ai-research-system\youtube-ai-research-system')

from src.pipeline.auto_publish_pipeline import AutoPublishPipeline, VideoPlan
from src.models.content_package import RenderConfig
from src.services.video_assembler import VideoAssembler

# Load the plan to get format info
plan = VideoPlan.from_file('examples/plan_visual_example.json')

output_dir = 'output/publish_visual'
scene_files = [
    f'{output_dir}/scenes/scene_001.mp4',
    f'{output_dir}/scenes/scene_002.mp4',
    f'{output_dir}/scenes/scene_003.mp4',
    f'{output_dir}/scenes/scene_004.mp4',
    f'{output_dir}/scenes/scene_005.mp4',
]

# Build render_outputs with required fields
render_outputs = []
for idx, path in enumerate(scene_files, start=1):
    render_outputs.append({
        'job_id': f'scene_{idx:03d}',
        'status': 'completed',
        'output_reference': os.path.abspath(path),
        'duration_seconds': 5,
        'scene_number': idx,
        'transition_to_next': {'type': 'crossfade', 'duration': 0.5},
    })

# Assemble
pipeline = AutoPublishPipeline(output_directory=output_dir)
assembled = pipeline._assemble(render_outputs, plan.format)
print('Assembly:', assembled.get('status'), assembled.get('output_reference', assembled.get('error')))

if assembled['status'] == 'completed':
    # Concat audio
    import glob
    audio_paths = sorted(glob.glob(f'{output_dir}/audio/narration_*.wav'))
    audio_track = pipeline._concat_audio(audio_paths)
    print('Audio concat:', audio_track.get('status'), audio_track.get('audio_reference', audio_track.get('error')))

    if audio_track['status'] == 'completed':
        # Mux
        final_path = os.path.join(output_dir, 'final_with_audio.mp4')
        mux_result = pipeline.muxer.mux(assembled['output_reference'], audio_track['audio_reference'], final_path)
        print('Mux:', mux_result.get('status'))
        print('Final video:', final_path)
        print()
        print(json.dumps({'status': 'completed', 'video_path': os.path.abspath(final_path)}, indent=2))