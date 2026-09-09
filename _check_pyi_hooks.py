import sys, os

# Check PyInstaller hooks and their dependencies
pyi_dir = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller'
hooks_dir = os.path.join(pyi_dir, 'hooks')

# Check if any hooks have problematic dependencies
print("Checking hook files for 'isolated' imports...")
for f in os.listdir(hooks_dir):
    if f.startswith('hook-') and f.endswith('.py'):
        path = os.path.join(hooks_dir, f)
        with open(path, 'r', errors='ignore') as fh:
            content = fh.read()
        if 'isolated' in content:
            print(f"  HOOK WITH isolated: {f}")

print("\nChecking contrib hooks...")
pyi_contrib = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\_pyinstaller_hooks_contrib'
for root, dirs, files in os.walk(pyi_contrib):
    for f in files:
        if f.startswith('hook-') and f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r', errors='ignore') as fh:
                content = fh.read()
            if 'isolated' in content:
                print(f"  HOOK WITH isolated: {path}")

print("\nChecking PyInstaller isolated module...")
isolated_dir = os.path.join(pyi_dir, 'isolated')
if os.path.exists(isolated_dir):
    files = os.listdir(isolated_dir)
    print(f"  Isolated dir: {files}")
else:
    print("  Isolated dir: NOT FOUND")

# Check PyInstaller itself for isolated
from PyInstaller import isolated
print(f"\nIsolated module: {isolated}")
print(f"Isolated file: {isolated.__file__}")

# Check what happens when we import PyInstaller.building
from PyInstaller.building import build_main
print(f"\nbuild_main: {build_main}")
print(f"build_main file: {build_main.__file__}")

# Check if there's a PYINSTALLER_* env var set
print("\nPyInstaller env vars:")
for k, v in os.environ.items():
    if 'PYINSTALLER' in k.upper():
        print(f"  {k}: {v}")

# Check if there's a conflicting PyInstaller installation
import shutil
print(f"\nPyInstaller path: {pyi_dir}")
print(f"PyInstaller size: {sum(os.path.getsize(os.path.join(pyi_dir, f)) for f in os.listdir(pyi_dir) if os.path.isfile(os.path.join(pyi_dir, f))):,} bytes")
