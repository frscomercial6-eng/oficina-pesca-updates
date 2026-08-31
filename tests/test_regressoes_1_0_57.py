# -*- coding: utf-8 -*-
"""Regressões críticas corrigidas na versão 1.0.57."""

from __future__ import annotations

import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from core.financeiro import repository as financeiro_repository
from core import gestao_os_repository


class TestRegressoes1057(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(
            """
            CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT);
            CREATE TABLE orcamentos_aguardo (
                id INTEGER PRIMARY KEY,
                cliente TEXT,
                equipamento TEXT,
                defeito TEXT,
                valor_total REAL,
                sinal REAL,
                saldo REAL,
                status TEXT,
                data TEXT,
                itens_detalhes TEXT,
                telefone_cliente_whatsapp TEXT,
                dados_adicionais TEXT
            );
            CREATE TABLE fluxo_caixa (
                id INTEGER PRIMARY KEY,
                data TEXT,
                descricao TEXT,
                tipo TEXT,
                valor REAL,
                categoria TEXT,
                metodo_pagamento TEXT
            );
            INSERT INTO clientes (id, nome) VALUES (7, 'Cliente Teste');
            INSERT INTO orcamentos_aguardo VALUES (
                10, 'Cliente Teste', 'Molinete', 'Travado', 150, 50, 100,
                'APROVADO', '31/08/2026', '[]', '5511999999999', 'Observação'
            );
            INSERT INTO fluxo_caixa VALUES
                (1, '30/08/2026', 'Venda balcão', 'ENTRADA', 120, 'PDV', 'PIX'),
                (2, '01/09/2026', 'Compra material', 'SAIDA', 20, 'INSUMOS', 'DINHEIRO');
            """
        )

        @contextmanager
        def conexao_teste():
            yield self.conn

        self.conexao_teste = conexao_teste

    def tearDown(self) -> None:
        self.conn.close()

    def test_consulta_os_le_telefone_da_ordem(self) -> None:
        with patch.object(gestao_os_repository, "get_db_connection", self.conexao_teste):
            linhas = gestao_os_repository.listar_orcamentos_para_gestao()

        self.assertEqual(len(linhas), 1)
        self.assertEqual(len(linhas[0]), 13)
        self.assertEqual(linhas[0][11], "5511999999999")

    def test_fluxo_caixa_filtra_datas_brasileiras_por_periodo(self) -> None:
        with patch.object(financeiro_repository, "get_db_connection", self.conexao_teste):
            registros, saldo, pagamentos = financeiro_repository.listar_lancamentos_financeiro(
                "29/08/2026", "31/08/2026"
            )

        self.assertEqual([registro[0] for registro in registros], [1])
        self.assertEqual(saldo, 100.0)
        self.assertEqual(dict(pagamentos), {"DINHEIRO": 20.0, "PIX": 120.0})

    def test_fluxo_caixa_aplica_busca_sem_perder_periodo(self) -> None:
        with patch.object(financeiro_repository, "get_db_connection", self.conexao_teste):
            registros, _, _ = financeiro_repository.listar_lancamentos_financeiro(
                "2026-08-01", "2026-08-31", "venda"
            )

        self.assertEqual([registro[0] for registro in registros], [1])


if __name__ == "__main__":
    unittest.main()