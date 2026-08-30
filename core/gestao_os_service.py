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

    try:
        dados_adicionais = json.loads(registro[10] or "{}")
    except Exception:
        dados_adicionais = {}

    equipamento = str(registro[2] or "").strip()
    defeito = str(registro[3] or "").strip()
    resumo = " - ".join(p for p in (equipamento, defeito) if p)

    return {
        "id": registro[0],
        "cliente": registro[1],
        "equipamento": equipamento,
        "defeito": defeito,
        "valor_total": registro[4],
        "sinal": registro[5],
        "saldo": registro[6],
        "status": registro[7],
        "data": registro[8],
        "itens_detalhes": registro[9] or "",
        "resumo_equipamento_defeito": resumo,
        "dados_adicionais": dados_adicionais,
    }
