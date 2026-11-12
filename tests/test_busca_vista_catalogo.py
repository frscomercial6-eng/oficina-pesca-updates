import threading
from types import SimpleNamespace

import pytest

import busca_vista_catalogo as cat
import busca_vista_fontes as fontes
import tela_os

F = tela_os.FrmOS

PDF = "https://www.reelschematic.com/wp-content/uploads/schematics/Shimano/Curado/"


def _viewer(nome, pdf=None):
    from urllib.parse import quote
    pdf = pdf or f"{PDF}{nome}.pdf"
    return f'<a href="https://www.reelschematic.com/schematic-viewer/?rs_doc={quote(pdf, safe="")}&#038;rs_model={quote(nome)}">{nome}</a>'


NOMES = [
    "Shiimano Curado CUMGL151XG", "SHIMANO BANTAM CURADO 200(91-06)", "Shimano Curado 17CU200",
    "Shimano Curado 17CU200XG", "Shimano Curado 12CU200G5", "Shimano Curado 17CU2001", "Shimano Curado 18CUDC150",
    "Shimano Curado 09CU300E",
]
HTML_FAMILIA = "".join(_viewer(n) + _viewer(n) for n in NOMES)  # cada link aparece duas vezes (imagem + texto)
HTML_MARCA = '<a href="https://www.reelschematic.com/reel-schematics/shimano-reel-schematics/shimano-curado-schematics/">c</a>' \
             '<a href="https://www.reelschematic.com/reel-schematics/shimano-reel-schematics/shimano-stella-schematics/">s</a>' \
             'schematic'


@pytest.fixture(autouse=True)
def _limpar():
    cat.limpar_cache_catalogo()
    yield
    cat.limpar_cache_catalogo()


def _fetch(urls):
    def buscar(url):
        urls.append(url)
        if url.endswith("shimano-reel-schematics/"):
            return HTML_MARCA
        if url.endswith("shimano-curado-schematics/"):
            return HTML_FAMILIA
        raise OSError("sem rota")
    return buscar


def test_parse_remove_duplicatas_e_hosts_invalidos():
    html = HTML_FAMILIA + _viewer("Malicioso", "https://evil.example/x.pdf")
    variantes = cat.parse_variantes_reelschematic(html, "https://www.reelschematic.com/x/")
    assert len(variantes) == len(NOMES)
    assert all(v["pdf_url"].startswith("https://www.reelschematic.com/wp-content/uploads/") for v in variantes)
    assert {v["codigo"] for v in variantes} >= {"CUMGL151XG", "17CU200"}


def test_familia_com_numero_filtra_variacoes_200():
    variantes = cat.parse_variantes_reelschematic(HTML_FAMILIA, "https://www.reelschematic.com/x/")
    nomes = {v["nome"] for v in cat.filtrar_variantes(variantes, "CURADO 200")}
    assert nomes == {"SHIMANO BANTAM CURADO 200(91-06)", "Shimano Curado 17CU200", "Shimano Curado 17CU200XG", "Shimano Curado 12CU200G5"}
    assert not cat.consulta_eh_exata("CURADO 200")


def test_familia_sem_numero_lista_todas():
    variantes = cat.parse_variantes_reelschematic(HTML_FAMILIA, "https://www.reelschematic.com/x/")
    assert len(cat.filtrar_variantes(variantes, "CURADO")) == len(NOMES)


def test_modelo_exato_e_unico_mesmo_com_codigos_parecidos():
    variantes = cat.parse_variantes_reelschematic(HTML_FAMILIA, "https://www.reelschematic.com/x/")
    assert cat.consulta_eh_exata("CURADO CUMGL151XG")
    achados = cat.filtrar_variantes(variantes, "CURADO CUMGL151XG")
    assert [v["codigo"] for v in achados] == ["CUMGL151XG"]
    # GL1 XG é parcial: casa o código real, sem inventar outros
    assert [v["codigo"] for v in cat.filtrar_variantes(variantes, "CURADO GL1 XG")] == ["CUMGL151XG"]


def test_descoberta_envia_apenas_marca_e_familia_e_cacheia_resultado_completo():
    urls = []
    variantes, estado, _ = cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO 200", _fetch(urls))
    assert estado == "ok" and len(variantes) == 4
    assert all("200" not in u and "joao" not in u.lower() for u in urls)
    assert all(u.startswith("https://www.reelschematic.com/reel-schematics/shimano") for u in urls)
    antes = len(urls)
    cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO CUMGL151XG", _fetch(urls))
    assert len(urls) == antes  # mesma família: servido pelo cache


def test_bloqueio_nao_vira_ausencia_nem_entra_no_cache():
    def bloqueado(url):
        raise PermissionError("HTTP 403")
    variantes, estado, msg = cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO 200", bloqueado)
    assert variantes == [] and estado == "incompleto" and "indispon" in msg
    urls = []
    _, estado2, _ = cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO 200", _fetch(urls))
    assert estado2 == "ok" and urls  # não reutilizou a falha


def test_familia_inexistente_e_sem_resultado():
    variantes, estado, _ = cat.descobrir_variantes_reelschematic("SHIMANO", "ZZZNOME 200", _fetch([]))
    assert variantes == [] and estado == "sem_resultado"


def test_mesmo_codigo_com_grafias_diferentes_vira_uma_variacao():
    def buscar(url):
        if url.endswith("shimano-reel-schematics/"):
            return HTML_MARCA
        return _viewer("Shiimano Curado CUMGL151XG") + _viewer("Shimano Curado CUMGL151XG", PDF + "outro.pdf")
    variantes, estado, _ = cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO CUMGL151XG", buscar)
    assert estado == "ok" and [v["nome"] for v in variantes] == ["Shimano Curado CUMGL151XG"]


def test_mesmo_ano_nao_mescla_modelos_diferentes():
    def buscar(url):
        if url.endswith("shimano-reel-schematics/"):
            return HTML_MARCA
        return (_viewer("Shimano Curado 100 2015") + _viewer("Shimano Curado 200 2015"))
    variantes, estado, _ = cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO", buscar)
    assert estado == "ok"
    assert {v["nome"] for v in variantes} == {"Shimano Curado 100 2015", "Shimano Curado 200 2015"}


def test_cache_catalogo_expira_e_atualiza_fontes(monkeypatch):
    momento = [100.0]
    monkeypatch.setattr(cat, "time", SimpleNamespace(monotonic=lambda: momento[0]))
    urls = []
    cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO", _fetch(urls))
    assert len(urls) == 2
    cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO", _fetch(urls))
    assert len(urls) == 2
    momento[0] += 301
    cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO", _fetch(urls))
    assert len(urls) == 4


def test_cancelamento_interrompe_antes_da_rede():
    evento = threading.Event()
    evento.set()
    urls = []
    _, estado, _ = cat.descobrir_variantes_reelschematic("SHIMANO", "CURADO 200", _fetch(urls), evento)
    assert estado == "cancelado" and urls == []


def test_pdfs_de_outras_fontes_viram_candidatos_identificados():
    links = [{"url": "https://cdn.shopify.com/files/KastKing_Sharky_III_3000_Manual.pdf", "source": "KastKing"},
             {"url": "https://example.com/pagina", "source": "X"}]
    itens = cat.variantes_de_pdfs_genericos(links, "KASTKING", "SHARKY 3000")
    assert len(itens) == 1 and itens[0]["verificado"] is False and itens[0]["fonte"] == "KastKing"


def test_detecta_texto_de_pdf_ilegivel():
    ruim = "\n".join(["$BTU$POUSPM4QBDFS", "$MJDL4QSJOH", "4UBS%SBH4QBDFS", "03JOH", "#BMM#FBSJOH", "8BTIFS%SBH",
                      "*EMF(FBS1JO", "$MJDL1JO", "#FBSJOH3FUBJOFS", "4DSFX"])
    bom = "\n".join(f"{i}  6{i:03d}  Ball Bearing {i}" for i in range(12))
    assert tela_os._texto_pdf_ilegivel(ruim)
    assert not tela_os._texto_pdf_ilegivel(bom)


def _host_fake(abertos, exibidos):
    h = SimpleNamespace(_ultima_busca_limitacoes=[], status=[])
    h._equipamento_seguro_para_consulta = lambda termo: F._equipamento_seguro_para_consulta(h, termo)
    h._extrair_fabricante_modelo = lambda t: F._extrair_fabricante_modelo(h, t)
    h._atualizar_status_busca_diagrama = lambda texto, cor="": h.status.append(texto)
    h._abrir_visualizador_pdf_busca_vista = lambda c: abertos.append(c)
    h._exibir_catalogo_modelos = lambda termo, fab, cands, links: exibidos.append(cands)
    return h


def _catalogo(modelo):
    variantes = cat.parse_variantes_reelschematic(HTML_FAMILIA, "https://www.reelschematic.com/x/", "SHIMANO", "CURADO")
    return cat.filtrar_variantes(variantes, modelo), "ok", ""


def test_modelo_exato_unico_abre_direto_no_visualizador():
    abertos, exibidos = [], []
    h = _host_fake(abertos, exibidos)
    assert F._apresentar_catalogo_busca_vista(h, "SHIMANO CURADO CUMGL151XG", [], _catalogo("CURADO CUMGL151XG"))
    assert len(abertos) == 1 and abertos[0]["codigo"] == "CUMGL151XG" and not exibidos


def test_familia_com_varias_variacoes_exige_selecao():
    abertos, exibidos = [], []
    h = _host_fake(abertos, exibidos)
    assert F._apresentar_catalogo_busca_vista(h, "SHIMANO CURADO 200", [], _catalogo("CURADO 200"))
    assert not abertos and len(exibidos[0]) == 4


def test_sem_documento_devolve_false_para_informar_ausencia():
    abertos, exibidos = [], []
    h = _host_fake(abertos, exibidos)
    assert F._apresentar_catalogo_busca_vista(h, "SHIMANO CURADO 999", [], _catalogo("CURADO 999")) is False
    assert not abertos and not exibidos


NOMES_PREFIXO = ["Shimano Curado 12CU200G5", "Shimano Curado 12CU200G6", "Shimano Curado 14CU200IHG",
                 "Shimano Curado 17CU200", "Shimano Curado 12CU200G60", "Shimano Curado 18CUDC150",
                 "Shimano Calcutta 12CT200G6"]


def _prefixados(nomes=NOMES_PREFIXO):
    html = "".join(_viewer(n) for n in nomes)
    base = cat.parse_variantes_reelschematic(html, "https://www.reelschematic.com/x/", "SHIMANO", "CURADO")
    for v in base:
        if "Calcutta" in v["nome"]:
            v["familia"] = "CALCUTTA"
    return base


def test_200_g6_encontra_documento_com_prefixo_cu_sem_usuario_digitar():
    achados = cat.filtrar_variantes(_prefixados(), "CURADO 200 G6")
    assert [v["codigo"] for v in achados] == ["12CU200G6"]  # G5, G60 e Calcutta ficam de fora
    assert cat.correspondencia_inequivoca(achados, "CURADO 200 G6")


def test_prefixo_digitado_pelo_usuario_tambem_funciona():
    assert [v["codigo"] for v in cat.filtrar_variantes(_prefixados(), "CURADO CU 200 G6")] == ["12CU200G6"]


def test_duvida_entre_variacoes_nao_abre_direto():
    achados = cat.filtrar_variantes(_prefixados(), "CURADO 200")
    assert len(achados) > 1 and not cat.correspondencia_inequivoca(achados, "CURADO 200")
    assert not cat.correspondencia_inequivoca(achados[:1], "CURADO 200")


def test_variantes_hg_dc_preservadas():
    assert [v["codigo"] for v in cat.filtrar_variantes(_prefixados(), "CURADO 200 HG")] == ["14CU200IHG"]
    assert [v["codigo"] for v in cat.filtrar_variantes(_prefixados(), "CURADO DC 150")] == ["18CUDC150"]


def test_identificadores_tecnicos_so_para_familias_comprovadas():
    assert cat.identificadores_tecnicos("SHIMANO", "CURADO 200 G6") == ["CU200G6", "CU-200 G6"]
    assert cat.identificadores_tecnicos("SHIMANO", "CURADO CU 200 G6") == ["CU200G6", "CU-200 G6"]
    assert cat.identificadores_tecnicos("SHIMANO", "STELLA 4000 XG") == []
    assert cat.identificadores_tecnicos("DAIWA", "CALDIA 3000") == []


def _manual(nome, numero, host="www.marinefishing.com.br"):
    return (f'<a class="download-link" href="https://{host}/manuais/download/3/{numero}">'
            f'<div class="col-7 text1">{nome}.pdf</div></a>')


HTML_MARINE = "".join((
    _manual("CARRETILHA VENATOR AC SHI-SHIL", 10),
    _manual("CARRETILHA VENATOR AC SHIL 2023", 11),
    _manual("CARRETILHA BRISA BR-3000 Hi", 12),
    _manual("CARRETILHA BRISA BR-3000 HiL", 13),
    _manual("MOLINETE BRISA 3000", 14),
    _manual("CARRETILHA BRISA BR-3000 Hi", 12),
    _manual("CARRETILHA VENATOR MALICIOSO", 15, "evil.example"),
))


def test_catalogo_marine_preserva_documentos_e_filtra_categoria_e_familia():
    docs = cat.parse_manuais_marine(HTML_MARINE)
    assert len(docs) == 5
    carretilhas = cat.filtrar_manuais_marine(docs, "", "CARRETILHA")
    assert len(carretilhas) == 4
    assert len(cat.filtrar_manuais_marine(docs, "VENATOR")) == 2
    brisa = cat.filtrar_manuais_marine(docs, "BRISA", "CARRETILHA")
    assert [d["nome"] for d in brisa] == [
        "CARRETILHA BRISA BR-3000 Hi", "CARRETILHA BRISA BR-3000 HiL"
    ]
    assert len(cat.filtrar_manuais_marine(docs, "BRISA 3000", "CARRETILHA")) == 2
    assert len(cat.filtrar_manuais_marine(docs, "BRISA BR-3000 HiL", "CARRETILHA")) == 1
    assert not cat.filtrar_manuais_marine(docs, "BRISA 3000 JOAO")


def _executar_marine(termo, pagina=HTML_MARINE, falha=False, cancelado=False):
    import queue
    h = _host_fake([], [])
    h._callbacks_busca_vista = queue.Queue()
    h.urls = []
    h.conclusoes = []
    h._ultima_busca_limitacoes = []

    def buscar(url, timeout):
        h.urls.append(url)
        if falha:
            raise TimeoutError("tempo excedido")
        return pagina, "text/html"

    h._buscar_pagina_tecnica = buscar
    h._concluir_busca_vista = lambda *a, **kw: h.conclusoes.append((a, kw))
    evento = threading.Event()
    if cancelado:
        evento.set()
    F._executar_busca_filtrada_bg(h, termo, evento)
    h._callbacks_busca_vista.get(timeout=2)()
    return h


@pytest.mark.parametrize("consulta,quantidade", [
    ("carretilha Marine Sports", 4),
    ("Marine Sports Venator", 2),
    ("Marine Sports Brisa", 3),
])
def test_fluxo_marine_consulta_pagina_fixa_e_apresenta_modelos(consulta, quantidade):
    h = _executar_marine(consulta)
    assert h.urls == [cat.MANUAIS_MARINE_URL]
    args, kwargs = h.conclusoes[0]
    candidatos = kwargs["catalogo"][0]
    assert len(candidatos) == quantidade
    abertos, exibidos = [], []
    tela = _host_fake(abertos, exibidos)
    assert F._apresentar_catalogo_busca_vista(tela, consulta, [], kwargs["catalogo"])
    assert not abertos and len(exibidos[0]) == quantidade


def test_marine_nao_transmite_texto_livre_e_nao_associa_modelo_ambiguo():
    h = _executar_marine("Marine Sports Venator Joao 11999998888")
    assert h.urls == [cat.MANUAIS_MARINE_URL]
    assert "inválida" in h.conclusoes[0][1]["mensagem"]


def test_modelo_exato_aparece_antes_de_outras_variantes():
    docs = cat.parse_manuais_marine(
        _manual("CARRETILHA VENATOR AC SHI-SHIL", 10)
        + _manual("CARRETILHA VENATOR AC", 11)
    )
    achados = cat.filtrar_manuais_marine(docs, "VENATOR AC")
    assert [item["nome"] for item in achados] == [
        "CARRETILHA VENATOR AC", "CARRETILHA VENATOR AC SHI-SHIL"
    ]


def test_catalogo_marine_indisponivel_nao_envia_modelo_nao_validado():
    h = _executar_marine("Marine Sports Venator", falha=True)
    assert h.urls == [cat.MANUAIS_MARINE_URL]
    assert "indisponível" in h.conclusoes[0][1]["mensagem"]


@pytest.mark.parametrize("falha", [True, False])
def test_catalogo_sem_modelo_prossegue_com_fontes_para_modelo_ja_validado(falha):
    import queue
    h = _host_fake([], [])
    h._callbacks_busca_vista = queue.Queue()
    h._ultima_busca_limitacoes = []
    h.conclusoes, h.consultas = [], []

    def falhar(url, timeout):
        assert url == cat.MANUAIS_MARINE_URL
        if falha:
            raise TimeoutError("tempo excedido")
        return HTML_MARINE, "text/html"

    h._buscar_pagina_tecnica = falhar
    h._descobrir_catalogo_busca_vista = lambda fab, modelo, cancel: ([], "sem_resultado", "")
    h._buscar_links_web_diagrama = lambda fab, modelo, cancel: h.consultas.append((fab, modelo)) or []
    h._concluir_busca_vista = lambda *a, **kw: h.conclusoes.append((a, kw))
    F._executar_busca_filtrada_bg(h, "Marine Sports BG 400 - cliente Joao", threading.Event())
    h._callbacks_busca_vista.get(timeout=2)()
    assert h.consultas == [("MARINE SPORTS", "BG 400")]
    assert any("indisponível" in item for item in h._ultima_busca_limitacoes) is falha
    assert h.conclusoes[0][1]["catalogo"][1] == "sem_resultado"


def test_marine_cancelado_nao_consulta_nenhuma_fonte():
    h = _executar_marine("Marine Sports Brisa", cancelado=True)
    assert h.urls == []
    assert h.conclusoes[0][0][2] is True


def test_fabricante_desconhecido_continua_bloqueado_sem_rede():
    h = _executar_marine("Fabricante Inexistente 200")
    assert not h.urls
    assert "identificar fabricante" in h.conclusoes[0][1]["mensagem"]


def test_modelo_nao_cadastrado_descoberto_localmente_sem_transmitir_texto_da_os():
    import queue
    from unittest.mock import patch
    fontes.limpar_cache_fontes()
    h = _host_fake([], [])
    h._callbacks_busca_vista = queue.Queue()
    h.urls, h.conclusoes = [], []
    def buscar(url, timeout):
        h.urls.append(url)
        return '<a href="https://site.test/CUSTOM-NOVO.pdf">CUSTOM NOVO</a>', "text/html"
    h._buscar_pagina_tecnica = buscar
    h._concluir_busca_vista = lambda *a, **kw: h.conclusoes.append((a, kw))
    with patch.dict(fontes.FONTES_INICIAIS, {"DAIWA": (("Fonte", "https://site.test/manual"),)}):
        F._executar_busca_filtrada_bg(h, "Daiwa Custom Novo", threading.Event())
        h._callbacks_busca_vista.get(timeout=2)()
        catalogo = h.conclusoes[0][1]["catalogo"]
        assert catalogo[0][0]["validado_no_catalogo"]
        assert F._apresentar_catalogo_busca_vista(h, "Daiwa Custom Novo", [], catalogo)
        h.conclusoes.clear()
        F._executar_busca_filtrada_bg(h, "Daiwa Custom Novo Joao 11999998888", threading.Event())
        h._callbacks_busca_vista.get(timeout=2)()
        assert "não identificado" in h.conclusoes[0][1]["mensagem"]
    assert h.urls == ["https://site.test/manual"]
    fontes.limpar_cache_fontes()
