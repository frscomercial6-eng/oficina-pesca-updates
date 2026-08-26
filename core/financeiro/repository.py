# -*- coding: utf-8 -*-
"""Persistência de dados financeiros isolada da interface gráfica."""

from __future__ import annotations

import sqlite3
from typing import Any

from config import get_db_connection


def listar_lancamentos_financeiro(data_inicio: str, data_fim: str, busca: str = "") -> tuple[list[tuple[Any, ...]], float, list[tuple[str, float]]]:
    """Retorna lançamentos, saldo e resumo por método de pagamento."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, data, descricao, tipo, valor, COALESCE(categoria, 'GERAL'), COALESCE(metodo_pagamento, '-')
            FROM fluxo_caixa
            WHERE data BETWEEN ? AND ?
            """,
            (data_inicio, data_fim),
        )
        if busca:
            cursor.execute(
                """
                SELECT id, data, descricao, tipo, valor, COALESCE(categoria, 'GERAL'), COALESCE(metodo_pagamento, '-')
                FROM fluxo_caixa
                WHERE data BETWEEN ? AND ? AND (
                    UPPER(descricao) LIKE ? OR UPPER(categoria) LIKE ? OR UPPER(metodo_pagamento) LIKE ?
                )
                """,
                (data_inicio, data_fim, f"%{busca.upper()}%", f"%{busca.upper()}%", f"%{busca.upper()}%"),
            )

        registros = cursor.fetchall()
        cursor.execute("SELECT COALESCE(SUM(CASE WHEN UPPER(tipo)='ENTRADA' THEN valor ELSE -valor END), 0) FROM fluxo_caixa")
        saldo_total = float(cursor.fetchone()[0] or 0.0)
        cursor.execute(
            """
            SELECT UPPER(COALESCE(metodo_pagamento, '-')), COALESCE(SUM(valor), 0)
            FROM fluxo_caixa
            GROUP BY UPPER(COALESCE(metodo_pagamento, '-'))
            ORDER BY 1
            """
        )
        pagamentos = cursor.fetchall()

    return registros, saldo_total, pagamentos


def inserir_lancamento_financeiro(data: str, descricao: str, tipo: str, valor: float, categoria: str, metodo_pagamento: str) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?, ?, ?, ?, ?, ?)",
            (data, descricao, tipo, valor, categoria, metodo_pagamento),
        )
        conn.commit()


def editar_lancamento_financeiro(lancamento_id: int, descricao: str, valor: float, categoria: str, metodo_pagamento: str) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fluxo_caixa SET descricao = ?, valor = ?, categoria = ?, metodo_pagamento = ? WHERE id = ?",
            (descricao, valor, categoria, metodo_pagamento, lancamento_id),
        )
        conn.commit()


def estornar_lancamento_financeiro(lancamento_id: int) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data, descricao, tipo, valor, categoria, metodo_pagamento FROM fluxo_caixa WHERE id = ?", (lancamento_id,))
        reg = cursor.fetchone()
        if not reg:
            raise sqlite3.Error("Lançamento não encontrado")
        data, descricao, tipo, valor, categoria, metodo_pagamento = reg
        tipo_oposto = "SAIDA" if str(tipo).upper() == "ENTRADA" else "ENTRADA"
        cursor.execute(
            "INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento) VALUES (?, ?, ?, ?, ?, ?)",
            (data, f"ESTORNO: {descricao}", tipo_oposto, float(valor), categoria, metodo_pagamento),
        )
        conn.commit()
