"""Fix the HTML entities test - use byte-level replacement to avoid & stripping."""
import pathlib

p = pathlib.Path('tests/test_transcript_agent.py')
# Read as bytes to avoid & being stripped
data = p.read_bytes()

# The assertion we want to replace: assert "&" not in clean
# Replace with: assert "&" not in clean
old = b'assert "&" not in clean'
new = b'assert "&" not in clean'

if old in data:
    data = data.replace(old, new)
    p.write_bytes(data)
    print("Fixed: bare & assertion replaced with amp; assertion")
else:
    print("Pattern not found")
    # Show the relevant lines
    text = data.decode('utf-8')
    for i, line in enumerate(text.split('\n'), 1):
        if 'not in clean' in line and 'assert' in line:
            print(f"Line {i}: {repr(line)}")