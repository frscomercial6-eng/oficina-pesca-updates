import subprocess, os, time

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, '_build_pyi611.log')

os.chdir(BASE)

print(f"Python: {PYI}")

# Check current PyInstaller version
r = subprocess.run([PYI, '-m', 'pip', 'show', 'pyinstaller'], capture_output=True, text=True)
print(f"Current: {r.stdout.split(chr(10))[0] if r.returncode == 0 else 'NOT FOUND'}")

# Try to install an older version
print("\nTrying PyInstaller 6.11.0...")
r = subprocess.run([PYI, '-m', 'pip', 'install', 'pyinstaller==6.11.0', '--quiet'], 
    capture_output=True, text=True, timeout=120)
print(f"Install result: {r.returncode}")
if r.returncode != 0:
    print(f"STDERR: {r.stderr[:500]}")

# Check version again
r = subprocess.run([PYI, '-m', 'pip', 'show', 'pyinstaller'], capture_output=True, text=True)
print(f"After install: {r.stdout.split(chr(10))[0] if r.returncode == 0 else 'NOT FOUND'}")

# If install failed, try 6.10.0
if r.returncode != 0 or '6.11.0' not in r.stdout:
    print("\nTrying PyInstaller 6.10.0...")
    r = subprocess.run([PYI, '-m', 'pip', 'install', 'pyinstaller==6.10.0', '--quiet'],
        capture_output=True, text=True, timeout=120)
    print(f"Install result: {r.returncode}")
    if r.returncode != 0:
        print(f"STDERR: {r.stderr[:500]}")

# Check version
r = subprocess.run([PYI, '-m', 'pip', 'show', 'pyinstaller'], capture_output=True, text=True)
print(f"After 2nd install: {r.stdout.split(chr(10))[0] if r.returncode == 0 else 'NOT FOUND'}")

# If still not 6.11, try from PyPI index
if '6.11.0' not in r.stdout and '6.10.0' not in r.stdout:
    print("\nTrying PyInstaller 6.11.0 without version constraint...")
    # Try to find available versions
    r = subprocess.run([PYI, '-m', 'pip', 'install', 
        'pyinstaller>=6.10,<6.12', '--dry-run', '--quiet'],
        capture_output=True, text=True, timeout=30)
    print(f"Available: {r.stdout[:200]}")
