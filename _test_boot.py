import subprocess, os, sys, time

boot_exe = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller\bootloader\Windows-64bit-intel\run.exe'
LOG = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\_boot_test.txt'

print(f"Boot exe: {boot_exe}")
print(f"Exists: {os.path.exists(boot_exe)}")
print(f"Size: {os.path.getsize(boot_exe):,} bytes")
print()

# Test running the bootloader directly
print("Testing bootloader directly...")
r = subprocess.run([boot_exe, '--help'], capture_output=True, text=True, timeout=10)
print(f"Exit: {r.returncode}")
print(f"STDOUT: {r.stdout[:500]}")
print(f"STDERR: {r.stderr[:500]}")

print()

# Test running the bootloader with a simple Python script
test_script = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\_boot_test.py'
with open(test_script, 'w') as f:
    f.write('print("Hello from bootloader"); import sys; print(sys.version)\n')

print("Testing bootloader with Python script...")
r2 = subprocess.run([boot_exe, '--script', test_script], capture_output=True, text=True, timeout=15)
print(f"Exit: {r2.returncode}")
print(f"STDOUT: {r2.stdout[:500]}")
print(f"STDERR: {r2.stderr[:500]}")

print()
print("Testing Analysis subprocess directly...")

# Test PyInstaller's analysis directly
sys.path.insert(0, r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages')

from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.building.datastruct import Tree

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'

print("Creating Analysis...")
try:
    a = Analysis(
        [os.path.join(BASE, 'login.py')],
        pathex=[BASE],
        binaries=[],
        datas=[],
        hiddenimports=['firebase_admin', 'firebase_admin.credentials'],
        excludes=['.backup_i18n', 'api', 'android_apk', 'infra', 'static', 'templates', 'tests', 'tools'],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        noarchive=False,
    )
    print(f"Analysis OK! {len(a.scripts)} scripts")
except Exception as e:
    print(f"Analysis ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
