# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any


def _colunas_tabela(cursor: sqlite3.Cursor, nome_tabela: str) -> set[str]:
    cursor.execute(f"PRAGMA table_info({nome_tabela})")
    return {str(row[1] or "").strip().lower() for row in cursor.fetchall()}


def _tabela_existe(cursor: sqlite3.Cursor, nome_tabela: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (nome_tabela,),
    )
    return cursor.fetchone() is not None


def _adicionar_coluna(cursor: sqlite3.Cursor, tabela: str, coluna: str, ddl: str) -> None:
    if not _tabela_existe(cursor, tabela):
        return
    if coluna not in _colunas_tabela(cursor, tabela):
        cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {ddl}")


def garantir_estrutura_reforma_tributaria(cursor: sqlite3.Cursor) -> None:
    """Cria a estrutura latente de IBS/CBS sem alterar o cálculo atual."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS configuracao_reforma_tributaria (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            regime TEXT DEFAULT 'latente',
            ativo INTEGER NOT NULL DEFAULT 0,
            vigencia_inicio TEXT,
            aliquota_ibs_padrao REAL DEFAULT 0,
            aliquota_cbs_padrao REAL DEFAULT 0,
            split_payment_padrao INTEGER DEFAULT 0,
            xml_mapeamento_json TEXT DEFAULT '{}',
            observacoes TEXT,
            atualizado_em TEXT
        )
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO configuracao_reforma_tributaria
            (id, regime, ativo, vigencia_inicio, aliquota_ibs_padrao, aliquota_cbs_padrao,
             split_payment_padrao, xml_mapeamento_json, observacoes, atualizado_em)
        VALUES
            (1, 'latente', 0, '', 0, 0, 0, '{}', '', '')
        """
    )

    for tabela in ("produtos",):
        if not _tabela_existe(cursor, tabela):
            continue
        _adicionar_coluna(cursor, tabela, "aliquota_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "aliquota_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "reforma_tributaria_json", "TEXT DEFAULT '{}'" )

    for tabela in ("pdv_vendas",):
        if not _tabela_existe(cursor, tabela):
            continue
        _adicionar_coluna(cursor, tabela, "aliquota_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "aliquota_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "split_payment_json", "TEXT DEFAULT '{}'" )
        _adicionar_coluna(cursor, tabela, "reforma_tributaria_json", "TEXT DEFAULT '{}'" )

    for tabela in ("orcamentos_aguardo",):
        if not _tabela_existe(cursor, tabela):
            continue
        _adicionar_coluna(cursor, tabela, "aliquota_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "aliquota_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "reforma_tributaria_json", "TEXT DEFAULT '{}'" )

    for tabela in ("fluxo_caixa", "financeiro_geral"):
        if not _tabela_existe(cursor, tabela):
            continue
        _adicionar_coluna(cursor, tabela, "aliquota_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "aliquota_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_ibs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "valor_cbs", "REAL DEFAULT 0")
        _adicionar_coluna(cursor, tabela, "split_payment_json", "TEXT DEFAULT '{}'" )


def ler_config_reforma_tributaria(cursor: sqlite3.Cursor) -> dict[str, Any]:
    garantir_estrutura_reforma_tributaria(cursor)
    cursor.execute(
        """
        SELECT id, regime, ativo, vigencia_inicio, aliquota_ibs_padrao, aliquota_cbs_padrao,
               split_payment_padrao, xml_mapeamento_json, observacoes, atualizado_em
        FROM configuracao_reforma_tributaria
        WHERE id = 1
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    if not row:
        return {
            "id": 1,
            "regime": "latente",
            "ativo": 0,
            "vigencia_inicio": "",
            "aliquota_ibs_padrao": 0.0,
            "aliquota_cbs_padrao": 0.0,
            "split_payment_padrao": 0,
            "xml_mapeamento_json": "{}",
            "observacoes": "",
            "atualizado_em": "",
        }
    return {
        "id": int(row[0] or 1),
        "regime": str(row[1] or "latente"),
        "ativo": int(row[2] or 0),
        "vigencia_inicio": str(row[3] or ""),
        "aliquota_ibs_padrao": float(row[4] or 0),
        "aliquota_cbs_padrao": float(row[5] or 0),
        "split_payment_padrao": int(row[6] or 0),
        "xml_mapeamento_json": str(row[7] or "{}"),
        "observacoes": str(row[8] or ""),
        "atualizado_em": str(row[9] or ""),
    }


def salvar_config_reforma_tributaria(cursor: sqlite3.Cursor, dados: dict[str, Any]) -> None:
    garantir_estrutura_reforma_tributaria(cursor)
    payload = dict(dados or {})
    xml_map = payload.get("xml_mapeamento_json")
    if not isinstance(xml_map, str):
        xml_map = json.dumps(xml_map or {}, ensure_ascii=False)
    cursor.execute(
        """
        UPDATE configuracao_reforma_tributaria
        SET regime = ?,
            ativo = ?,
            vigencia_inicio = ?,
            aliquota_ibs_padrao = ?,
            aliquota_cbs_padrao = ?,
            split_payment_padrao = ?,
            xml_mapeamento_json = ?,
            observacoes = ?,
            atualizado_em = ?
        WHERE id = 1
        """,
        (
            str(payload.get("regime") or "latente").strip() or "latente",
            int(bool(payload.get("ativo", 0))),
            str(payload.get("vigencia_inicio") or "").strip(),
            float(payload.get("aliquota_ibs_padrao") or 0),
            float(payload.get("aliquota_cbs_padrao") or 0),
            int(bool(payload.get("split_payment_padrao", 0))),
            xml_map,
            str(payload.get("observacoes") or "").strip(),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )


def montar_mapeamento_xml_futuro(registro: dict[str, Any] | None, quantidade: float = 1.0, total_item: float | None = None) -> dict[str, Any]:
    dados = dict(registro or {})
    aliquota_ibs = float(dados.get("aliquota_ibs") or 0)
    aliquota_cbs = float(dados.get("aliquota_cbs") or 0)
    total_base = float(total_item if total_item is not None else dados.get("total_item") or 0)
    if total_base <= 0 and quantidade:
        total_base = float(dados.get("valor_base") or 0) * float(quantidade or 1)

    valor_ibs = float(dados.get("valor_ibs") or (total_base * aliquota_ibs / 100.0 if total_base > 0 else 0))
    valor_cbs = float(dados.get("valor_cbs") or (total_base * aliquota_cbs / 100.0 if total_base > 0 else 0))
    split_payment = int(dados.get("split_payment") or dados.get("split_payment_padrao") or 0)

    return {
        "IBS": {"pIBS": aliquota_ibs, "vIBS": valor_ibs},
        "CBS": {"pCBS": aliquota_cbs, "vCBS": valor_cbs},
        "SplitPayment": {"indSplitPayment": split_payment, "vBase": total_base},
        "reforma_tributaria_json": dados.get("reforma_tributaria_json") or "{}",
    }