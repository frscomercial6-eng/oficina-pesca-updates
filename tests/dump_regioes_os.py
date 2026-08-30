# -*- coding: utf-8 -*-
"""Dump persistido das regiões dos bugs #2 (painel de pendências) e #3 (salvar).

Grava:
- tests/_dump_painel.txt : menu.py (chamador do painel, indicadores, painel fixo +
  dashboard modular, _consultar_pendencias_login) e gestao_os.py (unpack da UI);
- tests/_dump_salvar.txt : tela_os.py (salvar_documento, salvar_entrada,
  carregar_proximo_numero).

Uso: python tests/dump_regioes_os.py
"""
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ler(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


def achar_def(linhas, nome):
    padrao = re.compile(rf"^\s*def {re.escape(nome)}\s*\(")
    for i, l in enumerate(linhas):
        if padrao.match(l):
            return i
    return None


def limites_funcao(linhas, idx):
    ind = len(linhas[idx]) - len(linhas[idx].lstrip())
    for j in range(idx + 1, len(linhas)):
        l = linhas[j]
        if l.strip() and (len(l) - len(l.lstrip())) <= ind:
            return j
    return len(linhas)


def main():
    menu = ler(os.path.join(RAIZ, "menu.py")).splitlines(keepends=True)
    gestao = ler(os.path.join(RAIZ, "gestao_os.py")).splitlines(keepends=True)
    tela = ler(os.path.join(RAIZ, "tela_os.py")).splitlines(keepends=True)

    # ---- painel (bug #2) ----
    with open(os.path.join(RAIZ, "tests", "_dump_painel.txt"), "w", encoding="utf-8", newline="\n") as f:
        for titulo, a, b in (
            ("chamador painel (2760-2820)", 2760, 2820),
            ("indicadores (3015-3115)", 3015, 3115),
            ("painel fixo + dashboard modular (3260-3540)", 3260, 3540),
        ):
            f.write(f"\n===== menu.py :: {titulo} =====\n")
            for k in range(a - 1, min(b, len(menu))):
                f.write(f"{k + 1}: {menu[k]}")
        f.write("\n===== menu.py :: _consultar_pendencias_login =====\n")
        idx = achar_def(menu, "_consultar_pendencias_login")
        if idx is None:
            f.write("(não encontrada em menu.py)\n")
        else:
            for k in range(idx, limites_funcao(menu, idx)):
                f.write(f"{k + 1}: {menu[k]}")
        f.write("\n===== gestao_os.py :: unpack da UI (290-340) =====\n")
        for k in range(289, min(340, len(gestao))):
            f.write(f"{k + 1}: {gestao[k]}")
    print(f"[OK] tests/_dump_painel.txt")

    # ---- salvar (bug #3) ----
    with open(os.path.join(RAIZ, "tests", "_dump_salvar.txt"), "w", encoding="utf-8", newline="\n") as f:
        for nome in ("salvar_documento", "salvar_entrada", "carregar_proximo_numero"):
            f.write(f"\n===== tela_os.py :: {nome} =====\n")
            idx = achar_def(tela, nome)
            if idx is None:
                f.write("(não encontrada)\n")
                continue
            for k in range(idx, limites_funcao(tela, idx)):
                f.write(f"{k + 1}: {tela[k]}")
    print("[OK] tests/_dump_salvar.txt")

    # ---- resumo rápido no console ----
    texto_tela = "".join(tela)
    print(f"[#3] INSERT orcamentos_aguardo presente: {'INSERT INTO orcamentos_aguardo' in texto_tela.upper() or 'insert into orcamentos_aguardo' in texto_tela.lower()}")
    idx = achar_def(menu, "_consultar_pendencias_login")
    print(f"[#2] _consultar_pendencias_login em menu.py: linha {idx + 1 if idx is not None else '?'}")


if __name__ == "__main__":
    main()
