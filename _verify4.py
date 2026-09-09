# -*- coding: utf-8 -*-
"""Verifica args finais do PyInstaller."""
from pathlib import Path

s = Path(__file__).parent / "mestre_build.py"
texto = s.read_text(encoding="utf-8")

# Procura _gerar_args_pyi completa
idx = texto.find("def _gerar_args_pyi(")
assert idx >= 0, "_gerar_args_pyi nao encontrada"

prox = [i for i in [texto.find("\ndef ", idx+1), texto.find("\nclass ", idx+1)] if i >= 0]
fim = min(prox) if prox else len(texto)

funcao = texto[idx:fim]
print("=== _gerar_args_pyi ===")
print(funcao[:2000])
print()
print("FIM da funcao.")

# Conta collect-all
print()
print(f"--collect-all no comando: {texto.count('--collect-all')}")
print(f"--clean no comando: {texto.count('--clean')}")
