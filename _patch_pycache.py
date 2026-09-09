# -*- coding: utf-8 -*-
"""Corrige _limpar_pycache_recursivo para preservar .venv/site-packages."""
from pathlib import Path
import ast

PROJETO = Path(__file__).parent / "mestre_build.py"
backup = PROJETO.with_suffix(".py.backup_pre_pycache_fix")
PROJETO.rename(backup)
texto = backup.read_text(encoding="utf-8")

inicio = texto.find("def _limpar_pycache_recursivo(")
assert inicio >= 0, "Funcao nao encontrada"

proximas = [i for i in [
    texto.find("\ndef ", inicio + 1),
    texto.find("\nclass ", inicio + 1),
    texto.find("\n# ===", inicio + 1),
    texto.find("\n\n\n", inicio + 1),
] if i >= 0]
fim = min(proximas) if proximas else len(texto)

nova = '''
def _limpar_pycache_recursivo(base_dir):
    """
    Remove caches Python SOMENTE do codigo do projeto.

    IMPORTANTE:
    Nunca remover __pycache__ dentro de .venv/site-packages,
    pois essas areas pertencem ao ambiente de dependencias e ao
    proprio PyInstaller.
    """
    base = Path(base_dir).resolve()
    ignorados = {".venv", "venv", "site-packages", "site_packages"}

    removidos = 0

    for caminho in base.rglob("__pycache__"):
        try:
            relativo = caminho.relative_to(base)
        except ValueError:
            continue

        partes = {parte.lower() for parte in relativo.parts}

        if partes.intersection({x.lower() for x in ignorados}):
            continue

        if not caminho.is_dir():
            continue

        import shutil
        shutil.rmtree(caminho, ignore_errors=False)
        removidos += 1

    print(f"__pycache__ do projeto removidos: {removidos}")
    print(".venv/site-packages preservado.")
    return removidos
'''

novo_texto = texto[:inicio] + nova + texto[fim:]
ast.parse(novo_texto, filename=str(PROJETO))
PROJETO.write_text(novo_texto, encoding="utf-8")

print("OK: mestre_build.py corrigido.")
print("Backup:", backup)
print("Protegido: .venv, venv, site-packages, site_packages")
