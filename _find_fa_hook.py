import os, re

hooks_dirs = [
    r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller\hooks',
    r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller\hooks\contrib',
    r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\_pyinstaller_hooks_contrib\stdhooks',
]

print("Searching for firebase_admin hooks...")
for hooks_dir in hooks_dirs:
    if not os.path.exists(hooks_dir):
        print(f"  NOT FOUND: {hooks_dir}")
        continue
    
    for f in os.listdir(hooks_dir):
        if f.startswith('hook-') and 'firebase' in f.lower():
            path = os.path.join(hooks_dir, f)
            print(f"\n  HOOK: {f}")
            with open(path, 'r', errors='ignore') as fh:
                content = fh.read()
            print(f"  Content ({len(content)} bytes):")
            for line in content.split('\n')[:30]:
                if line.strip() and not line.strip().startswith('#'):
                    print(f"    {line.rstrip()}")

print("\n\nSearching for ALL hooks that mention 'firebase':")
for hooks_dir in hooks_dirs:
    if not os.path.exists(hooks_dir):
        continue
    for f in os.listdir(hooks_dir):
        if f.endswith('.py'):
            path = os.path.join(hooks_dir, f)
            try:
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                if 'firebase' in content.lower():
                    print(f"\n  HOOK: {f}")
                    for i, line in enumerate(content.split('\n')):
                        if 'firebase' in line.lower():
                            print(f"    Line {i+1}: {line.rstrip()}")
            except:
                pass
