# -*- coding: utf-8 -*-
"""Valida o funcionamento do módulo core/i18n após a correção.

Executa: python tests/validar_i18n.py  (a partir da raiz do projeto)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import i18n  # noqa: E402

falhas = []


def verificar(nome, obtido, esperado):
    ok = obtido == esperado
    print(f"{'OK ' if ok else 'ERRO'} {nome}: {obtido!r}" + ("" if ok else f" (esperado {esperado!r})"))
    if not ok:
        falhas.append(nome)


# 1) pt_BR carregado por padrão na inicialização
verificar("idioma padrao", i18n.get_default_locale(), "pt_BR")
verificar("idioma ativo", i18n.get_current_locale(), "pt_BR")
verificar("dicionario carregado", i18n.translations_loaded(), True)

# 2) Chaves clássicas
verificar("t(titulo_pdv)", i18n.t("titulo_pdv"), "PDV - Venda de Balcão")
verificar("t(label_pagamentos)", i18n.t("label_pagamentos"), "Pagamentos")
verificar("t(btn_salvar)", i18n.t("btn_salvar"), "Salvar")
verificar("t(titulo_oficina)", i18n.t("titulo_oficina"), "OFICINA DE PESCA")

# 3) Chave em MAIÚSCULAS resolve para a chave em minúsculas
verificar("t(BTN_IMPRIMIR_DANFE_PDV)", i18n.t("BTN_IMPRIMIR_DANFE_PDV"), "Imprimir DANFE")
verificar("t(TITULO_PDV)", i18n.t("TITULO_PDV"), "PDV - Venda de Balcão")

# 4) Chaves novas da migração (ui_*)
verificar("t(ui_dashboard)", i18n.t("ui_dashboard"), "Dashboard")
verificar("t(ui_senha)", i18n.t("ui_senha"), "Senha")

# 5) Chave inexistente -> default -> própria chave (nunca texto quebrado)
verificar("t(inexistente+default)", i18n.t("chave_inexistente", default="Texto"), "Texto")
verificar("t(inexistente)", i18n.t("chave_inexistente"), "chave_inexistente")
verificar("t(None)", i18n.t(None), "")
verificar("t(vazia+default)", i18n.t("", default="X"), "X")

# 6) Troca de idioma + fallback
i18n.set_default_locale("es_UY")
verificar("es btn_salvar", i18n.t("btn_salvar"), "Guardar")
verificar("es fallback ui_dashboard", i18n.t("ui_dashboard"), "Dashboard")

i18n.set_default_locale("en_US")
verificar("en btn_salvar", i18n.t("btn_salvar"), "Save")

i18n.set_default_locale("pt-br")  # normalização de variação de nome
verificar("normalizacao pt-br", i18n.get_current_locale(), "pt_BR")

# 7) Recarga do cache
i18n.reload_translations()
verificar("pos-reload titulo_pdv", i18n.t("titulo_pdv"), "PDV - Venda de Balcão")
verificar("locales_dir", str(i18n.LOCALES_DIR.name), "locales")

print()
if falhas:
    print(f"FALHOU: {len(falhas)} verificacoes: {falhas}")
    sys.exit(1)
print("TODAS AS VERIFICACOES PASSARAM ✔")