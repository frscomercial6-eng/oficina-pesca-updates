"""Análise de PDFs técnicos sem acesso à aplicação ou ao banco de dados."""
from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import unicodedata

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def normalizar_termo_tecnico(texto, separar_alfanumerico=False):
    base = unicodedata.normalize("NFKD", str(texto or ""))
    base = "".join(char for char in base if not unicodedata.combining(char)).casefold()
    base = re.sub(r"[^a-z0-9]+", " ", base)
    if separar_alfanumerico:
        base = re.sub(r"(?<=[a-z])(?=[0-9])|(?<=[0-9])(?=[a-z])", " ", base)
    romanos = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10"}
    return " ".join(romanos.get(token, token) for token in base.split())


def texto_pdf_ilegivel(texto):
    tokens = [t for t in re.findall(r"\S{5,}", str(texto or "")) if re.search(r"[A-Za-z]", t)]
    if len(tokens) < 8:
        return False
    suspeitos = sum(1 for t in tokens if re.search(r"[A-Za-z][#$&*][A-Za-z0-9]|[#$&*][A-Z]{2,}", t))
    return suspeitos / len(tokens) > 0.3


def peca_parece_dado_pessoal(codigo, descricao=""):
    codigo = str(codigo or "").strip()
    descricao = str(descricao or "")
    digitos = re.sub(r"\D", "", codigo)
    if len(digitos) >= 10 and not re.search(r"[A-Za-z]", codigo):
        return True
    if re.fullmatch(r"\+?\(?\d{2,3}\)?[\s.-]?9?\d{4}[\s.-]\d{4}", codigo) or re.fullmatch(r"\d{5}[\s.-]\d{4}", codigo):
        return True
    if codigo.upper().startswith(("R$", "TEL", "WHATS")):
        return True
    if "@" in codigo or "@" in descricao:
        return True
    return bool(re.search(
        r"(?:\+?\d{2}\s?)?\(?\d{2}\)?\s?9?\d{4}[-\s]\d{4}|\b(?:telefone|whatsapp|fone|cpf|cnpj|n[ºo°]?\s*de\s*s[ée]rie)\b",
        descricao, re.I,
    ))


def extrair_pecas_pdf_texto(texto, pagina):
    pecas = []
    vistos = set()
    inicio_peca = re.compile(
        r"(?<!\S)([0-9]{1,3}(?:-[0-9]{1,3})?[a-z]?)\s{2,}"
        r"([a-z0-9][a-z0-9./_-]{3,39})\s{2,}", re.I
    )
    for linha in str(texto or "").splitlines():
        if not linha.strip() or len(linha) > 400:
            continue
        inicios = list(inicio_peca.finditer(linha))
        if not inicios or inicios[0].start() > 15:
            continue
        for indice, inicio in enumerate(inicios):
            fim = inicios[indice + 1].start() if indice + 1 < len(inicios) else len(linha)
            posicao, codigo = inicio.groups()
            descricao = re.sub(r"\s+", " ", linha[inicio.end():fim]).strip(" .:-")
            if not re.search(r"\d", codigo) or len(descricao) < 3 or not re.search(r"[a-z]", descricao, re.I):
                continue
            if peca_parece_dado_pessoal(codigo, descricao):
                continue
            chave = (posicao.casefold(), codigo.casefold(), descricao.casefold(), pagina)
            if chave in vistos:
                continue
            vistos.add(chave)
            pecas.append({"codigo": codigo, "descricao": descricao, "posicao": posicao, "pagina": pagina})
    return pecas


def analisar_pdf_bytes(corpo, url, fabricante, modelo, cancelamento=None, resultado=None):
    if resultado is None:
        resultado = {"status": "error", "pages": 0, "text_pages": 0, "parts": [],
                     "manufacturer": "", "model": "", "error": ""}
    try:
        reader = PdfReader(io.BytesIO(corpo), strict=False)
        if reader.is_encrypted:
            resultado.update(status="unavailable", error="PDF protegido por senha.")
            return resultado
        resultado["pages"] = len(reader.pages)
        page_limit = min(len(reader.pages), 150)
        textos = []
        for index in range(page_limit):
            if cancelamento is not None and cancelamento.is_set():
                resultado["status"] = "cancelled"
                return resultado
            try:
                pagina = reader.pages[index]
                try:
                    texto_pagina = pagina.extract_text(extraction_mode="layout") or ""
                except TypeError:
                    texto_pagina = pagina.extract_text() or ""
                if not texto_pagina.strip():
                    texto_pagina = pagina.extract_text() or ""
            except Exception:
                logger.exception("Falha ao extrair texto da página %s em %s.", index + 1, url)
                texto_pagina = ""
            if texto_pagina.strip():
                resultado["text_pages"] += 1
                textos.append(texto_pagina)
                resultado["parts"].extend(extrair_pecas_pdf_texto(texto_pagina, index + 1))
        texto_documento = "\n".join(textos)
        metadata = reader.metadata
        metadata_text = " ".join(
            str(getattr(metadata, campo, "") or "")
            for campo in ("/Title", "/Author", "/Subject", "/Keywords")
        ) if metadata else ""
        texto_normalizado = normalizar_termo_tecnico(f"{metadata_text} {texto_documento}")
        fabricante_normalizado = normalizar_termo_tecnico(fabricante)
        if fabricante_normalizado and all(token in texto_normalizado.split() for token in fabricante_normalizado.split()):
            resultado["manufacturer"] = fabricante
        modelo_tokens = [token for token in normalizar_termo_tecnico(modelo).split() if len(token) > 1]
        if modelo_tokens and all(token in texto_normalizado.split() for token in modelo_tokens):
            resultado["model"] = modelo
        resultado["parts"] = resultado["parts"][:500]
        if texto_pdf_ilegivel(texto_documento):
            resultado["parts"] = []
            resultado.update(status="unreadable_text", error="O texto do PDF usa codificação de fonte ilegível; peças não extraídas.")
        elif len(reader.pages) > page_limit:
            resultado.update(status="page_limit", error="Leitura limitada às primeiras 150 páginas.")
        elif resultado["text_pages"] == 0:
            resultado.update(status="scanned", error="PDF sem texto extraível; pode ser digitalizado como imagem. OCR não é realizado.")
        elif not resultado["parts"]:
            resultado.update(status="text_only", error="Texto extraído, mas sem linhas de peças com relação confiável.")
        else:
            resultado["status"] = "extracted"
    except Exception as exc:
        logger.info("Não foi possível ler o PDF técnico %s: %s", url, exc)
        resultado.update(status="error", error=f"{type(exc).__name__}: {exc}")
    return resultado


def analisar_em_processo(corpo, url, fabricante, modelo, cancelamento=None, timeout=60):
    if cancelamento is not None and cancelamento.is_set():
        return {"status": "cancelled", "parts": []}
    if getattr(sys, "frozen", False):
        with tempfile.TemporaryDirectory(prefix="ofp_pdf_") as pasta:
            entrada = os.path.join(pasta, "entrada.pdf")
            saida = os.path.join(pasta, "resultado.json")
            with open(entrada, "wb") as arquivo:
                arquivo.write(corpo)
            comando = [
                sys.executable, "--ofp-busca-vista-pdf-worker", entrada, saida,
                json.dumps([url, fabricante, modelo], ensure_ascii=True),
            ]
            processo = subprocess.Popen(
                comando, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            prazo = time.monotonic() + timeout
            try:
                while True:
                    if cancelamento is not None and cancelamento.is_set():
                        raise InterruptedError("Análise cancelada.")
                    restante = prazo - time.monotonic()
                    if restante <= 0:
                        raise TimeoutError("Prazo da análise do PDF esgotado.")
                    try:
                        _, erro = processo.communicate(timeout=min(0.1, restante))
                        break
                    except subprocess.TimeoutExpired:
                        pass
                if processo.returncode:
                    raise RuntimeError(f"Falha no processo de análise: {erro.decode('utf-8', 'replace')[-1000:]}")
                with open(saida, "r", encoding="utf-8") as arquivo:
                    return json.load(arquivo)
            finally:
                if processo.poll() is None:
                    processo.kill()
                    processo.communicate()
    cabecalho = json.dumps([url, fabricante, modelo], ensure_ascii=True).encode("ascii") + b"\n"
    processo = subprocess.Popen(
        [sys.executable, "-u", os.path.abspath(__file__), "--worker"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    prazo = time.monotonic() + timeout
    entrada = cabecalho + corpo
    try:
        while True:
            if cancelamento is not None and cancelamento.is_set():
                raise InterruptedError("Análise cancelada.")
            restante = prazo - time.monotonic()
            if restante <= 0:
                raise TimeoutError("Prazo da análise do PDF esgotado.")
            try:
                saida, erro = processo.communicate(input=entrada, timeout=min(0.1, restante))
                break
            except subprocess.TimeoutExpired:
                entrada = None
        if processo.returncode:
            raise RuntimeError(f"Falha no processo de análise: {erro.decode('utf-8', 'replace')[-1000:]}")
        return json.loads(saida.decode("utf-8"))
    finally:
        if processo.poll() is None:
            processo.kill()
            processo.communicate()


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    url, fabricante, modelo = json.loads(sys.stdin.buffer.readline())
    corpo = sys.stdin.buffer.read()
    resposta = analisar_pdf_bytes(corpo, url, fabricante, modelo)
    sys.stdout.buffer.write(json.dumps(resposta, ensure_ascii=True).encode("utf-8"))
