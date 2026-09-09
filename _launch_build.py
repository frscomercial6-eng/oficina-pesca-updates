# -*- coding: utf-8 -*-
import subprocess, sys, os, shutil, time

BASE = os.path.dirname(os.path.abspath(__file__))
PY_VENV = os.path.join(BASE, ".venv", "Scripts", "python.exe")

if not os.path.exists(PY_VENV):
    print(f"ERRO: Python venv nao encontrado: {PY_VENV}")
    sys.exit(1)

print(f"Python: {PY_VENV}")
print(f"Versao:")
subprocess.run([PY_VENV, "--version"])

print("\nExecutando _build_isolated.py...")
r = subprocess.run(
    [PY_VENV, "_build_isolated.py"],
    cwd=BASE,
    timeout=3900,  # 65 min timeout
)
print(f"\nBuild exit code: {r.returncode}")
sys.exit(r.returncode)
