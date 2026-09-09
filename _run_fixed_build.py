import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv_build', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_v1064.log')

os.chdir(BASE)

print(f"CWD: {os.getcwd()}")
print(f"PYI: {PYI}")
print(f"SPEC: {SPEC}")
print()

# Kill any existing python build processes
for proc_line in os.popen('tasklist /FO CSV /NH').readlines():
    parts = proc_line.strip().split(',')
    if len(parts) >= 2 and 'python' in parts[0].lower():
        try:
            pid = int(parts[1].strip())
            print(f"Killing residual PID: {pid}")
            os.kill(pid, 9)
        except:
            pass

time.sleep(2)

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

last_print = time.time()
last_size = 0

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    sys.stdout.write(line)
    sys.stdout.flush()
    
    now = time.time()
    if now - last_print > 5:
        log_file.seek(0, 2)
        size = log_file.tell()
        print(f"[{now:.0f}s] {size} chars, alive={proc.poll() is None}")
        last_print = now
        last_size = size

proc.wait()
log_file.close()

exit_code = proc.returncode

print()
print(f"EXIT CODE: {exit_code}")
print(f"Duration: {time.time() - last_print:.0f}s")

with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"LOG LINES: {len(lines)}")
    if lines:
        print(f"LAST LINE: {lines[-1].strip()}")

# Check for EXE
dist_exe = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
if os.path.exists(dist_exe):
    size = os.path.getsize(dist_exe)
    mtime = os.path.getmtime(dist_exe)
    from datetime import datetime
    print(f"EXE FOUND: {dist_exe}")
    print(f"  Size: {size:,} bytes ({size/1024/1024:.1f} MB)")
    print(f"  Modified: {datetime.fromtimestamp(mtime)}")
else:
    print("EXE NOT FOUND")

# Check build dir
build_dir = os.path.join(BASE, 'build', 'Oficina_Pesca')
if os.path.exists(build_dir):
    items = os.listdir(build_dir)
    print(f"BUILD DIR ITEMS: {len(items)} -> {items[:10]}")
else:
    print("BUILD DIR: NOT FOUND")
