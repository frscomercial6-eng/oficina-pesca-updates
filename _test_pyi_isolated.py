# -*- coding: utf-8 -*-
"""Teste mínimo isolado do PyInstaller."""
import subprocess, os, sys, time

PYI = r"F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe"
BASE = r"E:\TEST_PYI"
LOG = os.path.join(BASE, "test_log.txt")

# Criar arquivos de teste mínimo
os.makedirs(BASE, exist_ok=True)

test_py = os.path.join(BASE, "test_min.py")
with open(test_py, "w") as f:
    f.write('print("HELLO FROM ISOLATED PYINSTALLER")\ninput()\n')

spec = os.path.join(BASE, "test.spec")
with open(spec, "w") as f:
    f.write(
        'a = Analysis(["test_min.py"], pathex=[""])\n'
        'pyz = PYZ(a.pure)\n'
        'exe = EXE(pyz, a.scripts, [], console=True, name="TEST_MIN")\n'
        'coll = COLLECT(exe, a.binaries, a.datas, name="dist")\n'
    )

print("Arquivos de teste criados.")
print(f"PyInstaller: {PYI}")
print(f"Existe: {os.path.exists(PYI)}")

# Teste 1: PyInstaller --version
r = subprocess.run([PYI, "-m", "PyInstaller", "--version"],
                   capture_output=True, text=True, timeout=10)
print(f"PyInstaller version: {r.stdout.strip()}")

# Teste 2: Build mínimo com spec
env = os.environ.copy()
env["PYTHONPATH"] = os.path.dirname(os.path.dirname(PYI))

cmd = [PYI, "-m", "PyInstaller", "test.spec", "--noconfirm"]
print(f"\nExecutando: {' '.join(cmd)}")
print(f"CWD: {BASE}")

start = time.time()
r = subprocess.run(
    cmd,
    cwd=BASE,
    capture_output=True,
    text=True,
    timeout=300,
    env=env,
)

elapsed = time.time() - start
with open(LOG, "w") as f:
    f.write(f"Exit code: {r.returncode}\n")
    f.write(f"Tempo: {elapsed:.1f}s\n")
    f.write("\n=== STDOUT ===\n")
    f.write(r.stdout)
    f.write("\n=== STDERR ===\n")
    f.write(r.stderr)

print(f"\nExit code: {r.returncode}")
print(f"Tempo: {elapsed:.1f}s")
print(f"Linhas stdout: {r.stdout.count(chr(10))}")

exe_path = os.path.join(BASE, "dist", "TEST_MIN", "TEST_MIN.exe")
print(f"\nEXE gerado: {os.path.exists(exe_path)}")
if os.path.exists(exe_path):
    print(f"Tamanho: {os.path.getsize(exe_path):,} bytes")
    print("SUCESSO: PyInstaller funciona!")
else:
    print("FALHA: EXE não encontrado.")
    print("\nÚltimas 10 linhas do log:")
    lines = r.stdout.split("\n")
    for line in lines[-10:]:
        print(f"  {line}")
