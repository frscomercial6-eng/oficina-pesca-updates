import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from supabase import create_client
except Exception:  # pragma: no cover - depende da instalação do pacote
    create_client = None


load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def _get_env_config() -> tuple[str, str]:
    return os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")


def get_supabase_client() -> Any:
    """Cria e retorna um cliente Supabase configurado a partir das variáveis de ambiente."""
    supabase_url, supabase_key = _get_env_config()
    if not supabase_url or not supabase_key:
        raise RuntimeError("Configure SUPABASE_URL e SUPABASE_KEY antes de usar o cliente Supabase.")
    if create_client is None:
        raise RuntimeError("O pacote 'supabase' não está instalado. Instale-o para usar a conexão.")
    return create_client(supabase_url, supabase_key)


supabase_client = None


def get_supabase_client_cached() -> Any:
    """Retorna uma instância reutilizada do cliente Supabase."""
    global supabase_client
    if supabase_client is None:
        supabase_client = get_supabase_client()
    return supabase_client
