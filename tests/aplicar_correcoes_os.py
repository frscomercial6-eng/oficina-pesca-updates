# -*- coding: utf-8 -*-
"""Corrige o botao de planos (bug #4) nos dois logins e gera dumps de analise
para os bugs #1 (mapeamento de colunas), #2 (painel Aguardando Retirada) e
#3 (salvamento/reserva de numero da O.S.).

Uso: python tests/aplicar_correcoes_os.py [--dump]
"""
import os
import py_compile
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
BASE = r"f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
BP = r"f:\PROGRAMA\OFICINA DE PESCA\build_protegido"
DUMP_PATH = os.path.join(BASE, "tests", "dump_correcoes.txt")
DUMP_ONLY = "--dump" in sys.argv
URL = "https://www.frssolutions.com.br/planos"


def ler(p):
    with open(p, "r", encoding="utf-8") as a:
        return a.read()


def salvar(p, t):
    with open(p, "w", encoding="utf-8", newline="") as a:
        a.write(t)


def bloco_em_texto(texto, nome):
    m = re.search(r"(?m)^(?P<ind>[ ]*)def %s\b.*$" % re.escape(nome), texto)
    if not m:
        return ""
    ind = len(m.group("ind"))
    linhas = texto[m.start():].split("\n")
    saida = [linhas[0]]
    for l in linhas[1:]:
        if l.strip() and (len(l) - len(l.lstrip())) <= ind:
            break
        saida.append(l)
    return "\n".join(saida)


def dump_bloco(fh, texto, nome, titulo, maximo=170):
    trecho = bloco_em_texto(texto, nome)
    fh.write("\n===== %s :: def %s =====\n" % (titulo, nome))
    linhas = (trecho or "(NAO ENCONTRADA)").split("\n")
    fh.write("\n".join(linhas[:maximo]) + "\n")


def dump_regiao(fh, texto, ini, fim, titulo):
    linhas = texto.split("\n")
    fh.write("\n===== %s :: linhas %d-%d =====\n" % (titulo, ini, fim))
    for i in range(ini, min(fim, len(linhas)) + 1):
        fh.write("%d: %s\n" % (i, linhas[i - 1]))


def substituir_todas(texto, nome, novo_corpo):
    saida, pos, alterado = [], 0, False
    while True:
        trecho = texto[pos:]
        m = re.search(r"(?m)^(?P<ind>[ ]*)def %s\b.*$" % re.escape(nome), trecho)
        if not m:
            saida.append(trecho)
            break
        ind = m.group("ind")
        linhas = trecho[m.start():].split("\n")
        fim = len(linhas[0])
        for l in linhas[1:]:
            if l.strip() and (len(l) - len(l.lstrip())) <= len(ind):
                break
            fim += len(l) + 1
        novo = "\n".join((ind + l) if l else "" for l in novo_corpo.strip("\n").split("\n"))
        saida.append(trecho[: m.start()] + novo)
        pos += m.start() + fim
        alterado = True
    return "".join(saida), alterado


NOVO_PLANOS = '''
def abrir_janela_planos(*args, **kwargs):
    """Abre diretamente a pagina de planos no site (link externo)."""
    try:
        webbrowser.open("%s")
    except Exception:
        pass
''' % URL


def main():
    with open(DUMP_PATH, "w", encoding="utf-8") as fh:
        # ---------- dumps p/ bugs #1, #2 e #3 ----------
        menu = ler(os.path.join(BASE, "menu.py"))
        nomes = re.findall(r"(?m)^\s*def ([A-Za-z_0-9]*(?:pendenc|retirada)[A-Za-z_0-9]*)\b", menu, re.I)
        fh.write("MENU defs pendenc/retirada: %s\n" % nomes)
        for n in nomes:
            dump_bloco(fh, menu, n, "MENU", 170)
        dump_regiao(fh, menu, 3040, 3110, "MENU INDICADORES (contadores)")
        dump_regiao(fh, menu, 2760, 2830, "MENU CHAMADOR PAINEL")
        tela = ler(os.path.join(BASE, "tela_os.py"))
        nomes_t = sorted(set(re.findall(r"(?m)^\s*def ([A-Za-z_0-9]*(?:numero|salvar)[A-Za-z_0-9]*)\b", tela)))
        fh.write("TELA_OS defs numero/salvar: %s\n" % nomes_t)
        for n in nomes_t:
            dump_bloco(fh, tela, n, "TELA_OS", 170)
        repo = ler(os.path.join(BASE, "core", "gestao_os_repository.py"))
        dump_bloco(fh, repo, "listar_orcamentos_para_gestao", "REPOSITORY", 80)
        dump_regiao(fh, ler(os.path.join(BASE, "gestao_os.py")), 300, 335, "UI UNPACK gestao_os")
        dump_regiao(fh, ler(os.path.join(BASE, "core", "gestao_os_service.py")), 1, 70, "SERVICE")
        cfg = ler(os.path.join(BASE, "config.py"))
        nomes_c = re.findall(r"(?m)^\s*def ([A-Za-z_0-9]*(?:os_completa|orcamento)[A-Za-z_0-9]*)\b", cfg)
        fh.write("CONFIG defs os_completa/orcamento: %s\n" % nomes_c)
        for n in nomes_c[:4]:
            dump_bloco(fh, cfg, n, "CONFIG", 200)
        # ---------- fix #4 nos dois logins ----------
        for raiz, tag in ((BASE, "FONTE"), (BP, "BUILD_PROTEGIDO")):
            caminho = os.path.join(raiz, "login.py")
            texto = ler(caminho)
            dump_bloco(fh, texto, "abrir_janela_planos", "LOGIN %s ANTES" % tag, 60)
            if not DUMP_ONLY:
                novo, ok = substituir_todas(texto, "abrir_janela_planos", NOVO_PLANOS)
                if ok:
                    salvar(caminho, novo)
                    py_compile.compile(caminho, doraise=True)
                    print("[%s] abrir_janela_planos substituida e compilou OK" % tag)
                    print("[%s] import webbrowser presente: %s" % (tag, "import webbrowser" in novo))
                else:
                    print("[%s] abrir_janela_planos NAO ENCONTRADA" % tag)
            dump_bloco(fh, ler(caminho), "abrir_janela_planos", "LOGIN %s DEPOIS" % tag, 20)
    print("Dump completo em:", DUMP_PATH)


if __name__ == "__main__":
    main()
