"""Descoberta limitada de documentos em índices técnicos públicos."""
from __future__ import annotations

import concurrent.futures
import heapq
import html
import itertools
import re
import threading
import time
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse

import busca_vista_catalogo as catalogo


_FONTES_GRUPO_JOGA = (
    ("Grupo Jogá", "https://www.grupojoga.com.br/"),
    ("Grupo Jogá", "https://www.grupojoga.com.br/sitemap.xml"),
    ("Jogá", "https://jogaoficial.grupojoga.com.br/"),
    ("Saint", "https://saintoficial.grupojoga.com.br/"),
    ("Saint", "https://www.saintoficial.com.br/"),
    ("Juninho Pesca (loja independente)", "https://www.juninhopesca.com.br/categoria/pesca/carretilhas-e-protetores"),
)

FONTES_INICIAIS = {
    "DAIWA": (
        ("Daiwa USA", "https://daiwa.us/pages/parts-diagram-owners-manuals"),
        ("Daiwa USA", "https://daiwa.us/pages/light-tackle-spin-reel-schematics"),
        ("Daiwa USA", "https://daiwa.us/pages/saltwater-spinning-reel-schematics"),
        ("Daiwa USA", "https://daiwa.us/pages/fly-reel-schematics"),
        ("Daiwa USA", "https://daiwa.us/pages/spincast-reel-schematics"),
        ("Daiwa USA", "https://daiwa.us/pages/old-schematics"),
    ),
    "KASTKING": (("KastKing", "https://kastking.com/pages/manuals-schematics"),),
    "MARURI": (
        ("Maruri", "https://marurifishing.com.py/catalogos"),
        ("Maruri Brasil", "https://maruri.com.br/acessorios/pecas"),
        ("Maruri Brasil", "https://maruri.com.br/carretilhas"),
    ),
    "PENN": (("Penn", "https://www.pennfishing.com/pages/schematics"),),
    "OKUMA": (
        ("Okuma Brasil", "https://www.okumafishing.com.br/assistencia-tecnica"),
        ("Okuma", "https://www.okumafishing.com/Templates/att/"),
    ),
    "ABU GARCIA": (
        ("Abu Garcia", "https://www.abugarcia.com/pages/performance-parts"),
        ("Abu Garcia Australia", "https://abugarcia-fishing.com.au/abu-garcia-reel-schematics/"),
    ),
    "SHIMANO": (
        ("Shimano", "https://fishshop.shimano.com/collections/all-parts"),
        ("Shimano", "https://fishshop.shimano.com/collections/spinning-reels-parts"),
    ),
    "JOGA": _FONTES_GRUPO_JOGA + (("Jogá (endereço histórico)", "https://joga.com.br/manuais/"),),
    "JOGÁ": _FONTES_GRUPO_JOGA + (("Jogá (endereço histórico)", "https://joga.com.br/manuais/"),),
    "SAINT PLUS": _FONTES_GRUPO_JOGA + (("Jogá / Saint Plus (endereço histórico)", "https://joga.com.br/manuais/"),),
    "SAINT": _FONTES_GRUPO_JOGA + (("Jogá / Saint Plus (endereço histórico)", "https://joga.com.br/manuais/"),),
}
_CACHE_PAGINAS = {}
_CACHE_LOCK = threading.Lock()
_VALIDADE_CACHE = 300.0
_LIMITE_CACHE = 24


def limpar_cache_fontes():
    with _CACHE_LOCK:
        _CACHE_PAGINAS.clear()


def _obter_pagina(url, buscar_html):
    with _CACHE_LOCK:
        entrada = _CACHE_PAGINAS.get(url)
        if entrada and time.monotonic() - entrada[0] < _VALIDADE_CACHE:
            return entrada[1]
    pagina = buscar_html(url)
    visivel = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", " ", pagina, flags=re.I | re.S)
    visivel = html.unescape(re.sub(r"<[^>]*>", " ", visivel))
    if (not pagina or not re.search(r"<(?:html|a|urlset|sitemapindex)\b", pagina, re.I)
            or re.search(r"captcha|verify you are human|unusual traffic|robot check|sign in to continue", visivel, re.I)):
        raise ValueError("Página vazia ou exige verificação/login")
    with _CACHE_LOCK:
        if len(_CACHE_PAGINAS) >= _LIMITE_CACHE:
            _CACHE_PAGINAS.pop(next(iter(_CACHE_PAGINAS)))
        _CACHE_PAGINAS[url] = (time.monotonic(), pagina)
    return pagina


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.anchor = None
        self.product = ""
        self.in_product = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "li":
            self.product = ""
        if tag == "span" and "product_text" in attrs.get("class", "").split():
            self.in_product = True
            self.product = ""
        if tag == "a" and attrs.get("href"):
            self.anchor = [attrs["href"], []]
        if tag == "img":
            if self.anchor:
                self.anchor[1].append(attrs.get("alt", ""))
            if attrs.get("src"):
                self.links.append((attrs["src"], attrs.get("alt", "")))

    def handle_data(self, data):
        if self.in_product:
            self.product += data
        if self.anchor:
            self.anchor[1].append(data)

    def handle_endtag(self, tag):
        if tag == "span" and self.in_product:
            self.in_product = False
        if tag == "a" and self.anchor:
            href, fragments = self.anchor
            titulo = re.sub(r"\s+", " ", " ".join(fragments)).strip()
            if self.product and catalogo._norm(titulo) in {"download pdf", "baixar", "download"}:
                titulo = re.sub(r"\s+", " ", self.product).strip()
            self.links.append((href, titulo))
            self.anchor = None


def _tokens(texto):
    texto = catalogo._norm(texto)
    palavras = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", texto).split()
    romanos = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6"}
    return [romanos.get(palavra, palavra) for palavra in palavras]


def _corresponde(modelo, nome):
    procurados = _tokens(modelo)
    palavras = _tokens(nome)
    if not procurados:
        return False
    indice = 0
    for palavra in palavras:
        if indice < len(procurados) and palavra == procurados[indice]:
            indice += 1
    return indice == len(procurados)


def ler_indice(html, pagina, fonte, fabricante, modelo, dominios_permitidos=None):
    if re.search(r"<(?:urlset|sitemapindex)\b", html, re.I):
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", html, re.I):
            raise ValueError("Mapa do site contém declaração XML não permitida.")
        raiz = ET.fromstring(html)
        links = [(elemento.text or "", "") for elemento in raiz.iter()
                 if elemento.tag.split("}")[-1] == "loc"]
    else:
        parser = _Links()
        parser.feed(html)
        links = parser.links
    documentos, paginas = [], []
    host = urlparse(pagina).hostname
    dominios = set(dominios_permitidos or ()) | {host, "cdn.shopify.com"}
    for href, titulo in links:
        url = urljoin(pagina, href)
        partes = urlparse(url)
        if partes.scheme != "https" or not partes.hostname:
            continue
        caminho = unquote(partes.path)
        extensao = caminho.rsplit(".", 1)[-1].lower() if "." in caminho else ""
        nome_arquivo = re.sub(r"\.[^.]+$", "", caminho.rsplit("/", 1)[-1]).replace("_", " ")
        nome = titulo
        if not nome or nome.lower().endswith(".pdf") or catalogo._norm(nome) in {"download", "download pdf", "baixar"}:
            nome = nome_arquivo
        if extensao in {"pdf", "jpg", "jpeg", "png", "svg"}:
            if partes.hostname not in dominios:
                continue
            if extensao != "pdf" and not re.search(r"schematic|diagram|exploded|vista.explodida", nome + " " + caminho, re.I):
                continue
            if not _corresponde(modelo, nome):
                continue
            documentos.append({
                "fabricante": fabricante, "familia": modelo, "nome": nome,
                "codigo": catalogo.codigo_da_variacao(nome), "pdf_url": url,
                "fonte": fonte, "origem_url": pagina, "verificado": False,
                "tipo_documento": "pdf" if extensao == "pdf" else ("svg" if extensao == "svg" else "imagem"),
                "identificacao_exata": _tokens(nome) == _tokens(modelo) == _tokens(nome_arquivo),
            })
        elif (partes.hostname in dominios and partes.hostname != "cdn.shopify.com"
              and not partes.fragment and (not partes.query or re.fullmatch(r"page=\d+", partes.query, re.I))):
            caminho_norm = catalogo._norm(unquote(partes.path))
            produto = bool(re.search(r"(?:^|/)(?:p|produto|product|products)/", partes.path, re.I))
            indice = bool(re.search(
                r"schematic|diagram|manual|catalog|pecas|parts|carretilha|molinete|reel|categor|sitemap",
                caminho_norm, re.I,
            ))
            if (partes.path != urlparse(pagina).path or partes.query) and (
                    (produto and (_corresponde(modelo, caminho_norm) or _corresponde(modelo, titulo)))
                    or (indice and not produto)):
                paginas.append(url)
    paginas = list(dict.fromkeys(paginas))
    paginas.sort(key=lambda url: (
        not _corresponde(modelo, unquote(urlparse(url).path)),
        not bool(re.search(r"schematic|diagram|manual|explod", url, re.I)),
    ))
    return documentos, paginas


def catalogos_html(resultados, fabricante, modelo):
    candidatos = []
    for item in resultados:
        url = str(item.get("url") or "")
        partes = urlparse(url)
        if (partes.scheme not in {"http", "https"} or not item.get("parts")
                or partes.path.lower().endswith((".pdf", ".jpg", ".jpeg", ".png", ".svg"))
                or not _corresponde(modelo, unquote(partes.path))):
            continue
        candidatos.append({
            "fabricante": fabricante, "familia": modelo,
            "nome": item.get("display_name") or modelo,
            "codigo": "", "pdf_url": url, "fonte": item.get("source") or partes.hostname,
            "origem_url": url, "verificado": False, "tipo_documento": "html",
            "identificacao_exata": False, "parts": item["parts"],
        })
    return candidatos


def descobrir(fabricante, modelo, buscar_html, cancelado=None, prazo=15.0, max_paginas=20):
    """Percorre índices e subpáginas técnicas com prazo e número de páginas limitados."""
    if cancelado and cancelado.is_set():
        return [], "cancelado", ""
    seeds = FONTES_INICIAIS.get(fabricante, ())
    if not seeds:
        return [], "sem_resultado", ""
    deadline = time.monotonic() + prazo
    dominios = {urlparse(url).hostname for _, url in seeds}
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
    pendentes, vistos, na_fila, documentos, falhas = {}, set(), set(), [], []
    fila = []
    ordem = itertools.count()
    paginas_por_host = {}
    limite_por_host = 6 if len(dominios) > 1 else max_paginas
    limite_host_atingido = False

    def enfileirar(fonte, url, inicial=False):
        if cancelado and cancelado.is_set():
            return
        if url in vistos or url in na_fila:
            return
        caminho = unquote(urlparse(url).path)
        if inicial:
            prioridade = -1
        elif _corresponde(modelo, caminho):
            prioridade = 0
        elif re.search(r"schematic|diagram|manual|explod", caminho, re.I):
            prioridade = 1
        elif re.search(r"carretilha|molinete|reel|pecas|parts", caminho, re.I):
            prioridade = 2
        else:
            prioridade = 3
        heapq.heappush(fila, (prioridade, next(ordem), fonte, url))
        na_fila.add(url)

    for fonte, url in seeds:
        enfileirar(fonte, url, inicial=True)
    try:
        while (pendentes or fila) and time.monotonic() < deadline and not (cancelado and cancelado.is_set()):
            while fila and len(pendentes) < 6 and len(vistos) < max_paginas:
                _, _, fonte, url = heapq.heappop(fila)
                na_fila.remove(url)
                host = urlparse(url).hostname
                if paginas_por_host.get(host, 0) >= limite_por_host:
                    limite_host_atingido = True
                    continue
                paginas_por_host[host] = paginas_por_host.get(host, 0) + 1
                vistos.add(url)
                pendentes[pool.submit(_obter_pagina, url, buscar_html)] = (fonte, url)
            if not pendentes:
                break
            prontos, _ = concurrent.futures.wait(
                pendentes, timeout=min(0.2, max(0, deadline - time.monotonic())),
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
            for futuro in prontos:
                fonte, url = pendentes.pop(futuro)
                try:
                    html = futuro.result()
                    encontrados, links = ler_indice(html, url, fonte, fabricante, modelo, dominios)
                    documentos.extend(encontrados)
                    for link in links:
                        enfileirar(fonte, link)
                except Exception as exc:
                    codigo = getattr(exc, "code", None)
                    falhas.append(f"{fonte}: HTTP {codigo}" if codigo else f"{fonte}: {type(exc).__name__}")
        if pendentes or (fila and len(vistos) < max_paginas):
            falhas.append("Prazo do catálogo esgotado")
        if fila and len(vistos) >= max_paginas:
            falhas.append("Limite de páginas do catálogo atingido")
        if limite_host_atingido:
            falhas.append("Limite de páginas por domínio atingido")
        if cancelado and cancelado.is_set():
            return [], "cancelado", ""
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    unicos = list({item["pdf_url"]: item for item in documentos}.values())
    if falhas:
        return unicos, "incompleto", "Fontes de catálogo indisponíveis ou incompletas: " + ", ".join(sorted(set(falhas)))
    return unicos, "ok" if unicos else "sem_resultado", ""
