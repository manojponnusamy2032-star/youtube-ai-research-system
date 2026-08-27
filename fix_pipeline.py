with open('d:/youtube-ai-research-system/youtube-ai-research-system/src/pipeline/auto_publish_pipeline.py', 'rb') as f:
    content = f.read()

old = b'job_spec = RenderJobSpec(\r\n            job_id=f"scene_{scene_number:03d}",\r\n            config=config,\r\n            motions=motions,\r\n            transition=transition,\r\n            audio_request=audio_request,\r\n            caption=scene.display_caption,\r\n            visual_prompt=visual.visual_prompt,\r\n            animation_instructions=visual.animation_instructions,\r\n            camera_instructions=visual.camera_instructions,\r\n            motion_intent=visual.to_motion_intent(),\r\n        )\r\n        \r\n        # Render using StickmanRenderer\r\n        record = stickman_renderer.render(job_spec)\r\n        return record'

new = b'job_spec = RenderJobSpec(\r\n            job_id=f"scene_{scene_number:03d}",\r\n            scene_number=scene_number,\r\n            duration_seconds=int(duration),\r\n            render_type="stickman_animation",\r\n            character_ids=[],\r\n            asset_ids=[],\r\n            visual_prompt=visual.visual_prompt,\r\n            animation_instructions=visual.animation_instructions,\r\n            camera_instructions=visual.camera_instructions,\r\n            audio_requirements="",\r\n            motions=motions,\r\n            transition=transition,\r\n            audio_request=audio_request,\r\n        )\r\n        \r\n        # Render using StickmanRenderer via render_stickman_job function\r\n        from src.services.stickman_renderer import render_stickman_job\r\n        record = render_stickman_job(job_spec, config)\r\n        return record'

if old in content:
    new_content = content.replace(old, new)
    with open('d:/youtube-ai-research-system/youtube-ai-research-system/src/pipeline/auto_publish_pipeline.py', 'wb') as f:
        f.write(new_content)
    print('Replaced successfully')
else:
    print('Old text not found')
    # Try with \n instead of \r\n
    old2 = old.replace(b'\r\n', b'\n')
    new2 = new.replace(b'\r\n', b'\n')
    if old2 in content:
        new_content = content.replace(old2, new2)
        with open('d:/youtube-ai-research-system/youtube-ai-research-system/src/pipeline/auto_publish_pipeline.py', 'wb') as f:
            f.write(new_content)
        print('Replaced with LF')
    else:
        print('Still not found')