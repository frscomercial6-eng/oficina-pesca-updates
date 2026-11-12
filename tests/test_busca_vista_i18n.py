import sys
import queue
import threading
import time
import tkinter as tk
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import customtkinter as ctk
import pytest

import busca_vista_defeitos as defeitos
import busca_vista_traducao as traducao
import busca_vista_visualizador as visualizador
from busca_vista_visualizador import VisualizadorPdfBuscaVista
from core.i18n import t
from tela_os import FrmOS


ITEM = {
    "titulo": "Shimano Curado 12CU200G6 problem",
    "sintomas": "Shimano Curado 12CU200G6 stopped working",
    "causa": "",
    "reparo": "12CU200G6 fixed",
    "escopo": "Variante",
    "classificacao": "Não confirmado",
    "url_defeito": "https://example.test/threads/123",
    "url_reparo": "https://example.test/threads/123",
    "idioma": "en",
    "titulo_publico": "Shimano Curado 12CU200G6 problem",
    "mensagens_publicas": (
        "My Shimano Curado 12CU200G6 stopped working.",
        "The cause was a worn washer. I replaced the washer and fixed it.",
    ),
}
IDENTIDADE = {"fabricante": "shimano", "familia": "curado", "modelo": "curado 12cu200g6"}


@pytest.fixture(scope="module")
def root():
    janela = ctk.CTk()
    janela.geometry("1000x700+20+20")
    janela.update()
    yield janela
    janela.destroy()


def test_idioma_da_fonte_e_fallback_sem_modelo(monkeypatch):
    parser = defeitos._Conteudo()
    parser.feed('<html lang="en-US"><title>test</title></html>')
    assert parser.idioma == "en"
    monkeypatch.setitem(sys.modules, "argostranslate", None)
    original, disponivel = traducao.traduzir_item(ITEM, "pt_BR", IDENTIDADE)
    assert not disponivel and original == ITEM
    assert traducao.traduzir_item(ITEM, "en_US", IDENTIDADE) == (ITEM, True)
    assert traducao.traduzir_item({**ITEM, "idioma": ""}, "pt_BR", IDENTIDADE)[1] is False


def test_traducao_local_preserva_identificadores_e_links(monkeypatch):
    class Idioma:
        def __init__(self, code):
            self.code = code

        def get_translation(self, destino):
            return SimpleNamespace(translate=lambda texto: texto.replace("problem", "problema")
                                   .replace("stopped working", "parou de funcionar").replace("fixed", "consertado"))

    api = SimpleNamespace(get_installed_languages=lambda: [Idioma("en"), Idioma("pt")])
    monkeypatch.setitem(sys.modules, "argostranslate", SimpleNamespace(translate=api))
    traduzido, disponivel = traducao.traduzir_item(ITEM, "pt_BR", IDENTIDADE)
    assert disponivel and "problema" in traduzido["titulo"]
    assert "12CU200G6" in traduzido["titulo"]
    assert traduzido["url_defeito"] == ITEM["url_defeito"]
    api.get_installed_languages = lambda: [
        SimpleNamespace(code="en", get_translation=lambda destino: SimpleNamespace(translate=lambda texto: "texto sem código")),
        Idioma("pt"),
    ]
    assert traducao.traduzir_item(ITEM, "pt_BR", IDENTIDADE) == (ITEM, False)


def test_status_seguem_locale():
    mensagem = "Bing: tempo excedido; demais fontes continuam."
    assert traducao.localizar_status(mensagem, "pt_BR") == mensagem
    assert traducao.localizar_status(mensagem, "en_US") == "Bing: timed out; other sources continue."
    assert "tiempo agotado" in traducao.localizar_status(mensagem, "es_UY")
    assert t("bv_nao_confirmado", locale="en_US") == "Unconfirmed"


def test_traducao_progressiva_nao_troca_resultados_e_links(root):
    texto = tk.Text(root)
    try:
        janela = SimpleNamespace(texto_defeitos=texto, _links_defeitos=0, _locale_defeitos="pt_BR",
                                 _abrir_discussao=lambda url: None,
                                 _texto_publico=VisualizadorPdfBuscaVista._texto_publico)
        metodo = VisualizadorPdfBuscaVista._mostrar_defeito
        segundo = {**ITEM, "titulo": "Segundo 12CU200G6", "url_defeito": "https://example.test/threads/456",
                   "url_reparo": "https://example.test/threads/456"}
        metodo(janela, ITEM, 0, "bv_traducao_pendente")
        metodo(janela, segundo, 1, "bv_traducao_indisponivel")
        metodo(janela, ITEM, 0, "bv_local_concluido", atualizar=True, traducao="Texto traduzido")
        conteudo = texto.get("1.0", "end")
        assert conteudo.count("Texto traduzido") == 1
        assert conteudo.count("Segundo 12CU200G6") == 1
        assert conteudo.index("Texto traduzido") < conteudo.index("Segundo")
        assert conteudo.index("Texto original") < conteudo.index("Texto traduzido")
        assert conteudo.count(ITEM["url_defeito"]) == 2
        assert segundo["url_defeito"] in conteudo
        assert any(texto.tag_ranges(tag) for tag in texto.tag_names() if tag.startswith("link_defeito_"))
    finally:
        texto.destroy()


def test_cancelar_pesquisa_informa_fallback_para_traducoes_pendentes():
    exibidos, mensagens = [], []
    janela = SimpleNamespace(
        _cancel_defeitos=threading.Event(), _traducoes_pendentes={0: ITEM},
        _itens_defeitos={0: {"original": ITEM, "traduzido": None, "estado": "bv_traducao_pendente"}},
        _locale_defeitos="pt_BR",
        _atualizar_defeito_traduzido=lambda numero: exibidos.append(numero),
        lbl_defeitos=SimpleNamespace(configure=lambda **kw: mensagens.append(kw["text"])),
        btn_cancelar_defeitos=SimpleNamespace(configure=lambda **kw: None),
    )
    VisualizadorPdfBuscaVista._cancelar_pesquisa_defeitos(janela)
    assert janela._cancel_defeitos.is_set()
    assert not janela._traducoes_pendentes
    assert janela._itens_defeitos[0]["estado"] == "bv_local_cancelada"
    assert exibidos == [0]
    assert "cancelada" in mensagens[0]


def test_endereco_google_por_idioma():
    for locale, destino in (("pt_BR", "pt"), ("en_US", "en"), ("es_UY", "es")):
        url = traducao.endereco_google(locale)
        partes = urlparse(url)
        assert partes.scheme == "https" and partes.netloc == "translate.google.com"
        assert parse_qs(partes.query) == {"sl": ["auto"], "tl": [destino]}
    with pytest.raises(ValueError):
        traducao.endereco_google("idioma-desconhecido")

def test_partes_google_preservam_texto_e_limite():
    texto = ("The Shimano Curado drag washer is worn. Çã 🎣\n" * 250)
    urls = traducao.partes_google(texto, "pt_BR")
    assert len(urls) > 1 and all(len(url) <= 1800 for url in urls)
    trechos = []
    for i, url in enumerate(urls, 1):
        dados = parse_qs(urlparse(url).query)
        assert dados["sl"] == ["auto"] and dados["tl"] == ["pt"]
        cabecalho = f"[Parte {i}/{len(urls)}]\n"
        assert dados["text"][0].startswith(cabecalho)
        trechos.append(dados["text"][0][len(cabecalho):])
    assert "".join(trechos) == texto


@pytest.mark.parametrize("texto,chave", [
    ("Drag issue; John Smith repaired the reel.", "bv_dado_nome"),
    ("Drag issue. Email: person@example.test", "bv_dado_contato"),
    ("Drag issue. Phone +55 11 99999-8888", "bv_dado_contato"),
    ("Drag repair, 45 Main Street", "bv_dado_endereco"),
    ("Drag repair price $300", "bv_dado_comercial"),
    ("Drag repair FRS OS 123", "bv_dado_operacional"),
    ("Shimano Curado drag issue.\n\nGreat weekend everyone.", "bv_dado_nao_tecnico"),
])
def test_dados_sensiveis_bloqueados(texto, chave):
    assert chave in traducao.detectar_sensiveis(texto, IDENTIDADE)


def test_revisao_admite_apenas_remover_e_sem_dados_sensiveis():
    original = "Shimano Curado drag repair. Email person@example.test"
    revisado = "Shimano Curado drag repair. "
    assert traducao.somente_remocoes(original, revisado)
    assert not traducao.somente_remocoes(original, revisado + "FRS")
    assert traducao.detectar_sensiveis(original, IDENTIDADE)
    assert not traducao.detectar_sensiveis(revisado, IDENTIDADE)


def test_preparacao_local_remove_contato_e_bloqueia_dados_comerciais():
    texto = "Shimano Curado drag repair. Email person@example.test"
    preparado = traducao.preparar_texto_local(texto, IDENTIDADE)
    assert "person@example.test" not in preparado
    assert "Shimano Curado" in preparado
    with pytest.raises(traducao.TraducaoLocalIndisponivel, match="dados_sensiveis"):
        traducao.preparar_texto_local("Shimano Curado drag price $300.", IDENTIDADE)


def test_traducao_local_preserva_paragrafos_e_protege_codigo(monkeypatch):
    class Tokenizer:
        def __init__(self, **kwargs):
            pass

        def encode(self, texto, out_type=str):
            return texto.split()

        def decode(self, tokens):
            return " ".join(tokens)

    class Tradutor:
        def __init__(self, *args, **kwargs):
            pass

        def translate_batch(self, fontes, **kwargs):
            palavras = ["problema" if palavra == "problem" else palavra for palavra in fontes[0]]
            return [SimpleNamespace(hypotheses=[palavras])]

    monkeypatch.setattr(type(traducao._MODELO_LOCAL), "is_file", lambda self: True)
    monkeypatch.setitem(sys.modules, "sentencepiece", SimpleNamespace(SentencePieceProcessor=Tokenizer))
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(Translator=Tradutor))
    texto = ("Shimano Curado 12CU200G6 problem\n\n" + "drag problem " * 120).strip()
    resultado = traducao.traduzir_texto_local(texto, "en", "pt_BR", IDENTIDADE, threading.Event())
    assert resultado.count("\n\n") == 1
    assert resultado.count("problema") == 121
    assert "12CU200G6" in resultado
    with pytest.raises(traducao.TraducaoLocalIndisponivel, match="idioma"):
        traducao.traduzir_texto_local(texto, "", "pt_BR", IDENTIDADE, threading.Event())
    cancelado = threading.Event()
    cancelado.set()
    with pytest.raises(InterruptedError):
        traducao.traduzir_texto_local(texto, "en", "pt_BR", IDENTIDADE, cancelado)


def test_painel_traduz_progressivamente_sem_navegador(root):
    liberar_primeira, liberar_pesquisa = threading.Event(), threading.Event()
    segundo = {**ITEM, "titulo": "Segunda discussão", "titulo_publico": "Second reel problem",
               "mensagens_publicas": ("Second reel has a problem.",)}

    def pesquisar(candidato, cancelamento, emitir):
        emitir("resultado", ITEM)
        emitir("resultado", segundo)
        liberar_pesquisa.wait(5)
        emitir("fim", "Concluída")

    def traduzir(texto, idioma, locale, identidade, cancelamento):
        if texto.startswith(ITEM["titulo_publico"]):
            liberar_primeira.wait(5)
            return "Primeira tradução\n\nPrimeiro comentário\n\nSegundo comentário"
        return "Segunda tradução\n\nComentário"

    with patch.object(defeitos, "pesquisar", side_effect=pesquisar), \
         patch.object(defeitos, "identidade_tecnica", return_value=IDENTIDADE), \
         patch.object(VisualizadorPdfBuscaVista, "_carregar"), \
         patch.object(traducao, "traduzir_texto_local", side_effect=traduzir), \
         patch.object(visualizador.webbrowser, "open", side_effect=AssertionError("navegador aberto")):
        janela = VisualizadorPdfBuscaVista(root, {"nome": "Teste", "fabricante": "SHIMANO"})
        try:
            prazo = time.monotonic() + 4
            while time.monotonic() < prazo and "Segunda tradução" not in janela.texto_defeitos.get("1.0", "end"):
                root.update()
                time.sleep(0.01)
            conteudo = janela.texto_defeitos.get("1.0", "end")
            assert "Segunda tradução" in conteudo and "Primeira tradução" not in conteudo
            assert not liberar_pesquisa.is_set()
            liberar_primeira.set()
            prazo = time.monotonic() + 4
            while time.monotonic() < prazo and "Primeira tradução" not in janela.texto_defeitos.get("1.0", "end"):
                root.update()
                time.sleep(0.01)
            conteudo = janela.texto_defeitos.get("1.0", "end")
            original = VisualizadorPdfBuscaVista._texto_publico(ITEM)
            assert original in conteudo
            assert conteudo.index(original) < conteudo.index("Primeira tradução") < conteudo.index("Segunda discussão")
            assert "Primeiro comentário\n\nSegundo comentário" in conteudo
            assert "Não confirmado" in conteudo and ITEM["url_defeito"] in conteudo
            assert any(janela.texto_defeitos.tag_ranges(tag) for tag in janela.texto_defeitos.tag_names() if tag.startswith("link_defeito_"))
        finally:
            liberar_primeira.set()
            liberar_pesquisa.set()
            janela._fechar()


def test_painel_bloqueia_conteudo_comercial_sem_acionar_modelo(root):
    item = {**ITEM, "mensagens_publicas": ("Shimano Curado drag repair price $300.",)}

    def pesquisar(candidato, cancelamento, emitir):
        emitir("resultado", item)
        emitir("fim", "Concluída")

    with patch.object(defeitos, "pesquisar", side_effect=pesquisar), \
         patch.object(defeitos, "identidade_tecnica", return_value=IDENTIDADE), \
         patch.object(VisualizadorPdfBuscaVista, "_carregar"), \
         patch("ctranslate2.Translator", side_effect=AssertionError("modelo acionado")):
        janela = VisualizadorPdfBuscaVista(root, {"nome": "Teste", "fabricante": "SHIMANO"})
        try:
            prazo = time.monotonic() + 4
            while time.monotonic() < prazo:
                root.update()
                if janela._itens_defeitos and not janela._traducoes_pendentes:
                    break
                time.sleep(0.01)
            assert janela._itens_defeitos[0]["estado"] == "bv_local_erro_dados_sensiveis"
            conteudo = janela.texto_defeitos.get("1.0", "end")
            assert item["mensagens_publicas"][0] in conteudo
            assert "dados sensíveis" in conteudo
        finally:
            janela._fechar()


@pytest.mark.parametrize("item,locale,estado", [
    ({**ITEM, "texto_publico_incompleto": True}, "pt_BR", "bv_google_incompleto"),
    ({**ITEM, "mensagens_publicas": ()}, "pt_BR", "bv_google_sem_texto"),
    (ITEM, "en_US", "bv_local_mesmo_idioma"),
])
def test_painel_nao_traduz_extracao_incompleta_ou_mesmo_idioma(root, item, locale, estado):
    def pesquisar(candidato, cancelamento, emitir):
        emitir("resultado", item)
        emitir("fim", "Concluída")

    with patch.object(defeitos, "pesquisar", side_effect=pesquisar), \
         patch.object(visualizador, "get_current_locale", return_value=locale), \
         patch.object(VisualizadorPdfBuscaVista, "_carregar"), \
         patch.object(traducao, "traduzir_texto_local", side_effect=AssertionError("tradução inesperada")):
        janela = VisualizadorPdfBuscaVista(root, {"nome": "Teste", "fabricante": "SHIMANO"})
        try:
            prazo = time.monotonic() + 4
            while time.monotonic() < prazo and not janela._itens_defeitos:
                root.update()
                time.sleep(0.01)
            assert janela._itens_defeitos[0]["estado"] == estado
            assert VisualizadorPdfBuscaVista._texto_publico(item) in janela.texto_defeitos.get("1.0", "end")
        finally:
            janela._fechar()


def test_janela_modelos_abre_sem_modalidade_e_redimensionavel(root):
    quadro = ctk.CTkFrame(root)
    quadro.pack()
    root.update()
    try:
        FrmOS._exibir_catalogo_modelos(quadro, "CURADO", "SHIMANO", [], [])
        janela = next(w for w in quadro.winfo_children() if isinstance(w, ctk.CTkToplevel))
        assert janela.state() == "withdrawn"
        pronto = tk.BooleanVar(root, False)
        root.after(100, lambda: pronto.set(True))
        root.wait_variable(pronto)
        assert janela.state() == "normal"
        assert str(janela.transient()) == str(root)
        assert janela.resizable() == (1, 1)
        assert not bool(int(janela.attributes("-topmost")))
        assert janela.grab_current() is None
        assert janela.winfo_width() == 820 and janela.winfo_height() == 520
    finally:
        quadro.destroy()
