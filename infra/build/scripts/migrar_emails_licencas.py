# -*- coding: utf-8 -*-
"""Vincula retroativamente e-mails de clientes as licencas antigas geradas pelo
Hub (tabela licencas_geradas no oficina.db) e ao arquivo licencas.json, para que
clientes ja existentes tambem consigam se autenticar no APK pelo novo fluxo de
identificacao por e-mail (/api/licencas/status-email).

Fontes de e-mail usadas, em ordem de prioridade:
  1) logs/hub_licencas_api.log - log historico do Hub (grava email por chave/hash
     desde que o endpoint /api/licencas/gerar/oficina foi criado).
  2) Mapa manual informado via --mapa (CSV com colunas: identificador,email).
     O identificador pode ser o nome do cliente, a chave completa ou o hash
     publico da licenca (qualquer um dos tres, comparado sem diferenciar
     maiusculas/minusculas).

Uso:
    python migrar_emails_licencas.py --mapa mapa_emails.csv
    python migrar_emails_licencas.py --mapa mapa_emails.csv --dry-run

O arquivo licencas.json e sempre copiado para um .bak antes de ser reescrito.
"""
import argparse
import csv
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
# Permite rodar tanto da raiz do projeto quanto de infra/build/scripts.
for candidato in (REPO_ROOT, os.path.join(REPO_ROOT, "..", "..", "..")):
    caminho = os.path.abspath(candidato)
    if os.path.exists(os.path.join(caminho, "config.py")):
        sys.path.insert(0, caminho)
        os.chdir(caminho)
        break

from config import get_db_connection  # noqa: E402


def _ler_log_hub(caminho: str) -> tuple[dict, dict]:
    """Retorna (chave -> email, hash_publico -> email) a partir do log do Hub."""
    por_chave: dict[str, str] = {}
    por_hash: dict[str, str] = {}
    if not os.path.exists(caminho):
        return por_chave, por_hash

    with open(caminho, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                registro = json.loads(linha)
            except json.JSONDecodeError:
                continue
            email = str(registro.get("email") or "").strip().lower()
            if not email:
                continue
            chave = str(registro.get("chave") or "").strip()
            hash_pub = str(registro.get("hash_publico") or "").strip()
            if chave:
                por_chave[chave] = email
            if hash_pub:
                por_hash[hash_pub] = email
    return por_chave, por_hash


def _ler_mapa_manual(caminho: str) -> dict:
    """CSV com colunas identificador,email. Chaves normalizadas em minusculas."""
    mapa: dict[str, str] = {}
    if not caminho:
        return mapa
    if not os.path.exists(caminho):
        print(f"[AVISO] Mapa manual nao encontrado: {caminho}")
        return mapa

    with open(caminho, "r", encoding="utf-8", newline="") as f:
        leitor = csv.reader(f)
        for linha in leitor:
            if not linha or len(linha) < 2:
                continue
            identificador = str(linha[0] or "").strip().lower()
            email = str(linha[1] or "").strip().lower()
            if identificador and email and "@" in email:
                mapa[identificador] = email
    return mapa


def _garantir_colunas(cur) -> None:
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
    for coluna in ("email", "cliente", "tipo", "plano"):
        if coluna not in cols:
            cur.execute(f"ALTER TABLE licencas_geradas ADD COLUMN {coluna} TEXT DEFAULT ''")


def migrar_banco(por_chave: dict, mapa_manual: dict, dry_run: bool) -> tuple[int, list]:
    atualizados = 0
    pendentes: list[str] = []

    with get_db_connection() as conn:
        cur = conn.cursor()
        _garantir_colunas(cur)
        conn.commit()

        cur.execute("SELECT id, chave, cliente, email FROM licencas_geradas")
        linhas = cur.fetchall()

        for id_, chave, cliente, email in linhas:
            email_atual = str(email or "").strip()
            if email_atual:
                continue

            candidato = (
                por_chave.get(str(chave or "").strip())
                or mapa_manual.get(str(chave or "").strip().lower())
                or mapa_manual.get(str(cliente or "").strip().lower())
            )
            if candidato:
                atualizados += 1
                if not dry_run:
                    cur.execute("UPDATE licencas_geradas SET email = ? WHERE id = ?", (candidato, id_))
            else:
                pendentes.append(f"id={id_} cliente='{cliente or ''}' chave='{str(chave or '')[:24]}...'")

        if not dry_run:
            conn.commit()

    return atualizados, pendentes


def migrar_licencas_json(caminho: str, por_hash: dict, mapa_manual: dict, dry_run: bool) -> tuple[int, list]:
    atualizados = 0
    pendentes: list[str] = []

    if not os.path.exists(caminho):
        print(f"[AVISO] licencas.json nao encontrado em {caminho}; etapa ignorada.")
        return atualizados, pendentes

    with open(caminho, "r", encoding="utf-8") as f:
        dados = json.load(f)

    licencas = dados.get("licencas")
    if not isinstance(licencas, dict):
        print("[AVISO] licencas.json sem secao 'licencas' valida; etapa ignorada.")
        return atualizados, pendentes

    for hash_pub, entrada in licencas.items():
        if not isinstance(entrada, dict):
            continue
        email_atual = str(entrada.get("email") or "").strip()
        if email_atual:
            continue

        candidato = (
            por_hash.get(hash_pub)
            or mapa_manual.get(hash_pub.strip().lower())
            or mapa_manual.get(str(entrada.get("cliente") or "").strip().lower())
        )
        if candidato:
            atualizados += 1
            entrada["email"] = candidato
        else:
            pendentes.append(f"hash={hash_pub[:16]}... cliente='{entrada.get('cliente', '')}'")

    if atualizados and not dry_run:
        backup = f"{caminho}.bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(caminho, backup)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
        print(f"[OK] Backup de licencas.json criado em {backup}")

    return atualizados, pendentes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mapa", default="", help="CSV manual identificador,email (nome do cliente, chave ou hash).")
    parser.add_argument("--hub-log", default=os.path.join("logs", "hub_licencas_api.log"))
    parser.add_argument("--licencas-json", default="licencas.json")
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula, nao grava alteracoes.")
    args = parser.parse_args()

    print("=" * 60)
    print(" MIGRACAO: vincular e-mails as licencas antigas")
    print("=" * 60)

    por_chave, por_hash = _ler_log_hub(args.hub_log)
    mapa_manual = _ler_mapa_manual(args.mapa)
    print(f"[INFO] Log do Hub: {len(por_chave)} chave(s) e {len(por_hash)} hash(es) com e-mail.")
    print(f"[INFO] Mapa manual: {len(mapa_manual)} identificador(es) com e-mail.")

    atualizados_db, pendentes_db = migrar_banco(por_chave, mapa_manual, args.dry_run)
    print(f"[OK] licencas_geradas (banco): {atualizados_db} registro(s) {'seriam ' if args.dry_run else ''}atualizado(s).")

    atualizados_json, pendentes_json = migrar_licencas_json(args.licencas_json, por_hash, mapa_manual, args.dry_run)
    print(f"[OK] licencas.json: {atualizados_json} registro(s) {'seriam ' if args.dry_run else ''}atualizado(s).")

    if pendentes_db:
        print(f"\n[PENDENTE] {len(pendentes_db)} licenca(s) no banco sem e-mail encontrado:")
        for item in pendentes_db:
            print(f"  - {item}")

    if pendentes_json:
        print(f"\n[PENDENTE] {len(pendentes_json)} licenca(s) em licencas.json sem e-mail encontrado:")
        for item in pendentes_json:
            print(f"  - {item}")

    if pendentes_db or pendentes_json:
        print(
            "\nAdicione essas entradas ao CSV do --mapa (coluna 1 = nome do cliente, "
            "chave ou hash; coluna 2 = e-mail) e rode o script novamente."
        )

    if args.dry_run:
        print("\n[DRY-RUN] Nenhuma alteracao foi gravada.")

    print("=" * 60)


if __name__ == "__main__":
    main()
