import concurrent.futures
import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import customtkinter as ctk
import pytest
from pypdf import PdfReader

import pdv
import config


@pytest.fixture
def banco(tmp_path, monkeypatch):
    caminho = tmp_path / "pdv_teste.db"
    with sqlite3.connect(caminho) as con:
        con.executescript("""
            CREATE TABLE produtos (id INTEGER PRIMARY KEY, nome TEXT, preco_venda REAL, estoque INTEGER, codigo_barras TEXT);
            CREATE TABLE pdv_vendas (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, total REAL, forma_pagamento TEXT, status TEXT);
            CREATE TABLE pdv_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, venda_id INTEGER, produto_id INTEGER,
                                    nome_produto TEXT, quantidade INTEGER, preco_unitario REAL, total_item REAL);
            CREATE TABLE fluxo_caixa (id INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT, descricao TEXT, tipo TEXT,
                                      valor REAL, categoria TEXT, metodo_pagamento TEXT);
            CREATE TABLE orcamentos_aguardo (id INTEGER PRIMARY KEY);
            CREATE TABLE configuracoes (ultimo_orcamento INTEGER);
            INSERT INTO configuracoes VALUES (987);
            INSERT INTO produtos VALUES (1, 'Produto A', 50, 5, '123456789');
        """)

    @contextmanager
    def conexao():
        con = sqlite3.connect(caminho, timeout=10)
        try:
            yield con
        finally:
            con.close()

    monkeypatch.setattr(pdv, "get_db_connection", conexao)
    monkeypatch.setattr(pdv, "CAMINHO_BANCO", str(caminho))
    monkeypatch.setattr(pdv, "obter_dados_oficina", lambda: {"nome_oficina": "Oficina Teste"})
    return caminho


class Campo:
    def __init__(self, value=""):
        self.value = str(value)

    def get(self):
        return self.value

    def delete(self, *args):
        self.value = ""

    def insert(self, index, value):
        self.value = str(value)


class PDVFake:
    _total_itens = pdv.FrmPDV._total_itens
    _total_pago = pdv.FrmPDV._total_pago
    _total_desconto = pdv.FrmPDV._total_desconto
    _total_liquido = pdv.FrmPDV._total_liquido
    _validar_desconto = pdv.FrmPDV._validar_desconto
    _pagamentos_descricao = pdv.FrmPDV._pagamentos_descricao
    _snapshot_venda = pdv.FrmPDV._snapshot_venda
    _base_venda_para_saida = pdv.FrmPDV._base_venda_para_saida
    _gerar_pdf_documento = pdv.FrmPDV._gerar_pdf_documento
    _salvar_pdf_documento = pdv.FrmPDV._salvar_pdf_documento
    _gerar_pdf_venda = pdv.FrmPDV._gerar_pdf_venda
    _registrar_orcamento_comercial = pdv.FrmPDV._registrar_orcamento_comercial
    _gerar_orcamento_comercial = pdv.FrmPDV._gerar_orcamento_comercial
    _recuperar_documento_pdv = pdv.FrmPDV._recuperar_documento_pdv
    _resumo_fechamento_dia = pdv.FrmPDV._resumo_fechamento_dia
    _fechamento_de_caixa = pdv.FrmPDV._fechamento_de_caixa
    _finalizar_venda = pdv.FrmPDV._finalizar_venda

    def __init__(self, nome="Produto A", quantidade=2, preco=50, desconto="0"):
        self._carrinho = [{"produto_id": 1, "nome_produto": nome, "quantidade": quantidade,
                           "preco_unitario": preco, "total_item": quantidade * preco}]
        self._pagamentos = []
        self._metodo_pagamento = "DINHEIRO"
        self._orcamento_vinculado = None
        self._ultima_venda = None
        self.ent_desconto = Campo(desconto)
        self._auto_impressao = SimpleNamespace(get=lambda: False)
        self._finalizando_venda = False

    def _alternar_estado_finalizacao(self, valor):
        self._finalizando_venda = valor

    def _limpar_venda(self):
        self._carrinho = []
        self._pagamentos = []
        self._orcamento_vinculado = None

    def _focar_qtd(self):
        pass

    def _abrir_pdf_salvo(self, caminho):
        pass


@pytest.fixture
def mensagens(monkeypatch):
    avisos = []
    for nome in ("showwarning", "showerror", "showinfo"):
        monkeypatch.setattr(pdv.messagebox, nome, lambda *args, _nome=nome, **kwargs: avisos.append((_nome, args)))
    return avisos


def texto_pdf(caminho):
    return "\n".join(p.extract_text() for p in PdfReader(str(caminho)).pages)


def dados_orcamento():
    return {"date": "12/11/2026 10:00", "cliente": "Cliente Teste", "items": [
        {"produto_id": 1, "nome_produto": "Produto A", "quantidade": 2, "preco_unitario": 50, "total_item": 100}
    ], "total_bruto": 100, "desconto": 0, "total": 100}


def test_sequencia_orcamento_concorrente_e_sem_efeitos_colaterais(banco):
    objeto = PDVFake()
    with sqlite3.connect(banco) as con:
        antes = [con.execute(f"SELECT * FROM {t}").fetchall() for t in
                 ("produtos", "pdv_vendas", "pdv_itens", "fluxo_caixa", "orcamentos_aguardo", "configuracoes")]
    assert objeto._registrar_orcamento_comercial(dados_orcamento())["numero"] == 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        resultados = list(pool.map(lambda _: PDVFake()._registrar_orcamento_comercial(dados_orcamento()), range(10)))
    assert sorted(r["numero"] for r in resultados) == list(range(1, 11))
    with sqlite3.connect(banco) as con:
        depois = [con.execute(f"SELECT * FROM {t}").fetchall() for t in
                  ("produtos", "pdv_vendas", "pdv_itens", "fluxo_caixa", "orcamentos_aguardo", "configuracoes")]
        registros = con.execute("SELECT numero, dados_json FROM pdv_orcamentos_comerciais ORDER BY numero").fetchall()
    assert antes == depois
    assert [r[0] for r in registros] == list(range(11))
    assert all(json.loads(dados)["cliente"] == "Cliente Teste" for _, dados in registros)
    assert PDVFake()._registrar_orcamento_comercial(dados_orcamento())["numero"] == 11


def test_sequencia_concorrente_com_conexao_real(banco, monkeypatch):
    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(pdv, "get_db_connection", config.get_db_connection)
    with config.get_db_connection():
        pass
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        resultados = list(pool.map(lambda _: PDVFake()._registrar_orcamento_comercial(dados_orcamento()), range(10)))
    assert sorted(r["numero"] for r in resultados) == list(range(10))


def test_orcamento_preservado_se_pdf_falhar(banco, monkeypatch, mensagens):
    objeto = PDVFake()
    monkeypatch.setattr(pdv.simpledialog, "askstring", lambda *a, **k: "Cliente Teste")
    monkeypatch.setattr(pdv.filedialog, "asksaveasfilename", lambda *a, **k: "nao_gravar.pdf")
    monkeypatch.setattr(objeto, "_salvar_pdf_documento", lambda *a, **k: (_ for _ in ()).throw(PermissionError("erro")))
    objeto._gerar_orcamento_comercial()
    assert any(tipo == "showerror" and "erro" in args[1] for tipo, args in mensagens)
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT numero FROM pdv_orcamentos_comerciais").fetchall() == [(0,)]
        assert con.execute("SELECT COUNT(*) FROM pdv_vendas").fetchone()[0] == 0
    assert objeto._registrar_orcamento_comercial(dados_orcamento())["numero"] == 1


def test_orcamento_gera_pdf_e_recupera_sem_repetir_numero(banco, tmp_path, monkeypatch, mensagens):
    objeto = PDVFake(desconto="10")
    arquivo = tmp_path / "orcamento.pdf"
    recuperado = tmp_path / "recuperado.pdf"
    monkeypatch.setattr(pdv.simpledialog, "askstring", lambda *a, **k: "Cliente Teste")
    monkeypatch.setattr(pdv.filedialog, "asksaveasfilename", lambda *a, **k: str(arquivo))
    monkeypatch.setattr(pdv.os, "startfile", lambda *a, **k: None, raising=False)
    objeto._gerar_orcamento_comercial()
    conteudo = texto_pdf(arquivo)
    assert "ORCAMENTO COMERCIAL" in conteudo and "Orcamento #0" in conteudo
    assert "Cliente Teste" in conteudo and "Produto A" in conteudo
    assert "90,00" in conteudo and "10,00" in conteudo
    monkeypatch.setattr(pdv.simpledialog, "askinteger", lambda *a, **k: 0)
    monkeypatch.setattr(pdv.filedialog, "asksaveasfilename", lambda *a, **k: str(recuperado))
    objeto._recuperar_documento_pdv("orcamento")
    assert "Orcamento #0" in texto_pdf(recuperado)
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT COUNT(*) FROM pdv_orcamentos_comerciais").fetchone()[0] == 1
        assert con.execute("SELECT estoque FROM produtos WHERE id=1").fetchone()[0] == 5
        assert con.execute("SELECT COUNT(*) FROM pdv_vendas").fetchone()[0] == 0


def test_pdf_usa_carrinho_atual_e_preserva_itens_em_varias_paginas(banco):
    objeto = PDVFake(nome="Produto Atual")
    objeto._ultima_venda = {**objeto._snapshot_venda(), "sale_id": 99,
                            "items": [{**objeto._carrinho[0], "nome_produto": "Produto Antigo"}]}
    objeto._carrinho.extend(
        {"produto_id": n + 2, "nome_produto": f"Produto {n} " + "X" * 130, "quantidade": 1,
         "preco_unitario": 1, "total_item": 1} for n in range(90)
    )
    venda = objeto._base_venda_para_saida()
    assert venda["sale_id"] is None
    arquivo = objeto._gerar_pdf_venda(venda)
    conteudo = texto_pdf(arquivo)
    assert len(PdfReader(arquivo).pages) > 1
    assert "Produto Atual" in conteudo and "Produto Antigo" not in conteudo
    assert "Venda em andamento" in conteudo and "Produto 89" in conteudo
    assert "X" * 130 in conteudo.replace("\n", "")


def test_finalizacao_mista_troco_caixa_e_recuperacao(banco, tmp_path, monkeypatch, mensagens):
    objeto = PDVFake()
    objeto._pagamentos = [{"metodo": "PIX", "valor": 60}, {"metodo": "DINHEIRO", "valor": 50}]
    objeto._finalizar_venda()
    assert objeto._ultima_venda["sale_id"] == 1 and objeto._ultima_venda["troco"] == 10
    assert not objeto._carrinho
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT estoque FROM produtos WHERE id=1").fetchone()[0] == 3
        assert con.execute("SELECT metodo_pagamento, valor FROM fluxo_caixa ORDER BY id").fetchall() == [
            ("PIX", 60), ("DINHEIRO", 40)]
        salvo = json.loads(con.execute("SELECT dados_json FROM pdv_documentos_venda WHERE venda_id=1").fetchone()[0])
        assert salvo["payments"] == [{"metodo": "PIX", "valor": 60}, {"metodo": "DINHEIRO", "valor": 50}]
    resumo = objeto._resumo_fechamento_dia(objeto._ultima_venda["date_only"])
    assert (resumo["total_vendas"], resumo["pix"], resumo["dinheiro"]) == (100, 60, 40)
    arquivo = tmp_path / "venda_recuperada.pdf"
    monkeypatch.setattr(pdv.simpledialog, "askinteger", lambda *a, **k: 1)
    monkeypatch.setattr(pdv.filedialog, "asksaveasfilename", lambda *a, **k: str(arquivo))
    monkeypatch.setattr(pdv.os, "startfile", lambda *a, **k: None, raising=False)
    PDVFake()._recuperar_documento_pdv("venda")
    assert "Venda #1" in texto_pdf(arquivo) and "Produto A" in texto_pdf(arquivo)


def test_estoque_alterado_aborta_venda_inteira(banco, mensagens):
    objeto = PDVFake(quantidade=7)
    objeto._finalizar_venda()
    assert objeto._carrinho and objeto._ultima_venda is None
    assert any(tipo == "showerror" and "Estoque insuficiente" in args[1] for tipo, args in mensagens)
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT estoque FROM produtos WHERE id=1").fetchone()[0] == 5
        assert con.execute("SELECT COUNT(*) FROM pdv_vendas").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM fluxo_caixa").fetchone()[0] == 0


def test_falha_no_caixa_reverte_estoque_e_venda(banco, mensagens):
    with sqlite3.connect(banco) as con:
        con.execute("CREATE TRIGGER caixa_indisponivel BEFORE INSERT ON fluxo_caixa "
                    "BEGIN SELECT RAISE(ABORT, 'caixa indisponivel'); END")
    objeto = PDVFake()
    objeto._finalizar_venda()
    assert objeto._carrinho and objeto._ultima_venda is None
    assert any(tipo == "showerror" and "caixa indisponivel" in args[1] for tipo, args in mensagens)
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT estoque FROM produtos WHERE id=1").fetchone()[0] == 5
        assert con.execute("SELECT COUNT(*) FROM pdv_vendas").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM pdv_itens").fetchone()[0] == 0


def test_fechamento_preserva_carrinho_e_nao_fecha_nova_venda(banco, mensagens, monkeypatch):
    with sqlite3.connect(banco) as con:
        con.execute("CREATE TABLE financeiro_geral (data_hora TEXT, data_referencia TEXT, descricao TEXT, tipo TEXT, "
                    "total_dinheiro REAL, total_pix REAL, total_cartao REAL, total_geral REAL, detalhe_json TEXT)")
    venda = PDVFake()
    venda._finalizar_venda()
    pendente = PDVFake(nome="Carrinho pendente")

    def confirmar(*args, **kwargs):
        with sqlite3.connect(banco) as con:
            con.execute("INSERT INTO pdv_vendas(data,total,forma_pagamento,status) VALUES (?,30,'PIX','aberto')",
                        (venda._ultima_venda["date_only"],))
        return True

    monkeypatch.setattr(pdv.messagebox, "askyesno", confirmar)
    pendente._fechamento_de_caixa()
    assert pendente._carrinho[0]["nome_produto"] == "Carrinho pendente"
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT status FROM pdv_vendas ORDER BY id").fetchall() == [("fechado",), ("aberto",)]
        assert con.execute("SELECT total_geral FROM financeiro_geral").fetchall() == [(100,)]


def test_excesso_de_pix_nao_gera_troco_ou_venda(banco, mensagens):
    objeto = PDVFake()
    objeto._pagamentos = [{"metodo": "PIX", "valor": 110}]
    objeto._finalizar_venda()
    assert any("troco" in args[1].lower() for _, args in mensagens)
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT COUNT(*) FROM pdv_vendas").fetchone()[0] == 0


@pytest.mark.parametrize("desconto", ["-1", "101", "NaN", "texto"])
def test_desconto_invalido_nao_finaliza_venda(banco, mensagens, desconto):
    objeto = PDVFake(desconto=desconto)
    objeto._finalizar_venda()
    assert objeto._carrinho and objeto._ultima_venda is None
    assert any(tipo == "showwarning" and "desconto" in args[1].lower() for tipo, args in mensagens)
    with sqlite3.connect(banco) as con:
        assert con.execute("SELECT COUNT(*) FROM pdv_vendas").fetchone()[0] == 0
        assert con.execute("SELECT estoque FROM produtos WHERE id=1").fetchone()[0] == 5


def test_busca_modal_debounce_selecao_e_fechamento_seguro(root_pdv, banco, monkeypatch):
    janela, root = root_pdv
    with sqlite3.connect(banco) as con:
        con.executemany("INSERT INTO produtos (id, nome, preco_venda, estoque, codigo_barras) VALUES (?, ?, ?, ?, ?)",
                        [(n, f"Produto teste {n:04}", 5, 10, str(100000000 + n)) for n in range(2, 1002)])
    erros = []
    root.report_callback_exception = lambda *args: erros.append(args)
    callbacks = {}
    bind_original = ctk.CTkEntry.bind

    def capturar_bind(widget, sequencia, callback, *args, **kwargs):
        callbacks[widget, sequencia] = callback
        return bind_original(widget, sequencia, callback, *args, **kwargs)

    monkeypatch.setattr(ctk.CTkEntry, "bind", capturar_bind)
    janela.ent_qtd.delete(0, "end")
    janela.ent_qtd.insert(0, "2")
    inicio = time.monotonic()
    janela._abrir_busca_estoque()
    assert time.monotonic() - inicio < 0.5
    modal = next(w for w in janela.winfo_children() if isinstance(w, ctk.CTkToplevel))
    campo = next(w for w in modal.winfo_children() if isinstance(w, ctk.CTkEntry))
    arvore = next(w for w in modal.winfo_children() if isinstance(w, pdv.ttk.Treeview))
    root.update()
    campo.delete(0, "end")
    campo.insert(0, "100000999")
    inicio = time.monotonic()
    callbacks[campo, "<KeyRelease>"](None)
    root.update()
    assert time.monotonic() - inicio < 0.5
    prazo = time.monotonic() + 4
    while time.monotonic() < prazo:
        root.update()
        if arvore.get_children() and arvore.item(arvore.get_children()[0], "values")[0] == "999":
            break
        time.sleep(0.01)
    assert len(arvore.get_children()) == 1
    assert arvore.item(arvore.get_children()[0], "values")[0] == "999"
    rodape = [w for w in modal.winfo_children() if isinstance(w, ctk.CTkFrame)][-1]
    botoes = [w for w in rodape.winfo_children() if isinstance(w, ctk.CTkButton)]
    botoes[-1].invoke()
    root.update()
    assert janela._carrinho[0]["produto_id"] == 999
    assert janela._carrinho[0]["quantidade"] == 2
    janela._abrir_busca_estoque()
    modal = next(w for w in janela.winfo_children() if isinstance(w, ctk.CTkToplevel))
    modal.destroy()
    for _ in range(15):
        root.update()
        time.sleep(0.01)
    assert not erros


def test_visualizacao_local_do_pdf_em_varias_paginas(root_pdv, tmp_path):
    janela, root = root_pdv
    arquivo = tmp_path / "multiplas_paginas.pdf"
    documento = pdv.canvas.Canvas(str(arquivo))
    for texto in ("Primeira página", "Segunda página"):
        documento.drawString(30, 700, texto)
        documento.showPage()
    documento.save()
    janela._visualizar_pdf_local(str(arquivo))
    visualizador = next(w for w in janela.winfo_children() if isinstance(w, ctk.CTkToplevel))
    barra = next(w for w in visualizador.winfo_children() if isinstance(w, ctk.CTkFrame))
    estado = next(w for w in barra.winfo_children() if isinstance(w, ctk.CTkLabel))
    botoes = [w for w in barra.winfo_children() if isinstance(w, ctk.CTkButton)]

    def aguardar(texto):
        prazo = time.monotonic() + 5
        while time.monotonic() < prazo and estado.cget("text") != texto:
            root.update()
            time.sleep(0.01)
        assert estado.cget("text") == texto

    aguardar("Página 1 de 2")
    botoes[1].invoke()
    aguardar("Página 2 de 2")
    visualizador.destroy()
    root.update()


def test_busca_direta_assincrona_descarta_resultado_antigo(root_pdv, monkeypatch):
    janela, root = root_pdv
    liberar = threading.Event()
    chamadas = []

    def buscar(termo):
        chamadas.append(termo)
        if termo == "antigo":
            liberar.wait(3)
            return (1, "Antigo", 50, 5)
        return (2, "Atual", 10, 5)

    monkeypatch.setattr(janela, "_buscar_produto_por_termo", buscar)
    janela.ent_busca.delete(0, "end")
    janela.ent_busca.insert(0, "antigo")
    inicio = time.monotonic()
    janela._enter_na_busca()
    janela._enter_na_busca()
    assert time.monotonic() - inicio < 0.1
    janela.ent_busca.delete(0, "end")
    janela.ent_busca.insert(0, "atual")
    janela._invalidar_busca_direta()
    janela._enter_na_busca()
    prazo = time.monotonic() + 3
    while time.monotonic() < prazo and not janela._carrinho:
        root.update()
        time.sleep(0.01)
    liberar.set()
    for _ in range(20):
        root.update()
        time.sleep(0.01)
    assert [i["nome_produto"] for i in janela._carrinho] == ["Atual"]
    assert chamadas.count("antigo") == 1


def test_busca_direta_reutiliza_consulta_em_andamento(root_pdv, monkeypatch):
    janela, root = root_pdv
    liberar = threading.Event()
    chamadas = []

    def buscar(termo):
        chamadas.append(termo)
        liberar.wait(3)
        return (1, termo, 5, 5)

    monkeypatch.setattr(janela, "_buscar_produto_por_termo", buscar)
    for termo in ("Produto A", "Produto B", "Produto A"):
        janela.ent_busca.delete(0, "end")
        janela.ent_busca.insert(0, termo)
        janela._invalidar_busca_direta()
        janela._enter_na_busca()
    liberar.set()
    prazo = time.monotonic() + 3
    while time.monotonic() < prazo and janela._buscas_diretas_ativas:
        root.update()
        time.sleep(0.01)
    assert chamadas.count("Produto A") == 1
    assert [item["nome_produto"] for item in janela._carrinho] == ["Produto A"]


@pytest.fixture
def root_pdv(banco):
    root = ctk.CTk()
    root.withdraw()
    with patch.object(pdv.FrmPDV, "_aplicar_maximizacao"):
        janela = pdv.FrmPDV(root)
        root.update()
        yield janela, root
        janela.destroy()
    root.destroy()
