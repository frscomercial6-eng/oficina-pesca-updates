# -*- coding: utf-8 -*-
"""Valida os 4 fixes críticos de O.S./Dashboard/Licença.

Uso: python tests/validar_fixes_os.py
"""
import io
import os
import py_compile
import sqlite3
import sys
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

URL_PLANOS = "https://www.frssolutions.com.br/planos"

SCHEMA = """
CREATE TABLE orcamentos_aguardo (
    id INTEGER PRIMARY KEY,
    cliente TEXT, telefone_cliente_whatsapp TEXT, equipamento TEXT, defeito TEXT,
    resumo_equipamento_defeito TEXT, valor_total REAL, sinal REAL, saldo REAL,
    status TEXT, data TEXT, itens_detalhes TEXT, dados_adicionais TEXT,
    status_entrega TEXT, data_finalizacao TEXT, data_entrega TEXT
);
CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT, telefone_cliente_whatsapp TEXT);
CREATE TABLE configuracoes (chave TEXT PRIMARY KEY, valor TEXT);
"""


def _conexao_memoria():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    conn.execute(
        "INSERT INTO orcamentos_aguardo VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            501, "CLIENTE TESTE", "5511999998888", "NOTEBOOK", "N LIGA", "NOTEBOOK - N LIGA",
            250.0, 50.0, 200.0, "AGUARDANDO", "01/08/2026", "[{\"item\":\"A\"}]",
            '{"cliente_telefone":"5511999998888"}', "PENDENTE", "Vazio", "Vazio",
        ),
    )
    conn.execute("INSERT INTO clientes VALUES (1, 'CLIENTE TESTE', '5511999998888')")
    conn.execute("INSERT INTO configuracoes VALUES ('ultimo_orcamento', '500')")
    return conn


class TestFix1ListagemOds(unittest.TestCase):
    def test_repository_devolve_13_colunas(self):
        from core import gestao_os_repository

        conn = _conexao_memoria()
        with mock.patch.object(gestao_os_repository, "get_db_connection", return_value=conn):
            linhas = gestao_os_repository.listar_orcamentos_para_gestao()
        self.assertEqual(len(linhas), 1)
        linha = linhas[0]
        self.assertEqual(len(linha), 13)
        self.assertEqual(linha[0], 501)                 # id
        self.assertEqual(linha[1], 1)                   # id do cliente
        self.assertEqual(linha[2], "CLIENTE TESTE")     # nome do cliente
        self.assertEqual(linha[10], '[{"item":"A"}]')   # itens_detalhes
        self.assertEqual(linha[11], "5511999998888")    # telefone_whatsapp
        self.assertIn("cliente_telefone", linha[12])    # dados_adicionais
        conn.close()

    def test_ui_unpack_compativel(self):
        with open(os.path.join(RAIZ, "gestao_os.py"), "r", encoding="utf-8") as arquivo:
            codigo = arquivo.read()
        self.assertIn(
            "id_orc, id_cli, nome_cli, equipamento, defeito, total, sinal, saldo, status, data, itens_json, telefone_cli, dados_adicionais = row",
            codigo,
        )


class TestFix2PainelRetirada(unittest.TestCase):
    def _checar_menu(self, caminho):
        with open(os.path.abspath(caminho), "r", encoding="utf-8") as arquivo:
            codigo = arquivo.read()
        self.assertIn('("AGUARDANDO RETIRADA", "#e74c3c", aguardando_retirada)', codigo)
        self.assertIn("corpo.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)", codigo)
        self.assertIn("aguardando_retirada", codigo.split("def _criar_painel_pendencias_fixo")[1].split("\n")[0])
        self.assertIn("return orcamentos, bancada, status_finalizados, aguardando_orcamento, aguardando_retirada\n", codigo)
        self.assertIn("([], [], [], [], [])", codigo)

    def test_painel_com_card_aguardando_retirada(self):
        self._checar_menu(os.path.join(RAIZ, "menu.py"))
        self._checar_menu(os.path.join(os.path.dirname(RAIZ), "build_protegido", "menu.py"))


class TestFix3SalvarEntrada(unittest.TestCase):
    def test_insert_reserva_numero_e_leitura(self):
        from core import gestao_os_repository, os_repository

        conn = _conexao_memoria()
        with mock.patch.object(os_repository, "get_db_connection", return_value=conn), \
             mock.patch.object(gestao_os_repository, "get_db_connection", return_value=conn):
            proximo = os_repository.obter_proximo_numero_orcamento_oficial()
            self.assertGreaterEqual(proximo, 501)
            os_repository.salvar_orcamento_aguardo_oficial(
                proximo,
                {
                    "cliente": "OUTRO CLIENTE",
                    "telefone_cliente_whatsapp": "5511988887777",
                    "equipamento": "TV",
                    "defeito": "TELA",
                    "resumo_equipamento_defeito": "TV - TELA",
                    "total": 900.0,
                    "status": "AGUARDANDO",
                    "data": "02/08/2026",
                    "itens_json": "[]",
                    "dados_adicionais": "{}",
                },
                sinal=0.0,
                saldo=900.0,
            )
            registro = gestao_os_repository.buscar_dados_orcamento(proximo)
            self.assertIsNotNone(registro)
            self.assertEqual(len(registro), 11)
            self.assertEqual(registro[1], "OUTRO CLIENTE")
            self.assertEqual(registro[9], "[]")
            self.assertEqual(registro[10], "{}")
            maior = os_repository.obter_proximo_numero_orcamento_oficial()
            self.assertEqual(maior, proximo + 1)
        conn.close()

    def test_listagem_nao_aborta_em_linha_malformada(self):
        with open(os.path.join(RAIZ, "gestao_os.py"), "r", encoding="utf-8") as arquivo:
            codigo = arquivo.read()
        self.assertIn("except ValueError:", codigo)
        self.assertIn("logger = get_logger()", codigo)


class TestFix4LicencaLinkExterno(unittest.TestCase):
    def _login_codigo(self, build=False):
        base = os.path.join(os.path.dirname(RAIZ), "build_protegido") if build else RAIZ
        with open(os.path.join(base, "login.py"), "r", encoding="utf-8") as arquivo:
            return arquivo.read()

    def test_botao_abre_link_externo(self):
        for build in (False, True):
            codigo = self._login_codigo(build)
            self.assertIn("webbrowser.open(\"%s\")" % URL_PLANOS, codigo)
            self.assertIn("command=abrir_janela_planos", codigo)
            # Nenhuma chamada à tela interna de planos permanece no fluxo do login.
            self.assertNotIn("janela_vendas(", codigo)


class TestCompilacao(unittest.TestCase):
    def test_py_compile(self):
        alvos = [
            "menu.py", "gestao_os.py", "login.py",
            "core/gestao_os_repository.py", "core/gestao_os_service.py",
            "core/os_repository.py", "core/os_service.py",
            os.path.join(os.pardir, "build_protegido", "login.py"),
            os.path.join(os.pardir, "build_protegido", "menu.py"),
        ]
        for relativo in alvos:
            caminho = os.path.abspath(os.path.join(RAIZ, relativo))
            py_compile.compile(caminho, doraise=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    stream = io.StringIO()
    resultado = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    print(stream.getvalue())
    sys.exit(0 if resultado.wasSuccessful() else 1)