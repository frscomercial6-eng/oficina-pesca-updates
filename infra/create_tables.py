import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from infra.supabase_client import get_supabase_client_cached

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency
    psycopg = None


def build_sql() -> list[str]:
    return [
        """
        create table if not exists public.usuarios (
            id uuid primary key default gen_random_uuid(),
            nome text not null,
            email text unique not null,
            senha_hash text,
            perfil text default 'usuario',
            ativo boolean default true,
            criado_em timestamptz default now()
        );
        """,
        """
        create table if not exists public.clientes (
            id uuid primary key default gen_random_uuid(),
            nome text not null,
            cpf_cnpj text,
            telefone text,
            email text,
            endereco text,
            ativo boolean default true,
            criado_em timestamptz default now()
        );
        """,
        """
        create table if not exists public.ordens_servico (
            id uuid primary key default gen_random_uuid(),
            numero text unique,
            cliente_id uuid references public.clientes(id) on delete set null,
            status text default 'aberta',
            valor_total numeric(12,2) default 0,
            observacoes text,
            criado_em timestamptz default now()
        );
        """,
        """
        create table if not exists public.produtos_servicos (
            id uuid primary key default gen_random_uuid(),
            nome text not null,
            tipo text default 'servico',
            valor numeric(12,2) default 0,
            ativo boolean default true,
            criado_em timestamptz default now()
        );
        """,
        """
        create table if not exists public.licencas_geradas (
            id bigserial primary key,
            chave text,
            data_expiracao text not null,
            chave_instalacao text default '',
            data_geracao timestamptz default now(),
            email text default '',
            cliente text default '',
            tipo text default '',
            plano text default ''
        );
        """,
    ]


def run_migration() -> dict[str, Any]:
    results: list[dict[str, Any]] = []

    database_url = os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL")
    if database_url and psycopg is not None:
        try:
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cur:
                    for statement in build_sql():
                        cur.execute(statement)
                        results.append({"statement": statement.strip().splitlines()[0], "ok": True})
            return {"ok": True, "results": results}
        except Exception as exc:
            return {"ok": False, "results": [{"statement": "database direct connection", "ok": False, "error": str(exc)}]}

    client = get_supabase_client_cached()
    for statement in build_sql():
        try:
            response = client.rpc("exec_sql", {"sql": statement}).execute()
            results.append({"statement": statement.strip().splitlines()[0], "ok": True, "response": getattr(response, "data", None)})
        except Exception as exc:
            results.append({"statement": statement.strip().splitlines()[0], "ok": False, "error": str(exc)})

    return {"ok": all(item["ok"] for item in results), "results": results}


if __name__ == "__main__":
    result = run_migration()
    print("[MIGRATION] Resultado:")
    for item in result["results"]:
        status = "OK" if item["ok"] else "ERRO"
        print(f"- {status}: {item['statement']}")
        if not item["ok"]:
            print(f"  {item['error']}")
    if result["ok"]:
        print("[MIGRATION] Tabelas provisionadas com sucesso.")
    else:
        print("[MIGRATION] Falha ao provisionar tabelas. Verifique permissões e credenciais de admin.")
