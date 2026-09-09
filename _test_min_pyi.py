# -*- coding: utf-8 -*-
"""Teste minimo do PyInstaller no ambiente atual."""
import subprocess, os, sys

BASE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(BASE, ".venv", "Scripts", "python.exe")
LOG = os.path.join(BASE, "_test_min_log.txt")

# Teste 1: PyInstaller --help
print("Teste 1: PyInstaller --help")
r = subprocess.run([PY, "-m", "PyInstaller", "--help"], capture_output=True, text=True)
print(f"  Exit: {r.returncode}")
if r.returncode != 0:
    print(f"  STDERR: {r.stderr[:200]}")

# Teste 2: import PyInstaller
print("\nTeste 2: import PyInstaller")
try:
    import PyInstaller
    print(f"  OK: {PyInstaller.__version__}")
except Exception as e:
    print(f"  ERRO: {e}")

# Teste 3: import analysis module
print("\nTeste 3: import depend.analysis")
try:
    sys.path.insert(0, os.path.join(BASE, ".venv", "Lib", "site-packages", "PyInstaller"))
    import PyInstaller.depend.analysis
    print("  OK")
except Exception as e:
    print(f"  ERRO: {e}")

# Teste 4: initialize_modgraph
print("\nTeste 4: initialize_modgraph()")
try:
    sys.path.insert(0, os.path.join(BASE, ".venv", "Lib", "site-packages", "PyInstaller"))
    from PyInstaller.depend import analysis as pyi_analysis
    result = pyi_analysis.initialize_modgraph()
    print(f"  OK: graph nodes={len(result.nodes())}")
except Exception as e:
    import traceback
    print(f"  ERRO: {e}")
    traceback.print_exc()

print("\nFeito.")
