import sys, os, py_compile, tempfile, subprocess

# Test if Python can compile all standard library modules
pyi_dir = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv_build\Lib\site-packages\PyInstaller'

print("Testing bytecode compilation...")
errors = []

# Test specific modules
modules_to_test = [
    r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\spawn.py',
    r'C:\Users\User\AppData\Local\Programs\Python\Python311\Lib\multiprocessing\__init__.py',
]

for mod in modules_to_test:
    try:
        py_compile.compile(mod, doraise=True)
        print(f"  OK: {os.path.basename(mod)}")
    except py_compile.PyCompileError as e:
        print(f"  ERROR: {os.path.basename(mod)}: {e}")
        errors.append(mod)

print(f"\nErrors: {len(errors)}")

# Test importing critical modules
print("\nTesting critical imports...")
critical = [
    'multiprocessing',
    'multiprocessing.spawn',
    'multiprocessing.context',
]

for mod in critical:
    try:
        __import__(mod)
        print(f"  OK: {mod}")
    except Exception as e:
        print(f"  ERROR: {mod}: {type(e).__name__}: {e}")
        errors.append(mod)

print(f"\nTotal errors: {len(errors)}")

# Now test if Analysis can run without multiprocessing
print("\nTesting Analysis without multiprocessing subprocess...")
sys.path.insert(0, pyi_dir)

# Patch multiprocessing to avoid the subprocess issue
import multiprocessing.context
_original_spawn = multiprocessing.context.SpawnContext.__init__

def _patched_spawn_init(self, *args, **kwargs):
    print(f"  [PATCHED] SpawnContext.__init__ called")
    # Don't actually spawn
    pass

# Check if there's a __main__ module issue
print("\nTesting Analysis isolated subprocess directly...")
from PyInstaller.isolated import Python
from PyInstaller import isolated

# Try to run a simple isolated subprocess
print("Running simple isolated test...")
try:
    with Python() as python:
        result = python.call('os.getpid')
        print(f"  os.getpid() = {result}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
