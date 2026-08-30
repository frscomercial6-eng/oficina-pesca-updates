# -*- coding: utf-8 -*-
"""Aplica o fix #4 (link externo de planos nos logins), valida compilação
e grava dump persistente das regiões dos bugs #1, #2 e #3.

Uso: python tests/executar_fixes.py
"""
import os
import py_compile
import re

RAIZ = r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
BP = r"f:\PROGRAMA\OFICINA DE PESCA\build_protegido"
DUMP = os.path.join(RAIZ, "tests", "_dump_os_fix.txt")

NOVA_FUNC = (
    "def abrir_janela_planos(*args, **kwargs):\n"
    '    """Abre diretamente a página de planos no navegador (link externo)."""\n'
    "    try:\n"
    '        webbrowser.open("https://www.frssolutions.com.br/planos")\n'
    "    except Exception:\n"
    "        pass\n"
)

RELATORIO = []


def ler(caminho):
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def salvar(caminho, conteudo):
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        f.write(conteudo)


def fix_login(caminho):
    """Substitui o corpo de abrir_janela_planos pelo link externo.

    Cirurgia por linhas: independe de indentação/corpo atual.
    """
    linhas = ler(caminho).splitlines(keepends=True)
    saida, i, substituicoes = [], 0, 0
    while i < len(linhas):
        m = re.match(r"^(\s*)def abrir_janela_planos\s*\(", linhas[i])
        if not m:
            saida.append(linhas[i])
            i += 1
            continue
        indent = m.group(1)
        j = i + 1
        while j < len(linhas):
            linha = linhas[j]
            if linha.strip() == "":
                j += 1
                continue
            recuo = len(linha) - len(linha.lstrip())
            if recuo > len(indent):
                j += 1
                continue
            break
        saida.append(indent + NOVA_FUNC)
        substituicoes += 1
        i = j
    texto = "".join(saida)
    if substituicoes and "import webbrowser" not in texto:
        texto = texto.replace("import sys\n", "import sys\nimport webbrowser\n", 1)
    if substituicoes:
        salvar(caminho, texto)
    ja_ok = "frssolutions.com.br/planos" in ler(caminho)
    RELATORIO.append(
        f"[FIX4] {os.path.basename(os.path.dirname(caminho))}/{os.path.basename(caminho)}: "
        + ("já corrigido" if (not substituicoes and ja_ok) else f"{substituicoes} função(ões) substituída(s)")
    )


def compilar(caminho):
    try:
        py_compile.compile(caminho, doraise=True)
        RELATORIO.append(f"[OK] compila: {caminho}")
        return True
    except Exception as erro:
        RELATORIO.append(f"[ERRO] compilação {caminho}: {erro}")
        return False


# --- PARTE 2 (dump + checagens estáticas + relatório) ---
