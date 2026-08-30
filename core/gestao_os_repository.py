# -*- coding: utf-8 -*-
"""Persistência de gestão de orçamentos isolada da interface gráfica."""

from __future__ import annotations

from typing import Any

from config import get_db_connection


def listar_orcamentos_para_gestao() -> list[tuple[Any, ...]]:
    """Lista O.S. para a consulta da gestão.

    Layout fixo de 13 colunas consumido pela interface (gestao_os.py):
      0 id_orc, 1 id_cli, 2 nome_cli, 3 equipamento, 4 defeito, 5 total,
      6 sinal, 7 saldo, 8 status, 9 data, 10 itens_detalhes (JSON),
      11 telefone_whatsapp, 12 dados_adicionais
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT oa.id, COALESCE(c.id, ''), oa.cliente, oa.equipamento, oa.defeito, oa.valor_total,
                   oa.sinal, oa.saldo, oa.status, oa.data,
                   COALESCE(oa.itens_detalhes, ''),
                   COALESCE(c.telefone_cliente_whatsapp, ''),
                   COALESCE(oa.dados_adicionais, '')
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
                   COALESCE(itens_detalhes, ''), COALESCE(dados_adicionais, '')
            FROM orcamentos_aguardo
            WHERE id = ?
            """,
            (os_id,),
        )
        return cursor.fetchone()
