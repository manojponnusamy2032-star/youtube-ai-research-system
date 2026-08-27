with open(r'd:\youtube-ai-research-system\youtube-ai-research-system\src\pipeline\auto_publish_pipeline.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''        # Add camera motion based on camera_pattern
        if visual.camera_pattern and visual.camera_pattern != "hold":
            camera_type = "zoom"
            if visual.camera_pattern in {"zoom_in", "zoom_out"}:
                camera_type = "zoom"
            elif visual.camera_pattern in {"pan", "tracking", "follow"}:
                camera_type = "pan"

            camera_motion = Motion(
                type=camera_type,
                target="camera",
                start_time=0.0,
                duration=duration,
                easing="ease_in_out",
                parameters={"from": 1.0, "to": 1.5} if visual.camera_pattern in {"zoom_in", "zoom"} else {"from": 1.5, "to": 1.0} if visual.camera_pattern == "zoom_out" else {"from": {"x": 0.0, "y": 0.0}, "to": {"x": 0.15, "y": 0.0}},
            )
            motions.append(camera_motion)'''

new = '''        # Add camera motion based on camera_pattern
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

if old in content:
    content = content.replace(old, new)
    with open(r'd:\youtube-ai-research-system\youtube-ai-research-system\src\pipeline\auto_publish_pipeline.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Fixed successfully!')
else:
    print('Pattern not found - checking for CRLF...')
    old_crlf = old.replace('\n', '\r\n')
    if old_crlf in content:
        content = content.replace(old_crlf, new.replace('\n', '\r\n'))
        with open(r'd:\youtube-ai-research-system\youtube-ai-research-system\src\pipeline\auto_publish_pipeline.py', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Fixed with CRLF!')
    else:
        print('Not found')