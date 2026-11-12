import queue
import threading
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote_plus
from unittest.mock import patch

import pytest

import busca_vista_defeitos as defeitos
import busca_vista_visualizador as visualizador

PDF = "https://www.reelschematic.com/wp-content/uploads/schematics/Shimano/Curado/Shimano%20Curado%2012CU200G6.pdf"
TOPICO = "https://www.bdoutdoors.com/forums/threads/curado-drag.123/"
CANDIDATO = {
    "fabricante": "SHIMANO", "familia": "CURADO cliente João",
    "nome": "cliente João telefone 11999998888", "pdf_url": PDF,
}
PAGINA = """
<html><title>Shimano Curado 12CU200G6 drag problem</title>
<article class="message-body"><div class="bbWrapper">
My Shimano Curado 12CU200G6 drag stopped working.
</div></article>
<article class="message-body"><div class="bbWrapper">
The cause was a worn washer. I replaced the washer and fixed it.
</div></article></html>
"""


def test_identidade_vem_do_documento_nao_do_texto_da_os():
    identidade = defeitos.identidade_tecnica(CANDIDATO)
    assert identidade["modelo"] == "curado 12cu200g6"
    assert identidade["familia"] == "curado"
    assert defeitos.identidade_tecnica({**CANDIDATO, "fabricante": "CLIENTE JOAO"}) is None
    assert defeitos.identidade_tecnica({**CANDIDATO, "pdf_url": "https://site.test/cliente-11999998888.pdf"}) is None


def test_identidade_preserva_ano_antes_da_familia():
    candidato = {"fabricante": "DAIWA", "pdf_url": "https://example.test/18-TATULA-100H.pdf"}
    identidade = defeitos.identidade_tecnica(candidato)
    assert identidade["familia"] == "tatula"
    assert identidade["modelo"] == "18 tatula 100h"
    assert identidade["variantes"] == ["18", "100h"]


def test_marca_desconhecida_nao_faz_rede():
    eventos = []
    def nunca(*args):
        raise AssertionError("Consulta insegura não deve usar rede")
    defeitos.pesquisar({**CANDIDATO, "fabricante": "DESCONHECIDO"}, threading.Event(),
                      lambda *args: eventos.append(args), buscar_html=nunca)
    assert eventos[0][0] == "fim" and "nenhuma consulta" in eventos[0][1]


def test_discussao_e_solucao_com_fontes_sem_inventar_recorrencia():
    identidade = defeitos.identidade_tecnica(CANDIDATO)
    item = defeitos.analisar_discussao(TOPICO, PAGINA, identidade)
    assert item["escopo"] == "Variante"
    assert item["classificacao"] == "Não confirmado"
    assert "stopped" in item["sintomas"] and "replaced" in item["reparo"]
    assert item["url_defeito"] == item["url_reparo"] == TOPICO
    assert item["titulo_publico"] == "Shimano Curado 12CU200G6 drag problem"
    assert item["mensagens_publicas"] == (
        "My Shimano Curado 12CU200G6 drag stopped working.",
        "The cause was a worn washer. I replaced the washer and fixed it.",
    )
    outro_modelo = PAGINA.replace("12CU200G6", "12CU200G60")
    assert defeitos.analisar_discussao(TOPICO, outro_modelo, identidade) is None
    sem_causa_ou_reparo = '<title>Shimano Curado question</title><div class="message-body">My Curado has a problem.</div>'
    item = defeitos.analisar_discussao(TOPICO, sem_causa_ou_reparo, identidade)
    assert not item["causa"] and not item["reparo"] and not item["url_reparo"]
    sugestao = sem_causa_ou_reparo.replace("</div>", "</div><div class='message-body'>You should replace the washer.</div>")
    assert not defeitos.analisar_discussao(TOPICO, sugestao, identidade)["reparo"]
    assert defeitos.analisar_discussao(TOPICO, "<title>Shimano Stella problem</title><p>problem</p>", identidade) is None
    outro_tamanho = PAGINA.replace("12CU200G6", "300")
    assert defeitos.analisar_discussao(TOPICO, outro_tamanho, identidade) is None
    anuncio = PAGINA.replace("drag problem", "for sale")
    assert defeitos.analisar_discussao(TOPICO, anuncio, identidade) is None
    negacao = PAGINA.replace("drag stopped working", "has no problems")
    assert defeitos.analisar_discussao(TOPICO, negacao, identidade) is None


def test_extrai_mensagem_inteira_com_html_aninhado():
    parser = defeitos._MensagensPublicas()
    trecho = "washer problem " * 30
    parser.feed(f'<article class="message-body"><div><p>{trecho}</p><p>Fixed by replacing gear.</p></div></article>'
                '<div class="postbody">Bearing issue.<div>Repaired the bearing.</div></div>')
    assert len(parser.mensagens) == 2
    assert trecho.strip() in parser.mensagens[0] and "Fixed by replacing gear." in parser.mensagens[0]
    assert "Bearing issue." in parser.mensagens[1] and "Repaired the bearing." in parser.mensagens[1]
    pagina_incompleta = PAGINA + '<div class="postbody">Bearing repair'
    item = defeitos.analisar_discussao(TOPICO, pagina_incompleta, defeitos.identidade_tecnica(CANDIDATO))
    assert item["texto_publico_incompleto"]


def test_links_de_busca_e_enderecos_privados_nao_sao_discussao():
    assert not defeitos._link_publico("https://www.bing.com/search?q=curado")
    assert not defeitos._link_publico("https://forum.test/forums/fishing-reels/")
    assert not defeitos._link_publico("http://127.0.0.1/threads/a/")
    assert defeitos._link_publico(TOPICO)
    assert defeitos._link_publico("https://alantani.com/index.php?topic=23848.0")


def test_formulario_publico_do_forum_envia_apenas_consulta_tecnica():
    requisicoes = []
    class Resposta:
        def __init__(self, corpo, url):
            self.corpo, self.url = corpo.encode(), url
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limite):
            return self.corpo[:limite]
        def geturl(self):
            return self.url
    class Abridor:
        def open(self, request, timeout):
            requisicoes.append(request)
            if request.data is None:
                return Resposta('<script>var captcha = false;</script><input name="_xfToken" value="token">', request.full_url)
            return Resposta(f'<a href="{TOPICO}">Curado problem</a>', request.full_url)
    with patch.object(defeitos, "build_opener", return_value=Abridor()):
        pagina, _ = defeitos._buscar_forum("SHIMANO curado 12cu200g6", 2)
    dados = parse_qs(requisicoes[1].data.decode())
    assert dados == {"keywords": ["SHIMANO curado 12cu200g6 problem"], "_xfToken": ["token"]}
    parser = defeitos._ResultadosForum()
    parser.feed(pagina)
    assert parser.links == [(TOPICO, "Curado problem")]


def test_forum_bloqueado_e_reportado_sem_impedir_outros_resultados():
    eventos, tentativas = [], []
    def bloqueado(*args):
        tentativas.append(args)
        raise PermissionError("verificação")
    defeitos.pesquisar(
        CANDIDATO, threading.Event(), lambda *args: eventos.append(args),
        buscar_forum=bloqueado, buscar_html=lambda url, timeout: ("<html></html>", url),
    )
    assert "Bloodydecks: bloqueio ou verificação" in eventos[-1][1]
    assert len(tentativas) == 1


def test_forum_nao_contorna_verificacao():
    class Resposta:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limite):
            return b"<html>Verify you are human</html>"
    abridor = SimpleNamespace(open=lambda *args, **kwargs: Resposta())
    with patch.object(defeitos, "build_opener", return_value=abridor), pytest.raises(PermissionError):
        defeitos._buscar_forum("SHIMANO curado", 2)


def test_cancelar_forum_antes_do_envio_do_formulario():
    cancelamento = threading.Event()
    chamadas = []
    class Resposta:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self, limite):
            cancelamento.set()
            return b'<input name="_xfToken" value="token">'
    def abrir(request, timeout):
        chamadas.append(request)
        return Resposta()
    with patch.object(defeitos, "build_opener", return_value=SimpleNamespace(open=abrir)):
        with pytest.raises(InterruptedError):
            defeitos._buscar_forum("SHIMANO curado", 2, cancelamento)
    assert len(chamadas) == 1 and chamadas[0].data is None


def test_fontes_independentes_deduplicam_e_nao_transmitem_os():
    eventos, urls = [], []
    resultados = f'<html><h2><a href="{TOPICO}">Shimano Curado problem</a></h2></html>'
    def buscar(url, timeout):
        urls.append(url)
        if "duckduckgo" in url:
            raise HTTPError(url, 403, "Forbidden", {}, None)
        if "bing.com" in url:
            return resultados, url
        assert url == TOPICO
        return PAGINA, url
    defeitos.pesquisar(CANDIDATO, threading.Event(), lambda *args: eventos.append(args), buscar_html=buscar,
                      buscar_forum=lambda consulta, timeout: ("<html></html>", defeitos.FORUM_BD))
    encontrados = [valor for tipo, valor in eventos if tipo == "resultado"]
    assert len(encontrados) == 1
    assert "bloqueado" in eventos[-1][1]
    for url in urls:
        enviado = unquote_plus(url).lower()
        assert "joao" not in enviado and "joão" not in enviado and "11999998888" not in enviado


def test_resultado_aparece_antes_de_fonte_lenta_e_cancelamento():
    liberar, recebido, cancelar = threading.Event(), threading.Event(), threading.Event()
    eventos = []
    def buscar(url, timeout):
        if "duckduckgo" in url:
            liberar.wait(3)
            return "<html>nada</html>", url
        if "bing.com" in url:
            return f'<h2><a href="{TOPICO}">Curado</a></h2>', url
        return PAGINA, url
    def emitir(tipo, valor):
        eventos.append((tipo, valor))
        if tipo == "resultado":
            recebido.set()
    worker = threading.Thread(target=defeitos.pesquisar, args=(CANDIDATO, cancelar, emitir),
                              kwargs={"buscar_html": buscar, "prazo": 2,
                                      "buscar_forum": lambda consulta, timeout: ("<html></html>", defeitos.FORUM_BD)})
    worker.start()
    assert recebido.wait(1.5)
    cancelar.set()
    worker.join(1)
    liberar.set()
    assert not worker.is_alive()
    assert not any(tipo == "fim" for tipo, _ in eventos)


def test_fonte_lenta_nao_atrasa_resultado_e_informa_tempo_excedido():
    liberar = threading.Event()
    eventos, consultas = [], []
    def buscar(url, timeout):
        consultas.append(unquote_plus(url))
        if "duckduckgo" in url:
            liberar.wait(2)
            return "<html></html>", url
        if "bing.com" in url:
            return f'<h2><a href="{TOPICO}">Curado 12CU200G6 problem</a></h2>', url
        return PAGINA, url
    def forum(consulta, timeout):
        consultas.append(consulta)
        liberar.wait(2)
        return "<html></html>", defeitos.FORUM_BD
    try:
        inicio = time.monotonic()
        with patch.object(defeitos, "PRAZO_FONTE", 0.3):
            defeitos.pesquisar(CANDIDATO, threading.Event(), lambda *x: eventos.append(x),
                              buscar_html=buscar, buscar_forum=forum, prazo=1.5)
        assert time.monotonic() - inicio < 1.2
        assert any(t == "resultado" and v["escopo"] == "Variante" for t, v in eventos)
        assert any(t == "status" and "tempo excedido" in v for t, v in eventos)
        assert "tempo excedido" in eventos[-1][1]
        assert all("12cu200g6" in q.lower() for q in consultas if q != TOPICO)
    finally:
        liberar.set()


def test_prazo_total_encerra_mesmo_com_todas_as_fontes_paradas():
    liberar = threading.Event()
    eventos = []
    def lenta(url, timeout):
        liberar.wait(2)
        return "<html></html>", url
    try:
        inicio = time.monotonic()
        defeitos.pesquisar(
            CANDIDATO, threading.Event(), lambda *x: eventos.append(x),
            buscar_html=lenta, buscar_forum=lenta, prazo=0.25,
        )
        assert time.monotonic() - inicio < 1
        assert eventos[-1][0] == "fim" and "Prazo total" in eventos[-1][1]
        assert any(t == "status" and "tempo excedido" in v for t, v in eventos)
    finally:
        liberar.set()


def test_discussoes_lentas_de_duas_fontes_nao_bloqueiam_terceira():
    liberar, lentas_iniciadas, recebido = threading.Event(), threading.Event(), threading.Event()
    contagem, lock = [], threading.Lock()
    bing = "".join(f'<h2><a href="https://forum.test/threads/curado-slow-{i}/">Curado problem</a></h2>' for i in range(4))
    forum = "".join(f'<a href="/forums/threads/curado-slow-{i}/">Curado problem</a>' for i in range(4))
    def buscar(url, timeout):
        if "bing.com" in url:
            return bing, url
        if "duckduckgo.com" in url:
            assert lentas_iniciadas.wait(2)
            return f'<h2><a href="{TOPICO}">Curado 12CU200G6 problem</a></h2>', url
        if url == TOPICO:
            return PAGINA, url
        with lock:
            contagem.append(url)
            if len(contagem) == 8:
                lentas_iniciadas.set()
        liberar.wait(3)
        return "<html></html>", url
    def emitir(tipo, valor):
        if tipo == "resultado":
            recebido.set()
    worker = threading.Thread(
        target=defeitos.pesquisar, args=(CANDIDATO, threading.Event(), emitir),
        kwargs={"buscar_html": buscar, "buscar_forum": lambda *args: (forum, defeitos.FORUM_BD), "prazo": 4},
    )
    try:
        worker.start()
        assert recebido.wait(2.5)
        assert len(contagem) == 8
    finally:
        liberar.set()
        worker.join(4)
    assert not worker.is_alive()


def test_familia_pesquisada_apenas_se_variante_nao_confirmada():
    consultas, eventos = [], []
    familiar = '<title>Shimano Curado problem</title><article class="message-body">My Shimano Curado has a problem.</article>'
    def buscar(url, timeout):
        if url == TOPICO:
            return familiar, url
        consultas.append(unquote_plus(url).lower())
        if "bing.com" in url and "12cu200g6" not in unquote_plus(url).lower():
            return f'<h2><a href="{TOPICO}">Curado problem</a></h2>', url
        return "<html></html>", url
    def forum(consulta, timeout):
        consultas.append(consulta.lower())
        return "<html></html>", defeitos.FORUM_BD
    defeitos.pesquisar(CANDIDATO, threading.Event(), lambda *x: eventos.append(x),
                      buscar_html=buscar, buscar_forum=forum)
    resultados = [v for t, v in eventos if t == "resultado"]
    assert len(resultados) == 1 and resultados[0]["escopo"] == "Família; variante não confirmada"
    assert len(consultas) == 6 and sum("12cu200g6" in q for q in consultas) == 3
    assert any(t == "status" and "pesquisando a família" in v for t, v in eventos)


def test_pesquisa_equivalente_compartilhada_e_cancelamento_independente():
    liberar, iniciou, segundo_inscrito = threading.Event(), threading.Event(), threading.Event()
    consultas, eventos1, eventos2 = [], [], []
    cancelar1, cancelar2 = threading.Event(), threading.Event()
    def buscar(url, timeout):
        if url == TOPICO:
            return PAGINA, url
        consultas.append(url)
        if "bing.com" in url:
            iniciou.set()
            liberar.wait(2)
            return f'<h2><a href="{TOPICO}">Curado 12CU200G6 problem</a></h2>', url
        return "<html></html>", url
    def forum(consulta, timeout):
        consultas.append(consulta)
        return "<html></html>", defeitos.FORUM_BD
    def emitir2(tipo, valor):
        eventos2.append((tipo, valor))
        segundo_inscrito.set()
    kwargs = {"buscar_html": buscar, "buscar_forum": forum, "prazo": 3}
    t1 = threading.Thread(target=defeitos.pesquisar, args=(CANDIDATO, cancelar1, lambda *x: eventos1.append(x)), kwargs=kwargs)
    candidato_equivalente = {**CANDIDATO, "pdf_url": "https://example.test/Shimano%20Curado%2012CU200G6.pdf"}
    t2 = threading.Thread(target=defeitos.pesquisar, args=(candidato_equivalente, cancelar2, emitir2), kwargs=kwargs)
    try:
        t1.start()
        assert iniciou.wait(1)
        t2.start()
        assert segundo_inscrito.wait(1)
        cancelar1.set()
        t1.join(1)
        assert not t1.is_alive()
        liberar.set()
        t2.join(2)
        assert not t2.is_alive()
        assert len(consultas) == 3
        assert any(t == "resultado" and v["escopo"] == "Variante" for t, v in eventos2)
        assert eventos2[-1][0] == "fim"
        assert not any(t == "resultado" for t, _ in eventos1)
    finally:
        liberar.set()
        t1.join(2)
        if t2.ident is not None:
            t2.join(2)


def test_worker_entrega_resultados_por_fila_e_sem_widgets():
    fila = queue.Queue()
    objeto = SimpleNamespace(candidato=CANDIDATO, _cancel_defeitos=threading.Event(), _fila=fila)
    def pesquisar(candidato, cancelamento, emitir):
        emitir("resultado", {"titulo": "Relato"})
        emitir("fim", "Concluído")
    with patch.object(visualizador.busca_vista_defeitos, "pesquisar", side_effect=pesquisar):
        thread = threading.Thread(target=visualizador.VisualizadorPdfBuscaVista._pesquisar_defeitos, args=(objeto,))
        thread.start()
        thread.join(2)
    assert fila.get_nowait() == ("defeitos_resultado", {"titulo": "Relato"})
    assert fila.get_nowait() == ("defeitos_fim", "Concluído")


def test_link_da_discussao_abre_direto_e_informa_falha():
    mensagens = []
    janela = SimpleNamespace(lbl_defeitos=SimpleNamespace(configure=lambda **kw: mensagens.append(kw["text"])))
    with patch.object(visualizador.webbrowser, "open", return_value=True) as abrir:
        visualizador.VisualizadorPdfBuscaVista._abrir_discussao(janela, TOPICO)
        abrir.assert_called_once_with(TOPICO, new=2)
    with patch.object(visualizador.webbrowser, "open", return_value=False):
        visualizador.VisualizadorPdfBuscaVista._abrir_discussao(janela, TOPICO)
    assert "Não foi possível abrir" in mensagens[-1]
