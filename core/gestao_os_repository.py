# -*- coding: utf-8 -*-
"""Persistência de gestão de orçamentos isolada da interface gráfica."""

from __future__ import annotations

from typing import Any

from config import get_db_connection


def listar_orcamentos_para_gestao() -> list[tuple[Any, ...]]:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT oa.id, COALESCE(c.id, ''), oa.cliente, oa.equipamento, oa.defeito, oa.valor_total,
                   oa.sinal, oa.saldo, oa.status, oa.data, oa.resumo_equipamento_defeito, COALESCE(oa.dados_adicionais, '')
            FROM orcamentos_aguardo oa
            LEFT JOIN clientes c ON UPPER(TRIM(c.nome)) = UPPER(TRIM(oa.cliente))
            ORDER BY oa.id DESC
            """
        )
        return cursor.fetchall()


def alterar_status_orcamento(os_id: int, novo_status: str) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE id = ?", (novo_status, os_id))
        conn.commit()


def buscar_dados_orcamento(os_id: int) -> tuple[Any, ...] | None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, cliente, equipamento, defeito, valor_total, sinal, saldo, status, data,
                   resumo_equipamento_defeito, COALESCE(dados_adicionais, '')
            FROM orcamentos_aguardo
            WHERE id = ?
            """,
            (os_id,),
        )
        return cursor.fetchone()
