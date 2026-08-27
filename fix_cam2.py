path = r'd:\youtube-ai-research-system\youtube-ai-research-system\src\pipeline\auto_publish_pipeline.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('Add camera motion based on')
end_marker = 'motions.append(camera_motion)'
end_idx = content.find(end_marker, idx) + len(end_marker)

new_block = '''# Add camera motion based on camera_pattern
        if visual.camera_pattern and visual.camera_pattern not in {"hold", "static"}:
            camera_type = "zoom"
            camera_params = {"from": 1.0, "to": 1.5}
            if visual.camera_pattern in {"zoom_in", "zoom"}:
                camera_type = "zoom"
                camera_params = {"from": 1.0, "to": 1.5}
            elif visual.camera_pattern == "zoom_out":
                camera_type = "zoom"
                camera_params = {"from": 1.5, "to": 1.0}
            elif visual.camera_pattern in {"pan", "tracking", "follow"}:
                camera_type = "pan"
                camera_params = {"from": {"x": 0.0, "y": 0.0}, "to": {"x": 0.15, "y": 0.0}}

            camera_motion = Motion(
                type=camera_type,
                target="camera",
                start_time=0.0,
                duration=duration,
                easing="ease_in_out",
                parameters=camera_params,
            )
            motions.append(camera_motion)'''

content = content[:idx] + new_block + content[end_idx:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed!')