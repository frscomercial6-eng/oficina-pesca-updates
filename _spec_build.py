# -*- coding: utf-8 -*-
"""Build via spec file - clean, no --clean, no collect-all."""
import subprocess, os, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_spec_log.txt')
DIST_EXE = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')

print(f"BASE: {BASE}")
print(f"PY: {PY}")
print(f"SPEC: {SPEC}")

if not os.path.exists(PY):
    print("ERROR: python.exe not found")
    sys.exit(1)

if not os.path.exists(SPEC):
    print("ERROR: spec file not found")
    sys.exit(1)

log_f = open(LOG, 'w', encoding='utf-8', errors='replace')

print("Starting PyInstaller with spec file (no --clean)...")
proc = subprocess.Popen(
    [PY, '-m', 'PyInstaller', SPEC, '--noconfirm'],
    cwd=BASE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    universal_newlines=True,
    encoding='utf-8',
    errors='replace',
)

print(f"PID: {proc.pid}")

for line in iter(proc.stdout.readline, ''):
    if line:
        log_f.write(line)
        log_f.flush()
        if 'INFO' in line or 'WARNING' in line or 'ERROR' in line:
            print(line.rstrip())

rc = proc.wait()
log_f.close()

print(f"PyInstaller exit code: {rc}")

if rc == 0 and os.path.exists(DIST_EXE):
    size = os.path.getsize(DIST_EXE)
    print(f"SUCCESS: EXE generated - {size // 1024 // 1024} MB")
    sys.exit(0)
else:
    print(f"FAILURE: exit code {rc}, EXE exists: {os.path.exists(DIST_EXE)}")
    sys.exit(rc)
