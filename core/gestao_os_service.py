# -*- coding: utf-8 -*-
"""Regras de negócio de gestão de O.S. isoladas da interface gráfica."""

from __future__ import annotations

import json
from typing import Any

from core.gestao_os_repository import alterar_status_orcamento, buscar_dados_orcamento, listar_orcamentos_para_gestao


def listar_orcamentos_gestao() -> list[tuple[Any, ...]]:
    return listar_orcamentos_para_gestao()


def mudar_status_orcamento(os_id: int, novo_status: str) -> None:
    alterar_status_orcamento(os_id, novo_status)


def carregar_dados_orcamento(os_id: int) -> dict[str, Any] | None:
    registro = buscar_dados_orcamento(os_id)
    if not registro:
        return None

    return {
        "id": registro[0],
        "cliente": registro[1],
        "equipamento": registro[2],
        "defeito": registro[3],
        "valor_total": registro[4],
        "sinal": registro[5],
        "saldo": registro[6],
        "status": registro[7],
        "data": registro[8],
        "resumo_equipamento_defeito": registro[9],
        "dados_adicionais": json.loads(registro[10] or "{}"),
    }
