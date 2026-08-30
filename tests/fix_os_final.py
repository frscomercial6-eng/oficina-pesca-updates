# -*- coding: utf-8 -*-
"""Correções idempotentes dos 4 problemas de O.S. + dumps persistidos.

Uso: python tests/fix_os_final.py
- FIX #4: botão de licença -> abre https://www.frssolutions.com.br/planos
  (nos dois logins; corpo substituído preservando a assinatura).
- FIX #1: valida colunas do repositório x unpack da UI x runtime real.
- FIX #3: valida INSERT/reserva em salvar_documento (dump persistido).
- FIX #2: grava dumps persistidos das funções de pendências/retirada.
"""
from __future__ import annotations

import os
import py_compile
import re
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BP = os.path.normpath(os.path.join(RAIZ, os.pardir, "build_protegido"))
TESTES = os.path.join(RAIZ, "tests")
sys.path.insert(0, RAIZ)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LINK_PLANOS = "https://www.frssolutions.com.br/planos"


def _ler(caminho: str) -> str:
    with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def _gravar(caminho: str, conteudo: str) -> None:
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(conteudo)


def _extremos_funcao(linhas: list, indice_def: int) -> int:
    """Índice da primeira linha após o corpo do def (por indentação)."""
    linha_def = linhas[indice_def]
    indent = len(linha_def) - len(linha_def.lstrip())
    for j in range(indice_def + 1, len(linhas)):
        atual = linhas[j]
        if not atual.strip():
            continue
        atual_indent = len(atual) - len(atual.lstrip())
        if atual_indent <= indent:
            return j
    return len(linhas)


def _substituir_corpo_funcao(texto: str, nome: str) -> tuple[str, bool]:
    """Substitui o corpo de `def <nome>` preservando a linha de assinatura."""
    linhas = texto.splitlines(keepends=True)
    padrao = re.compile(r"^(\s*)def\s+" + re.escape(nome) + r"\s*\(")
    for i, linha in enumerate(linhas):
        if padrao.match(linha):
            fim = _extremos_funcao(linhas, i)
            indent = " " * (len(linha) - len(linha.lstrip()))
            corpo = (
                f'{indent}    """Abre a página de planos no navegador (link externo)."""\n'
                f"{indent}    try:\n"
                f"{indent}        import webbrowser\n"
                f'{indent}        webbrowser.open("{LINK_PLANOS}")\n'
                f"{indent}    except Exception as exc:\n"
                f"{indent}        try:\n"
                f"{indent}            messagebox.showerror(\n"
                f'{indent}                "Oficina de Pesca",\n'
                f'{indent}                "Não foi possível abrir o navegador: %s\\n\\nAcesse: {LINK_PLANOS}" % exc,\n'
                f"{indent}            )\n"
                f"{indent}        except Exception:\n"
                f"{indent}            pass\n"
                f"\n"
            )
            novas = linhas[: i + 1] + [corpo] + linhas[fim:]
            return "".join(novas), True
    return texto, False


def fix4_aplicar() -> list:
    resultado = []
    for caminho in (os.path.join(RAIZ, "login.py"), os.path.join(BP, "login.py")):
        if not os.path.isfile(caminho):
            resultado.append(f"[FIX4] AUSENTE: {caminho}")
            continue
        texto = _ler(caminho)
        if "def abrir_janela_planos" not in texto:
            resultado.append(f"[FIX4] função abrir_janela_planos não encontrada em {caminho}")
            continue
        novo, ok = _substituir_corpo_funcao(texto, "abrir_janela_planos")
        if not ok:
            resultado.append(f"[FIX4] falha ao localizar corpo em {caminho}")
            continue
        _gravar(caminho, novo)
        resultado.append(f"[FIX4] aplicado em {caminho}")
    return resultado


# --- PARTE 2 (validações #1/#3 + dumps #2 + relatório) ---
