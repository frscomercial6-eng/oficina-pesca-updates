# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from typing import Any


def _tabela_existe(cursor: sqlite3.Cursor, nome_tabela: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (nome_tabela,),
    )
    return cursor.fetchone() is not None


def _colunas_tabela(cursor: sqlite3.Cursor, nome_tabela: str) -> set[str]:
    if not _tabela_existe(cursor, nome_tabela):
        return set()
    cursor.execute(f"PRAGMA table_info({nome_tabela})")
    return {str(row[1] or "").strip().lower() for row in cursor.fetchall()}


def _pendencias_fiscais(cursor: sqlite3.Cursor) -> dict[str, Any]:
    colunas_produtos = _colunas_tabela(cursor, "produtos")
    faltando_produtos = [
        coluna
        for coluna in ("aliquota_cbs", "aliquota_ibs", "ncm")
        if coluna not in colunas_produtos
    ]
    falta_config_fiscal = not _tabela_existe(cursor, "configuracao_fiscal")
    return {
        "produtos": faltando_produtos,
        "configuracao_fiscal": falta_config_fiscal,
    }


def criar_backup_seguranca(caminho_banco: str) -> str | None:
    if not caminho_banco or not os.path.exists(caminho_banco):
        return None
    if os.path.getsize(caminho_banco) <= 0:
        return None

    pasta_backup = os.path.join(os.path.dirname(caminho_banco), "backup_seguranca")
    os.makedirs(pasta_backup, exist_ok=True)

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(pasta_backup, f"oficina_pre_migracao_fiscal_2027_{carimbo}.db")
    shutil.copy2(caminho_banco, destino)
    return destino


def executar_migracao_fiscal_2027(caminho_banco: str) -> dict[str, Any]:
    resultado = {
        "alterado": False,
        "backup": None,
        "acoes": [],
    }

    if not caminho_banco:
        return resultado

    os.makedirs(os.path.dirname(caminho_banco), exist_ok=True)

    with sqlite3.connect(caminho_banco) as conn:
        cursor = conn.cursor()
        pendencias = _pendencias_fiscais(cursor)
        precisa_migrar = bool(pendencias["produtos"] or pendencias["configuracao_fiscal"])

        if not precisa_migrar:
            return resultado

        resultado["backup"] = criar_backup_seguranca(caminho_banco)

        for coluna in pendencias["produtos"]:
            if coluna == "aliquota_cbs":
                cursor.execute("ALTER TABLE produtos ADD COLUMN aliquota_cbs REAL DEFAULT 0")
                resultado["acoes"].append("ALTER TABLE produtos ADD COLUMN aliquota_cbs REAL DEFAULT 0")
            elif coluna == "aliquota_ibs":
                cursor.execute("ALTER TABLE produtos ADD COLUMN aliquota_ibs REAL DEFAULT 0")
                resultado["acoes"].append("ALTER TABLE produtos ADD COLUMN aliquota_ibs REAL DEFAULT 0")
            elif coluna == "ncm":
                cursor.execute("ALTER TABLE produtos ADD COLUMN ncm VARCHAR(8)")
                resultado["acoes"].append("ALTER TABLE produtos ADD COLUMN ncm VARCHAR(8)")

        colunas_apos_migracao = _colunas_tabela(cursor, "produtos")
        if "codigo_ncm" in colunas_apos_migracao and "ncm" in colunas_apos_migracao:
            cursor.execute(
                """
                UPDATE produtos
                SET ncm = COALESCE(NULLIF(ncm, ''), codigo_ncm)
                WHERE COALESCE(NULLIF(codigo_ncm, ''), '') <> ''
                """
            )
            resultado["acoes"].append("UPDATE produtos SET ncm = codigo_ncm WHERE ncm vazio")

        if pendencias["configuracao_fiscal"]:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS configuracao_fiscal (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    api_key_plugnotas TEXT,
                    api_key_focusnfe TEXT,
                    ambiente TEXT DEFAULT 'homologacao',
                    parametros_gerais TEXT
                )
                """
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO configuracao_fiscal
                    (id, api_key_plugnotas, api_key_focusnfe, ambiente, parametros_gerais)
                VALUES
                    (1, '', '', 'homologacao', '{}')
                """
            )
            resultado["acoes"].append("CREATE TABLE configuracao_fiscal")

        conn.commit()
        resultado["alterado"] = True

    return resultado


if __name__ == "__main__":
    banco = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oficina.db")
    resultado = executar_migracao_fiscal_2027(banco)
    print(resultado)
