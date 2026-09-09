import subprocess, os, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv_build', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_v1064_final.log')

os.chdir(BASE)

print(f"CWD: {os.getcwd()}")
print(f"PYI: {PYI}")
print(f"SPEC: {SPEC}")
print(f"LOG: {LOG}")
print()

log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

env = os.environ.copy()

proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', SPEC, '--noconfirm'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=env,
    bufsize=1,
    text=False,
)

print(f"Started PID: {proc.pid}")
print()

for line in proc.stdout:
    try:
        decoded = line.decode('utf-8', errors='replace')
    except:
        decoded = line.decode('latin-1', errors='replace')
    
    log_file.write(decoded)
    log_file.flush()
    sys.stdout.write(decoded)
    sys.stdout.flush()

proc.wait()
log_file.close()

exit_code = proc.returncode

print()
print(f"EXIT CODE: {exit_code}")
print(f"LOG: {LOG}")

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
    print(f"EXE FOUND: {dist_exe} ({size:,} bytes)")
else:
    print("EXE NOT FOUND")

# Check build dir
build_dir = os.path.join(BASE, 'build', 'Oficina_Pesca')
if os.path.exists(build_dir):
    items = os.listdir(build_dir)
    print(f"BUILD DIR ITEMS: {len(items)} -> {items}")
else:
    print("BUILD DIR: EMPTY or NOT FOUND")
