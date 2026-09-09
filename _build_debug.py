import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_debug.log')

os.chdir(BASE)

print(f"PYI: {PYI}")
print(f"SPEC: {SPEC}")

log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

# Use DEBUG log level
proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', SPEC, '--noconfirm', '--log-level=DEBUG'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    text=True,
)

print(f"PID: {proc.pid}")
last_progress = time.time()

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    # Only print INFO lines
    if ' INFO:' in line or 'ERROR' in line or 'WARNING' in line:
        sys.stdout.write(line)
        sys.stdout.flush()
    elif time.time() - last_progress > 10:
        print(f"[{time.time():.0f}] Still running... (last: {line.strip()[:80]})")
        sys.stdout.flush()
        last_progress = time.time()

proc.wait()
log_file.close()

exit_code = proc.returncode
print(f"\nEXIT: {exit_code}")

# Print last 30 lines
with open(LOG) as f:
    lines = f.readlines()
print(f"Total lines: {len(lines)}")
print("Last 30 lines:")
for l in lines[-30:]:
    print(f"  {l.rstrip()}")
