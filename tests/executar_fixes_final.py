# -*- coding: utf-8 -*-
"""Correções automatizadas dos problemas de O.S. (execução única).

1. Fix #4: `abrir_janela_planos` nos dois logins passa a abrir diretamente
   https://www.frssolutions.com.br/planos (sem tela interna de planos).
2. Fix #1: validação estática do SELECT do repository (13 colunas).
3. Compila todos os arquivos envolvidos.
4. Grava dump persistido (tests/_dump_os_fix.txt) com as regiões exatas dos
   bugs #2 (painel Aguardando Retirada) e #3 (salvar_documento), para edição
   assistida à prova de compactação de contexto.

Uso: python tests/executar_fixes_final.py
"""
import os
import py_compile
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
BP = r"f:\PROGRAMA\OFICINA DE PESCA\build_protegido"
LINK = "https://www.frssolutions.com.br/planos"
LOGINS = [os.path.join(RAIZ, "login.py"), os.path.join(BP, "login.py")]


def _indentacao(linha):
    return len(linha) - len(linha.lstrip())


def _fim_do_bloco(linhas, inicio):
    base = _indentacao(linhas[inicio])
    for i in range(inicio + 1, len(linhas)):
        t = linhas[i].strip()
        if t and _indentacao(linhas[i]) <= base and (
            t.startswith("def ") or t.startswith("class ") or t.startswith("@")
        ):
            return i
    return len(linhas)


def corrigir_login(caminho):
    """Substitui o corpo de abrir_janela_planos pelo link externo."""
    with open(caminho, "r", encoding="utf-8", errors="ignore") as arquivo:
        texto = arquivo.read()
    eol = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.splitlines(keepends=True)
    idx = next(
        (i for i, l in enumerate(linhas) if l.strip().startswith("def abrir_janela_planos")),
        None,
    )
    if idx is None:
        return "FUNCAO AUSENTE (nada feito)"
    base = _indentacao(linhas[idx])
    fim = _fim_do_bloco(linhas, idx)
    p = linhas[idx][:base]
    corpo = [
        f"def abrir_janela_planos(*_args, **_kwargs):{eol}",
        f'    """Abre diretamente a página de planos no navegador (link externo)."""{eol}',
        f"    try:{eol}",
        f"        import webbrowser{eol}",
        f'        webbrowser.open("{LINK}"){eol}',
        f"    except Exception:{eol}",
        f"        pass{eol}",
    ]
    corpo = [p + linha for linha in corpo]
    linhas[idx:fim] = corpo
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        arquivo.write("".join(linhas))
    return f"corrigido (linhas {idx + 1}-{fim} substituidas)"


def _contar_colunas(select_part):
    prof = 0
    colunas = 1
    for ch in select_part:
        if ch == "(":
            prof += 1
        elif ch == ")":
            prof -= 1
        elif ch == "," and prof == 0:
            colunas += 1
    return colunas


def validar_repository():
    caminho = os.path.join(RAIZ, "core", "gestao_os_repository.py")
    with open(caminho, "r", encoding="utf-8", errors="ignore") as arquivo:
        texto = arquivo.read()
    m = re.search(r"SELECT(.*?)FROM\s+orcamentos_aguardo", texto, re.S | re.I)
    if not m:
        print("  [AVISO] SELECT de orcamentos_aguardo nao encontrado")
        return
    print(f"  [INFO] repository SELECT orcamentos_aguardo -> {_contar_colunas(m.group(1))} colunas")

# === PARTE 2 ===
