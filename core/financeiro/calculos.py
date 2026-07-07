# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""Regras de cálculo financeiro compartilhadas pelo sistema."""

from __future__ import annotations

from typing import Any, Iterable


class OSCalculator:
    """Centraliza cálculos da ordem de serviço sem acoplar a interface."""

    @staticmethod
    def parse_monetario(valor_str: Any, default: float = 0.0) -> float:
        """Converte texto monetário para float aceitando vírgula ou ponto."""
        try:
            texto = str(valor_str).strip().replace("R$", "").replace(" ", "")
            if not texto:
                return float(default)

            # Trata separadores de milhar/decimal em formatos como:
            # 1.234,56 | 1,234.56 | 1234,56 | 1234.56
            if "," in texto and "." in texto:
                if texto.rfind(",") > texto.rfind("."):
                    texto = texto.replace(".", "").replace(",", ".")
                else:
                    texto = texto.replace(",", "")
            elif "," in texto:
                texto = texto.replace(",", ".")

            if texto in {"", "-", ".", "-."}:
                return float(default)

            return float(texto)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def calcular_total(
        itens: Iterable[Any],
        desconto: Any = 0.0,
        frete: Any = 0.0,
        adicional: Any = 0.0,
    ) -> float:
        """Calcula o total da O.S. preservando a regra atual da tela."""
        soma_itens = sum(OSCalculator.parse_monetario(item) for item in itens)
        valor_desconto = OSCalculator.parse_monetario(desconto)
        valor_frete = OSCalculator.parse_monetario(frete)
        valor_adicional = OSCalculator.parse_monetario(adicional)
        return (soma_itens + valor_adicional + valor_frete) - valor_desconto

    @staticmethod
    def calcular_sinal(total: Any, percentual: float = 50) -> float:
        """Calcula o sinal com base em um percentual do total."""
        valor_total = OSCalculator.parse_monetario(total)
        return valor_total * (float(percentual) / 100.0)

    @staticmethod
    def calcular_sinal_por_forma(
        total: Any,
        forma_de_pagamento: Any,
        percentual_sinal: float = 50,
    ) -> float:
        """Aplica regra de negócio: 100% total não tem sinal."""
        forma = str(forma_de_pagamento or "").strip().lower()
        if forma in {"100%_total", "100_total", "vista", "100%", "100%_entrega", "entrega"}:
            return 0.0
        return OSCalculator.calcular_sinal(total, percentual=percentual_sinal)


def parse_monetario(valor_str: Any, default: float = 0.0) -> float:
    """Wrapper público para padronizar o parse monetário."""
    return OSCalculator.parse_monetario(valor_str, default=default)


def formatar_monetario(valor: Any, prefixo: str = "R$ ") -> str:
    """Formata um valor monetário seguindo o padrão textual atual do sistema."""
    valor_float = parse_monetario(valor)
    return f"{prefixo}{valor_float:.2f}"


def modulo_pronto() -> bool:
    """Sinaliza que a estrutura-base do módulo financeiro já existe."""
    return True