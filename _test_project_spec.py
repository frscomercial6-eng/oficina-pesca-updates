# -*- coding: utf-8 -*-
"""Teste do spec file real do projeto."""
import subprocess, os, sys, time

PYI = r"F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe"
PROJ = r"F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
LOG = os.path.join(PROJ, "test_project_spec_log.txt")

# Verificar spec file
spec_path = os.path.join(PROJ, "Oficina_Pesca.spec")
print(f"Spec: {spec_path}")
print(f"Existe: {os.path.exists(spec_path)}")

# Verificar assets
assets = os.path.join(PROJ, "assets")
print(f"Assets: {os.path.exists(assets)}")

# Testar com spec file (sem --clean, sem deps de subprocess)
# Usar --noconfirm para não pedir
cmd = [
    PYI, "-m", "PyInstaller",
    "Oficina_Pesca.spec",
    "--noconfirm",
]

env = os.environ.copy()
env["PYTHONPATH"] = PROJ

print(f"\nCWD: {PROJ}")
print("Executando PyInstaller com spec do projeto...")
print("=" * 60)

start = time.time()
try:
    r = subprocess.run(
        cmd,
        cwd=PROJ,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    elapsed = time.time() - start

    with open(LOG, "w") as f:
        f.write(f"Exit code: {r.returncode}\n")
        f.write(f"Tempo: {elapsed:.1f}s\n")
        f.write(f"Linhas stdout: {r.stdout.count(chr(10))}\n")
        f.write("\n=== STDOUT (ultimas 30 linhas) ===\n")
        lines = r.stdout.split("\n")
        for line in lines[-30:]:
            f.write(line + "\n")
        f.write("\n=== STDERR (ultimas 20 linhas) ===\n")
        for line in r.stderr.split("\n")[-20:]:
            f.write(line + "\n")

    print(f"\nExit code: {r.returncode}")
    print(f"Tempo: {elapsed:.1f}s")
    print(f"Linhas stdout: {r.stdout.count(chr(10))}")

    exe_path = os.path.join(PROJ, "dist", "Oficina_Pesca", "Oficina_Pesca.exe")
    if os.path.exists(exe_path):
        print(f"\nSUCESSO! EXE: {os.path.getsize(exe_path):,} bytes")
    else:
        print("\nEXE não encontrado.")
        print("\nÚltimas 20 linhas stdout:")
        for line in lines[-20:]:
            print(f"  {line}")

except subprocess.TimeoutExpired:
    elapsed = time.time() - start
    with open(LOG, "w") as f:
        f.write(f"TIMEOUT after {elapsed:.1f}s\n")
        f.write("Build stalled - checking processes...\n")
    print(f"\nTIMEOUT after {elapsed:.1f}s - Build stalled!")
    print("Verificando processos...")
    r2 = subprocess.run(["tasklist", "/FI", "IMAGENAME eq python*"],
                        capture_output=True, text=True)
    print(r2.stdout)
