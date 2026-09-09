# -*- coding: utf-8 -*-
"""Verifica args finais do PyInstaller."""
from pathlib import Path
import re

s = Path(__file__).parent / "mestre_build.py"
texto = s.read_text(encoding="utf-8")

# Procura a funcao que adiciona collect-all
for padrao in ["collect_all", "PYINSTALLER_COLLECT", "collect-all"]:
    idx = texto.find(padrao)
    if idx >= 0:
        print(f"Encontrado '{padrao}' em {idx}:")
        print(texto[max(0,idx-100):idx+200])
        print()

print(f"--collect-all no arquivo: {texto.count('--collect-all')}")
print(f"--clean no arquivo: {texto.count('--clean')}")
print()

# Procura subprocess.run com PyInstaller
matches = [(m.start(), texto[max(0,m.start()-50):m.start()+300])
           for m in re.finditer(r'PyInstaller|subprocess.*pyi|pyi.*subprocess', texto, re.I)]
print(f"Referencias PyInstaller: {len(matches)}")
for _, ctx in matches[:5]:
    print("---")
    for ln in ctx.split("\n"):
        if ln.strip():
            print(f"  {ln.strip()[:120]}")
