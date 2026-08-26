import os
from datetime import datetime, timedelta, timezone
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

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))


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


class TokenPayload(BaseModel):
    sub: str
    exp: int


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> str:
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode = {"sub": subject, "exp": expire.timestamp()}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(credentials: HTTPAuthorizationCredentials | None) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token ausente")
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "oficina-pesca-api"}


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
def seed_admin(payload: SeedUserPayload) -> dict[str, Any]:
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
