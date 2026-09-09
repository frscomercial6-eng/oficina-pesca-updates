import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_v1064.log')

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

last_line_time = time.time()
last_line = ""

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    sys.stdout.write(line)
    sys.stdout.flush()
    last_line = line.strip()
    last_line_time = time.time()

proc.wait()
log_file.close()

exit_code = proc.returncode
duration = time.time() - last_line_time

print()
print(f"EXIT CODE: {exit_code}")
print(f"DURATION: {duration:.0f}s")
print(f"LAST LINE: {last_line}")

with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"LOG LINES: {len(lines)}")

dist_exe = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
if os.path.exists(dist_exe):
    size = os.path.getsize(dist_exe)
    print(f"EXE FOUND: {size:,} bytes")
else:
    print("EXE NOT FOUND")

build_dir = os.path.join(BASE, 'build', 'Oficina_Pesca')
if os.path.exists(build_dir):
    items = os.listdir(build_dir)
    print(f"BUILD DIR: {len(items)} items -> {items[:10]}")
else:
    print("BUILD DIR: NOT FOUND")
