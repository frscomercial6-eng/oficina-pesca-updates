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
import subprocess
import re
import threading
import time
import glob
import shutil
import platform
import uuid
from datetime import date, datetime
from typing import Optional
from contextlib import contextmanager
import urllib.request
import urllib.error

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
    import winreg  # type: ignore
except Exception:
    winreg = None

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Carrega variÃ¡veis de ambiente locais (desenvolvimento/build) sem quebrar em produÃ§Ã£o.
try:
    _ENV_BASE = os.path.dirname(os.path.abspath(__file__))
    _ENV_PATH = os.path.join(_ENV_BASE, ".env")
    if load_dotenv:
        load_dotenv(_ENV_PATH, override=False)
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


def _obter_diretorio_dados() -> str:
    if getattr(sys, 'frozen', False):
        base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or _obter_diretorio_execucao()
        return os.path.join(base, 'OficinaPesca', 'dados')
    return _obter_diretorio_execucao()


if getattr(sys, 'frozen', False):
    DIRETORIO_ATUAL = _obter_diretorio_execucao()
    DIRETORIO_RECURSOS = sys._MEIPASS
else:
    DIRETORIO_ATUAL = _obter_diretorio_execucao()
    DIRETORIO_RECURSOS = DIRETORIO_ATUAL

DIRETORIO_DADOS = _obter_diretorio_dados()
CAMINHO_BANCO_LOCAL = os.path.join(DIRETORIO_DADOS, 'oficina.db')
CAMINHO_BANCO_INSTALACAO = os.path.join(DIRETORIO_ATUAL, 'oficina.db')
CAMINHO_BANCO = CAMINHO_BANCO_INSTALACAO if os.path.exists(CAMINHO_BANCO_INSTALACAO) else CAMINHO_BANCO_LOCAL
CAMINHO_LOG = os.path.join((os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA') or DIRETORIO_ATUAL), 'OficinaPesca', 'logs', 'oficina_debug.txt')

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

CENTRAL_SUPORTE_EMAIL = "frs.suporte.oficina@gmail.com"
CENTRAL_UPDATE_MANIFEST_URL = str(
    os.environ.get('OFP_CENTRAL_UPDATE_MANIFEST_URL', '')
    or _CFG.get('central', 'update_manifest_url', fallback='https://raw.githubusercontent.com/frscomercial6-eng/oficina-pesca-updates/main/versao.txt')
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
    fallback='https://api.infinitepay.io/invoices/public/checkout/links'
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
# Se a variÃ¡vel de ambiente nÃ£o existir, mantÃ©m fallback compatÃ­vel.
LICENCA_SECRET = os.environ.get("OFP_LICENCA_SECRET", "")

_CLOUD_SYNC_THREAD: Optional[threading.Thread] = None
_CLOUD_SYNC_STARTED = False
_DISCOVERY_CACHE = {"url": "", "ts": 0.0}
GOOGLE_DRIVE_USER_SCOPES = [
    # Escopo explicitamente definido para permitir acesso a arquivos criados pelo App
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]
GOOGLE_DRIVE_PASTA_APP = "Oficina de Pesca"


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


def obter_info_nova_versao() -> dict:
    """ObtÃ©m dados da versÃ£o remota (JSON ou TXT). Retorna dict vazio em caso de falha."""
    # Limpeza agressiva da URL para evitar caracteres de controle e prefixos indesejados
    url_raw = str(URL_CHECK_VERSAO or "").strip()
    # Usa Regex para garantir que pegamos apenas o link válido, removendo lixos como "url_check ="
    match = re.search(r'https?://[^\s]+', url_raw)
    url_limpa = match.group(0) if match else ""
    
    if not url_limpa or len(url_limpa) < 10:
        return {}

    def _parse_manifesto(conteudo: str) -> dict:
        bruto = str(conteudo or "").strip()
        if not bruto:
            return {}

        # Tenta JSON primeiro
        try:
            data_json = json.loads(bruto)
            if isinstance(data_json, dict):
                return data_json
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
            or ""
        )

        saida = {
            "versao": str(versao).strip(),
            "novidades": str(novidades).strip(),
            "url_download": str(url_download).strip(),
        }
        return {k: v for k, v in saida.items() if v}

    try:
        import urllib.request
        req = urllib.request.Request(
            url_limpa,
            headers={"User-Agent": f"OficinaPesca/{APP_VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=1) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
        return _parse_manifesto(payload)
    except Exception as e:
        print(f"❌ ERRO CRÍTICO NA BUSCA DE ATUALIZAÇÃO: {e}")
        return {}


def eh_versao_mais_nova(versao_remota: str, versao_local: str) -> bool:
    """Compara versÃµes no formato semÃ¢ntico simples (ex.: 1.2.3)."""
    def _to_tuple(v: str) -> tuple[int, ...]:
        partes = []
        for p in str(v or "").strip().split("."):
            try:
                partes.append(int(p))
            except ValueError:
                partes.append(0)
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
            return True, "Banco sincronizado (upload para nuvem)."
        elif timestamp_nuvem > timestamp_local and existe_na_nuvem:
            # Nuvem é mais recente: download
            request = service.files().get_media(fileId=file_id)
            with open(CAMINHO_BANCO, "wb") as f:
                f.write(request.execute())
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
) -> tuple[bool, str]:
    """Fluxo de autoatualização desativado para evitar instalação em diretórios temporários."""
    url = str(url_download or "").strip()
    if not url:
        return False, "URL de download nÃ£o configurada."

    if not url.lower().startswith(("http://", "https://")):
        return False, "URL de download invÃ¡lida."
    return (
        False,
        "Autoatualização desativada nesta versão. Use apenas o instalador oficial Instalador_Oficina_Pesca.exe.",
    )


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
            cep TEXT,
            rua TEXT,
            numero TEXT,
            bairro TEXT,
            cidade TEXT,
            estado TEXT,
            data_cadastro TEXT
        )
    """)

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

    cursor.execute("PRAGMA table_info(fluxo_caixa)")
    colunas_fluxo = [row[1] for row in cursor.fetchall()]
    if 'categoria' not in colunas_fluxo:
        cursor.execute("ALTER TABLE fluxo_caixa ADD COLUMN categoria TEXT")

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

    Prioridades (da mais para a menos estável):
      1. MachineGuid do registro do Windows — não muda entre reinicializações.
      2. ID persistido em arquivo em AppData — gerado uma vez e reutilizado.
    """
    # Prioridade 1: MachineGuid do Windows (altamente estável)
    if winreg is not None:
        try:
            _reg_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            _machine_guid, _ = winreg.QueryValueEx(_reg_key, "MachineGuid")
            if _machine_guid:
                return hashlib.sha256(str(_machine_guid).strip().encode("utf-8")).hexdigest().upper()
        except Exception:
            pass

    # Prioridade 2: ID persistido em arquivo (estável entre reinicializações sem depender de rede)
    _pasta_appdata = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("APPDATA")
        or DIRETORIO_ATUAL
    )
    _id_file = os.path.join(_pasta_appdata, "OficinaPesca", "hardware_id.txt")
    try:
        if os.path.exists(_id_file):
            with open(_id_file, "r", encoding="utf-8") as _f:
                _cached = _f.read().strip()
            if _cached:
                return _cached
    except Exception:
        pass

    # Fallback: gerar a partir de dados disponíveis e persistir para estabilidade futura
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
    _hw_id = hashlib.sha256(_base.encode("utf-8")).hexdigest().upper()
    try:
        os.makedirs(os.path.dirname(_id_file), exist_ok=True)
        with open(_id_file, "w", encoding="utf-8") as _f:
            _f.write(_hw_id)
    except Exception:
        pass
    return _hw_id


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

    return True, "Licenca ativada com sucesso."


def obter_status_licenca():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_chave'")
        row_chave = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_cliente'")
        row_cliente = cursor.fetchone()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_validade'")
        row_validade = cursor.fetchone()

    chave = row_chave[0] if row_chave and row_chave[0] else ""
    cliente = row_cliente[0] if row_cliente and row_cliente[0] else ""
    validade = row_validade[0] if row_validade and row_validade[0] else "PERMANENTE"

    if not chave:
        return False, "Sem licenca ativa.", "", "PERMANENTE"

    valida, msg, _payload = validar_chave_licenca(chave)
    if not valida:
        return False, msg, cliente, validade

    return True, "Licenca ativa.", cliente, validade


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
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_tipo'")
        row_tipo = cursor.fetchone()
        if row_tipo and row_tipo[0]:
            tipo = str(row_tipo[0]).upper().strip()
            if tipo in TIPOS_LICENCA_DIAS:
                return tipo

        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_validade'")
        row_validade = cursor.fetchone()
        validade = str(row_validade[0] if row_validade and row_validade[0] else "").upper().strip()

    return _inferir_tipo_por_validade(validade)


def obter_chave_licenca_ativa() -> str:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = 'licenca_chave'")
        row = cursor.fetchone()
    return str(row[0] if row and row[0] else "").strip()


def obter_status_trial():
    """Retorna status do trial: (ativo, dias_restantes, data_limite)."""
    hoje_ordinal = date.today().toordinal()
    data_limite = ""

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
            inicio_ordinal = int(row[0]) if row and row[0] is not None else hoje_ordinal
        except Exception:
            inicio_ordinal = hoje_ordinal

    dias_passados = max(0, hoje_ordinal - inicio_ordinal)
    dias_restantes = max(0, TRIAL_DIAS - dias_passados)
    limite_ordinal = inicio_ordinal + TRIAL_DIAS
    data_limite = date.fromordinal(limite_ordinal).strftime("%d/%m/%Y")

    return dias_restantes > 0, dias_restantes, data_limite
