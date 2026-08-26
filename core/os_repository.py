# -*- coding: utf-8 -*-
"""Persistência de O.S. e orçamentos isolada da interface gráfica."""

from __future__ import annotations

from typing import Any

from config import get_db_connection, get_logger
from reforma_tributaria import garantir_estrutura_reforma_tributaria
from status_os import STATUS_AGUARDANDO_ORCAMENTO, STATUS_ORCAMENTO, normalizar_status_orcamento

logger = get_logger()


def obter_proximo_numero_orcamento_oficial() -> int:
    """Fonte única oficial da O.S. para sequência de numeração de orçamento."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'ultimo_orcamento'")
            res = cursor.fetchone()
            ultimo_config = int(res[0] or 0) if res else 0
            cursor.execute("SELECT COALESCE(MAX(id), 0) FROM orcamentos_aguardo")
            ultimo_banco = int((cursor.fetchone() or [0])[0] or 0)
        return max(ultimo_config, ultimo_banco, 500) + 1
    except Exception as e:
        logger.exception("Erro ao carregar próximo número oficial de orçamento: %s", e)
        return 501


def salvar_orcamento_aguardo_oficial(os_id: int, dados: dict[str, Any], sinal: float = 0.0, saldo: float = 0.0) -> None:
    """Persistência oficial de O.S. usada pela tela e por fluxos rápidos do PDV."""
    if not isinstance(dados, dict):
        raise ValueError("Dados inválidos para salvar O.S.")

    status_final = normalizar_status_orcamento(dados.get("status", "AGUARDANDO"))

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO orcamentos_aguardo
            (id, cliente, telefone_cliente_whatsapp, equipamento, defeito, resumo_equipamento_defeito,
             valor_total, sinal, saldo, status, data, itens_detalhes, dados_adicionais)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(os_id),
                str(dados.get("cliente", "")),
                str(dados.get("telefone_cliente_whatsapp", "")),
                str(dados.get("equipamento", "")),
                str(dados.get("defeito", "")),
                str(dados.get("resumo_equipamento_defeito", "")),
                float(dados.get("total", 0.0) or 0.0),
                float(sinal or 0.0),
                float(saldo or 0.0),
                str(status_final),
                str(dados.get("data", "")),
                str(dados.get("itens_json", "[]")),
                str(dados.get("dados_adicionais", "{}")),
            ),
        )
        cursor.execute("INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ultimo_orcamento', ?)", (int(os_id),))
        conn.commit()


def garantir_colunas_orcamentos_aguardo() -> None:
    """Garante estrutura mínima do banco usada pela tela de O.S."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS status_orcamento (
                    status TEXT PRIMARY KEY,
                    ativo INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            for status in ("ORÇAMENTO", "AGUARDANDO ORÇAMENTO", "EM ANDAMENTO", "APROVADO", "FINALIZADO", "REPROVADO", "ENTREGUE"):
                cursor.execute(
                    "INSERT OR REPLACE INTO status_orcamento (status, ativo) VALUES (?, 1)",
                    (status,),
                )
            cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO'", (STATUS_ORCAMENTO,))
            cursor.execute("UPDATE orcamentos_aguardo SET status = ? WHERE UPPER(COALESCE(status,'')) = 'AGUARDANDO ORCAMENTO'", (STATUS_AGUARDANDO_ORCAMENTO,))
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS esquemas_vistas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fabricante TEXT,
                    modelo TEXT,
                    url TEXT UNIQUE,
                    origem TEXT
                )
                """
            )
            cursor.execute("PRAGMA table_info(orcamentos_aguardo)")
            cols = {row[1] for row in cursor.fetchall()}
            if "telefone_cliente_whatsapp" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN telefone_cliente_whatsapp TEXT")
            if "resumo_equipamento_defeito" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN resumo_equipamento_defeito TEXT")
            if "status_entrega" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN status_entrega TEXT")
            if "data_finalizacao" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_finalizacao TEXT")
            if "data_entrega" not in cols:
                cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_entrega TEXT")
            garantir_estrutura_reforma_tributaria(cursor)
            cursor.execute(
                """
                UPDATE orcamentos_aguardo
                SET resumo_equipamento_defeito = TRIM(
                        COALESCE(NULLIF(equipamento, ''), '') ||
                        CASE
                            WHEN COALESCE(NULLIF(equipamento, ''), '') <> ''
                             AND COALESCE(NULLIF(defeito, ''), '') <> '' THEN ' - '
                            ELSE ''
                        END ||
                        COALESCE(NULLIF(defeito, ''), '')
                    )
                WHERE COALESCE(NULLIF(resumo_equipamento_defeito, ''), '') = ''
                """
            )
            cursor.execute(
                """
                UPDATE orcamentos_aguardo
                SET status_entrega = COALESCE(NULLIF(status_entrega, ''), 'PENDENTE'),
                    data_finalizacao = COALESCE(NULLIF(data_finalizacao, ''), 'Vazio'),
                    data_entrega = COALESCE(NULLIF(data_entrega, ''), 'Vazio')
                WHERE status_entrega IS NULL OR status_entrega = ''
                   OR data_finalizacao IS NULL OR data_finalizacao = ''
                   OR data_entrega IS NULL OR data_entrega = ''
                """
            )
            conn.commit()
    except Exception as exc:
        logger.info("Falha ao garantir colunas extras de orcamentos_aguardo: %s", exc)
