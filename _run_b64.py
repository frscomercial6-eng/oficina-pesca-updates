# -*- coding: utf-8 -*-
import subprocess, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
LOG = os.path.join(BASE, "build_v1064_final.log")

with open(LOG, "w", encoding="utf-8", errors="replace") as lf:
    lf.write("START\n")
    lf.flush()
    p = subprocess.Popen(
        [PY, "mestre_build.py", "--no-bump", "--nome", "Oficina_Pesca", "--auto", "--no-git"],
        cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        encoding="utf-8", errors="replace", bufsize=1)
    for linha in p.stdout:
        lf.write(linha)
        lf.flush()
        print(linha, end="")
    p.wait()
    lf.write(f"\nEXIT_CODE={p.returncode}\n")
    lf.flush()

with open(LOG, "r", encoding="utf-8", errors="replace") as f:
    linhas = f.readlines()

print(f"\nTOTAL_LINES={len(linhas)}")
print(f"EXIT_CODE={p.returncode}")

for a in [os.path.join(BASE, "dist", "Oficina_Pesca", "Oficina_Pesca.exe"),
           os.path.join(BASE, "PACOTE_ENVIO", "Oficina_Pesca_Instalador.exe"),
           os.path.join(BASE, "PACOTE_ENVIO", "Oficina_Pesca_Portatil.zip")]:
    e = os.path.exists(a)
    t = os.path.getsize(a) if e else 0
    print(f"{'EXISTS' if e else 'MISSING'}: {os.path.basename(a)} ({t/1024/1024:.1f} MB)")
