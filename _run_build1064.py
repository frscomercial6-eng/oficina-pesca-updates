BUILD SCRIPT
BUILD SCRIPT
import subprocess, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
SPEC = os.path.join(BASE, "Oficina_Pesca.spec")
LOG = os.path.join(BASE, "build_v1064.log")

cmd = [
    PY, "-m", "PyInstaller",
    "--noconfirm",
    "--specpath", ".",
    "--distpath", "dist",
    "--workpath", "build",
    "Oficina_Pesca.spec"
]

print(f"Running from: {BASE}")
print(f"Python: {PY}")
print(f"Spec: {SPEC}")
print(f"Command: {' '.join(cmd)}")

with open(LOG, "w", encoding="utf-8", errors="replace") as lf:
    lf.write(f"CWD: {BASE}\n")
    lf.write(f"CMD: {' '.join(cmd)}\n")
    lf.write("STARTING\n")
    lf.flush()

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        text=True,
        errors="replace"
    )

    lf.write(f"PID={proc.pid}\n")
    lf.flush()
    print(f"PyInstaller PID={proc.pid}")

    for line in iter(proc.stdout.readline, ""):
        if line:
            lf.write(line)
            lf.flush()
            print(line, end="")

    proc.wait()
    exit_code = proc.returncode
    lf.write(f"\nEXIT_CODE={exit_code}\n")
    lf.flush()
    print(f"\n=== EXIT_CODE={exit_code} ===")

print("Script finished.")
