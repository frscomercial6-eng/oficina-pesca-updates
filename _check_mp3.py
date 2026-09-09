import sys

# Read the spawn.py file directly
with open(r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\spawn.py', 'r') as f:
    content = f.read()

print(f"File size: {len(content)} bytes")
print(f"Has 'def spawn': {'def spawn' in content}")
print(f"Has 'spawn_main': {'spawn_main' in content}")

# Show first 100 lines
lines = content.split('\n')
print(f"\nLines: {len(lines)}")
print("\nFirst 50 lines:")
for i, line in enumerate(lines[:50]):
    print(f"{i+1:3d}: {line}")
