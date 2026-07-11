# -*- coding: utf-8 -*-
import unicodedata

STATUS_ORCAMENTO = "ORÇAMENTO"
STATUS_AGUARDANDO_ORCAMENTO = "AGUARDANDO ORÇAMENTO"
STATUS_ORCAMENTO_ALIASES = (
    "AGUARDANDO",
    "ORCAMENTO",
    "ORÇAMENTO",
)
STATUS_AGUARDANDO_ORCAMENTO_ALIASES = (
    "AGUARDANDO ORCAMENTO",
    "AGUARDANDO ORÇAMENTO",
)


def _normalizar_texto(valor: str) -> str:
    texto = str(valor or "").strip().upper()
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    return " ".join(texto.split())


def normalizar_status_orcamento(status: str) -> str:
    bruto = str(status or "").strip().upper()
    sem_acento = _normalizar_texto(bruto)

    if sem_acento in ("AGUARDANDO", "ORCAMENTO"):
        return STATUS_ORCAMENTO

    if sem_acento == "AGUARDANDO ORCAMENTO":
        return STATUS_AGUARDANDO_ORCAMENTO

    return bruto


def is_status_orcamento(status: str) -> bool:
    sem_acento = _normalizar_texto(status)
    return sem_acento in ("AGUARDANDO", "ORCAMENTO")


def is_status_aguardando_orcamento(status: str) -> bool:
    sem_acento = _normalizar_texto(status)
    return sem_acento == "AGUARDANDO ORCAMENTO"
