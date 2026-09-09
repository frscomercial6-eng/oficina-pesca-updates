import sys

# Read the spawn.py file
with open(r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\spawn.py', 'r') as f:
    content = f.read()

lines = content.split('\n')
print(f"Total lines: {len(lines)}")
print("\nSearching for 'spawn' function definitions:")
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('def '):
        print(f"  Line {i+1}: {line.rstrip()}")

print("\n\nSearching for 'spawn' references:")
for i, line in enumerate(lines):
    if 'spawn(' in line and not line.strip().startswith('#'):
        print(f"  Line {i+1}: {line.rstrip()}")
