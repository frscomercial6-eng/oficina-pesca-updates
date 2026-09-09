import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, '_build_min.log')

os.chdir(BASE)

# Remove old spec and build
for path in [
    os.path.join(BASE, 'Oficina_Pesca.spec'),
    os.path.join(BASE, 'build'),
    os.path.join(BASE, 'dist'),
]:
    if os.path.exists(path):
        import shutil
        print(f"Removing: {path}")
        shutil.rmtree(path, ignore_errors=True)

time.sleep(1)

# Create minimal spec - only firebase_admin
spec = r'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['login.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'firebase_admin',
        'firebase_admin.credentials',
    ],
    excludes=[
        '.backup_i18n', 'api', 'android_apk', 'infra', 'static',
        'templates', 'tests', 'tools',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Oficina_Pesca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=[],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Oficina_Pesca',
)
'''

spec_path = os.path.join(BASE, 'Oficina_Pesca.spec')
with open(spec_path, 'w', encoding='utf-8') as f:
    f.write(spec)

print(f"Spec: {spec_path}")

# Build
print("Building...")
log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', spec_path, '--noconfirm'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    text=True,
)

print(f"PID: {proc.pid}")

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    sys.stdout.write(line)
    sys.stdout.flush()

proc.wait()
log_file.close()

print(f"\nEXIT: {proc.returncode}")

with open(LOG) as f:
    lines = f.readlines()
print(f"Log: {len(lines)} linhas")
for l in lines[-20:]:
    print(f"  {l.rstrip()}")

exe_path = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
print(f"EXE: {os.path.exists(exe_path)}")
if os.path.exists(exe_path):
    print(f"Size: {os.path.getsize(exe_path):,} bytes")
