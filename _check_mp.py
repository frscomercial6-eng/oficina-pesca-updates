import sys, os
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")

# Check if PYINSTALLER_NO_MP is set
print(f"PYINSTALLER_NO_MP: {os.environ.get('PYINSTALLER_NO_MP', 'NOT SET')}")

# Try to import multiprocessing.spawn
import multiprocessing.spawn as mp_spawn
print(f"mp_spawn dir: {[x for x in dir(mp_spawn) if not x.startswith('_')]}")
print(f"has spawn: {hasattr(mp_spawn, 'spawn')}")
print(f"spawn: {getattr(mp_spawn, 'spawn', 'NOT FOUND')}")

# Check sys.modules
import sys
print(f"multiprocessing.spawn in sys.modules: {'multiprocessing.spawn' in sys.modules}")
