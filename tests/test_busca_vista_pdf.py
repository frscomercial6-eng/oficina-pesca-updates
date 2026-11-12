from __future__ import annotations

import ast
import io
import queue
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from reportlab.pdfgen import canvas

import tela_os
import busca_vista_pdf
import busca_vista_visualizador as visualizador


def test_analise_pdf_em_executavel_usa_worker_sem_abrir_login(monkeypatch):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=(120, 240))
    pdf.drawString(10, 100, "Technical diagram")
    pdf.showPage()
    pdf.save()
    launcher = Path(__file__).resolve().parents[1] / "login.py"
    original = subprocess.Popen

    def executar_worker(comando, **kwargs):
        assert comando[1] == "--ofp-busca-vista-pdf-worker"
        script = (
            "import runpy,sys; sys.frozen=True; "
            "sys.argv=[sys.argv[1]]+sys.argv[2:]; "
            "runpy.run_path(sys.argv[0],run_name='__main__')"
        )
        return original([sys.executable, "-c", script, str(launcher), *comando[1:]], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", executar_worker)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    resultado = busca_vista_pdf.analisar_em_processo(
        buffer.getvalue(), "https://example.test/diagrama.pdf", "Shimano", "Curado", timeout=20
    )
    assert resultado["status"] == "text_only"
    assert resultado["pages"] == 1


class PdfResponse:
    def __init__(self, content: bytes):
        self._content = io.BytesIO(content)
        self.headers = {
            "Content-Type": "application/pdf",
            "Content-Length": str(len(content)),
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._content.read(size)

    def geturl(self) -> str:
        return "https://example.test/manual.pdf"


def test_download_marine_usa_sessao_publica_e_valida_pdf():
    pagina = b"""<script>data: { csrf:'token_publico', 'csrf_token_marine':'token_sessao' }</script>"""
    respostas = [
        PdfResponse(pagina),
        PdfResponse(b'{"code":200,"redirect":"https://www.marinefishing.com.br/manuais/download-processa"}'),
        PdfResponse(b"%PDF-1.5\nconteudo"),
    ]
    chamadas = []

    class Opener:
        def open(self, request, timeout):
            chamadas.append((request.full_url, request.data, timeout))
            return respostas.pop(0)

    with patch.object(visualizador, "build_opener", return_value=Opener()):
        corpo = visualizador.baixar_pdf_marine(
            "https://www.marinefishing.com.br/manuais/download/3/489", threading.Event(), timeout=3
        )
    assert corpo.startswith(b"%PDF-")
    assert [c[0] for c in chamadas] == [
        visualizador.MARINE_MANUAIS,
        "https://www.marinefishing.com.br/manuais/download/3/489",
        "https://www.marinefishing.com.br/manuais/download-processa",
    ]
    assert b"cliente" not in chamadas[1][1].lower()


def test_download_marine_nao_aceita_pagina_de_erro_nem_destino_externo():
    pagina = b"""data: { csrf:'a', 'csrf_token_marine':'b' }"""
    class Opener:
        def __init__(self, redirect):
            self.respostas = [PdfResponse(pagina), PdfResponse(redirect), PdfResponse(b"<html>oops</html>")]
        def open(self, request, timeout):
            return self.respostas.pop(0)

    url = "https://www.marinefishing.com.br/manuais/download/3/489"
    for resposta in (
        b'{"code":200,"redirect":"https://www.marinefishing.com.br/manuais/download-processa"}',
        b'{"code":200,"redirect":"https://evil.example/arquivo.pdf"}',
    ):
        with patch.object(visualizador, "build_opener", return_value=Opener(resposta)):
            try:
                visualizador.baixar_pdf_marine(url, threading.Event())
            except ValueError:
                pass
            else:
                raise AssertionError("Resposta inválida foi aceita")


def test_tabela_em_duas_colunas_preserva_associacao():
    texto = (
        " 1       6J187802       DRAG KNOB                          47      6H619301      MAGNET ASSEMBLY\n"
        "105      21056602       PINION BEARING FIXED  BUSHING      700     27000420      DRIVE GEAR\n"
        "                                  4147                       Brake Collar                 3208\n"
        "            C-10  PARTS LIST\n"
    )
    pecas = PdfSearchHarness()._extrair_pecas_pdf_texto(texto, 3)
    assert [(p["posicao"], p["codigo"], p["descricao"], p["pagina"]) for p in pecas] == [
        ("1", "6J187802", "DRAG KNOB", 3),
        ("47", "6H619301", "MAGNET ASSEMBLY", 3),
        ("105", "21056602", "PINION BEARING FIXED BUSHING", 3),
        ("700", "27000420", "DRIVE GEAR", 3),
    ]


def test_visualizador_valida_imagem_antes_de_apresentar():
    from PIL import Image
    imagem = io.BytesIO()
    Image.new("RGB", (20, 10), "white").save(imagem, "PNG")

    def carregar(corpo):
        h = SimpleNamespace(
            candidato={"pdf_url": "https://example.test/diagrama.png", "tipo_documento": "imagem"},
            _baixar=lambda url, cancel: corpo, _cancel=threading.Event(), _fila=queue.Queue(),
            _lock_pdf=threading.Lock(), _imagem=None, _pdf=None, _analisar=None,
        )
        visualizador.VisualizadorPdfBuscaVista._carregar(h)
        return h._fila.get_nowait()

    assert carregar(imagem.getvalue()) == ("aberto", 1, 20.0)
    assert carregar(b"<html>erro</html>")[0] == "erro"


def test_rotacao_pdf_preserva_pagina_zoom_e_orientacao_original():
    pedidos = []
    janela = SimpleNamespace(
        _paginas=2, _fechada=False, _pagina=1, _zoom=1.5, _rotacao=0,
        _ajustar_largura=True,
    )
    janela._pedir_render = lambda: pedidos.append((janela._pagina, janela._zoom, janela._rotacao))
    for angulo in (90, 90, -90, -90, -90):
        visualizador.VisualizadorPdfBuscaVista.girar(janela, angulo)
    assert [item[2] for item in pedidos] == [90, 180, 90, 0, 270]
    visualizador.VisualizadorPdfBuscaVista.restaurar_orientacao(janela)
    assert pedidos[-1] == (1, 1.5, 0)
    assert all(pagina == 1 and zoom == 1.5 for pagina, zoom, _ in pedidos)
    assert not janela._ajustar_largura


def test_render_pdf_gira_retrato_paisagem_e_respeita_orientacao_original():
    import pypdfium2 as pdfium
    from pypdf import PdfReader, PdfWriter

    arquivo = io.BytesIO()
    pdf = canvas.Canvas(arquivo, pagesize=(120, 240))
    pdf.setFillColorRGB(1, 0, 0)
    pdf.rect(10, 190, 20, 20, fill=1, stroke=0)
    pdf.showPage()
    pdf.setPageSize((240, 120))
    pdf.showPage()
    pdf.save()
    original = arquivo.getvalue()
    documento = pdfium.PdfDocument(original)

    def render(doc, pagina, rotacao, largura=None):
        janela = SimpleNamespace(
            _lock_pdf=threading.Lock(), _cancel=threading.Event(), _geracao=1,
            _pdf=doc, _imagem=None, _fila=queue.Queue(),
        )
        visualizador.VisualizadorPdfBuscaVista._renderizar(janela, pagina, 1.0, 1, rotacao, largura)
        mensagem = janela._fila.get_nowait()
        assert mensagem[0] == "imagem", mensagem
        return mensagem

    retrato = render(documento, 0, 0)
    direita = render(documento, 0, 90)
    esquerda = render(documento, 0, 270)
    paisagem = render(documento, 1, 0)
    assert retrato[3] == (120, 240)
    assert direita[3] == (240, 120) and esquerda[3] == (240, 120)
    assert paisagem[3] == (240, 120) and render(documento, 1, 90)[3] == (120, 240)
    for mensagem, ponto in ((retrato, (20, 40)), (direita, (199, 20)), (esquerda, (40, 99))):
        pixel = mensagem[4][0][2].convert("RGB").getpixel(ponto)
        assert pixel[0] > 200 and pixel[1] < 50 and pixel[2] < 50
    ajuste = render(documento, 0, 90, 360)
    assert ajuste[5] == 1.5 and ajuste[3] == (360, 180)
    documento.close()
    assert arquivo.getvalue() == original

    leitor = PdfReader(io.BytesIO(original))
    escritor = PdfWriter()
    leitor.pages[0].rotate(90)
    escritor.add_page(leitor.pages[0])
    saida = io.BytesIO()
    escritor.write(saida)
    documento = pdfium.PdfDocument(saida.getvalue())
    assert render(documento, 0, 0)[3] == (240, 120)
    assert render(documento, 0, 90)[3] == (120, 240)
    documento.close()


def test_rotacao_da_imagem_preserva_proporcao_e_posicao():
    from PIL import Image
    imagem = Image.new("RGB", (20, 10), "white")
    imagem.putpixel((2, 3), (255, 0, 0))
    janela = SimpleNamespace(
        _lock_pdf=threading.Lock(), _cancel=threading.Event(), _geracao=1,
        _pdf=None, _imagem=imagem, _fila=queue.Queue(),
    )
    visualizador.VisualizadorPdfBuscaVista._renderizar(janela, 0, 1, 1, 90, None)
    mensagem = janela._fila.get_nowait()
    assert mensagem[0] == "imagem" and mensagem[3] == (10, 20)
    assert mensagem[4][0][2].getpixel((6, 2)) == (255, 0, 0)
    assert imagem.getpixel((2, 3)) == (255, 0, 0)


def test_analise_isolada_preserva_resultado_e_associacoes():
    corpo = TestBuscaVistaPdf().make_pdf()
    direto = busca_vista_pdf.analisar_pdf_bytes(corpo, "https://example.test/a.pdf", "SHIMANO", "FX 2500")
    isolado = busca_vista_pdf.analisar_em_processo(
        corpo, "https://example.test/a.pdf", "SHIMANO", "FX 2500", threading.Event()
    )
    assert isolado == direto
    assert isolado["parts"][0]["pagina"] == 2


def test_cancelar_analise_encerra_e_recolhe_processo():
    import subprocess
    cancelamento = threading.Event()

    class Processo:
        returncode = None
        encerrado = False
        recolhido = False
        def communicate(self, input=None, timeout=None):
            if timeout is None:
                self.recolhido = True
                return b"", b""
            cancelamento.set()
            raise subprocess.TimeoutExpired("worker", timeout)
        def poll(self):
            return 0 if self.encerrado else None
        def kill(self):
            self.encerrado = True

    processo = Processo()
    with patch.object(busca_vista_pdf.subprocess, "Popen", return_value=processo):
        try:
            busca_vista_pdf.analisar_em_processo(b"%PDF", "", "", "", cancelamento)
        except InterruptedError:
            pass
        else:
            raise AssertionError("Cancelamento não interrompeu a análise")
    assert processo.encerrado and processo.recolhido


def test_cancelar_analise_encerra_processo_real():
    import subprocess
    cancelamento = threading.Event()
    iniciado = threading.Event()
    processos, erros = [], []
    popen = subprocess.Popen

    def iniciar(*args, **kwargs):
        processo = popen(*args, **kwargs)
        processos.append(processo)
        iniciado.set()
        return processo

    def executar():
        try:
            busca_vista_pdf.analisar_em_processo(
                TestBuscaVistaPdf().make_pdf(), "https://example.test/a.pdf", "", "", cancelamento,
            )
        except InterruptedError:
            erros.append("cancelado")

    with patch.object(busca_vista_pdf.subprocess, "Popen", side_effect=iniciar):
        thread = threading.Thread(target=executar)
        thread.start()
        assert iniciado.wait(5)
        cancelamento.set()
        thread.join(5)
    assert not thread.is_alive() and erros == ["cancelado"]
    assert processos[0].poll() is not None


def test_destruicao_do_pai_encerra_o_visualizador():
    cancelamento = threading.Event()
    encerramentos = []
    objeto = SimpleNamespace(
        _fechada=False, _cancel=cancelamento, _cancel_defeitos=threading.Event(), _cancel_google=None,
        _render_pool=SimpleNamespace(shutdown=lambda **kw: encerramentos.append(kw)),
        _liberar_pdf=lambda: None,
    )
    objeto._encerrar_trabalho = lambda: visualizador.VisualizadorPdfBuscaVista._encerrar_trabalho(objeto)
    visualizador.VisualizadorPdfBuscaVista._ao_destruir(objeto, SimpleNamespace(widget=object()))
    assert not cancelamento.is_set()
    visualizador.VisualizadorPdfBuscaVista._ao_destruir(objeto, SimpleNamespace(widget=objeto))
    visualizador.VisualizadorPdfBuscaVista._ao_destruir(objeto, SimpleNamespace(widget=objeto))
    assert cancelamento.is_set() and len(encerramentos) == 1


def test_montagem_progressiva_descarta_paginas_obsoletas():
    from PIL import Image, ImageTk
    tarefas, desenhos = [], []
    canvas_fake = SimpleNamespace(
        delete=lambda *a: desenhos.clear(),
        configure=lambda **kw: None,
        yview_moveto=lambda _: None,
        create_image=lambda x, y, **kw: desenhos.append((x, y, kw["image"])),
    )
    objeto = SimpleNamespace(
        _geracao=1, _pagina=0, _fechada=False, _foto=None, canvas=canvas_fake,
        after=lambda _, callback: tarefas.append(callback),
    )
    imagem = Image.new("RGB", (4, 4), "white")
    blocos = [(i, 0, imagem) for i in range(12)]
    with patch.object(ImageTk, "PhotoImage", side_effect=lambda image, **kw: object()):
        visualizador.VisualizadorPdfBuscaVista._mostrar_imagem(objeto, 1, 0, (12, 4), blocos)
        assert len(desenhos) == 8 and objeto._foto is None
        objeto._geracao = 2
        tarefas.pop(0)()
        assert len(desenhos) == 8 and objeto._foto is None
        visualizador.VisualizadorPdfBuscaVista._mostrar_imagem(objeto, 2, 0, (12, 4), blocos)
        tarefas.pop(0)()
    assert len(desenhos) == 12 and len(objeto._foto) == 12
    assert [linha[0] for linha in desenhos] == list(range(12))


class PdfSearchHarness:
    _normalizar_termo_tecnico = tela_os.FrmOS._normalizar_termo_tecnico
    _extrair_pecas_pdf_texto = tela_os.FrmOS._extrair_pecas_pdf_texto
    _baixar_e_extrair_pdf = tela_os.FrmOS._baixar_e_extrair_pdf
    _analisar_pdf_bytes = tela_os.FrmOS._analisar_pdf_bytes
    _extrair_pecas_pagina_tecnica = tela_os.FrmOS._extrair_pecas_pagina_tecnica


class SearchButton:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        self.text = kwargs.get("text", self.text)


class SearchEntry:
    def get(self):
        return "SHIMANO FX 2500"


class SearchController:
    _buscar_vista_equipamento = tela_os.FrmOS.buscar_vista_equipamento

    def __init__(self):
        self._busca_vista_em_andamento = False
        self._busca_vista_cancelamento = None
        self._ultima_busca_limitacoes = []
        self.btn_buscar_vista = SearchButton()
        self.txt_equip = SearchEntry()
        self.status = ""

    def _atualizar_status_busca_diagrama(self, texto, cor=None):
        self.status = texto

    def _executar_busca_filtrada_bg(self, _termo, _cancelamento):
        raise AssertionError("A thread simulada não deve ser executada neste teste.")


class BackgroundSearchHarness:
    _executar_busca_filtrada_bg = tela_os.FrmOS._executar_busca_filtrada_bg
    _equipamento_seguro_para_consulta = tela_os.FrmOS._equipamento_seguro_para_consulta

    def __init__(self):
        self._callbacks_busca_vista = queue.Queue()
        self.completed_on = None

    def _extrair_fabricante_modelo(self, _termo):
        return "SHIMANO", "FX 2500"

    def _buscar_links_web_diagrama(self, _fabricante, _modelo, _cancelamento):
        return [{"url": "https://example.test/manual.pdf"}]

    def _descobrir_catalogo_busca_vista(self, _fabricante, _modelo, _cancelamento):
        return [], "sem_resultado", ""

    def _concluir_busca_vista(self, _termo, _results, _cancelled, _error=False, catalogo=None):
        self.completed_on = threading.current_thread()


class FakeThread:
    started = []

    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self):
        self.started.append(self)


class FakeWidget:
    def __init__(self, _parent=None, **kwargs):
        self.kwargs = kwargs
        self.text = kwargs.get("text", "")
        self.bindings = {}
        self.destroyed = False

    def pack(self, **_kwargs):
        return None

    def bind(self, event, callback):
        self.bindings[event] = callback

    def title(self, _text):
        return None

    def geometry(self, _geometry):
        return None

    def configure(self, **_kwargs):
        return None

    def grab_set(self):
        return None

    def focus_force(self):
        return None

    def lift(self):
        return None

    def destroy(self):
        self.destroyed = True


class ResultsWindowHarness:
    _exibir_janela_diagramas_multiplas_escolhas = (
        tela_os.FrmOS._exibir_janela_diagramas_multiplas_escolhas
    )
    _abrir_url_busca_vista = tela_os.FrmOS._abrir_url_busca_vista
    _extrair_fabricante_modelo = tela_os.FrmOS._extrair_fabricante_modelo
    _equipamento_seguro_para_consulta = tela_os.FrmOS._equipamento_seguro_para_consulta
    _tipo_documentacao_tecnica = tela_os.FrmOS._tipo_documentacao_tecnica
    _rotulo_fonte_tecnica = tela_os.FrmOS._rotulo_fonte_tecnica

    def __init__(self):
        self._ultima_busca_limitacoes = []
        self._ultima_busca_fontes_consultadas = []
        self.window = None
        self.widgets = []
        self.status = ""

    def _atualizar_status_busca_diagrama(self, texto, cor=None):
        self.status = texto


class SearchResultsHarness(ResultsWindowHarness):
    _buscar_links_web_diagrama = tela_os.FrmOS._buscar_links_web_diagrama
    _normalizar_termo_tecnico = tela_os.FrmOS._normalizar_termo_tecnico
    _normalizar_link_resultado = tela_os.FrmOS._normalizar_link_resultado
    _link_eh_tecnico_valido = tela_os.FrmOS._link_eh_tecnico_valido
    _pontuar_link_diagrama = tela_os.FrmOS._pontuar_link_diagrama
    _extrair_pecas_pagina_tecnica = tela_os.FrmOS._extrair_pecas_pagina_tecnica
    _extrair_conhecimento_pagina_tecnica = tela_os.FrmOS._extrair_conhecimento_pagina_tecnica
    _variantes_modelo = tela_os.FrmOS._variantes_modelo

    def _buscar_pagina_tecnica(self, url, timeout):
        if url.startswith("https://duckduckgo.com/"):
            return "", "text/html"
        if url == "https://kastking.com/pages/manuals-schematics?ref=top":
            return "verify you are human", "text/html"
        return "<html><body>Catalogo tecnico</body></html>", "text/html"


class TestBuscaVistaPdf(unittest.TestCase):
    def setUp(self):
        tela_os._limpar_cache_busca_vista()
    @staticmethod
    def make_pdf():
        buffer = io.BytesIO()
        document = canvas.Canvas(buffer)
        document.setTitle("SHIMANO FX 2500 parts")
        document.drawString(40, 790, "Technical manual")
        document.showPage()
        document.drawString(40, 790, "SHIMANO FX 2500")
        document.drawString(40, 760, "Position    Part No    Description")
        document.drawString(40, 740, "1    123456    Drag lever")
        document.save()
        return buffer.getvalue()

    def test_extracts_pdf_part_relation_and_page(self):
        content = self.make_pdf()
        harness = PdfSearchHarness()

        with patch.object(tela_os, "urlopen", return_value=PdfResponse(content)):
            result = harness._baixar_e_extrair_pdf(
                "https://example.test/manual.pdf", "SHIMANO", "FX 2500"
            )

        self.assertEqual(result["status"], "extracted")
        self.assertEqual(result["parts"][0]["codigo"], "123456")
        self.assertEqual(result["parts"][0]["descricao"], "Drag lever")
        self.assertEqual(result["parts"][0]["posicao"], "1")
        self.assertEqual(result["parts"][0]["pagina"], 2)

    def test_reports_scanned_pdf_without_ocr(self):
        buffer = io.BytesIO()
        document = canvas.Canvas(buffer)
        document.showPage()
        document.save()

        with patch.object(tela_os, "urlopen", return_value=PdfResponse(buffer.getvalue())):
            result = PdfSearchHarness()._baixar_e_extrair_pdf(
                "https://example.test/manual.pdf", "SHIMANO", "FX 2500"
            )

        self.assertEqual(result["status"], "scanned")
        self.assertIn("OCR não é realizado", result["error"])
        self.assertEqual(result["parts"], [])

    def test_timeout_and_cancellation_are_reported(self):
        with patch.object(tela_os, "urlopen", side_effect=TimeoutError("timeout")):
            timed_out = PdfSearchHarness()._baixar_e_extrair_pdf(
                "https://example.test/manual.pdf", "SHIMANO", "FX 2500"
            )

        cancellation = threading.Event()
        cancellation.set()
        with patch.object(tela_os, "urlopen", return_value=PdfResponse(self.make_pdf())):
            cancelled = PdfSearchHarness()._baixar_e_extrair_pdf(
                "https://example.test/manual.pdf",
                "SHIMANO",
                "FX 2500",
                cancelamento=cancellation,
            )

        self.assertEqual(timed_out["status"], "error")
        self.assertIn("TimeoutError", timed_out["error"])
        self.assertEqual(cancelled["status"], "cancelled")

    def test_html_piece_table_keeps_position_code_and_description(self):
        html = """
        <table><tr><th>Pos</th><th>Part Number</th><th>Description</th></tr>
        <tr><td>12</td><td>ABC123</td><td>Drive gear</td></tr></table>
        """

        parts = PdfSearchHarness()._extrair_pecas_pagina_tecnica(html)

        self.assertEqual(parts, [{"codigo": "ABC123", "descricao": "Drive gear", "posicao": "12"}])

    def test_repeated_search_click_requests_cancel_without_starting_another_worker(self):
        FakeThread.started = []
        controller = SearchController()
        with patch.object(tela_os.threading, "Thread", FakeThread):
            controller._buscar_vista_equipamento("SHIMANO FX 2500")
            cancellation = controller._busca_vista_cancelamento
            controller._buscar_vista_equipamento("SHIMANO FX 2500")

        self.assertEqual(len(FakeThread.started), 1)
        self.assertTrue(cancellation.is_set())
        self.assertEqual(controller.btn_buscar_vista.text, "CANCELANDO...")

    def test_worker_hands_results_to_a_callback_for_the_main_thread(self):
        harness = BackgroundSearchHarness()
        cancel = threading.Event()
        worker = threading.Thread(
            target=harness._executar_busca_filtrada_bg,
            args=("SHIMANO FX 2500", cancel),
        )
        worker.start()
        worker.join(timeout=3)

        self.assertFalse(worker.is_alive())
        self.assertIsNone(harness.completed_on)
        callback = harness._callbacks_busca_vista.get_nowait()
        callback()
        self.assertIs(harness.completed_on, threading.current_thread())

    def test_equipment_field_has_no_automatic_search_binding(self):
        source = Path(tela_os.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        search_bindings = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "bind"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "txt_equip"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value in {"<KeyRelease>", "<FocusOut>"}
        ]

        self.assertEqual(search_bindings, [])

    def show_results(self, harness, termo, links):
        def make_window(parent, **kwargs):
            widget = FakeWidget(parent, **kwargs)
            harness.window = widget
            harness.widgets.append(widget)
            return widget

        def make_widget(parent, **kwargs):
            widget = FakeWidget(parent, **kwargs)
            harness.widgets.append(widget)
            return widget

        fake_ctk = SimpleNamespace(
            CTkToplevel=make_window,
            CTkLabel=make_widget,
            CTkFrame=make_widget,
            CTkScrollableFrame=make_widget,
            CTkButton=make_widget,
        )
        with patch.object(tela_os, "ctk", fake_ctk):
            harness._exibir_janela_diagramas_multiplas_escolhas(termo, links)

    def test_sumax_akita_document_has_url_link_and_open_button(self):
        harness = ResultsWindowHarness()
        url = "https://example.test/sumax-akita-2-manual.pdf"
        harness._ultima_busca_fontes_consultadas = [
            {
                "source": "Maruri Fishing",
                "url": "https://marurifishing.com.py/produto/pecas-carretilha-black-pira-bg-400",
                "status": "Página consultada; documento correspondente não confirmado.",
            }
        ]
        self.show_results(
            harness,
            "Sumax Akita 2",
            [{
                "url": url,
                "display_name": "Manual técnico candidato — Sumax Akita 2",
                "source": "Reel Schematics",
                "kind": "PDF técnico",
                "parts": [],
                "knowledge": {},
            }],
        )

        url_labels = [widget for widget in harness.widgets if widget.text == url]
        open_buttons = [
            widget for widget in harness.widgets
            if widget.kwargs.get("text") == "Abrir documento"
        ]
        self.assertEqual(len(url_labels), 1)
        self.assertIn("<Button-1>", url_labels[0].bindings)
        self.assertEqual(len(open_buttons), 1)
        with patch.object(tela_os.webbrowser, "open", return_value=True) as open_browser:
            open_buttons[0].kwargs["command"]()
        open_browser.assert_called_once_with(url, new=2)
        self.assertFalse(harness.window.destroyed)

    def test_no_document_keeps_login_limited_source_interactive(self):
        harness = SearchResultsHarness()
        links = harness._buscar_links_web_diagrama("SUMAX", "AKITA 2")
        urls_esperadas = {
            "https://marurifishing.com.py/produto/pecas-carretilha-black-pira-bg-400",
            "https://kastking.com/collections/fishing-reels?ref=shopbycategory",
            "https://kastking.com/pages/manuals-schematics?ref=top",
            "https://www.okumabrasil.com.br/assistencia-tecnica",
        }
        fontes = harness._ultima_busca_fontes_consultadas
        self.assertEqual(links, [])
        self.assertTrue(urls_esperadas <= {fonte["url"] for fonte in fontes})
        self.assertIn("https://www.bing.com/search", {fonte["url"] for fonte in fontes})
        self.assertEqual(
            next(fonte["status"] for fonte in fontes if "manuals-schematics" in fonte["url"]),
            "Exige verificação ou login.",
        )

        self.show_results(harness, "Sumax Akita 2", [])

        visible_text = [widget.text for widget in harness.widgets]
        self.assertTrue(any("Nenhum documento técnico correspondente" in text for text in visible_text))
        self.assertIn("Exige verificação ou login.", visible_text)
        self.assertTrue(urls_esperadas.issubset(set(visible_text)))
        url_labels = [widget for widget in harness.widgets if widget.text in urls_esperadas]
        self.assertEqual(len(url_labels), len(urls_esperadas))
        self.assertTrue(all("<Button-1>" in widget.bindings for widget in url_labels))
        open_buttons = [
            widget for widget in harness.widgets
            if widget.kwargs.get("text") == "Abrir site"
        ]
        self.assertGreaterEqual(len(open_buttons), len(urls_esperadas))
        with patch.object(tela_os.webbrowser, "open", return_value=True) as open_browser:
            for button in open_buttons:
                button.kwargs["command"]()
        opened_urls = {call.args[0] for call in open_browser.call_args_list}
        self.assertTrue(urls_esperadas <= opened_urls)
        self.assertTrue(all(call.kwargs == {"new": 2} for call in open_browser.call_args_list))
        self.assertFalse(harness.window.destroyed)


if __name__ == "__main__":
    unittest.main()
