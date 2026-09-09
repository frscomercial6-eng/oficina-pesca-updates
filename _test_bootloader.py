# -*- coding: utf-8 -*-
"""Testa se o bootloader do PyInstaller consegue rodar no subprocesso."""
import subprocess, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
LOG = os.path.join(BASE, "_test_boot_log.txt")

print("Ambiente:")
print(f"  Python: {sys.executable}")
print(f"  Version: {sys.version}")
print(f"  Platform: {sys.platform}")
print()

# Teste: rodar um script simples via subprocesso
code = "import sys; print(sys.executable); import pickle; print('pickle OK')"
print(f"Subprocesso test: {code[:50]}...")
r = subprocess.run([PY, "-c", code], capture_output=True, text=True, timeout=10)
print(f"  Exit: {r.returncode}")
print(f"  STDOUT: {r.stdout[:200]}")
if r.stderr:
    print(f"  STDERR: {r.stderr[:200]}")
print()

# Teste: simular o que o bootloader faz
# Rodar hook-pickle.py via subprocesso
pickle_hook = os.path.join(BASE, ".venv", "Lib", "site-packages", "PyInstaller", "hooks", "hook-pickle.py")
if os.path.exists(pickle_hook):
    print(f"Rodando hook-pickle.py em subprocesso...")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(BASE, ".venv", "Lib", "site-packages", "PyInstaller") + os.pathsep + os.environ.get("PYTHONPATH", "")
    r2 = subprocess.run([PY, pickle_hook], capture_output=True, text=True, timeout=30, env=env)
    print(f"  Exit: {r2.returncode}")
    print(f"  STDOUT: {r2.stdout[:300]}")
    if r2.stderr:
        print(f"  STDERR: {r2.stderr[:300]}")
else:
    print(f"  hook-pickle.py nao encontrado")

print("\nFeito.")
