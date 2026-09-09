# -*- coding: utf-8 -*-
"""Verifica onde --collect-all aparece no mestre_build.py."""
from pathlib import Path

texto = Path(__file__).parent / "mestre_build.py"
s = texto.read_text(encoding="utf-8")

idx = 0
count = 0
while True:
    idx = s.find("--collect-all", idx)
    if idx < 0:
        break
    # Pega 200 chars de contexto
    ctx = s[max(0,idx-50):idx+60]
    print(f"[{count+1}] Linhaaproximada ~{s[:idx].count(chr(10))+1}:")
    for ln in ctx.split("\n"):
        if ln.strip():
            print(f"  {ln.strip()[:100]}")
    print()
    idx += 1
    count += 1

print(f"Total: {count} ocorrencias de --collect-all")
