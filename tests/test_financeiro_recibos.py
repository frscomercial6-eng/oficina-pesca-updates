from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile
import unittest
import zlib
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

import config
import gestao_os
import tela_financeiro
import tela_os
import util_recibo
from core import gestao_os_repository
from core.gestao_os_service import arquivar_orcamento_gestao, listar_orcamentos_gestao
from core import os_repository
from core.financeiro import repository as financeiro_repository
from core.os_service import montar_payload_os


class FakeWidget:
    def __init__(self, *_args, **kwargs):
        self.command = kwargs.get("command")
        self.state = kwargs.get("state")

    def pack(self, **_kwargs):
        return None

    def grid(self, **_kwargs):
        return None

    def grid_columnconfigure(self, *_args, **_kwargs):
        return None

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs["state"]

    def bind(self, *_args, **_kwargs):
        return None


class FakeEntry(FakeWidget):
    def __init__(self, *_args, **kwargs):
        super().__init__(**kwargs)
        self.value = ""
        self.bindings = {}
        FakePaymentWindow.current.entries.append(self)

    def insert(self, _index, value):
        self.value = str(value)

    def delete(self, *_args):
        self.value = ""

    def get(self):
        return self.value

    def bind(self, event, callback):
        self.bindings[event] = callback


class FakePaymentWindow(FakeWidget):
    behavior = "pix"
    current = None

    def __init__(self, *_args, **kwargs):
        super().__init__(**kwargs)
        self.buttons = []
        self.entries = []
        FakePaymentWindow.current = self

    def title(self, *_args):
        return None

    def geometry(self, *_args):
        return None

    def resizable(self, *_args):
        return None

    def attributes(self, *_args):
        return None

    def grab_set(self):
        return None

    def focus_force(self):
        return None

    def lift(self):
        return None

    def destroy(self):
        return None

    def wait_window(self):
        self.buttons[1].command()
        if self.behavior == "cash":
            self.entries[0].value = "0,00"
            self.entries[1].value = "100,00"
            self.entries[1].bindings["<KeyRelease>"](None)
        elif self.behavior == "mixed":
            self.entries[0].value = "50,00"
            self.entries[1].value = "50,00"
            self.entries[1].bindings["<KeyRelease>"](None)
        if self.behavior == "cancel":
            self.buttons[4].command()
        else:
            if self.buttons[3].state != "normal":
                raise AssertionError("Confirmação não habilitada para pagamento válido.")
            self.buttons[3].command()


class FakeButton(FakeWidget):
    def __init__(self, *_args, **kwargs):
        super().__init__(**kwargs)
        FakePaymentWindow.current.buttons.append(self)


class TestFinanceiroRecibos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.menu_import_dir = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.menu_import_dir.cleanup)
        if "menu" not in sys.modules:
            caminho_teste = str(Path(cls.menu_import_dir.name) / "menu_import.db")
            with patch.object(config, "CAMINHO_BANCO", caminho_teste):
                import_module("menu")
        cls.menu = sys.modules["menu"]

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(
            """
            CREATE TABLE clientes (
                id INTEGER PRIMARY KEY,
                nome TEXT
            );
            CREATE TABLE fluxo_caixa (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT,
                descricao TEXT,
                tipo TEXT,
                valor REAL,
                categoria TEXT,
                metodo_pagamento TEXT
            );
            CREATE TABLE orcamentos_aguardo (
                id INTEGER PRIMARY KEY,
                cliente TEXT,
                telefone_cliente_whatsapp TEXT,
                equipamento TEXT,
                defeito TEXT,
                resumo_equipamento_defeito TEXT,
                valor_total REAL,
                sinal REAL,
                saldo REAL,
                itens_detalhes TEXT,
                data TEXT,
                status TEXT,
                dados_adicionais TEXT,
                status_entrega TEXT,
                data_entrega TEXT,
                data_finalizacao TEXT
            );
            CREATE TABLE configuracoes (chave TEXT PRIMARY KEY, valor TEXT);
            CREATE TABLE dados_oficina (
                id INTEGER PRIMARY KEY,
                nome_oficina TEXT,
                endereco_oficina TEXT,
                telefone_oficina TEXT
            );
            INSERT INTO orcamentos_aguardo
                (id, cliente, equipamento, defeito, valor_total, saldo, itens_detalhes,
                 data, status, status_entrega, data_entrega, data_finalizacao)
            VALUES
                (21, 'Cliente Exemplo', 'Carretilha Teste', 'Revisao completa',
                 100, 100, '[["Rolamento",2],["Mao de obra",1]]',
                 '03/11/2026', 'FINALIZADO', '', '', '');
            INSERT INTO dados_oficina
                (id, nome_oficina, endereco_oficina, telefone_oficina)
            VALUES (1, 'Oficina Teste', 'Rua do Porto, 10', '11999990000');
            """
        )
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

    def tearDown(self):
        self.conn.close()

    @contextmanager
    def conexao_teste(self):
        try:
            yield self.conn
        except Exception:
            self.conn.rollback()
            raise

    def registrar_aprovacao(self, pagamentos):
        dados_os = {
            "cliente": "Cliente Exemplo",
            "telefone_cliente_whatsapp": "11999990000",
            "equipamento": "Carretilha Teste",
            "defeito": "Revisao completa",
            "resumo_equipamento_defeito": "Carretilha Teste - Revisao completa",
            "total": 100,
            "data": "03/11/2026",
            "itens_json": "[]",
            "dados_adicionais": "{}",
            "status": "APROVADO",
        }
        with patch.object(os_repository, "get_db_connection", self.conexao_teste):
            os_repository.salvar_orcamento_aguardo_oficial(
                21,
                dados_os,
                sinal=100,
                saldo=0,
                pagamentos=pagamentos,
                valor_recebido=100,
            )

    def obter_lancamentos(self):
        return self.conn.execute(
            "SELECT descricao, valor, metodo_pagamento FROM fluxo_caixa ORDER BY id"
        ).fetchall()

    def executar_dialogo_pagamento(self, comportamento):
        FakePaymentWindow.behavior = comportamento
        with patch.multiple(
            tela_os.ctk,
            CTkToplevel=FakePaymentWindow,
            CTkFrame=FakeWidget,
            CTkLabel=FakeWidget,
            CTkButton=FakeButton,
            CTkEntry=FakeEntry,
        ):
            return tela_os.FrmOS._selecionar_pagamento_simples(
                SimpleNamespace(), 100
            )

    def criar_tela_baixa_fake(self, pagamentos):
        janela_consulta = SimpleNamespace(buscar_os=Mock())
        master = SimpleNamespace(
            _janela_gestao_os=janela_consulta,
            _janela_viva=Mock(return_value=True),
            _ultima_os_contexto=(21,),
            _atualizar_dashboard_modular=Mock(),
        )
        tela = SimpleNamespace(
            master=master,
            _selecionar_os=Mock(
                return_value=(
                    21, "Cliente Exemplo", "Carretilha Teste", "Revisao completa",
                    100, 100, 100, "FINALIZADO", "03/11/2026",
                )
            ),
            _perguntar_pagamentos=Mock(return_value=pagamentos),
            carregar_os_finalizadas=Mock(),
        )
        tela._atualizar_apos_entrega = MethodType(
            self.menu.FrmBaixaRecibo._atualizar_apos_entrega,
            tela,
        )
        return tela

    def test_dialogo_os_seleciona_pix_integral(self):
        escolha = self.executar_dialogo_pagamento("pix")
        self.assertEqual(escolha["pagamentos"], [("PIX", 100)])

    def test_dialogo_os_seleciona_dinheiro_integral(self):
        escolha = self.executar_dialogo_pagamento("cash")
        self.assertEqual(escolha["pagamentos"], [("DINHEIRO", 100)])

    def test_dialogo_os_seleciona_pix_e_dinheiro(self):
        escolha = self.executar_dialogo_pagamento("mixed")
        self.assertEqual(escolha["pagamentos"], [("PIX", 50), ("DINHEIRO", 50)])

    def test_cancelar_dialogo_pagamento_nao_confirma(self):
        escolha = self.executar_dialogo_pagamento("cancel")
        self.assertIsNone(escolha)

    def test_os_integralmente_paga_em_pix(self):
        self.registrar_aprovacao([("PIX", 100)])

        linhas = self.obter_lancamentos()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0][1:], (100, "PIX"))
        self.assertIn("O.S. 21", linhas[0][0])

    def test_os_integralmente_paga_em_dinheiro(self):
        self.registrar_aprovacao([("DINHEIRO", 100)])

        linhas = self.obter_lancamentos()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0][1:], (100, "DINHEIRO"))
        self.assertIn("O.S. 21", linhas[0][0])

    def test_os_paga_com_pix_e_dinheiro(self):
        self.registrar_aprovacao([("PIX", 50), ("DINHEIRO", 50)])

        linhas = self.obter_lancamentos()
        self.assertEqual([(linha[1], linha[2]) for linha in linhas], [(50, "PIX"), (50, "DINHEIRO")])
        self.assertTrue(all("O.S. 21" in linha[0] for linha in linhas))

    def test_total_recebido_corresponde_as_parcelas(self):
        self.registrar_aprovacao([("PIX", 50), ("DINHEIRO", 50)])

        self.assertEqual(
            self.conn.execute("SELECT SUM(valor) FROM fluxo_caixa").fetchone()[0],
            100,
        )

    def test_reprocessar_baixa_nao_duplica_parcelas(self):
        pagamentos = [("PIX", 50), ("DINHEIRO", 50)]
        self.registrar_aprovacao(pagamentos)
        self.registrar_aprovacao(pagamentos)

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT SUM(valor) FROM fluxo_caixa").fetchone()[0], 100)
        os_salva = self.conn.execute(
            "SELECT status, sinal, saldo FROM orcamentos_aguardo WHERE id = 21"
        ).fetchone()
        self.assertEqual(os_salva, ("APROVADO", 100, 0))

    def test_reprocessar_lancamento_legado_com_categoria_acentuada(self):
        self.conn.execute(
            """
            INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES ('03/11/2026', 'O.S. 21 - Cliente Exemplo (100% TOTAL)',
                    'ENTRADA', 100, 'ORDEM DE SERVIÇO', 'PIX')
            """
        )
        self.conn.commit()

        self.registrar_aprovacao([("PIX", 100)])

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0], 1)
        with patch.object(util_recibo, "get_db_connection", self.conexao_teste):
            self.assertEqual(util_recibo.obter_valor_pendente_os(21, 100), 0)

    def test_recebimento_misto_no_saldo_final(self):
        self.conn.execute(
            "UPDATE orcamentos_aguardo SET valor_total = 120, saldo = 60 WHERE id = 21"
        )
        self.conn.execute(
            """
            INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES ('03/11/2026', 'O.S. 21 - Cliente Exemplo [APROVACAO] [PIX]',
                    'ENTRADA', 60, 'ORDEM DE SERVICO', 'PIX')
            """
        )
        self.conn.commit()

        with patch.object(util_recibo, "get_db_connection", self.conexao_teste):
            nova_entrega = util_recibo.concluir_entrega_os(
                (21,),
                pagamentos_entrega=[("PIX", 30), ("DINHEIRO", 30)],
            )

        self.assertTrue(nova_entrega)
        lancamentos = self.conn.execute(
            "SELECT valor, metodo_pagamento FROM fluxo_caixa ORDER BY id"
        ).fetchall()
        self.assertEqual(lancamentos, [(60, "PIX"), (30, "PIX"), (30, "DINHEIRO")])
        self.assertEqual(sum(row[0] for row in lancamentos), 120)
        self.assertEqual(
            self.conn.execute(
                "SELECT status, status_entrega FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone(),
            ("ENTREGUE", "ENTREGUE"),
        )

    def test_entrega_idempotente_nao_duplica_recebimentos(self):
        with patch.object(util_recibo, "get_db_connection", self.conexao_teste):
            self.assertTrue(util_recibo.concluir_entrega_os((21,), [("PIX", 50), ("DINHEIRO", 50)]))
            self.assertFalse(util_recibo.concluir_entrega_os((21,), [("PIX", 100)]))

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT SUM(valor) FROM fluxo_caixa").fetchone()[0], 100)

    def test_entrega_concluida_mesmo_se_salvamento_do_pdf_for_cancelado(self):
        tela = self.criar_tela_baixa_fake([("PIX", 50), ("DINHEIRO", 50)])
        with patch.object(self.menu.messagebox, "askyesno", return_value=True), patch.object(
            self.menu.messagebox, "showinfo"
        ) as mostrar_sucesso, patch.object(
            self.menu.messagebox, "showerror"
        ) as mostrar_erro, patch.object(
            self.menu.messagebox, "showwarning"
        ), patch.object(
            self.menu, "obter_valor_pendente_os", return_value=100
        ), patch.object(
            util_recibo.filedialog, "asksaveasfilename", return_value=""
        ), patch.object(
            util_recibo, "get_db_connection", self.conexao_teste
        ):
            self.menu.FrmBaixaRecibo.gerar_recibo_selecionado(tela)

        self.assertFalse(mostrar_erro.called)
        self.assertTrue(mostrar_sucesso.called)
        self.assertIn("baixa financeira permanece concluida", mostrar_sucesso.call_args.args[1])
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "ENTREGUE",
        )
        self.assertEqual(self.conn.execute("SELECT SUM(valor) FROM fluxo_caixa").fetchone()[0], 100)
        tela.carregar_os_finalizadas.assert_called_once_with()
        tela.master._janela_gestao_os.buscar_os.assert_called_once_with()
        tela.master._atualizar_dashboard_modular.assert_called_once_with()
        self.assertIsNone(tela.master._ultima_os_contexto)

    def test_entrega_nao_reverte_se_geracao_do_pdf_falhar(self):
        tela = self.criar_tela_baixa_fake([("PIX", 100)])
        with patch.object(self.menu.messagebox, "askyesno", return_value=True), patch.object(
            self.menu.messagebox, "showwarning"
        ) as mostrar_aviso, patch.object(
            self.menu.messagebox, "showerror"
        ) as mostrar_erro, patch.object(
            self.menu, "obter_valor_pendente_os", return_value=100
        ), patch.object(
            util_recibo.filedialog,
            "asksaveasfilename",
            return_value=os.path.join(self.tempdir.name, "recibo-falha.pdf"),
        ), patch.object(
            util_recibo,
            "gerar_recibo_entrega",
            side_effect=OSError("falha de gravação simulada"),
        ), patch.object(
            util_recibo, "get_db_connection", self.conexao_teste
        ):
            self.menu.FrmBaixaRecibo.gerar_recibo_selecionado(tela)

        self.assertFalse(mostrar_erro.called)
        self.assertIn("recebimento e a entrega", mostrar_aviso.call_args.args[1])
        self.assertIn("falha de gravação simulada", mostrar_aviso.call_args.args[1])
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "ENTREGUE",
        )
        self.assertEqual(self.conn.execute("SELECT SUM(valor) FROM fluxo_caixa").fetchone()[0], 100)

    def test_entrega_remove_os_de_finalizados_e_preserva_historico(self):
        with patch.object(util_recibo, "get_db_connection", self.conexao_teste):
            util_recibo.concluir_entrega_os((21,), [("PIX", 100)])

        finalizados = self.conn.execute(
            """
            SELECT id FROM orcamentos_aguardo
            WHERE UPPER(COALESCE(status, '')) = 'FINALIZADO'
              AND UPPER(COALESCE(status_entrega, '')) <> 'ENTREGUE'
            """
        ).fetchall()
        self.assertEqual(finalizados, [])
        with patch.object(gestao_os_repository, "get_db_connection", self.conexao_teste):
            historico = listar_orcamentos_gestao()
        self.assertEqual([(row[0], row[8]) for row in historico], [(21, "ENTREGUE")])

    def test_saldo_geral_inclui_historico_enquanto_lista_mostra_periodo_filtrado(self):
        self.conn.executemany(
            """
            INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES (?, ?, 'ENTRADA', ?, 'TESTE', 'DINHEIRO')
            """,
            [
                ("30/10/2026", "Entrada antiga", 10),
                ("30/10/2026", "O.S. 501 antiga", 50),
                ("30/10/2026", "O.S. 502 antiga", 50),
                ("03/11/2026", "O.S. 21 parte 1", 60),
                ("03/11/2026", "O.S. 21 parte 2", 60),
            ],
        )
        self.conn.commit()

        with patch.object(financeiro_repository, "get_db_connection", self.conexao_teste):
            registros, saldo, _ = financeiro_repository.listar_lancamentos_financeiro(
                "2026-11-01", "2026-11-30"
            )
        self.assertEqual(len(registros), 2)
        self.assertEqual(saldo, 230)

        with patch.object(financeiro_repository, "get_db_connection", self.conexao_teste):
            financeiro_repository.excluir_lancamento_financeiro(registros[0][0], "operador")
            financeiro_repository.excluir_lancamento_financeiro(registros[1][0], "operador")
            registros, saldo, _ = financeiro_repository.listar_lancamentos_financeiro(
                "2026-11-01", "2026-11-30"
            )

        self.assertEqual(registros, [])
        self.assertEqual(saldo, 110)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM historico_exclusoes_fluxo_caixa"
            ).fetchone()[0],
            2,
        )

    def test_arquivar_os_preserva_historico_financeiro_e_registro_legado(self):
        self.conn.executescript(
            """
            CREATE TABLE ordens_servico (id_os INTEGER PRIMARY KEY, detalhe TEXT);
            INSERT INTO ordens_servico (id_os, detalhe) VALUES (21, 'documento legado');
            INSERT INTO fluxo_caixa (data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES
                ('03/11/2026', 'O.S. 21 - Cliente Exemplo [APROVACAO] [PIX]',
                 'ENTRADA', 60, 'ORDEM DE SERVICO', 'PIX'),
                ('03/11/2026', 'Receita avulsa não vinculada',
                 'ENTRADA', 10, 'RECEITA AVULSA', 'DINHEIRO');
            """
        )
        self.conn.commit()

        with patch.object(gestao_os_repository, "get_db_connection", self.conexao_teste):
            vinculados = arquivar_orcamento_gestao(21, usuario="operador")

        self.assertEqual(vinculados, 1)
        self.assertEqual(
            self.conn.execute(
                "SELECT status, status_entrega FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone(),
            ("EXCLUIDO", ""),
        )
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM ordens_servico WHERE id_os = 21").fetchone()[0], 1)
        audit = self.conn.execute(
            "SELECT os_id, usuario, lancamentos_financeiros, snapshot_json FROM historico_exclusoes_os"
        ).fetchone()
        self.assertEqual(audit[:3], (21, "operador", 1))
        self.assertIn("documento legado", audit[3])
        self.assertIn("O.S. 21 - Cliente Exemplo", audit[3])
        with patch.object(gestao_os_repository, "get_db_connection", self.conexao_teste):
            self.assertEqual(listar_orcamentos_gestao(), [])

        with patch.object(os_repository, "get_db_connection", self.conexao_teste):
            with self.assertRaisesRegex(ValueError, "está arquivada"):
                os_repository.salvar_orcamento_aguardo_oficial(
                    21,
                    {"cliente": "Cliente Exemplo", "total": 100, "status": "APROVADO"},
                )

    def test_botao_excluir_os_confirma_arquiva_e_atualiza_telas(self):
        tela = SimpleNamespace(
            tab=SimpleNamespace(
                selection=Mock(return_value=("linha",)),
                item=Mock(return_value=(21, "Cliente Exemplo", "", "", "", "", "", "", "", "", "")),
            ),
            master=SimpleNamespace(usuario="operador"),
            buscar_os=Mock(),
            _notificar_dashboard=Mock(),
        )
        with patch.object(gestao_os.messagebox, "askyesno", return_value=True), patch.object(
            gestao_os.messagebox, "showinfo"
        ) as mostrar_sucesso, patch.object(
            gestao_os.messagebox, "showerror"
        ) as mostrar_erro, patch.object(
            gestao_os_repository, "get_db_connection", self.conexao_teste
        ):
            gestao_os.FrmGestaoOrcamentos.excluir_os_selecionada(tela)

        self.assertFalse(mostrar_erro.called)
        mostrar_sucesso.assert_called_once()
        tela.buscar_os.assert_called_once_with()
        tela._notificar_dashboard.assert_called_once_with()
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "EXCLUIDO",
        )

    def test_cancelar_exclusao_de_os_nao_arquiva(self):
        tela = SimpleNamespace(
            tab=SimpleNamespace(
                selection=Mock(return_value=("linha",)),
                item=Mock(return_value=(21, "Cliente Exemplo")),
            ),
            master=SimpleNamespace(usuario="operador"),
        )
        with patch.object(gestao_os.messagebox, "askyesno", return_value=False), patch.object(
            gestao_os, "arquivar_orcamento_gestao"
        ) as arquivar:
            gestao_os.FrmGestaoOrcamentos.excluir_os_selecionada(tela)

        arquivar.assert_not_called()
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "FINALIZADO",
        )

    def test_pagamentos_incompletos_nao_salvam_os_nem_parcelas(self):
        with self.assertRaises(ValueError):
            self.registrar_aprovacao([("PIX", 50), ("DINHEIRO", 40)])

        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0], 0)
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "FINALIZADO",
        )

    def test_exclusao_atualiza_totais_e_registra_historico(self):
        self.conn.executemany(
            """
            INSERT INTO fluxo_caixa (id, data, descricao, tipo, valor, categoria, metodo_pagamento)
            VALUES (?, '03/11/2026', ?, ?, ?, 'TESTE', 'PIX')
            """,
            [(1, "Entrada", "ENTRADA", 100), (2, "Saida", "SAIDA", 40)],
        )
        self.conn.commit()
        fake_ui = SimpleNamespace(
            _selecionado=Mock(return_value=(1, "03/11/2026", "Entrada", "ENTRADA", "R$ 100.00", "TESTE", "PIX")),
            master=SimpleNamespace(usuario="operador"),
            carregar_dados=Mock(),
        )
        with patch.object(tela_financeiro.messagebox, "askyesno", return_value=True), patch.object(
            tela_financeiro.messagebox, "showinfo"
        ), patch.object(tela_financeiro.messagebox, "showerror") as mostrar_erro, patch.object(
            tela_financeiro.simpledialog, "askstring", side_effect=AssertionError("Não deve pedir senha")
        ), patch.object(financeiro_repository, "get_db_connection", self.conexao_teste):
            tela_financeiro.FrmFinanceiro.excluir_lancamento(fake_ui)

        self.assertFalse(mostrar_erro.called)
        fake_ui.carregar_dados.assert_called_once_with()
        with patch.object(financeiro_repository, "get_db_connection", self.conexao_teste):
            registros, saldo, _ = financeiro_repository.listar_lancamentos_financeiro(
                "2026-11-01", "2026-11-30"
            )
        self.assertEqual([registro[0] for registro in registros], [2])
        self.assertEqual(saldo, -40)
        historico = self.conn.execute(
            "SELECT lancamento_id, usuario, descricao, valor FROM historico_exclusoes_fluxo_caixa"
        ).fetchone()
        self.assertEqual(historico, (1, "operador", "Entrada", 100))

    def test_cancelar_confirmacao_mantem_lancamento(self):
        self.conn.execute(
            "INSERT INTO fluxo_caixa (id, data, descricao, tipo, valor, categoria, metodo_pagamento) "
            "VALUES (1, '03/11/2026', 'Entrada', 'ENTRADA', 100, 'TESTE', 'PIX')"
        )
        fake_ui = SimpleNamespace(
            _selecionado=Mock(return_value=(1, "03/11/2026", "Entrada", "ENTRADA", "100", "TESTE", "PIX")),
            master=SimpleNamespace(usuario="operador"),
        )
        with patch.object(tela_financeiro.messagebox, "askyesno", return_value=False), patch.object(
            tela_financeiro, "excluir_lancamento_financeiro"
        ) as excluir:
            tela_financeiro.FrmFinanceiro.excluir_lancamento(fake_ui)

        excluir.assert_not_called()
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0], 1)

    def test_salvar_recibo_no_diretorio_escolhido(self):
        destino = os.path.join(self.tempdir.name, "recibo-escolhido.pdf")
        with patch.object(util_recibo, "get_db_connection", self.conexao_teste):
            util_recibo.concluir_entrega_os((21,), [("PIX", 100)])
        with patch.object(
            util_recibo.filedialog, "asksaveasfilename", return_value=destino
        ) as dialogo, patch.object(
            util_recibo, "get_db_connection", self.conexao_teste
        ), patch.object(
            util_recibo, "enviar_arquivo_para_drive_usuario"
        ), patch.object(
            util_recibo.os, "startfile", create=True
        ):
            salvo = util_recibo.salvar_recibo_com_dialogo(
                "janela_teste",
                (
                    21,
                    "Cliente Exemplo",
                    "Carretilha Teste",
                    "Revisao completa",
                    100,
                    100,
                    100,
                    "FINALIZADO",
                    "03/11/2026",
                ),
            )

        self.assertEqual(dialogo.call_args.kwargs["defaultextension"], ".pdf")
        self.assertEqual(dialogo.call_args.kwargs["filetypes"], [("Arquivo PDF", "*.pdf")])
        self.assertEqual(salvo, destino)
        self.assertTrue(os.path.isfile(destino))
        self.assertGreater(os.path.getsize(destino), 0)
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "ENTREGUE",
        )
        self.assertEqual(self.conn.execute("SELECT SUM(valor) FROM fluxo_caixa").fetchone()[0], 100)

    def test_cancelar_dialogo_de_salvamento_nao_da_baixa(self):
        with patch.object(
            util_recibo.filedialog, "asksaveasfilename", return_value=""
        ), patch.object(util_recibo, "gerar_recibo_entrega") as gerar_recibo:
            salvo = util_recibo.salvar_recibo_com_dialogo(
                "janela_teste",
                (
                    21,
                    "Cliente Exemplo",
                    "Carretilha Teste",
                    "Revisao completa",
                    100,
                    100,
                    100,
                    "FINALIZADO",
                    "03/11/2026",
                ),
            )

        self.assertIsNone(salvo)
        gerar_recibo.assert_not_called()
        self.assertEqual(
            self.conn.execute(
                "SELECT status FROM orcamentos_aguardo WHERE id = 21"
            ).fetchone()[0],
            "FINALIZADO",
        )

    def test_recibo_mantem_identificacao_e_servicos(self):
        destino = os.path.join(self.tempdir.name, "recibo-informacoes.pdf")
        with patch.object(util_recibo, "get_db_connection", self.conexao_teste):
            util_recibo.concluir_entrega_os(
                (21,),
                pagamentos_entrega=[("PIX", 50), ("DINHEIRO", 50)],
            )
        with patch.object(util_recibo, "get_db_connection", self.conexao_teste), patch.object(
            util_recibo, "enviar_arquivo_para_drive_usuario"
        ), patch.object(util_recibo.os, "startfile", create=True):
            util_recibo.gerar_recibo_entrega(
                (21, "Cliente Exemplo", "Carretilha Teste", "Revisao completa", 100, 100, 100, "FINALIZADO", ""),
                destino,
            )

        conteudo = Path(destino).read_bytes()
        self.assertTrue(conteudo.startswith(b"%PDF-"))
        stream = re.search(rb"stream\r?\n(.*?)\r?\nendstream", conteudo, re.DOTALL)
        self.assertIsNotNone(stream)
        conteudo_pdf = zlib.decompress(stream.group(1))
        for texto in (
            b"Cliente Exemplo",
            b"Carretilha Teste",
            b"Revisao completa",
            b"2x Rolamento",
            b"Mao de obra",
            b"Oficina Teste",
            b"11999990000",
            b"Valor Total: R$ 100.00",
            b"VIA OFICINA",
            b"VIA CLIENTE",
        ):
            self.assertIn(texto, conteudo_pdf)

    def test_os_paga_integralmente_atualiza_saldo_para_zero(self):
        payload = montar_payload_os(
            os_id=21,
            cliente="Cliente Exemplo",
            telefone="11999990000",
            endereco="Rua do Porto",
            equipamentos=[
                {
                    "equipamento": "Carretilha Teste",
                    "defeito": "Revisao completa",
                    "itens": [["Peca", "Descricao", "tipo", 100, "ATIVO"]],
                    "desconto": 0,
                    "frete": 0,
                    "opcional": 0,
                }
            ],
            status="APROVADO",
            forma_pagamento="100%_total",
        )

        self.assertEqual(payload["sinal"], 100)
        self.assertEqual(payload["saldo"], 0)


if __name__ == "__main__":
    unittest.main()
