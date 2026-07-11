# -*- coding: utf-8 -*-
"""Utilitarios para leitura dos dados institucionais da oficina.

Este modulo e utilizado pelo PDV para preencher comprovantes e XMLs.
"""

from __future__ import annotations

from config import get_db_connection


def obter_dados_oficina() -> dict:
    """Retorna dados da oficina com fallback seguro.

    Estrutura retornada:
    - nome_oficina
    - cnpj_oficina
    - endereco_oficina
    - telefone_oficina
    - chave_pix
    - logo_path
    - logo_patrocinador_path
    """
    dados_padrao = {
        "nome_oficina": "OFICINA DE PESCA",
        "cnpj_oficina": "",
        "endereco_oficina": "",
        "telefone_oficina": "",
        "chave_pix": "",
        "logo_path": "",
        "logo_patrocinador_path": "",
    }

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    COALESCE(nome_oficina, ''),
                    COALESCE(cnpj_oficina, ''),
                    COALESCE(endereco_oficina, ''),
                    COALESCE(telefone_oficina, ''),
                    COALESCE(chave_pix, ''),
                    COALESCE(logo_path, ''),
                    COALESCE(logo_patrocinador_path, '')
                FROM dados_oficina
                WHERE id = 1
                LIMIT 1
                """
            )
            row = cursor.fetchone()
            if not row:
                return dados_padrao

            return {
                "nome_oficina": str(row[0] or "").strip() or dados_padrao["nome_oficina"],
                "cnpj_oficina": str(row[1] or "").strip(),
                "endereco_oficina": str(row[2] or "").strip(),
                "telefone_oficina": str(row[3] or "").strip(),
                "chave_pix": str(row[4] or "").strip(),
                "logo_path": str(row[5] or "").strip(),
                "logo_patrocinador_path": str(row[6] or "").strip(),
            }
    except Exception:
        return dados_padrao
