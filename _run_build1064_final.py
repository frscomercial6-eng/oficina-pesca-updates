# -*- coding: utf-8 -*-
"""Executa o build completo v1.0.64."""
import subprocess, os, time, sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
LOG = os.path.join(BASE, "build_v1064_final.log")

with open(LOG, "w", encoding="utf-8") as log_file:
    log_file.write("START\n")
    log_file.flush()

    proc = subprocess.Popen(
        [PY, "mestre_build.py", "--no-bump", "--nome", "Oficina_Pesca", "--auto", "--no-git"],
        cwd=BASE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    for linha in proc.stdout:
        log_file.write(linha)
        log_file.flush()
        print(linha, end="")

    proc.wait()
    log_file.write(f"\nEXIT_CODE={proc.returncode}\n")
    log_file.flush()

with open(LOG, "r", encoding="utf-8") as f:
    linhas = f.readlines()

print(f"\nTOTAL_LINES={len(linhas)}")
print(f"EXIT_CODE={proc.returncode}")

# Verifica artefatos
BASE2 = BASE
artefatos = [
    os.path.join(BASE2, "dist", "Oficina_Pesca", "Oficina_Pesca.exe"),
    os.path.join(BASE2, "PACOTE_ENVIO", "Oficina_Pesca_Instalador.exe"),
    os.path.join(BASE2, "PACOTE_ENVIO", "Oficina_Pesca_Portatil.zip"),
]
for a in artefatos:
    existe = os.path.exists(a)
    tam = os.path.getsize(a) if existe else 0
    print(f"{'EXISTS' if existe else 'MISSING'}: {os.path.basename(a)} ({tam/1024/1024:.1f} MB)")
