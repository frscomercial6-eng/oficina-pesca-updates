# -*- coding: utf-8 -*-
"""Regras de negócio financeiras isoladas da interface gráfica."""

from __future__ import annotations

from typing import Any

from core.financeiro.calculos import formatar_monetario
from core.financeiro.repository import listar_lancamentos_financeiro


def calcular_saldo_visual(saldo_total: float) -> tuple[str, str]:
    """Retorna texto e cor do saldo para a interface."""
    cor_saldo = "#2ecc71" if saldo_total >= 0 else "#e74c3c"
    texto = f"SALDO GERAL EM CAIXA: {formatar_monetario(saldo_total)}"
    return texto, cor_saldo


def carregar_dados_financeiros(data_inicio: str, data_fim: str, busca: str = "") -> tuple[list[tuple[Any, ...]], float, list[tuple[str, float]], str, str]:
    """Consulta consolidada para a tela financeira."""
    registros, saldo_total, pagamentos = listar_lancamentos_financeiro(data_inicio, data_fim, busca=busca)
    texto_saldo, cor_saldo = calcular_saldo_visual(saldo_total)
    return registros, saldo_total, pagamentos, texto_saldo, cor_saldo
