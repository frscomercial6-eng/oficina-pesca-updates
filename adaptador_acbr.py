# -*- coding: utf-8 -*-
"""Adaptador mínimo para comunicação por arquivos com ACBrMonitor."""

import os

PASTA_ENTRADA = r"C:\ACBrMonitor\ENT.txt"
PASTA_SAIDA = r"C:\ACBrMonitor\SAI.txt"


def ler_ncm_produto(produto: dict) -> str:
    """Lê e normaliza o NCM de um produto para uso na comunicação fiscal."""
    ncm_bruto = str((produto or {}).get("ncm", "") or "")
    return "".join(ch for ch in ncm_bruto if ch.isdigit())[:8]


def verificar_status_acbr() -> str:
    """Escreve o comando de status no arquivo de entrada do ACBrMonitor."""
    pasta_destino = os.path.dirname(PASTA_ENTRADA)
    if pasta_destino:
        os.makedirs(pasta_destino, exist_ok=True)

    with open(PASTA_ENTRADA, "w", encoding="utf-8") as arquivo_entrada:
        arquivo_entrada.write("NFe.StatusServico\n")

    return PASTA_ENTRADA
