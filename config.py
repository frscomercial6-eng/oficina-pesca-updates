# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
# --- GERENCIAMENTO CENTRALIZADO DA PLANILHA DE CONHECIMENTO TÉCNICO NO DRIVE ---
PASTA_MESTRE_CONHECIMENTO = "frs_ecossistema-fontes"
PLANILHA_CONHECIMENTO = "base_conhecimento_tecnico"

def get_or_create_knowledge_sheet():
    """Garante a existência da planilha base_conhecimento_tecnico na pasta mestre do Drive."""
    drive_service, sheets_service, msg = _obter_servico_google_sheets_drive()
    if not drive_service or not sheets_service:
        return None, None, msg
    # Localiza/cria pasta mestre
    ok_pasta, pasta_id, _ = localizar_ou_criar_pasta_drive(PASTA_MESTRE_CONHECIMENTO)
    if not ok_pasta:
        return None, None, "Falha ao acessar/criar pasta mestre no Drive."
    # Localiza/cria planilha
    ok_plan, planilha_id, _ = localizar_ou_criar_planilha(PLANILHA_CONHECIMENTO, pasta_id)
    if not ok_plan:
        return None, None, "Falha ao acessar/criar planilha de conhecimento técnico."
    return planilha_id, sheets_service, "OK"

def ler_links_alertas_conhecimento(fabricante, modelo, aba="dados"):
    """Lê links/alertas da planilha de conhecimento técnico para um fabricante/modelo."""
    planilha_id, sheets_service, msg = get_or_create_knowledge_sheet()
    if not planilha_id or not sheets_service:
        return None, msg
    linhas = ler_linhas_planilha(planilha_id, aba)
    for linha in linhas:
        if len(linha) >= 2 and str(linha[0]).strip().lower() == fabricante.strip().lower() and str(linha[1]).strip().lower() == modelo.strip().lower():
            return linha, "OK"
    return None, "Não encontrado"

def salvar_link_alerta_conhecimento(fabricante, modelo, url, origem="web_scraping", alerta="", aba="dados"):
    """Salva ou atualiza link/alerta na planilha de conhecimento técnico."""
    from datetime import datetime
    planilha_id, sheets_service, msg = get_or_create_knowledge_sheet()
    if not planilha_id or not sheets_service:
        return False, msg
    # Remove linha antiga (Sheets não tem update direto, mas append é seguro)
    # Apenas adiciona nova linha
    nova_linha = [fabricante, modelo, url, origem, alerta, datetime.now().isoformat()]
    adicionar_linha_planilha(planilha_id, nova_linha, aba)
    return True, "OK"
def _obter_servico_google_sheets_drive():
    """Retorna serviços autenticados do Google Sheets e Drive."""
    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return None, None, msg
    if google_build is None:
        return None, None, "Dependência google-api-python-client não encontrada."
    try:
        drive_service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        sheets_service = google_build("sheets", "v4", credentials=creds, cache_discovery=False)
        return drive_service, sheets_service, "OK"
    except Exception as e:
        return None, None, f"Erro ao criar serviços Google: {e}"

def localizar_ou_criar_pasta_drive(nome_pasta: str) -> tuple[bool, str, str]:
    """Localiza ou cria uma pasta no Google Drive do usuário."""
    drive_service, _, msg = _obter_servico_google_sheets_drive()
    if not drive_service:
        return False, "", msg
    try:
        nome_pasta_esc = nome_pasta.replace("'", "\\'")
        query = f"mimeType='application/vnd.google-apps.folder' and name='{nome_pasta_esc}' and trashed=false"
        pastas = drive_service.files().list(q=query, fields="files(id,name)", pageSize=1).execute().get("files", [])
        if pastas:
            return True, pastas[0]["id"], "OK"
        pasta = drive_service.files().create(
            body={"name": nome_pasta, "mimeType": "application/vnd.google-apps.folder"},
            fields="id",
        ).execute()
        return True, pasta["id"], "OK"
    except Exception as e:
        return False, "", f"Erro ao localizar/criar pasta: {e}"

def localizar_ou_criar_planilha(nome_planilha: str, pasta_id: str) -> tuple[bool, str, str]:
    """Localiza ou cria uma Google Sheet pelo nome dentro da pasta especificada."""
    drive_service, sheets_service, msg = _obter_servico_google_sheets_drive()
    if not drive_service or not sheets_service:
        return False, "", msg
    try:
        nome_planilha_esc = nome_planilha.replace("'", "\\'")
        query = f"mimeType='application/vnd.google-apps.spreadsheet' and name='{nome_planilha_esc}' and trashed=false and '{pasta_id}' in parents"
        arquivos = drive_service.files().list(q=query, fields="files(id,name)", pageSize=1).execute().get("files", [])
        if arquivos:
            return True, arquivos[0]["id"], "OK"
        # Cria nova planilha
        sheet = sheets_service.spreadsheets().create(
            body={
                "properties": {"title": nome_planilha},
                "sheets": [{"properties": {"title": "dados"}}],
            }
        ).execute()
        planilha_id = sheet["spreadsheetId"]
        # Move para a pasta
        drive_service.files().update(fileId=planilha_id, addParents=pasta_id, removeParents="root").execute()
        return True, planilha_id, "OK"
    except Exception as e:
        return False, "", f"Erro ao localizar/criar planilha: {e}"

def ler_linhas_planilha(planilha_id: str, aba: str = "dados") -> list:
    """Lê todas as linhas da aba especificada da planilha."""
    _, sheets_service, msg = _obter_servico_google_sheets_drive()
    if not sheets_service:
        return []
    try:
        result = sheets_service.spreadsheets().values().get(spreadsheetId=planilha_id, range=f"{aba}!A1:Z1000").execute()
        return result.get("values", [])
    except Exception:
        return []

def adicionar_linha_planilha(planilha_id: str, linha: list, aba: str = "dados") -> bool:
    """Adiciona uma linha ao final da aba especificada."""
    _, sheets_service, msg = _obter_servico_google_sheets_drive()
    if not sheets_service:
        return False
    try:
        sheets_service.spreadsheets().values().append(
            spreadsheetId=planilha_id,
            range=f"{aba}!A1",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": [linha]},
        ).execute()
        return True
    except Exception:
        return False

def buscar_linha_por_fabricante_modelo(planilha_id: str, fabricante: str, modelo: str, aba: str = "dados") -> list:
    """Busca linhas que contenham fabricante e modelo (case-insensitive)."""
    linhas = ler_linhas_planilha(planilha_id, aba)
    if not linhas:
        return []
    for linha in linhas:
        if len(linha) >= 2 and str(linha[0]).strip().lower() == fabricante.strip().lower() and str(linha[1]).strip().lower() == modelo.strip().lower():
            return linha
    return []
import os
import sys
import hashlib
import binascii
import sqlite3
import hmac
import base64
import json
import logging
import configparser
import tempfile
import io
import subprocess
import re
import threading
import time
import glob
import shutil
import platform
import uuid
from datetime import date, datetime, timedelta
from typing import Optional
from contextlib import contextmanager
import urllib.request
import urllib.error

try:
    import firebase_admin
    from firebase_admin import credentials as firebase_credentials
    from firebase_admin import db as firebase_db
except Exception:
    firebase_admin = None
    firebase_credentials = None
    firebase_db = None

try:
    import google.auth  # type: ignore  # noqa: F401
    import google_auth_oauthlib  # type: ignore  # noqa: F401
    import googleapiclient  # type: ignore  # noqa: F401
    from google.oauth2.credentials import Credentials as GoogleCredentials
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as google_build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
except Exception:
    GoogleCredentials = None
    GoogleAuthRequest = None
    InstalledAppFlow = None
    google_build = None
    MediaFileUpload = None
    MediaIoBaseDownload = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Carrega variÃ¡veis de ambiente locais (desenvolvimento/build) sem quebrar em produÃ§Ã£o.
try:
    if load_dotenv:
        _env_candidates = []
        _module_dir = os.path.dirname(os.path.abspath(__file__))
        _exec_dir = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else ""
        _cwd_dir = os.getcwd()

        for _base in (_exec_dir, _cwd_dir, _module_dir):
            if not _base:
                continue
            _env_candidates.append(os.path.join(_base, ".env"))
            _env_candidates.append(os.path.join(_base, ".env.local"))

        _seen = set()
        for _env_path in _env_candidates:
            _abs = os.path.abspath(_env_path)
            if _abs in _seen:
                continue
            _seen.add(_abs)
            load_dotenv(_abs, override=False)

        # Mantém fallback padrão do python-dotenv (sem caminho explícito).
        load_dotenv(override=False)
except Exception:
    pass

import configparser
_CFG = configparser.ConfigParser()
_CFG.read("config.cfg", encoding="utf-8")
try:
    from version_info import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = _CFG.get("versao", "versao_atual", fallback="1.0.0")

# Caminhos globais
# Quando empacotado com PyInstaller:
#   DIRETORIO_ATUAL  -> pasta real do executável (onde oficina.db deve ficar)
#   DIRETORIO_RECURSOS -> pasta dos arquivos bundlados (imagens, etc.)
def _obter_diretorio_execucao() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _obter_diretorio_dados_usuario() -> str:
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or _obter_diretorio_execucao()
    pasta = os.path.join(base, 'OficinaPesca')
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _obter_diretorio_dados() -> str:
    if getattr(sys, 'frozen', False):
        return _obter_diretorio_dados_usuario()
    return _obter_diretorio_execucao()


def _resolver_caminho_banco() -> str:
    caminho_env = str(os.environ.get('OFP_DB_PATH', '')).strip()
    if caminho_env:
        caminho_abs = os.path.abspath(caminho_env)
        os.makedirs(os.path.dirname(caminho_abs), exist_ok=True)
        return caminho_abs

    caminho_usuario = os.path.join(_obter_diretorio_dados_usuario(), 'oficina.db')
    caminho_instalacao = os.path.join(_obter_diretorio_execucao(), 'oficina.db')

    if os.path.exists(caminho_usuario) and os.path.getsize(caminho_usuario) > 0:
        return caminho_usuario

    if os.path.exists(caminho_instalacao) and os.path.getsize(caminho_instalacao) > 0:
        try:
            shutil.copy2(caminho_instalacao, caminho_usuario)
            return caminho_usuario
        except Exception:
            return caminho_instalacao

    if getattr(sys, 'frozen', False):
        return caminho_usuario
    return caminho_instalacao


if getattr(sys, 'frozen', False):
    DIRETORIO_ATUAL = _obter_diretorio_execucao()
    DIRETORIO_RECURSOS = sys._MEIPASS
else:
    DIRETORIO_ATUAL = _obter_diretorio_execucao()
    DIRETORIO_RECURSOS = DIRETORIO_ATUAL

DIRETORIO_DADOS = _obter_diretorio_dados()
CAMINHO_BANCO_LOCAL = os.path.join(DIRETORIO_DADOS, 'oficina.db')
CAMINHO_BANCO_INSTALACAO = os.path.join(DIRETORIO_ATUAL, 'oficina.db')
CAMINHO_BANCO = _resolver_caminho_banco()
_DIRETORIO_LOG_BASE = os.environ.get('APPDATA') or os.environ.get('LOCALAPPDATA') or os.environ.get('TEMP') or DIRETORIO_ATUAL
CAMINHO_LOG = os.path.join(_DIRETORIO_LOG_BASE, 'OficinaDePesca', 'logs', 'oficina_debug.txt')

# â”€â”€â”€ config.cfg â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def _ler_cfg() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg_path = os.path.join(DIRETORIO_ATUAL, 'config.cfg')
    if os.path.exists(cfg_path):
        cfg.read(cfg_path, encoding='utf-8')
    return cfg

_CFG = _ler_cfg()
SERVIDOR_URL = _CFG.get('app', 'servidor_url', fallback='http://localhost:8000')
URL_APP_CELULAR_PUBLICA = _CFG.get('app', 'url_app_celular_publica', fallback='').strip()
WHATSAPP_ADMIN_DESTINO = _CFG.get('app', 'whatsapp_admin', fallback='').strip()


def _flag_bool(valor, default: bool = False) -> bool:
    txt = str(valor if valor is not None else "").strip().lower()
    if not txt:
        return bool(default)
    return txt in {"1", "true", "t", "yes", "y", "sim", "on"}


_MODO_CLIENTE_FINAL = _flag_bool(
    os.environ.get("OFP_MODO_CLIENTE_FINAL", ""),
    default=_CFG.getboolean("licenca", "modo_cliente_final", fallback=bool(getattr(sys, "frozen", False))),
)


def modo_cliente_final_licenciado() -> bool:
    """Fluxo legado desativado: a licença deve sempre ser validada por arquivo externo."""
    return False

CENTRAL_SUPORTE_EMAIL = "frs.suporte.oficina@gmail.com"
CENTRAL_UPDATE_MANIFEST_URL = str(
    os.environ.get('OFP_CENTRAL_UPDATE_MANIFEST_URL', '')
    or _CFG.get('central', 'update_manifest_url', fallback='https://raw.githubusercontent.com/frscomercial6-eng/oficina-pesca-updates/main/config.json')
).split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')
CENTRAL_UPDATE_DOWNLOAD_URL = str(
    os.environ.get('OFP_CENTRAL_UPDATE_DOWNLOAD_URL', '')
    or _CFG.get('central', 'update_download_url', fallback='https://github.com/frscomercial6-eng/oficina-pesca-updates/releases/latest/download/Oficina_Pesca_Instalador.exe')
).split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')
CENTRAL_COMPAT_JSON_URL = str(
    os.environ.get('OFP_CENTRAL_COMPAT_JSON_URL', '')
    or _CFG.get('central', 'compat_json_url', fallback='')
).split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')
CENTRAL_COMPAT_WEBHOOK_URL = str(
    os.environ.get('OFP_CENTRAL_COMPAT_WEBHOOK_URL', '')
    or _CFG.get('central', 'compat_webhook_url', fallback='')
).split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')
# ---------------------------------------------------------------------------
# Endpoint central FRS — Google Apps Script (sem servidor pago).
# Após deployar o script em script.google.com, cole a URL de execução abaixo
# no lugar da string vazia. Funciona como fallback de último recurso; o
# operador pode sobrescrever via variável OFP_CENTRAL_LOG_UPLOAD_URL ou
# pela chave [suporte] log_upload_url no config.cfg.
# ---------------------------------------------------------------------------
FRS_APPS_SCRIPT_ENDPOINT: str = (
    "https://script.google.com/macros/s/AKfycbxog8gr4WrMwWKHPcjdeBpFrJn7jHgnhT9K4_SNquQCOjp7psGlEll-Ib2Wu6-oKabR/exec"
)

CENTRAL_LOG_UPLOAD_URL = str(
    os.environ.get('OFP_CENTRAL_LOG_UPLOAD_URL', '')
    or _CFG.get('suporte', 'log_upload_url', fallback='')
    or FRS_APPS_SCRIPT_ENDPOINT
).split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')

URL_CHECK_VERSAO = str(_CFG.get('versao', 'url_check', fallback=CENTRAL_UPDATE_MANIFEST_URL)).split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')
URL_CHECK_LICENCAS = str(_CFG.get('versao', 'url_check_licencas', fallback='')).strip().split('#')[0].split(';')[0].strip().replace('\n', '').replace('\r', '')
INTERVALO_DIAS_CHECK_VERSAO = max(1, _CFG.getint('versao', 'intervalo_dias_check', fallback=15))
VERSAO_TRAVA_LOOP_UPDATE = "1.0.50"
ARQUIVO_ESTADO_UPDATE = os.path.join(_obter_diretorio_dados_usuario(), "update_state.json")
CLOUD_BACKUP_EMAIL = _CFG.get('cloud_backup', 'email_cliente', fallback='').strip()
CLOUD_BACKUP_ENABLED = _CFG.getboolean('cloud_backup', 'habilitado', fallback=True)
CLOUD_SYNC_API_KEY = _CFG.get('cloud_backup', 'api_key', fallback='').strip()
CLOUD_AUTO_SYNC = _CFG.getboolean('cloud_backup', 'auto_sync', fallback=True)
CLOUD_SYNC_INTERVAL_SEG = _CFG.getint('cloud_backup', 'sync_interval_seg', fallback=60)
INFINITEPAY_LINK_PAGAMENTO = _CFG.get('pagamento', 'infinitepay_link', fallback='').strip()
INFINITEPAY_LINK_MENSAL = _CFG.get('pagamento', 'infinitepay_link_mensal', fallback='https://invoice.infinitepay.io/plans/frsoficinadepesca/7n8vLUjOnD').strip()
INFINITEPAY_LINK_TRIMESTRAL = _CFG.get('pagamento', 'infinitepay_link_trimestral', fallback='https://invoice.infinitepay.io/plans/frsoficinadepesca/2arDagkoGn').strip()
INFINITEPAY_LINK_SEMESTRAL = _CFG.get('pagamento', 'infinitepay_link_semestral', fallback='https://invoice.infinitepay.io/plans/frsoficinadepesca/1CYUQRLzf').strip()
INFINITEPAY_LINK_ANUAL = _CFG.get('pagamento', 'infinitepay_link_anual', fallback='https://invoice.infinitepay.io/plans/frsoficinadepesca/7l0Qu7fjmN').strip()
INFINITEPAY_API_CHECKOUT_URL = _CFG.get(
    'pagamento',
    'infinitepay_checkout_url',
    fallback='https://api.checkout.infinitepay.io/links'
).strip()
INFINITEPAY_API_TOKEN = _CFG.get('pagamento', 'infinitepay_api_token', fallback='').strip()
INFINITEPAY_HANDLE = _CFG.get('pagamento', 'infinitepay_handle', fallback='frsoficinadepesca').strip()

# Chave mestre de IA/sincronizacao (uso interno, sem exposicao na UI).
# Prioriza OFP_GOOGLE_AI_MASTER_KEY; mantem fallbacks para compatibilidade.
GOOGLE_AI_MASTER_KEY = str(
    os.environ.get('OFP_GOOGLE_AI_MASTER_KEY', '')
    or os.environ.get('GOOGLE_AI_STUDIO_API_KEY', '')
    or os.environ.get('GEMINI_API_KEY', '')
    or ''
).strip()

# Cores do tema (para CustomTkinter)
COR_PRIMARIA = "#27ae60"  # Verde para botÃµes principais
COR_SECUNDARIA = "#e67e22"  # Laranja para aÃ§Ãµes
COR_ERRO = "#c0392b"  # Vermelho para erros

# Tema visual do Menu Principal (sidebar + fundo + logo)
MENU_BG_IMAGE = "fundomenu.png"
MENU_LOGO_IMAGE = "LOGO.bmp"
MENU_COR_FUNDO = "#0b172a"
MENU_COR_SIDEBAR = "#10253e"
MENU_COR_BOTAO = "#1b3658"
MENU_COR_BOTAO_HOVER = "#264b78"
MENU_COR_TEXTO = "#f2f5f7"
MENU_COR_DESTAQUE = "#f6b73c"

TRIAL_DIAS = 15
VALOR_ATUALIZACAO_NAO_PERMANENTE = 50.00
VALOR_LICENCA_MENSAL = 149.90
VALOR_LICENCA_TRIMESTRAL = 249.90
VALOR_LICENCA_PERMANENTE = 599.90
# Permite segredo externo para licenciamento sem quebrar instalaÃ§Ãµes antigas.
# Se a variÃ¡vel de ambiente nÃ£o existir, tenta fallback automÃ¡tico no instalar.iss.
def _resolver_licenca_secret() -> str:
    secret_env = str(os.environ.get("OFP_LICENCA_SECRET", "")).strip()
    if secret_env:
        return secret_env

    candidatos = [
        os.path.join(DIRETORIO_ATUAL, "instalar.iss"),
        os.path.join(DIRETORIO_RECURSOS, "instalar.iss"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "instalar.iss"),
    ]

    for caminho in candidatos:
        try:
            if not os.path.exists(caminho):
                continue
            with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                conteudo = f.read()
            match = re.search(r'^#define\s+LicenseSecret\s+"([^"]+)"', conteudo, re.MULTILINE)
            if match:
                return str(match.group(1)).strip()
        except Exception:
            continue

    return ""


LICENCA_SECRET = _resolver_licenca_secret()
if LICENCA_SECRET:
    os.environ.setdefault("OFP_LICENCA_SECRET", LICENCA_SECRET)

_CLOUD_SYNC_THREAD: Optional[threading.Thread] = None
_CLOUD_SYNC_STARTED = False
_FIREBASE_LISTENER_THREAD: Optional[threading.Thread] = None
_FIREBASE_LISTENER_STARTED = False
_FIREBASE_LAST_REMOTE_EVENT_TS = ""
_FIREBASE_SYNC_EMAIL_CACHE = {"email": "", "ts": 0.0}
_DISCOVERY_CACHE = {"url": "", "ts": 0.0}
GOOGLE_DRIVE_USER_SCOPES = [
    # Escopo explicitamente definido para permitir acesso a arquivos criados pelo App
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
GOOGLE_DRIVE_PASTA_APP = "Oficina de Pesca"
GOOGLE_DRIVE_PASTA_TOKEN = "Oficina de Pesca - Tokens"
GOOGLE_DRIVE_PASTA_LICENCA = "Oficina de Pesca - Licencas"
TOKEN_ARQUIVO_NOME = "acesso.token"
TOKEN_VALIDADE_DIAS = 30
TOKEN_RENOVAR_FALTANDO_DIAS = 5
_FIREBASE_GSERVICES_CACHE = {"loaded": False, "values": {}}


def _carregar_firebase_google_services_local() -> dict:
    """Lê google-services.json local para preencher config Firebase sem hardcode."""
    global _FIREBASE_GSERVICES_CACHE
    if _FIREBASE_GSERVICES_CACHE.get("loaded"):
        return dict(_FIREBASE_GSERVICES_CACHE.get("values") or {})

    candidatos = [
        os.path.join(DIRETORIO_ATUAL, "google-services.json"),
        os.path.join(DIRETORIO_RECURSOS, "google-services.json"),
        os.path.join(DIRETORIO_ATUAL, "android_apk", "app", "google-services.json"),
        os.path.join(os.getcwd(), "google-services.json"),
    ]

    mapeado: dict[str, str] = {}
    for caminho in candidatos:
        try:
            if not os.path.isfile(caminho):
                continue
            with open(caminho, "r", encoding="utf-8") as f:
                raw = json.load(f)

            project_info = raw.get("project_info") or {}
            client = ((raw.get("client") or [{}])[0]) or {}
            client_info = client.get("client_info") or {}
            api_cfg = ((client.get("api_key") or [{}])[0]) or {}

            project_id = str(project_info.get("project_id") or "").strip()
            mapeado = {
                "database_url": str(project_info.get("firebase_url") or "").strip(),
                "project_id": project_id,
                "storage_bucket": str(project_info.get("storage_bucket") or "").strip(),
                "messaging_sender_id": str(project_info.get("project_number") or "").strip(),
                "app_id": str(client_info.get("mobilesdk_app_id") or "").strip(),
                "api_key": str(api_cfg.get("current_key") or "").strip(),
                "auth_domain": f"{project_id}.firebaseapp.com" if project_id else "",
            }
            break
        except Exception:
            continue

    _FIREBASE_GSERVICES_CACHE = {"loaded": True, "values": mapeado}
    return dict(mapeado)


def _firebase_cfg_get(key: str, default: str = "") -> str:
    cfg = _ler_cfg()
    valor_env = str(os.environ.get(f"OFP_FIREBASE_{key.upper()}", "") or "").strip()
    if valor_env:
        return valor_env

    valor_cfg = str(cfg.get("firebase", key, fallback="") or "").strip()
    if valor_cfg:
        return valor_cfg

    valor_local = str(_carregar_firebase_google_services_local().get(key, "") or "").strip()
    if valor_local:
        return valor_local

    return str(default or "").strip()


def _firebase_safe_scope(valor: str) -> str:
    txt = str(valor or "").strip().lower()
    if not txt:
        return ""
    txt = re.sub(r"[^a-z0-9@._-]", "", txt)
    txt = txt.replace("@", "_at_").replace(".", "_dot_")
    txt = re.sub(r"_+", "_", txt).strip("_")
    return txt


def _obter_email_google_drive_usuario_conectado(force: bool = False) -> str:
    """Obtém e-mail do OAuth do Drive para isolar o nó Firebase por cliente."""
    global _FIREBASE_SYNC_EMAIL_CACHE
    agora = time.time()
    cache_email = str(_FIREBASE_SYNC_EMAIL_CACHE.get("email") or "").strip().lower()
    cache_ts = float(_FIREBASE_SYNC_EMAIL_CACHE.get("ts") or 0.0)
    if not force and cache_email and (agora - cache_ts) < 300:
        return cache_email

    try:
        creds, _msg = _obter_credenciais_google_drive_usuario(interativo=False)
        if not creds or google_build is None:
            return ""
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        about = service.about().get(fields="user(emailAddress)").execute()
        user = about.get("user", {}) if isinstance(about, dict) else {}
        email = str(user.get("emailAddress") or "").strip().lower()
        if email:
            _FIREBASE_SYNC_EMAIL_CACHE = {"email": email, "ts": agora}
        return email
    except Exception:
        return ""


def _firebase_sync_scope() -> str:
    """Escopo lógico por cliente (e-mail), evitando canal compartilhado entre clientes."""
    manual = (
        str(os.environ.get("OFP_FIREBASE_SYNC_SCOPE", "") or "").strip()
        or _firebase_cfg_get("sync_scope", "")
    )
    if manual:
        return _firebase_safe_scope(manual) or "global"

    email_drive = _obter_email_google_drive_usuario_conectado()
    if email_drive:
        return _firebase_safe_scope(email_drive) or "global"

    try:
        user_id = str(obter_user_id_token_padrao() or "").strip().lower()
        if user_id and user_id != "ofp-user":
            return _firebase_safe_scope(user_id) or "global"
    except Exception:
        pass

    return "global"


def _firebase_sync_channel() -> str:
    canal = _firebase_cfg_get("sync_channel", "bridge")
    canal = re.sub(r"[^a-zA-Z0-9_-]", "", str(canal or "")).strip()
    base = canal or "bridge"
    scope = _firebase_sync_scope()
    return f"{base}/{scope}"


def obter_firebase_web_config() -> dict:
    """Retorna config web do Firebase para cliente WebView/PWA."""
    return {
        "apiKey": _firebase_cfg_get("api_key"),
        "authDomain": _firebase_cfg_get("auth_domain"),
        # Sem fallback hardcoded: a URL deve vir de ambiente/config local.
        "databaseURL": _firebase_cfg_get("database_url"),
        "projectId": _firebase_cfg_get("project_id"),
        "storageBucket": _firebase_cfg_get("storage_bucket"),
        "messagingSenderId": _firebase_cfg_get("messaging_sender_id"),
        "appId": _firebase_cfg_get("app_id"),
        "syncChannel": _firebase_sync_channel(),
        "syncScope": _firebase_sync_scope(),
    }


def publicar_evento_ponte_firebase_para_apk(acao: str = "desktop_drive_synced", extras: Optional[dict] = None) -> tuple[bool, str]:
    """Publica evento Desktop->APK no Firebase como ponte temporária."""
    ok_fb, msg_fb = _inicializar_firebase_admin()
    if not ok_fb:
        return False, msg_fb

    try:
        canal = _firebase_sync_channel()
        event_id = f"desktop_{int(time.time() * 1000)}"
        payload = {
            "acao": str(acao or "desktop_drive_synced").strip().lower(),
            "source": "desktop",
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "canal": canal,
        }
        if isinstance(extras, dict):
            payload.update(extras)
        firebase_db.reference(f"sync_nodes/{canal}/bridge/{event_id}").set(payload)
        return True, "Evento de ponte Desktop->APK publicado."
    except Exception as e:
        return False, f"Falha ao publicar evento de ponte: {e}"


def _firebase_service_account_path() -> str:
    """Resolve o caminho da conta de serviço do Firebase (Desktop/Admin SDK)."""
    candidatos = []
    env_path = str(os.environ.get("OFP_FIREBASE_SERVICE_ACCOUNT", "") or "").strip()
    if env_path:
        candidatos.append(env_path)

    cfg = _ler_cfg()
    cfg_path = cfg.get("firebase", "service_account_path", fallback="").strip()
    if cfg_path:
        candidatos.append(cfg_path)

    candidatos.extend(
        [
            os.path.join(DIRETORIO_ATUAL, "google-services.json"),
            os.path.join(DIRETORIO_RECURSOS, "google-services.json"),
            os.path.join(DIRETORIO_ATUAL, "firebase-service-account.json"),
            os.path.join(DIRETORIO_RECURSOS, "firebase-service-account.json"),
        ]
    )

    for caminho in candidatos:
        try:
            c = os.path.abspath(str(caminho))
            if os.path.isfile(c):
                return c
        except Exception:
            continue
    return ""


def _inicializar_firebase_admin() -> tuple[bool, str]:
    if firebase_admin is None or firebase_credentials is None or firebase_db is None:
        return False, "firebase_admin indisponível no ambiente."

    cfg_web = obter_firebase_web_config()
    db_url = str(cfg_web.get("databaseURL") or "").strip()
    if not db_url:
        return False, "databaseURL do Firebase não configurada."

    if getattr(firebase_admin, "_apps", None):
        return True, "Firebase Admin já inicializado."

    cred_path = _firebase_service_account_path()
    if not cred_path:
        return False, "Conta de serviço Firebase não encontrada."

    try:
        cred = firebase_credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"databaseURL": db_url})
        return True, "Firebase Admin inicializado."
    except Exception as e:
        return False, f"Falha ao inicializar Firebase Admin: {e}"


def publicar_heartbeat_firebase() -> tuple[bool, str]:
    """Publica status da instância Desktop para sincronização bidirecional com clientes Web/APK."""
    ok_fb, msg_fb = _inicializar_firebase_admin()
    if not ok_fb:
        return False, msg_fb

    try:
        canal = _firebase_sync_channel()
        status_licenca = obter_status_acesso_centralizado()
        ref = firebase_db.reference(f"sync_nodes/{canal}/desktop")
        ref.update(
            {
                "last_seen": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "version": APP_VERSION,
                "db_mtime": int(os.path.getmtime(CAMINHO_BANCO)) if os.path.exists(CAMINHO_BANCO) else 0,
                "status": "online",
                "license_bloqueada": bool(status_licenca.get("bloqueada")),
                "license": {
                    "allowed": bool(status_licenca.get("ativa")),
                    "blocked": bool(status_licenca.get("bloqueada")),
                    "message": str(status_licenca.get("mensagem") or "").strip(),
                    "tipo": str(status_licenca.get("tipo") or "").strip(),
                    "validade": str(status_licenca.get("validade") or "").strip(),
                },
            }
        )
        return True, "Heartbeat Firebase publicado."
    except Exception as e:
        return False, f"Falha ao publicar heartbeat Firebase: {e}"


def iniciar_listener_firebase_realtime() -> tuple[bool, str]:
    """Ativa listener de eventos remotos no Realtime Database (SnapshotListener equivalente)."""
    global _FIREBASE_LISTENER_THREAD, _FIREBASE_LISTENER_STARTED, _FIREBASE_LAST_REMOTE_EVENT_TS

    if _FIREBASE_LISTENER_STARTED and _FIREBASE_LISTENER_THREAD and _FIREBASE_LISTENER_THREAD.is_alive():
        return True, "Listener Firebase já está ativo."

    ok_fb, msg_fb = _inicializar_firebase_admin()
    if not ok_fb:
        return False, msg_fb

    canal = _firebase_sync_channel()
    logger_fb = get_logger("firebase-sync")

    def _registrar_payload_local(payload: dict) -> None:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO fila_sync_firebase (origem, acao, payload_json, recebido_em, processado)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (
                        str(payload.get("source") or "apk").strip().lower(),
                        str(payload.get("acao") or "apk_data_push").strip().lower(),
                        json.dumps(payload, ensure_ascii=False),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                conn.commit()
        except Exception:
            pass

    def _limpar_evento_ponte(origem_path: str, event_id: str):
        try:
            if origem_path == "bridge" and event_id:
                firebase_db.reference(f"sync_nodes/{canal}/bridge/{event_id}").delete()
            elif origem_path == "commands":
                firebase_db.reference(f"sync_nodes/{canal}/commands").set({})
        except Exception:
            pass

    def _processar_evento(payload: dict, event_id: str = "", origem_path: str = "bridge"):
        nonlocal canal
        global _FIREBASE_LAST_REMOTE_EVENT_TS
        try:
            if not isinstance(payload, dict):
                return

            origem = str(payload.get("source") or "").strip().lower()
            if origem.startswith("desktop"):
                return

            acao = str(payload.get("acao") or "").strip().lower()
            ts = str(payload.get("ts") or "").strip()
            if ts and ts == _FIREBASE_LAST_REMOTE_EVENT_TS:
                return

            if acao in {"sync_now", "pull_latest", "refresh", "apk_data_push"}:
                if acao == "apk_data_push":
                    _registrar_payload_local(payload)

                ok, msg = sincronizar_hibrido_banco_drive()
                if ok:
                    _FIREBASE_LAST_REMOTE_EVENT_TS = ts
                    logger_fb.info("Evento remoto Firebase processado (%s): %s", acao, msg)
                    try:
                        firebase_db.reference(f"sync_nodes/{canal}/desktop").update(
                            {
                                "last_sync": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                                "last_action": acao,
                                "last_result": "ok",
                            }
                        )
                    except Exception:
                        pass
                    _limpar_evento_ponte(origem_path, event_id)
                else:
                    logger_fb.warning("Falha ao processar evento remoto Firebase (%s): %s", acao, msg)
        except Exception as e:
            logger_fb.warning("Falha no processamento de evento Firebase: %s", e)

    def _worker_listener():
        nonlocal canal
        while True:
            stream_commands = None
            stream_bridge = None
            try:
                publicar_heartbeat_firebase()

                # Listener nativo do Realtime Database; em caso de queda, o loop reconecta.
                ref_commands = firebase_db.reference(f"sync_nodes/{canal}/commands")
                ref_bridge = firebase_db.reference(f"sync_nodes/{canal}/bridge")

                def _on_commands(event):
                    dados = event.data
                    if isinstance(dados, dict):
                        _processar_evento(dados, "", "commands")

                def _on_bridge(event):
                    dados = event.data
                    path = str(getattr(event, "path", "") or "")
                    if path in {"", "/"} and isinstance(dados, dict):
                        for k, v in dados.items():
                            if isinstance(v, dict):
                                _processar_evento(v, str(k), "bridge")
                        return
                    if isinstance(dados, dict):
                        event_id = path.strip("/").split("/")[0]
                        _processar_evento(dados, event_id, "bridge")

                stream_commands = ref_commands.listen(_on_commands)
                stream_bridge = ref_bridge.listen(_on_bridge)

                while True:
                    publicar_heartbeat_firebase()
                    time.sleep(25)
            except Exception as e:
                logger_fb.warning("Listener Firebase desconectado/reconectando: %s", e)
                time.sleep(8)
            finally:
                try:
                    if stream_commands:
                        stream_commands.close()
                except Exception:
                    pass
                try:
                    if stream_bridge:
                        stream_bridge.close()
                except Exception:
                    pass

    _FIREBASE_LISTENER_THREAD = threading.Thread(target=_worker_listener, daemon=True, name="ofp-firebase-listener")
    _FIREBASE_LISTENER_THREAD.start()
    _FIREBASE_LISTENER_STARTED = True
    return True, "Listener Firebase em tempo real iniciado."


class _ErrorForwardHandler(logging.Handler):
    """Encaminha eventos ERROR/CRITICAL para a central de suporte (best effort).

    A URL é resolvida dinamicamente no momento do emit — não no __init__ —
    para que FRS_APPS_SCRIPT_ENDPOINT possa ser preenchido depois da
    importação do módulo sem necessidade de recriar o handler.
    """

    def __init__(self, token: str = ""):
        super().__init__(level=logging.ERROR)
        self.token = str(token or "").strip()

    def _url_ativa(self) -> str:
        """Retorna o endpoint ativo, priorizando variáveis de ambiente."""
        return (
            os.environ.get('OFP_CENTRAL_LOG_UPLOAD_URL', '').strip()
            or CENTRAL_LOG_UPLOAD_URL
            or FRS_APPS_SCRIPT_ENDPOINT
        )

    def emit(self, record: logging.LogRecord) -> None:
        url = self._url_ativa()
        if not url:
            return

        def _enviar_async():
            try:
                msg = self.format(record)
                payload = {
                    "app": "Oficina de Pesca",
                    "versao": APP_VERSION,
                    "tipo": "erro_runtime",
                    "destino_suporte": CENTRAL_SUPORTE_EMAIL,
                    "host": platform.node(),
                    "logger": str(record.name or "").strip(),
                    "nivel": str(record.levelname or "ERROR"),
                    "mensagem": msg[-4000:],
                    "enviado_em": datetime.now().isoformat(timespec="seconds"),
                }
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": f"OficinaPesca/{APP_VERSION}",
                }
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"

                req = urllib.request.Request(url, data=body, headers=headers, method="POST")
                # Timeout de 1s para não travar threads de background
                with urllib.request.urlopen(req, timeout=1):
                    pass
            except Exception:
                pass

        threading.Thread(target=_enviar_async, daemon=True).start()


def _url_endpoint_central() -> str:
    """Resolve URL ativa da central de suporte (Apps Script)."""
    return (
        os.environ.get('OFP_CENTRAL_LOG_UPLOAD_URL', '').strip()
        or CENTRAL_LOG_UPLOAD_URL
        or FRS_APPS_SCRIPT_ENDPOINT
    )


def enviar_post_central_silencioso(payload: dict, token: str = "", timeout: int = 5) -> bool:
    """Envia payload JSON para a central sem interromper o fluxo do usuário."""
    url = _url_endpoint_central()
    if not url:
        return False

    try:
        corpo = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"OficinaPesca/{APP_VERSION}",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=corpo, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=max(2, int(timeout))):
            pass
        return True
    except Exception:
        return False


def enviar_registro_os_central_silencioso(registro_os: dict, operacao: str = "upsert") -> None:
    """Enfileira envio best-effort de registro de O.S./Orçamento para a central."""

    def _worker() -> None:
        try:
            payload = {
                "app": "Oficina de Pesca",
                "versao": APP_VERSION,
                "tipo": "registro_os",
                "operacao": str(operacao or "upsert").strip().lower(),
                "destino_suporte": CENTRAL_SUPORTE_EMAIL,
                "host": platform.node(),
                "enviado_em": datetime.now().isoformat(timespec="seconds"),
                "registro": registro_os or {},
            }
            enviar_post_central_silencioso(payload=payload, timeout=5)
        except Exception:
            return

    try:
        threading.Thread(target=_worker, daemon=True).start()
    except Exception:
        return


def _resolver_servidor_rede_url(timeout_seg: float = 3.0) -> str:
    cfg = _ler_cfg()
    base_cfg = str(cfg.get('app', 'servidor_url', fallback='http://localhost:8000') or '').strip()
    modo = str(cfg.get('app', 'modo', fallback='local') or '').strip().lower()
    if modo != 'rede':
        return base_cfg or 'http://localhost:8000'

    base_lower = base_cfg.lower()
    if base_cfg and 'localhost' not in base_lower and '127.0.0.1' not in base_lower and '0.0.0.0' not in base_lower:
        return base_cfg

    agora = time.time()
    cache_url = str(_DISCOVERY_CACHE.get('url') or '').strip()
    cache_ts = float(_DISCOVERY_CACHE.get('ts') or 0.0)
    if cache_url and (agora - cache_ts) < 60:
        return cache_url

    try:
        from zeroconf import ServiceBrowser, Zeroconf

        encontrado = {"url": ""}
        tipo = '_oficinapesca._tcp.local.'

        class _Listener:
            def add_service(self, zc, service_type, name):
                if encontrado['url']:
                    return
                info = zc.get_service_info(service_type, name, timeout=int(timeout_seg * 1000))
                if not info or not info.addresses:
                    return
                try:
                    host = socket.inet_ntoa(info.addresses[0])
                except Exception:
                    return
                port = int(info.port or 8000)
                encontrado['url'] = f'http://{host}:{port}'

            def update_service(self, zc, service_type, name):
                self.add_service(zc, service_type, name)

            def remove_service(self, zc, service_type, name):
                return None

        zc = Zeroconf()
        try:
            listener = _Listener()
            browser = ServiceBrowser(zc, tipo, listener)
            limite = time.time() + max(1.0, timeout_seg)
            while time.time() < limite and not encontrado['url']:
                time.sleep(0.1)
            del browser
        finally:
            zc.close()

        if encontrado['url']:
            _DISCOVERY_CACHE['url'] = encontrado['url']
            _DISCOVERY_CACHE['ts'] = agora
            return encontrado['url']
    except Exception:
        pass

    return base_cfg or 'http://localhost:8000'


def obter_modo_operacao() -> str:
    """Retorna modo de operaÃ§Ã£o atual: local (padrÃ£o) ou rede."""
    try:
        cfg = _ler_cfg()
        # Adiciona um log de aviso se o modo Ã© rede mas o servidor_url ainda Ã© localhost
        if cfg.get('app', 'modo', fallback='local').lower() == 'rede':
            servidor_url_cfg = cfg.get('app', 'servidor_url', fallback='http://localhost:8000').strip().lower()
            if "localhost" in servidor_url_cfg or "127.0.0.1" in servidor_url_cfg:
                get_logger("config").warning("Modo 'rede' ativado, mas 'servidor_url' ainda aponta para 'localhost'. Dispositivos externos nÃ£o conseguirÃ£o se conectar.")

        modo = str(cfg.get('app', 'modo', fallback='local')).strip().lower()
        return modo if modo in {'local', 'rede'} else 'local'
    except Exception:
        return 'local'


def _restaurar_banco_por_backup_se_necessario() -> tuple[bool, str]:
    """Restaura oficina.db automaticamente do backup mais recente quando ausente."""
    try:
        if os.path.exists(CAMINHO_BANCO) and os.path.getsize(CAMINHO_BANCO) > 0:
            return False, "Banco local jÃ¡ existe; restauraÃ§Ã£o automÃ¡tica nÃ£o necessÃ¡ria."
    except Exception:
        pass

    diretorios_backup = [
        os.path.join(DIRETORIO_ATUAL, "backup_db"),
        os.path.join(os.path.dirname(DIRETORIO_ATUAL), "backup_db"),
        os.path.join(os.getcwd(), "backup_db"),
    ]

    candidatos = []
    vistos = set()
    for pasta in diretorios_backup:
        if not os.path.isdir(pasta):
            continue
        for padrao in ("*.db", "*.sqlite", "*.sqlite3"):
            for caminho in glob.glob(os.path.join(pasta, padrao)):
                try:
                    abs_path = os.path.abspath(caminho)
                    if abs_path in vistos:
                        continue
                    vistos.add(abs_path)
                    if os.path.abspath(CAMINHO_BANCO) == abs_path:
                        continue
                    if os.path.getsize(abs_path) <= 0:
                        continue
                    candidatos.append(abs_path)
                except Exception:
                    continue

    if not candidatos:
        return False, "Nenhum backup local encontrado para restauraÃ§Ã£o automÃ¡tica."

    candidatos.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    os.makedirs(os.path.dirname(CAMINHO_BANCO), exist_ok=True)

    for origem in candidatos:
        try:
            shutil.copy2(origem, CAMINHO_BANCO)
            with sqlite3.connect(CAMINHO_BANCO, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
                cursor.fetchone()
            return True, f"Banco restaurado automaticamente de: {origem}"
        except Exception:
            try:
                if os.path.exists(CAMINHO_BANCO):
                    os.remove(CAMINHO_BANCO)
            except Exception:
                pass
            continue

    return False, "Falha ao restaurar banco a partir dos backups encontrados."


def configurar_logging() -> logging.Logger:
    """Configura logger da aplicaÃ§Ã£o com saÃ­da em arquivo."""
    logger = logging.getLogger("oficina")
    if logger.handlers:
        return logger

    os.makedirs(os.path.dirname(CAMINHO_LOG), exist_ok=True)
    logger.setLevel(logging.INFO)

    handler = logging.FileHandler(CAMINHO_LOG, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    try:
        _habilitado, _url_cfg, token, _intervalo = _obter_config_envio_logs()
        # O handler é SEMPRE registrado; ele resolve a URL dinamicamente no emit.
        # Assim, mesmo que FRS_APPS_SCRIPT_ENDPOINT seja preenchido depois,
        # os erros serão encaminhados sem reconfigurar o logger.
        err_handler = _ErrorForwardHandler(token)
        err_handler.setFormatter(formatter)
        logger.addHandler(err_handler)
    except Exception:
        pass

    logger.propagate = False
    return logger


def get_logger(nome: Optional[str] = None) -> logging.Logger:
    base_logger = configurar_logging()
    if not nome:
        return base_logger
    return base_logger.getChild(nome)


def _caminho_meta_envio_logs() -> str:
    return os.path.join(DIRETORIO_ATUAL, "logs", "log_envio_meta.json")


def _ler_meta_envio_logs() -> dict:
    try:
        with open(_caminho_meta_envio_logs(), "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _salvar_meta_envio_logs(payload: dict) -> None:
    os.makedirs(os.path.join(DIRETORIO_ATUAL, "logs"), exist_ok=True)
    with open(_caminho_meta_envio_logs(), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _deve_enviar_logs(meta: dict, intervalo_dias: int) -> bool:
    ultimo = str(meta.get("ultimo_envio", "")).strip()
    if not ultimo:
        return True
    try:
        dt_ultimo = datetime.fromisoformat(ultimo)
    except Exception:
        return True
    return (datetime.now() - dt_ultimo).days >= max(1, int(intervalo_dias))


def _obter_config_envio_logs() -> tuple[bool, str, str, int]:
    cfg = _ler_cfg()
    habilitado = cfg.getboolean("suporte", "envio_logs_quinzenal", fallback=True)
    url = str(cfg.get("suporte", "log_upload_url", fallback=CENTRAL_LOG_UPLOAD_URL)).strip()
    token = str(cfg.get("suporte", "log_upload_token", fallback="")).strip()
    intervalo = cfg.getint("suporte", "log_upload_intervalo_dias", fallback=15)
    return habilitado, url, token, max(1, int(intervalo))


def enviar_log_automatico_quinzenal() -> tuple[bool, str]:
    """Envia o log principal ao suporte quando completar o intervalo configurado."""
    log = get_logger("suporte")
    habilitado, url, token, intervalo = _obter_config_envio_logs()
    if not habilitado:
        return False, "Envio de logs estÃ¡ desabilitado no config.cfg."
    if not url:
        return False, "log_upload_url nÃ£o configurado em [suporte]."

    meta = _ler_meta_envio_logs()
    if not _deve_enviar_logs(meta, intervalo):
        return False, "Ainda nÃ£o atingiu o intervalo para novo envio de logs."

    if not os.path.exists(CAMINHO_LOG):
        return False, f"Log nÃ£o encontrado em: {CAMINHO_LOG}"

    try:
        with open(CAMINHO_LOG, "rb") as f:
            bruto = f.read()
        # Limita payload para nÃ£o estourar integraÃ§Ã£o remota.
        texto = bruto[-800_000:].decode("utf-8", errors="replace")
    except Exception as e:
        return False, f"Falha ao ler arquivo de log: {e}"

    payload = {
        "app": "Oficina de Pesca",
        "versao": APP_VERSION,
        "destino_suporte": CENTRAL_SUPORTE_EMAIL,
        "host": platform.node(),
        "enviado_em": datetime.now().isoformat(timespec="seconds"),
        "arquivo": os.path.basename(CAMINHO_LOG),
        "conteudo": texto,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": f"OficinaPesca/{APP_VERSION}",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            status = int(getattr(resp, "status", 0) or 0)
            if status < 200 or status >= 300:
                return False, f"Servidor de logs retornou HTTP {status}."
    except urllib.error.HTTPError as e:
        return False, f"Falha HTTP no envio de logs: {getattr(e, 'code', 'N/A')}"
    except Exception as e:
        return False, f"Erro ao enviar logs: {e}"

    _salvar_meta_envio_logs(
        {
            "ultimo_envio": datetime.now().isoformat(timespec="seconds"),
            "intervalo_dias": intervalo,
            "destino": url,
        }
    )
    log.info("Envio automÃ¡tico de logs concluÃ­do com sucesso para o suporte remoto.")
    return True, "Logs enviados com sucesso."

@contextmanager
def get_db_connection():
    """Context manager para garantir que a conexÃ£o sempre feche."""
    conn = sqlite3.connect(CAMINHO_BANCO, timeout=10)
    # WAL mode: permite leituras simultÃ¢neas sem bloquear escritas
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    try:
        yield conn
    except sqlite3.Error as e:
        get_logger("db").exception("Erro no banco de dados: %s", e)
        raise
    finally:
        conn.close()


def _parse_data_br_flex_db(valor_data: str):
    txt = str(valor_data or "").strip()
    if not txt or txt.upper() == "VAZIO":
        return None
    formatos = (
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
    )
    for fmt in formatos:
        try:
            return datetime.strptime(txt, fmt)
        except Exception:
            continue
    return None


def listar_os_rejeitados_abandono_dashboard(
    dias_abandono_min: int = 20,
    dias_aviso1: int = 15,
    dias_aviso2: int = 85,
    limite_card: int = 8,
) -> dict:
    """Retorna itens do card Rejeitados/Abandono e níveis de alerta para o dashboard."""
    hoje = datetime.now()
    itens = []

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id,
                    COALESCE(cliente, ''),
                    COALESCE(telefone_cliente_whatsapp, ''),
                    UPPER(COALESCE(status, '')),
                    UPPER(COALESCE(status_entrega, '')),
                    COALESCE(valor_total, 0),
                    COALESCE(saldo, 0),
                    COALESCE(data, ''),
                    COALESCE(data_finalizacao, ''),
                    COALESCE(data_entrega, '')
                FROM orcamentos_aguardo
                WHERE UPPER(COALESCE(status, '')) IN ('REPROVADO', 'ABANDONO')
                """
            )
            rows = cursor.fetchall()

        for row in rows:
            os_id = int(row[0] or 0)
            cliente = str(row[1] or "").strip()
            telefone = str(row[2] or "").strip()
            status = str(row[3] or "").strip()
            status_entrega = str(row[4] or "").strip()
            valor_total = float(row[5] or 0)
            saldo = float(row[6] or 0)
            data_base = str(row[7] or "").strip()
            data_finalizacao = str(row[8] or "").strip()
            data_entrega = str(row[9] or "").strip()

            if status_entrega == "ENTREGUE" or (data_entrega and data_entrega.upper() != "VAZIO"):
                continue

            dt_ref = _parse_data_br_flex_db(data_finalizacao) or _parse_data_br_flex_db(data_base)
            if dt_ref is None:
                continue

            dias = max(0, (hoje.date() - dt_ref.date()).days)

            # Regra de negócio: status ABANDONO só entra no card após 20 dias sem retirada.
            if status == "ABANDONO" and dias < int(dias_abandono_min or 0):
                continue

            valor_alerta = saldo if float(saldo or 0) > 0 else valor_total

            if dias >= int(dias_aviso2 or 0):
                nivel_alerta = "critico"
            elif dias >= int(dias_aviso1 or 0):
                nivel_alerta = "aviso"
            else:
                nivel_alerta = "normal"

            itens.append(
                {
                    "os_id": os_id,
                    "cliente": cliente,
                    "telefone": telefone,
                    "status_tipo": status.lower(),
                    "valor": float(valor_alerta or 0),
                    "dias": dias,
                    "nivel_alerta": nivel_alerta,
                }
            )
    except Exception as exc:
        get_logger("dashboard").info("Falha ao consultar rejeitados/abandono: %s", exc)
        return {
            "itens_card": [],
            "itens_aviso1": [],
            "itens_aviso2": [],
            "tem_aviso1": False,
            "tem_aviso2": False,
        }

    itens.sort(key=lambda x: int(x.get("dias") or 0), reverse=True)
    itens_aviso2 = [x for x in itens if x.get("nivel_alerta") == "critico"]
    itens_aviso1 = [x for x in itens if x.get("nivel_alerta") == "aviso"]

    if isinstance(limite_card, int) and limite_card > 0:
        itens_card = itens[:limite_card]
    else:
        itens_card = list(itens)

    return {
        "itens_card": itens_card,
        "itens_aviso1": itens_aviso1,
        "itens_aviso2": itens_aviso2,
        "tem_aviso1": bool(itens_aviso1),
        "tem_aviso2": bool(itens_aviso2),
    }


def obter_info_nova_versao() -> dict:
    """Obtém dados da versão remota (GitHub Releases/Tags + fallback manifesto)."""
    # Limpeza agressiva da URL para evitar caracteres de controle e prefixos indesejados.
    url_raw = str(URL_CHECK_VERSAO or "").strip()
    match = re.search(r'https?://[^\s]+', url_raw)
    url_limpa = match.group(0) if match else ""

    owner = "frscomercial6-eng"
    repo = "oficina-pesca-updates"

    def _normalizar_versao(valor: str) -> str:
        partes = [int(x) for x in re.findall(r"\d+", str(valor or "").strip().lower())]
        if not partes:
            return ""
        return ".".join(str(x) for x in partes)

    def _tuple_versao(valor: str) -> tuple[int, ...]:
        partes = [int(x) for x in re.findall(r"\d+", str(valor or "").strip().lower())]
        return tuple(partes) if partes else (0,)

    def _montar_url_instalador_por_versao(versao: str) -> str:
        v = _normalizar_versao(versao)
        if not v:
            return str(CENTRAL_UPDATE_DOWNLOAD_URL or "").strip()
        return f"https://github.com/{owner}/{repo}/releases/download/v{v}/Oficina_Pesca_Instalador.exe"

    def _corrigir_url_download_por_versao(url: str, versao: str) -> str:
        u = str(url or "").strip()
        v = _normalizar_versao(versao)
        if not v:
            return u
        if not u:
            return _montar_url_instalador_por_versao(v)
        # Corrige manifests defasados que apontam para outra tag.
        if "github.com" in u.lower() and "/releases/download/" in u.lower():
            return re.sub(r"/releases/download/v[0-9]+(?:\.[0-9]+)*/", f"/releases/download/v{v}/", u, flags=re.IGNORECASE)
        return u

    def _gerar_urls_remotas_oficiais() -> list[str]:
        # Mantém foco em manifesto remoto RAW oficial para compatibilidade com clientes em produção.
        base_fixa = "https://raw.githubusercontent.com/frscomercial6-eng/oficina-pesca-updates/main/"
        candidatos_base = [url_limpa, str(CENTRAL_UPDATE_MANIFEST_URL or "").strip(), str(URL_CHECK_VERSAO or "").strip(), base_fixa + "config.json"]

        saida: list[str] = []
        vistos = set()

        def _add(url: str) -> None:
            u = str(url or "").strip()
            if not u:
                return
            if not re.match(r"^https?://", u, flags=re.IGNORECASE):
                return
            if u in vistos:
                return
            vistos.add(u)
            saida.append(u)

        for base in candidatos_base:
            _add(base)
            lower = str(base or "").lower()
            if lower.endswith("config.json"):
                _add(base[:-11] + "version.txt")
                _add(base[:-11] + "version.json")
                _add(base[:-11] + "versao.json")
            elif lower.endswith("version.txt"):
                _add(base[:-11] + "config.json")
                _add(base[:-11] + "version.json")
                _add(base[:-11] + "versao.json")
            elif lower.endswith("versao.txt"):
                _add(base[:-10] + "config.json")
                _add(base[:-10] + "version.json")
                _add(base[:-10] + "versao.json")
            elif lower.endswith("version.json"):
                _add(base[:-12] + "config.json")
                _add(base[:-12] + "version.txt")
                _add(base[:-12] + "versao.json")

        return saida

    def _parse_manifesto(conteudo: str) -> dict:
        bruto = str(conteudo or "").strip()
        if not bruto:
            return {}

        # Tenta JSON primeiro
        try:
            data_json = json.loads(bruto)
            if isinstance(data_json, dict):
                update_block = data_json.get("update")
                if isinstance(update_block, dict):
                    merged = dict(data_json)
                    merged.update(update_block)
                    data_json = merged

                versao = data_json.get("versao") or data_json.get("version") or data_json.get("tag") or data_json.get("latest_version") or ""
                novidades = data_json.get("novidades") or data_json.get("changelog") or data_json.get("notes") or data_json.get("descricao") or ""
                url_download = (
                    data_json.get("url_download")
                    or data_json.get("download_url")
                    or data_json.get("download")
                    or data_json.get("latest_download")
                    or CENTRAL_UPDATE_DOWNLOAD_URL
                )
                versao_norm = _normalizar_versao(str(versao).strip())
                url_download = _corrigir_url_download_por_versao(str(url_download).strip(), versao_norm)

                saida = {
                    "versao": versao_norm or str(versao).strip(),
                    "novidades": str(novidades).strip(),
                    "url_download": str(url_download).strip(),
                }
                return {k: v for k, v in saida.items() if v}
        except Exception:
            pass

        # Formato TXT: chave=valor / chave: valor
        data_txt = {}
        for linha in bruto.splitlines():
            item = linha.strip()
            if not item or item.startswith("#"):
                continue
            if "=" in item:
                k, v = item.split("=", 1)
            elif ":" in item:
                k, v = item.split(":", 1)
            else:
                # Permite arquivo com apenas "1.2.3"
                if re.match(r"^\d+(\.\d+)+$", item):
                    data_txt.setdefault("versao", item)
                continue

            chave = str(k or "").strip().lower()
            valor = str(v or "").strip()
            if not chave:
                continue
            data_txt[chave] = valor

        if not data_txt:
            return {}

        # Normaliza aliases comuns
        versao = data_txt.get("versao") or data_txt.get("version") or data_txt.get("tag") or ""
        novidades = data_txt.get("novidades") or data_txt.get("changelog") or data_txt.get("notes") or ""
        url_download = (
            data_txt.get("url_download")
            or data_txt.get("download")
            or data_txt.get("url")
            or data_txt.get("download_url")
            or CENTRAL_UPDATE_DOWNLOAD_URL
            or ""
        )
        versao_norm = _normalizar_versao(str(versao).strip())
        url_download = _corrigir_url_download_por_versao(str(url_download).strip(), versao_norm)

        saida = {
            "versao": versao_norm or str(versao).strip(),
            "novidades": str(novidades).strip(),
            "url_download": str(url_download).strip(),
        }
        return {k: v for k, v in saida.items() if v}

    def _consultar_release_latest(headers: dict) -> dict:
        import urllib.request

        api = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(payload)
        if not isinstance(data, dict):
            return {}

        versao = _normalizar_versao(str(data.get("tag_name") or data.get("name") or ""))
        if not versao:
            return {}

        novidades = str(data.get("body") or data.get("name") or "").strip()
        assets = data.get("assets") if isinstance(data.get("assets"), list) else []
        url_download = ""

        for asset in assets:
            if not isinstance(asset, dict):
                continue
            nome = str(asset.get("name") or "").strip().lower()
            link = str(asset.get("browser_download_url") or "").strip()
            if nome == "oficina_pesca_instalador.exe" and link:
                url_download = link
                break

        if not url_download:
            for asset in assets:
                if not isinstance(asset, dict):
                    continue
                nome = str(asset.get("name") or "").strip().lower()
                link = str(asset.get("browser_download_url") or "").strip()
                if nome.endswith(".exe") and link:
                    url_download = link
                    break

        url_download = _corrigir_url_download_por_versao(url_download or _montar_url_instalador_por_versao(versao), versao)
        return {"versao": versao, "novidades": novidades, "url_download": url_download}

    def _consultar_tags(headers: dict) -> dict:
        import urllib.request

        api = f"https://api.github.com/repos/{owner}/{repo}/tags?per_page=30"
        req = urllib.request.Request(api, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
        data = json.loads(payload)
        if not isinstance(data, list):
            return {}

        candidatos = []
        for item in data:
            if not isinstance(item, dict):
                continue
            tag = str(item.get("name") or "").strip()
            versao = _normalizar_versao(tag)
            if not versao:
                continue
            candidatos.append((_tuple_versao(versao), versao))

        if not candidatos:
            return {}

        candidatos.sort(reverse=True)
        versao = candidatos[0][1]
        return {
            "versao": versao,
            "novidades": f"Nova versão disponível: v{versao}",
            "url_download": _montar_url_instalador_por_versao(versao),
        }

    try:
        import urllib.request

        headers = {
            "User-Agent": f"OficinaPesca/{APP_VERSION}",
            "Accept": "application/vnd.github+json",
        }

        # 1) Fonte principal: GitHub release mais recente.
        try:
            info = _consultar_release_latest(headers)
            if info.get("versao"):
                return info
        except Exception:
            pass

        # 2) Fallback: tags do repositório quando release ainda não estiver completa.
        try:
            info = _consultar_tags(headers)
            if info.get("versao"):
                return info
        except Exception:
            pass

        # 3) Fallback legado: manifestos RAW (config/version/versao txt/json).
        urls_tentativa = _gerar_urls_remotas_oficiais()

        ultimo_erro = ""
        for url in urls_tentativa:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"})
                with urllib.request.urlopen(req, timeout=4) as resp:
                    payload = resp.read().decode("utf-8", errors="ignore")
                info = _parse_manifesto(payload)
                if info:
                    return info
            except Exception as e:
                ultimo_erro = str(e)

        if ultimo_erro:
            print(f"❌ ERRO CRÍTICO NA BUSCA DE ATUALIZAÇÃO: {ultimo_erro}")
        return {}
    except Exception as e:
        print(f"❌ ERRO CRÍTICO NA BUSCA DE ATUALIZAÇÃO: {e}")
        return {}


def eh_versao_mais_nova(versao_remota: str, versao_local: str) -> bool:
    """Compara versÃµes no formato semÃ¢ntico simples (ex.: 1.2.3)."""
    def _to_tuple(v: str) -> tuple[int, ...]:
        texto = str(v or "").strip().lower()
        # Aceita formatos como "1.0.30", "v1.0.30" e "versao=1.0.30".
        partes = [int(x) for x in re.findall(r"\d+", texto)]
        if not partes:
            return (0,)
        return tuple(partes)

    remota = _to_tuple(versao_remota)
    local = _to_tuple(versao_local)

    tamanho = max(len(remota), len(local))
    remota += (0,) * (tamanho - len(remota))
    local += (0,) * (tamanho - len(local))
    return remota > local


def verificar_nova_versao() -> tuple[bool, str, str]:
    """Verifica se hÃ¡ nova versÃ£o disponÃ­vel. Retorna (disponivel, versao_nova, novidades)."""
    data = obter_info_nova_versao()
    versao_remota = str(data.get("versao", "")).strip()
    if versao_remota and eh_versao_mais_nova(versao_remota, APP_VERSION):
        return True, versao_remota, str(data.get("novidades", ""))
    return False, "", ""


def _versao_em_tupla(valor: str) -> tuple[int, ...]:
    partes = [int(x) for x in re.findall(r"\d+", str(valor or "").strip().lower())]
    return tuple(partes) if partes else (0,)


def _versao_eh_igual_ou_maior(versao_atual: str, versao_ref: str) -> bool:
    atual = _versao_em_tupla(versao_atual)
    ref = _versao_em_tupla(versao_ref)
    tamanho = max(len(atual), len(ref))
    atual += (0,) * (tamanho - len(atual))
    ref += (0,) * (tamanho - len(ref))
    return atual >= ref


def _ler_estado_update_local() -> dict:
    try:
        if not os.path.exists(ARQUIVO_ESTADO_UPDATE):
            return {}
        with open(ARQUIVO_ESTADO_UPDATE, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def _salvar_estado_update_local(dados: dict) -> None:
    try:
        os.makedirs(os.path.dirname(ARQUIVO_ESTADO_UPDATE), exist_ok=True)
        with open(ARQUIVO_ESTADO_UPDATE, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def registrar_update_aplicado_local(versao: str, origem: str = "desktop", status: str = "aplicado") -> None:
    dados = _ler_estado_update_local()
    dados["ultima_versao_aplicada"] = str(versao or "").strip()
    dados["status"] = str(status or "aplicado").strip() or "aplicado"
    dados["origem"] = str(origem or "desktop").strip() or "desktop"
    dados["atualizado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _salvar_estado_update_local(dados)


def bloqueio_loop_update_ativo(versao_alvo: str = "") -> bool:
    alvo = str(versao_alvo or "").strip()
    if alvo and eh_versao_mais_nova(alvo, APP_VERSION):
        return False

    # A trava emergencial valia apenas para a própria versão problemática.
    # Se o cliente já está acima da versão de trava, nunca deve bloquear updates.
    if _versao_em_tupla(APP_VERSION) > _versao_em_tupla(VERSAO_TRAVA_LOOP_UPDATE):
        return False

    # Trava de segurança emergencial: se o app local já chegou na 1.0.50,
    # nunca tenta baixar novamente o instalador no startup.
    if _versao_eh_igual_ou_maior(APP_VERSION, VERSAO_TRAVA_LOOP_UPDATE):
        dados = _ler_estado_update_local()
        versao_local = str(dados.get("ultima_versao_aplicada", "")).strip()
        if not versao_local:
            registrar_update_aplicado_local(VERSAO_TRAVA_LOOP_UPDATE, origem="startup", status="travado")
            return True
        return _versao_eh_igual_ou_maior(versao_local, VERSAO_TRAVA_LOOP_UPDATE)
    return False


def limpar_cache_instalacao_update() -> tuple[bool, str]:
    base_tmp = os.path.join(tempfile.gettempdir(), "oficina_pesca_update")
    if not os.path.isdir(base_tmp):
        return True, "Cache de atualização limpo."

    removidos = 0
    falhas = 0
    for nome in os.listdir(base_tmp):
        caminho = os.path.join(base_tmp, nome)
        nome_lower = nome.lower()
        if os.path.isdir(caminho) and nome_lower.startswith("run_"):
            try:
                shutil.rmtree(caminho, ignore_errors=True)
                removidos += 1
            except Exception:
                falhas += 1
            continue
        if not (
            nome_lower.endswith(".part")
            or nome_lower.endswith(".exe")
            or nome_lower.endswith(".tmp")
            or nome_lower.endswith(".cmd")
            or nome_lower.endswith(".json")
        ):
            continue
        try:
            if os.path.isfile(caminho):
                os.remove(caminho)
                removidos += 1
        except Exception:
            falhas += 1

    if falhas:
        return False, f"Cache parcialmente limpo ({removidos} removido(s), {falhas} falha(s))."
    return True, f"Cache de atualização limpo ({removidos} arquivo(s) removido(s))."


def _resetar_trava_update_para_versao_alvo(versao_alvo: str) -> tuple[bool, str]:
    alvo = str(versao_alvo or "").strip()
    if not alvo or alvo != VERSAO_TRAVA_LOOP_UPDATE:
        return True, "Sem reset de trava para esta versão-alvo."

    try:
        if os.path.exists(ARQUIVO_ESTADO_UPDATE):
            os.remove(ARQUIVO_ESTADO_UPDATE)
            return True, f"Trava local removida para atualização {alvo}."
        return True, f"Trava local não encontrada para atualização {alvo}."
    except Exception as exc:
        return False, f"Falha ao resetar trava local da atualização {alvo}: {exc}"


def obter_politica_atualizacao(licenca_ativa: bool, validade_licenca: str, tipo_licenca: str = "") -> tuple[bool, str]:
    """Retorna polÃ­tica de atualizaÃ§Ã£o: (automatica_liberada, mensagem)."""
    tipo = str(tipo_licenca or "").upper().strip()
    validade = str(validade_licenca or "").upper().strip()
    if not tipo:
        tipo = "PERMANENTE" if validade == "PERMANENTE" else "MENSAL"

    if licenca_ativa and (validade == "PERMANENTE" or tipo == "PERMANENTE"):
        return True, "AtualizaÃ§Ã£o automÃ¡tica liberada para cliente permanente."

    if tipo in {"PROMOCIONAL", "MENSAL"}:
        valor_plano = VALOR_LICENCA_MENSAL
        nome_plano = tipo.lower()
    elif tipo in {"TRIMESTRAL", "SEMESTRAL"}:
        valor_plano = VALOR_LICENCA_TRIMESTRAL
        nome_plano = tipo.lower()
    else:
        valor_plano = VALOR_LICENCA_PERMANENTE
        nome_plano = tipo.lower() if tipo else "anual"

    valor = f"{valor_plano:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    msg = (
        f"Cliente {nome_plano}: atualizaÃ§Ã£o mediante renovaÃ§Ã£o do plano (R$ {valor}). "
        "Pagamento via InfinitePay (PIX/cartÃ£o)."
    )
    return False, msg


def _sha256_texto(texto: str) -> str:
    return hashlib.sha256(str(texto or "").encode("utf-8")).hexdigest().lower()


def gerar_hash_publico_licenca(chave_licenca: str) -> str:
    """Retorna hash SHA-256 da chave para cadastro remoto sem expor a chave original."""
    return _sha256_texto(chave_licenca)


def validar_licenca_remota(url_licencas: str, chave_licenca: str) -> tuple[bool, str, str]:
    """
    Valida a licença em endpoint remoto (ex.: JSON no GitHub raw).

    Formato esperado do JSON remoto:
    {
      "licencas": {
        "<sha256_da_chave>": {"status": "ativo", "tipo": "PERMANENTE|PROMOCIONAL|MENSAL|TRIMESTRAL|SEMESTRAL|ANUAL"}
      }
    }
    """
    url = str(url_licencas or "").strip()
    chave = str(chave_licenca or "").strip()
    if not url or not chave:
        return False, "Fonte remota de licenças nÃ£o configurada.", ""

    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"})
        with urllib.request.urlopen(req, timeout=1) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        licencas = data.get("licencas", {}) if isinstance(data, dict) else {}
        if not isinstance(licencas, dict):
            return False, "Cadastro remoto de licenças invÃ¡lido.", ""

        chave_hash = _sha256_texto(chave)
        registro = licencas.get(chave_hash, {})
        if not isinstance(registro, dict):
            return False, "Licença nÃ£o encontrada no cadastro remoto.", ""

        status = str(registro.get("status", "")).lower().strip()
        tipo = str(registro.get("tipo", "")).upper().strip()
        if status != "ativo":
            return False, "Licença encontrada, porÃ©m inativa no cadastro remoto.", tipo

        if tipo not in {"PERMANENTE", "MENSAL", "TRIMESTRAL"}:
            tipo = ""

        return True, "Licença validada no cadastro remoto.", tipo
    except Exception as e:
        return False, f"Falha ao validar licença no cadastro remoto: {e}", ""


def deve_verificar_atualizacao(intervalo_dias: int = 15) -> bool:
    """Controla periodicidade de checagem de atualizaÃ§Ã£o por data (ex.: 15 dias)."""
    intervalo = max(1, int(intervalo_dias or 15))
    hoje = date.today().toordinal()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'ultimo_check_update_ordinal'")
        row = cursor.fetchone()

        try:
            ultimo = int(row[0]) if row and row[0] is not None else 0
        except Exception:
            ultimo = 0

        if ultimo <= 0 or (hoje - ultimo) >= intervalo:
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('ultimo_check_update_ordinal', ?)",
                (hoje,),
            )
            conn.commit()
            return True

    return False


def validar_email_basico(email: str) -> bool:
    email = str(email or "").strip()
    if not email or len(email) > 254:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))


def _diretorio_oauth_usuario() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or DIRETORIO_ATUAL
    pasta = os.path.join(base, "OficinaPesca")
    os.makedirs(pasta, exist_ok=True)
    return pasta


def _base_recursos_runtime() -> str:
    return getattr(sys, "_MEIPASS", DIRETORIO_RECURSOS)


def _resolver_recurso(*partes: str) -> str:
    return os.path.join(_base_recursos_runtime(), *partes)


def _token_google_drive_usuario_path() -> str:
    # Token OAuth2 persistido no AppData/LocalAppData para operação silenciosa do usuário.
    return os.path.join(_diretorio_oauth_usuario(), "token.json")


def _token_google_drive_usuario_paths() -> list[str]:
    pasta_oauth = _diretorio_oauth_usuario()
    candidatos = [
        _token_google_drive_usuario_path(),
        os.path.join(pasta_oauth, "google_drive_user_token.json"),
        os.path.join(DIRETORIO_ATUAL, "token.json"),
        os.path.join(os.getcwd(), "token.json"),
    ]
    vistos = set()
    ordenados = []
    for caminho in candidatos:
        chave = os.path.normcase(os.path.abspath(caminho))
        if chave in vistos:
            continue
        vistos.add(chave)
        ordenados.append(caminho)
    return ordenados


def _salvar_token_google_drive_usuario(creds) -> None:
    caminhos_destino = [_token_google_drive_usuario_path()]
    payload = creds.to_json()
    for caminho in caminhos_destino:
        try:
            pasta = os.path.dirname(caminho)
            if pasta:
                os.makedirs(pasta, exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(payload)
        except Exception:
            # Continua tentando os demais caminhos para máxima compatibilidade.
            continue


def _client_secret_google_path() -> str:
    caminho_env = str(os.environ.get("OFP_GOOGLE_OAUTH_CLIENT_SECRET", "") or "").strip()
    if caminho_env and os.path.exists(caminho_env):
        return os.path.abspath(caminho_env)

    if getattr(sys, "frozen", False):
        base_bundle = getattr(sys, "_MEIPASS", DIRETORIO_RECURSOS)
        candidatos = [
            os.path.join(base_bundle, "assets", "client_secret_desktop.json"),
            os.path.join(base_bundle, "client_secret_desktop.json"),
        ]
    else:
        candidatos = [
            _resolver_recurso("assets", "client_secret_desktop.json"),
            _resolver_recurso("client_secret_desktop.json"),
            os.path.join(DIRETORIO_ATUAL, "assets", "client_secret_desktop.json"),
            os.path.join(DIRETORIO_ATUAL, "client_secret_desktop.json"),
            os.path.join(DIRETORIO_RECURSOS, "assets", "client_secret_desktop.json"),
            os.path.join(DIRETORIO_RECURSOS, "client_secret_desktop.json"),
            os.path.join(os.getcwd(), "assets", "client_secret_desktop.json"),
            os.path.join(os.getcwd(), "client_secret_desktop.json"),
        ]
    for caminho in candidatos:
        if os.path.exists(caminho):
            return os.path.abspath(caminho)
    return ""


def _verificar_arquivo_credenciais_google_drive() -> tuple[bool, str]:
    """Valida presença do client secret OAuth2 para autenticação do Drive."""
    caminho = _client_secret_google_path()
    if caminho and os.path.exists(caminho):
        return True, caminho
    return (
        False,
        "Arquivo de credenciais Google OAuth2 não encontrado. "
        "Use a opção 'Conectar Google Drive' para solicitar autenticação e concluir a configuração.",
    )


def _obter_credenciais_google_drive_usuario(interativo: bool = False, login_hint: str = ""):
    if GoogleCredentials is None:
        return None, "Dependências OAuth2 ausentes. Instale google-auth, google-auth-oauthlib e google-api-python-client."

    creds = None

    try:
        for candidato_token in _token_google_drive_usuario_paths():
            if not os.path.exists(candidato_token):
                continue
            creds = GoogleCredentials.from_authorized_user_file(candidato_token, GOOGLE_DRIVE_USER_SCOPES)
            break
    except Exception:
        creds = None

    try:
        if creds and creds.expired and creds.refresh_token and GoogleAuthRequest is not None:
            creds.refresh(GoogleAuthRequest())
            _salvar_token_google_drive_usuario(creds)
    except Exception:
        creds = None

    if creds and getattr(creds, "valid", False):
        return creds, "OK"

    if not interativo:
        existe_client_secret, detalhe = _verificar_arquivo_credenciais_google_drive()
        if not existe_client_secret:
            return None, detalhe
        return None, "Usuário ainda não autenticado no Google Drive. Use 'Conectar Google Drive' para autenticar."

    if InstalledAppFlow is None:
        return None, "Fluxo OAuth2 indisponível. Dependência google-auth-oauthlib não encontrada."

    existe_client_secret, detalhe = _verificar_arquivo_credenciais_google_drive()
    if not existe_client_secret:
        return None, (
            "Arquivo client_secret_desktop.json não encontrado no bundle interno do executável. "
            "Refaça o build incluindo esse arquivo como recurso."
        )
    client_secret = detalhe

    try:
        flow = InstalledAppFlow.from_client_secrets_file(client_secret, GOOGLE_DRIVE_USER_SCOPES)
        extra_kwargs: dict = {"open_browser": True}
        if login_hint:
            extra_kwargs["login_hint"] = login_hint
        creds = flow.run_local_server(port=0, **extra_kwargs)
        _salvar_token_google_drive_usuario(creds)
        return creds, "OK"
    except Exception as e:
        return None, f"Falha no login OAuth2 (Debug Google Code: {getattr(e, 'status_code', 'N/A')}) - Detalhes: {e}"


def conectar_google_drive_usuario(login_hint: str = "") -> tuple[bool, str, str]:
    """Autentica o usuário via OAuth2 e retorna (ok, mensagem, email)."""
    creds, msg = _obter_credenciais_google_drive_usuario(interativo=True, login_hint=login_hint)
    if not creds:
        return False, msg, ""

    if google_build is None:
        return False, "Dependência google-api-python-client não encontrada.", ""

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        about = service.about().get(fields="user(emailAddress,displayName)").execute()
        user = about.get("user", {}) if isinstance(about, dict) else {}
        email = str(user.get("emailAddress") or "").strip().lower()
        return True, "Conexão OAuth2 com Google Drive concluída.", email
    except Exception as e:
        # Tenta extrair o código de status HTTP ou erro interno do Google
        err_code = "Desconhecido"
        if hasattr(e, 'resp') and hasattr(e.resp, 'status'):
            err_code = e.resp.status
        elif hasattr(e, 'status_code'):
            err_code = e.status_code
        elif "12500" in str(e):
            err_code = "12500 (SIGN_IN_FAILED)"
            
        return False, f"Erro de Configuração Google (Código: {err_code}) - {e}", ""


def google_drive_usuario_conectado() -> bool:
    creds, _msg = _obter_credenciais_google_drive_usuario(interativo=False)
    return bool(creds)


def garantir_banco_no_drive_usuario() -> tuple[bool, str]:
    """Garante que o banco local esteja criado/atualizado no Drive pessoal do usuário logado."""
    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco local não encontrado para sincronizar no Google Drive do usuário."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg

    if google_build is None or MediaFileUpload is None:
        return False, "Dependências Google Drive ausentes para upload do banco."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)

        nome_pasta = GOOGLE_DRIVE_PASTA_APP.replace("'", "\\'")
        folder_query = (
            "mimeType='application/vnd.google-apps.folder' and "
            f"name='{nome_pasta}' and trashed=false"
        )
        folders = service.files().list(q=folder_query, fields="files(id,name)", pageSize=1).execute().get("files", [])
        if folders:
            folder_id = str(folders[0]["id"])
        else:
            pasta = service.files().create(
                body={"name": GOOGLE_DRIVE_PASTA_APP, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()
            folder_id = str(pasta["id"])

        arquivo_nome = "oficina.db"
        file_query = (
            "name='oficina.db' and trashed=false and "
            f"'{folder_id}' in parents"
        )
        arquivos = service.files().list(q=file_query, fields="files(id,name)", pageSize=1).execute().get("files", [])
        media = MediaFileUpload(CAMINHO_BANCO, mimetype="application/octet-stream", resumable=False)

        if arquivos:
            file_id = str(arquivos[0]["id"])
            service.files().update(fileId=file_id, media_body=media).execute()
            return True, "Banco local atualizado no Google Drive do usuário."

        service.files().create(
            body={"name": arquivo_nome, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        return True, "Banco local criado no Google Drive do usuário."
    except Exception as e:
        return False, f"Falha ao sincronizar banco no Google Drive do usuário: {e}"


def _obter_ou_criar_pasta_backup_drive_usuario(service, nome_pasta: str = "Oficina_Backup") -> str:
    nome = str(nome_pasta or "Oficina_Backup").strip() or "Oficina_Backup"
    nome_esc = nome.replace("'", "\\'")
    q = (
        "mimeType='application/vnd.google-apps.folder' and "
        f"name='{nome_esc}' and trashed=false"
    )
    pastas = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])
    if pastas:
        return str(pastas[0]["id"])

    pasta = service.files().create(
        body={"name": nome, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return str(pasta["id"])


def enviar_backup_banco_para_drive_usuario() -> tuple[bool, str]:
    """Cria um backup versionado do banco local na pasta Oficina_Backup do Drive do usuário."""
    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco local não encontrado para backup."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg

    if google_build is None or MediaFileUpload is None:
        return False, "Dependências Google Drive ausentes para upload do backup."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = _obter_ou_criar_pasta_backup_drive_usuario(service)

        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_backup = f"oficina_backup_{carimbo}.db"
        media = MediaFileUpload(CAMINHO_BANCO, mimetype="application/octet-stream", resumable=False)
        service.files().create(
            body={"name": nome_backup, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        return True, f"Backup enviado para o Drive: {nome_backup}"
    except Exception as e:
        return False, f"Falha ao enviar backup para o Drive do usuário: {e}"


def listar_backups_banco_drive_usuario(limit: int = 50) -> tuple[bool, list[dict], str]:
    """Lista backups .db da pasta Oficina_Backup no Drive pessoal autenticado."""
    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, [], msg

    if google_build is None:
        return False, [], "Dependência google-api-python-client não encontrada."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = _obter_ou_criar_pasta_backup_drive_usuario(service)
        limite = max(1, min(int(limit or 50), 200))
        q = f"name contains '.db' and trashed=false and '{folder_id}' in parents"
        arquivos = (
            service.files()
            .list(
                q=q,
                fields="files(id,name,modifiedTime,size)",
                orderBy="modifiedTime desc",
                pageSize=limite,
            )
            .execute()
            .get("files", [])
        )

        saida: list[dict] = []
        for item in arquivos:
            nome = str(item.get("name") or "")
            if not nome.lower().endswith(".db"):
                continue
            mod = str(item.get("modifiedTime") or "")
            try:
                dt = datetime.fromisoformat(mod.replace("Z", "+00:00"))
                mod_fmt = dt.strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                mod_fmt = mod
            saida.append(
                {
                    "id": str(item.get("id") or ""),
                    "name": nome,
                    "modified": mod_fmt,
                    "modified_raw": mod,
                    "size": str(item.get("size") or "0"),
                }
            )

        return True, saida, "OK"
    except Exception as e:
        return False, [], f"Falha ao listar backups no Drive do usuário: {e}"


def restaurar_backup_banco_drive_usuario(file_id: str, file_name: str = "") -> tuple[bool, str]:
    """Baixa um backup .db selecionado do Drive e substitui o banco local com segurança."""
    fid = str(file_id or "").strip()
    if not fid:
        return False, "Backup inválido: arquivo não selecionado."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg

    if google_build is None or MediaIoBaseDownload is None:
        return False, "Dependências Google Drive ausentes para restauração."

    try:
        import io

        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        req = service.files().get_media(fileId=fid)

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, req)
        done = False
        while not done:
            _status, done = downloader.next_chunk()

        conteudo = buffer.getvalue()
        if not conteudo:
            return False, "Arquivo baixado do Drive está vazio."

        pasta_backup = os.path.join(os.path.dirname(CAMINHO_BANCO), "backup_db")
        os.makedirs(pasta_backup, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")

        if os.path.exists(CAMINHO_BANCO):
            copia_previa = os.path.join(pasta_backup, f"pre_drive_restore_{carimbo}.db")
            shutil.copy2(CAMINHO_BANCO, copia_previa)

        with open(CAMINHO_BANCO, "wb") as f:
            f.write(conteudo)

        inicializar_banco()
        nome = str(file_name or "backup.db").strip() or "backup.db"
        return True, f"Backup restaurado com sucesso: {nome}"
    except Exception as e:
        return False, f"Falha ao restaurar backup do Drive: {e}"


def enviar_arquivo_para_drive_usuario(caminho_local: str, pasta_remota: str = "Oficina de Pesca - Arquivos") -> tuple[bool, str]:
    """Envia um arquivo local para o Drive pessoal autenticado via OAuth2."""
    arquivo = str(caminho_local or "").strip()
    if not arquivo or not os.path.isfile(arquivo):
        return False, "Arquivo local não encontrado para envio ao Drive do usuário."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg
    if google_build is None or MediaFileUpload is None:
        return False, "Dependências Google Drive ausentes para upload de arquivo."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)

        nome_pasta = str(pasta_remota or "Oficina de Pesca - Arquivos").strip()
        nome_pasta_esc = nome_pasta.replace("'", "\\'")
        pasta_q = f"mimeType='application/vnd.google-apps.folder' and name='{nome_pasta_esc}' and trashed=false"
        pastas = service.files().list(q=pasta_q, fields="files(id,name)", pageSize=1).execute().get("files", [])
        if pastas:
            folder_id = str(pastas[0]["id"])
        else:
            pasta = service.files().create(
                body={"name": nome_pasta, "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()
            folder_id = str(pasta["id"])

        nome_arq = os.path.basename(arquivo)
        nome_arq_esc = nome_arq.replace("'", "\\'")
        q_file = f"name='{nome_arq_esc}' and trashed=false and '{folder_id}' in parents"
        existentes = service.files().list(q=q_file, fields="files(id,name)", pageSize=1).execute().get("files", [])

        media = MediaFileUpload(arquivo, mimetype="application/octet-stream", resumable=False)
        if existentes:
            service.files().update(fileId=str(existentes[0]["id"]), media_body=media).execute()
            return True, f"Arquivo atualizado no Drive do usuário: {nome_arq}"

        service.files().create(
            body={"name": nome_arq, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        return True, f"Arquivo enviado ao Drive do usuário: {nome_arq}"
    except Exception as e:
        return False, f"Falha ao enviar arquivo para o Drive do usuário: {e}"


def obter_google_ai_key_mestre() -> str:
    """Retorna a chave de IA usada internamente pelo sistema."""
    if GOOGLE_AI_MASTER_KEY:
        return GOOGLE_AI_MASTER_KEY

    cfg = _ler_cfg()
    return str(cfg.get('ia_diagramas', 'gemini_api_key', fallback='') or '').strip()


def validar_google_ai_key_ativa() -> tuple[bool, str]:
    """Validação objetiva da chave da IA usada no login."""
    key = obter_google_ai_key_mestre()
    if not key:
        return False, "Chave Google AI não configurada."
    if len(key) < 20:
        return False, "Chave Google AI inválida (muito curta)."
    return True, "Chave Google AI configurada."


def obter_email_backup_nuvem() -> str:
    global CLOUD_BACKUP_EMAIL
    if CLOUD_BACKUP_EMAIL:
        return CLOUD_BACKUP_EMAIL

    cfg = _ler_cfg()
    CLOUD_BACKUP_EMAIL = cfg.get('cloud_backup', 'email_cliente', fallback='').strip()
    return CLOUD_BACKUP_EMAIL


def salvar_email_backup_nuvem(email: str) -> tuple[bool, str]:
    global CLOUD_BACKUP_EMAIL, _CFG
    email = str(email or "").strip().lower()
    if not validar_email_basico(email):
        return False, "E-mail invÃ¡lido para backup na nuvem."

    cfg_path = os.path.join(DIRETORIO_ATUAL, 'config.cfg')
    cfg = _ler_cfg()
    if not cfg.has_section('cloud_backup'):
        cfg.add_section('cloud_backup')
    cfg.set('cloud_backup', 'email_cliente', email)

    with open(cfg_path, 'w', encoding='utf-8') as f:
        cfg.write(f)

    CLOUD_BACKUP_EMAIL = email
    _CFG = cfg
    return True, "E-mail de backup em nuvem salvo com sucesso."


def obter_config_backup_nuvem() -> dict:
    cfg = _ler_cfg()
    drive_webhook_env = str(os.environ.get("GOOGLE_DRIVE_SYNC_WEBHOOK_URL", "") or "").strip()
    drive_latest_env = str(os.environ.get("GOOGLE_DRIVE_SYNC_LATEST_URL", "") or "").strip()
    drive_key_env = str(os.environ.get("GOOGLE_DRIVE_SYNC_API_KEY", "") or "").strip()
    drive_webhook_cfg = cfg.get('cloud_backup', 'drive_webhook_url', fallback=cfg.get('ia_diagramas', 'drive_webhook_url', fallback='')).strip()
    drive_latest_cfg = cfg.get('cloud_backup', 'drive_latest_url', fallback='').strip()
    return {
        "email": cfg.get('cloud_backup', 'email_cliente', fallback='').strip().lower(),
        "habilitado": cfg.getboolean('cloud_backup', 'habilitado', fallback=True),
        "api_key": drive_key_env or cfg.get('cloud_backup', 'api_key', fallback='').strip() or obter_google_ai_key_mestre(),
        "auto_sync": cfg.getboolean('cloud_backup', 'auto_sync', fallback=True),
        "sync_interval_seg": max(20, cfg.getint('cloud_backup', 'sync_interval_seg', fallback=60)),
        "drive_webhook_url": drive_webhook_env or drive_webhook_cfg,
        "drive_latest_url": drive_latest_env or drive_latest_cfg,
    }


def _enviar_backup_via_drive_webhook(
    email_cliente: str,
    conteudo: bytes,
    nome_backup: str,
    api_key: str,
    origem: str,
) -> tuple[bool, str]:
    cfg = obter_config_backup_nuvem()
    webhook = str(cfg.get("drive_webhook_url") or "").strip()
    if not webhook:
        return False, "Webhook Google Drive nÃ£o configurado."
    if not api_key:
        return False, "API key do hub Google Drive nÃ£o configurada."

    try:
        import urllib.request

        payload = {
            "acao": "cloud_backup_upload",
            "email_cliente": str(email_cliente or "").strip().lower(),
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": origem,
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-OFP-Cloud-Key": api_key,
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore") or "{}")

        arquivo = str(data.get("arquivo") or data.get("arquivo_nome") or nome_backup)
        return True, f"Backup em nuvem criado com sucesso: {arquivo}"
    except Exception as e:
        return False, f"Falha ao enviar backup para webhook Google Drive: {e}"


def _obter_token_admin_servidor(usuario_admin: str, senha_admin: str) -> tuple[bool, str, str]:
    try:
        import urllib.request
        import urllib.error
        import urllib.parse

        base_url = _resolver_servidor_rede_url(timeout_seg=3.0)
        url_token = f"{base_url.rstrip('/')}/api/token"
        body = urllib.parse.urlencode(
            {
                "username": usuario_admin,
                "password": senha_admin,
                "grant_type": "password",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            url_token,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        role = str(data.get("role", "")).upper()
        token = str(data.get("access_token", "")).strip()
        if role != "ADMIN" or not token:
            return False, "Acesso negado: autenticaÃ§Ã£o ADMIN nÃ£o confirmada no servidor.", ""
        return True, "Token ADMIN vÃ¡lido.", token
    except urllib.error.URLError as e:
        motivo = str(getattr(e, "reason", e))
        motivo_lower = motivo.lower()
        if "10061" in motivo or "connection refused" in motivo_lower or "conex" in motivo_lower and "recus" in motivo_lower:
            return (
                False,
                "Servidor de nuvem indisponÃ­vel no momento (conexÃ£o recusada). "
                "Inicie o servidor local e confira a URL em config.cfg (app.servidor_url).",
                "",
            )
        return False, f"Falha de conexÃ£o com o servidor: {motivo}", ""
    except Exception as e:
        return False, f"Falha de autenticaÃ§Ã£o no servidor: {e}", ""


def enviar_backup_nuvem(email_cliente: str, usuario_admin: str, senha_admin: str) -> tuple[bool, str]:
    """Envia cÃ³pia do banco para nuvem do cliente via API (somente ADMIN)."""
    ok_drive, msg_drive = garantir_banco_no_drive_usuario()
    if ok_drive:
        return True, msg_drive

    email = str(email_cliente or "").strip().lower()
    if not validar_email_basico(email):
        return False, "E-mail de nuvem invÃ¡lido."

    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco de dados nÃ£o encontrado para backup."

    try:
        with open(CAMINHO_BANCO, "rb") as f:
            conteudo_drive = f.read()
        nome_backup_drive = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        cfg_drive = obter_config_backup_nuvem()
        if cfg_drive.get("drive_webhook_url"):
            ok_drive, msg_drive = _enviar_backup_via_drive_webhook(
                email,
                conteudo_drive,
                nome_backup_drive,
                str(cfg_drive.get("api_key") or "").strip(),
                origem="desktop_admin",
            )
            if ok_drive:
                return ok_drive, msg_drive
    except Exception:
        pass

    ok_token, msg_token, token = _obter_token_admin_servidor(usuario_admin, senha_admin)
    if not ok_token:
        return False, msg_token

    try:
        import urllib.request

        with open(CAMINHO_BANCO, "rb") as f:
            conteudo = f.read()

        nome_backup = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        payload = {
            "email_cliente": email,
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": "desktop_admin",
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        base_url = _resolver_servidor_rede_url(timeout_seg=3.0)
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/cloud-backup",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        arquivo = str(data.get("arquivo", nome_backup))
        return True, f"Backup em nuvem criado com sucesso: {arquivo}"
    except Exception as e:
        return False, f"Falha ao enviar backup para nuvem: {e}"

def sincronizar_dados_da_nuvem(usuario_admin: str, senha_admin: str) -> tuple[bool, str]:
    """Baixa o banco mais recente do Google Drive (via OAuth2) e atualiza o arquivo local."""
    import io
    import shutil as _shutil

    # ── Verifica bibliotecas ──────────────────────────────────────────────────
    if google_build is None or MediaIoBaseDownload is None:
        return False, (
            "Biblioteca google-api-python-client não instalada.\n"
            "Execute: pip install google-api-python-client"
        )

    # ── Obtém credenciais salvas (não-interativo) ─────────────────────────────
    creds, msg_creds = _obter_credenciais_google_drive_usuario(interativo=False)
    if creds is None:
        return False, (
            msg_creds
            or "Você ainda não está conectado ao Google Drive.\n"
               "Use o botão 'Entrar no Google Drive' em Dados da Oficina para autenticar."
        )

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)

        # Localiza pasta "Oficina de Pesca - Dados"
        folder_query = (
            "mimeType='application/vnd.google-apps.folder' "
            "and name='Oficina de Pesca - Dados' "
            "and trashed=false"
        )
        folders = (
            service.files()
            .list(q=folder_query, fields="files(id,name)", pageSize=1)
            .execute()
            .get("files", [])
        )
        if not folders:
            return False, (
                "Pasta 'Oficina de Pesca - Dados' não encontrada no Google Drive.\n"
                "Faça um backup primeiro usando 'Entrar no Google Drive'."
            )

        folder_id = str(folders[0]["id"])

        # Busca arquivos .db na pasta, ordenados pelo mais recente
        file_query = (
            f"(name='oficina.db' or name contains '.db') "
            f"and trashed=false "
            f"and '{folder_id}' in parents"
        )
        files = (
            service.files()
            .list(
                q=file_query,
                fields="files(id,name,modifiedTime)",
                orderBy="modifiedTime desc",
                pageSize=10,
            )
            .execute()
            .get("files", [])
        )
        if not files:
            return False, (
                "Nenhum arquivo de banco de dados (.db) encontrado na pasta "
                "'Oficina de Pesca - Dados' do Google Drive."
            )

        file_meta = files[0]
        file_id = str(file_meta["id"])
        file_name = str(file_meta.get("name", "oficina.db"))

        # Faz o download
        req = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, req)
        done = False
        while not done:
            _status, done = downloader.next_chunk()

        conteudo = buffer.getvalue()
        if not conteudo:
            return False, "Arquivo baixado do Drive está vazio."

        # Salva backup do banco atual antes de substituir
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        pasta_backup = os.path.join(os.path.dirname(CAMINHO_BANCO), "backup_db")
        os.makedirs(pasta_backup, exist_ok=True)
        backup_local_pre = os.path.join(pasta_backup, f"pre_sync_{carimbo}.db")
        if os.path.exists(CAMINHO_BANCO):
            _shutil.copy2(CAMINHO_BANCO, backup_local_pre)

        with open(CAMINHO_BANCO, "wb") as f:
            f.write(conteudo)

        return True, (
            f"Sincronização concluída!\n"
            f"Arquivo '{file_name}' baixado do Google Drive.\n"
            f"Backup anterior salvo em backup_db/pre_sync_{carimbo}.db"
        )

    except Exception as e:
        _log = get_logger("cloud-sync")
        _log.warning("Falha ao sincronizar via Google Drive API: %s", e)
        return False, f"Falha ao sincronizar com o Google Drive: {e}"


def enviar_backup_nuvem_api_key(email_cliente: str, api_key: str, origem: str = "desktop_auto") -> tuple[bool, str]:
    """Envia cÃ³pia do banco para nuvem usando API key tÃ©cnica (instalaÃ§Ã£o Ãºnica)."""
    email = str(email_cliente or "").strip().lower()
    key = str(api_key or "").strip()
    if not validar_email_basico(email):
        return False, "E-mail de nuvem invÃ¡lido."
    if not key:
        return False, "API key de nuvem nÃ£o configurada."
    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco de dados nÃ£o encontrado para backup."

    try:
        with open(CAMINHO_BANCO, "rb") as f:
            conteudo_drive = f.read()
        nome_backup_drive = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        cfg_drive = obter_config_backup_nuvem()
        if cfg_drive.get("drive_webhook_url"):
            return _enviar_backup_via_drive_webhook(
                email,
                conteudo_drive,
                nome_backup_drive,
                key,
                origem=origem,
            )
    except Exception:
        pass

    try:
        import urllib.request

        with open(CAMINHO_BANCO, "rb") as f:
            conteudo = f.read()

        nome_backup = f"oficina_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        payload = {
            "email_cliente": email,
            "arquivo_nome": nome_backup,
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "origem": origem,
            "versao_app": APP_VERSION,
        }
        body = json.dumps(payload).encode("utf-8")
        base_url = _resolver_servidor_rede_url(timeout_seg=3.0)
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/cloud-backup",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-OFP-Cloud-Key": key,
                "User-Agent": f"OficinaPesca/{APP_VERSION}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        arquivo = str(data.get("arquivo", nome_backup))
        return True, f"Backup automÃ¡tico enviado para nuvem: {arquivo}"
    except Exception as e:
        return False, f"Falha no backup automÃ¡tico em nuvem: {e}"


def _obter_ou_salvar_id_arquivo_drive(service, folder_id: str, arquivo_nome: str = "oficina.db") -> str:
    """
    Recupera ou cria o arquivo no Drive e salva seu ID em config.cfg para sincronizacao híbrida.
    Isso garante que o APK do Android sempre consiga localizar o mesmo arquivo.
    """
    try:
        file_query = f"name='{arquivo_nome}' and trashed=false and '{folder_id}' in parents"
        arquivos = service.files().list(q=file_query, fields="files(id,name,webViewLink)", pageSize=1).execute().get("files", [])
        if arquivos:
            file_id = str(arquivos[0]["id"])
            # Salva o ID e o link para consulta posterior pelo APK
            cfg = obter_config_backup_nuvem()
            cfg["drive_banco_file_id"] = file_id
            cfg["drive_banco_link"] = str(arquivos[0].get("webViewLink", ""))
            return file_id
    except Exception as e:
        logger = get_logger("sync-hybrid")
        logger.warning("Falha ao recuperar ID do arquivo Drive: %s", e)
    return ""


def _verificar_versao_banco_drive(service, folder_id: str) -> tuple[float, bool]:
    """
    Retorna (timestamp_nuvem, existe_na_nuvem).
    Compara versão local vs nuvem para determinar qual é mais recente.
    """
    try:
        cfg = obter_config_backup_nuvem()
        file_id = cfg.get("drive_banco_file_id", "")
        if not file_id:
            return 0.0, False
        
        arquivo = service.files().get(fileId=file_id, fields="modifiedTime").execute()
        if arquivo:
            from datetime import datetime
            timestamp_str = arquivo.get("modifiedTime", "")
            # Parse ISO 8601
            dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            timestamp_nuvem = dt.timestamp()
            return timestamp_nuvem, True
    except Exception as e:
        logger = get_logger("sync-hybrid")
        logger.debug("Versao nuvem indisponivel: %s", e)
    return 0.0, False


def sincronizar_hibrido_banco_drive() -> tuple[bool, str]:
    """
    Sincronizacao híbrida com verificação de versão:
    - Se local é mais novo: faz upload
    - Se nuvem é mais nova: faz download  
    - Mantém ID do arquivo Drive persistente para o APK Android
    """
    if not os.path.exists(CAMINHO_BANCO):
        return False, "Banco local não encontrado."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, "Usuário não autenticado no Google Drive."

    if google_build is None or MediaFileUpload is None:
        return False, "Dependências Google Drive ausentes."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)

        # Garante pasta Oficina_Backup (nao a anterior 'Oficina de Pesca - Dados')
        folder_query = "mimeType='application/vnd.google-apps.folder' and name='Oficina_Backup' and trashed=false"
        folders = service.files().list(q=folder_query, fields="files(id,name)", pageSize=1).execute().get("files", [])
        if folders:
            folder_id = str(folders[0]["id"])
        else:
            pasta = service.files().create(
                body={"name": "Oficina_Backup", "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()
            folder_id = str(pasta["id"])

        # Recupera ou cria arquivo e salva ID
        file_id = _obter_ou_salvar_id_arquivo_drive(service, folder_id, "oficina.db")
        if not file_id:
            # Arquivo nao existe ainda, faz criacao inicial
            media = MediaFileUpload(CAMINHO_BANCO, mimetype="application/octet-stream", resumable=False)
            arquivo = service.files().create(
                body={"name": "oficina.db", "parents": [folder_id]},
                media_body=media,
                fields="id,webViewLink",
            ).execute()
            file_id = str(arquivo["id"])
            cfg = obter_config_backup_nuvem()
            cfg["drive_banco_file_id"] = file_id
            cfg["drive_banco_link"] = str(arquivo.get("webViewLink", ""))
            return True, "Banco criado no Google Drive (Oficina_Backup)."

        # Verifica versoes
        timestamp_nuvem, existe_na_nuvem = _verificar_versao_banco_drive(service, folder_id)
        timestamp_local = os.path.getmtime(CAMINHO_BANCO)

        if timestamp_local > timestamp_nuvem:
            # Local é mais recente: upload
            media = MediaFileUpload(CAMINHO_BANCO, mimetype="application/octet-stream", resumable=False)
            service.files().update(fileId=file_id, media_body=media).execute()
            try:
                publicar_evento_ponte_firebase_para_apk(
                    "desktop_drive_synced",
                    {
                        "db_mtime": int(timestamp_local),
                        "flow": "pc_to_apk",
                    },
                )
            except Exception:
                pass
            return True, "Banco sincronizado (upload para nuvem)."
        elif timestamp_nuvem > timestamp_local and existe_na_nuvem:
            # Nuvem é mais recente: download
            request = service.files().get_media(fileId=file_id)
            with open(CAMINHO_BANCO, "wb") as f:
                f.write(request.execute())
            try:
                # Após receber mudança (ex.: vinda do APK pela ponte), atualiza observabilidade no Firebase.
                publicar_evento_ponte_firebase_para_apk(
                    "desktop_applied_remote",
                    {
                        "db_mtime": int(os.path.getmtime(CAMINHO_BANCO)) if os.path.exists(CAMINHO_BANCO) else 0,
                        "flow": "apk_to_pc",
                    },
                )
            except Exception:
                pass
            return True, "Banco sincronizado (download da nuvem)."
        else:
            # Versoes iguais
            return True, "Banco já está sincronizado."
    except Exception as e:
        return False, f"Erro na sincronizacao híbrida: {e}"


def iniciar_sincronizacao_hibrida_nuvem() -> tuple[bool, str]:
    """
    Inicia background thread de sincronizacao híbrida com verificacao de versao.
    Só executada apos autenticacao manual do usuario via botao.
    """
    global _CLOUD_SYNC_THREAD, _CLOUD_SYNC_STARTED
    if _CLOUD_SYNC_STARTED and _CLOUD_SYNC_THREAD and _CLOUD_SYNC_THREAD.is_alive():
        return True, "Sincronizacao híbrida já está ativa."

    cfg = obter_config_backup_nuvem()
    if not cfg["habilitado"]:
        return False, "Backup em nuvem desabilitado no config.cfg."
    if not cfg["auto_sync"]:
        return False, "Sincronizacao automática desabilitada no config.cfg."

    creds, _msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, "Usuário não autenticado no Google Drive."

    intervalo = int(cfg["sync_interval_seg"])
    logger = get_logger("cloud-sync-hybrid")

    def _worker():
        while True:
            try:
                if os.path.exists(CAMINHO_BANCO):
                    ok, msg = sincronizar_hibrido_banco_drive()
                    if ok:
                        logger.info(msg)
                    else:
                        logger.warning(msg)
                time.sleep(intervalo)
            except Exception as e:
                logger.exception("Falha no loop de sincronizacao híbrida: %s", e)
                time.sleep(max(intervalo, 30))

    _CLOUD_SYNC_THREAD = threading.Thread(target=_worker, daemon=True, name="ofp-cloud-sync-hybrid")
    _CLOUD_SYNC_THREAD.start()
    _CLOUD_SYNC_STARTED = True
    return True, "Sincronizacao híbrida em background iniciada."


def iniciar_sincronizacao_automatica_nuvem() -> tuple[bool, str]:
    """Mantido para compatibilidade; chama sincronização híbrida."""
    return iniciar_sincronizacao_hibrida_nuvem()


def executar_atualizacao(
    url_download: str,
    app_executavel: str = "",
    processo_pid: Optional[int] = None,
    silenciosa: bool = True,
    progresso_cb=None,
    versao_alvo: str = "",
) -> tuple[bool, str]:
    """Baixa o instalador oficial e inicia a atualização em fluxo seguro no Windows."""
    alvo = str(versao_alvo or "").strip()
    base_log_update = os.path.dirname(ARQUIVO_ESTADO_UPDATE)
    os.makedirs(base_log_update, exist_ok=True)
    update_error_log = os.path.join(base_log_update, "update_error.log")

    def _registrar_erro_update(mensagem: str, exc: Exception | None = None) -> None:
        try:
            detalhe = str(mensagem or "").strip() or "Falha de atualização sem detalhe."
            if exc is not None:
                detalhe = f"{detalhe} | excecao={repr(exc)}"
            with open(update_error_log, "a", encoding="utf-8") as ferr:
                ferr.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {detalhe}\n")
        except Exception:
            pass

    if alvo == VERSAO_TRAVA_LOOP_UPDATE:
        _ok_reset, _msg_reset = _resetar_trava_update_para_versao_alvo(alvo)
        try:
            get_logger("update-download").info("[update] %s", _msg_reset)
        except Exception:
            pass

    if alvo != VERSAO_TRAVA_LOOP_UPDATE and bloqueio_loop_update_ativo(versao_alvo=alvo):
        return False, "Sistema atualizado"

    url = str(url_download or "").strip()
    if not url:
        _registrar_erro_update("URL de download não configurada para atualização.")
        return False, f"URL de download não configurada. Log: {update_error_log}"

    if not url.lower().startswith(("http://", "https://")):
        _registrar_erro_update(f"URL de download inválida: {url}")
        return False, f"URL de download inválida. Log: {update_error_log}"

    log_upd = get_logger("update-download")

    try:
        import urllib.parse

        base_tmp_root = os.path.join(tempfile.gettempdir(), "oficina_pesca_update")
        os.makedirs(base_tmp_root, exist_ok=True)

        ok_cache, msg_cache = limpar_cache_instalacao_update()
        if not ok_cache:
            log_upd.warning("[update] %s", msg_cache)
        else:
            log_upd.info("[update] %s", msg_cache)
        if callable(progresso_cb):
            try:
                progresso_cb(0.0, "Limpando cache de atualização...")
            except Exception:
                pass

        exec_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        base_tmp = os.path.join(base_tmp_root, f"run_{exec_id}")
        os.makedirs(base_tmp, exist_ok=True)

        # Falhas de permissão em TEMP eram causa recorrente de updater "piscar" e encerrar.
        for pasta_teste in (base_tmp_root, base_tmp):
            teste_perm = os.path.join(pasta_teste, ".perm_check.tmp")
            with open(teste_perm, "w", encoding="utf-8") as fperm:
                fperm.write("ok")
            os.remove(teste_perm)

        nome_url = os.path.basename(urllib.parse.urlsplit(url).path or "").strip()
        if not nome_url.lower().endswith(".exe"):
            nome_url = "Setup_OficinaPesca_update.exe"

        destino = os.path.join(base_tmp, nome_url)
        destino_part = destino + ".part"

        headers = {"User-Agent": f"OficinaPesca/{APP_VERSION}"}
        req = urllib.request.Request(url, headers=headers)

        log_upd.info("[update] Iniciando download de atualização: %s", url)
        if callable(progresso_cb):
            try:
                progresso_cb(0.0, "Iniciando download da atualização...")
            except Exception:
                pass
        with urllib.request.urlopen(req, timeout=45) as resp, open(destino_part, "wb") as out:
            final_url = str(getattr(resp, "geturl", lambda: url)() or url).strip()
            if alvo and "github.com" in final_url.lower() and f"/download/v{alvo}/" not in final_url.lower():
                detalhe = (
                    f"Release remota divergente da versão alvo. alvo={alvo} final_url={final_url} url_original={url}"
                )
                log_upd.error("[update] %s", detalhe)
                _registrar_erro_update(detalhe)
                return False, (
                    f"O servidor de atualização ainda está entregando outra release ({final_url}). "
                    f"Esperado: v{alvo}. Log: {update_error_log}"
                )
            content_length = int(resp.headers.get("Content-Length", "0") or "0")
            sha = hashlib.sha256()
            total = 0
            while True:
                chunk = resp.read(1024 * 128)
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                total += len(chunk)
                if callable(progresso_cb) and content_length > 0:
                    try:
                        progresso_cb(min(total / float(content_length), 1.0), f"Baixando atualização... {int((total / float(content_length)) * 100)}%")
                    except Exception:
                        pass

        if content_length > 0 and total != content_length:
            log_upd.error("[update] Download inconsistente: esperado=%s recebido=%s", content_length, total)
            _registrar_erro_update(
                f"Download inconsistente: esperado={content_length}, recebido={total}, url={url}"
            )
            return False, f"Falha de integridade no download (tamanho divergente). Log: {update_error_log}"

        if total < 1024 * 1024:
            log_upd.error("[update] Download inválido: tamanho muito pequeno (%s bytes)", total)
            _registrar_erro_update(f"Download inválido: tamanho insuficiente ({total} bytes), url={url}")
            return False, f"Falha de integridade no download (arquivo inválido). Log: {update_error_log}"

        with open(destino_part, "rb") as fchk:
            assinatura = fchk.read(2)
        if assinatura != b"MZ":
            log_upd.error("[update] Download inválido: assinatura PE ausente em %s", destino_part)
            _registrar_erro_update(f"Assinatura PE inválida para arquivo baixado: {destino_part}")
            return False, f"Falha de integridade no download (executável corrompido). Log: {update_error_log}"

        if os.path.exists(destino):
            try:
                os.remove(destino)
            except Exception as ex_remove:
                _registrar_erro_update(f"Falha ao substituir instalador existente em {destino}", ex_remove)
                return False, f"Falha ao substituir arquivo de atualização. Verifique permissões. Log: {update_error_log}"

        os.replace(destino_part, destino)
        hash_hex = sha.hexdigest()
        log_upd.info("[update] Download concluído com integridade: arquivo=%s bytes=%s sha256=%s", destino, total, hash_hex)
        if callable(progresso_cb):
            try:
                progresso_cb(1.0, "Download concluído. Iniciando instalador...")
            except Exception:
                pass

        meta = {
            "url": url,
            "arquivo": destino,
            "bytes": total,
            "sha256": hash_hex,
            "versao_local": APP_VERSION,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(os.path.join(base_tmp, "update_download_meta.json"), "w", encoding="utf-8") as fmeta:
            json.dump(meta, fmeta, ensure_ascii=False, indent=2)

        args = []
        app_exec = str(app_executavel or "").strip()
        app_exec_abs = os.path.abspath(app_exec) if app_exec else ""
        nomes_processo = []
        if app_exec_abs:
            nomes_processo.append(os.path.basename(app_exec_abs))
        nomes_processo.extend(["Oficina_Pesca.exe", "Oficina de Pesca.exe"])
        nomes_processo_unicos = []
        for nome_proc in nomes_processo:
            nome_proc = str(nome_proc or "").strip()
            if nome_proc and nome_proc.lower() not in {n.lower() for n in nomes_processo_unicos}:
                nomes_processo_unicos.append(nome_proc)
        nomes_processo_cmd = " ".join(f'\"{nome}\"' for nome in nomes_processo_unicos)
        dir_instalacao_alvo = ""
        if getattr(sys, "frozen", False) and app_exec_abs and os.path.exists(app_exec_abs):
            dir_instalacao_alvo = os.path.dirname(app_exec_abs)
        if silenciosa:
            args.extend([
                "/SP-",
                "/VERYSILENT",
                "/SUPPRESSMSGBOXES",
                "/NOCANCEL",
                "/CLOSEAPPLICATIONS",
                "/FORCECLOSEAPPLICATIONS",
                "/NORESTARTAPPLICATIONS",
            ])

        if dir_instalacao_alvo:
            args.append(f'/DIR="{dir_instalacao_alvo}"')
            log_upd.info("[update] Diretório-alvo forçado para instalação: %s", dir_instalacao_alvo)

        inno_log = os.path.join(base_tmp, "inno_update.log")
        args.append(f'/LOG="{inno_log}"')

        launcher_script = os.path.join(base_tmp, "run_update_forcado.cmd")
        launcher_err_log = update_error_log.replace("/", "\\")
        pid_txt = str(int(processo_pid)) if processo_pid else ""
        args_txt = " ".join(str(a) for a in args)
        script_lines = [
            "@echo off",
            "setlocal EnableExtensions",
            f'set "INSTALLER={destino}"',
            f'set "APP_EXEC={app_exec}"',
            f'set "PARENT_PID={pid_txt}"',
            f'set "UPDATE_ERR_LOG={launcher_err_log}"',
            f'set "INNO_LOG={inno_log}"',
            f'set "PROCESS_NAMES={nomes_processo_cmd}"',
            'if not exist "%INSTALLER%" (',
            '  echo [%date% %time%] Instalador não encontrado: %INSTALLER%>>"%UPDATE_ERR_LOG%"',
            '  echo ERRO: Instalador não encontrado: %INSTALLER%',
            '  echo Consulte o log: %UPDATE_ERR_LOG%',
            '  pause',
            '  exit /b 2',
            ')',
        ]
        if pid_txt:
            script_lines.extend(
                [
                    'taskkill /PID %PARENT_PID% /T /F >nul 2>nul',
                    'for /l %%I in (1,1,25) do (',
                    '  tasklist /FI "PID eq %PARENT_PID%" | find "%PARENT_PID%" >nul',
                    '  if errorlevel 1 goto :pid_encerrado',
                    '  ping 127.0.0.1 -n 2 >nul',
                    ')',
                    ':pid_encerrado',
                ]
            )
        script_lines.extend(
            [
                'for %%P in (%PROCESS_NAMES%) do (',
                '  taskkill /IM %%~P /T /F >nul 2>nul',
                ')',
                'for /l %%I in (1,1,8) do (',
                '  set "LOCK_FOUND=0"',
                '  for %%P in (%PROCESS_NAMES%) do (',
                '    tasklist /FI "IMAGENAME eq %%~P" | find /I "%%~P" >nul && set "LOCK_FOUND=1"',
                '  )',
                '  if "%LOCK_FOUND%"=="0" goto :processos_encerrados',
                '  ping 127.0.0.1 -n 2 >nul',
                ')',
                ':processos_encerrados',
                'for %%P in (%PROCESS_NAMES%) do (',
                '  tasklist /FI "IMAGENAME eq %%~P" | find /I "%%~P" >nul && echo [%date% %time%] Processo remanescente detectado antes do instalador: %%~P>>"%UPDATE_ERR_LOG%"',
                ')',
            ]
        )
        script_lines.extend(
            [
                f"start \"\" /wait \"{destino}\" {args_txt}".rstrip(),
                "set \"UPD_EXIT=%ERRORLEVEL%\"",
                'if not "%UPD_EXIT%"=="0" (',
                '  echo [%date% %time%] Falha na execução do instalador. exit=%UPD_EXIT% arquivo=%INSTALLER%>>"%UPDATE_ERR_LOG%"',
                '  if exist "%INNO_LOG%" echo [%date% %time%] Consulte também: %INNO_LOG%>>"%UPDATE_ERR_LOG%"',
                '  echo.',
                '  echo ERRO: Atualização falhou (exit=%UPD_EXIT%).',
                '  echo Log de diagnostico: %UPDATE_ERR_LOG%',
                '  if exist "%INNO_LOG%" echo Log do instalador: %INNO_LOG%',
                '  pause',
                ')',
                'if not "%APP_EXEC%"=="" if exist "%APP_EXEC%" start "" "%APP_EXEC%"',
                "exit /b %UPD_EXIT%",
            ]
        )
        with open(launcher_script, "w", encoding="utf-8") as fscript:
            fscript.write("\r\n".join(script_lines) + "\r\n")

        creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["cmd", "/c", launcher_script],
            cwd=base_tmp,
            creationflags=creationflags,
        )

        registrar_update_aplicado_local(
            versao_alvo or APP_VERSION,
            origem="download",
            status="instalador_iniciado",
        )

        log_upd.info("[update] Instalador iniciado em processo desacoplado: %s", destino)
        return True, "Atualização iniciada com sucesso."
    except Exception as e:
        _registrar_erro_update("Falha ao executar atualização (exceção de runtime).", e)
        log_upd.exception("[update] Falha ao executar atualização: %s", e)
        registrar_update_aplicado_local(
            versao_alvo or APP_VERSION,
            origem="erro",
            status="travado",
        )
        if callable(progresso_cb):
            try:
                progresso_cb(0.0, f"Falha na atualização: {e}")
            except Exception:
                pass
        return False, f"Falha na atualização: {e}. Log: {update_error_log}"


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Gera um hash seguro para senha usando PBKDF2-SHA256 e salt."""
    if salt is None:
        salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return f"pbkdf2_sha256${binascii.hexlify(salt).decode()}${binascii.hexlify(digest).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verifica senha contra hash PBKDF2 ou SHA-256 antigo."""
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, salt_hex, digest_hex = stored_hash.split("$")
            salt = binascii.unhexlify(salt_hex)
            return hash_password(password, salt) == stored_hash
        except Exception:
            return False
    return hashlib.sha256(password.encode('utf-8')).hexdigest() == stored_hash


def validate_password(password: str) -> tuple[bool, str]:
    password = password.strip()
    if len(password) < 8:
        return False, "A senha deve ter pelo menos 8 caracteres."
    if not any(ch.isupper() for ch in password):
        return False, "Use ao menos uma letra maiÃºscula."
    if not any(ch.islower() for ch in password):
        return False, "Use ao menos uma letra minÃºscula."
    if not any(ch.isdigit() for ch in password):
        return False, "Use ao menos um nÃºmero."
    if not any(ch in "!@#$%&*()-_=+[]{};:,.<>?/~^" for ch in password):
        return False, "Use ao menos um caractere especial."
    return True, ""


def inicializar_banco():
    # --- VERIFICAÇÃO DE INTEGRIDADE (RESGATE DE BANCO CORROMPIDO) ---
    if os.path.exists(CAMINHO_BANCO):
        try:
            # Tenta uma conexão rápida e executa o check de integridade
            with sqlite3.connect(CAMINHO_BANCO, timeout=2) as conn_test:
                cursor_test = conn_test.cursor()
                cursor_test.execute("PRAGMA integrity_check")
                res = cursor_test.fetchone()
                if not res or res[0] != "ok":
                    raise sqlite3.DatabaseError("Database is malformed")
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            logger_repair = get_logger("db_repair")
            logger_repair.error("Detectada corrupção no banco de dados em %s. Iniciando resgate.", CAMINHO_BANCO)
            
            # Renomeia o arquivo atual para backup conforme solicitado
            diretorio_base = os.path.dirname(CAMINHO_BANCO)
            caminho_corrompido = os.path.join(diretorio_base, 'oficina_corrompido.db')
            
            try:
                if os.path.exists(caminho_corrompido):
                    os.remove(caminho_corrompido) # Remove backup anterior para permitir a renomeação
                os.rename(CAMINHO_BANCO, caminho_corrompido)
                logger_repair.info(f"Sucesso: Arquivo corrompido isolado em {caminho_corrompido}")
            except Exception as e:
                logger_repair.exception(f"Falha crítica ao renomear arquivo corrompido: {e}")

    try:
        ok_restore, msg_restore = _restaurar_banco_por_backup_se_necessario()
        if ok_restore:
            get_logger("db").info(msg_restore)
    except Exception as e:
        get_logger("db").warning("Falha na restauraÃ§Ã£o automÃ¡tica do banco: %s", e)

    os.makedirs(os.path.dirname(CAMINHO_BANCO), exist_ok=True)
    conn = sqlite3.connect(CAMINHO_BANCO)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE,
            senha TEXT,
            role TEXT DEFAULT 'VENDEDOR'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            telefone TEXT,
            email TEXT,
            cpf_cnpj TEXT,
            cep TEXT,
            rua TEXT,
            numero TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            data_cadastro TEXT
        )
    """)

    cursor.execute("PRAGMA table_info(clientes)")
    colunas_clientes = [row[1] for row in cursor.fetchall()]
    if 'cpf_cnpj' not in colunas_clientes:
        cursor.execute("ALTER TABLE clientes ADD COLUMN cpf_cnpj TEXT")
    if 'cpf_cnpj_normalizado' not in colunas_clientes:
        cursor.execute("ALTER TABLE clientes ADD COLUMN cpf_cnpj_normalizado TEXT")

    # Backfill do identificador normalizado para registros antigos.
    cursor.execute(
        """
        UPDATE clientes
        SET cpf_cnpj_normalizado = UPPER(
            REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(cpf_cnpj,''), '.', ''), '-', ''), '/', ''), ' ', ''), '(', ''), ')', '')
        )
        WHERE COALESCE(cpf_cnpj,'') <> ''
          AND (cpf_cnpj_normalizado IS NULL OR cpf_cnpj_normalizado = '')
        """
    )

    cursor.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_cpf_cnpj_unico
        ON clientes(cpf_cnpj_normalizado)
        WHERE cpf_cnpj_normalizado IS NOT NULL AND cpf_cnpj_normalizado <> ''
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            preco_custo REAL DEFAULT 0,
            preco_venda REAL DEFAULT 0,
            estoque INTEGER DEFAULT 0,
            compatibilidade TEXT,
            quantidade_minima INTEGER DEFAULT 3
        )
    """)

    cursor.execute("PRAGMA table_info(produtos)")
    colunas_produtos = [row[1] for row in cursor.fetchall()]
    if 'compatibilidade' not in colunas_produtos:
        cursor.execute("ALTER TABLE produtos ADD COLUMN compatibilidade TEXT")
    if 'quantidade_minima' not in colunas_produtos:
        cursor.execute("ALTER TABLE produtos ADD COLUMN quantidade_minima INTEGER DEFAULT 3")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ordens_servico (
            id_os INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            equipamento TEXT,
            modelo TEXT,
            defeito TEXT,
            valor_pecas REAL,
            valor_obra REAL,
            valor_total REAL,
            entrada REAL,
            restante REAL,
            status TEXT,
            data_abertura TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor INTEGER
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('ultimo_orcamento', 500)")
    cursor.execute(
        "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
        (date.today().toordinal(),)
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orcamentos_aguardo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente TEXT,
            equipamento TEXT,
            defeito TEXT,
            valor_total REAL,
            sinal REAL,
            saldo REAL,
            status TEXT,
            data TEXT,
            itens_detalhes TEXT,
            dados_adicionais TEXT,
            status_entrega TEXT,
            data_finalizacao TEXT,
            data_entrega TEXT
        )
    """)

    # Garantir migraÃ§Ã£o do schema existente para adicionar dados_adicionais
    cursor.execute("PRAGMA table_info(orcamentos_aguardo)")
    colunas = [row[1] for row in cursor.fetchall()]
    if 'dados_adicionais' not in colunas:
        cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN dados_adicionais TEXT")
    if 'status_entrega' not in colunas:
        cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN status_entrega TEXT")
    if 'data_finalizacao' not in colunas:
        cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_finalizacao TEXT")
    if 'data_entrega' not in colunas:
        cursor.execute("ALTER TABLE orcamentos_aguardo ADD COLUMN data_entrega TEXT")

    cursor.execute(
        """
        UPDATE orcamentos_aguardo
        SET status_entrega = COALESCE(NULLIF(status_entrega, ''), 'PENDENTE'),
            data_finalizacao = COALESCE(NULLIF(data_finalizacao, ''), 'Vazio'),
            data_entrega = COALESCE(NULLIF(data_entrega, ''), 'Vazio')
        WHERE status_entrega IS NULL OR status_entrega = ''
           OR data_finalizacao IS NULL OR data_finalizacao = ''
           OR data_entrega IS NULL OR data_entrega = ''
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fluxo_caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            descricao TEXT,
            tipo TEXT,
            valor REAL,
            categoria TEXT,
            metodo_pagamento TEXT
        )
    """)

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS fila_sync_firebase (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            origem TEXT,
            acao TEXT,
            payload_json TEXT,
            recebido_em TEXT,
            processado INTEGER DEFAULT 0
        )
        """
    )

    cursor.execute("PRAGMA table_info(fluxo_caixa)")
    colunas_fluxo = [row[1] for row in cursor.fetchall()]
    if 'categoria' not in colunas_fluxo:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN categoria TEXT")

    from reforma_tributaria import garantir_estrutura_reforma_tributaria
    garantir_estrutura_reforma_tributaria(cursor)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dados_oficina (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            nome_oficina TEXT,
            cnpj_oficina TEXT,
            endereco_oficina TEXT,
            telefone_oficina TEXT,
            chave_pix TEXT,
            logo_path TEXT,
            logo_patrocinador_path TEXT
        )
    """)
    cursor.execute("PRAGMA table_info(dados_oficina)")
    colunas_oficina = [row[1] for row in cursor.fetchall()]
    if 'logo_patrocinador_path' not in colunas_oficina:
        cursor.execute("ALTER TABLE dados_oficina ADD COLUMN logo_patrocinador_path TEXT")
    if 'cnpj_oficina' not in colunas_oficina:
        cursor.execute("ALTER TABLE dados_oficina ADD COLUMN cnpj_oficina TEXT")
    cursor.execute(
        """
        INSERT OR IGNORE INTO dados_oficina
            (id, nome_oficina, cnpj_oficina, endereco_oficina, telefone_oficina, chave_pix, logo_path, logo_patrocinador_path)
        VALUES
            (1, '', '', '', '', '', '', '')
        """
    )

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_servicos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_nome TEXT,
            data_servico TEXT,
            equipamento TEXT,
            defeito_relatado TEXT,
            servicos_detalhados TEXT,
            valor_total REAL
        )
    """)

    conn.commit()
    conn.close()


def existe_algum_usuario() -> bool:
    """Indica se jÃ¡ existe ao menos um usuário cadastrado."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM usuarios")
        return int(cursor.fetchone()[0] or 0) > 0


def dados_oficina_sao_padrao() -> bool:
    """Retorna True se os dados da oficina ainda nÃ£o foram configurados."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT nome_oficina FROM dados_oficina WHERE id = 1")
            row = cursor.fetchone()
            if not row or not (row[0] or "").strip():
                return True
    except Exception:
        pass
    return False


def obter_chave_pix_oficina() -> str:
    """Retorna a chave PIX cadastrada nos dados da oficina."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT chave_pix FROM dados_oficina WHERE id = 1")
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _assinar_payload(payload_b64: str) -> str:
    assinatura = hmac.new(
        LICENCA_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return assinatura[:20].upper()


def obter_hardware_id() -> str:
    """Retorna identificador estável da máquina para proteção da licença.

    Implementação portátil: não usa Registro do Windows nem grava ID em AppData.
    Gera um identificador determinístico em memória com dados locais disponíveis.
    """
    _partes: list[str] = []
    try:
        _partes.append(str(uuid.getnode()))
    except Exception:
        pass
    try:
        _partes.append(platform.node())
    except Exception:
        pass
    _base = "|".join([p for p in _partes if p]) or str(uuid.uuid4())
    return hashlib.sha256(_base.encode("utf-8")).hexdigest().upper()


def _caminhos_licenca_externa() -> list[str]:
    base = DIRETORIO_ATUAL
    return [
        os.path.join(base, "licenca.key"),
        os.path.join(base, "licenca.json"),
        os.path.join(base, "licencas.json"),
    ]


def _extrair_licenca_de_arquivo() -> tuple[str, str, str, str]:
    """Lê licença externa da raiz da instalação.

    Retorna (chave, cliente, validade, erro).
    """
    candidatos = _caminhos_licenca_externa()
    existente = ""
    for caminho in candidatos:
        if os.path.exists(caminho):
            existente = caminho
            break

    if not existente:
        ok_drive, chave_drive, erro_drive = obter_chave_licenca_drive()
        if ok_drive:
            return chave_drive, "", "", ""
        return "", "", "", f"Arquivo de licença ausente na raiz (licenca.key/licenca.json/licencas.json) e no Drive ({erro_drive})."

    try:
        if existente.lower().endswith(".key"):
            with open(existente, "r", encoding="utf-8") as f:
                chave = _normalizar_texto_chave_licenca(f.read())
            if not chave:
                return "", "", "", "Arquivo licenca.key vazio."
            return chave, "", "", ""

        with open(existente, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return "", "", "", "Arquivo JSON de licença inválido."

        chave = _normalizar_texto_chave_licenca(
            data.get("chave")
            or data.get("licenca")
            or data.get("license_key")
            or ""
        )
        cliente = str(data.get("cliente") or data.get("nome") or "").strip()
        validade = str(data.get("validade") or "").strip()

        if not chave:
            return "", "", "", "Arquivo JSON sem campo de chave de licença."
        return chave, cliente, validade, ""
    except Exception as e:
        return "", "", "", f"Falha ao ler arquivo de licença: {e}"


def obter_chave_instalacao() -> str:
    """Chave curta enviada pelo cliente ao administrador para emissão da licença."""
    hw = obter_hardware_id()
    return f"OFP-INST-{hw[:24]}"


def normalizar_chave_instalacao(chave_instalacao: str) -> str:
    chave = str(chave_instalacao or "").strip().upper()
    if not chave:
        return ""

    if re.fullmatch(r"OFP-INST-[A-F0-9]{24}", chave):
        return chave

    if re.fullmatch(r"[A-F0-9]{24}", chave):
        return f"OFP-INST-{chave}"

    return chave


def _normalizar_texto_chave_licenca(chave: str) -> str:
    """Remove espacos/quebras acidentais de copia e cola da chave."""
    return "".join(str(chave or "").split()).strip()


def _normalizar_hw_para_assinatura(chave_instalacao: str) -> str:
    """Padroniza a chave OFP-INST para uso consistente em assinatura/validacao."""
    return normalizar_chave_instalacao(chave_instalacao).strip().upper()


TIPOS_LICENCA_DIAS = {
    "PROMOCIONAL": 90,
    "MENSAL": 30,
    "TRIMESTRAL": 90,
    "SEMESTRAL": 180,
    "ANUAL": 365,
    "PERMANENTE": None,
}


def _inferir_tipo_por_validade(validade: str) -> str:
    validade = str(validade or "").strip().upper()
    if validade == "PERMANENTE":
        return "PERMANENTE"

    try:
        data_validade = date.fromisoformat(validade)
        dias = max((data_validade - date.today()).days, 0)
    except Exception:
        return "MENSAL"

    if dias >= 365:
        return "ANUAL"
    if dias >= 180:
        return "SEMESTRAL"
    if dias >= 90:
        return "TRIMESTRAL"
    return "MENSAL"


def _normalizar_tipo_licenca(tipo: str, validade: str = "") -> str:
    tipo = str(tipo or "").upper().strip()
    if tipo in TIPOS_LICENCA_DIAS:
        return tipo
    return _inferir_tipo_por_validade(validade)


def gerar_chave_licenca(
    cliente: str,
    dias_validade: Optional[int] = None,
    tipo_licenca: str = "",
    chave_instalacao: str = "",
) -> str:
    # cliente mantido apenas por compatibilidade da assinatura.
    _ = cliente
    tipo_in = str(tipo_licenca or "").upper().strip()

    if tipo_in == "PERMANENTE":
        dias_validade = None
    elif tipo_in in TIPOS_LICENCA_DIAS and (dias_validade is None or dias_validade <= 0):
        dias_validade = TIPOS_LICENCA_DIAS[tipo_in]

    if dias_validade is not None and dias_validade > 0:
        validade = date.fromordinal(date.today().toordinal() + dias_validade).isoformat()
    else:
        validade = "PERMANENTE"

    hw = _normalizar_hw_para_assinatura(chave_instalacao) or _normalizar_hw_para_assinatura(obter_chave_instalacao())

    payload = {
        "val": validade,
        "hw": hw,
        "ver": 2,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")
    assinatura = _assinar_payload(payload_b64)
    return f"OFP-{payload_b64}-{assinatura}"


def validar_chave_licenca(chave: str):
    chave = _normalizar_texto_chave_licenca(chave)
    if not chave.startswith("OFP-"):
        return False, "Formato de chave invalido.", None

    try:
        _, payload_b64, assinatura = chave.split("-", 2)
    except ValueError:
        return False, "Chave incompleta.", None

    assinatura_recebida = str(assinatura or "").strip().upper()
    assinatura_ok = _assinar_payload(payload_b64)
    if not hmac.compare_digest(assinatura_ok, assinatura_recebida):
        return False, "Assinatura da chave invalida.", None

    try:
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode((payload_b64 + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return False, "Conteudo da chave invalido.", None

    validade = str(payload.get("val", "PERMANENTE"))
    chave_hw = _normalizar_hw_para_assinatura(payload.get("hw", ""))
    chave_local = _normalizar_hw_para_assinatura(obter_chave_instalacao())
    if not chave_hw.startswith("OFP-INST-"):
        return False, "Chave de instalação da licença inválida (prefixo OFP-INST ausente).", payload
    if not chave_hw or chave_hw != chave_local:
        return False, "Licença não pertence a este computador (Hardware ID divergente).", payload

    tipo = _normalizar_tipo_licenca("", validade)
    payload["tipo"] = tipo

    if validade != "PERMANENTE":
        try:
            data_validade = date.fromisoformat(validade)
        except ValueError:
            return False, "Data de validade invalida na chave.", None
        if date.today() > data_validade:
            return False, f"Licenca expirada em {data_validade.strftime('%d/%m/%Y')}.", payload

    return True, "Licenca valida.", payload


def _assinar_payload_token(payload_b64: str) -> str:
    assinatura = hmac.new(
        LICENCA_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return assinatura[:20].upper()


def gerar_token_acesso(user_id: str, dias_validade: int = TOKEN_VALIDADE_DIAS) -> str:
    uid = str(user_id or "").strip().lower()
    if not uid:
        raise ValueError("user_id do token não pode estar vazio.")

    dias = max(1, int(dias_validade or TOKEN_VALIDADE_DIAS))
    hoje = date.today()
    exp = (hoje + timedelta(days=dias)).isoformat()
    payload = {
        "uid": uid,
        "exp": exp,
        "iat": hoje.isoformat(),
        "ver": 1,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("ascii").rstrip("=")
    assinatura = _assinar_payload_token(payload_b64)
    return f"OFP-TKN-{payload_b64}-{assinatura}"


def validar_token_acesso(token: str, user_id_esperado: str = "") -> tuple[bool, str, Optional[dict]]:
    token_limpo = "".join(str(token or "").split()).strip()
    if not token_limpo:
        return False, "Token vazio.", None

    if not token_limpo.startswith("OFP-TKN-"):
        return False, "Formato de token inválido.", None

    try:
        _p1, _p2, payload_b64, assinatura = token_limpo.split("-", 3)
    except ValueError:
        return False, "Token incompleto.", None

    assinatura_recebida = str(assinatura or "").strip().upper()
    assinatura_ok = _assinar_payload_token(payload_b64)
    if not hmac.compare_digest(assinatura_ok, assinatura_recebida):
        return False, "Assinatura de token inválida.", None

    try:
        padding = "=" * ((4 - len(payload_b64) % 4) % 4)
        payload_json = base64.urlsafe_b64decode((payload_b64 + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(payload_json)
    except Exception:
        return False, "Conteúdo do token inválido.", None

    if not isinstance(payload, dict):
        return False, "Payload do token inválido.", None

    uid = str(payload.get("uid") or "").strip().lower()
    if not uid:
        return False, "Token sem uid.", payload

    esperado = str(user_id_esperado or "").strip().lower()
    if esperado and uid != esperado:
        return False, "Token não pertence ao usuário esperado.", payload

    exp = str(payload.get("exp") or "").strip()
    if not exp:
        return False, "Token sem validade.", payload
    try:
        data_exp = date.fromisoformat(exp)
    except Exception:
        return False, "Data de validade do token inválida.", payload

    if date.today() > data_exp:
        return False, f"Token expirado em {data_exp.strftime('%d/%m/%Y')}.", payload

    return True, "Token válido.", payload


def obter_user_id_token_padrao() -> str:
    email_cfg = str(obter_email_backup_nuvem() or "").strip().lower()
    if validar_email_basico(email_cfg):
        return email_cfg

    try:
        creds, _msg = _obter_credenciais_google_drive_usuario(interativo=False)
        if creds and google_build is not None:
            service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
            about = service.about().get(fields="user(emailAddress)").execute()
            user = about.get("user", {}) if isinstance(about, dict) else {}
            email = str(user.get("emailAddress") or "").strip().lower()
            if validar_email_basico(email):
                return email
    except Exception:
        pass

    return "ofp-user"


def _obter_ou_criar_pasta_drive_usuario(service, nome_pasta: str) -> str:
    nome = str(nome_pasta or "").strip() or GOOGLE_DRIVE_PASTA_TOKEN
    nome_esc = nome.replace("'", "\\'")
    q = (
        "mimeType='application/vnd.google-apps.folder' and "
        f"name='{nome_esc}' and trashed=false"
    )
    pastas = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])
    if pastas:
        return str(pastas[0]["id"])

    pasta = service.files().create(
        body={"name": nome, "mimeType": "application/vnd.google-apps.folder"},
        fields="id",
    ).execute()
    return str(pasta["id"])


def _upsert_arquivo_texto_drive(service, folder_id: str, nome_arquivo: str, conteudo: str) -> tuple[bool, str]:
    if MediaFileUpload is None:
        return False, "Dependência Google Drive ausente para upload do token."

    nome = str(nome_arquivo or TOKEN_ARQUIVO_NOME).strip() or TOKEN_ARQUIVO_NOME
    nome_esc = nome.replace("'", "\\'")
    q = f"name='{nome_esc}' and trashed=false and '{folder_id}' in parents"
    existentes = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".token", delete=False) as ftmp:
        ftmp.write(str(conteudo or "").strip())
        caminho_tmp = ftmp.name

    try:
        media = MediaFileUpload(caminho_tmp, mimetype="text/plain", resumable=False)
        if existentes:
            file_id = str(existentes[0].get("id") or "")
            if not file_id:
                return False, "Arquivo de token existente sem id no Drive."
            service.files().update(fileId=file_id, media_body=media).execute()
            return True, f"Token atualizado no Drive: {nome}"

        service.files().create(
            body={"name": nome, "parents": [folder_id]},
            media_body=media,
            fields="id",
        ).execute()
        return True, f"Token enviado ao Drive: {nome}"
    finally:
        try:
            os.remove(caminho_tmp)
        except Exception:
            pass


def _ler_arquivo_texto_drive(service, folder_id: str, nome_arquivo: str) -> tuple[bool, str, str]:
    if MediaIoBaseDownload is None:
        return False, "", "Dependência Google Drive ausente para leitura do arquivo."

    nome = str(nome_arquivo or "").strip()
    if not nome:
        return False, "", "Nome do arquivo de leitura inválido."

    nome_esc = nome.replace("'", "\\'")
    q = f"name='{nome_esc}' and trashed=false and '{folder_id}' in parents"
    arquivos = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])
    if not arquivos:
        return False, "", "Arquivo não encontrado no Drive."

    fid = str(arquivos[0].get("id") or "").strip()
    if not fid:
        return False, "", "Arquivo encontrado no Drive sem ID."

    req = service.files().get_media(fileId=fid)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, req)
    done = False
    while not done:
        _status, done = downloader.next_chunk()

    conteudo = buffer.getvalue().decode("utf-8", errors="ignore").strip()
    if not conteudo:
        return False, "", "Arquivo vazio no Drive."
    return True, conteudo, "OK"


def _ler_token_drive(service, folder_id: str, nome_arquivo: str = TOKEN_ARQUIVO_NOME) -> tuple[bool, str, str]:
    if MediaIoBaseDownload is None:
        return False, "", "Dependência Google Drive ausente para download do token."

    nome = str(nome_arquivo or TOKEN_ARQUIVO_NOME).strip() or TOKEN_ARQUIVO_NOME
    nome_esc = nome.replace("'", "\\'")
    q = f"name='{nome_esc}' and trashed=false and '{folder_id}' in parents"
    arquivos = service.files().list(q=q, fields="files(id,name)", pageSize=1).execute().get("files", [])
    if not arquivos:
        return False, "", "Arquivo de token não encontrado no Drive."

    fid = str(arquivos[0].get("id") or "").strip()
    if not fid:
        return False, "", "Arquivo de token encontrado sem ID no Drive."

    req = service.files().get_media(fileId=fid)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, req)
    done = False
    while not done:
        _status, done = downloader.next_chunk()

    conteudo = buffer.getvalue().decode("utf-8", errors="ignore").strip()
    if not conteudo:
        return False, "", "Arquivo de token vazio no Drive."
    return True, conteudo, "OK"


def publicar_token_acesso_drive(user_id: str = "", dias_validade: int = TOKEN_VALIDADE_DIAS) -> tuple[bool, str]:
    uid = str(user_id or "").strip().lower() or obter_user_id_token_padrao()
    if not uid:
        return False, "Não foi possível determinar user_id para token."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg
    if google_build is None:
        return False, "Dependência google-api-python-client não encontrada."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = _obter_ou_criar_pasta_drive_usuario(service, GOOGLE_DRIVE_PASTA_TOKEN)
        token = gerar_token_acesso(uid, dias_validade=dias_validade)
        return _upsert_arquivo_texto_drive(service, folder_id, TOKEN_ARQUIVO_NOME, token)
    except Exception as e:
        return False, f"Falha ao publicar token no Drive: {e}"


def publicar_licenca_drive(chave: str) -> tuple[bool, str]:
    chave_limpa = _normalizar_texto_chave_licenca(chave)
    if not chave_limpa:
        return False, "Chave de licença vazia."

    valida, msg, _payload = validar_chave_licenca(chave_limpa)
    if not valida:
        return False, msg

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg
    if google_build is None:
        return False, "Dependência google-api-python-client não encontrada."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = _obter_ou_criar_pasta_drive_usuario(service, GOOGLE_DRIVE_PASTA_LICENCA)
        return _upsert_arquivo_texto_drive(service, folder_id, "licenca.key", chave_limpa)
    except Exception as e:
        return False, f"Falha ao publicar licença no Drive: {e}"


def obter_chave_licenca_drive() -> tuple[bool, str, str]:
    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, "", msg
    if google_build is None:
        return False, "", "Dependência google-api-python-client não encontrada."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = _obter_ou_criar_pasta_drive_usuario(service, GOOGLE_DRIVE_PASTA_LICENCA)
        return _ler_arquivo_texto_drive(service, folder_id, "licenca.key")
    except Exception as e:
        return False, "", f"Falha ao ler licença no Drive: {e}"


def renovar_token_acesso_drive_se_necessario(force: bool = False) -> tuple[bool, str]:
    status = obter_status_acesso_centralizado()
    if not bool(status.get("ativa")):
        return False, "Licença principal inativa; token não renovado."

    uid = obter_user_id_token_padrao()
    if not uid:
        return False, "User ID do token não definido."

    creds, msg = _obter_credenciais_google_drive_usuario(interativo=False)
    if not creds:
        return False, msg
    if google_build is None:
        return False, "Dependência google-api-python-client não encontrada."

    try:
        service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
        folder_id = _obter_ou_criar_pasta_drive_usuario(service, GOOGLE_DRIVE_PASTA_TOKEN)

        if not force:
            ok_token, token_atual, msg_token = _ler_token_drive(service, folder_id, TOKEN_ARQUIVO_NOME)
            if ok_token:
                ok_val, _msg_val, payload = validar_token_acesso(token_atual, user_id_esperado=uid)
                if ok_val and isinstance(payload, dict):
                    exp_txt = str(payload.get("exp") or "").strip()
                    try:
                        exp = date.fromisoformat(exp_txt)
                        faltam = (exp - date.today()).days
                        if faltam > TOKEN_RENOVAR_FALTANDO_DIAS:
                            return True, f"Token vigente por {faltam} dia(s); renovação não necessária."
                    except Exception:
                        pass
            elif "não encontrado" not in str(msg_token or "").lower():
                return False, msg_token

        token_novo = gerar_token_acesso(uid, dias_validade=TOKEN_VALIDADE_DIAS)
        return _upsert_arquivo_texto_drive(service, folder_id, TOKEN_ARQUIVO_NOME, token_novo)
    except Exception as e:
        return False, f"Falha na renovação automática do token: {e}"


def diagnosticar_chave_licenca(chave: str) -> dict:
    """Retorna dados tecnicos para suporte da ativacao de licenca."""
    chave_bruta = str(chave or "")
    chave_limpa = _normalizar_texto_chave_licenca(chave_bruta)

    diag = {
        "chave_bruta": chave_bruta,
        "chave_limpa": chave_limpa,
        "tem_prefixo_ofp": chave_limpa.startswith("OFP-"),
        "partes": 0,
        "payload_b64": "",
        "assinatura_recebida": "",
        "assinatura_esperada": "",
        "assinatura_confere": False,
        "payload_decodificado": False,
        "hw_payload": "",
        "hw_payload_normalizado": "",
        "hw_local": normalizar_chave_instalacao(obter_chave_instalacao()),
        "hw_igual": False,
    }

    if not diag["tem_prefixo_ofp"]:
        return diag

    try:
        _prefixo, payload_b64, assinatura = chave_limpa.split("-", 2)
        diag["partes"] = 3
        diag["payload_b64"] = payload_b64
        diag["assinatura_recebida"] = str(assinatura or "").strip().upper()
        diag["assinatura_esperada"] = _assinar_payload(payload_b64)
        diag["assinatura_confere"] = hmac.compare_digest(diag["assinatura_esperada"], diag["assinatura_recebida"])
    except ValueError:
        diag["partes"] = len(chave_limpa.split("-"))
        return diag

    try:
        padding = "=" * ((4 - len(diag["payload_b64"]) % 4) % 4)
        payload_json = base64.urlsafe_b64decode((diag["payload_b64"] + padding).encode("ascii")).decode("utf-8")
        payload = json.loads(payload_json)
        hw_payload = str(payload.get("hw", ""))
        diag["payload_decodificado"] = True
        diag["hw_payload"] = hw_payload
        diag["hw_payload_normalizado"] = _normalizar_hw_para_assinatura(hw_payload)
        diag["hw_igual"] = bool(diag["hw_payload_normalizado"]) and (diag["hw_payload_normalizado"] == diag["hw_local"])
    except Exception:
        return diag

    return diag


def ativar_licenca(chave: str):
    chave_limpa = _normalizar_texto_chave_licenca(chave)
    valida, msg, payload = validar_chave_licenca(chave_limpa)
    if not valida:
        return False, msg

    cliente = ""
    validade = str((payload or {}).get("val", "PERMANENTE"))
    tipo = str((payload or {}).get("tipo", "")).upper().strip()
    tipo = _normalizar_tipo_licenca(tipo, validade)

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_chave', ?)",
            (chave_limpa,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_cliente', ?)",
            (cliente,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_validade', ?)",
            (validade,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_tipo', ?)",
            (tipo,)
        )
        cursor.execute(
            "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_ja_ativada', '1')"
        )
        conn.commit()

    try:
        caminho_key = os.path.join(DIRETORIO_ATUAL, "licenca.key")
        with open(caminho_key, "w", encoding="utf-8") as f:
            f.write(chave_limpa)
    except Exception as exc:
        return False, f"Licença validada, mas falhou ao gravar arquivo licenca.key: {exc}"

    return True, "Licenca ativada com sucesso."


def obter_status_licenca():
    """Retorna status da licença ativa (chave local/Drive ou token).

    Observação: o fallback para trial é tratado em obter_status_acesso_centralizado().
    """
    chave, cliente_arquivo, validade_arquivo, _erro_arquivo = _extrair_licenca_de_arquivo()
    if chave:
        ok_chave, msg_chave, payload_chave = validar_chave_licenca(chave)
        if ok_chave:
            validade = str((payload_chave or {}).get("val") or validade_arquivo or "PERMANENTE").strip()
            cliente = str((payload_chave or {}).get("cliente") or cliente_arquivo or "").strip()
            tipo = _normalizar_tipo_licenca(str((payload_chave or {}).get("tipo") or ""), validade)

            try:
                with get_db_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_chave', ?)",
                        (chave,)
                    )
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_cliente', ?)",
                        (cliente,)
                    )
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_validade', ?)",
                        (validade,)
                    )
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_tipo', ?)",
                        (tipo,)
                    )
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_ja_ativada', '1')"
                    )
                    conn.commit()
            except Exception:
                pass

            return True, "Licença válida.", cliente, validade

    uid = str(obter_user_id_token_padrao() or "").strip().lower()
    if not uid:
        return False, "Licença inativa", "", "SEM_TOKEN"

    token = ""
    token_origem = ""
    caminhos_token = [
        os.path.join(DIRETORIO_ATUAL, TOKEN_ARQUIVO_NOME),
        os.path.join(DIRETORIO_DADOS, TOKEN_ARQUIVO_NOME),
    ]

    for caminho in caminhos_token:
        try:
            if os.path.exists(caminho):
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = str(f.read() or "").strip()
                if conteudo:
                    token = conteudo
                    token_origem = caminho
                    break
        except Exception:
            continue

    if not token:
        try:
            creds, _msg = _obter_credenciais_google_drive_usuario(interativo=False)
            if creds and google_build is not None:
                service = google_build("drive", "v3", credentials=creds, cache_discovery=False)
                folder_id = _obter_ou_criar_pasta_drive_usuario(service, GOOGLE_DRIVE_PASTA_TOKEN)
                ok_drive, token_drive, _msg_drive = _ler_token_drive(service, folder_id, TOKEN_ARQUIVO_NOME)
                if ok_drive:
                    token = token_drive
                    token_origem = "drive"
        except Exception:
            token = ""

    if not token:
        return False, "Licença inativa", uid, "SEM_TOKEN"

    ok, _msg_token, payload = validar_token_acesso(token, user_id_esperado=uid)
    if not ok:
        validade_payload = str((payload or {}).get("exp") or "INVALIDA").strip() if isinstance(payload, dict) else "INVALIDA"
        return False, "Licença inativa", uid, validade_payload

    validade = str((payload or {}).get("exp") or "ATIVA").strip() if isinstance(payload, dict) else "ATIVA"

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_chave', ?)",
                (f"TOKEN::{token_origem}",)
            )
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_cliente', ?)",
                (uid,)
            )
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_validade', ?)",
                (validade,)
            )
            cursor.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('licenca_tipo', ?)",
                ("TOKEN",)
            )
            conn.commit()
    except Exception:
        pass

    return True, "Token de acesso válido.", uid, validade


def obter_status_acesso_centralizado() -> dict:
    """Avalia acesso final: licença ativa OU trial válido (15 dias)."""
    licenca_ativa, msg_licenca, cliente_licenca, validade_licenca = obter_status_licenca()
    trial_ativo = False
    dias_trial_restantes = 0
    data_limite_trial = ""

    if not licenca_ativa:
        try:
            trial_ativo, dias_trial_restantes, data_limite_trial = obter_status_trial()
            trial_ativo = bool(trial_ativo)
            dias_trial_restantes = int(dias_trial_restantes or 0)
            data_limite_trial = str(data_limite_trial or "").strip()
        except Exception:
            trial_ativo = False
            dias_trial_restantes = 0
            data_limite_trial = ""

    acesso_liberado = bool(licenca_ativa or trial_ativo)
    bloqueada = not acesso_liberado

    if licenca_ativa:
        mensagem = str(msg_licenca or "Licença ativa.").strip()
        tipo = str(obter_tipo_licenca() or "ATIVO").strip().upper()
    elif trial_ativo:
        mensagem = f"Modo Trial ativo: {dias_trial_restantes} dia(s) restante(s) (até {data_limite_trial})."
        tipo = "TRIAL"
    else:
        mensagem = str(msg_licenca or "Licença inativa.").strip()
        tipo = "INATIVA"

    return {
        "ativa": acesso_liberado,
        "bloqueada": bloqueada,
        "licenca_ativa": bool(licenca_ativa),
        "trial_ativo": bool(trial_ativo),
        "mensagem": str(mensagem or "").strip(),
        "cliente": str(cliente_licenca or "").strip(),
        "validade": str(validade_licenca or "").strip(),
        "tipo": tipo,
        "dias_trial_restantes": int(dias_trial_restantes or 0),
        "data_limite_trial": data_limite_trial,
        "validacao_remota_ok": True,
        "validacao_remota_msg": "",
    }


def obter_dias_para_vencimento_licenca() -> Optional[int]:
    """Retorna dias para vencimento da licença ativa; None para permanente/invalida."""
    lic_ativa, _msg, _cliente, validade = obter_status_licenca()
    if not lic_ativa:
        return None

    validade_txt = str(validade or "").strip()
    if not validade_txt or validade_txt.upper() == "PERMANENTE":
        return None

    try:
        data_validade = date.fromisoformat(validade_txt)
    except ValueError:
        return None

    return (data_validade - date.today()).days


def licenca_vence_em_ate_dias(dias_limite: int = 7) -> tuple[bool, Optional[int]]:
    """Indica se a licença ativa vence em ate dias_limite (inclusive)."""
    dias_restantes = obter_dias_para_vencimento_licenca()
    if dias_restantes is None:
        return False, None
    return 0 <= dias_restantes <= int(dias_limite), dias_restantes


def ja_teve_licenca_ativa() -> bool:
    """Sinaliza se ja houve ativacao de licença nesta instalaÃ§Ã£o."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_ja_ativada'")
            row_hist = cursor.fetchone()
            historico = str(row_hist[0] if row_hist and row_hist[0] else "").strip()
            if historico in {"1", "TRUE", "True", "SIM", "sim"}:
                return True
    except Exception:
        pass

    return bool(obter_chave_licenca_ativa())


def obter_tipo_licenca() -> str:
    ativa, _msg, _cliente, validade = obter_status_licenca()
    if ativa:
        return _normalizar_tipo_licenca("", str(validade or ""))

    trial_ativo, _dias, _limite = obter_status_trial()
    if bool(trial_ativo):
        return "TRIAL"

    return "INATIVA"


def obter_chave_licenca_ativa() -> str:
    chave, _cliente, _validade, _erro = _extrair_licenca_de_arquivo()
    return chave


def obter_status_trial():
    """Retorna status do trial: (ativo, dias_restantes, data_limite)."""
    hoje_ordinal = date.today().toordinal()
    data_limite = ""

    def _ler_trial() -> tuple[int, int]:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
                (hoje_ordinal,)
            )
            conn.commit()

            cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'trial_inicio_ordinal'")
            row = cursor.fetchone()

            try:
                inicio = int(row[0]) if row and row[0] is not None else hoje_ordinal
            except Exception:
                inicio = hoje_ordinal
            return inicio, hoje_ordinal

    try:
        inicio_ordinal, _ = _ler_trial()
    except Exception as exc:
        msg_exc = str(exc)
        if "no such table: configuracoes" in msg_exc.lower():
            try:
                inicializar_banco()
                inicio_ordinal, _ = _ler_trial()
            except Exception:
                inicio_ordinal = hoje_ordinal
        else:
            inicio_ordinal = hoje_ordinal

    dias_passados = max(0, hoje_ordinal - inicio_ordinal)
    dias_restantes = max(0, TRIAL_DIAS - dias_passados)

    # Regra operacional: sem licença ativa prévia, libera um ciclo de trial automático.
    if dias_restantes <= 0:
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'trial_auto_bootstrap_v1'")
                row_bootstrap = cursor.fetchone()
                bootstrap_ja_usado = str(row_bootstrap[0] if row_bootstrap and row_bootstrap[0] is not None else "").strip() in {"1", "true", "TRUE", "sim", "SIM"}

                cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_ja_ativada'")
                row_hist = cursor.fetchone()
                historico_ativacao = str(row_hist[0] if row_hist and row_hist[0] is not None else "").strip() in {"1", "true", "TRUE", "sim", "SIM"}

                tem_chave_ativa = bool(obter_chave_licenca_ativa())

                if (not bootstrap_ja_usado) and (not historico_ativacao) and (not tem_chave_ativa):
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('trial_inicio_ordinal', ?)",
                        (hoje_ordinal,)
                    )
                    cursor.execute(
                        "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES ('trial_auto_bootstrap_v1', '1')"
                    )
                    conn.commit()
                    inicio_ordinal = hoje_ordinal
                    dias_passados = 0
                    dias_restantes = TRIAL_DIAS
        except Exception:
            pass

    limite_ordinal = inicio_ordinal + TRIAL_DIAS
    data_limite = date.fromordinal(limite_ordinal).strftime("%d/%m/%Y")

    return dias_restantes > 0, dias_restantes, data_limite
