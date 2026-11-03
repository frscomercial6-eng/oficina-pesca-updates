# -*- coding: utf-8 -*-
"""Persistência de dados financeiros isolada da interface gráfica."""

from __future__ import annotations

from datetime import datetime
import math
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


def _valor_em_centavos(valor: Any) -> int:
    try:
        valor_float = float(valor)
    except (TypeError, ValueError) as exc:
        raise ValueError("Valor financeiro inválido.") from exc
    if not math.isfinite(valor_float):
        raise ValueError("Valor financeiro inválido.")
    return int(round(valor_float * 100))


def _pagamentos_os(cursor, os_id: int, etapa: str | None = None) -> list[tuple[Any, ...]]:
    prefixo_os = f"O.S. {int(os_id)} - %"
    prefixo_sinal = f"SINAL O.S. {int(os_id)} - %"
    prefixo_entrega = f"ENTREGA O.S. {int(os_id)} - %"
    filtros = {
        "APROVACAO": "(descricao LIKE ? OR descricao LIKE ?)",
        "ENTREGA": "descricao LIKE ?",
    }
    if etapa:
        etapa_normalizada = str(etapa).strip().upper()
        if etapa_normalizada not in filtros:
            raise ValueError(f"Etapa financeira inválida: {etapa}")
        prefixos = (
            (prefixo_os, prefixo_sinal)
            if etapa_normalizada == "APROVACAO"
            else (prefixo_entrega,)
        )
        where_etapa = filtros[etapa_normalizada]
        cursor.execute(
            f"""
            SELECT id, descricao, valor, metodo_pagamento
            FROM fluxo_caixa
            WHERE UPPER(COALESCE(tipo, '')) = 'ENTRADA'
              AND UPPER(COALESCE(categoria, '')) IN ('ORDEM DE SERVICO', 'ORDEM DE SERVIÇO')
              AND {where_etapa}
            ORDER BY id
            """,
            prefixos,
        )
    else:
        cursor.execute(
            """
            SELECT id, descricao, valor, metodo_pagamento
            FROM fluxo_caixa
            WHERE UPPER(COALESCE(tipo, '')) = 'ENTRADA'
              AND UPPER(COALESCE(categoria, '')) IN ('ORDEM DE SERVICO', 'ORDEM DE SERVIÇO')
              AND (descricao LIKE ? OR descricao LIKE ? OR descricao LIKE ?)
            ORDER BY id
            """,
            (prefixo_os, prefixo_sinal, prefixo_entrega),
        )
    return cursor.fetchall()


def obter_total_recebido_os(cursor, os_id: int) -> int:
    """Retorna em centavos o total de entradas já relacionadas à O.S."""
    return sum(_valor_em_centavos(registro[2]) for registro in _pagamentos_os(cursor, os_id))


def registrar_recebimentos_os(
    cursor,
    os_id: int,
    cliente: str,
    pagamentos: list[tuple[str, Any]],
    valor_esperado: Any,
    etapa: str,
    data: str,
) -> bool:
    """Registra parcelas de uma etapa da O.S. como uma operação idempotente."""
    etapa_normalizada = str(etapa or "").strip().upper()
    if etapa_normalizada not in {"APROVACAO", "ENTREGA"}:
        raise ValueError(f"Etapa financeira inválida: {etapa}")

    esperado_centavos = _valor_em_centavos(valor_esperado)
    parcelas = []
    metodos_validos = {"PIX", "DINHEIRO", "CARTAO", "CARTÃO"}
    for metodo, valor in pagamentos:
        metodo_normalizado = str(metodo or "").strip().upper()
        valor_centavos = _valor_em_centavos(valor)
        if metodo_normalizado not in metodos_validos:
            raise ValueError(f"Forma de pagamento inválida: {metodo}")
        if valor_centavos <= 0:
            raise ValueError("Cada parcela deve ter valor maior que zero.")
        parcelas.append((metodo_normalizado, valor_centavos))

    if esperado_centavos <= 0:
        if parcelas:
            raise ValueError("Não há valor pendente para registrar.")
        return False
    if not parcelas or sum(valor for _, valor in parcelas) != esperado_centavos:
        raise ValueError("A soma dos pagamentos não corresponde ao valor esperado.")

    existentes = _pagamentos_os(cursor, os_id, etapa_normalizada)
    if existentes:
        total_existente = sum(_valor_em_centavos(registro[2]) for registro in existentes)
        if total_existente == esperado_centavos:
            return False
        raise sqlite3.Error(
            f"A O.S. {int(os_id)} já possui recebimentos parciais nesta etapa "
            f"(R$ {total_existente / 100:.2f}); confira o histórico antes de reprocessar."
        )

    prefixo = f"O.S. {int(os_id)} - {str(cliente or '').strip()}"
    if etapa_normalizada == "ENTREGA":
        prefixo = f"ENTREGA {prefixo}"
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM fluxo_caixa WHERE UPPER(COALESCE(tipo, '')) = 'ENTRADA' "
            "AND UPPER(COALESCE(categoria, '')) IN ('ORDEM DE SERVICO', 'ORDEM DE SERVIÇO') "
            "AND descricao LIKE ?",
            (f"SINAL O.S. {int(os_id)} - %",),
        )
        if int(cursor.fetchone()[0] or 0):
            prefixo = f"SINAL {prefixo}"

    for metodo, valor_centavos in parcelas:
        descricao = f"{prefixo} [{etapa_normalizada}] [{metodo}]"
        cursor.execute(
            """
            INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES (?, ?, 'ENTRADA', ?, 'ORDEM DE SERVICO', ?)
            """,
            (data, descricao, valor_centavos / 100, metodo),
        )
    return True


def editar_lancamento_financeiro(lancamento_id: int, descricao: str, valor: float, categoria: str, metodo_pagamento: str) -> None:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fluxo_caixa SET descricao = ?, valor = ?, categoria = ?, metodo_pagamento = ? WHERE id = ?",
            (descricao, valor, categoria, metodo_pagamento, lancamento_id),
        )
        conn.commit()


def excluir_lancamento_financeiro(lancamento_id: int, usuario: str = "") -> None:
    """Exclui somente o lançamento selecionado e registra seus dados no histórico."""
    try:
        lancamento_id = int(lancamento_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Identificador de lançamento inválido.") from exc

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        cursor.execute(
            """
            SELECT data, descricao, tipo, valor, categoria, metodo_pagamento
            FROM fluxo_caixa
            WHERE id = ?
            """,
            (lancamento_id,),
        )
        registro = cursor.fetchone()
        if registro is None:
            raise sqlite3.Error("Lançamento não encontrado.")

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS historico_exclusoes_fluxo_caixa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lancamento_id INTEGER NOT NULL,
                data_exclusao TEXT NOT NULL,
                usuario TEXT,
                data TEXT,
                descricao TEXT,
                tipo TEXT,
                valor REAL,
                categoria TEXT,
                metodo_pagamento TEXT
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO historico_exclusoes_fluxo_caixa
                (lancamento_id, data_exclusao, usuario, data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                lancamento_id,
                datetime.now().isoformat(timespec="seconds"),
                str(usuario or ""),
                *registro,
            ),
        )
        cursor.execute("DELETE FROM fluxo_caixa WHERE id = ?", (lancamento_id,))
        if cursor.rowcount != 1:
            raise sqlite3.Error("O lançamento selecionado não foi excluído.")
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
