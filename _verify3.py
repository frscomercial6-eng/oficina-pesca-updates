# -*- coding: utf-8 -*-
"""Verifica a secao _gerar_args_pyi e PYINSTALLER_COLLECT_ALL."""
from pathlib import Path

s = Path(__file__).parent / "mestre_build.py"
texto = s.read_text(encoding="utf-8")

# Procura PYINSTALLER_COLLECT_ALL
idx = texto.find("PYINSTALLER_COLLECT_ALL")
if idx >= 0:
    ctx = texto[idx:idx+400]
    print("=== PYINSTALLER_COLLECT_ALL ===")
    print(ctx[:400])

print()

# Procura _gerar_args_pyi
idx = texto.find("def _gerar_args_pyi(")
if idx >= 0:
    ctx = texto[idx:idx+800]
    print("=== _gerar_args_pyi ===")
    print(ctx[:800])

# Procura args.append --collect
idx = texto.find('args.append("--collect')
while idx >= 0:
    ctx = texto[max(0,idx-100):idx+100]
    print()
    print("=== args.append --collect ===")
    for ln in ctx.split("\n"):
        if ln.strip():
            print(f"  {ln.strip()[:100]}")
    break
