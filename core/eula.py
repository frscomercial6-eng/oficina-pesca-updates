# -*- coding: utf-8 -*-
"""Detecção automática de idioma do sistema operacional + resolução do EULA.

Módulo autônomo (não importa core.i18n) para funcionar tanto no código-fonte
quanto no build protegido (onde core.i18n é um .pyd compilado).

Funções:
- ``detectar_idioma_sistema()``: idioma do Windows -> pt_BR/en_US/es_UY
  ("" se desconhecido);
- ``caminho_eula(locale=None)``: arquivo do Contrato de Licença para o idioma;
- ``carregar_texto_eula(locale=None)``: texto do contrato no idioma certo;
- ``rtf_para_texto(conteudo)``: conversão simples de RTF para texto plano.

Prioridade do idioma: o idioma configurado no Windows do usuário
(``locale.getdefaultlocale()``), com fallback para ``pt_BR``.
"""

from __future__ import annotations

import os
import re
import sys
import warnings

SUPPORTED_LOCALES = ("pt_BR", "es_UY", "en_US")
FALLBACK_LOCALE = "pt_BR"

_EULA_PADRAO = "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf"

__all__ = [
    "SUPPORTED_LOCALES",
    "FALLBACK_LOCALE",
    "detectar_idioma_sistema",
    "detect_os_locale",
    "normalizar_locale",
    "caminho_eula",
    "carregar_texto_eula",
    "rtf_para_texto",
]


# ---------------------------------------------------------------------------
# Normalização do nome de locale
# ---------------------------------------------------------------------------


# Nomes por extenso que o Windows retorna (ex.: "Portuguese_Brazil.1252").
_NOMES_IDIOMA = {
    "portuguese": "pt_BR",
    "portugues": "pt_BR",
    "english": "en_US",
    "ingles": "en_US",
    "spanish": "es_UY",
    "espanol": "es_UY",
    "espanhol": "es_UY",
}


def normalizar_locale(nome) -> str:
    """Converte nomes como 'pt-br', 'Portuguese_Brazil.1252', 'es_419' em
    pt_BR/en_US/es_UY.

    Retorna "" quando o idioma não é um dos suportados.
    """
    if not nome:
        return ""
    texto = str(nome).strip().lower()
    texto = texto.split(".")[0]  # remove sufixo de codepage (.utf8, .1252...)
    texto = texto.replace("-", "_")
    partes = [p for p in texto.split("_") if p]
    if not partes:
        return ""
    idioma = partes[0]
    if idioma.startswith("pt"):
        return "pt_BR"
    if idioma.startswith("es"):
        return "es_UY"
    if idioma.startswith("en"):
        return "en_US"
    # Nomes por extenso do Windows (locale.getwindowslocale()).
    for parte in partes:
        if parte in _NOMES_IDIOMA:
            return _NOMES_IDIOMA[parte]
    return ""


# Alias curto usado pelo core.i18n.
_normalizar_locale = normalizar_locale


# ---------------------------------------------------------------------------
# Detecção do idioma do sistema operacional (Windows)
# ---------------------------------------------------------------------------


def detectar_idioma_sistema() -> str:
    """Detecta o idioma padrão do Windows e devolve pt_BR/en_US/es_UY.

    Ordem de tentativa (todas envolvidas em try/except — nunca levanta):
      1. ``locale.getdefaultlocale()`` — idioma/regional do usuário no Windows;
      2. ``locale.getwindowslocale()``  — locale regional do Windows;
      3. ``GetUserDefaultUILanguage`` (ctypes) — idioma da interface do Windows;
      4. Variáveis de ambiente ``LANG``/``LC_ALL``/``LC_MESSAGES`` (Unix/CI).
    Retorna "" se nenhum idioma suportado for detectado (chamador aplica
    o fallback pt_BR).
    """
    nome = ""

    # 1) Idioma do usuário no Windows (solicitação principal).
    try:
        import locale

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            par = locale.getdefaultlocale()
        nome = (par[0] if par and par[0] else "") or ""
    except Exception:
        nome = ""

    # 2) Locale regional do Windows.
    if not nome:
        try:
            import locale

            if hasattr(locale, "getwindowslocale"):
                nome = locale.getwindowslocale()[0] or ""
        except Exception:
            nome = ""

    # 3) Idioma da interface (UI language) via API do Windows.
    if not nome:
        try:
            import ctypes
            import locale

            lcid = int(ctypes.windll.kernel32.GetUserDefaultUILanguage())
            nome = locale.windows_locale.get(lcid, "") or ""
        except Exception:
            nome = ""

    # 4) Ambientes Unix/CI.
    if not nome:
        for variavel in ("LANG", "LC_ALL", "LC_MESSAGES"):
            valor = os.environ.get(variavel, "")
            if valor:
                nome = valor.split(".")[0]
                break

    return normalizar_locale(nome)


# Alias público (compatibilidade de nomes).
detect_os_locale = detectar_idioma_sistema


# ---------------------------------------------------------------------------
# Resolução do arquivo de EULA/Contrato por idioma
# ---------------------------------------------------------------------------


def _candidate_base_dirs() -> list:
    """Caminhos plausíveis onde o contrato pode estar (fonte/frozen/onefile)."""
    candidatos = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidatos.append(meipass)

    try:
        # <projeto>/core/eula.py -> <projeto>
        candidatos.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    except Exception:
        pass

    if getattr(sys, "frozen", False):
        try:
            exe_dir = os.path.dirname(os.path.abspath(sys.executable))
            candidatos.append(exe_dir)
            candidatos.append(os.path.join(exe_dir, "_internal"))
        except Exception:
            pass

    try:
        candidatos.append(os.getcwd())
    except Exception:
        pass

    return candidatos


def caminho_eula(locale: str | None = None) -> str:
    """Retorna o caminho do Contrato de Licença (EULA) para o idioma.

    Procura, na ordem: ``<Contrato>_pt_BR.rtf`` / ``_en_US.rtf`` / ``_es_UY.rtf``
    (conforme o idioma), depois os arquivos padrão em português. Se o idioma
    solicitado não tiver arquivo próprio, cai automaticamente para pt_BR.
    """
    loc = normalizar_locale(locale) or detectar_idioma_sistema() or FALLBACK_LOCALE

    nomes_do_idioma = [
        f"Contrato_Oficina_de_Pesca_V3_Maio_2026_{loc}.rtf",
        os.path.join("Documentos", f"Contrato_Oficina_de_Pesca_V3_Maio_2026_{loc}.rtf"),
        os.path.join("Documentos", f"eula_{loc}.rtf"),
        os.path.join("Documentos", f"termos_de_uso_{loc}.txt"),
    ]
    nomes_padrao = [
        _EULA_PADRAO,
        os.path.join("Documentos", "contrato.rtf"),
        os.path.join("Documentos", "termos_de_uso.txt"),
    ]

    ordem = nomes_padrao if loc == FALLBACK_LOCALE else nomes_do_idioma + nomes_padrao
    for base in _candidate_base_dirs():
        for relativo in ordem:
            caminho = os.path.join(base, relativo)
            try:
                if os.path.isfile(caminho):
                    return caminho
            except Exception:
                continue
    return ""


def _ler_arquivo_texto(caminho: str) -> str:
    """Lê um arquivo de texto tentando múltiplos encodings comuns."""
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with open(caminho, "r", encoding=encoding) as arquivo:
                return arquivo.read()
        except UnicodeDecodeError:
            continue
        except Exception:
            return ""
    return ""


def carregar_texto_eula(locale: str | None = None) -> str:
    """Texto do EULA/Contrato no idioma informado (ou detectado no SO).

    Arquivos ``.rtf`` são convertidos para texto plano antes de retornar.
    Retorna "" quando nenhum contrato for encontrado.
    """
    caminho = caminho_eula(locale)
    if not caminho:
        return ""
    conteudo = _ler_arquivo_texto(caminho)
    if not conteudo:
        return ""
    if caminho.lower().endswith(".rtf"):
        conteudo = rtf_para_texto(conteudo)
    return conteudo.strip()


# ---------------------------------------------------------------------------
# Conversão simples de RTF para texto plano
# ---------------------------------------------------------------------------


def _remover_grupo_rtf(texto: str, palavra: str) -> str:
    """Remove um grupo RTF balanceado (ex.: {\\fonttbl...})."""
    marcador = "{\\" + palavra
    inicio = texto.find(marcador)
    while inicio != -1:
        profundidade = 0
        fim = -1
        for indice in range(inicio, len(texto)):
            caractere = texto[indice]
            if caractere == "{":
                profundidade += 1
            elif caractere == "}":
                profundidade -= 1
                if profundidade == 0:
                    fim = indice
                    break
        if fim == -1:
            break
        texto = texto[:inicio] + texto[fim + 1:]
        inicio = texto.find(marcador)
    return texto


def rtf_para_texto(conteudo: str) -> str:
    """Converte RTF (contratos gerados internamente) em texto plano."""
    if not conteudo:
        return ""
    texto = conteudo

    for palavra in ("fonttbl", "colortbl", "stylesheet", "info", "pict"):
        texto = _remover_grupo_rtf(texto, palavra)

    # Escapes hexadecimais \'e9 etc. (codepage Windows-1252).
    texto = re.sub(
        r"\\'([0-9a-fA-F]{2})",
        lambda m: bytes([int(m.group(1), 16)]).decode("cp1252", "ignore"),
        texto,
    )

    # Quebras de linha do RTF.
    texto = re.sub(r"\\par\b", "\n", texto)
    texto = re.sub(r"\\line\b", "\n", texto)

    # Demais palavras de controle (\b, \b0, \fs24, \deff0, ...).
    texto = re.sub(r"\\[a-zA-Z]+-?[0-9]*\s?", "", texto)
    texto = texto.replace("\\*", "")

    # Chaves residuais e limpeza final.
    texto = texto.replace("{", "").replace("}", "")
    texto = re.sub(r"[ \t]+\n", "\n", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


if __name__ == "__main__":  # diagnóstico rápido: python core/eula.py
    print(f"Idioma do sistema : {detectar_idioma_sistema() or '(desconhecido)'}")
    print(f"EULA (idioma SO)  : {caminho_eula() or '(não encontrado)'}")
    texto = carregar_texto_eula()
    print(f"Texto carregado   : {len(texto)} caracteres")
