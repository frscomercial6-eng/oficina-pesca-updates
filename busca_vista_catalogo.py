"""Descoberta de variações de modelos (PDFs de diagramas) para a Busca Vista.

Módulo sem dependência de interface nem de banco de dados. Recebe apenas fabricante e
modelo técnico já validados; nunca recebe texto livre da OS.
"""
from __future__ import annotations

import html
import re
import threading
import time
import unicodedata
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

REELSCHEMATIC_HOST = "www.reelschematic.com"
REELSCHEMATIC_RAIZ = f"https://{REELSCHEMATIC_HOST}/reel-schematics/"
MAX_FAMILIAS = 3
LIMITE_VARIANTES = 400
MANUAIS_MARINE_URL = "https://www.marinefishing.com.br/manuais"

_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()
_VALIDADE_CACHE = 300.0
_LIMITE_CACHE = 64


def limpar_cache_catalogo() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


class _ManuaisMarineParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.documentos = []
        self._link = None
        self._capturando_nome = False
        self._nome = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "download-link" in attrs.get("class", "").split():
            url = urljoin(MANUAIS_MARINE_URL, attrs.get("href", ""))
            partes = urlparse(url)
            if (partes.scheme == "https" and partes.hostname == "www.marinefishing.com.br"
                    and re.fullmatch(r"/manuais/download/\d+/\d+", partes.path)
                    and not partes.query and not partes.fragment):
                self._link = url
                self._nome = []
        elif self._link and tag == "div" and "text1" in attrs.get("class", "").split():
            self._capturando_nome = True

    def handle_data(self, data):
        if self._link and self._capturando_nome:
            self._nome.append(data)

    def handle_endtag(self, tag):
        if tag == "div" and self._capturando_nome:
            self._capturando_nome = False
        if tag == "a" and self._link:
            nome = re.sub(r"\s+", " ", " ".join(self._nome)).strip()
            nome = re.sub(r"\.pdf$", "", nome, flags=re.I).strip()
            if nome:
                self.documentos.append((nome, self._link))
            self._link = None
            self._capturando_nome = False


def parse_manuais_marine(html_bruto: str) -> list[dict]:
    parser = _ManuaisMarineParser()
    parser.feed(html_bruto)
    documentos, vistos = [], set()
    for nome, url in parser.documentos:
        if url in vistos:
            continue
        vistos.add(url)
        categoria = _norm(nome).split()[:1]
        if not categoria or categoria[0] not in {"carretilha", "molinete"}:
            continue
        documentos.append({
            "fabricante": "MARINE SPORTS",
            "familia": categoria[0].upper(),
            "nome": nome,
            "codigo": codigo_da_variacao(nome),
            "pdf_url": url,
            "fonte": "Marine Fishing",
            "origem_url": MANUAIS_MARINE_URL,
            "verificado": False,
        })
    return documentos


def filtrar_manuais_marine(documentos: list[dict], modelo: str, categoria: str = "") -> list[dict]:
    """Compara localmente a identificação inteira com o início do nome oficial."""
    def tokens(texto):
        texto = _norm(texto)
        texto = re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", texto)
        return texto.split()

    procurados = tokens(modelo)
    categoria = _norm(categoria)
    candidatos = []

    def corresponde(oficial, prefixos_numericos):
        i = j = 0
        while i < len(procurados):
            if j < len(oficial) and procurados[i] == oficial[j]:
                i += 1
                j += 1
            elif (i > 0 and procurados[i].isdigit() and j + 1 < len(oficial)
                  and (oficial[j], procurados[i]) in prefixos_numericos
                  and oficial[j + 1] == procurados[i]):
                j += 1
            else:
                return False
        return True

    for item in documentos:
        nome = tokens(item["nome"])
        if not nome or (categoria and nome[0] != categoria):
            continue
        modelo_oficial = nome[1:]
        prefixos_numericos = {
            (prefixo.lower(), numero) for prefixo, numero in
            re.findall(r"\b([A-Za-z]{1,3})\s*-\s*(\d+)\b", item["nome"])
        }
        if procurados and not corresponde(modelo_oficial, prefixos_numericos):
            continue
        candidatos.append(item)
    return sorted(candidatos, key=lambda item: (
        tokens(item["nome"])[1:] != procurados if procurados else False,
        _norm(item["nome"]),
    ))


def _norm(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or ""))
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()


def _junto(texto: str) -> str:
    return _norm(texto).replace(" ", "")


def eh_url_pdf_reelschematic(url: str) -> bool:
    partes = urlparse(str(url or ""))
    return (
        partes.scheme == "https"
        and partes.hostname == REELSCHEMATIC_HOST
        and partes.path.lower().endswith(".pdf")
        and "/wp-content/uploads/" in partes.path
    )


def codigo_da_variacao(nome: str) -> str:
    """Último termo com dígito do nome (ex.: 'Shimano Curado CUMGL151XG' -> 'CUMGL151XG')."""
    tokens = [t for t in re.split(r"\s+", str(nome or "").strip()) if t]
    for token in reversed(tokens):
        if re.search(r"\d", token):
            return token
    return ""


def parse_variantes_reelschematic(html_bruto: str, base_url: str, fabricante: str = "", familia: str = "") -> list[dict]:
    """Extrai (nome, código, PDF) dos links do visualizador do Reel Schematics, sem duplicatas."""
    variantes = []
    vistos = set()
    for href in re.findall(r"""href=["']([^"']*schematic-viewer/\?[^"']+)["']""", html_bruto or "", re.I):
        link = urljoin(base_url, html.unescape(href))
        consulta = parse_qs(urlparse(link).query)
        pdf = (consulta.get("rs_doc") or [""])[0]
        nome = re.sub(r"\s+", " ", (consulta.get("rs_model") or [""])[0]).strip()
        if not eh_url_pdf_reelschematic(pdf) or not nome:
            continue
        chave = unquote(pdf).casefold()
        if chave in vistos:
            continue
        vistos.add(chave)
        variantes.append({
            "fabricante": fabricante,
            "familia": familia,
            "nome": nome,
            "codigo": codigo_da_variacao(nome),
            "pdf_url": pdf,
            "fonte": "Reel Schematics",
            "origem_url": base_url,
            "verificado": False,
        })
        if len(variantes) >= LIMITE_VARIANTES:
            break
    return variantes


def _slug_tokens(href: str) -> list[str]:
    caminho = urlparse(href).path.strip("/").split("/")
    return _norm(caminho[-1] if caminho else "").split()


def _links_da_pagina(html_bruto: str, base_url: str) -> list[str]:
    encontrados = []
    for href in re.findall(r"""href=["']([^"'#]+)["']""", html_bruto or "", re.I):
        link = urljoin(base_url, html.unescape(href)).split("?")[0]
        if urlparse(link).hostname == REELSCHEMATIC_HOST and "/reel-schematics/" in link:
            encontrados.append(link if link.endswith("/") else link + "/")
    return list(dict.fromkeys(encontrados))


def separar_modelo(modelo: str):
    """Divide o modelo em palavras de família (nome) e termos de variação (números/códigos)."""
    familia, variacao = [], []
    for token in _norm(modelo).split():
        if re.fullmatch(r"[a-z]{3,}", token):
            familia.append(token)
        else:
            variacao.append(token)
    return familia, variacao


def consulta_eh_exata(modelo: str) -> bool:
    """Exata = traz um código técnico completo (letras e dígitos), não só um número de família."""
    _, variacao = separar_modelo(modelo)
    return any(len(t) >= 5 and re.search(r"[a-z]", t) and re.search(r"\d", t) for t in variacao)


# Prefixos que os fabricantes usam nos códigos de catálogo, confirmados em documentos reais
# (ex.: Shimano Curado -> 12CU200G6, 09CU300E, 18CUDC150). Só entram aqui equivalências comprovadas.
PREFIXOS_TECNICOS: dict[tuple[str, str], tuple[str, ...]] = {
    ("SHIMANO", "CURADO"): ("CU",),
}


def prefixos_da_familia(fabricante: str, familia: str) -> tuple[str, ...]:
    fab = _norm(fabricante).upper()
    palavras = set(_norm(familia).upper().split())
    achados = []
    for (f, fam), prefixos in PREFIXOS_TECNICOS.items():
        if f == fab and set(fam.split()) <= palavras:
            achados.extend(prefixos)
    return tuple(achados)


def identificadores_tecnicos(fabricante: str, modelo: str) -> list[str]:
    """Identificadores técnicos internos (ex.: 'SHIMANO CURADO 200 G6' -> 'CU200G6', 'CU-200 G6').

    Só deriva do fabricante/família/modelo validados; nunca de texto livre.
    """
    familia, variacao = separar_modelo(modelo)
    prefixos = prefixos_da_familia(fabricante, " ".join(familia))
    if not prefixos:
        return []
    minusculos = {p.lower() for p in prefixos}
    variacao = [t for t in variacao if t not in minusculos]
    if not variacao or not variacao[0].isdigit():
        return []
    tamanho, sufixos = variacao[0], [t.upper() for t in variacao[1:]]
    ids = []
    for p in prefixos:
        ids.append(f"{p}{tamanho}{''.join(sufixos)}")
        ids.append(f"{p}-{tamanho}" + (" " + " ".join(sufixos) if sufixos else ""))
    return list(dict.fromkeys(ids))


def correspondencia_inequivoca(candidatos: list[dict], modelo: str) -> bool:
    """Um único candidato e a consulta traz código completo ou tamanho + variante (ex.: '200 G6')."""
    if len(candidatos) != 1:
        return False
    if consulta_eh_exata(modelo):
        return True
    _, variacao = separar_modelo(modelo)
    return any(t.isdigit() for t in variacao) and any(re.search(r"[a-z]", t) for t in variacao)


def _token_casa(token: str, codigo_junto: str, nome_tokens: set[str], prefixos=()) -> bool:
    if token in nome_tokens or token == codigo_junto:
        return True
    if prefixos and not token.isdigit() and len(token) < 5 and re.search(r"[a-z]", token):
        # Variante curta (G6, DC): precisa estar após o prefixo técnico; G6 não pode virar G60.
        resto = re.sub(rf"^\d{{0,2}}(?:{'|'.join(map(re.escape, prefixos))})", "", codigo_junto)
        return re.search(rf"{re.escape(token)}(?!\d)" if token[-1].isdigit() else re.escape(token), resto) is not None
    if token.isdigit():
        return re.search(rf"(?<!\d){re.escape(token)}(?!\d)", codigo_junto) is not None
    if len(token) >= 3:
        return token in codigo_junto
    return codigo_junto.endswith(token)


def filtrar_variantes(variantes: list[dict], modelo: str) -> list[dict]:
    """Mantém só variações compatíveis com os termos de variação do modelo pesquisado."""
    familia_consulta, variacao = separar_modelo(modelo)
    if not variacao:
        return [
            item for item in variantes
            if not item.get("familia") or all(
                palavra in set(_norm(item.get("familia")).split()) | set(_norm(item.get("nome")).split())
                for palavra in familia_consulta
            )
        ]
    # Sufixos como XG/HG isolados e números romanos não identificam sozinhos.
    resultado = []
    for item in variantes:
        codigo_junto = _junto(item.get("codigo") or item.get("nome"))
        nome_tokens = set(_norm(item.get("nome")).split())
        # Mesmo tamanho/código em outra família não é o mesmo equipamento.
        familia_item = set(_norm(item.get("familia")).split())
        if familia_item and not all(w in familia_item or w in nome_tokens for w in familia_consulta):
            continue
        prefixos = tuple(p.lower() for p in prefixos_da_familia(item.get("fabricante"), item.get("familia")))
        # Quem digita o prefixo técnico (CU) não precisa ser obrigado a tê-lo no código.
        termos = [t for t in variacao if t not in prefixos] if prefixos else variacao
        if all(_token_casa(t, codigo_junto, nome_tokens, prefixos) for t in termos):
            resultado.append(item)
    if consulta_eh_exata(modelo):
        iguais = [i for i in resultado if _junto(i.get("codigo")) in {t for t in variacao}]
        if len(iguais) == 1:
            return iguais
    return resultado


def descobrir_variantes_reelschematic(fabricante: str, modelo: str, buscar_html, cancelado=None):
    """Navega marca -> família -> variações no Reel Schematics.

    `buscar_html(url)` devolve o HTML ou levanta exceção. Retorna (variantes, estado, mensagem)
    onde estado é 'ok', 'sem_resultado', 'incompleto' ou 'cancelado'. Só 'ok'/'sem_resultado'
    são cacheáveis.
    """
    def parou():
        return cancelado is not None and cancelado.is_set()

    marca = _norm(fabricante).replace(" ", "-")
    familia_palavras, _ = separar_modelo(modelo)
    if not marca or not familia_palavras:
        return [], "sem_resultado", "Modelo sem nome de família identificável."
    chave = f"{marca}|{' '.join(familia_palavras)}"
    with _CACHE_LOCK:
        entrada = _CACHE.get(chave)
        if entrada and time.monotonic() - entrada[0] < _VALIDADE_CACHE:
            todas = [dict(v) for v in entrada[1]]
            return filtrar_variantes(todas, modelo), "ok", ""

    falhas = []

    def obter(url):
        try:
            return buscar_html(url)
        except Exception as exc:  # falha de rede/bloqueio: não vira "sem resultado"
            falhas.append(f"{type(exc).__name__}")
            return ""

    pagina_marca, url_marca = "", ""
    for candidata in (f"{REELSCHEMATIC_RAIZ}{marca}-reel-schematics/", f"{REELSCHEMATIC_RAIZ}{marca}-schematics/"):
        if parou():
            return [], "cancelado", ""
        pagina_marca = obter(candidata)
        if pagina_marca and "schematic" in pagina_marca.lower():
            url_marca = candidata
            break
    if not url_marca:
        if falhas:
            return [], "incompleto", f"Reel Schematics indisponível ({falhas[0]})."
        return [], "sem_resultado", "Marca não encontrada no Reel Schematics."

    familias = []
    for link in _links_da_pagina(pagina_marca, url_marca):
        if link == url_marca or not link.startswith(url_marca):
            continue
        tokens = _slug_tokens(link)
        pontos = sum(1 for p in familia_palavras if p in tokens)
        if pontos:
            familias.append((pontos, link))
    familias.sort(key=lambda x: -x[0])
    todas = []
    if len(familias) > MAX_FAMILIAS:
        falhas.append("limite de famílias atingido")
    for _, link in familias[:MAX_FAMILIAS]:
        if parou():
            return [], "cancelado", ""
        pagina = obter(link)
        if not pagina:
            continue
        nome_familia = " ".join(t.upper() for t in _slug_tokens(link) if t not in {"schematics", "reel", marca})
        variantes = parse_variantes_reelschematic(pagina, link, fabricante.upper(), nome_familia)
        if len(variantes) >= LIMITE_VARIANTES:
            falhas.append("limite de variantes atingido")
        todas.extend(variantes)
    if parou():
        return [], "cancelado", ""
    if falhas:
        return filtrar_variantes(todas, modelo), "incompleto", f"Reel Schematics respondeu parcialmente ({falhas[0]})."
    unicas = {}
    for v in todas:
        # A identificação completa evita mesclar códigos iguais de modelos/anos diferentes.
        nome = _junto(v.get("nome")).replace("shiimano", "shimano")
        id_var = (_junto(v.get("familia")), nome or unquote(v["pdf_url"]).casefold())
        atual = unicas.get(id_var)
        if atual is None or ("shiimano" in _norm(atual["nome"]) and "shiimano" not in _norm(v["nome"])):
            unicas[id_var] = v
    todas = list(unicas.values())
    with _CACHE_LOCK:
        if len(_CACHE) >= _LIMITE_CACHE and chave not in _CACHE:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[chave] = (time.monotonic(), [dict(v) for v in todas])
    return filtrar_variantes(todas, modelo), ("ok" if todas else "sem_resultado"), ""


def variantes_de_pdfs_genericos(resultados: list[dict], fabricante: str, modelo: str) -> list[dict]:
    """Converte PDFs de outras fontes em candidatos identificados pelo nome do arquivo."""
    candidatos = []
    for item in resultados or []:
        url = str(item.get("url") or "")
        caminho = urlparse(url).path
        if not caminho.lower().endswith(".pdf"):
            continue
        nome = re.sub(r"\.pdf$", "", unquote(caminho.rsplit("/", 1)[-1]), flags=re.I)
        nome = re.sub(r"[_+]+", " ", nome).strip()
        if not nome:
            continue
        candidatos.append({
            "fabricante": fabricante,
            "familia": "",
            "nome": nome,
            "codigo": codigo_da_variacao(nome),
            "pdf_url": url,
            "fonte": item.get("source") or urlparse(url).hostname or "",
            "origem_url": url,
            "verificado": False,
        })
    familia, _ = separar_modelo(modelo)
    return [c for c in filtrar_variantes(candidatos, modelo)
            if not familia or any(p in _norm(c["nome"]).split() or p in _norm(c["pdf_url"]) for p in familia)]


def combinar_candidatos(*listas: list[dict]) -> list[dict]:
    vistos, final = set(), []
    for lista in listas:
        for item in lista:
            chave = unquote(item["pdf_url"]).casefold()
            if chave not in vistos:
                vistos.add(chave)
                final.append(item)
    return sorted(final, key=lambda i: (_norm(i.get("familia")), _norm(i.get("nome"))))
