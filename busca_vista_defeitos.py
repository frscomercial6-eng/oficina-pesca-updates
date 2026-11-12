"""Pesquisa pública de relatos, sem acessar dados operacionais da oficina."""
from __future__ import annotations

import base64
import concurrent.futures
import html
import http.cookiejar
import ipaddress
import queue
import re
import threading
import time
import unicodedata
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urldefrag, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

import busca_vista_catalogo
import rede_validacao

MOTORES = {
    "Bing": "https://www.bing.com/search?q={}",
    "DuckDuckGo": "https://duckduckgo.com/html/?q={}",
}
FABRICANTES = frozenset({
    "SHIMANO", "DAIWA", "KASTKING", "MARURI", "MARINE SPORTS", "MARINE FISHING",
    "PENN", "OKUMA", "ABU GARCIA", "SAINT", "SAINT PLUS", "JOGA", "JOGÁ",
    "SUMAX", "DAISEN", "PINNACLE", "ALBATROZ",
})
PALAVRAS_GENERICAS = frozenset({
    "manual", "schematic", "schematics", "diagram", "diagrama", "parts", "pecas",
    "vista", "explodida", "exploded", "carretilha", "molinete", "reel", "fishing",
    "owners", "owner", "pdf", "produto", "product",
})
PRAZO_FONTE = 6.0
PRAZO_TOTAL = 18.0
FORUM_BD = "https://www.bdoutdoors.com/forums/search/"
_pesquisas_ativas = {}
_lock_pesquisas = threading.Lock()


def _norm(texto):
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def identidade_tecnica(candidato):
    """Deriva a consulta do endereço do documento ou do catálogo oficial Marine."""
    fabricante = str(candidato.get("fabricante") or "").upper().strip()
    if fabricante not in FABRICANTES:
        return None
    partes = urlparse(str(candidato.get("pdf_url") or ""))
    if partes.scheme != "https" or not partes.hostname or partes.username or partes.password:
        return None
    caminho = unquote(partes.path)
    if (partes.hostname == "www.marinefishing.com.br"
            and candidato.get("origem_url") == "https://www.marinefishing.com.br/manuais"
            and re.fullmatch(r"/manuais/download/\d+/\d+", caminho)):
        nome = str(candidato.get("nome") or "")
    else:
        nome = caminho.rstrip("/").rsplit("/", 1)[-1]
        nome = re.sub(r"\.(?:pdf|jpg|jpeg|png|svg)$", "", nome, flags=re.I)
    if len(nome) > 160 or re.search(r"@|\d{9,}", nome):
        return None
    marcas = set(_norm(fabricante).split()) | {"shiimano"}
    tokens = [t for t in _norm(nome).split() if t not in PALAVRAS_GENERICAS and t not in marcas]
    if not tokens or len(tokens) > 8 or any(len(t) > 24 for t in tokens):
        return None
    if any(t in {"cliente", "telefone", "whatsapp", "endereco", "preco", "custo", "venda", "os"} for t in tokens):
        return None
    palavras = [t for t in tokens if re.search(r"[a-z]", t)]
    if not palavras or len(palavras[0]) < 3:
        return None
    familia = []
    for token in tokens:
        if re.search(r"\d", token):
            if not familia and re.fullmatch(r"\d{2,4}", token):
                continue
            break
        familia.append(token)
    if not familia:
        return None
    tamanho = ""
    for prefixo in busca_vista_catalogo.prefixos_da_familia(fabricante, " ".join(familia)):
        for token in tokens:
            match = re.fullmatch(rf"\d{{0,2}}{re.escape(prefixo.lower())}(\d{{2,4}})[a-z0-9]*", token)
            if match:
                tamanho = match.group(1)
                break
    return {
        "fabricante": fabricante,
        "modelo": " ".join(tokens),
        "familia": " ".join(familia),
        "variantes": [t for t in tokens if re.search(r"\d", t)],
        "tamanho": tamanho,
    }


def _link_publico(url):
    partes = urlparse(str(url or ""))
    if partes.scheme not in {"https", "http"} or not partes.hostname or partes.username or partes.password:
        return False
    host = partes.hostname.lower().rstrip(".")
    if "." not in host or host == "localhost" or host.endswith((".local", ".internal")):
        return False
    try:
        if not ipaddress.ip_address(host).is_global:
            return False
    except ValueError:
        pass
    return bool(
        re.search(r"/(?:threads?|topics?|discussion|comments)/[^/]+", partes.path, re.I)
        or (partes.path.endswith("index.php") and re.fullmatch(r"\d+(?:\.\d+)?", (parse_qs(partes.query).get("topic") or [""])[0]))
    )


def _normalizar_link(url):
    partes = urlparse(html.unescape(url))
    host = (partes.hostname or "").lower()
    if host.endswith("duckduckgo.com") and partes.path.startswith("/l/"):
        url = (parse_qs(partes.query).get("uddg") or [""])[0]
    elif host.endswith("bing.com") and partes.path.startswith("/ck/"):
        codificado = (parse_qs(partes.query).get("u") or [""])[0]
        if not codificado.startswith("a1"):
            return ""
        try:
            dados = codificado[2:]
            url = base64.urlsafe_b64decode(dados + "=" * (-len(dados) % 4)).decode("utf-8")
        except (ValueError, UnicodeError):
            return ""
    return url if _link_publico(url) else ""


class _Resultados(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.em_h2 = False
        self.atual = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "h2":
            self.em_h2 = True
        if tag == "a" and attrs.get("href") and (
                self.em_h2 or "result__a" in attrs.get("class", "").split()):
            self.atual = [attrs["href"], []]

    def handle_data(self, data):
        if self.atual:
            self.atual[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.atual:
            link = _normalizar_link(self.atual[0])
            if link:
                self.links.append((link, " ".join(" ".join(self.atual[1]).split())))
            self.atual = None
        if tag == "h2":
            self.em_h2 = False


class _ResultadosForum(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.atual = None
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "/threads/" in attrs.get("href", ""):
            self.atual = [attrs["href"], []]

    def handle_data(self, data):
        if self.atual:
            self.atual[1].append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.atual:
            url = urljoin(FORUM_BD, self.atual[0])
            titulo = " ".join(" ".join(self.atual[1]).split())
            if _link_publico(url) and urlparse(url).hostname == "www.bdoutdoors.com" and titulo:
                self.links.append((url, titulo))
            self.atual = None


class _Conteudo(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.oculto = 0
        self.em_titulo = False
        self.titulo = []
        self.blocos = []
        self.mensagens = []
        self.bloco = None
        self.idioma = ""

    def handle_starttag(self, tag, attrs):
        if tag == "html":
            atributos = dict(attrs)
            self.idioma = (atributos.get("lang") or atributos.get("xml:lang") or "").lower().replace("_", "-").split("-")[0]
        if tag in {"script", "style", "noscript"}:
            self.oculto += 1
        elif tag == "title":
            self.em_titulo = True
        elif tag in {"p", "article", "div"} and self.bloco is None:
            classes = (dict(attrs).get("class") or "").lower()
            mensagem = any(c in classes for c in ("bbwrapper", "message-body", "postbody", "post-content"))
            if tag == "p" or mensagem:
                self.bloco = [tag, [], mensagem]

    def handle_data(self, data):
        if self.oculto:
            return
        if self.em_titulo:
            self.titulo.append(data)
        if self.bloco is not None:
            self.bloco[1].append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.oculto:
            self.oculto -= 1
        elif tag == "title":
            self.em_titulo = False
        elif self.bloco is not None and tag == self.bloco[0]:
            texto = " ".join(" ".join(self.bloco[1]).split())
            if texto:
                (self.mensagens if self.bloco[2] else self.blocos).append(texto)
            self.bloco = None


class _MensagensPublicas(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.mensagens = []
        self.bloco = None
        self.profundidade = 0
        self.oculto = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.oculto += 1
        if self.oculto:
            return
        classes = (dict(attrs).get("class") or "").lower()
        if self.bloco is None:
            if tag in {"article", "div"} and any(
                classe in classes for classe in ("bbwrapper", "message-body", "postbody", "post-content")
            ):
                self.bloco = []
                self.profundidade = 1
        elif tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.profundidade += 1
        if self.bloco is not None and tag in {"br", "p", "li"}:
            self.bloco.append("\n")

    def handle_data(self, data):
        if self.bloco is not None and not self.oculto:
            self.bloco.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.oculto:
            self.oculto -= 1
            return
        if self.oculto or self.bloco is None:
            return
        if tag in {"p", "li"}:
            self.bloco.append("\n")
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.profundidade -= 1
            if self.profundidade == 0:
                texto = re.sub(r"[ \t\r\f\v]+", " ", "".join(self.bloco))
                texto = re.sub(r"\n[ \t]*\n+", "\n", texto).strip()
                if texto:
                    self.mensagens.append(texto)
                self.bloco = None


def _trecho(blocos, padrao):
    for texto in blocos[:80]:
        if re.search(r"@|(?:\+?\d[\d\s().-]{7,}\d)", texto):
            continue
        normalizado = _norm(texto)
        if re.search(r"\b(?:no|without|never had|sem|nenhum)\s+(?:any\s+)?(?:problems?|issues?|defeitos?|problemas?)\b", normalizado):
            continue
        if re.search(padrao, normalizado, re.I):
            return texto[:120].strip()
    return ""


def analisar_discussao(url, pagina, identidade):
    parser = _Conteudo()
    parser.feed(pagina)
    titulo = " ".join(" ".join(parser.titulo).split())[:160]
    titulo_normalizado = _norm(titulo)
    if not all(token in titulo_normalizado.split() for token in identidade["familia"].split()):
        return None
    if re.search(r"\b(selling|for sale|sale|wanted|wtb|reduced|vendendo|venda)\b|\$", titulo, re.I):
        return None
    if not parser.mensagens:
        return None
    contexto = _norm(titulo + " " + parser.mensagens[0])
    familia = re.escape(identidade["familia"])
    codigo_titulo = re.search(rf"\b{familia}\s+(\d{{2,4}})(?:[a-z]\d?)?\b", titulo_normalizado)
    if codigo_titulo and identidade["tamanho"] and codigo_titulo.group(1) != identidade["tamanho"]:
        return None
    for prefixo in busca_vista_catalogo.prefixos_da_familia(identidade["fabricante"], identidade["familia"]):
        codigos = re.findall(rf"\b\d{{0,2}}{re.escape(prefixo.lower())}\d+[a-z0-9]*\b", titulo_normalizado)
        if codigos and identidade["variantes"] and not any(
                variante.endswith(codigo) or codigo.endswith(variante)
                for codigo in codigos for variante in identidade["variantes"]):
            return None
    sufixo_titulo = re.search(rf"\b{familia}\s+([a-z]{{1,3}})\b", titulo_normalizado)
    palavras_comuns = {"and", "com", "has", "is", "the", "for", "was", "new", "vs", "de"}
    if (sufixo_titulo and identidade["variantes"] and sufixo_titulo.group(1) not in palavras_comuns
            and not any(sufixo_titulo.group(1) in variante for variante in identidade["variantes"])):
        return None
    fabricante_confirmado = all(token in contexto.split() for token in _norm(identidade["fabricante"]).split())
    sintoma = _trecho(parser.mensagens[:1], r"\b(problem|issue|fail|failure|broken|stopped|stuck|slipping|defeito|problema|falha|travou|quebrou|nao funciona)\b")
    if not sintoma or not all(token in _norm(parser.mensagens[0]).split() for token in identidade["familia"].split()):
        return None
    causa = _trecho(parser.mensagens, r"\b(caused by|because|due to|cause was|causado por|devido a|causa foi)\b")
    reparo = _trecho(parser.mensagens, r"\b(fixed|solved|resolved|repaired|resolvido|resolvi|consertado)\b")
    variante = fabricante_confirmado and bool(identidade["variantes"]) and all(
        re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", contexto)
        for token in identidade["variantes"]
    )
    publicas = _MensagensPublicas()
    publicas.feed(pagina)
    publicas.close()
    return {
        "titulo": titulo or "Discussão sobre o equipamento",
        "sintomas": sintoma,
        "causa": causa,
        "reparo": reparo,
        "classificacao": "Não confirmado",
        "escopo": ("Variante" if variante else "Família; variante não confirmada"
                   if fabricante_confirmado else "Possível família; fabricante e variante não confirmados"),
        "url_defeito": url,
        "url_reparo": url if reparo else "",
        "idioma": parser.idioma,
        "titulo_publico": " ".join(" ".join(parser.titulo).split()),
        "mensagens_publicas": tuple(publicas.mensagens),
        "texto_publico_incompleto": publicas.bloco is not None,
    }


@rede_validacao.rede_tecnica
def _buscar_html(url, timeout):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; FRSTechnicalSearch/1.0)"})
    with urlopen(req, timeout=timeout) as response:
        tipo = str(response.headers.get("Content-Type") or "").lower()
        if "html" not in tipo:
            raise ValueError("A fonte não retornou HTML.")
        bruto = response.read(1_000_001)
        if len(bruto) > 1_000_000:
            raise ValueError("Página excede o limite de leitura.")
        charset = re.search(r"charset=([\w.-]+)", tipo)
        return bruto.decode(charset.group(1) if charset else "utf-8", errors="replace"), response.geturl()


class _RedirectForum(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        destino = urlparse(newurl)
        if destino.scheme != "https" or destino.hostname != "www.bdoutdoors.com":
            raise ValueError("Redirecionamento fora do fórum público.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@rede_validacao.rede_tecnica
def _buscar_forum(consulta, timeout, cancelamento=None):
    prazo = time.monotonic() + timeout
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), _RedirectForum())
    cabecalhos = {"User-Agent": "Mozilla/5.0 (compatible; FRSTechnicalSearch/1.0)"}
    with opener.open(Request(FORUM_BD, headers=cabecalhos), timeout=timeout) as response:
        pagina = response.read(1_000_001)
    if len(pagina) > 1_000_000:
        raise ValueError("Formulário de pesquisa excede o limite.")
    texto = pagina.decode("utf-8", errors="replace")
    visivel = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", " ", texto, flags=re.I | re.S)
    if re.search(r"captcha|verify you are human|sign in to continue", re.sub(r"<[^>]*>", " ", visivel), re.I):
        raise PermissionError("bloqueio ou verificação")
    token = re.search(r'<input\b[^>]*name=["\']_xfToken["\'][^>]*value=["\']([^"\']+)', texto, re.I)
    if not token:
        raise ValueError("Formulário público de pesquisa indisponível.")
    if cancelamento is not None and cancelamento.is_set():
        raise InterruptedError("Pesquisa cancelada.")
    dados = urlencode({"keywords": consulta + " problem", "_xfToken": token.group(1)}).encode()
    req = Request(urljoin(FORUM_BD, "search"), data=dados, headers=cabecalhos)
    restante = prazo - time.monotonic()
    if restante <= 0:
        raise TimeoutError("Prazo da fonte esgotado.")
    with opener.open(req, timeout=restante) as response:
        resultado = response.read(1_000_001)
        if len(resultado) > 1_000_000:
            raise ValueError("Resultados do fórum excedem o limite.")
        return resultado.decode("utf-8", errors="replace"), response.geturl()


def _pesquisar_fontes(identidade, cancelamento, emitir, buscar_html, prazo, buscar_forum):
    consulta = f"{identidade['fabricante']} {identidade['modelo']}"
    emitir("status", f"Pesquisando relatos: {consulta}")
    familiar = f"{identidade['fabricante']} {identidade['familia']}"
    busca_familiar = _norm(familiar) != _norm(consulta)
    pool_fontes = concurrent.futures.ThreadPoolExecutor(max_workers=3)
    pools_discussoes = {
        fonte: concurrent.futures.ThreadPoolExecutor(max_workers=4)
        for fonte in (*MOTORES, "Bloodydecks")
    }
    pendentes, vistos, falhas, fontes_indisponiveis = {}, set(), [], set()
    total = 0
    variantes = 0
    finais = set()
    deadline = time.monotonic() + prazo

    def agendar(tipo, fonte, url):
        buscar = buscar_forum if tipo == "forum" else buscar_html
        restante = min(PRAZO_FONTE, max(0.01, deadline - time.monotonic()))
        pool = pools_discussoes[fonte] if tipo == "discussao" else pool_fontes
        def requisitar():
            if cancelamento.is_set():
                raise InterruptedError("Pesquisa cancelada.")
            if tipo == "forum" and buscar is _buscar_forum:
                return buscar(url, restante, cancelamento)
            return buscar(url, restante)
        pendentes[pool.submit(requisitar)] = (tipo, fonte, url, time.monotonic() + restante)

    def agendar_consulta(termo):
        for fonte, modelo_url in MOTORES.items():
            if fonte in fontes_indisponiveis:
                continue
            url = modelo_url.format(quote_plus(termo + " fishing reel problem repair forum"))
            agendar("busca", fonte, url)
        if "Bloodydecks" not in fontes_indisponiveis:
            agendar("forum", "Bloodydecks", termo)

    agendar_consulta(consulta)
    try:
        while not cancelamento.is_set() and time.monotonic() < deadline:
            if not pendentes:
                if busca_familiar and not variantes and len(vistos) < 12:
                    busca_familiar = False
                    emitir("status", "Sem relato confirmado da variante; pesquisando a família.")
                    agendar_consulta(familiar)
                    if not pendentes:
                        break
                else:
                    break
            restante = max(0, deadline - time.monotonic())
            prontos, _ = concurrent.futures.wait(pendentes, timeout=min(0.1, restante), return_when=concurrent.futures.FIRST_COMPLETED)
            for futuro in prontos:
                if cancelamento.is_set():
                    break
                tipo, fonte, url, _ = pendentes.pop(futuro)
                try:
                    pagina, final = futuro.result()
                    visivel = re.sub(r"<(script|style|noscript)\b[^>]*>.*?</\1>", " ", pagina, flags=re.I | re.S)
                    visivel = re.sub(r"<[^>]*>", " ", visivel)
                    if re.search(r"captcha|verify you are human|unusual traffic|sign in to continue", visivel, re.I):
                        raise PermissionError("bloqueio ou verificação")
                    if tipo in {"busca", "forum"}:
                        parser = _ResultadosForum() if tipo == "forum" else _Resultados()
                        parser.feed(pagina)
                        links = [(link, titulo) for link, titulo in parser.links
                                 if all(t in _norm(titulo).split() for t in identidade["familia"].split())]
                        links.sort(key=lambda item: (
                            not all(t in _norm(item[1]).split() for t in identidade["variantes"]),
                            not bool(re.search(r"\b(problem|issue|fail|broken|stuck|defeito|problema|falha|travou)\b",
                                               _norm(item[1]), re.I)),
                        ))
                        adicionados = 0
                        for link, _ in links:
                            chave_link = urldefrag(link)[0]
                            if chave_link not in vistos and adicionados >= 4:
                                falhas.append(f"{fonte}: limite de discussões; pesquisa incompleta")
                                break
                            if chave_link not in vistos and len(vistos) < 12:
                                vistos.add(chave_link)
                                adicionados += 1
                                agendar("discussao", fonte, link)
                            elif chave_link not in vistos:
                                falhas.append("Limite de discussões analisadas; pesquisa incompleta")
                    else:
                        if not _link_publico(final):
                            raise ValueError("Redirecionamento para página não reconhecida como discussão.")
                        item = analisar_discussao(final, pagina, identidade)
                        chave_final = urldefrag(final)[0]
                        if item and chave_final not in finais:
                            finais.add(chave_final)
                            total += 1
                            if item["escopo"] == "Variante":
                                variantes += 1
                            emitir("resultado", item)
                            emitir("status", f"Pesquisando: {total} discussão(ões) encontrada(s).")
                except HTTPError as exc:
                    origem = fonte if tipo in {"busca", "forum"} else (urlparse(url).hostname or "Discussão")
                    if tipo in {"busca", "forum"}:
                        fontes_indisponiveis.add(fonte)
                    detalhe = f"{origem}: HTTP {exc.code}" + (" (bloqueado)" if exc.code in (401, 403, 429) else " (indisponível)")
                    falhas.append(detalhe)
                    emitir("status", f"{detalhe}; demais fontes continuam.")
                except PermissionError:
                    origem = fonte if tipo in {"busca", "forum"} else (urlparse(url).hostname or "Discussão")
                    if tipo in {"busca", "forum"}:
                        fontes_indisponiveis.add(fonte)
                    falhas.append(f"{origem}: bloqueio ou verificação")
                    emitir("status", f"{origem}: bloqueio ou verificação; demais fontes continuam.")
                except (URLError, TimeoutError, OSError, ValueError) as exc:
                    origem = fonte if tipo in {"busca", "forum"} else (urlparse(url).hostname or "Discussão")
                    expirou = isinstance(exc, TimeoutError) or (
                        isinstance(exc, URLError) and isinstance(exc.reason, TimeoutError)
                    )
                    if tipo in {"busca", "forum"}:
                        fontes_indisponiveis.add(fonte)
                    detalhe = "tempo excedido" if expirou else f"indisponível ({type(exc).__name__})"
                    falhas.append(f"{origem}: {detalhe}")
                    emitir("status", f"{origem}: {detalhe}; demais fontes continuam.")
                if cancelamento.is_set():
                    break
            agora = time.monotonic()
            for futuro, (tipo, fonte, url, limite) in list(pendentes.items()):
                if agora >= limite:
                    pendentes.pop(futuro)
                    futuro.cancel()
                    origem = fonte if tipo in {"busca", "forum"} else (urlparse(url).hostname or "Discussão")
                    if tipo in {"busca", "forum"}:
                        fontes_indisponiveis.add(fonte)
                    falhas.append(f"{origem}: tempo excedido")
                    emitir("status", f"{origem}: tempo excedido; demais fontes continuam.")
        if cancelamento.is_set():
            return
        if pendentes or time.monotonic() >= deadline:
            falhas.append("Prazo total da pesquisa esgotado")
        resumo = f"{total} discussão(ões) com possível relato; frequência e reparos não verificados." if total else "Nenhuma discussão correspondente confirmada nesta pesquisa."
        if falhas:
            resumo += " Limitações: " + "; ".join(sorted(set(falhas)))
        emitir("fim", resumo)
    finally:
        pool_fontes.shutdown(wait=False, cancel_futures=True)
        for pool in pools_discussoes.values():
            pool.shutdown(wait=False, cancel_futures=True)


def pesquisar(candidato, cancelamento, emitir, buscar_html=_buscar_html, prazo=PRAZO_TOTAL,
              buscar_forum=_buscar_forum):
    identidade = identidade_tecnica(candidato)
    if not identidade:
        emitir("fim", "Identidade técnica insuficiente; nenhuma consulta externa foi enviada.")
        return
    if cancelamento.is_set():
        return
    chave = (identidade["fabricante"], identidade["modelo"])
    fila = queue.Queue()
    with _lock_pesquisas:
        pesquisa = _pesquisas_ativas.get(chave)
        nova = pesquisa is None
        if nova:
            pesquisa = {"filas": set(), "historico": [], "cancelar": threading.Event()}
            _pesquisas_ativas[chave] = pesquisa
        for evento in pesquisa["historico"]:
            fila.put(evento)
        pesquisa["filas"].add(fila)

        if nova:
            def distribuir(tipo, valor):
                with _lock_pesquisas:
                    evento = (tipo, valor)
                    pesquisa["historico"].append(evento)
                    for destino in pesquisa["filas"]:
                        destino.put(evento)

            def executar():
                try:
                    _pesquisar_fontes(identidade, pesquisa["cancelar"], distribuir, buscar_html, prazo, buscar_forum)
                except Exception as exc:
                    distribuir("fim", f"Falha na pesquisa de relatos: {type(exc).__name__}: {exc}")
                finally:
                    with _lock_pesquisas:
                        if _pesquisas_ativas.get(chave) is pesquisa:
                            del _pesquisas_ativas[chave]

            threading.Thread(target=executar, daemon=True).start()
    try:
        while not cancelamento.is_set():
            try:
                tipo, valor = fila.get(timeout=0.1)
            except queue.Empty:
                continue
            if cancelamento.is_set():
                break
            emitir(tipo, valor)
            if tipo == "fim":
                break
    finally:
        with _lock_pesquisas:
            pesquisa["filas"].discard(fila)
            if not pesquisa["filas"]:
                pesquisa["cancelar"].set()
                if _pesquisas_ativas.get(chave) is pesquisa:
                    del _pesquisas_ativas[chave]
