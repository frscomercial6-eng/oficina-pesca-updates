from __future__ import annotations

import threading
import time
import unittest
import urllib.error
from unittest.mock import patch

import tela_os
import busca_vista_fontes as descoberta

F = tela_os.FrmOS
MARURI = "https://marurifishing.com.py/produto/pecas-carretilha-black-pira-bg-400"


def maruri_html(total: int = 66) -> str:
    # Mesmo formato da página real: <strong>CÓDIGO</strong> | Peças MODELO #POSIÇÃO descrição
    linhas = "".join(
        f"<span><strong>{180000 + i}</strong> |  Peças BLACK PIRA #{100 + i} peça {i}\n</span>"
        for i in range(total)
    )
    linhas += "<span><strong>184584</strong> |  Peças BLACK PIRA #T05 parafuso da tr. manivela </span>"
    return f"<html><body><h1>BLACK PIRA BG 400 | Maruri Fishing</h1>{linhas}</body></html>"


def test_indice_reconhece_modelo_variantes_e_nao_confia_em_rotulo_pdf_incorreto():
    pagina = """
    <a href="/pages/baitcast-schematics">Baitcast</a>
    <a href="https://cdn.shopify.com/files/TATULA-SV-TW-103XSL.pdf">TATULA SV TW 103XSL</a>
    <a href="https://cdn.shopify.com/files/TATULA-SV-TW-103H.pdf">TATULA SV TW 103H</a>
    <a href="https://cdn.shopify.com/files/OTHER-103H.pdf">TATULA-103H.pdf</a>
    <a href="https://cdn.shopify.com/files/TATULA-SV-TW-1030.pdf">TATULA SV TW 1030</a>
    """
    docs, paginas = descoberta.ler_indice(pagina, "https://daiwa.us/pages/index", "Daiwa", "DAIWA", "TATULA SV TW 103")
    assert {d["nome"] for d in docs} == {"TATULA SV TW 103XSL", "TATULA SV TW 103H"}
    assert paginas == ["https://daiwa.us/pages/baitcast-schematics"]
    assert all(not d["verificado"] for d in docs)


def test_kastking_usa_nome_contextual_e_preserva_variantes():
    html = """
    <li><span class="product_text">Sharky III Spinning Reel</span>
    <a href="https://cdn.shopify.com/files/Sharky_III_SP.pdf"><span>Download PDF</span></a></li>
    <li><span class="product_text">Sharky III Baitcasting Reel</span>
    <a href="https://cdn.shopify.com/files/Sharky_III_BC.pdf"><span>Download PDF</span></a></li>
    """
    docs, _ = descoberta.ler_indice(html, "https://kastking.com/pages/manuals-schematics", "KastKing", "KASTKING", "SHARKY")
    assert {d["nome"] for d in docs} == {"Sharky III Spinning Reel", "Sharky III Baitcasting Reel"}
    assert len({d["pdf_url"] for d in docs}) == 2


def test_indices_sao_independentes_e_falha_nao_entra_no_cache():
    descoberta.limpar_cache_fontes()
    seeds = (("Boa", "https://site.test/manual"), ("Bloqueada", "https://outro.test/manual"))
    chamadas = []
    def obter(url):
        chamadas.append(url)
        if "outro" in url:
            raise urllib.error.HTTPError(url, 403, "bloqueado", {}, None)
        return '<a href="https://site.test/diagram-BG-3000.pdf">BG 3000</a>'
    with patch.dict(descoberta.FONTES_INICIAIS, {"DAIWA": seeds}):
        docs, estado, mensagem = descoberta.descobrir("DAIWA", "BG", obter)
        assert len(docs) == 1 and estado == "incompleto" and "HTTP 403" in mensagem
        descoberta.descobrir("DAIWA", "BG", obter)
    assert chamadas.count("https://site.test/manual") == 1
    assert chamadas.count("https://outro.test/manual") == 2
    descoberta.limpar_cache_fontes()


def test_prazo_e_cancelamento_nao_impedem_resultado_da_fonte_rapida():
    descoberta.limpar_cache_fontes()
    liberar = threading.Event()
    seeds = (("Boa", "https://site.test/manual"), ("Lenta", "https://lento.test/manual"))
    def obter(url):
        if "lento" in url:
            liberar.wait(2)
        return '<a href="https://site.test/BG-3000.pdf">BG 3000</a>'
    with patch.dict(descoberta.FONTES_INICIAIS, {"DAIWA": seeds}):
        inicio = time.monotonic()
        docs, estado, mensagem = descoberta.descobrir("DAIWA", "BG", obter, prazo=0.15)
        assert time.monotonic() - inicio < 0.8
        assert docs and estado == "incompleto" and "Prazo" in mensagem
        cancelamento = threading.Event()
        cancelamento.set()
        docs, estado, _ = descoberta.descobrir("DAIWA", "BG", obter, cancelamento)
        assert not docs and estado == "cancelado"
    liberar.set()
    descoberta.limpar_cache_fontes()


def test_fonte_com_muitos_produtos_nao_esgota_cota_das_outras():
    descoberta.limpar_cache_fontes()
    seeds = (("Grande", "https://grande.test/"), ("Outra", "https://outra.test/"))
    def obter(url):
        if url == "https://grande.test/":
            return "<html>" + "".join(
                f'<a href="/p/kratos-{i}">Kratos {i}</a>' for i in range(20)
            ) + "</html>"
        if url == "https://outra.test/":
            time.sleep(0.1)
            return '<html><a href="/p/kratos-real">Kratos real</a></html>'
        if url == "https://outra.test/p/kratos-real":
            return '<html><a href="/diagrama-kratos-real.pdf">Kratos real</a></html>'
        return "<html>Produto</html>"

    with patch.dict(descoberta.FONTES_INICIAIS, {"SAINT": seeds}):
        docs, estado, mensagem = descoberta.descobrir("SAINT", "KRATOS", obter, max_paginas=10)
    assert any(d["pdf_url"] == "https://outra.test/diagrama-kratos-real.pdf" for d in docs)
    assert estado == "incompleto" and "Limite" in mensagem
    descoberta.limpar_cache_fontes()


def test_imagem_tecnica_e_catalogo_html_nao_viram_pdf():
    pagina = '<a href="/diagramas/tatula-exploded.png">Tatula exploded</a>'
    docs, _ = descoberta.ler_indice(pagina, "https://daiwa.us/pages/a", "Daiwa", "DAIWA", "TATULA")
    assert len(docs) == 1 and docs[0]["tipo_documento"] == "imagem"
    parts = [{"codigo": "184584", "descricao": "parafuso", "posicao": "T05"}]
    html = descoberta.catalogos_html([{"url": MARURI, "parts": parts, "source": "Maruri"}], "MARURI", "BLACK PIRA BG 400")
    assert len(html) == 1 and html[0]["tipo_documento"] == "html"
    assert html[0]["parts"] == parts and not html[0]["verificado"]


def test_produtos_variantes_e_documentos_entre_dominios_do_catalogo():
    categoria = """
    <a href="/p/carretilha-kratos-20-r">Kratos 20</a>
    <a href="/p/carretilha-kratos-30">Kratos 30</a>
    <a href="/p/carretilha-sole-g3">Sole</a>
    <a href="/c/carretilhas/2">Próxima</a>
    <a href="/login">Entrar</a>
    """
    _, paginas = descoberta.ler_indice(
        categoria, "https://www.saintoficial.com.br/c/carretilhas", "Saint", "SAINT PLUS", "KRATOS"
    )
    assert "https://www.saintoficial.com.br/p/carretilha-kratos-20-r" in paginas
    assert "https://www.saintoficial.com.br/p/carretilha-kratos-30" in paginas
    assert "https://www.saintoficial.com.br/c/carretilhas/2" in paginas
    assert not any("sole" in p or "login" in p for p in paginas)

    produto = """
    <h1>Vista Explodida Carretilha Kratos 20</h1>
    <a href="https://www.grupojoga.com.br/saint/vista_explodida/carretilha/Vista_Explodida_Carretilha_Kratos_20_30.pdf">Baixar</a>
    <a href="https://inseguro.test/Kratos-20.pdf">Baixar</a>
    """
    docs, _ = descoberta.ler_indice(
        produto, "https://www.saintoficial.com.br/p/carretilha-kratos-20-r", "Saint",
        "SAINT PLUS", "KRATOS", {"www.saintoficial.com.br", "www.grupojoga.com.br"},
    )
    assert len(docs) == 1
    assert docs[0]["nome"].endswith("Kratos 20 30")
    assert docs[0]["origem_url"].endswith("carretilha-kratos-20-r")
    assert not docs[0]["verificado"]


def test_svg_e_identificado_sem_ser_apresentado_como_pdf():
    docs, _ = descoberta.ler_indice(
        '<a href="/diagramas/tatula-exploded.svg">Tatula exploded</a>',
        "https://daiwa.us/pages/index", "Daiwa", "DAIWA", "TATULA",
    )
    assert len(docs) == 1 and docs[0]["tipo_documento"] == "svg"


def test_svg_informa_limite_sem_download():
    import queue
    from types import SimpleNamespace
    import busca_vista_visualizador as viewer

    def nao_baixar(*args):
        raise AssertionError("SVG não deve ser baixado sem suporte de visualização")

    objeto = SimpleNamespace(
        candidato={"tipo_documento": "svg"}, _fila=queue.Queue(), _baixar=nao_baixar,
    )
    viewer.VisualizadorPdfBuscaVista._carregar(objeto)
    tipo, mensagem = objeto._fila.get_nowait()
    assert tipo == "erro" and "SVG" in mensagem and "não é suportada" in mensagem


def test_captcha_em_formulario_nao_bloqueia_catalogo():
    descoberta.limpar_cache_fontes()
    pagina = '<html><div class="captcha-widget"></div><a href="/manual.pdf">Manual</a></html>'
    assert descoberta._obter_pagina("https://example.test/", lambda _: pagina) == pagina
    descoberta.limpar_cache_fontes()


def test_mapa_xml_descobre_subindices_e_produtos_sem_entidades():
    indice = """<?xml version="1.0"?>
    <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://site.test/products-sitemap.xml</loc></sitemap>
        <sitemap><loc>https://outro.test/sitemap.xml</loc></sitemap>
    </sitemapindex>"""
    _, paginas = descoberta.ler_indice(indice, "https://site.test/sitemap.xml", "Teste", "SAINT", "KRATOS")
    assert paginas == ["https://site.test/products-sitemap.xml"]
    produtos = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://site.test/p/carretilha-kratos-20</loc></url>
        <url><loc>https://site.test/p/carretilha-sole</loc></url>
    </urlset>"""
    _, paginas = descoberta.ler_indice(produtos, paginas[0], "Teste", "SAINT", "KRATOS")
    assert paginas == ["https://site.test/p/carretilha-kratos-20"]
    import pytest
    with pytest.raises(ValueError, match="XML"):
        descoberta.ler_indice('<!DOCTYPE urlset [<!ENTITY x "x">]><urlset/>',
                             "https://site.test/sitemap.xml", "Teste", "SAINT", "KRATOS")


def test_pecas_sao_inseridas_em_lotes_cancelaveis():
    from types import SimpleNamespace
    import busca_vista_visualizador as viewer

    linhas, tarefas = [], []
    tree = SimpleNamespace(
        get_children=lambda: (), insert=lambda *args, **kw: linhas.append(kw["values"]),
    )
    objeto = SimpleNamespace(
        tree=tree, _fechada=False, lbl_pecas=SimpleNamespace(configure=lambda **kw: None),
        after=lambda _, callback: tarefas.append(callback),
    )
    pecas = [{"codigo": str(i)} for i in range(120)]
    viewer.VisualizadorPdfBuscaVista._mostrar_analise(objeto, {"parts": pecas})
    assert len(linhas) == 50 and len(tarefas) == 1
    tarefas.pop(0)()
    assert len(linhas) == 100 and len(tarefas) == 1
    objeto._fechada = True
    tarefas.pop(0)()
    assert len(linhas) == 100


class Harness:
    _normalizar_termo_tecnico = F._normalizar_termo_tecnico
    _variantes_modelo = F._variantes_modelo
    _extrair_fabricante_modelo = F._extrair_fabricante_modelo
    _equipamento_seguro_para_consulta = F._equipamento_seguro_para_consulta
    _extrair_pecas_pagina_tecnica = F._extrair_pecas_pagina_tecnica
    _extrair_conhecimento_pagina_tecnica = F._extrair_conhecimento_pagina_tecnica
    _buscar_links_web_diagrama = F._buscar_links_web_diagrama
    _normalizar_link_resultado = F._normalizar_link_resultado
    _link_eh_tecnico_valido = F._link_eh_tecnico_valido
    _pontuar_link_diagrama = F._pontuar_link_diagrama
    _tipo_documentacao_tecnica = F._tipo_documentacao_tecnica
    _rotulo_fonte_tecnica = F._rotulo_fonte_tecnica

    def __init__(self, paginas=None, atraso=None):
        self.paginas = paginas or {}
        self.atraso = atraso or {}
        self.chamadas = []
        self.liberar = threading.Event()

    def _buscar_pagina_tecnica(self, url, timeout):
        self.chamadas.append(url)
        if url in self.atraso:
            self.liberar.wait(self.atraso[url])
        resposta = self.paginas.get(url)
        if isinstance(resposta, Exception):
            raise resposta
        if resposta is None:
            return "<html><body>Catalogo tecnico</body></html>", "text/html"
        return resposta, "text/html"


class TestBuscaVistaFontes(unittest.TestCase):
    def setUp(self):
        tela_os._limpar_cache_busca_vista()
        descoberta.limpar_cache_fontes()

    def test_maruri_keeps_code_description_and_position_for_every_part(self):
        pecas = Harness()._extrair_pecas_pagina_tecnica(maruri_html())

        self.assertEqual(len(pecas), 67)  # a versão anterior cortava em 40
        primeira = pecas[0]
        self.assertEqual((primeira["codigo"], primeira["posicao"]), ("180000", "100"))
        self.assertNotIn("#", primeira["descricao"])
        self.assertTrue(any(p["codigo"] == "184584" and p["posicao"] == "T05" for p in pecas))

    def test_maruri_page_is_a_candidate_with_origin_and_not_verified(self):
        harness = Harness({MARURI: maruri_html()})
        resultados = harness._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400")

        pagina = next(item for item in resultados if item["url"] == MARURI)
        self.assertFalse(pagina["verified"])
        self.assertEqual(pagina["source"], "Maruri Fishing")
        self.assertGreater(len(pagina["parts"]), 40)
        self.assertTrue(all(p["origem_url"] == MARURI for p in pagina["parts"]))
        self.assertNotIn("PDF técnico —", pagina["kind"])

    def test_model_variants_and_compact_spelling(self):
        harness = Harness()
        self.assertEqual(harness._extrair_fabricante_modelo("Carretilha Sumax Akita 2"), ("SUMAX", "AKITA 2"))
        self.assertEqual(harness._variantes_modelo("Akita 2"), ["AKITA II", "AKITA2"])
        self.assertEqual(
            harness._normalizar_termo_tecnico("BG400", separar_alfanumerico=True),
            harness._normalizar_termo_tecnico("BG 400", separar_alfanumerico=True),
        )
        pagina = "<html><body>Sumax Akita2 parts <strong>123456</strong> | Drag washer</body></html>"
        resultados = Harness({MARURI: pagina})._buscar_links_web_diagrama("SUMAX", "AKITA 2")
        self.assertTrue(any(item["url"] == MARURI for item in resultados))

    def test_sumax_without_match_returns_no_documents(self):
        harness = Harness()
        self.assertEqual(harness._buscar_links_web_diagrama("SUMAX", "AKITA 2"), [])
        estados = {f["state"] for f in harness._ultima_busca_fontes_consultadas}
        self.assertEqual(estados, {"ok"})
        self.assertTrue(all(not f["status"].startswith("Documento encontrado") for f in harness._ultima_busca_fontes_consultadas))

    def test_blocked_sources_are_distinguished_from_unavailable(self):
        forbidden = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
        harness = Harness({
            "https://kastking.com/collections/fishing-reels?ref=shopbycategory": forbidden,
            "https://www.okumabrasil.com.br/assistencia-tecnica": OSError("sem rede"),
            "https://kastking.com/pages/manuals-schematics?ref=top": "Please verify you are human",
        })
        harness._buscar_links_web_diagrama("SUMAX", "AKITA 2")
        estados = {f["url"]: f["state"] for f in harness._ultima_busca_fontes_consultadas}

        self.assertEqual(estados["https://kastking.com/collections/fishing-reels?ref=shopbycategory"], "blocked")
        self.assertEqual(estados["https://kastking.com/pages/manuals-schematics?ref=top"], "blocked")
        self.assertEqual(estados["https://www.okumabrasil.com.br/assistencia-tecnica"], "unavailable")

    def test_slow_source_does_not_block_other_results(self):
        harness = Harness({MARURI: maruri_html()}, atraso={"https://www.okumabrasil.com.br/assistencia-tecnica": 30})
        with patch.object(tela_os, "PRAZO_TOTAL_BUSCA_VISTA", 1.0):
            inicio = time.monotonic()
            resultados = harness._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400")
            duracao = time.monotonic() - inicio
        harness.liberar.set()

        self.assertLess(duracao, 5.0)
        self.assertTrue(any(item["url"] == MARURI for item in resultados))
        estados = {f["url"]: f["state"] for f in harness._ultima_busca_fontes_consultadas}
        self.assertEqual(estados["https://www.okumabrasil.com.br/assistencia-tecnica"], "timeout")

    def test_repeated_search_uses_cache_without_new_network_calls(self):
        harness = Harness({MARURI: maruri_html()})
        primeira = harness._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400")
        chamadas = len(harness.chamadas)
        segunda = harness._buscar_links_web_diagrama("maruri", "Black Pira BG400")

        self.assertGreater(chamadas, 0)
        self.assertEqual(len(harness.chamadas), chamadas)
        self.assertEqual([i["url"] for i in primeira], [i["url"] for i in segunda])

    def test_web_search_failure_is_not_cached_as_valid_result(self):
        falha = OSError("sem rede")
        harness = Harness({MARURI: maruri_html(), "https://duckduckgo.com/html/?q=x": falha})
        original = harness._buscar_pagina_tecnica

        def buscar(url, timeout):
            if url.startswith("https://duckduckgo.com/"):
                harness.chamadas.append(url)
                raise falha
            return original(url, timeout)

        harness._buscar_pagina_tecnica = buscar
        harness._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400")
        chamadas = len(harness.chamadas)
        harness._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400")

        self.assertGreater(len(harness.chamadas), chamadas)

    def test_blocked_engine_does_not_hide_results_from_working_engine(self):
        pdf = "https://example.org/docs/shimano-stella-4000-xg-parts-manual.pdf"
        bing = f'<html><li class="b_algo"><a href="{pdf}">Shimano Stella 4000 XG parts manual</a></li></html>'
        harness = Harness({"__bing": bing})
        base = harness._buscar_pagina_tecnica

        def buscar(url, timeout):
            if url.startswith("https://duckduckgo.com/"):
                harness.chamadas.append(url)
                raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
            if url.startswith("https://www.bing.com/"):
                harness.chamadas.append(url)
                return bing, "text/html"
            return base(url, timeout)

        harness._buscar_pagina_tecnica = buscar
        harness._baixar_e_extrair_pdf = lambda *a, **k: {
            "status": "text_only", "pages": 1, "text_pages": 1, "parts": [], "manufacturer": "", "model": "",
        }
        resultados = harness._buscar_links_web_diagrama("SHIMANO", "STELLA 4000 XG")

        self.assertIn(pdf, [r["url"] for r in resultados])
        self.assertTrue(all(r["verified"] is False for r in resultados))
        estados = {f["source"]: f["state"] for f in harness._ultima_busca_fontes_consultadas}
        self.assertEqual(estados["DuckDuckGo"], "blocked")
        self.assertEqual(estados["Bing"], "ok")
        self.assertTrue(any("DuckDuckGo bloqueou" in x for x in harness._ultima_busca_limitacoes))

        chamadas = len(harness.chamadas)
        harness._buscar_links_web_diagrama("SHIMANO", "STELLA 4000 XG")
        self.assertGreater(len(harness.chamadas), chamadas)  # bloqueio não foi guardado em cache

    def test_blocked_engine_is_queried_once_and_duplicates_are_merged(self):
        import base64
        alvo = "https://example.org/docs/daiwa-caldia-3000-parts.pdf"
        codificado = "a1" + base64.urlsafe_b64encode(alvo.encode()).decode().rstrip("=")
        bing = (
            f'<a href="https://www.bing.com/ck/a?!&amp;p=x&amp;u={codificado}&amp;ntb=1">Daiwa Caldia 3000 parts</a>'
            f'<a href="{alvo}">Daiwa Caldia 3000 parts</a>'
        )
        harness = Harness()
        base = harness._buscar_pagina_tecnica

        def buscar(url, timeout):
            if url.startswith("https://duckduckgo.com/"):
                harness.chamadas.append(url)
                return "<html>captcha</html>", "text/html"
            if url.startswith("https://www.bing.com/"):
                harness.chamadas.append(url)
                return bing, "text/html"
            return base(url, timeout)

        harness._buscar_pagina_tecnica = buscar
        harness._baixar_e_extrair_pdf = lambda *a, **k: {
            "status": "text_only", "pages": 1, "text_pages": 1, "parts": [], "manufacturer": "", "model": "",
        }
        resultados = harness._buscar_links_web_diagrama("DAIWA", "CALDIA 3000")

        self.assertEqual([r["url"] for r in resultados].count(alvo), 1)
        ddg = [u for u in harness.chamadas if u.startswith("https://duckduckgo.com/")]
        self.assertLess(len(ddg), 10)  # após o bloqueio, as demais consultas do motor são puladas
        for u in harness.chamadas:
            self.assertNotIn("JOAO", u.upper())

    def test_engine_urls_carry_only_manufacturer_and_model(self):
        harness = Harness()
        harness._buscar_links_web_diagrama("KASTKING", "SHARKY 3000")
        for u in harness.chamadas:
            if "bing.com" in u or "reelschematic.com/?s=" in u:
                self.assertTrue(any(t in u.upper() for t in ("SHARKY", "KASTKING")))

    def test_captcha_word_in_asset_name_is_not_a_block(self):
        pagina = "<html><link href='/plugins/image-captcha/style.css'><body>Stella 4000 XG</body></html>"
        h = Harness({"https://www.reelschematic.com/?s=SHIMANO+STELLA+4000+XG": pagina})
        h._buscar_links_web_diagrama("SHIMANO", "STELLA 4000 XG")
        estados = {f["url"]: f["state"] for f in h._ultima_busca_fontes_consultadas}
        self.assertEqual(estados["https://www.reelschematic.com/?s=SHIMANO+STELLA+4000+XG"], "ok")

    def test_number_only_match_and_search_page_query_do_not_make_links_relevant(self):
        busca = "https://www.reelschematic.com/?s=DAIWA+CALDIA+3000"
        pagina = (
            '<a href="/trolling-motor-schematics/">Trolling motor schematics</a>'
            '<a href="https://cdn.example.com/Kapstan_Elite_SP_3000-8000.pdf">Kapstan 3000</a>'
            '<a href="https://cdn.example.com/Daiwa_Caldia_3000_parts.pdf">Daiwa Caldia 3000 parts</a>'
        )
        h = Harness({busca: pagina})
        h._baixar_e_extrair_pdf = lambda *a, **k: {
            "status": "text_only", "pages": 1, "text_pages": 1, "parts": [], "manufacturer": "", "model": "",
        }
        urls = [r["url"] for r in h._buscar_links_web_diagrama("DAIWA", "CALDIA 3000")]
        self.assertIn("https://cdn.example.com/Daiwa_Caldia_3000_parts.pdf", urls)
        self.assertFalse(any("trolling-motor" in u or "Kapstan" in u for u in urls))

    def test_cancellation_returns_quickly_without_results(self):
        harness = Harness({MARURI: maruri_html()}, atraso={MARURI: 30})
        cancelamento = threading.Event()
        threading.Timer(0.3, cancelamento.set).start()
        inicio = time.monotonic()
        resultados = harness._buscar_links_web_diagrama("MARURI", "BLACK PIRA BG 400", cancelamento)
        harness.liberar.set()

        self.assertEqual(resultados, [])
        self.assertLess(time.monotonic() - inicio, 5.0)


if __name__ == "__main__":
    unittest.main()

