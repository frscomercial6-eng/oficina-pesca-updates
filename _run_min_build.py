import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv_build', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca_minimo.spec')
LOG = os.path.join(BASE, 'build_minimo.log')

os.chdir(BASE)

print(f"CWD: {os.getcwd()}")
print(f"PYI: {PYI}")
print(f"SPEC: {SPEC}")
print()

log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', SPEC, '--noconfirm'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    text=True,
)

print(f"Started PID: {proc.pid}")
print()

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    sys.stdout.write(line)
    sys.stdout.flush()

proc.wait()
log_file.close()

exit_code = proc.returncode

print()
print(f"EXIT CODE: {exit_code}")

with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"LOG LINES: {len(lines)}")
    if lines:
        print(f"LAST LINE: {lines[-1].strip()}")

# Check for EXE
dist_exe = os.path.join(BASE, 'dist', 'Oficina_Pesca_Min', 'Oficina_Pesca_Min.exe')
if os.path.exists(dist_exe):
    size = os.path.getsize(dist_exe)
    print(f"EXE FOUND: {dist_exe} ({size:,} bytes)")
else:
    print("EXE NOT FOUND")

# Check build dir
build_dir = os.path.join(BASE, 'build', 'Oficina_Pesca_Min')
if os.path.exists(build_dir):
    items = os.listdir(build_dir)
    print(f"BUILD DIR ITEMS: {len(items)} -> {items[:10]}")
else:
    print("BUILD DIR: NOT FOUND")
