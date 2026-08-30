# -*- coding: utf-8 -*-
"""Executor idempotente das 4 correções (O.S. / painel / salvamento / licença).

FIX 4: abrir_janela_planos -> abre https://www.frssolutions.com.br/planos
FIX 1: valida 13 colunas (repository/service/UI da Consulta de O.S.)
FIX 3: valida INSERT/reserva do número em salvar_documento
FIX 2: grava dump das regiões do painel de pendências (edição final depois)

Uso: python tests/fix_os_executar.py
"""
from __future__ import annotations

import py_compile
import re
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = Path(r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL")
BP = Path(r"f:\PROGRAMA\OFICINA DE PESCA\build_protegido")
DUMP = RAIZ / "tests" / "_dump_regioes_os.txt"
LINK = "https://www.frssolutions.com.br/planos"

NOVA_FUNCAO = '''def abrir_janela_planos(*_args, **_kwargs):
    """Abre a página oficial de planos no navegador padrão (link externo)."""
    import webbrowser

    try:
        webbrowser.open("https://www.frssolutions.com.br/planos")
    except Exception:
        pass
'''


def ler(c):
    bruto = Path(c).read_bytes()
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return bruto.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return bruto.decode("utf-8", "replace"), "utf-8"


def gravar(c, texto, enc):
    bruto = Path(c).read_bytes()
    nl = "\r\n" if bruto.count(b"\r\n") * 2 > bruto.count(b"\n") else "\n"
    with open(c, "w", encoding=enc, newline=nl) as a:
        a.write(texto)


def backup(c):
    b = Path(str(c) + ".bak_fix_os")
    if not b.exists():
        shutil.copy2(c, b)


def achar(linhas, nome):
    rx = re.compile(r"^(\s*)def\s+" + re.escape(nome) + r"\s*\(")
    for i, l in enumerate(linhas):
        if rx.match(l):
            return i
    return None


def corpo(linhas, idx):
    ind = re.match(r"^(\s*)def\s", linhas[idx]).group(1)
    fim = len(linhas)
    for j in range(idx + 1, len(linhas)):
        l = linhas[j]
        if not l.strip():
            continue
        if len(l) - len(l.lstrip()) <= len(ind):
            fim = j
            break
    return "\n".join(linhas[idx:fim]), idx, fim


def topo_split(s):
    partes, prof, atual, asp = [], 0, "", ""
    for ch in s:
        if asp:
            atual += ch
            if ch == asp:
                asp = ""
            continue
        if ch in "\"'":
            asp = ch
        elif ch in "([{":
            prof += 1
        elif ch in ")]}":
            prof = max(0, prof - 1)
        elif ch == "," and prof == 0:
            partes.append(atual)
            atual = ""
            continue
        atual += ch
    if atual.strip():
        partes.append(atual)
    return partes


def trocar_funcao(texto, nome, novo):
    linhas = texto.split("\n")
    idx = achar(linhas, nome)
    if idx is None:
        return texto, False, "função ausente"
    c, ini, fim = corpo(linhas, idx)
    if LINK in c:
        return texto, False, "já corrigida (link externo presente)"
    ind = re.match(r"^(\s*)def\s", linhas[idx]).group(1)
    novas = [ind + l if k == 0 else (ind + "    " + l if l.strip() else "")
             for k, l in enumerate(novo.strip("\n").split("\n"))]
    novas.append("")
    linhas[ini:fim] = novas
    return "\n".join(linhas), True, f"substituída (linhas {ini + 1}-{fim})"


def colunas_select(sql):
    m = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql, re.IGNORECASE | re.DOTALL)
    return len([p for p in topo_split(m.group(1)) if p.strip()]) if m else -1


def grep(linhas, termo, antes=2, depois=4, limite=40):
    rx = re.compile(termo, re.IGNORECASE)
    saida, n = [], 0
    for i, l in enumerate(linhas):
        if rx.search(l):
            for j in range(max(0, i - antes), min(len(linhas), i + depois + 1)):
                saida.append(f"{j + 1:5d} | {linhas[j]}")
            saida.append("-----")
            n += 1
            if n >= limite:
                break
    return saida


def fix4():
    log = ["== FIX 4: botão de licença -> link externo =="]
    for rot, c in (("fonte", RAIZ / "login.py"), ("build_protegido", BP / "login.py")):
        if not c.exists():
            log.append(f"[{rot}] ausente: {c}")
            continue
        t, enc = ler(c)
        novo, mudou, msg = trocar_funcao(t, "abrir_janela_planos", NOVA_FUNCAO)
        if mudou:
            backup(c)
            gravar(c, novo, enc)
        log.append(f"[{rot}] abrir_janela_planos: {msg}")
        rest = [f"  L{i + 1}: {l.strip()}" for i, l in enumerate(novo.split("\n"))
                if "janela_vendas" in l and "import" not in l]
        log.append(f"[{rot}] chamadas internas restantes a janela_vendas: {len(rest)}")
        log.extend(rest[:8])
        try:
            py_compile.compile(str(c), doraise=True)
            log.append(f"[{rot}] compilação OK")
        except Exception as e:
            log.append(f"[{rot}] ERRO COMPILAÇÃO: {e}")
    return log


# ---P2---
