import json

# Read the existing file
with open(r"d:\youtube-ai-research-system\youtube-ai-research-system\examples\plan_visual_example.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Add remaining 4 scenes
scene2 = {
  "narration": "After about 90 minutes, your brain stops forming new memories efficiently. You're just spinning your wheels.",
  "caption": "90 minutes \u2192 diminishing returns",
  "visual": {
    "scene_role": "problem",
    "primary_focus": "character",
    "camera_pattern": "static",
    "energy": "medium",
    "character_action": "surprised",
    "visual_prompt": "The student looks confused and tired. The clock shows 90 minutes. Thought bubbles with question marks appear above head. Books stop stacking.",
    "animation_instructions": "Student expression changes to surprised/confused. Clock stops at 90:00. Thought bubbles appear. Visual metaphor of spinning wheels.",
    "camera_instructions": "Medium shot on student's face, slight pan to clock.",
    "motions": [
      {"target": "character", "type": "talk", "start_time": 0.0, "duration": 1.0, "easing": "ease_in_out"},
      {"target": "object", "object_name": "clock", "type": "move", "start_time": 0.5, "duration": 1.5, "parameters": {"from": [100, 0], "to": [0, 0]}, "easing": "ease_out"},
      {"target": "character", "type": "surprised", "start_time": 1.0, "duration": 1.0, "easing": "ease_in"}
    ],
    "transition": {"type": "crossfade", "duration": 0.5}
  }
}

scene3 = {
  "narration": "The solution isn't more time. It's focused sessions with deliberate breaks. The Pomodoro method works because it matches your brain's natural rhythm.",
  "caption": "Focused sessions > Marathon cramming",
  "visual": {
    "scene_role": "solution",
    "primary_focus": "character",
    "camera_pattern": "pan",
    "energy": "high",
    "character_action": "point",
    "visual_prompt": "Student transforms - desk clears, single book appears. A timer shows 25:00 counting down. Student looks focused and confident. Checkmarks appear for completed sessions.",
    "animation_instructions": "Books disappear. Single book appears. Timer counts down. Student expression becomes confident. Checkmarks accumulate.",
    "camera_instructions": "Pan from messy desk to clean desk with timer. End on student's confident face.",
    "motions": [
      {"target": "object", "object_name": "books", "type": "fade", "start_time": 0.0, "duration": 1.0, "parameters": {"from": 1.0, "to": 0.0}, "easing": "linear"},
      {"target": "object", "object_name": "single_book", "type": "enter", "start_time": 1.0, "duration": 1.0, "easing": "ease_out"},
      {"target": "camera", "type": "pan", "start_time": 0.0, "duration": 3.0, "parameters": {"from": [-200, 0], "to": [200, 0]}, "easing": "ease_in_out"}
    ],
    "transition": {"type": "crossfade", "duration": 0.5}
  }
}

scene4 = {
  "narration": "25 minutes of deep focus. 5 minutes of true rest. Repeat. After four cycles, take a longer break. Your brain consolidates learning during the breaks.",
  "caption": "25 min focus + 5 min break = Better retention",
  "visual": {
    "scene_role": "method",
    "primary_focus": "character",
    "camera_pattern": "zoom_out",
    "energy": "medium",
    "character_action": "idle",
    "visual_prompt": "Four Pomodoro cycles visualized. Timer counts 25:00, break 5:00, repeat 4 times. Then long break 15:00. Student alternates between focused work and relaxed break poses. Brain icon shows consolidation during breaks.",
    "animation_instructions": "Cycle through 4 work/break periods. Show brain icon pulsing during breaks. Student alternates poses.",
    "camera_instructions": "Wide shot showing the cycle progression. Slow zoom out to show complete pattern.",
    "motions": [
      {"target": "character", "type": "idle", "start_time": 0.0, "duration": 2.0, "easing": "linear"},
      {"target": "camera", "type": "zoom", "start_time": 0.0, "duration": 4.0, "parameters": {"from": 1.0, "to": 0.7}, "easing": "linear"}
    ],
    "transition": {"type": "crossfade", "duration": 0.5}
  }
}

scene5 = {
  "narration": "Stop measuring study by hours. Measure it by focus quality. Try one focused session today and see the difference.",
  "caption": "Quality > Quantity. Start today.",
  "visual": {
    "scene_role": "cta",
    "primary_focus": "character",
    "camera_pattern": "zoom_in",
    "energy": "high",
    "character_action": "wave",
    "visual_prompt": "Student looks at camera confidently. Clean desk. Single book. Warm lighting. Text overlay: \"Try one session today.\"",
    "animation_instructions": "Final confident pose. Warm lighting. Text overlay fades in. Student waves.",
    "camera_instructions": "Close up on student's face, warm and inviting.",
    "motions": [
      {"target": "character", "type": "wave", "start_time": 0.5, "duration": 2.0, "easing": "ease_in_out"},
      {"target": "camera", "type": "zoom", "start_time": 0.0, "duration": 2.0, "parameters": {"from": 0.8, "to": 1.2}, "easing": "ease_out"}
    ],
    "transition": {"type": "fade", "duration": 0.5}
  }
}

data["scenes"].extend([scene2, scene3, scene4, scene5])

with open(r"d:\youtube-ai-research-system\youtube-ai-research-system\examples\plan_visual_example.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("All 5 scenes added successfully!")