from PIL import Image
import os

# Check for light bulb (should be top right per plan)
path = 'output/visual_quality_v1_single/frame_002.png'
img = Image.open(path)

# Light bulb region (top right where object at x=0.85, y=0.15 should be)
# At 1080x1920: x=918, y=288
bulb_region = img.crop((850, 200, 1000, 400))
bulb_colors = bulb_region.getcolors(maxcolors=10000)
print('Light bulb region (' + str(bulb_region.size) + '): ' + (str(len(bulb_colors)) if bulb_colors else "too many") + ' colors')
if bulb_colors:
    for count, color in sorted(bulb_colors, reverse=True)[:20]:
        print('  ' + str(color) + ': ' + str(count) + ' pixels')

# Check right side for any objects
right_region = img.crop((700, 200, 1080, 500))
right_colors = right_region.getcolors(maxcolors=10000)
print('\nRight region (' + str(right_region.size) + '): ' + (str(len(right_colors)) if right_colors else "too many") + ' colors')
if right_colors:
    for count, color in sorted(right_colors, reverse=True)[:15]:
        print('  ' + str(color) + ': ' + str(count) + ' pixels')

# Check for spotlight/glow effects - look for bright yellow/white pixels
# Check all pixels that are very bright
bright_pixels = 0
for y in range(200, 400):
    for x in range(850, 1000):
        r, g, b = img.getpixel((x, y))
        if r > 240 and g > 240 and b > 240:
            bright_pixels += 1
print('\nBright white pixels in bulb region:', bright_pixels, '/', 150*200)

# Check for yellow/orange glow
orange_pixels = 0
for y in range(200, 400):
    for x in range(850, 1000):
        r, g, b = img.getpixel((x, y))
        if r > 200 and g > 150 and b < 100:
            orange_pixels += 1
print('Orange/yellow pixels in bulb region:', orange_pixels, '/', 150*200)