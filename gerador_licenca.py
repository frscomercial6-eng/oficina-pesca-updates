# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta
from pathlib import Path

from config import (
    gerar_token_acesso,
    get_db_connection,
    publicar_token_acesso_drive,
    validar_email_basico,
)

TOKEN_VALIDADE_DIAS = 30

LOG_TXT = Path(__file__).parent / "licencas_geradas.txt"


# ─── Lógica de geração ────────────────────────────────────────────────────────

def _gerar_token_temporario(user_id: str, dias_validade: int = TOKEN_VALIDADE_DIAS) -> str:
    """Gera token temporário assinado para Desktop/APK sem expor chave mestre."""
    return gerar_token_acesso(user_id=user_id, dias_validade=dias_validade)


# ─── Persistência ─────────────────────────────────────────────────────────────

def _salvar_txt(cliente: str, user_id: str, validade: str, token: str) -> None:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    token_preview = f"{token[:24]}..." if token else ""
    linha = f"{agora} | {cliente} | {user_id} | {validade} | {token_preview}\n"
    LOG_TXT.parent.mkdir(parents=True, exist_ok=True)
    with LOG_TXT.open("a", encoding="utf-8") as f:
        f.write(linha)


def _salvar_db(token: str, validade: str, user_id: str) -> None:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS token_acesso_gerados (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    token            TEXT NOT NULL,
                    user_id          TEXT NOT NULL,
                    data_expiracao   TEXT NOT NULL,
                    origem           TEXT NOT NULL DEFAULT 'desktop_manual',
                    data_geracao     TEXT NOT NULL
                )
                """
            )
            cursor.execute("PRAGMA table_info(token_acesso_gerados)")
            cols = {row[1] for row in cursor.fetchall()}
            if "origem" not in cols:
                cursor.execute(
                    "ALTER TABLE token_acesso_gerados ADD COLUMN origem TEXT DEFAULT 'desktop_manual'"
                )
            cursor.execute(
                "INSERT INTO token_acesso_gerados (token, user_id, data_expiracao, origem, data_geracao)"
                " VALUES (?, ?, ?, 'desktop_manual', DATE('now'))",
                (token, user_id, validade),
            )
            conn.commit()
    except Exception as exc:
        print(f"[aviso] Banco de dados não gravado: {exc}")


# ─── Interface CLI ─────────────────────────────────────────────────────────────

def main() -> None:
    SEP = "=" * 54
    print(SEP)
    print("    GERADOR DE TOKEN DE ACESSO — OFICINA DE PESCA")
    print(SEP)
    print(f"Validade padrão: {TOKEN_VALIDADE_DIAS} dias")

    # 1. Nome do cliente
    cliente = input("\nNome do cliente: ").strip().upper()
    if not cliente:
        print("ERRO: nome do cliente obrigatório.")
        return

    # 2. User ID do token (e-mail usado no login Google do APK)
    user_id = input("E-mail do cliente (user_id do token): ").strip().lower()
    if not validar_email_basico(user_id):
        print("ERRO: informe um e-mail válido do cliente para vincular o token.")
        return

    validade = (date.today() + timedelta(days=TOKEN_VALIDADE_DIAS)).isoformat()
    token = _gerar_token_temporario(user_id=user_id, dias_validade=TOKEN_VALIDADE_DIAS)

    # Salvar
    _salvar_txt(cliente, user_id, validade, token)
    _salvar_db(token, validade, user_id)
    caminho_token = Path(__file__).parent / "acesso.token"
    caminho_token.write_text(token, encoding="utf-8")

    # Resultado
    print()
    print(SEP)
    print("  TOKEN DE ACESSO GERADO COM SUCESSO")
    print(SEP)
    print(f"  Cliente       : {cliente}")
    print(f"  User ID       : {user_id}")
    print(f"  Validade      : {validade}")
    print(f"  Arquivo token : {caminho_token}")
    print(SEP)
    print()
    print(token)
    print()
    print(f"Registrado em: {LOG_TXT}")

    try:
        publicar_drive = input("Publicar token no Google Drive agora? (s/N): ").strip().lower() == "s"
    except Exception:
        publicar_drive = False

    if publicar_drive:
        ok, msg = publicar_token_acesso_drive(user_id=user_id, dias_validade=TOKEN_VALIDADE_DIAS)
        print(msg if ok else f"[erro] {msg}")

    print(SEP)


if __name__ == "__main__":
    main()
