"""Inspect stickman renderer with audio integration."""
from src.models.content_package import AudioRequest, RenderConfig, RenderJobSpec
from src.services.stickman_renderer import render_stickman_job
import tempfile
from pathlib import Path

# Create config
config = RenderConfig(
    width=320,
    height=240,
    fps=10,
    video_format='mp4',
    video_codec='libx264',
    audio_format='aac',
    output_directory=tempfile.mkdtemp(),
    filename_template='stickman_audio_inspect_{job_id}.mp4',
)

# Create AudioRequest
audio_request = AudioRequest(
    scene_number=1,
    duration_seconds=3,
    narration_text='Watch the stickman walk animation',
    voice_reference='default',
    background_music_reference='',
    sound_effect_references=[],
    audio_format='aac',
)

# Create RenderJobSpec with audio_request
job_spec = RenderJobSpec(
    job_id='audio-inspect-test',
    scene_number=1,
    duration_seconds=3,
    render_type='stickman_animation',
    character_ids=[],
    asset_ids=[],
    visual_prompt='A stickman walking across the screen',
    animation_instructions='Walk cycle with arm/leg oscillation',
    camera_instructions='Slight camera follow',
    audio_requirements='Narration about walking',
    audio_request=audio_request,
)

# Render the job
result = render_stickman_job(job_spec, config)

print('Render result:')
print(f'  job_id: {result["job_id"]}')
print(f'  status: {result["status"]}')
if 'error' in result:
    print(f'  error: {result["error"]}')
print(f'  output_reference: {result["output_reference"]}')
print(f'  file_size_bytes: {result["file_size_bytes"]}')
print(f'  duration_seconds: {result["duration_seconds"]}')

output_path = Path(result['output_reference'])
print(f'\nOutput file exists: {output_path.exists()}')
if output_path.exists():
    print(f'  File size: {output_path.stat().st_size} bytes')
    
print('\n--- ffprobe inspection ---')

import subprocess

# Run ffprobe to get stream information
output = str(output_path)

# Get video stream info
video_streams = subprocess.run(
    ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_type,codec_name,width,height,r_frame_rate,duration', '-of', 'default=noprint_wrappers=1:nokey=1', output],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
print(f'Video streams: {video_streams}')

# Get audio stream info
audio_streams = subprocess.run(
    ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type,codec_name,duration', '-of', 'default=noprint_wrappers=1:nokey=1', output],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
print(f'Audio streams: {audio_streams}')

# Get format info (duration)
format_info = subprocess.run(
    ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', output],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
print(f'Format duration: {format_info}')

# Get video duration
video_duration = subprocess.run(
    ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=duration', '-of', 'default=noprint_wrappers=1:nokey=1', output],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
print(f'Video duration: {video_duration}')

# Get audio duration
audio_duration = subprocess.run(
    ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=duration', '-of', 'default=noprint_wrappers=1:nokey=1', output],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
print(f'Audio duration: {audio_duration}')

# Get resolution
import re
res_match = re.search(r'(\d+x\d+)', video_streams)
if res_match:
    print(f'Resolution: {res_match.group(1)}')

# Get FPS
fps_match = re.search(r'(\d+\.?\d*)\s*fps', video_streams)
if fps_match:
    print(f'FPS: {fps_match.group(1)}')

# Get video codec
codec_match = re.search(r'codec_name=(\S+)', video_streams)
if codec_match:
    print(f'Video codec: {codec_match.group(1)}')

# Get audio codec
audio_codec_match = re.search(r'codec_name=(\S+)', audio_streams)
if audio_codec_match:
    print(f'Audio codec: {audio_codec_match.group(1)}')

# File size
if output_path.exists():
    print(f'File size: {output_path.stat().st_size} bytes')
    print(f'File path: {output_path}')

# Extract a few frames to verify animation
print('\n--- Frame extraction ---')
frame_dir = tempfile.mkdtemp()
for i in range(0, 30, 5):  # Extract frames at 0, 5, 10, 15, 20, 25
    frame_path = Path(frame_dir) / f'frame_{i:03d}.png'
    result = subprocess.run(
        ['ffmpeg', '-v', 'error', '-y', '-i', output, '-ss', str(i/10), '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        with open(frame_path, 'wb') as f:
            f.write(result.stdout)
        print(f'  Extracted frame at {i/10}s: {frame_path.exists()} (size: {frame_path.stat().st_size if frame_path.exists() else 0} bytes)')
    else:
        print(f'  Failed to extract frame at {i/10}s: {result.stderr}')

print(f'\nFrame directory: {frame_dir}')