from PIL import Image
import os

# Check for character details in frame 2
path = 'output/visual_quality_v1_single/frame_002.png'
img = Image.open(path)

# Character head region (where head should be)
head_region = img.crop((450, 1150, 630, 1350))
head_colors = head_region.getcolors(maxcolors=10000)
print(f'Head region ({head_region.size}): {len(head_colors) if head_colors else "too many"} colors')
if head_colors:
    for count, color in sorted(head_colors, reverse=True)[:10]:
        print(f'  {color}: {count} pixels')

# Character body region (torso)
body_region = img.crop((430, 1350, 650, 1600))
body_colors = body_region.getcolors(maxcolors=10000)
print(f'\nBody region ({body_region.size}): {len(body_colors) if body_colors else "too many"} colors')
if body_colors:
    for count, color in sorted(body_colors, reverse=True)[:10]:
        print(f'  {color}: {count} pixels')

# Books stack (left side)
books_region = img.crop((80, 1200, 250, 1600))
books_colors = books_region.getcolors(maxcolors=10000)
print(f'\nBooks region ({books_region.size}): {len(books_colors) if books_colors else "too many"} colors')
if books_colors:
    for count, color in sorted(books_colors, reverse=True)[:10]:
        print(f'  {color}: {count} pixels')

# Desk region
desk_region = img.crop((200, 1600, 880, 1850))
desk_colors = desk_region.getcolors(maxcolors=10000)
print(f'\nDesk region ({desk_region.size}): {len(desk_colors) if desk_colors else "too many"} colors')
if desk_colors:
    for count, color in sorted(desk_colors, reverse=True)[:10]:
        print(f'  {color}: {count} pixels')

# Check clock movement - compare frame 1 vs frame 3
path1 = 'output/visual_quality_v1_single/frame_001.png'
path3 = 'output/visual_quality_v1_single/frame_003.png'
img1 = Image.open(path1)
img3 = Image.open(path3)

clock1 = img1.crop((800, 100, 1000, 300))
clock3 = img3.crop((800, 100, 1000, 300))

# Compare pixel differences
diff = sum(1 for p1, p3 in zip(clock1.getdata(), clock3.getdata()) if p1 != p3)
total = 200 * 200
print(f'\nClock region diff: {diff}/{total} pixels changed ({diff/total*100:.1f}%)')