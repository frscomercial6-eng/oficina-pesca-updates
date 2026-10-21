"""Chave curta FRS — camada de TRANSPORTE, não de segurança.

Cópia fiel do codec do FRS Mercado (referência congelada) para garantir paridade
byte a byte entre emissor e cliente. Alfabeto Crockford Base32 (sem I/L/O/U),
blocos de 5, checksum CRC32 de 4 caracteres.

O QUE ESTE MÓDULO É
-------------------
Uma codificação compacta de um documento que JÁ EXISTE e JÁ É assinado:

    chave de instalação  <->  <SCHEMA>-CHALLENGE  (challenge)
    chave de ativação    <->  <SCHEMA>-LICENSE    (envelope assinado)

O QUE ESTE MÓDULO NÃO É
-----------------------
Ele **não** cria, não substitui e não enfraquece a segurança: a assinatura
continua sendo Ed25519, o schema e o ``key_id`` continuam sendo os oficiais, e
a verificação continua fail-closed. Trocar um caractere altera o Base32 e
invalida a assinatura — adulterar a chave não produz licença válida.

Por que Crockford Base32: a chave vai por WhatsApp, muitas vezes digitada.
Sem I/L/O/U, case-insensitive, tolerante a traço/espaço/quebra de linha, em
blocos de 5. O CRC32 só evita erro de digitação; quem valida é a assinatura.
"""
from __future__ import annotations

import json
import re
import zlib
from typing import Any


#: Alfabeto Crockford: sem I, L, O e U. Dígitos primeiro, depois letras.
ALFABETO = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
PREFIXO_INSTALACAO = "FRS-I-"
PREFIXO_ATIVACAO = "FRS-A-"

#: Tamanho do bloco entre traços, e do checksum final.
TAMANHO_BLOCO = 5
TAMANHO_CHECKSUM = 4

#: Prefixos reconhecidos (a distinção impede colar a chave errada no campo).
PREFIXOS = (PREFIXO_INSTALACAO, PREFIXO_ATIVACAO)

_CARACTERES_INVALIDOS = re.compile(r"[^0-9A-Z]")


class ErroChaveCurta(ValueError):
    """Chave curta ausente, malformada, com checksum errado ou adulterada.

    ``motivo`` é uma palavra por caso de uso na tela; a mensagem para o cliente
    é genérica de propósito, para não ensinar a atacar o formato.
    """

    def __init__(self, motivo: str, mensagem: str):
        super().__init__(mensagem)
        self.motivo = motivo
        self.mensagem = mensagem


def _para_base32(dados: bytes) -> str:
    """Bytes -> Base32 CROCKFORD (o alfabeto ``ALFABETO``, sem I/L/O/U)."""
    if not dados:
        return ""
    acumulador = 0
    bits = 0
    saida = []
    for byte in dados:
        acumulador = (acumulador << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            saida.append(ALFABETO[(acumulador >> bits) & 0x1F])
    if bits:
        saida.append(ALFABETO[(acumulador << (5 - bits)) & 0x1F])
    return "".join(saida)


def _de_base32(texto: str) -> bytes:
    """Base32 Crockford -> bytes. Lança ``ValueError`` em caractere inválido."""
    acumulador = 0
    bits = 0
    saida = bytearray()
    for caractere in texto:
        valor = ALFABETO.index(caractere)  # IndexError -> vira erro de formato
        acumulador = (acumulador << 5) | valor
        bits += 5
        if bits >= 8:
            bits -= 8
            saida.append((acumulador >> bits) & 0xFF)
    return bytes(saida)


def _normalizar_para_base32(texto: str) -> str:
    """Aceita o que a pessoa digita e devolve o alfabeto Crockford puro."""
    limpo = str(texto or "").upper()
    limpo = limpo.replace("O", "0").replace("I", "1").replace("L", "1")
    return _CARACTERES_INVALIDOS.sub("", limpo)


def _checksum(corpo: str) -> str:
    """CRC32 em Base32, com 4 caracteres. Detecta erro de digitação."""
    bruto = zlib.crc32(corpo.encode("ascii")) & 0xFFFFFFFF
    return _para_base32(bruto.to_bytes(4, "big")).rstrip("=")[:TAMANHO_CHECKSUM]


def _formatar(corpo: str) -> str:
    blocos = [corpo[i:i + TAMANHO_BLOCO] for i in range(0, len(corpo), TAMANHO_BLOCO)]
    return "-".join(blocos)


def _documento_para_texto(documento: dict[str, Any]) -> str:
    """Documento -> Base32 canônico (ordenado, sem espaços)."""
    bruto = json.dumps(
        documento, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _para_base32(bruto)


def _gerar(prefixo: str, documento: dict[str, Any]) -> str:
    corpo = _documento_para_texto(documento)
    return f"{prefixo}{_formatar(corpo + _checksum(corpo))}"


def _texto_para_documento(texto: str, prefixo_esperado: str) -> dict[str, Any]:
    """Base32 -> documento, validando prefixo e checksum."""
    bruto = str(texto or "").strip()
    if not bruto:
        raise ErroChaveCurta("vazia", "Nenhuma chave informada.")

    # Procuramos o prefixo em qualquer posição (colar do WhatsApp costuma
    # arrastar texto antes) e ignoramos o que vier antes dele.
    maiusculo = bruto.upper()
    posicao = -1
    encontrado = ""
    for prefixo in PREFIXOS:
        achado = maiusculo.find(prefixo)
        if achado >= 0 and (posicao < 0 or achado < posicao):
            posicao, encontrado = achado, prefixo
    if posicao < 0:
        # Sem prefixo: tratamos o texto inteiro como corpo solto.
        corpo = maiusculo
    else:
        if encontrado != prefixo_esperado:
            raise ErroChaveCurta(
                "prefixo_errado",
                "Esta é uma chave de outro tipo. Confira se colou a chave certa.",
            )
        corpo = maiusculo[posicao + len(encontrado):]
    corpo = _normalizar_para_base32(corpo)
    if not corpo:
        raise ErroChaveCurta("vazia", "Nenhuma chave informada.")

    if len(corpo) <= TAMANHO_CHECKSUM:
        raise ErroChaveCurta("truncada", "Chave incompleta. Copie a chave inteira.")

    informado = corpo[-TAMANHO_CHECKSUM:]
    conteudo = corpo[:-TAMANHO_CHECKSUM]
    if _checksum(conteudo) != informado:
        raise ErroChaveCurta(
            "checksum",
            "Chave com dígito errado ou incompleta. Copie e cole novamente.",
        )

    try:
        dados = _de_base32(conteudo)
        documento = json.loads(dados.decode("utf-8"))
    except Exception as exc:
        raise ErroChaveCurta("formato", "Chave inválida ou adulterada.") from exc

    if not isinstance(documento, dict):
        raise ErroChaveCurta("formato", "Chave inválida ou adulterada.")
    return documento


def gerar_chave_instalacao(challenge: dict[str, Any]) -> str:
    """Challenge -> chave curta de INSTALAÇÃO (``FRS-I-...``)."""
    if not isinstance(challenge, dict):
        raise ErroChaveCurta("vazio", "Challenge de instalação ausente.")
    return _gerar(PREFIXO_INSTALACAO, challenge)


def ler_chave_instalacao(texto: str) -> dict[str, Any]:
    """Chave curta de instalação -> challenge (dicionário)."""
    return _texto_para_documento(texto, PREFIXO_INSTALACAO)


def gerar_chave_ativacao(envelope: dict[str, Any]) -> str:
    """Envelope assinado Ed25519 -> chave curta de ATIVAÇÃO (``FRS-A-...``)."""
    if not isinstance(envelope, dict):
        raise ErroChaveCurta("vazio", "Envelope de licença ausente.")
    return _gerar(PREFIXO_ATIVACAO, envelope)


def ler_chave_ativacao(texto: str) -> dict[str, Any]:
    """Chave curta de ativação -> envelope (pronto para verificação)."""
    return _texto_para_documento(texto, PREFIXO_ATIVACAO)


def parece_chave_curta(texto: str) -> bool:
    """True quando o texto tem cara de chave curta nossa."""
    maiusculo = str(texto or "").strip().upper()
    return any(maiusculo.startswith(prefixo) for prefixo in PREFIXOS)


def tamanho(chave: str) -> int:
    """Quantidade de caracteres útil, sem traços. Útil para diagnóstico."""
    return len(_normalizar_para_base32(str(chave or "")))


__all__ = [
    "ALFABETO", "PREFIXOS", "TAMANHO_BLOCO", "TAMANHO_CHECKSUM",
    "PREFIXO_INSTALACAO", "PREFIXO_ATIVACAO",
    "ErroChaveCurta",
    "gerar_chave_instalacao", "ler_chave_instalacao",
    "gerar_chave_ativacao", "ler_chave_ativacao",
    "parece_chave_curta", "tamanho",
]


