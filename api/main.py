import os
import hmac
import re
import threading
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from passlib.exc import UnknownHashError
from pydantic import BaseModel

from infra.supabase_client import get_supabase_client_cached

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

app = FastAPI(title="Oficina Pesca API", version="0.1.0")
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------------------------------------------------------
# Keep-alive do Render (plano gratuito): a instância dorme após ~15 min sem
# tráfego. Uma thread em background faz ping periódico no próprio /health
# através da URL pública (RENDER_EXTERNAL_URL), mantendo a instância acordada.
# ---------------------------------------------------------------------------
KEEP_ALIVE_INTERVAL_SEG = max(60, int(os.getenv("RENDER_KEEP_ALIVE_INTERVAL_SEG", "600")))
KEEP_ALIVE_DISABLED = os.getenv("RENDER_KEEP_ALIVE_DISABLED", "").strip().lower() in {"1", "true", "yes"}


def _url_keep_alive() -> str:
    base = (os.getenv("RENDER_KEEP_ALIVE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    return f"{base}/health" if base else ""


def _executar_keep_alive(alvo: str) -> None:
    while True:
        try:
            with urllib.request.urlopen(alvo, timeout=15) as resposta:
                print(f"[keep-alive] ping {alvo} -> HTTP {resposta.status}")
        except Exception as exc:  # ping nunca deve derrubar a API
            print(f"[keep-alive] falha no ping {alvo}: {exc}")
        time.sleep(KEEP_ALIVE_INTERVAL_SEG)


@app.on_event("startup")
def _iniciar_keep_alive_render() -> None:
    if KEEP_ALIVE_DISABLED:
        print("[keep-alive] desativado por RENDER_KEEP_ALIVE_DISABLED.")
        return
    alvo = _url_keep_alive()
    if not alvo:
        # Fora do Render (ou URL não configurada): comportamento atual preservado.
        print("[keep-alive] RENDER_EXTERNAL_URL/RENDER_KEEP_ALIVE_URL ausente; keep-alive inativo.")
        return
    threading.Thread(
        target=_executar_keep_alive,
        args=(alvo,),
        name="render-keep-alive",
        daemon=True,
    ).start()
    print(f"[keep-alive] ping automático ativo ({KEEP_ALIVE_INTERVAL_SEG}s) -> {alvo}")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


def _exigir_secret_key() -> str:
    if not SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configuracao do servidor incompleta: JWT nao configurado.",
        )
    return SECRET_KEY


SEED_ADMIN_TOKEN = os.getenv("OFP_SEED_ADMIN_TOKEN", "").strip()


def _autorizar_seed_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> bool:
    """Protege o bootstrap administrativo com token forte via ambiente.

    - Endpoint desativado (403) quando OFP_SEED_ADMIN_TOKEN nao esta configurado;
    - exige Authorization: Bearer <token>; nunca aceita segredo em query string;
    - nunca registra credenciais em logs.
    """
    if not SEED_ADMIN_TOKEN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Endpoint de bootstrap indisponivel.")
    if credentials is None or not getattr(credentials, "credentials", ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token de bootstrap ausente.")
    if not hmac.compare_digest(str(credentials.credentials), SEED_ADMIN_TOKEN):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token de bootstrap invalido.")
    return True


class LoginPayload(BaseModel):
    email: str
    senha: str


class SeedUserPayload(BaseModel):
    nome: str = "Admin Teste"
    email: str = "admin@teste.local"
    senha: str = "123456"
    perfil: str = "admin"


class ClientePayload(BaseModel):
    nome: str
    cpf_cnpj: str | None = None
    telefone: str | None = None
    email: str | None = None
    endereco: str | None = None


class OrdemServicoPayload(BaseModel):
    numero: str | None = None
    cliente_id: str | None = None
    status: str = "aberta"
    valor_total: float = 0
    observacoes: str | None = None


class LicencaStatusEmailResponse(BaseModel):
    ok: bool
    ativa: bool
    mensagem: str
    cliente: str = ""
    tipo: str = ""
    plano: str = ""
    validade: str = ""
    data_geracao: str = ""


class TokenPayload(BaseModel):
    sub: str
    exp: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"sub": subject, "exp": expire.timestamp()}
    return jwt.encode(to_encode, _exigir_secret_key(), algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    try:
        payload = jwt.decode(credentials.credentials, _exigir_secret_key(), algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token inválido") from exc
    return payload


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> dict[str, Any]:
    payload = verify_token(credentials)
    return {"user_id": payload.get("sub"), "payload": payload}


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except UnknownHashError:
        return plain_password == hashed_password


def _interpretar_validade(valor: Any) -> tuple[str, bool, bool]:
    """Interpreta o campo data_expiracao de um registro de licenca.

    Retorna (validade_normalizada, eh_permanente, eh_datada_valida):
      - PERMANENTE é sempre considerada válida;
      - datas interpretáveis são válidas quando >= hoje;
      - vazias ou ilegíveis nunca são válidas.
    """
    validade = str(valor or "").strip()
    if not validade:
        return "", False, False
    if validade.upper() == "PERMANENTE":
        return "PERMANENTE", True, True
    try:
        data_expiracao = date.fromisoformat(validade[:10])
    except (TypeError, ValueError):
        return validade, False, False
    return validade, False, data_expiracao >= date.today()


def _selecionar_licenca_vigente(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Seleciona a licença vigente no histórico do e-mail.

    Regras (rows chegam ordenadas por id desc — mais recente primeiro):
      P1: PERMANENTE válida mais recente por ID;
      P2: entre as datadas válidas, a de maior data_expiracao
          (empate: permanece a de maior ID, por comparação estrita);
      P3: nenhuma válida -> retorna None (o chamador aplica o fallback atual).
    """
    for row in rows:
        _validade, eh_permanente, _valida = _interpretar_validade((row or {}).get("data_expiracao"))
        if eh_permanente:
            return row

    vigente: dict[str, Any] | None = None
    melhor_data: date | None = None
    for row in rows:
        validade, _eh_permanente, valida = _interpretar_validade((row or {}).get("data_expiracao"))
        if not valida:
            continue
        try:
            data_expiracao = date.fromisoformat(validade[:10])
        except (TypeError, ValueError):
            continue
        if melhor_data is None or data_expiracao > melhor_data:
            melhor_data = data_expiracao
            vigente = row
    return vigente


def _status_licenca_por_email(email: str) -> dict[str, Any]:
    email_norm = str(email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email_norm):
        return {"ok": False, "ativa": False, "mensagem": "E-mail invalido."}

    try:
        client = get_supabase_client_cached()
        response = (
            client.table("licencas_geradas")
            .select("id, data_expiracao, cliente, tipo, plano, data_geracao")
            .eq("email", email_norm)
            .order("id", desc=True)
            .limit(50)
            .execute()
        )
    except Exception as exc:
        return {
            "ok": False,
            "ativa": False,
            "mensagem": f"Falha ao consultar licenca por e-mail: {exc}",
        }

    rows = [row for row in (getattr(response, "data", None) or []) if isinstance(row, dict)]
    if not rows:
        return {"ok": True, "ativa": False, "mensagem": "Nenhuma licenca encontrada para este e-mail."}

    # Histórico recente do e-mail: elege a licença vigente (P1/P2) em vez de
    # considerar apenas o registro mais recente por ID. Sem licença válida,
    # mantém o fallback atual (linha mais recente por ID).
    row = _selecionar_licenca_vigente(rows) or rows[0]

    validade, eh_permanente, valida_dated = _interpretar_validade(row.get("data_expiracao"))
    ativa = True if eh_permanente else valida_dated

    # Defesa: nenhum registro TRIAL libera acesso (o TRIAL é local ao desktop e
    # nunca é publicado; licenças comerciais normais não contêm esse rótulo).
    tipo_upper = str(row.get("tipo") or "").strip().upper()
    plano_upper = str(row.get("plano") or "").strip().upper()
    if "TRIAL" in tipo_upper or "TRIAL" in plano_upper:
        ativa = False

    mensagem = "Licenca ativa." if ativa else f"Licenca expirada em {validade}." if validade else "Licenca inativa."
    return {
        "ok": True,
        "ativa": ativa,
        "mensagem": mensagem,
        "cliente": str(row.get("cliente") or "").strip(),
        "tipo": str(row.get("tipo") or "").strip(),
        "plano": str(row.get("plano") or "").strip(),
        "validade": validade,
        "data_geracao": str(row.get("data_geracao") or "").strip(),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "oficina-pesca-api"}


@app.get("/licencas/status-email", response_model=LicencaStatusEmailResponse)
def licenca_status_por_email(email: str) -> dict[str, Any]:
    return _status_licenca_por_email(email)


@app.get("/api/licencas/status-email", response_model=LicencaStatusEmailResponse)
def api_licenca_status_por_email(email: str) -> dict[str, Any]:
    return _status_licenca_por_email(email)


@app.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginPayload) -> dict[str, Any]:
    client = get_supabase_client_cached()
    response = client.table("usuarios").select("id, nome, email, perfil, senha_hash").eq("email", payload.email).limit(1).execute()
    rows = getattr(response, "data", None) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    user = rows[0]
    stored_hash = user.get("senha_hash") or ""
    if not verify_password(payload.senha, stored_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = create_access_token(user["id"])
    return {"access_token": token, "token_type": "bearer"}


@app.get("/clientes")
def list_clientes(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    response = client.table("clientes").select("id, nome, email, telefone").limit(10).execute()
    rows = getattr(response, "data", None) or []
    return {"ok": True, "clientes": rows, "user": user["user_id"]}


@app.post("/clientes", status_code=status.HTTP_201_CREATED)
def create_cliente(payload: ClientePayload, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    row = payload.model_dump()
    inserted = client.table("clientes").insert(row).execute()
    return {"ok": True, "cliente": getattr(inserted, "data", None), "user": user["user_id"]}


@app.put("/clientes/{cliente_id}")
def update_cliente(cliente_id: str, payload: ClientePayload, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    updated = client.table("clientes").update(payload.model_dump()).eq("id", cliente_id).execute()
    return {"ok": True, "cliente": getattr(updated, "data", None), "user": user["user_id"]}


@app.delete("/clientes/{cliente_id}")
def delete_cliente(cliente_id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    removed = client.table("clientes").delete().eq("id", cliente_id).execute()
    return {"ok": True, "cliente": getattr(removed, "data", None), "user": user["user_id"]}


@app.get("/ordens-servico")
def list_ordens(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    response = client.table("ordens_servico").select("id, numero, status, valor_total, cliente_id").limit(10).execute()
    rows = getattr(response, "data", None) or []
    return {"ok": True, "ordens_servico": rows, "user": user["user_id"]}


@app.post("/ordens-servico", status_code=status.HTTP_201_CREATED)
def create_ordem(payload: OrdemServicoPayload, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    inserted = client.table("ordens_servico").insert(payload.model_dump()).execute()
    return {"ok": True, "ordem_servico": getattr(inserted, "data", None), "user": user["user_id"]}


@app.put("/ordens-servico/{ordem_id}")
def update_ordem(ordem_id: str, payload: OrdemServicoPayload, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    updated = client.table("ordens_servico").update(payload.model_dump()).eq("id", ordem_id).execute()
    return {"ok": True, "ordem_servico": getattr(updated, "data", None), "user": user["user_id"]}


@app.delete("/ordens-servico/{ordem_id}")
def delete_ordem(ordem_id: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    removed = client.table("ordens_servico").delete().eq("id", ordem_id).execute()
    return {"ok": True, "ordem_servico": getattr(removed, "data", None), "user": user["user_id"]}


@app.post("/seed/admin")
def seed_admin(payload: SeedUserPayload, _bootstrap: bool = Depends(_autorizar_seed_admin)) -> dict[str, Any]:
    client = get_supabase_client_cached()
    existing = client.table("usuarios").select("id").eq("email", payload.email).limit(1).execute()
    if getattr(existing, "data", None):
        return {"ok": True, "message": "Usuário já existe", "email": payload.email}

    row = {
        "nome": payload.nome,
        "email": payload.email,
        "senha_hash": get_password_hash(payload.senha),
        "perfil": payload.perfil,
        "ativo": True,
    }
    inserted = client.table("usuarios").insert(row).execute()
    return {"ok": True, "message": "Usuário criado", "data": getattr(inserted, "data", None)}
