# -*- coding: utf-8 -*-
"""Persistência de dados financeiros isolada da interface gráfica."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from config import get_db_connection


def _normalizar_data_iso(valor: Any) -> str:
    """Normaliza datas de filtro para o formato ISO (YYYY-MM-DD).

    Aceita tanto o formato brasileiro (DD/MM/AAAA) quanto ISO (AAAA-MM-DD),
    pois o banco armazena as datas do fluxo de caixa como DD/MM/AAAA e as
    telas podem enviar filtros em qualquer um dos dois formatos.
    """
    txt = str(valor or "").strip()
    if not txt or txt.upper() == "VAZIO":
        return ""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", txt)
    if m:
        dia, mes, ano = m.groups()
        return f"{int(ano):04d}-{int(mes):02d}-{int(dia):02d}"
    return txt[:10]


def _expressao_data_sql(coluna: str = "data") -> str:
    """Expressão SQL que converte a data armazenada (DD/MM/AAAA ou ISO) em data ISO comparável."""
    return (
        f"COALESCE("
        f"CASE WHEN substr({coluna}, 3, 1) = '/' AND length({coluna}) >= 10 "
        f"THEN date(substr({coluna}, 7, 4) || '-' || substr({coluna}, 4, 2) || '-' || substr({coluna}, 1, 2)) END, "
        f"date({coluna}))"
    )


def listar_lancamentos_financeiro(data_inicio: str, data_fim: str, busca: str = "") -> tuple[list[tuple[Any, ...]], float, list[tuple[str, float]]]:
    """Retorna lançamentos, saldo e resumo por método de pagamento.

    O filtro de período aceita datas em DD/MM/AAAA ou AAAA-MM-DD e compara
    corretamente com as datas gravadas no banco (armazenadas como DD/MM/AAAA).
    """
    d_ini = _normalizar_data_iso(data_inicio)
    d_fim = _normalizar_data_iso(data_fim)
    if not d_ini or not d_fim:
        raise sqlite3.Error("Período inválido para consulta do fluxo de caixa.")

    data_sql = _expressao_data_sql("data")
    where = [f"{data_sql} BETWEEN date(?) AND date(?)"]
    params: list[Any] = [d_ini, d_fim]

    termo = str(busca or "").strip().upper()
    if termo:
        where.append(
            "(UPPER(COALESCE(descricao, '')) LIKE ? "
            "OR UPPER(COALESCE(categoria, '')) LIKE ? "
            "OR UPPER(COALESCE(metodo_pagamento, '')) LIKE ?)"
        )
        like = f"%{termo}%"
        params.extend([like, like, like])

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, data, descricao, tipo, valor, COALESCE(categoria, 'GERAL'), COALESCE(metodo_pagamento, '-')
            FROM fluxo_caixa
            WHERE {' AND '.join(where)}
            ORDER BY id DESC
            """,
            tuple(params),
        )
        registros = cursor.fetchall()

        cursor.execute(
            "SELECT COALESCE(SUM(CASE WHEN UPPER(tipo)='ENTRADA' THEN valor ELSE -valor END), 0) FROM fluxo_caixa"
        )
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
