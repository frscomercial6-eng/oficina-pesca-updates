# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
servidor.py — Servidor multi-usuário da Oficina de Pesca

Permite acesso simultâneo de:
  - Múltiplos PCs na rede local (LAN)
  - Celular / tablet via navegador
  - Qualquer dispositivo com acesso à internet

Como iniciar:
    python servidor.py
    python servidor.py --host 0.0.0.0 --porta 8000

Acesso pela rede local:
    Desktop: configure config.cfg → servidor_url = http://IP_DO_SERVIDOR:8000
    Celular:  abra o navegador em   http://IP_DO_SERVIDOR:8000
"""

import os
import sys
import json
import re
import base64
import hmac
import argparse
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, Request, Form, status as http_status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from core.i18n import t
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

try:
    from zeroconf import ServiceInfo, Zeroconf
except Exception:
    ServiceInfo = None
    Zeroconf = None

# Importa funções do sistema existente
# Adaptar caminho se necessário
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    get_db_connection,
    hash_password,
    verify_password,
    validate_password,
    get_logger,
    inicializar_banco,
    APP_VERSION,
    _CFG,
    gerar_chave_licenca,
    gerar_hash_publico_licenca,
    normalizar_chave_instalacao,
)

logger = get_logger("servidor")
_ZEROCONF_INSTANCE = None
_ZEROCONF_SERVICE_INFO = None
_SERVER_RUNTIME_HOST = _CFG.get("servidor", "host", fallback="0.0.0.0")
_SERVER_RUNTIME_PORT = _CFG.getint("servidor", "porta", fallback=8000)
_DISCOVERY_PORT = 42111
_DISCOVERY_STOP_EVENT = threading.Event()
_DISCOVERY_THREAD: Optional[threading.Thread] = None


def _payload_discovery(runtime_port: int, kind: str = "OFP_DISCOVERY") -> bytes:
    ip_lan = _detectar_ip_lan()
    payload = {
        "type": kind,
        "app": "oficina_pesca",
        "version": APP_VERSION,
        "host": ip_lan,
        "port": int(runtime_port),
        "login_url": f"http://{ip_lan}:{int(runtime_port)}/web/login",
        "app_url": f"http://{ip_lan}:{int(runtime_port)}/app",
    }
    return json.dumps(payload).encode("utf-8")


def _loop_discovery_udp(runtime_port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("", _DISCOVERY_PORT))
        sock.settimeout(1.0)
        next_announce = 0.0

        while not _DISCOVERY_STOP_EVENT.is_set():
            now = time.time()
            if now >= next_announce:
                try:
                    sock.sendto(_payload_discovery(runtime_port, kind="OFP_DISCOVERY"), ("255.255.255.255", _DISCOVERY_PORT))
                except Exception:
                    pass
                next_announce = now + 2.5

            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                continue

            try:
                req = json.loads(data.decode("utf-8", errors="ignore"))
            except Exception:
                continue

            req_type = str(req.get("type", "")).strip().upper()
            if req_type != "OFP_DISCOVER_REQUEST":
                continue

            try:
                sock.sendto(_payload_discovery(runtime_port, kind="OFP_DISCOVER_RESPONSE"), addr)
            except Exception:
                pass
    except Exception as e:
        logger.info("Falha no serviço UDP discovery: %s", e)
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _iniciar_discovery_udp(runtime_port: int) -> None:
    global _DISCOVERY_THREAD
    if _DISCOVERY_THREAD and _DISCOVERY_THREAD.is_alive():
        return
    _DISCOVERY_STOP_EVENT.clear()
    _DISCOVERY_THREAD = threading.Thread(target=_loop_discovery_udp, args=(int(runtime_port),), daemon=True)
    _DISCOVERY_THREAD.start()
    logger.info("UDP discovery ativo na porta %s (anúncio + resposta).", _DISCOVERY_PORT)


def _encerrar_discovery_udp() -> None:
    _DISCOVERY_STOP_EVENT.set()

# ─── CONFIGURAÇÃO JWT ────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get(
    "OFP_JWT_SECRET",
    _CFG.get("servidor", "jwt_secret", fallback="OFP-JWT-ALTERAR-EM-PRODUCAO")
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HORAS = 8

# ─── APP ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Oficina de Pesca",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates HTML (interface web/mobile)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["t"] = t

# Arquivos estáticos (CSS/JS)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token", auto_error=False)


def _detectar_ip_lan() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = str(sock.getsockname()[0] or "").strip()
        finally:
            sock.close()
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _registrar_servico_zeroconf(host: str, porta: int) -> None:
    global _ZEROCONF_INSTANCE, _ZEROCONF_SERVICE_INFO
    if not Zeroconf or not ServiceInfo:
        logger.info("Zeroconf indisponível; anúncio LAN não iniciado.")
        return

    ip_lan = _detectar_ip_lan()
    if not ip_lan or ip_lan == "127.0.0.1":
        logger.info("IP LAN não detectado; anúncio Zeroconf ignorado.")
        return

    try:
        nome_host = re.sub(r"[^a-zA-Z0-9-]+", "-", socket.gethostname()).strip("-") or "oficina-pesca"
        service_type = "_oficinapesca._tcp.local."
        service_name = f"Oficina de Pesca - {nome_host}.{service_type}"
        props = {
            b"app": b"oficina_pesca",
            b"version": str(APP_VERSION).encode("utf-8"),
            b"login_path": b"/web/login",
            b"app_path": b"/app",
        }
        info = ServiceInfo(
            type_=service_type,
            name=service_name,
            addresses=[socket.inet_aton(ip_lan)],
            port=int(porta),
            properties=props,
            server=f"{nome_host}.local.",
        )
        _ZEROCONF_INSTANCE = Zeroconf()
        _ZEROCONF_SERVICE_INFO = info
        _ZEROCONF_INSTANCE.register_service(info)
        logger.info("Serviço Zeroconf anunciado em %s:%s", ip_lan, porta)
    except Exception as e:
        logger.info("Falha ao anunciar serviço Zeroconf: %s", e)


def _encerrar_servico_zeroconf() -> None:
    global _ZEROCONF_INSTANCE, _ZEROCONF_SERVICE_INFO
    try:
        if _ZEROCONF_INSTANCE and _ZEROCONF_SERVICE_INFO:
            _ZEROCONF_INSTANCE.unregister_service(_ZEROCONF_SERVICE_INFO)
    except Exception:
        pass
    try:
        if _ZEROCONF_INSTANCE:
            _ZEROCONF_INSTANCE.close()
    except Exception:
        pass
    _ZEROCONF_INSTANCE = None
    _ZEROCONF_SERVICE_INFO = None


def _coletar_saude_sistema() -> dict:
    from config import (
        obter_status_acesso_centralizado,
        obter_firebase_web_config,
        obter_config_backup_nuvem,
        google_drive_usuario_conectado,
    )

    status_licenca = obter_status_acesso_centralizado()
    firebase_cfg = obter_firebase_web_config()
    backup_cfg = obter_config_backup_nuvem()

    firebase_ok = bool(firebase_cfg.get("databaseURL") and firebase_cfg.get("syncChannel"))
    backup_ok = bool(backup_cfg.get("habilitado"))

    return {
        "app": "oficina_pesca",
        "versao": APP_VERSION,
        "licenca": {
            "ativa": bool(status_licenca.get("ativa")),
            "bloqueada": bool(status_licenca.get("bloqueada")),
            "mensagem": str(status_licenca.get("mensagem") or "").strip(),
            "tipo": str(status_licenca.get("tipo") or "").strip(),
            "validade": str(status_licenca.get("validade") or "").strip(),
        },
        "firebase": {
            "ok": firebase_ok,
            "database_url": str(firebase_cfg.get("databaseURL") or "").strip(),
            "sync_channel": str(firebase_cfg.get("syncChannel") or "").strip(),
        },
        "backup": {
            "habilitado": bool(backup_cfg.get("habilitado")),
            "auto_sync": bool(backup_cfg.get("auto_sync")),
            "google_drive_conectado": bool(google_drive_usuario_conectado()),
            "ok": backup_ok,
        },
        "producao_autonoma": bool(status_licenca.get("ativa")) and firebase_ok,
    }


# ─── MODELOS ─────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    usuario: str
    role: str


class ClienteIn(BaseModel):
    nome: str
    telefone: Optional[str] = ""
    email: Optional[str] = ""
    cep: Optional[str] = ""
    rua: Optional[str] = ""
    numero: Optional[str] = ""
    bairro: Optional[str] = ""
    cidade: Optional[str] = ""
    estado: Optional[str] = ""


class OrcamentoStatusIn(BaseModel):
    status: str


class LancamentoIn(BaseModel):
    descricao: str
    tipo: str  # ENTRADA | SAIDA
    valor: float
    categoria: Optional[str] = ""
    metodo_pagamento: Optional[str] = ""
    data: Optional[str] = ""


class ProdutoIn(BaseModel):
    nome: str
    preco_custo: float = 0.0
    preco_venda: float = 0.0
    estoque: int = 0


class CloudBackupIn(BaseModel):
    email_cliente: str
    arquivo_nome: str
    conteudo_b64: str
    origem: Optional[str] = "desktop_admin"
    versao_app: Optional[str] = ""


class HubLicencaIn(BaseModel):
    cliente: str
    hwid: str
    programa: str = "Oficina_Pesca"
    plano: str = "PROMOCIONAL"
    dias_validade: Optional[int] = None
    tipo_licenca: Optional[str] = ""
    transactionId: Optional[str] = ""
    email: Optional[str] = ""
    source: Optional[str] = "hub_gas"


def _email_cliente_livre(valor: Optional[str]) -> str:
    """Mantem o e-mail do cliente sempre como texto para o app mobile."""
    return str(valor or "").strip()


def _hub_api_key_configurada() -> str:
    return str(
        os.environ.get("OFP_HUB_API_KEY", "")
        or _CFG.get("central", "hub_api_key", fallback="")
    ).strip()


def _validar_hub_api_key(request: Request) -> None:
    key_cfg = _hub_api_key_configurada()
    key_req = str(request.headers.get("X-OFP-Hub-Key", "")).strip()
    if not key_cfg:
        raise HTTPException(status_code=503, detail="HUB API key nao configurada no servidor.")
    if not key_req or not hmac.compare_digest(key_cfg, key_req):
        raise HTTPException(status_code=401, detail="Chave tecnica invalida.")


def _dias_por_plano(plano: str) -> Optional[int]:
    mapa = {
        "PROMOCIONAL": 90,
        "MENSAL": 30,
        "TRIMESTRAL": 90,
        "SEMESTRAL": 180,
        "ANUAL": 365,
        "PERMANENTE": None,
        "VIP": None,
    }
    return mapa.get(str(plano or "").strip().upper())


def _registrar_licenca_hub_db(chave: str, validade: str, hwid: str, email: str = "", cliente: str = "", tipo: str = "", plano: str = "") -> None:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS licencas_geradas (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                chave            TEXT NOT NULL,
                data_expiracao   TEXT NOT NULL,
                chave_instalacao TEXT NOT NULL DEFAULT '',
                data_geracao     TEXT NOT NULL
            )
            """
        )
        cur.execute("PRAGMA table_info(licencas_geradas)")
        cols = {row[1] for row in cur.fetchall()}
        if "chave_instalacao" not in cols:
            cur.execute("ALTER TABLE licencas_geradas ADD COLUMN chave_instalacao TEXT DEFAULT ''")
        if "email" not in cols:
            cur.execute("ALTER TABLE licencas_geradas ADD COLUMN email TEXT DEFAULT ''")
        if "cliente" not in cols:
            cur.execute("ALTER TABLE licencas_geradas ADD COLUMN cliente TEXT DEFAULT ''")
        if "tipo" not in cols:
            cur.execute("ALTER TABLE licencas_geradas ADD COLUMN tipo TEXT DEFAULT ''")
        if "plano" not in cols:
            cur.execute("ALTER TABLE licencas_geradas ADD COLUMN plano TEXT DEFAULT ''")
        cur.execute(
            "INSERT INTO licencas_geradas (chave, data_expiracao, chave_instalacao, data_geracao, email, cliente, tipo, plano) "
            "VALUES (?, ?, ?, DATE('now'), ?, ?, ?, ?)",
            (chave, validade, hwid, str(email or "").strip().lower(), str(cliente or "").strip(), str(tipo or "").strip().upper(), str(plano or "").strip().upper()),
        )
        conn.commit()


def _status_licenca_por_email(email: str) -> dict:
    """Consulta a licenca mais recente gerada pelo Hub para o e-mail informado."""
    email_norm = str(email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_norm):
        return {"ok": False, "ativa": False, "mensagem": "E-mail invalido."}

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS licencas_geradas (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                chave            TEXT NOT NULL,
                data_expiracao   TEXT NOT NULL,
                chave_instalacao TEXT NOT NULL DEFAULT '',
                data_geracao     TEXT NOT NULL,
                email            TEXT DEFAULT '',
                cliente          TEXT DEFAULT '',
                tipo             TEXT DEFAULT '',
                plano            TEXT DEFAULT ''
            )
            """
        )
        cur.execute("PRAGMA table_info(licencas_geradas)")
        cols = {row[1] for row in cur.fetchall()}
        if "email" not in cols:
            cur.execute("ALTER TABLE licencas_geradas ADD COLUMN email TEXT DEFAULT ''")
            conn.commit()
            return {"ok": True, "ativa": False, "mensagem": "Nenhuma licenca encontrada para este e-mail."}

        cur.execute(
            "SELECT data_expiracao, cliente, tipo, plano, data_geracao FROM licencas_geradas "
            "WHERE lower(email) = ? ORDER BY id DESC LIMIT 1",
            (email_norm,),
        )
        row = cur.fetchone()

    if not row:
        return {"ok": True, "ativa": False, "mensagem": "Nenhuma licenca encontrada para este e-mail."}

    validade, cliente, tipo, plano, data_geracao = row
    validade = str(validade or "").strip()

    if validade.upper() == "PERMANENTE":
        ativa = True
    else:
        try:
            ativa = date.fromisoformat(validade) >= date.today()
        except ValueError:
            ativa = False

    mensagem = "Licenca ativa." if ativa else f"Licenca expirada em {validade}." if validade else "Licenca inativa."

    return {
        "ok": True,
        "ativa": ativa,
        "mensagem": mensagem,
        "cliente": str(cliente or "").strip(),
        "tipo": str(tipo or "").strip(),
        "plano": str(plano or "").strip(),
        "validade": validade,
        "data_geracao": str(data_geracao or "").strip(),
    }


def _registrar_licenca_hub_log(payload: dict) -> None:
    pasta_logs = os.path.join(BASE_DIR, "logs")
    os.makedirs(pasta_logs, exist_ok=True)
    caminho = os.path.join(pasta_logs, "hub_licencas_api.log")
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ─── HELPERS AUTH ─────────────────────────────────────────────────────────────
def _criar_token(usuario: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HORAS)
    payload = {"sub": usuario, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")


def _usuario_do_request(request: Request, bearer: str) -> dict:
    """Aceita Bearer token (API) ou cookie ofp_token (browser)."""
    if bearer:
        try:
            return _decodificar_token(bearer)
        except HTTPException:
            pass
    cookie = request.cookies.get("ofp_token", "")
    if cookie:
        try:
            return _decodificar_token(cookie)
        except HTTPException:
            pass
    raise HTTPException(status_code=401, detail="Não autenticado.")


async def get_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    return _usuario_do_request(request, token or "")


async def get_admin(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    payload = _usuario_do_request(request, token or "")
    if str(payload.get("role", "")).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN.")
    return payload


# ─── MIDDLEWARE: redireciona /web para login se sem cookie ───────────────────
def _checar_cookie(request: Request) -> Optional[dict]:
    cookie = request.cookies.get("ofp_token", "")
    if not cookie:
        return None
    try:
        return _decodificar_token(cookie)
    except HTTPException:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── AUTH ────────────────────────────────────────────────────────────────────
@app.post("/api/token", response_model=Token, tags=["Auth"])
async def api_login(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
            (form_data.username.strip(),)
        )
        row = cur.fetchone()
    if not row or not verify_password(form_data.password, str(row[0] or "")):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
    role = str(row[1] or "OPERADOR")
    token = _criar_token(form_data.username.strip(), role)
    return Token(access_token=token, token_type="bearer",
                 usuario=form_data.username.strip(), role=role)


# ─── VERSÃO ───────────────────────────────────────────────────────────────────
@app.get("/api/versao", tags=["Sistema"])
async def api_versao():
    """Retorna informações da versão atual do servidor.
    Configure url_check no config.cfg dos clientes apontando para este endpoint."""
    versao_file = os.path.join(BASE_DIR, "version.json")
    if not os.path.exists(versao_file):
        versao_file = os.path.join(BASE_DIR, "versao.json")
    if os.path.exists(versao_file):
        with open(versao_file, encoding="utf-8") as f:
            return json.load(f)
    return {"versao": APP_VERSION, "novidades": ""}


@app.get("/version.json", tags=["Sistema"], include_in_schema=False)
async def version_manifest():
    return await api_versao()


@app.get("/api/discovery", tags=["Sistema"])
async def api_discovery():
    porta = _CFG.getint("servidor", "porta", fallback=8000)
    ip_lan = _detectar_ip_lan()
    return {
        "ok": True,
        "app": "oficina_pesca",
        "version": APP_VERSION,
        "host": ip_lan,
        "port": porta,
        "login_url": f"http://{ip_lan}:{porta}/web/login",
        "app_url": f"http://{ip_lan}:{porta}/app",
    }


@app.get("/api/firebase-config", tags=["Sistema"])
async def api_firebase_config():
    """Retorna configuração pública do Firebase usada no app mobile/WebView."""
    try:
        from config import obter_firebase_web_config  # Import local para evitar ciclo.

        cfg = obter_firebase_web_config()
        return {
            "ok": True,
            "config": cfg,
            "syncChannel": str(cfg.get("syncChannel") or os.environ.get("OFP_FIREBASE_SYNC_CHANNEL", "global") or "global"),
        }
    except Exception as e:
        return {"ok": False, "erro": str(e), "config": {}}


@app.get("/api/licenca-status", tags=["Sistema"])
async def api_licenca_status():
    from config import obter_status_acesso_centralizado

    return obter_status_acesso_centralizado()


@app.get("/api/licencas/status-email", tags=["Licencas"])
async def api_licenca_status_por_email(email: str):
    """Consultado pelo APK mobile para liberar acesso a partir do e-mail cadastrado."""
    return _status_licenca_por_email(email)


@app.get("/api/health", tags=["Sistema"])
async def api_health():
    return _coletar_saude_sistema()


@app.post("/api/cloud-backup", tags=["Backup"])
async def api_cloud_backup(
    request: Request,
    body: CloudBackupIn,
    token: str = Depends(oauth2_scheme),
):
    """Recebe backup do desktop e grava no repositório de nuvem por e-mail do cliente."""
    actor = "SISTEMA"
    key_cfg = _CFG.get("cloud_backup", "api_key", fallback="").strip()
    key_req = request.headers.get("X-OFP-Cloud-Key", "").strip()

    autorizado = False
    if key_cfg and key_req and hmac.compare_digest(key_cfg, key_req):
        autorizado = True
        actor = "AUTO_SYNC"

    if not autorizado:
        payload = _usuario_do_request(request, token or "")
        if str(payload.get("role", "")).upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN ou chave técnica.")
        actor = str(payload.get("sub", "ADMIN"))

    email = str(body.email_cliente or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="E-mail de cliente inválido.")

    nome_arquivo = os.path.basename(str(body.arquivo_nome or "backup.db")).strip()
    if not nome_arquivo.lower().endswith(".db"):
        nome_arquivo += ".db"

    try:
        conteudo = base64.b64decode(str(body.conteudo_b64 or "").encode("ascii"), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Conteúdo de backup inválido (base64).")

    if not conteudo:
        raise HTTPException(status_code=400, detail="Backup vazio.")
    if len(conteudo) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup excede o limite de 50 MB.")

    cliente_dir = re.sub(r"[^a-z0-9._-]", "_", email)
    destino_dir = os.path.join(BASE_DIR, "cloud_backups", cliente_dir)
    os.makedirs(destino_dir, exist_ok=True)

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_final = f"{carimbo}_{nome_arquivo}"
    destino = os.path.join(destino_dir, nome_final)

    with open(destino, "wb") as f:
        f.write(conteudo)

    logger.info(
        "Backup nuvem criado por=%s para cliente=%s arquivo=%s origem=%s versao=%s",
        actor,
        email,
        nome_final,
        str(body.origem or ""),
        str(body.versao_app or ""),
    )
    return {"ok": True, "arquivo": nome_final, "email_cliente": email}


@app.post("/api/licencas/gerar/oficina", tags=["Licencas"])
async def api_gerar_licenca_oficina_hub(request: Request, body: HubLicencaIn):
    """Endpoint do Hub de Automacao para gerar licenca do modulo Oficina_Pesca."""
    _validar_hub_api_key(request)

    programa = str(body.programa or "Oficina_Pesca").strip()
    if programa != "Oficina_Pesca":
        raise HTTPException(status_code=400, detail="Este endpoint gera apenas licenca do modulo Oficina_Pesca.")

    hwid = normalizar_chave_instalacao(str(body.hwid or ""))
    if not hwid.startswith("OFP-INST-"):
        raise HTTPException(status_code=400, detail="HWID invalido. Esperado OFP-INST-...")

    dias = body.dias_validade if body.dias_validade is not None else _dias_por_plano(body.plano)
    if dias is None:
        validade = "PERMANENTE"
        tipo = "PERMANENTE"
    else:
        if int(dias) <= 0:
            raise HTTPException(status_code=400, detail="dias_validade deve ser maior que zero.")
        validade = (datetime.now().date() + timedelta(days=int(dias))).isoformat()
        tipo = str(body.tipo_licenca or "").strip().upper()

    chave = gerar_chave_licenca(
        cliente=str(body.cliente or "").strip(),
        dias_validade=None if validade == "PERMANENTE" else int(dias),
        tipo_licenca=tipo,
        chave_instalacao=hwid,
    )
    hash_pub = gerar_hash_publico_licenca(chave)

    _registrar_licenca_hub_db(
        chave,
        validade,
        hwid,
        email=str(body.email or ""),
        cliente=str(body.cliente or ""),
        tipo=tipo,
        plano=str(body.plano or ""),
    )
    _registrar_licenca_hub_log(
        {
            "ts": datetime.now().isoformat(),
            "programa": programa,
            "cliente": str(body.cliente or "").strip(),
            "hwid": hwid,
            "plano": str(body.plano or "").strip().upper(),
            "validade": validade,
            "transactionId": str(body.transactionId or "").strip(),
            "email": str(body.email or "").strip(),
            "source": str(body.source or "hub_gas").strip(),
            "chave": chave,
            "hash_publico": hash_pub,
        }
    )

    return {
        "ok": True,
        "message": "Licenca gerada com sucesso.",
        "programa": programa,
        "plano": str(body.plano or "").strip().upper(),
        "validade": validade,
        "chave": chave,
        "license_key": chave,
        "hash_publico": hash_pub,
    }


@app.get("/api/cloud-backup/latest", tags=["Backup"])
async def api_get_latest_backup(
    request: Request,
    email_cliente: str,
    token: str = Depends(oauth2_scheme),
):
    """Retorna o arquivo de banco de dados mais recente para o e-mail informado."""
    payload = _usuario_do_request(request, token or "")
    if str(payload.get("role", "")).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN.")

    email = str(email_cliente or "").strip().lower()
    cliente_dir = re.sub(r"[^a-z0-9._-]", "_", email)
    origem_dir = os.path.join(BASE_DIR, "cloud_backups", cliente_dir)

    if not os.path.exists(origem_dir):
        raise HTTPException(status_code=404, detail="Nenhum backup encontrado para este e-mail.")

    import glob
    arquivos = glob.glob(os.path.join(origem_dir, "*.db"))
    if not arquivos:
        raise HTTPException(status_code=404, detail="Nenhum arquivo .db encontrado.")

    # Pega o arquivo mais recente pela data de modificação
    mais_recente = max(arquivos, key=os.path.getmtime)
    
    # Opcional: Retornar o conteúdo em base64 ou direto como arquivo
    with open(mais_recente, "rb") as f:
        conteudo = f.read()

    logger.info("PC baixou backup mais recente para cliente=%s arquivo=%s", email, os.path.basename(mais_recente))
    
    return {
        "ok": True,
        "arquivo_nome": os.path.basename(mais_recente),
        "conteudo_b64": base64.b64encode(conteudo).decode("ascii")
    }


# ─── CLIENTES ─────────────────────────────────────────────────────────────────
@app.get("/api/clientes", tags=["Clientes"])
async def api_listar_clientes(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, telefone, email, cidade, estado, data_cadastro "
            "FROM clientes ORDER BY nome"
        )
        rows = cur.fetchall()
    keys = ["id", "nome", "telefone", "email", "cidade", "estado", "data_cadastro"]
    lista = []
    for r in rows:
        item = dict(zip(keys, r))
        item["email"] = _email_cliente_livre(item.get("email"))
        lista.append(item)
    return lista


@app.get("/api/clientes/{cliente_id}", tags=["Clientes"])
async def api_get_cliente(cliente_id: int, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    keys = ["id","nome","telefone","email","cep","rua","numero","bairro","cidade","estado","data_cadastro"]
    data = dict(zip(keys, row))
    data["email"] = _email_cliente_livre(data.get("email"))
    return data


@app.post("/api/clientes", status_code=201, tags=["Clientes"])
async def api_criar_cliente(cliente: ClienteIn, user=Depends(get_user)):
    now = datetime.now().strftime("%d/%m/%Y")
    email = _email_cliente_livre(cliente.email)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes "
            "(nome,telefone,email,cep,rua,numero,bairro,cidade,estado,data_cadastro) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cliente.nome, cliente.telefone, email, cliente.cep,
             cliente.rua, cliente.numero, cliente.bairro, cliente.cidade,
             cliente.estado, now)
        )
        conn.commit()
        return {"id": cur.lastrowid, "nome": cliente.nome}


@app.put("/api/clientes/{cliente_id}", tags=["Clientes"])
async def api_atualizar_cliente(cliente_id: int, cliente: ClienteIn, user=Depends(get_user)):
    email = _email_cliente_livre(cliente.email)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE clientes SET nome=?,telefone=?,email=?,cep=?,rua=?,numero=?,"
            "bairro=?,cidade=?,estado=? WHERE id=?",
            (cliente.nome, cliente.telefone, email, cliente.cep,
             cliente.rua, cliente.numero, cliente.bairro, cliente.cidade,
             cliente.estado, cliente_id)
        )
        conn.commit()
    return {"ok": True}


# ─── ORÇAMENTOS / OS ──────────────────────────────────────────────────────────
@app.get("/api/orcamentos", tags=["Orçamentos"])
async def api_listar_orcamentos(status: Optional[str] = None, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo WHERE status=? ORDER BY id DESC",
                (status,)
            )
        else:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo ORDER BY id DESC"
            )
        rows = cur.fetchall()
    keys = ["id","cliente","equipamento","defeito","valor_total","sinal","saldo","status","data"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/orcamentos/{orcamento_id}", tags=["Orçamentos"])
async def api_get_orcamento(orcamento_id: int, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orcamentos_aguardo WHERE id=?", (orcamento_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")
    keys = ["id","cliente","equipamento","defeito","valor_total","sinal","saldo",
            "status","data","itens_detalhes","dados_adicionais"]
    return dict(zip(keys, row))


@app.put("/api/orcamentos/{orcamento_id}/status", tags=["Orçamentos"])
async def api_atualizar_status(orcamento_id: int, body: OrcamentoStatusIn, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE orcamentos_aguardo SET status=? WHERE id=?",
            (body.status, orcamento_id)
        )
        conn.commit()
    return {"ok": True}


# ─── FINANCEIRO ───────────────────────────────────────────────────────────────
@app.get("/api/financeiro", tags=["Financeiro"])
async def api_listar_financeiro(
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    user=Depends(get_user)
):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,data,descricao,tipo,valor,categoria,metodo_pagamento "
            "FROM fluxo_caixa ORDER BY id DESC LIMIT 500"
        )
        rows = cur.fetchall()
    keys = ["id","data","descricao","tipo","valor","categoria","metodo_pagamento"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/financeiro/saldo", tags=["Financeiro"])
async def api_saldo(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(saldo),0) FROM orcamentos_aguardo "
            "WHERE status NOT IN ('FINALIZADO','CANCELADO','REPROVADO')"
        )
        a_receber = cur.fetchone()[0]
    return {"saldo": round(float(saldo or 0), 2), "a_receber": round(float(a_receber or 0), 2)}


@app.post("/api/financeiro", status_code=201, tags=["Financeiro"])
async def api_lancar(lancamento: LancamentoIn, user=Depends(get_user)):
    data = lancamento.data or datetime.now().strftime("%d/%m/%Y")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fluxo_caixa (data,descricao,tipo,valor,categoria,metodo_pagamento) "
            "VALUES (?,?,?,?,?,?)",
            (data, lancamento.descricao, lancamento.tipo.upper(), lancamento.valor,
             lancamento.categoria, lancamento.metodo_pagamento)
        )
        conn.commit()
        return {"id": cur.lastrowid}


# ─── PRODUTOS ─────────────────────────────────────────────────────────────────
@app.get("/api/produtos", tags=["Produtos"])
async def api_listar_produtos(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id,nome,preco_custo,preco_venda,estoque FROM produtos ORDER BY nome")
        rows = cur.fetchall()
    keys = ["id","nome","preco_custo","preco_venda","estoque"]
    return [dict(zip(keys, r)) for r in rows]


@app.post("/api/produtos", status_code=201, tags=["Produtos"])
async def api_criar_produto(produto: ProdutoIn, user=Depends(get_admin)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO produtos (nome,preco_custo,preco_venda,estoque) VALUES (?,?,?,?)",
            (produto.nome, produto.preco_custo, produto.preco_venda, produto.estoque)
        )
        conn.commit()
        return {"id": cur.lastrowid}


# ─── DADOS DA OFICINA ──────────────────────────────────────────────────────────
@app.get("/api/dados-oficina", tags=["Sistema"])
async def api_dados_oficina(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT nome_oficina,endereco_oficina,telefone_oficina,chave_pix "
            "FROM dados_oficina WHERE id=1"
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"nome": row[0], "endereco": row[1], "telefone": row[2], "pix": row[3]}


# ─── DASHBOARD STATS ──────────────────────────────────────────────────────────
@app.get("/api/dashboard", tags=["Sistema"])
async def api_dashboard(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(COALESCE(status,'')) IN ('AGUARDANDO','AGUARDANDO ORCAMENTO','AGUARDANDO ORÇAMENTO')")
        os_aguardando = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='EM ANDAMENTO'")
        os_andamento = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='FINALIZADO'")
        os_finalizadas = cur.fetchone()[0]
    return {
        "total_clientes": total_clientes,
        "os_aguardando": os_aguardando,
        "os_andamento": os_andamento,
        "os_finalizadas": os_finalizadas,
        "saldo": round(saldo, 2),
        "versao": APP_VERSION,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INTERFACE WEB (mobile / navegador)
# ═══════════════════════════════════════════════════════════════════════════════

def _redir_login():
    return RedirectResponse("/web/login", status_code=302)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    if _checar_cookie(request):
        return RedirectResponse("/web/dashboard")
    return RedirectResponse("/web/login")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def pwa_manifest():
    manifest_path = os.path.join(STATIC_DIR, "manifest.webmanifest")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifesto PWA não encontrado.")


@app.get("/sw.js", include_in_schema=False)
async def pwa_service_worker():
    sw_path = os.path.join(STATIC_DIR, "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(sw_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Service Worker não encontrado.")


@app.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_get(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erro": "", "versao": APP_VERSION})


@app.get("/web/licenca-bloqueada", response_class=HTMLResponse, include_in_schema=False)
async def web_licenca_bloqueada(request: Request):
    from config import obter_status_acesso_centralizado

    status_licenca = obter_status_acesso_centralizado()
    return templates.TemplateResponse(
        request,
        "licenca_bloqueada.html",
        {"versao": APP_VERSION, "mensagem": str(status_licenca.get("mensagem") or "").strip()},
    )


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def web_app_mobile(request: Request):
    return templates.TemplateResponse(request, "app_celular.html", {})


@app.post("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_post(
    request: Request,
    usuario: str = Form(...),
    senha: str = Form(...),
):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
            (usuario.strip(),)
        )
        row = cur.fetchone()
    if not row or not verify_password(senha, str(row[0] or "")):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "Usuário ou senha incorretos.", "versao": APP_VERSION}
        )
    role = str(row[1] or "OPERADOR")
    token = _criar_token(usuario.strip(), role)
    response = RedirectResponse("/web/dashboard", status_code=302)
    response.set_cookie(
        "ofp_token", token,
        max_age=JWT_EXPIRE_HORAS * 3600,
        httponly=True,
        samesite="lax"
    )
    return response


@app.get("/web/logout", include_in_schema=False)
async def web_logout():
    resp = RedirectResponse("/web/login", status_code=302)
    resp.delete_cookie("ofp_token")
    return resp


@app.get("/web/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def web_dashboard(request: Request):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(COALESCE(status,'')) IN ('AGUARDANDO','AGUARDANDO ORCAMENTO','AGUARDANDO ORÇAMENTO')")
        os_abertas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='EM ANDAMENTO'")
        os_andamento = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT nome_oficina FROM dados_oficina WHERE id=1"
        )
        row_oficina = cur.fetchone()
        nome_oficina = row_oficina[0] if row_oficina else "Oficina de Pesca"
    return templates.TemplateResponse(request, "dashboard.html", {
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "nome_oficina": nome_oficina,
        "total_clientes": total_clientes,
        "os_abertas": os_abertas,
        "os_andamento": os_andamento,
        "saldo": f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "versao": APP_VERSION,
    })


@app.get("/web/clientes", response_class=HTMLResponse, include_in_schema=False)
async def web_clientes(request: Request, busca: str = ""):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        if busca:
            cur.execute(
                "SELECT id,nome,telefone,email,cidade,estado FROM clientes "
                "WHERE nome LIKE ? OR telefone LIKE ? OR cidade LIKE ? ORDER BY nome",
                (f"%{busca}%", f"%{busca}%", f"%{busca}%")
            )
        else:
            cur.execute(
                "SELECT id,nome,telefone,email,cidade,estado FROM clientes ORDER BY nome"
            )
        clientes = cur.fetchall()
    return templates.TemplateResponse(request, "clientes.html", {
        "clientes": clientes,
        "busca": busca,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "versao": APP_VERSION,
    })


@app.get("/web/os", response_class=HTMLResponse, include_in_schema=False)
async def web_os(request: Request, status_filtro: str = ""):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        if status_filtro:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo WHERE status=? ORDER BY id DESC",
                (status_filtro,)
            )
        else:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo ORDER BY id DESC LIMIT 200"
            )
        orcamentos = cur.fetchall()
    return templates.TemplateResponse(request, "os.html", {
        "orcamentos": orcamentos,
        "status_filtro": status_filtro,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "versao": APP_VERSION,
    })


@app.get("/web/financeiro", response_class=HTMLResponse, include_in_schema=False)
async def web_financeiro(request: Request):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,data,descricao,tipo,valor,categoria,metodo_pagamento "
            "FROM fluxo_caixa ORDER BY id DESC LIMIT 200"
        )
        lancamentos = cur.fetchall()
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa WHERE tipo='ENTRADA'"
        )
        total_entradas = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(valor),0) FROM fluxo_caixa WHERE tipo='SAIDA'"
        )
        total_saidas = float(cur.fetchone()[0] or 0)

    def fmt(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return templates.TemplateResponse(request, "financeiro.html", {
        "lancamentos": lancamentos,
        "saldo": fmt(saldo),
        "total_entradas": fmt(total_entradas),
        "total_saidas": fmt(total_saidas),
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "versao": APP_VERSION,
    })


# ─── STARTUP ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    inicializar_banco()
    host = _SERVER_RUNTIME_HOST
    porta = _SERVER_RUNTIME_PORT
    logger.info("Servidor Oficina de Pesca v%s iniciado em %s:%s", APP_VERSION, host, porta)
    _registrar_servico_zeroconf(host, porta)
    _iniciar_discovery_udp(porta)


@app.on_event("shutdown")
async def on_shutdown():
    _encerrar_discovery_udp()
    _encerrar_servico_zeroconf()


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor Oficina de Pesca")
    parser.add_argument(
        "--host", default=_CFG.get("servidor", "host", fallback="0.0.0.0"),
        help="Endereço de escuta (padrão: 0.0.0.0 = todas as interfaces)"
    )
    parser.add_argument(
        "--porta", type=int,
        default=_CFG.getint("servidor", "porta", fallback=8000),
        help="Porta TCP (padrão: 8000)"
    )
    args = parser.parse_args()
    _SERVER_RUNTIME_HOST = args.host
    _SERVER_RUNTIME_PORT = args.porta

    import socket
    try:
        ip_local = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip_local = "SEU_IP"

    print("=" * 60)
    print(f"  🐟  Servidor Oficina de Pesca  v{APP_VERSION}")
    print("=" * 60)
    print(f"  🖥️  Acesso local (este PC):   http://localhost:{args.porta}")
    print(f"  🌐  Acesso na rede (outros):  http://{ip_local}:{args.porta}")
    print(f"  📱  Celular/tablet:            http://{ip_local}:{args.porta}")
    print(f"  📖  Documentação da API:       http://localhost:{args.porta}/api/docs")
    print("=" * 60)
    print("  Pressione Ctrl+C para encerrar.")
    print()

    uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
#!/usr/bin/env python3
"""
servidor.py — Servidor multi-usuário da Oficina de Pesca

Permite acesso simultâneo de:
  - Múltiplos PCs na rede local (LAN)
  - Celular / tablet via navegador
  - Qualquer dispositivo com acesso à internet

Como iniciar:
    python servidor.py
    python servidor.py --host 0.0.0.0 --porta 8000

Acesso pela rede local:
    Desktop: configure config.cfg → servidor_url = http://IP_DO_SERVIDOR:8000
    Celular:  abra o navegador em   http://IP_DO_SERVIDOR:8000
"""

import os
import sys
import json
import re
import base64
import hmac
import argparse
import socket
from datetime import datetime, timedelta, timezone
from typing import Optional

import uvicorn
from fastapi import (
    FastAPI, Depends, HTTPException, Request, Form,
    status as http_status,
)
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel

try:
    from zeroconf import ServiceInfo, Zeroconf
except Exception:
    ServiceInfo = None
    Zeroconf = None

# Importa funções do sistema existente
# Adaptar caminho se necessário
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    get_db_connection,
    hash_password,
    verify_password,
    validate_password,
    get_logger,
    inicializar_banco,
    APP_VERSION,
    _CFG,
)

logger = get_logger("servidor")
_ZEROCONF_INSTANCE = None
_ZEROCONF_SERVICE_INFO = None

# ─── CONFIGURAÇÃO JWT ────────────────────────────────────────────────────────
JWT_SECRET = os.environ.get(
    "OFP_JWT_SECRET",
    _CFG.get("servidor", "jwt_secret", fallback="OFP-JWT-ALTERAR-EM-PRODUCAO")
)
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HORAS = 8

# ─── APP ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Oficina de Pesca",
    version=APP_VERSION,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates HTML (interface web/mobile)
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["t"] = t

# Arquivos estáticos (CSS/JS)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token", auto_error=False)


def _detectar_ip_lan() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = str(sock.getsockname()[0] or "").strip()
        finally:
            sock.close()
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and ip != "127.0.0.1":
            return ip
    except Exception:
        pass
    return "127.0.0.1"


def _registrar_servico_zeroconf(porta: int) -> None:
    global _ZEROCONF_INSTANCE, _ZEROCONF_SERVICE_INFO
    if not Zeroconf or not ServiceInfo:
        logger.info("Zeroconf indisponível; anúncio LAN não iniciado.")
        return

    ip_lan = _detectar_ip_lan()
    if ip_lan == "127.0.0.1":
        logger.info("IP LAN não detectado; anúncio Zeroconf ignorado.")
        return

    try:
        nome_host = re.sub(r"[^a-zA-Z0-9-]+", "-", socket.gethostname()).strip("-") or "oficina-pesca"
        service_type = "_oficinapesca._tcp.local."
        service_name = f"Oficina de Pesca - {nome_host}.{service_type}"
        props = {
            b"app": b"oficina_pesca",
            b"version": str(APP_VERSION).encode("utf-8"),
            b"login_path": b"/web/login",
            b"app_path": b"/app",
        }
        info = ServiceInfo(
            type_=service_type,
            name=service_name,
            addresses=[socket.inet_aton(ip_lan)],
            port=int(porta),
            properties=props,
            server=f"{nome_host}.local.",
        )
        _ZEROCONF_INSTANCE = Zeroconf()
        _ZEROCONF_SERVICE_INFO = info
        _ZEROCONF_INSTANCE.register_service(info)
        logger.info("Serviço Zeroconf anunciado em %s:%s", ip_lan, porta)
    except Exception as e:
        logger.info("Falha ao anunciar serviço Zeroconf: %s", e)


def _encerrar_servico_zeroconf() -> None:
    global _ZEROCONF_INSTANCE, _ZEROCONF_SERVICE_INFO
    try:
        if _ZEROCONF_INSTANCE and _ZEROCONF_SERVICE_INFO:
            _ZEROCONF_INSTANCE.unregister_service(_ZEROCONF_SERVICE_INFO)
    except Exception:
        pass
    try:
        if _ZEROCONF_INSTANCE:
            _ZEROCONF_INSTANCE.close()
    except Exception:
        pass
    _ZEROCONF_INSTANCE = None
    _ZEROCONF_SERVICE_INFO = None


# ─── MODELOS ─────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    usuario: str
    role: str


class ClienteIn(BaseModel):
    nome: str
    telefone: Optional[str] = ""
    email: Optional[str] = ""
    cep: Optional[str] = ""
    rua: Optional[str] = ""
    numero: Optional[str] = ""
    bairro: Optional[str] = ""
    cidade: Optional[str] = ""
    estado: Optional[str] = ""


class OrcamentoStatusIn(BaseModel):
    status: str


class LancamentoIn(BaseModel):
    descricao: str
    tipo: str  # ENTRADA | SAIDA
    valor: float
    categoria: Optional[str] = ""
    metodo_pagamento: Optional[str] = ""
    data: Optional[str] = ""


class ProdutoIn(BaseModel):
    nome: str
    preco_custo: float = 0.0
    preco_venda: float = 0.0
    estoque: int = 0


class CloudBackupIn(BaseModel):
    email_cliente: str
    arquivo_nome: str
    conteudo_b64: str
    origem: Optional[str] = "desktop_admin"
    versao_app: Optional[str] = ""


# ─── HELPERS AUTH ─────────────────────────────────────────────────────────────
def _criar_token(usuario: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HORAS)
    payload = {"sub": usuario, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decodificar_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido ou expirado.")


def _usuario_do_request(request: Request, bearer: str) -> dict:
    """Aceita Bearer token (API) ou cookie ofp_token (browser)."""
    if bearer:
        try:
            return _decodificar_token(bearer)
        except HTTPException:
            pass
    cookie = request.cookies.get("ofp_token", "")
    if cookie:
        try:
            return _decodificar_token(cookie)
        except HTTPException:
            pass
    raise HTTPException(status_code=401, detail="Não autenticado.")


async def get_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    return _usuario_do_request(request, token or "")


async def get_admin(
    request: Request,
    token: str = Depends(oauth2_scheme),
) -> dict:
    payload = _usuario_do_request(request, token or "")
    if str(payload.get("role", "")).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN.")
    return payload


# ─── MIDDLEWARE: redireciona /web para login se sem cookie ───────────────────
def _checar_cookie(request: Request) -> Optional[dict]:
    cookie = request.cookies.get("ofp_token", "")
    if not cookie:
        return None
    try:
        return _decodificar_token(cookie)
    except HTTPException:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# API ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── AUTH ────────────────────────────────────────────────────────────────────
@app.post("/api/token", response_model=Token, tags=["Auth"])
async def api_login(form_data: OAuth2PasswordRequestForm = Depends()):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
            (form_data.username.strip(),)
        )
        row = cur.fetchone()
    if not row or not verify_password(form_data.password, str(row[0] or "")):
        raise HTTPException(status_code=401, detail="Usuário ou senha incorretos.")
    role = str(row[1] or "OPERADOR")
    token = _criar_token(form_data.username.strip(), role)
    return Token(access_token=token, token_type="bearer",
                 usuario=form_data.username.strip(), role=role)


# ─── VERSÃO ───────────────────────────────────────────────────────────────────
@app.get("/api/versao", tags=["Sistema"])
async def api_versao():
    """Retorna informações da versão atual do servidor.
    Configure url_check no config.cfg dos clientes apontando para este endpoint."""
    versao_file = os.path.join(BASE_DIR, "version.json")
    if not os.path.exists(versao_file):
        versao_file = os.path.join(BASE_DIR, "versao.json")
    if os.path.exists(versao_file):
        with open(versao_file, encoding="utf-8") as f:
            return json.load(f)
    return {"versao": APP_VERSION, "novidades": ""}


@app.get("/version.json", tags=["Sistema"], include_in_schema=False)
async def version_manifest():
    return await api_versao()


@app.get("/api/discovery", tags=["Sistema"])
async def api_discovery():
    porta = _CFG.getint("servidor", "porta", fallback=8000)
    ip_lan = _detectar_ip_lan()
    return {
        "ok": True,
        "app": "oficina_pesca",
        "version": APP_VERSION,
        "host": ip_lan,
        "port": porta,
        "login_url": f"http://{ip_lan}:{porta}/web/login",
        "app_url": f"http://{ip_lan}:{porta}/app",
    }


@app.get("/api/firebase-config", tags=["Sistema"])
async def api_firebase_config():
    """Retorna configuração pública do Firebase usada no app mobile/WebView."""
    try:
        from config import obter_firebase_web_config  # Import local para evitar ciclo.

        cfg = obter_firebase_web_config()
        return {
            "ok": True,
            "config": cfg,
            "syncChannel": str(cfg.get("syncChannel") or os.environ.get("OFP_FIREBASE_SYNC_CHANNEL", "global") or "global"),
        }
    except Exception as e:
        return {"ok": False, "erro": str(e), "config": {}}


@app.post("/api/cloud-backup", tags=["Backup"])
async def api_cloud_backup(
    request: Request,
    body: CloudBackupIn,
    token: str = Depends(oauth2_scheme),
):
    """Recebe backup do desktop e grava no repositório de nuvem por e-mail do cliente."""
    actor = "SISTEMA"
    key_cfg = _CFG.get("cloud_backup", "api_key", fallback="").strip()
    key_req = request.headers.get("X-OFP-Cloud-Key", "").strip()

    autorizado = False
    if key_cfg and key_req and hmac.compare_digest(key_cfg, key_req):
        autorizado = True
        actor = "AUTO_SYNC"

    if not autorizado:
        payload = _usuario_do_request(request, token or "")
        if str(payload.get("role", "")).upper() != "ADMIN":
            raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN ou chave técnica.")
        actor = str(payload.get("sub", "ADMIN"))

    email = str(body.email_cliente or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="E-mail de cliente inválido.")

    nome_arquivo = os.path.basename(str(body.arquivo_nome or "backup.db")).strip()
    if not nome_arquivo.lower().endswith(".db"):
        nome_arquivo += ".db"

    try:
        conteudo = base64.b64decode(str(body.conteudo_b64 or "").encode("ascii"), validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="Conteúdo de backup inválido (base64).")

    if not conteudo:
        raise HTTPException(status_code=400, detail="Backup vazio.")
    if len(conteudo) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Backup excede o limite de 50 MB.")

    cliente_dir = re.sub(r"[^a-z0-9._-]", "_", email)
    destino_dir = os.path.join(BASE_DIR, "cloud_backups", cliente_dir)
    os.makedirs(destino_dir, exist_ok=True)

    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_final = f"{carimbo}_{nome_arquivo}"
    destino = os.path.join(destino_dir, nome_final)

    with open(destino, "wb") as f:
        f.write(conteudo)

    logger.info(
        "Backup nuvem criado por=%s para cliente=%s arquivo=%s origem=%s versao=%s",
        actor,
        email,
        nome_final,
        str(body.origem or ""),
        str(body.versao_app or ""),
    )
    return {"ok": True, "arquivo": nome_final, "email_cliente": email}


@app.get("/api/cloud-backup/latest", tags=["Backup"])
async def api_get_latest_backup(
    request: Request,
    email_cliente: str,
    token: str = Depends(oauth2_scheme),
):
    """Retorna o arquivo de banco de dados mais recente para o e-mail informado."""
    payload = _usuario_do_request(request, token or "")
    if str(payload.get("role", "")).upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="Acesso restrito a ADMIN.")

    email = str(email_cliente or "").strip().lower()
    cliente_dir = re.sub(r"[^a-z0-9._-]", "_", email)
    origem_dir = os.path.join(BASE_DIR, "cloud_backups", cliente_dir)

    if not os.path.exists(origem_dir):
        raise HTTPException(status_code=404, detail="Nenhum backup encontrado para este e-mail.")

    import glob
    arquivos = glob.glob(os.path.join(origem_dir, "*.db"))
    if not arquivos:
        raise HTTPException(status_code=404, detail="Nenhum arquivo .db encontrado.")

    # Pega o arquivo mais recente pela data de modificação
    mais_recente = max(arquivos, key=os.path.getmtime)
    
    # Opcional: Retornar o conteúdo em base64 ou direto como arquivo
    with open(mais_recente, "rb") as f:
        conteudo = f.read()

    logger.info("PC baixou backup mais recente para cliente=%s arquivo=%s", email, os.path.basename(mais_recente))
    
    return {
        "ok": True,
        "arquivo_nome": os.path.basename(mais_recente),
        "conteudo_b64": base64.b64encode(conteudo).decode("ascii")
    }


# ─── CLIENTES ─────────────────────────────────────────────────────────────────
@app.get("/api/clientes", tags=["Clientes"])
async def api_listar_clientes(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, nome, telefone, email, cidade, estado, data_cadastro "
            "FROM clientes ORDER BY nome"
        )
        rows = cur.fetchall()
    keys = ["id", "nome", "telefone", "email", "cidade", "estado", "data_cadastro"]
    lista = []
    for r in rows:
        item = dict(zip(keys, r))
        item["email"] = _email_cliente_livre(item.get("email"))
        lista.append(item)
    return lista


@app.get("/api/clientes/{cliente_id}", tags=["Clientes"])
async def api_get_cliente(cliente_id: int, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM clientes WHERE id=?", (cliente_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado.")
    keys = ["id","nome","telefone","email","cep","rua","numero","bairro","cidade","estado","data_cadastro"]
    data = dict(zip(keys, row))
    data["email"] = _email_cliente_livre(data.get("email"))
    return data


@app.post("/api/clientes", status_code=201, tags=["Clientes"])
async def api_criar_cliente(cliente: ClienteIn, user=Depends(get_user)):
    now = datetime.now().strftime("%d/%m/%Y")
    email = _email_cliente_livre(cliente.email)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clientes "
            "(nome,telefone,email,cep,rua,numero,bairro,cidade,estado,data_cadastro) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (cliente.nome, cliente.telefone, email, cliente.cep,
             cliente.rua, cliente.numero, cliente.bairro, cliente.cidade,
             cliente.estado, now)
        )
        conn.commit()
        return {"id": cur.lastrowid, "nome": cliente.nome}


@app.put("/api/clientes/{cliente_id}", tags=["Clientes"])
async def api_atualizar_cliente(cliente_id: int, cliente: ClienteIn, user=Depends(get_user)):
    email = _email_cliente_livre(cliente.email)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE clientes SET nome=?,telefone=?,email=?,cep=?,rua=?,numero=?,"
            "bairro=?,cidade=?,estado=? WHERE id=?",
            (cliente.nome, cliente.telefone, email, cliente.cep,
             cliente.rua, cliente.numero, cliente.bairro, cliente.cidade,
             cliente.estado, cliente_id)
        )
        conn.commit()
    return {"ok": True}


# ─── ORÇAMENTOS / OS ──────────────────────────────────────────────────────────
@app.get("/api/orcamentos", tags=["Orçamentos"])
async def api_listar_orcamentos(status: Optional[str] = None, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        if status:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo WHERE status=? ORDER BY id DESC",
                (status,)
            )
        else:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo ORDER BY id DESC"
            )
        rows = cur.fetchall()
    keys = ["id","cliente","equipamento","defeito","valor_total","sinal","saldo","status","data"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/orcamentos/{orcamento_id}", tags=["Orçamentos"])
async def api_get_orcamento(orcamento_id: int, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orcamentos_aguardo WHERE id=?", (orcamento_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Orçamento não encontrado.")
    keys = ["id","cliente","equipamento","defeito","valor_total","sinal","saldo",
            "status","data","itens_detalhes","dados_adicionais"]
    return dict(zip(keys, row))


@app.put("/api/orcamentos/{orcamento_id}/status", tags=["Orçamentos"])
async def api_atualizar_status(orcamento_id: int, body: OrcamentoStatusIn, user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE orcamentos_aguardo SET status=? WHERE id=?",
            (body.status, orcamento_id)
        )
        conn.commit()
    return {"ok": True}


# ─── FINANCEIRO ───────────────────────────────────────────────────────────────
@app.get("/api/financeiro", tags=["Financeiro"])
async def api_listar_financeiro(
    data_inicio: Optional[str] = None,
    data_fim: Optional[str] = None,
    user=Depends(get_user)
):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,data,descricao,tipo,valor,categoria,metodo_pagamento "
            "FROM fluxo_caixa ORDER BY id DESC LIMIT 500"
        )
        rows = cur.fetchall()
    keys = ["id","data","descricao","tipo","valor","categoria","metodo_pagamento"]
    return [dict(zip(keys, r)) for r in rows]


@app.get("/api/financeiro/saldo", tags=["Financeiro"])
async def api_saldo(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(saldo),0) FROM orcamentos_aguardo "
            "WHERE status NOT IN ('FINALIZADO','CANCELADO','REPROVADO')"
        )
        a_receber = cur.fetchone()[0]
    return {"saldo": round(float(saldo or 0), 2), "a_receber": round(float(a_receber or 0), 2)}


@app.post("/api/financeiro", status_code=201, tags=["Financeiro"])
async def api_lancar(lancamento: LancamentoIn, user=Depends(get_user)):
    data = lancamento.data or datetime.now().strftime("%d/%m/%Y")
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO fluxo_caixa (data,descricao,tipo,valor,categoria,metodo_pagamento) "
            "VALUES (?,?,?,?,?,?)",
            (data, lancamento.descricao, lancamento.tipo.upper(), lancamento.valor,
             lancamento.categoria, lancamento.metodo_pagamento)
        )
        conn.commit()
        return {"id": cur.lastrowid}


# ─── PRODUTOS ─────────────────────────────────────────────────────────────────
@app.get("/api/produtos", tags=["Produtos"])
async def api_listar_produtos(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id,nome,preco_custo,preco_venda,estoque FROM produtos ORDER BY nome")
        rows = cur.fetchall()
    keys = ["id","nome","preco_custo","preco_venda","estoque"]
    return [dict(zip(keys, r)) for r in rows]


@app.post("/api/produtos", status_code=201, tags=["Produtos"])
async def api_criar_produto(produto: ProdutoIn, user=Depends(get_admin)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO produtos (nome,preco_custo,preco_venda,estoque) VALUES (?,?,?,?)",
            (produto.nome, produto.preco_custo, produto.preco_venda, produto.estoque)
        )
        conn.commit()
        return {"id": cur.lastrowid}


# ─── DADOS DA OFICINA ──────────────────────────────────────────────────────────
@app.get("/api/dados-oficina", tags=["Sistema"])
async def api_dados_oficina(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT nome_oficina,endereco_oficina,telefone_oficina,chave_pix "
            "FROM dados_oficina WHERE id=1"
        )
        row = cur.fetchone()
    if not row:
        return {}
    return {"nome": row[0], "endereco": row[1], "telefone": row[2], "pix": row[3]}


# ─── DASHBOARD STATS ──────────────────────────────────────────────────────────
@app.get("/api/dashboard", tags=["Sistema"])
async def api_dashboard(user=Depends(get_user)):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(COALESCE(status,'')) IN ('AGUARDANDO','AGUARDANDO ORCAMENTO','AGUARDANDO ORÇAMENTO')")
        os_aguardando = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='EM ANDAMENTO'")
        os_andamento = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='FINALIZADO'")
        os_finalizadas = cur.fetchone()[0]
    return {
        "total_clientes": total_clientes,
        "os_aguardando": os_aguardando,
        "os_andamento": os_andamento,
        "os_finalizadas": os_finalizadas,
        "saldo": round(saldo, 2),
        "versao": APP_VERSION,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# INTERFACE WEB (mobile / navegador)
# ═══════════════════════════════════════════════════════════════════════════════

def _redir_login():
    return RedirectResponse("/web/login", status_code=302)


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root(request: Request):
    if _checar_cookie(request):
        return RedirectResponse("/web/dashboard")
    return RedirectResponse("/web/login")


@app.get("/manifest.webmanifest", include_in_schema=False)
async def pwa_manifest():
    manifest_path = os.path.join(STATIC_DIR, "manifest.webmanifest")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifesto PWA não encontrado.")


@app.get("/sw.js", include_in_schema=False)
async def pwa_service_worker():
    sw_path = os.path.join(STATIC_DIR, "sw.js")
    if os.path.exists(sw_path):
        return FileResponse(sw_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Service Worker não encontrado.")


@app.get("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_get(request: Request):
    return templates.TemplateResponse(request, "login.html", {"erro": "", "versao": APP_VERSION})


@app.get("/app", response_class=HTMLResponse, include_in_schema=False)
async def web_app_mobile(request: Request):
    return templates.TemplateResponse(request, "app_celular.html", {})


@app.post("/web/login", response_class=HTMLResponse, include_in_schema=False)
async def web_login_post(
    request: Request,
    usuario: str = Form(...),
    senha: str = Form(...),
):
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT senha, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
            (usuario.strip(),)
        )
        row = cur.fetchone()
    if not row or not verify_password(senha, str(row[0] or "")):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"erro": "Usuário ou senha incorretos.", "versao": APP_VERSION}
        )
    role = str(row[1] or "OPERADOR")
    token = _criar_token(usuario.strip(), role)
    response = RedirectResponse("/web/dashboard", status_code=302)
    response.set_cookie(
        "ofp_token", token,
        max_age=JWT_EXPIRE_HORAS * 3600,
        httponly=True,
        samesite="lax"
    )
    return response


@app.get("/web/logout", include_in_schema=False)
async def web_logout():
    resp = RedirectResponse("/web/login", status_code=302)
    resp.delete_cookie("ofp_token")
    return resp


@app.get("/web/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def web_dashboard(request: Request):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM clientes")
        total_clientes = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE UPPER(COALESCE(status,'')) IN ('AGUARDANDO','AGUARDANDO ORCAMENTO','AGUARDANDO ORÇAMENTO')")
        os_abertas = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM orcamentos_aguardo WHERE status='EM ANDAMENTO'")
        os_andamento = cur.fetchone()[0]
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT nome_oficina FROM dados_oficina WHERE id=1"
        )
        row_oficina = cur.fetchone()
        nome_oficina = row_oficina[0] if row_oficina else "Oficina de Pesca"
    return templates.TemplateResponse(request, "dashboard.html", {
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "nome_oficina": nome_oficina,
        "total_clientes": total_clientes,
        "os_abertas": os_abertas,
        "os_andamento": os_andamento,
        "saldo": f"R$ {saldo:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "versao": APP_VERSION,
    })


@app.get("/web/clientes", response_class=HTMLResponse, include_in_schema=False)
async def web_clientes(request: Request, busca: str = ""):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        if busca:
            cur.execute(
                "SELECT id,nome,telefone,email,cidade,estado FROM clientes "
                "WHERE nome LIKE ? OR telefone LIKE ? OR cidade LIKE ? ORDER BY nome",
                (f"%{busca}%", f"%{busca}%", f"%{busca}%")
            )
        else:
            cur.execute(
                "SELECT id,nome,telefone,email,cidade,estado FROM clientes ORDER BY nome"
            )
        clientes = cur.fetchall()
    return templates.TemplateResponse(request, "clientes.html", {
        "clientes": clientes,
        "busca": busca,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "versao": APP_VERSION,
    })


@app.get("/web/os", response_class=HTMLResponse, include_in_schema=False)
async def web_os(request: Request, status_filtro: str = ""):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        if status_filtro:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo WHERE status=? ORDER BY id DESC",
                (status_filtro,)
            )
        else:
            cur.execute(
                "SELECT id,cliente,equipamento,defeito,valor_total,sinal,saldo,status,data "
                "FROM orcamentos_aguardo ORDER BY id DESC LIMIT 200"
            )
        orcamentos = cur.fetchall()
    return templates.TemplateResponse(request, "os.html", {
        "orcamentos": orcamentos,
        "status_filtro": status_filtro,
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "versao": APP_VERSION,
    })


@app.get("/web/financeiro", response_class=HTMLResponse, include_in_schema=False)
async def web_financeiro(request: Request):
    payload = _checar_cookie(request)
    if not payload:
        return _redir_login()
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id,data,descricao,tipo,valor,categoria,metodo_pagamento "
            "FROM fluxo_caixa ORDER BY id DESC LIMIT 200"
        )
        lancamentos = cur.fetchall()
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa"
        )
        saldo = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(CASE WHEN tipo='ENTRADA' THEN valor ELSE -valor END),0) "
            "FROM fluxo_caixa WHERE tipo='ENTRADA'"
        )
        total_entradas = float(cur.fetchone()[0] or 0)
        cur.execute(
            "SELECT COALESCE(SUM(valor),0) FROM fluxo_caixa WHERE tipo='SAIDA'"
        )
        total_saidas = float(cur.fetchone()[0] or 0)

    def fmt(v):
        return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    return templates.TemplateResponse(request, "financeiro.html", {
        "lancamentos": lancamentos,
        "saldo": fmt(saldo),
        "total_entradas": fmt(total_entradas),
        "total_saidas": fmt(total_saidas),
        "usuario": payload.get("sub", ""),
        "role": payload.get("role", ""),
        "versao": APP_VERSION,
    })


# ─── STARTUP ──────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def on_startup():
    inicializar_banco()
    host = _CFG.get("servidor", "host", fallback="0.0.0.0")
    porta = _CFG.getint("servidor", "porta", fallback=8000)
    logger.info("Servidor Oficina de Pesca v%s iniciado em %s:%s", APP_VERSION, host, porta)
    _registrar_servico_zeroconf(porta)


@app.on_event("shutdown")
async def on_shutdown():
    _encerrar_servico_zeroconf()


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor Oficina de Pesca")
    parser.add_argument(
        "--host", default=_CFG.get("servidor", "host", fallback="0.0.0.0"),
        help="Endereço de escuta (padrão: 0.0.0.0 = todas as interfaces)"
    )
    parser.add_argument(
        "--porta", type=int,
        default=_CFG.getint("servidor", "porta", fallback=8000),
        help="Porta TCP (padrão: 8000)"
    )
    args = parser.parse_args()

    import socket
    try:
        ip_local = socket.gethostbyname(socket.gethostname())
    except Exception:
        ip_local = "SEU_IP"

    print("=" * 60)
    print(f"  🐟  Servidor Oficina de Pesca  v{APP_VERSION}")
    print("=" * 60)
    print(f"  🖥️  Acesso local (este PC):   http://localhost:{args.porta}")
    print(f"  🌐  Acesso na rede (outros):  http://{ip_local}:{args.porta}")
    print(f"  📱  Celular/tablet:            http://{ip_local}:{args.porta}")
    print(f"  📖  Documentação da API:       http://localhost:{args.porta}/api/docs")
    print("=" * 60)
    print("  Pressione Ctrl+C para encerrar.")
    print()

    uvicorn.run(app, host=args.host, port=args.porta, log_level="warning")
