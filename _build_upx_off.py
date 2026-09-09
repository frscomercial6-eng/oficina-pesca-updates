# -*- coding: utf-8 -*-
"""
Build v1.0.64 - UPX disabled, direct PyInstaller invocation
"""
import subprocess, sys, os, time

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
SPEC = os.path.join(BASE, "Oficina_Pesca.spec")
LOG = os.path.join(BASE, "build_v1064_upxoff.log")

log_file = open(LOG, "w", buffering=1, encoding="utf-8")

env = os.environ.copy()
env["PYINSTALLER_LOG_LOGGER_LEVEL"] = "WARNING"

print(f"[BUILD] Starting at {time.strftime('%H:%M:%S')}", flush=True)
print(f"[BUILD] PY={PY}", flush=True)
print(f"[BUILD] SPEC={SPEC}", flush=True)

proc = subprocess.Popen(
    [PY, "-m", "PyInstaller", SPEC, "--noconfirm", "--log-level", "WARN"],
    cwd=BASE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=env,
    text=False,
)

print(f"[BUILD] PID={proc.pid}", flush=True)
log_file.write(f"[BUILD] PID={proc.pid}\n")

last_print = time.time()
last_size = 0
stall_count = 0

while True:
    ret = proc.poll()
    if ret is not None:
        print(f"[BUILD] Exit code: {ret}", flush=True)
        log_file.write(f"[BUILD] Exit code: {ret}\n")
        # Read remaining
        try:
            remaining = proc.stdout.read()
            if remaining:
                decoded = remaining.decode("utf-8", errors="replace")
                log_file.write(decoded)
                print(decoded[:500], flush=True)
        except Exception as e:
            log_file.write(f"[BUILD] Error reading remaining: {e}\n")
        break

    # Non-blocking read
    try:
        import select
        ready, _, _ = select.select([proc.stdout], [], [], 1.0)
        if ready:
            line_bytes = proc.stdout.readline()
            if line_bytes:
                line = line_bytes.decode("utf-8", errors="replace").rstrip()
                log_file.write(line + "\n")
                last_print = time.time()
    except ImportError:
        # Windows - use polling
        time.sleep(0.5)

    # Monitor progress every 10 seconds
    now = time.time()
    if now - last_print > 10:
        elapsed = now - last_print
        size = os.path.getsize(LOG)
        print(f"[MONITOR] alive={proc.poll() is None} stall={elapsed:.0f}s log_size={size}", flush=True)
        log_file.write(f"[MONITOR] stall={elapsed:.0f}s size={size}\n")
        log_file.flush()
        last_print = now
        stall_count += 1
        if stall_count > 6:  # 60 seconds of no output
            print(f"[BUILD] STALLED - terminating", flush=True)
            log_file.write("[BUILD] STALLED - terminating\n")
            proc.terminate()
            time.sleep(2)
            proc.kill()
            break

log_file.close()
print(f"[BUILD] Done. Log: {LOG}", flush=True)
