import os, re

pyi_dir = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv_build\Lib\site-packages\PyInstaller'

print("Searching for multiprocessing.spawn.spawn in PyInstaller...")
for root, dirs, files in os.walk(pyi_dir):
    dirs[:] = [d for d in dirs if '__pycache__' not in d]
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                if 'spawn.spawn' in content or 'from multiprocessing.spawn import spawn' in content:
                    print(f"FOUND in: {path}")
                    # Show context
                    for i, line in enumerate(content.split('\n')):
                        if 'spawn.spawn' in line or 'from multiprocessing.spawn import spawn' in line:
                            print(f"  Line {i+1}: {line}")
            except:
                pass

print("\nSearching for how Analysis is run...")
build_main = os.path.join(pyi_dir, 'building', 'build_main.py')
if os.path.exists(build_main):
    with open(build_main, 'r', errors='ignore') as f:
        content = f.read()
    
    # Find multiprocessing references
    for i, line in enumerate(content.split('\n')):
        if 'multiprocessing' in line.lower() or 'subprocess' in line.lower() or 'Popen' in line.lower():
            print(f"  {i+1}: {line.rstrip()}")
