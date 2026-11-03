# -*- coding: utf-8 -*-
"""Persistência de gestão de orçamentos isolada da interface gráfica."""

from __future__ import annotations

import json
from datetime import datetime
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
                   COALESCE(oa.telefone_cliente_whatsapp, ''),
                   COALESCE(oa.dados_adicionais, '')
            FROM orcamentos_aguardo oa
            LEFT JOIN clientes c ON UPPER(TRIM(c.nome)) = UPPER(TRIM(oa.cliente))
            WHERE UPPER(COALESCE(oa.status, '')) <> 'EXCLUIDO'
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
            WHERE id = ? AND UPPER(COALESCE(status, '')) <> 'EXCLUIDO'
            """,
            (os_id,),
        )
        return cursor.fetchone()


def arquivar_orcamento_gestao(os_id: int, usuario: str = "") -> int:
    """Arquiva a O.S. e registra um snapshot sem apagar dados associados."""
    try:
        os_id = int(os_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Identificador de O.S. inválido.") from exc
    if os_id <= 0:
        raise ValueError("Identificador de O.S. inválido.")

    padrao_os = f"O.S. {os_id} - %"
    padrao_sinal = f"SINAL O.S. {os_id} - %"
    padrao_entrega = f"ENTREGA O.S. {os_id} - %"
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute("SELECT * FROM orcamentos_aguardo WHERE id = ?", (os_id,))
        registro = cursor.fetchone()
        if registro is None:
            raise ValueError(f"O.S. {os_id} não encontrada.")
        colunas = [coluna[0] for coluna in cursor.description]
        snapshot_os = dict(zip(colunas, registro))
        status_anterior = str(snapshot_os.get("status") or "")
        if status_anterior.strip().upper() == "EXCLUIDO":
            raise ValueError(f"A O.S. {os_id} já está arquivada.")

        cursor.execute(
            """
            SELECT id, data, descricao, tipo, valor, categoria, metodo_pagamento
            FROM fluxo_caixa
            WHERE descricao LIKE ? OR descricao LIKE ? OR descricao LIKE ?
            ORDER BY id
            """,
            (padrao_os, padrao_sinal, padrao_entrega),
        )
        lancamentos = [dict(zip(
            ("id", "data", "descricao", "tipo", "valor", "categoria", "metodo_pagamento"),
            row,
        )) for row in cursor.fetchall()]

        historico_financeiro = []
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'historico_exclusoes_fluxo_caixa'"
        )
        if cursor.fetchone():
            cursor.execute(
                """
                SELECT id, lancamento_id, data_exclusao, usuario, data, descricao, tipo, valor, categoria, metodo_pagamento
                FROM historico_exclusoes_fluxo_caixa
                WHERE descricao LIKE ? OR descricao LIKE ? OR descricao LIKE ?
                ORDER BY id
                """,
                (padrao_os, padrao_sinal, padrao_entrega),
            )
            historico_financeiro = [
                dict(zip(
                    ("id", "lancamento_id", "data_exclusao", "usuario", "data", "descricao", "tipo", "valor", "categoria", "metodo_pagamento"),
                    row,
                ))
                for row in cursor.fetchall()
            ]

        registros_legados = []
        cursor.execute("PRAGMA table_info(ordens_servico)")
        colunas_legadas = {coluna[1] for coluna in cursor.fetchall()}
        if "id_os" in colunas_legadas:
            cursor.execute("SELECT * FROM ordens_servico WHERE id_os = ?", (os_id,))
            nomes_legados = [coluna[0] for coluna in cursor.description]
            registros_legados = [
                dict(zip(nomes_legados, row))
                for row in cursor.fetchall()
            ]

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_exclusoes_os (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                os_id INTEGER NOT NULL,
                data_exclusao TEXT NOT NULL,
                usuario TEXT,
                status_anterior TEXT,
                lancamentos_financeiros INTEGER NOT NULL DEFAULT 0,
                snapshot_json TEXT NOT NULL
            )
            """
        )
        snapshot = {
            "orcamentos_aguardo": snapshot_os,
            "lancamentos_financeiros": lancamentos,
            "historico_financeiro": historico_financeiro,
            "registros_legados": registros_legados,
        }
        cursor.execute(
            """
            INSERT INTO historico_exclusoes_os
                (os_id, data_exclusao, usuario, status_anterior, lancamentos_financeiros, snapshot_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                os_id,
                datetime.now().isoformat(timespec="seconds"),
                str(usuario or ""),
                status_anterior,
                len(lancamentos) + len(historico_financeiro),
                json.dumps(snapshot, ensure_ascii=False, default=str),
            ),
        )
        cursor.execute(
            "UPDATE orcamentos_aguardo SET status = 'EXCLUIDO' WHERE id = ? AND UPPER(COALESCE(status, '')) <> 'EXCLUIDO'",
            (os_id,),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(f"Não foi possível arquivar a O.S. {os_id}.")
        conn.commit()
        return len(lancamentos) + len(historico_financeiro)
