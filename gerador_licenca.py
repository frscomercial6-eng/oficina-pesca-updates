# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
from datetime import date, datetime, timedelta
from pathlib import Path

from config import LICENCA_SECRET, gerar_chave_licenca, gerar_hash_publico_licenca, get_db_connection, normalizar_chave_instalacao

# Usa exatamente o mesmo segredo ativo na aplicação em produção.

# ─── Tabela de planos ─────────────────────────────────────────────────────────
#  chave → (nome exibido, dias até expirar ou None, tipo lógico do plano)
DIAS_PROMOCIONAL = timedelta(days=90).days
PLANOS: dict[str, tuple[str, int | None, str]] = {
    "1": ("Promocional",        DIAS_PROMOCIONAL, "PROMOCIONAL"),
    "2": ("Mensal Padrão",      30,   "MENSAL"),
    "3": ("Trimestral",         90,   "TRIMESTRAL"),
    "4": ("Semestral",          180,  "SEMESTRAL"),
    "5": ("Anual",              365,  "ANUAL"),
    "6": ("VIP / Permanente",   None, "PERMANENTE"),
}

LOG_TXT = Path(__file__).parent / "licencas_geradas.txt"


# ─── Lógica de geração ────────────────────────────────────────────────────────

def _calcular_validade(dias: int | None) -> str:
    if dias is None:
        return "PERMANENTE"
    return (date.today() + timedelta(days=dias)).isoformat()


def _gerar_chave(hw: str, validade: str) -> str:
    """Delega ao mesmo gerador usado pela aplicação em produção."""
    dias_validade = None if validade == "PERMANENTE" else (date.fromisoformat(validade) - date.today()).days
    tipo_licenca = "PERMANENTE" if validade == "PERMANENTE" else ""
    return gerar_chave_licenca(
        cliente="",
        dias_validade=dias_validade,
        tipo_licenca=tipo_licenca,
        chave_instalacao=hw,
    )


# ─── Persistência ─────────────────────────────────────────────────────────────

def _salvar_txt(cliente: str, hw: str, plano_nome: str, validade: str, chave: str) -> None:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    linha = f"{agora} | {cliente} | {hw} | {plano_nome} | {validade} | {chave}\n"
    LOG_TXT.parent.mkdir(parents=True, exist_ok=True)
    with LOG_TXT.open("a", encoding="utf-8") as f:
        f.write(linha)


def _salvar_db(chave: str, validade: str, hw: str) -> None:
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
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
            cursor.execute("PRAGMA table_info(licencas_geradas)")
            cols = {row[1] for row in cursor.fetchall()}
            if "chave_instalacao" not in cols:
                cursor.execute(
                    "ALTER TABLE licencas_geradas ADD COLUMN chave_instalacao TEXT DEFAULT ''"
                )
            cursor.execute(
                "INSERT INTO licencas_geradas (chave, data_expiracao, chave_instalacao, data_geracao)"
                " VALUES (?, ?, ?, DATE('now'))",
                (chave, validade, hw),
            )
            conn.commit()
    except Exception as exc:
        print(f"[aviso] Banco de dados não gravado: {exc}")


# ─── Interface CLI ─────────────────────────────────────────────────────────────

def main() -> None:
    SEP = "=" * 54
    print(SEP)
    print("    GERADOR DE LICENÇA — OFICINA DE PESCA")
    print(SEP)

    # 1. Nome do cliente
    cliente = input("\nNome do cliente: ").strip().upper()
    if not cliente:
        print("ERRO: nome do cliente obrigatório.")
        return

    # 2. Hardware ID (campo 'hw' no payload — deve ser OFP-INST-XXXX da máquina do cliente)
    hw_raw = input("Hardware ID do cliente (OFP-INST-XXXXXXXXXXXXXXXXXXXXXXXX): ").strip()
    hw = normalizar_chave_instalacao(hw_raw)
    if not hw.startswith("OFP-INST-"):
        print("ERRO: o Hardware ID deve estar no formato OFP-INST-XXXXXXXXXXXXXXXXXXXXXXXX.")
        print("      Peça ao cliente o código exibido na tela de ativação do software.")
        return

    # 3. Plano
    print("\nPlanos disponíveis:")
    for k, (nome, dias, _) in PLANOS.items():
        expira = f"{dias} dias" if dias else "Sem expiração"
        print(f"  {k} - {nome}  ({expira})")
    opcao = input("\nEscolha o plano (1-6): ").strip()
    if opcao not in PLANOS:
        print("ERRO: escolha uma opção entre 1 e 6.")
        return

    plano_nome, dias, _ = PLANOS[opcao]
    validade = _calcular_validade(dias)

    # Gerar — hw entra no payload; cliente é só para log
    chave = _gerar_chave(hw, validade)
    hash_pub = gerar_hash_publico_licenca(chave)

    # Salvar
    _salvar_txt(cliente, hw, plano_nome, validade, chave)
    _salvar_db(chave, validade, hw)

    # Resultado
    print()
    print(SEP)
    print("  LICENÇA GERADA COM SUCESSO")
    print(SEP)
    print(f"  Cliente  : {cliente}")
    print(f"  HW ID    : {hw}")
    print(f"  Plano    : {plano_nome}")
    print(f"  Validade : {validade}")
    print(SEP)
    print()
    print(chave)
    print()
    print(f"HASH PÚBLICO (GitHost): {hash_pub}")
    print()
    print(f"Registrado em: {LOG_TXT}")
    print(SEP)


if __name__ == "__main__":
    main()
