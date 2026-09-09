# -*- coding: utf-8 -*-
"""Verifica o estado do mestre_build.py."""
from pathlib import Path

s = Path(__file__).parent / "mestre_build.py"
texto = s.read_text(encoding="utf-8")

checks = {
    "--clean": "--clean" in texto,
    "--collect-all": "--collect-all" in texto,
    ".venv protegido": ".venv" in texto,
    "site-packages protegido": "site-packages" in texto,
    "site_packages protegido": "site_packages" in texto,
}

for k, v in checks.items():
    print(f"  {k}: {'PRESENTE' if v else 'AUSENTE'} {'(OK)' if k.startswith('.') or not v else '(ALERTA)'}")

print()
# Verifica a secao do PyInstaller
idx = texto.find("PyInstaller")
if idx >= 0:
    secao = texto[idx:idx+500]
    linhas = secao.split("\n")
    print(f"Seção PyInstaller ({len(linhas)} linhas):")
    for ln in linhas[:10]:
        if ln.strip():
            print(f"  {ln.strip()[:120]}")

print()
print("VERIFICACAO COMPLETA.")
