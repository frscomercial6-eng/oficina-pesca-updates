"""Visualizador interno de PDF da Busca Vista (renderização com pypdfium2, sem sair da Oficina)."""
from __future__ import annotations

import queue
import concurrent.futures
import http.cookiejar
import io
import json
import logging
import re
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

import customtkinter as ctk
import busca_vista_defeitos
import busca_vista_traducao
import rede_validacao
from core.i18n import get_current_locale, t

LIMITE_PDF_BYTES = 25 * 1024 * 1024
PRAZO_DOWNLOAD = 20.0
ZOOM_MIN, ZOOM_MAX = 0.3, 4.0
MARINE_MANUAIS = "https://www.marinefishing.com.br/manuais"
USER_AGENT = "Mozilla/5.0 (compatible; FRSTechnicalSearch/1.0)"
TRADUCOES_SIMULTANEAS = 2
_LOCK_PDFIUM = threading.Lock()
logger = logging.getLogger(__name__)


def _ler_bytes(resp, cancelamento):
    tamanho = str(resp.headers.get("Content-Length") or "")
    if tamanho.isdigit() and int(tamanho) > LIMITE_PDF_BYTES:
        raise ValueError("Documento excede o limite de 25 MB.")
    corpo = bytearray()
    while True:
        if cancelamento.is_set():
            raise InterruptedError("cancelado")
        bloco = resp.read(64 * 1024)
        if not bloco:
            break
        corpo.extend(bloco)
        if len(corpo) > LIMITE_PDF_BYTES:
            raise ValueError("Documento excede o limite de 25 MB.")
    return bytes(corpo)


def _ler_pdf(resp, cancelamento):
    corpo = _ler_bytes(resp, cancelamento)
    if not corpo[:1024].lstrip().startswith(b"%PDF"):
        raise ValueError("A fonte não retornou um arquivo PDF.")
    return corpo


@rede_validacao.rede_tecnica
def baixar_pdf(url: str, cancelamento: threading.Event, timeout: float = PRAZO_DOWNLOAD) -> bytes:
    """Baixa o PDF com limite de tamanho, prazo e cancelamento. Somente http(s)."""
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Endereço de documento inválido.")
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=timeout) as resp:
        return _ler_pdf(resp, cancelamento)


@rede_validacao.rede_tecnica
def baixar_imagem(url: str, cancelamento: threading.Event, timeout: float = PRAZO_DOWNLOAD) -> bytes:
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("Endereço de imagem inválido.")
    with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout) as resp:
        return _ler_bytes(resp, cancelamento)


class _RedirecionamentoMarine(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        partes = urlparse(newurl)
        if partes.scheme != "https" or partes.hostname != "www.marinefishing.com.br":
            raise ValueError("Redirecionamento fora do site oficial Marine Fishing.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@rede_validacao.rede_tecnica
def baixar_pdf_marine(url: str, cancelamento: threading.Event, timeout: float = PRAZO_DOWNLOAD) -> bytes:
    """Usa a mesma sessão e o formulário público acionado pelo site oficial."""
    partes = urlparse(url)
    if (partes.scheme != "https" or partes.hostname != "www.marinefishing.com.br"
            or not re.fullmatch(r"/manuais/download/\d+/\d+", partes.path)
            or partes.query or partes.fragment):
        raise ValueError("Endereço de manual Marine inválido.")
    if cancelamento.is_set():
        raise InterruptedError("cancelado")
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), _RedirecionamentoMarine())
    with opener.open(Request(MARINE_MANUAIS, headers={"User-Agent": USER_AGENT}), timeout=timeout) as resp:
        pagina = resp.read(2_000_001)
    if len(pagina) > 2_000_000:
        raise ValueError("Página oficial excede o limite de leitura.")
    padrao = r"""data\s*:\s*\{\s*csrf\s*:\s*['"]([^'"]+)['"]\s*,\s*['"]csrf_token_marine['"]\s*:\s*['"]([^'"]+)['"]"""
    token = re.search(padrao, pagina.decode("utf-8", errors="replace"))
    if not token:
        raise ValueError("Formulário de download oficial indisponível.")
    if cancelamento.is_set():
        raise InterruptedError("cancelado")
    dados = urlencode({"csrf": token.group(1), "csrf_token_marine": token.group(2)}).encode()
    req = Request(url, data=dados, headers={
        "User-Agent": USER_AGENT, "X-Requested-With": "XMLHttpRequest",
        "Referer": MARINE_MANUAIS, "Origin": "https://www.marinefishing.com.br",
    })
    with opener.open(req, timeout=timeout) as resp:
        resposta = json.loads(resp.read(65537))
    if str(resposta.get("code")) != "200" or not resposta.get("redirect"):
        raise ValueError("O site oficial não autorizou o download do manual.")
    destino = urljoin(MARINE_MANUAIS, resposta["redirect"])
    partes_destino = urlparse(destino)
    if (partes_destino.scheme != "https" or partes_destino.hostname != "www.marinefishing.com.br"
            or partes_destino.path != "/manuais/download-processa"
            or partes_destino.query or partes_destino.fragment):
        raise ValueError("Resposta de download oficial inválida.")
    if cancelamento.is_set():
        raise InterruptedError("cancelado")
    with opener.open(Request(destino, headers={"User-Agent": USER_AGENT}), timeout=timeout) as resp:
        return _ler_pdf(resp, cancelamento)


class VisualizadorPdfBuscaVista(ctk.CTkToplevel):
    def __init__(self, master, candidato: dict, analisar=None, baixar=baixar_pdf):
        super().__init__(master)
        self.candidato = candidato
        self._analisar = analisar
        self._baixar = baixar
        self._cancel = threading.Event()
        self._cancel_defeitos = threading.Event()
        self._fila: queue.Queue = queue.Queue()
        self._fila_traducoes: queue.Queue = queue.Queue()
        self._locale_defeitos = get_current_locale()
        self._resultados_defeitos = 0
        self._traducoes_pendentes = {}
        self._itens_defeitos = {}
        self._lock_pdf = _LOCK_PDFIUM
        self._render_pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self._render_job = None
        self._pdf = None
        self._imagem = None
        self._paginas = 0
        self._pagina = 0
        self._zoom = 1.0
        self._rotacao = 0
        self._ajustar_largura = True
        self._geracao = 0
        self._foto = None
        self._largura_pagina_pt = 612.0
        self._fechada = False

        titulo = " • ".join(p for p in (
            candidato.get("fabricante"), candidato.get("familia"), candidato.get("nome"),
        ) if p)
        self.title(f"Diagrama — {candidato.get('nome') or 'documento'}")
        self.geometry("1180x760")
        self.configure(fg_color="#0d1117")
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<Destroy>", self._ao_destruir, add="+")

        ctk.CTkLabel(self, text=titulo, font=("Arial", 15, "bold"), text_color="#f8f8f8").pack(anchor="w", padx=14, pady=(10, 0))
        ident = f"Código: {candidato.get('codigo') or '—'}   |   Fonte: {candidato.get('fonte') or '—'}   |   Referência candidata, não verificada"
        self.lbl_ident = ctk.CTkLabel(self, text=ident, font=("Arial", 10), text_color="#f1c40f")
        self.lbl_ident.pack(anchor="w", padx=14)

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=12, pady=6)
        self.btn_ant = ctk.CTkButton(barra, text="◀ Anterior", width=90, command=lambda: self.ir_para(self._pagina - 1))
        self.btn_ant.pack(side="left", padx=2)
        self.ent_pagina = ctk.CTkEntry(barra, width=50, justify="center")
        self.ent_pagina.pack(side="left", padx=2)
        self.ent_pagina.bind("<Return>", lambda _e: self._ir_pela_caixa())
        self.lbl_total = ctk.CTkLabel(barra, text="/ —", width=50)
        self.lbl_total.pack(side="left")
        self.btn_prox = ctk.CTkButton(barra, text="Próxima ▶", width=90, command=lambda: self.ir_para(self._pagina + 1))
        self.btn_prox.pack(side="left", padx=2)
        ctk.CTkButton(barra, text="−", width=36, command=lambda: self.alterar_zoom(0.8)).pack(side="left", padx=(16, 2))
        self.lbl_zoom = ctk.CTkLabel(barra, text="100%", width=50)
        self.lbl_zoom.pack(side="left")
        ctk.CTkButton(barra, text="+", width=36, command=lambda: self.alterar_zoom(1.25)).pack(side="left", padx=2)
        ctk.CTkButton(barra, text="Ajustar largura", width=110, command=self.ajustar_largura).pack(side="left", padx=8)
        self.lbl_status = ctk.CTkLabel(barra, text="Baixando documento...", text_color="#95a5a6")
        self.lbl_status.pack(side="left", padx=12)

        barra_rotacao = ctk.CTkFrame(self, fg_color="transparent")
        barra_rotacao.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkButton(barra_rotacao, text="↶ Esquerda 90°", width=115, command=lambda: self.girar(-90)).pack(side="left", padx=2)
        ctk.CTkButton(barra_rotacao, text="↷ Direita 90°", width=115, command=lambda: self.girar(90)).pack(side="left", padx=2)
        ctk.CTkButton(barra_rotacao, text="Orientação original", width=130, command=self.restaurar_orientacao).pack(side="left", padx=2)

        corpo = tk.PanedWindow(self, orient="horizontal", bg="#0d1117", sashwidth=5, bd=0)
        corpo.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        esquerda = tk.Frame(corpo, bg="#161b22")
        self.canvas = tk.Canvas(esquerda, bg="#2b2f36", highlightthickness=0)
        sy = ttk.Scrollbar(esquerda, orient="vertical", command=self.canvas.yview)
        sx = ttk.Scrollbar(esquerda, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        corpo.add(esquerda, stretch="always", minsize=420)

        direita = tk.Frame(corpo, bg="#161b22")
        abas = ttk.Notebook(direita)
        abas.pack(fill="both", expand=True)
        defeitos = tk.Frame(abas, bg="#161b22")
        pecas = tk.Frame(abas, bg="#161b22")
        abas.add(defeitos, text=t("bv_aba", locale=self._locale_defeitos))
        abas.add(pecas, text="Peças extraídas")
        self.lbl_defeitos = ctk.CTkLabel(
            defeitos, text=t("bv_iniciando", locale=self._locale_defeitos), text_color="#f1c40f",
            wraplength=330, justify="left",
        )
        self.lbl_defeitos.pack(anchor="w", padx=8, pady=6)
        self.btn_cancelar_defeitos = ctk.CTkButton(
            defeitos, text=t("bv_cancelar", locale=self._locale_defeitos), width=140, command=self._cancelar_pesquisa_defeitos,
        )
        self.btn_cancelar_defeitos.pack(anchor="w", padx=8, pady=(0, 6))
        texto_quadro = tk.Frame(defeitos, bg="#161b22")
        texto_quadro.pack(fill="both", expand=True, padx=8, pady=6)
        self.texto_defeitos = tk.Text(
            texto_quadro, wrap="word", bg="#0d1117", fg="#e6edf3",
            insertbackground="#e6edf3", relief="flat", state="disabled",
        )
        barra_defeitos = ttk.Scrollbar(texto_quadro, orient="vertical", command=self.texto_defeitos.yview)
        self.texto_defeitos.configure(yscrollcommand=barra_defeitos.set)
        barra_defeitos.pack(side="right", fill="y")
        self.texto_defeitos.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(pecas, text="Peças extraídas", font=("Arial", 12, "bold"), text_color="#f8f8f8").pack(anchor="w", padx=8, pady=(8, 2))
        self.lbl_pecas = ctk.CTkLabel(pecas, text="Aguardando análise...", text_color="#95a5a6", wraplength=330, justify="left")
        self.lbl_pecas.pack(anchor="w", padx=8)
        estilo = ttk.Style(self)
        estilo.configure("BV.Treeview", background="#0d1117", foreground="#e6edf3", fieldbackground="#0d1117", rowheight=22)
        estilo.configure("BV.Treeview.Heading", background="#21262d", foreground="#f8f8f8")
        self.tree = ttk.Treeview(pecas, columns=("pos", "cod", "desc", "pag"), show="headings", style="BV.Treeview", height=20)
        for col, txt, larg in (("pos", "Pos.", 44), ("cod", "Código", 90), ("desc", "Descrição", 170), ("pag", "Pág.", 40)):
            self.tree.heading(col, text=txt)
            self.tree.column(col, width=larg, anchor="w", stretch=(col == "desc"))
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)
        self.tree.bind("<Double-1>", self._ir_para_peca)
        corpo.add(direita, minsize=300, width=360)

        self.canvas.bind("<MouseWheel>", self._roda)
        self.canvas.bind("<Shift-MouseWheel>", lambda e: self.canvas.xview_scroll(-1 * (e.delta // 120), "units"))
        self.canvas.bind("<Control-MouseWheel>", lambda e: self.alterar_zoom(1.15 if e.delta > 0 else 1 / 1.15))
        self.canvas.bind("<Configure>", lambda _e: self._reajustar_se_necessario())
        self._atualizar_botoes()
        self.after(80, self._processar_fila)
        threading.Thread(target=self._carregar, daemon=True).start()
        threading.Thread(target=self._pesquisar_defeitos, daemon=True).start()
        for _ in range(TRADUCOES_SIMULTANEAS):
            threading.Thread(target=self._traduzir_defeitos, daemon=True).start()

    # ---------- segundo plano ----------
    def _pesquisar_defeitos(self):
        def emitir(tipo, conteudo):
            if not self._cancel_defeitos.is_set():
                self._fila.put(("defeitos_" + tipo, conteudo))
        try:
            busca_vista_defeitos.pesquisar(self.candidato, self._cancel_defeitos, emitir)
        except Exception as exc:
            emitir("fim", f"Falha na pesquisa de relatos: {type(exc).__name__}: {exc}")

    def _traduzir_defeitos(self):
        identidade = busca_vista_defeitos.identidade_tecnica(self.candidato)
        while not self._cancel_defeitos.is_set():
            try:
                tarefa = self._fila_traducoes.get(timeout=0.1)
            except queue.Empty:
                continue
            if tarefa is None:
                return
            numero, item = tarefa
            original = self._texto_publico(item)
            try:
                traduzido = busca_vista_traducao.traduzir_texto_local(
                    original, item.get("idioma", ""), self._locale_defeitos, identidade, self._cancel_defeitos
                )
                estado = "bv_local_concluido"
            except InterruptedError:
                return
            except busca_vista_traducao.TraducaoLocalIndisponivel as exc:
                traduzido, estado = None, "bv_local_erro_" + str(exc)
            except Exception:
                logger.exception("Falha na tradução local de discussão pública")
                traduzido, estado = None, "bv_local_erro_geral"
            if not self._cancel_defeitos.is_set():
                self._fila.put(("defeitos_traducao", numero, traduzido, estado))

    @staticmethod
    def _texto_publico(item):
        return "\n\n".join((item.get("titulo_publico") or item["titulo"], *item.get("mensagens_publicas", ())))

    def _carregar(self):
        try:
            if self.candidato.get("tipo_documento") == "html":
                self._fila.put(("catalogo_html",))
                self._fila.put(("analise", {"parts": self.candidato.get("parts", [])}))
                return
            if self.candidato.get("tipo_documento") == "svg":
                raise ValueError("Visualização interna de SVG ainda não é suportada.")
            corpo = self._baixar(self.candidato["pdf_url"], self._cancel)
            with self._lock_pdf:
                if self._cancel.is_set():
                    return
                if self.candidato.get("tipo_documento") == "imagem":
                    from PIL import Image
                    imagem = Image.open(io.BytesIO(corpo))
                    if imagem.format not in {"PNG", "JPEG"} or imagem.width * imagem.height > 60_000_000:
                        raise ValueError("Imagem inválida ou excede o tamanho permitido.")
                    imagem.load()
                    self._imagem = imagem.copy()
                    paginas, largura = 1, float(imagem.width)
                else:
                    import pypdfium2 as pdfium
                    pdf = pdfium.PdfDocument(corpo)
                    self._pdf = pdf
                    paginas = len(pdf)
                    pagina0 = pdf[0]
                    largura = float(pagina0.get_size()[0])
            self._fila.put(("aberto", paginas, largura))
            analise = None
            if self._analisar is not None and self._imagem is None:
                try:
                    analise = self._analisar(corpo, self._cancel)
                except InterruptedError:
                    return
                except Exception as exc:
                    analise = {"status": "error", "error": f"{type(exc).__name__}: {exc}", "parts": []}
            if not self._cancel.is_set():
                self._fila.put(("analise", analise))
        except InterruptedError:
            pass
        except Exception as exc:
            self._fila.put(("erro", f"{type(exc).__name__}: {exc}"))

    def _renderizar(self, pagina: int, escala: float, geracao: int, rotacao: int, largura_ajuste):
        try:
            with self._lock_pdf:
                if self._cancel.is_set() or geracao != self._geracao or (self._pdf is None and self._imagem is None):
                    return
                if self._imagem is not None:
                    from PIL import Image
                    largura, altura = self._imagem.size
                else:
                    pagina_pdf = self._pdf[pagina]
                    largura, altura = pagina_pdf.get_size()
                largura_rotacionada = altura if rotacao in (90, 270) else largura
                if largura_ajuste is not None:
                    escala = min(max(largura_ajuste / largura_rotacionada, ZOOM_MIN), ZOOM_MAX)
                if largura * altura * escala * escala > 60_000_000:
                    raise ValueError("Zoom excede o tamanho permitido.")
                if self._imagem is not None:
                    imagem_base = self._imagem
                    if rotacao:
                        sentido = {90: Image.Transpose.ROTATE_270, 180: Image.Transpose.ROTATE_180,
                                   270: Image.Transpose.ROTATE_90}
                        imagem_base = imagem_base.transpose(sentido[rotacao])
                    dimensoes = (max(1, int(imagem_base.width * escala)), max(1, int(imagem_base.height * escala)))
                    if dimensoes[0] * dimensoes[1] > 60_000_000:
                        raise ValueError("Zoom excede o tamanho permitido.")
                    imagem = imagem_base.resize(dimensoes)
                else:
                    imagem = pagina_pdf.render(scale=escala, rotation=rotacao).to_pil()
            blocos = []
            for y in range(0, imagem.height, 512):
                for x in range(0, imagem.width, 512):
                    if self._cancel.is_set() or geracao != self._geracao:
                        return
                    blocos.append((x, y, imagem.crop((x, y, min(x + 512, imagem.width), min(y + 512, imagem.height)))))
            self._fila.put(("imagem", geracao, pagina, imagem.size, blocos, escala))
        except Exception as exc:
            self._fila.put(("erro_render", geracao, f"{type(exc).__name__}: {exc}"))

    # ---------- thread principal ----------
    def _processar_fila(self):
        if self._fechada:
            return
        try:
            while True:
                msg = self._fila.get_nowait()
                tipo = msg[0]
                if tipo == "aberto":
                    self._paginas, self._largura_pagina_pt = msg[1], msg[2]
                    self.lbl_total.configure(text=f"/ {self._paginas}")
                    self.lbl_status.configure(text="Documento aberto no visualizador interno.", text_color="#2ecc71")
                    self.ir_para(0)
                elif tipo == "imagem":
                    if msg[1] == self._geracao:
                        self._zoom = msg[5]
                        self.lbl_zoom.configure(text=f"{int(self._zoom * 100)}%")
                    self._mostrar_imagem(*msg[1:5])
                elif tipo == "analise":
                    self._mostrar_analise(msg[1])
                elif tipo == "catalogo_html":
                    self.lbl_status.configure(text="Catálogo HTML; sem imagem de diagrama confirmada.", text_color="#f1c40f")
                elif tipo == "erro":
                    self.lbl_status.configure(text=f"Não foi possível abrir o documento: {msg[1]}", text_color="#e74c3c")
                elif tipo == "erro_render":
                    if msg[1] == self._geracao:
                        self.lbl_status.configure(text=f"Falha ao desenhar a página: {msg[2]}", text_color="#e74c3c")
                elif tipo.startswith("defeitos_") and not self._cancel_defeitos.is_set():
                    if tipo == "defeitos_resultado":
                        item = msg[1]
                        numero = self._resultados_defeitos
                        self._resultados_defeitos += 1
                        origem = item.get("idioma", "").lower().replace("-", "_").split("_")[0]
                        destino = self._locale_defeitos.lower().replace("-", "_").split("_")[0]
                        traduzido = None
                        if item.get("texto_publico_incompleto"):
                            estado = "bv_google_incompleto"
                        elif not item.get("mensagens_publicas"):
                            estado = "bv_google_sem_texto"
                        elif origem and origem == destino:
                            traduzido = self._texto_publico(item)
                            estado = "bv_local_mesmo_idioma"
                        else:
                            estado = "bv_traducao_pendente"
                        self._itens_defeitos[numero] = {"original": item, "traduzido": traduzido, "estado": estado}
                        self._mostrar_defeito(item, numero, estado, traducao=traduzido)
                        if estado == "bv_traducao_pendente":
                            self._traducoes_pendentes[numero] = item
                            self._fila_traducoes.put((numero, item))
                    elif tipo == "defeitos_traducao":
                        self._traducoes_pendentes.pop(msg[1], None)
                        registro = self._itens_defeitos[msg[1]]
                        registro["traduzido"], registro["estado"] = msg[2], msg[3]
                        self._atualizar_defeito_traduzido(msg[1])
                    else:
                        self.lbl_defeitos.configure(text=busca_vista_traducao.localizar_status(msg[1], self._locale_defeitos))
                        if tipo == "defeitos_fim":
                            self.btn_cancelar_defeitos.configure(state="disabled")
                            for _ in range(TRADUCOES_SIMULTANEAS):
                                self._fila_traducoes.put(None)
        except queue.Empty:
            pass
        self.after(80, self._processar_fila)

    def _pedir_render(self):
        if not self._paginas or self._fechada:
            return
        self._geracao += 1
        largura_ajuste = max(self.canvas.winfo_width() - 4, 300) if self._ajustar_largura else None
        self.lbl_zoom.configure(text=f"{int(self._zoom * 100)}%")
        if self._render_job is not None:
            self._render_job.cancel()
        self._render_job = self._render_pool.submit(
            self._renderizar, self._pagina, self._zoom, self._geracao, self._rotacao, largura_ajuste
        )

    def _mostrar_imagem(self, geracao, pagina, tamanho, blocos):
        if geracao != self._geracao or pagina != self._pagina:
            return  # resultado atrasado de uma página/zoom anterior
        from PIL import ImageTk
        self.canvas.delete("all")
        self.canvas.configure(scrollregion=(0, 0, tamanho[0], tamanho[1]))
        self.canvas.yview_moveto(0)
        fotos = []
        self._fotos_em_montagem = fotos

        def inserir_lote(inicio=0):
            if self._fechada or geracao != self._geracao or pagina != self._pagina:
                return
            fim = min(inicio + 8, len(blocos))
            for x, y, imagem in blocos[inicio:fim]:
                foto = ImageTk.PhotoImage(imagem, master=self)
                fotos.append(foto)
                self.canvas.create_image(x, y, anchor="nw", image=foto)
            if fim < len(blocos):
                self.after(1, lambda: inserir_lote(fim))
            else:
                self._foto = fotos
                self._fotos_em_montagem = None
        inserir_lote()

    def ir_para(self, indice: int):
        if not self._paginas:
            return
        self._pagina = max(0, min(self._paginas - 1, int(indice)))
        self.ent_pagina.delete(0, "end")
        self.ent_pagina.insert(0, str(self._pagina + 1))
        self._atualizar_botoes()
        self._pedir_render()

    def _ir_pela_caixa(self):
        try:
            self.ir_para(int(self.ent_pagina.get()) - 1)
        except ValueError:
            self.ent_pagina.delete(0, "end")
            self.ent_pagina.insert(0, str(self._pagina + 1))

    def _atualizar_botoes(self):
        self.btn_ant.configure(state="normal" if self._pagina > 0 else "disabled")
        self.btn_prox.configure(state="normal" if self._pagina < self._paginas - 1 else "disabled")

    def alterar_zoom(self, fator: float):
        self._ajustar_largura = False
        self._zoom = min(max(self._zoom * fator, ZOOM_MIN), ZOOM_MAX)
        self._pedir_render()

    def girar(self, graus: int):
        if not self._paginas or self._fechada:
            return
        self._rotacao = (self._rotacao + graus) % 360
        self._ajustar_largura = False
        self._pedir_render()

    def restaurar_orientacao(self):
        if not self._paginas or self._fechada or not self._rotacao:
            return
        self._rotacao = 0
        self._ajustar_largura = False
        self._pedir_render()

    def ajustar_largura(self):
        self._ajustar_largura = True
        self._pedir_render()

    def _reajustar_se_necessario(self):
        if self._ajustar_largura and self._paginas:
            if getattr(self, "_job_reajuste", None):
                self.after_cancel(self._job_reajuste)
            self._job_reajuste = self.after(250, self._pedir_render)

    def _roda(self, evento):
        self.canvas.yview_scroll(-1 * (evento.delta // 120), "units")

    def _mostrar_analise(self, analise):
        self._geracao_analise = getattr(self, "_geracao_analise", 0) + 1
        geracao = self._geracao_analise
        linhas = self.tree.get_children()
        if linhas:
            self.tree.delete(*linhas)
        if not analise:
            self.lbl_pecas.configure(text="Análise de peças indisponível; consulte o diagrama visualmente.")
            return
        pecas = analise.get("parts") or []
        if pecas:
            self.lbl_pecas.configure(text=f"{len(pecas)} linha(s) extraída(s). Confira na fonte.", text_color="#2ecc71")
            def inserir_lote(inicio=0):
                if self._fechada or geracao != self._geracao_analise:
                    return
                for p in pecas[inicio:inicio + 50]:
                    self.tree.insert("", "end", values=(p.get("posicao", ""), p.get("codigo", ""), p.get("descricao", ""), p.get("pagina", "")))
                if inicio + 50 < len(pecas):
                    self.after(1, lambda: inserir_lote(inicio + 50))
            inserir_lote()
        else:
            motivo = analise.get("error") or "Nenhuma tabela de peças extraível."
            self.lbl_pecas.configure(text=f"{motivo} O PDF permanece disponível para consulta visual.", text_color="#f1c40f")

    def _ir_para_peca(self, _evento):
        selecionado = self.tree.selection()
        if selecionado:
            pagina = self.tree.item(selecionado[0], "values")[3]
            if str(pagina).isdigit():
                self.ir_para(int(pagina) - 1)

    def _cancelar_pesquisa_defeitos(self):
        self._cancel_defeitos.set()
        for numero in self._traducoes_pendentes:
            self._itens_defeitos[numero]["estado"] = "bv_local_cancelada"
            self._atualizar_defeito_traduzido(numero)
        self._traducoes_pendentes.clear()
        self.lbl_defeitos.configure(text=t("bv_cancelada", locale=self._locale_defeitos))
        self.btn_cancelar_defeitos.configure(state="disabled")

    def _atualizar_defeito_traduzido(self, numero):
        registro = self._itens_defeitos[numero]
        self._mostrar_defeito(
            registro["original"], numero, registro["estado"],
            atualizar=True, traducao=registro["traduzido"],
        )

    def _mostrar_defeito(self, item, numero, estado, atualizar=False, traducao=None):
        texto = self.texto_defeitos
        texto.configure(state="normal")
        inicio, fim = f"defeito_{numero}_inicio", f"defeito_{numero}_fim"
        if atualizar:
            texto.delete(inicio, fim)
        else:
            texto.mark_set(inicio, "end-1c")
            texto.mark_set(fim, inicio)
        texto.mark_gravity(inicio, "left")
        texto.mark_gravity(fim, "right")
        loc = lambda chave: t(chave, locale=self._locale_defeitos)
        escopos = {
            "Variante": "bv_variante",
            "Família; variante não confirmada": "bv_familia",
            "Possível família; fabricante e variante não confirmados": "bv_possivel_familia",
        }
        escopo = loc(escopos[item["escopo"]]) if item["escopo"] in escopos else item["escopo"]
        classificacoes = {
            "Não confirmado": "bv_nao_confirmado",
            "Relato isolado": "bv_relato_isolado",
            "Recorrente": "bv_recorrente",
        }
        classificacao = loc(classificacoes[item["classificacao"]]) if item["classificacao"] in classificacoes else item["classificacao"]
        texto.insert(fim, f"{item['titulo']}\n")
        texto.insert(fim, f"{loc('bv_escopo')}: {escopo}\n{loc('bv_classificacao')}: {classificacao}\n")
        texto.insert(fim, f"{loc('bv_sintomas')}: {item['sintomas']}\n")
        texto.insert(fim, f"{loc('bv_causa')}: {item['causa'] or loc('bv_nao_identificada')}\n")
        texto.insert(fim, f"{loc('bv_reparo')}: {item['reparo'] or loc('bv_nao_identificado')}\n")
        for indice, (rotulo, url) in enumerate(((loc("bv_link_defeito"), item["url_defeito"]), (loc("bv_link_reparo"), item["url_reparo"]))):
            if not url:
                continue
            tag = f"link_defeito_{numero}_{indice}"
            texto.insert(fim, f"{rotulo}: ")
            texto.insert(fim, url, tag)
            texto.insert(fim, "\n")
            texto.tag_configure(tag, foreground="#58a6ff", underline=True)
            texto.tag_bind(tag, "<Button-1>", lambda _evento, endereco=url: self._abrir_discussao(endereco))
        texto.insert(fim, f"\n{loc('bv_secao_original')}\n{self._texto_publico(item)}\n")
        texto.insert(fim, f"\n{loc('bv_secao_traducao')}\n")
        if traducao is not None:
            texto.insert(fim, f"{traducao}\n")
        if estado == "bv_local_concluido":
            texto.insert(fim, f"{loc('bv_google_revisao')}\n")
        if estado:
            texto.insert(fim, f"{loc(estado)}\n")
        texto.insert(fim, "\n")
        texto.mark_gravity(inicio, "right")
        texto.mark_gravity(fim, "left")
        texto.configure(state="disabled")

    @rede_validacao.navegador_usuario
    def _abrir_discussao(self, url):
        try:
            if not webbrowser.open(url, new=2):
                raise OSError(t("bv_erro_navegador"))
        except Exception as exc:
            self.lbl_defeitos.configure(text=f"{t('bv_erro_link')}: {type(exc).__name__}")

    def _encerrar_trabalho(self):
        if self._fechada:
            return
        self._fechada = True
        self._cancel.set()
        self._cancel_defeitos.set()
        self._render_pool.shutdown(wait=False, cancel_futures=True)
        threading.Thread(target=self._liberar_pdf, daemon=True).start()

    def _ao_destruir(self, evento):
        if evento.widget is self:
            self._encerrar_trabalho()

    def _fechar(self):
        self._encerrar_trabalho()
        self.destroy()

    def _liberar_pdf(self):
        with self._lock_pdf:
            try:
                if self._pdf is not None:
                    self._pdf.close()
            except Exception:
                pass
            self._pdf = None
            self._imagem = None
