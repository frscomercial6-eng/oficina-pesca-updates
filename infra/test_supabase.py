import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from infra.supabase_client import get_supabase_client_cached


def main() -> None:
    print("[TESTE] Carregando variáveis de ambiente...")
    print(f"[TESTE] SUPABASE_URL={os.getenv('SUPABASE_URL', '')[:40]}...")
    print(f"[TESTE] SUPABASE_KEY={os.getenv('SUPABASE_KEY', '')[:20]}...")

    try:
        client = get_supabase_client_cached()
        print("[TESTE] Cliente Supabase criado com sucesso.")
        response = client.table("usuarios").select("id, nome, email").limit(1).execute()
        data = getattr(response, "data", None)
        print("[TESTE] Requisição executada com sucesso.")
        print(f"[TESTE] Dados={data if data is not None else []}")
    except Exception as exc:
        code = getattr(exc, "code", None)
        if code == "PGRST205":
            print("[TESTE] CONEXAO_OK: a API do Supabase respondeu, mas a tabela solicitada não existe no schema atual.")
            return
        print(f"[TESTE] ERRO: {exc}")
        raise


if __name__ == "__main__":
    main()
