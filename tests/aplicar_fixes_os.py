# -*- coding: utf-8 -*-
"""Aplica e valida as correções dos 4 problemas de O.S. relatados.

- FIX 4: botão de licença abre https://www.frssolutions.com.br/planos (2 logins)
- FIX 1: valida repository/service (13 colunas) estática e runtime no banco real
- FIX 3: inspeciona salvar_documento (INSERT/reserva do número)
- FIX 2: grava dumps persistidos das regiões do painel para edição dirigida

Relatório: tests/_relatorio_fixes_os.txt | Dumps: tests/_dump_*.txt
"""
import os
import py_compile
import re
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
BPROT = r"f:\PROGRAMA\OFICINA DE PESCA\build_protegido"
LINK = "https://www.frssolutions.com.br/planos"
TESTS = os.path.join(BASE, "tests")
REL = os.path.join(TESTS, "_relatorio_fixes_os.txt")
relatorio = []


def log(msg):
    print(msg)
    relatorio.append(msg)


def ler(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def gravar(p, t):
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(t)


def backup(p):
    if os.path.exists(p):
        bak = p + ".bak_fix_os"
        if not os.path.exists(bak):
            shutil.copy2(p, bak)


CORPO_PLANOS = [
    "{i}def abrir_janela_planos(self):",
    '{i}    """Abre a página oficial de planos no navegador padrão."""',
    '{i}    url_planos = "' + LINK + '"',
    "{i}    try:",
    "{i}        import webbrowser",
    "{i}        webbrowser.open(url_planos)",
    "{i}    except Exception as exc:",
    "{i}        try:",
    '{i}            logger.info("Falha ao abrir link de planos: %s", exc)',
    "{i}        except Exception:",
    "{i}            pass",
    "{i}        messagebox.showinfo(",
    '{i}            "Planos Oficina de Pesca",',
    '{i}            "Não foi possível abrir o navegador. Acesse: " + url_planos,',
    "{i}        )",
]

PADRAO_METODO = re.compile(
    r"(?m)^(?P<i>[ \t]+)(?P<sig>def abrir_janela_planos\(self[^)]*\)[^\n]*:)\n"
    r"(?P<b>(?:[ \t]+[^\n]*\n|\n)*?)"
    r"(?=^(?P=i)def |\nclass |\Z)"
)


def aplicar_fix4(caminho):
    if not os.path.isfile(caminho):
        log(f"[FIX4] {caminho}: AUSENTE")
        return
    texto = ler(caminho)
    if LINK in texto:
        log(f"[FIX4] {os.path.basename(os.path.dirname(caminho))}/login.py: já usa o link oficial (OK)")
        return
    m = PADRAO_METODO.search(texto)
    if not m:
        log("[FIX4] login: método abrir_janela_planos NÃO encontrado — ver dump")
        return
    backup(caminho)
    i = m.group("i")
    linhas = [l.replace("{i}", i) for l in CORPO_PLANOS]
    novo = "\n".join(linhas) + "\n"
    texto2 = texto[: m.start()] + novo + texto[m.end():]
    if LINK not in texto2:
        log("[FIX4] login: FALHA na substituição")
        return
    gravar(caminho, texto2)
    log(f"[FIX4] {os.path.basename(os.path.dirname(caminho))}/login.py: abrir_janela_planos agora abre o link externo")


def contar_colunas_select(sql):
    nivel = 0
    cols = 1
    for ch in sql:
        if ch == "(":
            nivel += 1
        elif ch == ")":
            nivel = max(0, nivel - 1)
        elif ch == "," and nivel == 0:
            cols += 1
    return cols


def checar_fix1_estatico():
    rep = os.path.join(BASE, "core", "gestao_os_repository.py")
    texto = ler(rep)
    m = re.search(r"SELECT(.*?)FROM\s+orcamentos_aguardo", texto, re.S | re.I)
    if not m:
        log("[FIX1] repository: SELECT de orcamentos_aguardo não localizado")
        return
    cols = contar_colunas_select(m.group(1))
    log(f"[FIX1] repository SELECT retorna {cols} colunas (esperado: 13)")
    g = ler(os.path.join(BASE, "gestao_os.py"))
    unpacks = []
    for mm in re.finditer(r"(?m)^\(([^()\n]{15,600})\)\s*=\s*(linha|row|registro|dados\w*)\b", g):
        nomes = [n.strip() for n in mm.group(1).split(",") if n.strip()]
        unpacks.append((len(nomes), nomes, mm.group(2)))
    for n, nomes, fonte in unpacks:
        log(f"[FIX1] gestao_os.py unpack {n} vars de '{fonte}': {nomes[0]}...{nomes[-1]}")
    if cols != 13:
        log("[FIX1] ATENÇÃO: contagem difere de 13 — ver dump do repository")
    if "telefone_cli" not in g:
        log("[FIX1] ATENÇÃO: telefone_cli ausente na UI")
