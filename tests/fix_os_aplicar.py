# -*- coding: utf-8 -*-
"""Corrige/valida os 4 problemas de O.S. (idempotente).
1. Valida listagem de O.S. com 13 colunas (estatico + runtime).
2. Grava dump das regioes do painel de pendencias em tests/_dump_os_fix.txt.
3. Valida INSERT/reserva de numero em tela_os.py.
4. Botao de licenca dos 2 logins abre https://www.frssolutions.com.br/planos
"""
import datetime
import os
import py_compile
import re
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.normpath(os.path.join(RAIZ, os.pardir, "build_protegido"))
URL = "https://www.frssolutions.com.br/planos"
REL = os.path.join(RAIZ, "tests", "_relatorio_fixes.txt")
DUMP = os.path.join(RAIZ, "tests", "_dump_os_fix.txt")

_rel = []

def log(msg=""):
    print(msg)
    _rel.append(str(msg))

def _ind(linha):
    return len(linha) - len(linha.lstrip(" \t"))

def _funcao(codigo, nome):
    linhas = codigo.splitlines(keepends=True)
    for i, ln in enumerate(linhas):
        if re.match(r"^\s*def\s+" + re.escape(nome) + r"\b", ln):
            base = _ind(ln)
            fim = len(linhas)
            for j in range(i + 1, len(linhas)):
                l2 = linhas[j]
                if not l2.strip():
                    continue
                if _ind(l2) <= base and not l2.lstrip().startswith((")", "]", "}")):
                    fim = j
                    break
            while fim > i + 1 and not linhas[fim - 1].strip():
                fim -= 1
            return i, fim, "".join(linhas[i:fim]), linhas
    return None

def _trocar_funcao(codigo, nome, bloco):
    pos = _funcao(codigo, nome)
    if pos is None:
        return codigo, False
    i, fim, _t, linhas = pos
    pad = " " * _ind(linhas[i])
    eol = "\r\n" if "\r\n" in codigo else "\n"
    corpo = eol.join(pad + l for l in bloco.rstrip("\n").split("\n")) + eol
    return "".join(linhas[:i]) + corpo + "".join(linhas[fim:]), True

BLOCO_PLANOS = "\n".join([
    "def abrir_janela_planos(evento=None):",
    '    """Abre a pagina oficial de planos no navegador padrao."""',
    "    try:",
    '        webbrowser.open("' + URL + '")',
    "    except Exception as exc:",
    "        try:",
    '            messagebox.showerror("Oficina de Pesca", "Nao foi possivel abrir o link: %s" % exc)',
    "        except Exception:",
    "            pass",
]) + "\n"

def fix_planos():
    log("=== FIX 4: botao de licenca -> link externo ===")
    for caminho in (os.path.join(RAIZ, "login.py"), os.path.join(BUILD, "login.py")):
        if not os.path.isfile(caminho):
            log("[SKIP] ausente: %s" % caminho)
            continue
        with open(caminho, "r", encoding="utf-8", newline="") as f:
            codigo = f.read()
        pos = _funcao(codigo, "abrir_janela_planos")
        if pos is None:
            log("[ALERTA] funcao nao encontrada: %s" % caminho)
            continue
        if URL in pos[2]:
            log("[OK] ja corrigido: %s" % caminho)
        else:
            bak = caminho + ".bak_fix4"
            if not os.path.exists(bak):
                shutil.copy2(caminho, bak)
            codigo, ok = _trocar_funcao(codigo, "abrir_janela_planos", BLOCO_PLANOS)
            if not ok:
                log("[ERRO] falha ao substituir: %s" % caminho)
                continue
            if not re.search(r"^import webbrowser", codigo, re.M):
                codigo = re.sub(r"^(import threading\b)", r"import webbrowser\n\1", codigo, count=1, flags=re.M)
            with open(caminho, "w", encoding="utf-8", newline="") as f:
                f.write(codigo)
            log("[OK] substituido: %s" % caminho)
        usos = len(re.findall(r"abrir_janela_planos\s*\(", codigo))
        vendas = len(re.findall(r"janela_vendas\s*\(", codigo))
        log("     refs abrir_janela_planos: %d | refs janela_vendas: %d" % (usos, vendas))

def validar_listagem():
    log("=== FIX 1: validacao listagem O.S. ===")
    with open(os.path.join(RAIZ, "core", "gestao_os_repository.py"), "r", encoding="utf-8") as f:
        rcode = f.read()
    m = re.search(r"SELECT\s+(.+?)\s+FROM\s+orcamentos_aguardo", rcode, re.S | re.I)
    if m:
        alvo, prof, cols = m.group(1), 0, 1
        for ch in alvo:
            if ch == "(": prof += 1
            elif ch == ")": prof -= 1
            elif ch == "," and prof == 0: cols += 1
        log("     repository SELECT orcamentos_aguardo: %d colunas" % cols)
    with open(os.path.join(RAIZ, "gestao_os.py"), "r", encoding="utf-8") as f:
        ucode = f.read()
    m2 = re.search(r"^\s*for\s+([A-Za-z_][\w, ]*?)\s+in\s+[^\n]*listar[^\n]*:\s*$", ucode, re.M)
    if m2:
        alvo = m2.group(1)
        log("     UI unpack: %d variaveis (%s)" % (len(alvo.split(",")), alvo.strip()[:100]))
    try:
        from core import gestao_os_service as svc
        nome_fn = next((n for n in dir(svc) if "listar" in n.lower()), None)
        if nome_fn:
            fn = getattr(svc, nome_fn)
            dados = fn()
            n1 = len(dados[0]) if dados else 0
            log("[RUNTIME] %s(): %d registros | colunas 1a linha: %d" % (nome_fn, len(dados), n1))
            if dados and n1 != 13:
                log("[FALHA] esperado 13 colunas, obtido %d" % n1)
        else:
            log("[AVISO] service sem funcao de listagem")
    except Exception as exc:
        log("[AVISO] runtime: %s: %s" % (type(exc).__name__, exc))

def dumps():
    log("=== DUMPS FIX 2 / FIX 3 ===")
    with open(os.path.join(RAIZ, "menu.py"), "r", encoding="utf-8") as f:
        menu = f.read()
    with open(os.path.join(RAIZ, "tela_os.py"), "r", encoding="utf-8") as f:
        tos = f.read()
    with open(os.path.join(RAIZ, "gestao_os.py"), "r", encoding="utf-8") as f:
        gest = f.read()
    with open(os.path.join(RAIZ, "core", "gestao_os_repository.py"), "r", encoding="utf-8") as f:
        repo = f.read()
    partes = []
    for nome in ("_criar_painel_pendencias_fixo", "_consultar_pendencias_login", "_obter_indicadores_oficina"):
        pos = _funcao(menu, nome)
        partes.append("##### menu.py :: %s #####" % nome)
        partes.append(pos[2] if pos else "!!! NAO ENCONTRADA !!!")
    for nome in ("salvar_documento", "carregar_proximo_numero"):
        pos = _funcao(tos, nome)
        partes.append("##### tela_os.py :: %s #####" % nome)
        partes.append(pos[2] if pos else "!!! NAO ENCONTRADA !!!")
    pos = _funcao(repo, "listar_orcamentos_para_gestao")
    partes.append("##### core/gestao_os_repository.py :: listar_orcamentos_para_gestao #####")
    partes.append(pos[2] if pos else "!!! NAO ENCONTRADA !!!")
    if m2:
        lin = gest.count("\n", 0, m2.start())
        partes.append("##### gestao_os.py :: contexto do unpack #####")
        partes.append("\n".join(gest.splitlines()[max(0, lin - 5):lin + 18]))
    for m in re.finditer(r"INSERT INTO orcamentos_aguardo|def salvar_entrada|reservar_numero", tos):
        partes.append("tela_os.py:%d :: %s" % (tos.count("\n", 0, m.start()) + 1, m.group(0)))
    for m in re.finditer(r"_criar_painel_pendencias_fixo|_consultar_pendencias_login", menu):
        partes.append("menu.py:%d :: %s" % (menu.count("\n", 0, m.start()) + 1, m.group(0)))
    with open(DUMP, "w", encoding="utf-8") as f:
        f.write("\n".join(partes) + "\n")
    log("     dump: %s (%d bytes)" % (DUMP, os.path.getsize(DUMP)))

def compilar():
    log("=== Compilacao ===")
    ok = True
    alvos = [
        os.path.join(RAIZ, "menu.py"),
        os.path.join(RAIZ, "tela_os.py"),
        os.path.join(RAIZ, "gestao_os.py"),
        os.path.join(RAIZ, "login.py"),
        os.path.join(RAIZ, "core", "gestao_os_repository.py"),
        os.path.join(RAIZ, "core", "gestao_os_service.py"),
        os.path.join(BUILD, "login.py"),
    ]
    for c in alvos:
        try:
            py_compile.compile(c, doraise=True)
            log("[OK] %s" % os.path.relpath(c, os.path.dirname(RAIZ)))
        except Exception as exc:
            ok = False
            log("[ERRO] %s -> %s" % (c, exc))
    return ok

def main():
    log("== Correcao O.S. %s ==" % datetime.datetime.now().isoformat(timespec="seconds"))
    fix_planos()
    validar_listagem()
    dumps()
    ok = compilar()
    with open(REL, "w", encoding="utf-8") as f:
        f.write("\n".join(_rel) + "\n")
    log("relatorio: %s" % REL)
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
