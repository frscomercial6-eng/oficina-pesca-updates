# -*- coding: utf-8 -*-
"""Módulo simples de internacionalização (i18n) para o projeto."""

from __future__ import annotations

import configparser
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
LOCALES_DIR = BASE_DIR / "locales"


def _ler_idioma_config_cfg() -> str | None:
    """Le [idioma] idioma_atual em config.cfg, se o arquivo existir."""
    caminho_cfg = BASE_DIR / "config.cfg"
    if not caminho_cfg.exists():
        return None
    try:
        cfg = configparser.ConfigParser()
        cfg.read(caminho_cfg, encoding="utf-8")
        valor = cfg.get("idioma", "idioma_atual", fallback="").strip()
        return valor or None
    except Exception:
        return None


DEFAULT_LOCALE = os.getenv("OFICINA_LOCALE", "").strip() or _ler_idioma_config_cfg() or "pt_BR"

_CURRENT_LOCALE = DEFAULT_LOCALE


def get_default_locale() -> str:
    """Retorna o idioma padrão configurado para a aplicação."""
    return DEFAULT_LOCALE


def set_default_locale(locale: str | None) -> str:
    """Define o idioma padrão da aplicação e aplica o idioma imediatamente."""
    global DEFAULT_LOCALE
    locale_name = (locale or os.getenv("OFICINA_LOCALE", DEFAULT_LOCALE) or "pt_BR").strip()
    if locale_name not in {"pt_BR", "es_UY", "en_US"}:
        locale_name = "pt_BR"
    DEFAULT_LOCALE = locale_name
    os.environ["OFICINA_LOCALE"] = locale_name
    set_locale(locale_name)
    return DEFAULT_LOCALE


@lru_cache(maxsize=16)
def _load_locale(locale: str) -> dict[str, Any]:
    """Carrega um arquivo JSON de idioma e o mantém em cache."""
    locale_name = locale or DEFAULT_LOCALE
    file_path = LOCALES_DIR / f"{locale_name}.json"

    if not file_path.exists():
        if locale_name != DEFAULT_LOCALE:
            return _load_locale(DEFAULT_LOCALE)
        return {}

    with file_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle) or {}

    return {str(k): str(v) for k, v in data.items()}


def set_locale(locale: str) -> str:
    """Define o idioma ativo para a aplicação."""
    global _CURRENT_LOCALE
    locale_name = locale or DEFAULT_LOCALE
    file_path = LOCALES_DIR / f"{locale_name}.json"
    if not file_path.exists() and locale_name != DEFAULT_LOCALE:
        locale_name = DEFAULT_LOCALE
    _CURRENT_LOCALE = locale_name
    return locale_name


def get_current_locale() -> str:
    """Retorna o idioma ativo no momento."""
    return _CURRENT_LOCALE


def get_text(key: str, locale: str | None = None, default: str | None = None) -> str:
    """Busca o texto traduzido para a chave informada."""
    active_locale = locale or _CURRENT_LOCALE
    translations = _load_locale(active_locale)

    if key in translations and translations[key]:
        return translations[key]

    if active_locale != DEFAULT_LOCALE:
        fallback = _load_locale(DEFAULT_LOCALE)
        if key in fallback and fallback[key]:
            return fallback[key]

    return default or key


def t(key: str, locale: str | None = None, default: str | None = None) -> str:
    """Alias curto para get_text."""
    return get_text(key, locale=locale, default=default)


# Exemplo de uso nas telas:
# from core.i18n import t
# ctk.CTkLabel(self, text=t("btn_salvar")).pack()
