import subprocess
PYI = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'

# Search for psutil imports in site-packages
import os
site_packages = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages'

print("Searching for 'psutil' references in site-packages:")
for root, dirs, files in os.walk(site_packages):
    for f in files:
        if f.endswith('.py'):
            try:
                path = os.path.join(root, f)
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                if 'psutil' in content:
                    rel = path[len(site_packages)+1:]
                    print(f"  {rel}")
            except:
                pass

print()

# Check what's actually failing in Analysis
# Look at the build log more carefully
with open(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\build_v1064.log') as f:
    content = f.read()

print("Build log analysis:")
print(f"Total lines: {len(content.split(chr(10)))}")
print()

# Find all ERROR lines
for line in content.split('\n'):
    if 'ERROR' in line or 'error' in line or 'CRITICAL' in line:
        print(f"  ERROR: {line.strip()}")

print()

# Find all WARNING lines
warnings = [l for l in content.split('\n') if 'WARNING' in l or 'warning' in l]
print(f"Warnings: {len(warnings)}")
for w in warnings[:10]:
    print(f"  {w.strip()}")

print()

# Find last analysis step
print("Last 20 lines:")
lines = content.split('\n')
for l in lines[-20:]:
    print(f"  {l}")
