from PIL import Image
import os

# Check text region more carefully - look for non-background colors
path = 'output/visual_quality_v1_single/frame_002.png'
img = Image.open(path)

# Top caption region (where scene title should be)
top_region = img.crop((100, 100, 980, 300))
top_colors = top_region.getcolors(maxcolors=10000)
print('Top caption region (' + str(top_region.size) + '): ' + (str(len(top_colors)) if top_colors else "too many") + ' colors')
if top_colors:
    for count, color in sorted(top_colors, reverse=True)[:20]:
        print('  ' + str(color) + ': ' + str(count) + ' pixels')

# Bottom text region (where bottom text should be)
bottom_region = img.crop((100, 1600, 980, 1800))
bottom_colors = bottom_region.getcolors(maxcolors=10000)
print('\nBottom text region (' + str(bottom_region.size) + '): ' + (str(len(bottom_colors)) if bottom_colors else "too many") + ' colors')
if bottom_colors:
    for count, color in sorted(bottom_colors, reverse=True)[:20]:
        print('  ' + str(color) + ': ' + str(count) + ' pixels')

# Check a specific pixel in the text area to see if text color exists
print('\nPixel at (540, 150):', img.getpixel((540, 150)))  # Top center
print('Pixel at (540, 200):', img.getpixel((540, 200)))  # Top center lower
print('Pixel at (540, 1650):', img.getpixel((540, 1650)))  # Bottom center
print('Pixel at (100, 100):', img.getpixel((100, 100)))  # Top left corner
print('Pixel at (1000, 100):', img.getpixel((1000, 100)))  # Top right corner