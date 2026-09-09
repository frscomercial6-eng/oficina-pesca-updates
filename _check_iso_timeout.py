import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

# Check isolated module for timeout settings
from PyInstaller import isolated

# Read the _parent.py file
parent_file = os.path.join(os.path.dirname(isolated.__file__), '_parent.py')
with open(parent_file, 'r') as f:
    content = f.read()

print(f"Isolated _parent.py size: {len(content)}")

# Find timeout or communication settings
for i, line in enumerate(content.split('\n')):
    if 'timeout' in line.lower() or 'deadline' in line.lower() or 'poll' in line.lower():
        print(f"  Line {i+1}: {line.rstrip()}")

# Check the call method
print("\nSearching for 'call' method...")
in_call = False
for i, line in enumerate(content.split('\n')):
    if 'def call' in line or 'def _call' in line:
        in_call = True
    if in_call:
        print(f"  {i+1}: {line.rstrip()}")
        if line.strip().startswith('def ') and 'def call' not in line:
            break
