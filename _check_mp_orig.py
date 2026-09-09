import sys

# Check the original CPython spawn.py for 3.11.0
print("Python version:", sys.version_info)

# Read the installed spawn.py
with open(r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\spawn.py', 'r') as f:
    spawn_content = f.read()

print(f"\nspawn.py size: {len(spawn_content)}")
print(f"Has 'spawn' function def: {'def spawn(' in spawn_content}")
print(f"Has 'spawn_main' function def: {'def spawn_main(' in spawn_content}")

# Search for what imports spawn from spawn
print("\nSearching for 'from .spawn import' or conditional imports:")
lines = spawn_content.split('\n')
for i, line in enumerate(lines):
    if 'import' in line.lower() and 'spawn' in line.lower():
        print(f"  Line {i+1}: {line.rstrip()}")

# Check multiprocessing/__init__.py
print("\n\nChecking multiprocessing/__init__.py:")
with open(r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\__init__.py', 'r') as f:
    mp_init = f.read()
    
print(f"Size: {len(mp_init)}")
print(f"Has 'from .spawn import': {'from .spawn import' in mp_init}")

for i, line in enumerate(mp_init.split('\n')):
    if 'from .spawn' in line or 'import spawn' in line:
        print(f"  Line {i+1}: {line.rstrip()}")
