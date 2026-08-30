# -*- coding: utf-8 -*-
"""Módulo simples de internacionalização (i18n) para o projeto.

Garante que o dicionário em português (pt_BR) seja carregado na
inicialização da aplicação e que NENHUMA chave faltante apareça na tela
como texto interno (ex.: "BTN_IMPRIMIR_DANFE_PDV", "titulo_pdv").

Características:
- Resolve a pasta ``locales`` em vários cenários: código-fonte, executável
  PyInstaller (onefile/onedir com ``_internal``) e diretório de trabalho.
- Idioma 100% automático, com fallback ``pt_BR``
  (env ``OFICINA_LOCALE`` > idioma detectado no sistema operacional >
  ``config.cfg`` > pt_BR).
- Pré-carrega o dicionário padrão no import do módulo.
- Busca tolerante: chave exata -> chave em minúsculas -> idioma ativo ->
  pt_BR -> ``default`` -> própria chave (nunca levanta exceção).
"""

from __future__ import annotations

import configparser
import json
import os
import sys
from pathlib import Path
from typing import Any

try:  # Detecção de idioma do Windows (módulo autônomo, sem dependência circular)
    from core.eula import detectar_idioma_sistema
except Exception:  # pragma: no cover - fallback defensivo
    def detectar_idioma_sistema() -> str:  # type: ignore[misc]
        return ""

SUPPORTED_LOCALES = ("pt_BR", "es_UY", "en_US")
DEFAULT_FALLBACK_LOCALE = "pt_BR"

# ---------------------------------------------------------------------------
# Resolução de diretórios (fonte, PyInstaller onefile, onedir/_internal, exe)
# ---------------------------------------------------------------------------


def _candidate_base_dirs() -> list[Path]:
    """Caminhos plausíveis onde a pasta ``locales`` pode estar."""
    candidatos: list[Path] = []

    # PyInstaller onefile: arquivos de dados extraídos em _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.append(Path(meipass))

    # Execução pelo código-fonte: <projeto>/core/i18n.py -> <projeto>
    try:
        modulo_dir = Path(__file__).resolve().parent
        candidatos.append(modulo_dir.parent)
    except Exception:
        pass

    # Executável congelado (onedir): exe na raiz e dados em _internal
    if getattr(sys, "frozen", False):
        try:
            exe_dir = Path(sys.executable).resolve().parent
            candidatos.append(exe_dir)
            candidatos.append(exe_dir / "_internal")
        except Exception:
            pass

    # Último recurso: diretório de trabalho atual
    try:
        candidatos.append(Path.cwd())
    except Exception:
        pass

    return candidatos


def _encontrar_locales_dir() -> Path:
    """Retorna o primeiro diretório ``locales`` que contenha algum JSON."""
    for base in _candidate_base_dirs():
        pasta = base / "locales"
        if pasta.is_dir() and any(pasta.glob("*.json")):
            return pasta
    # Fallback histórico: <raiz do projeto>/locales ao lado do pacote core
    try:
        return Path(__file__).resolve().parent.parent / "locales"
    except Exception:
        return Path.cwd() / "locales"


BASE_DIR = _candidate_base_dirs()[0] if _candidate_base_dirs() else Path.cwd()
LOCALES_DIR = _encontrar_locales_dir()


# ---------------------------------------------------------------------------
# Leitura do idioma configurado (env OFICINA_LOCALE > config.cfg > pt_BR)
# ---------------------------------------------------------------------------


def _ler_idioma_config_cfg() -> str | None:
    """Lê [idioma] idioma_atual do config.cfg, se existir."""
    caminhos = list(_candidate_base_dirs())
    # Garante também o config.cfg clássico ao lado do pacote core/
    try:
        caminhos.append(Path(__file__).resolve().parent.parent / "config.cfg")
    except Exception:
        pass
    for base in caminhos:
        caminho_cfg = base / "config.cfg" if base.suffix != ".cfg" else base
        if not caminho_cfg.exists():
            continue
        try:
            cfg = configparser.ConfigParser()
            cfg.read(caminho_cfg, encoding="utf-8")
            valor = cfg.get("idioma", "idioma_atual", fallback="").strip()
            if valor:
                return valor
        except Exception:
            continue
    return None


def _normalizar_locale(locale: str | None) -> str:
    """Valida o nome do idioma; aceita variações (pt-br, PT_BR, en-US...)."""
    nome = (locale or "").strip().replace("-", "_").replace(".", "_")
    mapa = {v.lower(): v for v in SUPPORTED_LOCALES}
    return mapa.get(nome.lower(), "")


def _resolver_locale_inicial() -> str:
    return (
        _normalizar_locale(os.getenv("OFICINA_LOCALE", ""))
        or _normalizar_locale(_ler_idioma_config_cfg())
        or DEFAULT_FALLBACK_LOCALE
    )


DEFAULT_LOCALE = _resolver_locale_inicial()
_CURRENT_LOCALE = DEFAULT_LOCALE

# ---------------------------------------------------------------------------
# Cache de traduções (com suporte a recarga e busca sem diferenciar maiúsculas)
# ---------------------------------------------------------------------------

_cache_traducoes: dict[str, dict[str, str]] = {}
_cache_indices: dict[str, dict[str, str]] = {}  # chave minúscula -> chave real


def _indexar(dados: dict[str, str]) -> dict[str, str]:
    return {str(k).strip().lower(): k for k in dados}


def _load_locale(locale: str) -> dict[str, Any]:
    """Carrega (com cache) o dicionário de traduções de um idioma."""
    nome = _normalizar_locale(locale) or DEFAULT_LOCALE
    if nome in _cache_traducoes:
        return _cache_traducoes[nome]

    dados: dict[str, str] = {}
    arquivo = LOCALES_DIR / f"{nome}.json"
    if arquivo.exists():
        try:
            with arquivo.open("r", encoding="utf-8") as handle:
                bruto = json.load(handle) or {}
            dados = {str(k): str(v) for k, v in bruto.items() if v is not None}
        except Exception:
            dados = {}

    if not dados and nome != DEFAULT_LOCALE:
        return _load_locale(DEFAULT_LOCALE)

    _cache_traducoes[nome] = dados
    _cache_indices[nome] = _indexar(dados)
    return dados


def reload_translations() -> None:
    """Descarta o cache e recarrega os JSONs do disco (útil pós-instalação)."""
    global LOCALES_DIR
    _cache_traducoes.clear()
    _cache_indices.clear()
    LOCALES_DIR = _encontrar_locales_dir()
    _load_locale(_CURRENT_LOCALE)


def translations_loaded() -> bool:
    """True se o idioma ativo possui dicionário carregado não vazio."""
    return bool(_load_locale(_CURRENT_LOCALE))


def get_default_locale() -> str:
    """Retorna o idioma padrão configurado para a aplicação."""
    return DEFAULT_LOCALE


def set_default_locale(locale: str | None = None) -> str:
    """Define o idioma padrão da aplicação e aplica o idioma imediatamente.

    Sem argumento (uso recomendado) o idioma é 100% automático:
    ``OFICINA_LOCALE`` (env) > idioma do sistema operacional (Windows) >
    ``config.cfg`` > ``pt_BR`` (fallback).
    """
    global DEFAULT_LOCALE
    nome = _normalizar_locale(locale)
    if not nome:
        nome = (
            _normalizar_locale(os.getenv("OFICINA_LOCALE", ""))
            or detectar_idioma_sistema()
            or _normalizar_locale(_ler_idioma_config_cfg())
            or DEFAULT_LOCALE
            or DEFAULT_FALLBACK_LOCALE
        )
    DEFAULT_LOCALE = nome
    os.environ["OFICINA_LOCALE"] = nome
    set_locale(nome)
    return DEFAULT_LOCALE


def set_locale(locale: str) -> str:
    """Define o idioma ativo para a aplicação."""
    global _CURRENT_LOCALE
    nome = _normalizar_locale(locale) or DEFAULT_LOCALE
    _load_locale(nome)  # garante dicionário carregado
    _CURRENT_LOCALE = nome
    return _CURRENT_LOCALE


def get_current_locale() -> str:
    """Retorna o idioma ativo no momento."""
    return _CURRENT_LOCALE


def get_text(key: str, locale: str | None = None, default: str | None = None) -> str:
    """Busca o texto traduzido para a chave informada.

    Ordem de resolução:
    1. Chave exata no idioma ativo;
    2. Chave em minúsculas no idioma ativo (corrige chamadas antigas em
       maiúsculas, ex.: ``BTN_IMPRIMIR_DANFE_PDV`` -> ``btn_imprimir_danfe_pdv``);
    3. Mesma busca no idioma padrão (pt_BR);
    4. ``default`` informado pela tela;
    5. A própria chave (nunca quebra, nunca exibe erro).
    """
    if key is None:
        return default or ""
    chave = str(key).strip()
    if not chave:
        return default or chave

    ativo = _normalizar_locale(locale) or _CURRENT_LOCALE
    traducoes = _load_locale(ativo)
    indice = _cache_indices.get(ativo, {})

    if chave in traducoes and traducoes[chave]:
        return traducoes[chave]
    chave_real = indice.get(chave.lower())
    if chave_real and traducoes.get(chave_real):
        return traducoes[chave_real]

    if ativo != DEFAULT_LOCALE:
        fallback = _load_locale(DEFAULT_LOCALE)
        indice_fallback = _cache_indices.get(DEFAULT_LOCALE, {})
        if chave in fallback and fallback[chave]:
            return fallback[chave]
        chave_real_fb = indice_fallback.get(chave.lower())
        if chave_real_fb and fallback.get(chave_real_fb):
            return fallback[chave_real_fb]

    # Último recurso: qualquer idioma disponível que conheça a chave
    for nome in SUPPORTED_LOCALES:
        if nome in (ativo, DEFAULT_LOCALE):
            continue
        dados = _cache_traducoes.get(nome)
        if dados and chave in dados and dados[chave]:
            return dados[chave]

    return default or chave


def t(key: str, locale: str | None = None, default: str | None = None) -> str:
    """Alias curto para get_text."""
    return get_text(key, locale=locale, default=default)


translate = t  # alias adicional

# Alias público para a detecção automática de idioma do sistema operacional.
detect_os_locale = detectar_idioma_sistema

# Carrega o idioma padrão (pt_BR) já na inicialização da aplicação.
_load_locale(_CURRENT_LOCALE)

# Exemplo de uso nas telas:
# from core.i18n import t
# ctk.CTkLabel(self, text=t("btn_salvar")).pack()
