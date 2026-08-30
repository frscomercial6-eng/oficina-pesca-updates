# -*- coding: utf-8 -*-
"""Correção definitiva dos 4 problemas de O.S. (idempotente).

1. Valida o mapeamento de 13 colunas (repository -> service -> UI).
2. Grava dumps persistidos das regiões dos bugs #2 e #3.
3. Aplica o fix #4 (link externo de planos) nos dois logins.
4. Valida a compilação de tudo.

Uso: python tests/correcao_definitiva_os.py
"""
from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = Path(r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL")
BP = Path(r"f:\PROGRAMA\OFICINA DE PESCA\build_protegido")
LINK = "https://www.frssolutions.com.br/planos"

RELATORIO: list[str] = []


def _log(msg: str) -> None:
    RELATORIO.append(msg)
    print(msg)


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8", errors="replace")


def gravar(caminho: Path, texto: str) -> None:
    caminho.write_text(texto, encoding="utf-8", newline="\n")


def janela(caminho: Path, ini: int, fim: int) -> str:
    linhas = ler(caminho).splitlines()
    partes = []
    for n in range(max(1, ini), min(len(linhas), fim) + 1):
        partes.append(f"{n:5d}| {linhas[n - 1]}")
    return "\n".join(partes)


# ---------------------------------------------------------------------------
# FIX #4 - botão de licença/planos -> link externo direto
# ---------------------------------------------------------------------------

NOVO_CORPO = (
    "def abrir_janela_planos(parent=None, *args, **kwargs):\n"
    '    """Abre a página oficial de planos no navegador padrão (sem tela interna)."""\n'
    "    try:\n"
    f'        webbrowser.open("{LINK}")\n'
    "    except Exception:\n"
    "        pass\n"
)


def corrigir_login(caminho: Path) -> None:
    texto = ler(caminho)
    mudancas: list[str] = []

    if re.search(r"^import webbrowser$", texto, flags=re.M) is None:
        texto, n = re.subn(r"(^import sys$)", "import sys\nimport webbrowser", texto, count=1, flags=re.M)
        if n:
            mudancas.append("import webbrowser adicionado")
        else:
            # fallback: insere após o primeiro import
            texto, n = re.subn(r"^(import .+)$", r"\1\nimport webbrowser", texto, count=1, flags=re.M)
            if n:
                mudancas.append("import webbrowser adicionado (fallback)")

    m = re.search(r"^def abrir_janela_planos\(.*$", texto, flags=re.M)
    if m:
        inicio = m.start()
        m2 = re.search(r"^(def |class )\S", texto[m.end():], flags=re.M)
        fim = m.end() + (m2.start() if m2 else len(texto) - m.end())
        if texto[inicio:fim].rstrip("\n") != NOVO_CORPO.rstrip("\n"):
            texto = texto[:inicio] + NOVO_CORPO + texto[fim:]
            mudancas.append("corpo de abrir_janela_planos substituído pelo link externo")

    gravar(caminho, texto)
    ok_link = LINK in ler(caminho)
    _log(f"[#4] {caminho.name}: {'; '.join(mudancas) or 'já corrigido'} | link presente: {ok_link}")


# --- PARTE 2 (validações + dumps + compilação) abaixo ---
