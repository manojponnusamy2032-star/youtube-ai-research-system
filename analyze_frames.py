from PIL import Image
import os

for i in range(1, 4):
    path = f'output/visual_quality_v1_single/frame_{i:03d}.png'
    if os.path.exists(path):
        img = Image.open(path)
        # Sample specific regions for colors
        # Character region (center-bottom)
        char_region = img.crop((350, 1200, 730, 1700))
        char_colors = char_region.getcolors(maxcolors=10000)
        print(f'Frame {i} - Character region ({char_region.size}): {len(char_colors) if char_colors else "too many"} colors')
        if char_colors:
            for count, color in sorted(char_colors, reverse=True)[:5]:
                print(f'  {color}: {count} pixels')
        
        # Top text region
        top_region = img.crop((100, 100, 980, 300))
        top_colors = top_region.getcolors(maxcolors=10000)
        print(f'Frame {i} - Top region ({top_region.size}): {len(top_colors) if top_colors else "too many"} colors')
        if top_colors:
            for count, color in sorted(top_colors, reverse=True)[:5]:
                print(f'  {color}: {count} pixels')
        
        # Clock region (top-right)
        clock_region = img.crop((800, 100, 1000, 300))
        clock_colors = clock_region.getcolors(maxcolors=10000)
        print(f'Frame {i} - Clock region ({clock_region.size}): {len(clock_colors) if clock_colors else "too many"} colors')
        if clock_colors:
            for count, color in sorted(clock_colors, reverse=True)[:5]:
                print(f'  {color}: {count} pixels')
        
        # Ground region
        ground_region = img.crop((0, 1500, 1080, 1920))
        ground_colors = ground_region.getcolors(maxcolors=10000)
        print(f'Frame {i} - Ground region ({ground_region.size}): {len(ground_colors) if ground_colors else "too many"} colors')
        if ground_colors:
            for count, color in sorted(ground_colors, reverse=True)[:5]:
                print(f'  {color}: {count} pixels')
        print()