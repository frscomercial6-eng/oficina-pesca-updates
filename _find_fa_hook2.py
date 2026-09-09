import os

# Check all hook directories
pyi_dir = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller'
hooks_std = os.path.join(pyi_dir, 'hooks')
hooks_contrib = os.path.join(pyi_dir, 'hooks', 'contrib')
pyi_contrib = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\_pyinstaller_hooks_contrib'

print("Hook dirs:")
for d in [hooks_std, hooks_contrib, pyi_contrib]:
    print(f"  {d}: {'EXISTS' if os.path.exists(d) else 'NOT FOUND'}")

# Search all hook files for firebase
print("\nSearching for firebase_admin hooks...")
for base_dir in [hooks_std, pyi_contrib, os.path.join(pyi_contrib, 'stdhooks')]:
    if not os.path.exists(base_dir):
        continue
    for f in os.listdir(base_dir):
        if f.startswith('hook-firebase') and f.endswith('.py'):
            print(f"\n  HOOK: {f}")
            path = os.path.join(base_dir, f)
            with open(path, 'r', errors='ignore') as fh:
                content = fh.read()
            for line in content.split('\n'):
                if line.strip() and not line.strip().startswith('#'):
                    print(f"    {line.rstrip()}")

# Also search for 'firebase' in ALL hooks
print("\n\nSearching ALL hooks for 'firebase'...")
for base_dir in [hooks_std, pyi_contrib, os.path.join(pyi_contrib, 'stdhooks')]:
    if not os.path.exists(base_dir):
        continue
    for f in os.listdir(base_dir):
        if f.endswith('.py'):
            path = os.path.join(base_dir, f)
            with open(path, 'r', errors='ignore') as fh:
                content = fh.read()
            if 'firebase' in content.lower():
                print(f"\n  HOOK: {f}")
                for i, line in enumerate(content.split('\n')):
                    if 'firebase' in line.lower():
                        print(f"    Line {i+1}: {line.rstrip()}")
