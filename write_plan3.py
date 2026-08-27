import json

# Read the existing file
with open(r"d:\youtube-ai-research-system\youtube-ai-research-system\examples\plan_visual_example.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Fix scene 1: add direction to enter motion
data["scenes"][0]["visual"]["motions"][0]["parameters"] = {"direction": "bottom"}

# Fix scene 3: add direction to enter motion
data["scenes"][2]["visual"]["motions"][1]["parameters"] = {"direction": "bottom"}

with open(r"d:\youtube-ai-research-system\youtube-ai-research-system\examples\plan_visual_example.json", "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print("Motions fixed successfully!")