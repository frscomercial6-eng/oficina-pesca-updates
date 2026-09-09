import sys

# Read the spawn.py file directly
with open(r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\spawn.py', 'r') as f:
    lines = f.readlines()

print(f"Total lines: {len(lines)}")
print("\nSearching for 'def spawn':")
for i, line in enumerate(lines):
    if 'def spawn' in line:
        print(f"  Line {i+1}: {line.rstrip()}")
        # Show context
        for j in range(max(0,i-2), min(len(lines), i+10)):
            print(f"  {j+1:3d}: {lines[j].rstrip()}")
        print()
