# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from config import get_db_connection


def somente_digitos(valor: Any) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


def cpf_valido(cpf: Any) -> bool:
    cpf_txt = somente_digitos(cpf)
    if len(cpf_txt) != 11 or cpf_txt == cpf_txt[0] * 11:
        return False
    soma = sum(int(cpf_txt[i]) * (10 - i) for i in range(9))
    dig1 = (soma * 10) % 11
    dig1 = 0 if dig1 == 10 else dig1
    if dig1 != int(cpf_txt[9]):
        return False
    soma = sum(int(cpf_txt[i]) * (11 - i) for i in range(10))
    dig2 = (soma * 10) % 11
    dig2 = 0 if dig2 == 10 else dig2
    return dig2 == int(cpf_txt[10])


def cnpj_valido(cnpj: Any) -> bool:
    cnpj_txt = somente_digitos(cnpj)
    if len(cnpj_txt) != 14 or cnpj_txt == cnpj_txt[0] * 14:
        return False

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    soma1 = sum(int(cnpj_txt[i]) * pesos1[i] for i in range(12))
    resto1 = soma1 % 11
    dig1 = 0 if resto1 < 2 else 11 - resto1
    if dig1 != int(cnpj_txt[12]):
        return False

    soma2 = sum(int(cnpj_txt[i]) * pesos2[i] for i in range(13))
    resto2 = soma2 % 11
    dig2 = 0 if resto2 < 2 else 11 - resto2
    return dig2 == int(cnpj_txt[13])


def documento_fiscal_valido(documento: Any) -> bool:
    digitos = somente_digitos(documento)
    if len(digitos) == 11:
        return cpf_valido(digitos)
    if len(digitos) == 14:
        return cnpj_valido(digitos)
    return False


def _tem_coluna_clientes(nome_coluna: str) -> bool:
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(clientes)")
        cols = {str(row[1]).lower() for row in cur.fetchall()}
    return nome_coluna.lower() in cols


def obter_cliente_por_id(cliente_id: int | None) -> dict[str, str] | None:
    try:
        cid = int(cliente_id or 0)
    except Exception:
        return None
    if cid <= 0:
        return None

    tem_cpf = _tem_coluna_clientes("cpf_cnpj")
    campo_cpf = "COALESCE(cpf_cnpj, '')" if tem_cpf else "''"

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT COALESCE(nome,''), {campo_cpf}, COALESCE(cep,''), COALESCE(rua,''),
                   COALESCE(numero,''), COALESCE(cidade,''), COALESCE(estado,'')
            FROM clientes
            WHERE id = ?
            LIMIT 1
            """,
            (cid,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "nome": str(row[0] or "").strip(),
        "cpf_cnpj": str(row[1] or "").strip(),
        "cep": str(row[2] or "").strip(),
        "rua": str(row[3] or "").strip(),
        "numero": str(row[4] or "").strip(),
        "cidade": str(row[5] or "").strip(),
        "estado": str(row[6] or "").strip(),
    }


def obter_cliente_por_nome_telefone(nome: str, telefone: str = "") -> dict[str, str] | None:
    nome_up = str(nome or "").strip().upper()
    if not nome_up:
        return None

    tel_dig = somente_digitos(telefone)
    tem_cpf = _tem_coluna_clientes("cpf_cnpj")
    campo_cpf = "COALESCE(cpf_cnpj, '')" if tem_cpf else "''"

    with get_db_connection() as conn:
        cur = conn.cursor()
        if tel_dig:
            cur.execute(
                f"""
                SELECT COALESCE(nome,''), {campo_cpf}, COALESCE(cep,''), COALESCE(rua,''),
                       COALESCE(numero,''), COALESCE(cidade,''), COALESCE(estado,'')
                FROM clientes
                WHERE UPPER(COALESCE(nome,'')) = ?
                  AND REPLACE(REPLACE(REPLACE(REPLACE(COALESCE(telefone,''), '(', ''), ')', ''), '-', ''), ' ', '') = ?
                LIMIT 1
                """,
                (nome_up, tel_dig),
            )
            row = cur.fetchone()
            if row:
                return {
                    "nome": str(row[0] or "").strip(),
                    "cpf_cnpj": str(row[1] or "").strip(),
                    "cep": str(row[2] or "").strip(),
                    "rua": str(row[3] or "").strip(),
                    "numero": str(row[4] or "").strip(),
                    "cidade": str(row[5] or "").strip(),
                    "estado": str(row[6] or "").strip(),
                }

        cur.execute(
            f"""
            SELECT COALESCE(nome,''), {campo_cpf}, COALESCE(cep,''), COALESCE(rua,''),
                   COALESCE(numero,''), COALESCE(cidade,''), COALESCE(estado,'')
            FROM clientes
            WHERE UPPER(COALESCE(nome,'')) = ?
            LIMIT 1
            """,
            (nome_up,),
        )
        row = cur.fetchone()

    if not row:
        return None

    return {
        "nome": str(row[0] or "").strip(),
        "cpf_cnpj": str(row[1] or "").strip(),
        "cep": str(row[2] or "").strip(),
        "rua": str(row[3] or "").strip(),
        "numero": str(row[4] or "").strip(),
        "cidade": str(row[5] or "").strip(),
        "estado": str(row[6] or "").strip(),
    }


def _ncm_produtos_por_id(produto_ids: list[int]) -> dict[int, str]:
    ids = [int(pid) for pid in produto_ids if int(pid or 0) > 0]
    if not ids:
        return {}

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(produtos)")
        cols = {str(row[1]).lower() for row in cur.fetchall()}
        if "ncm" not in cols:
            return {}

        placeholders = ",".join("?" for _ in ids)
        cur.execute(
            f"SELECT id, COALESCE(ncm, '') FROM produtos WHERE id IN ({placeholders})",
            tuple(ids),
        )
        return {int(row[0]): somente_digitos(row[1])[:8] for row in cur.fetchall()}


def _ncm_produtos_por_nome(nomes: list[str]) -> dict[str, str]:
    nomes_up = [str(nome or "").strip().upper() for nome in nomes if str(nome or "").strip()]
    nomes_up = list(dict.fromkeys(nomes_up))
    if not nomes_up:
        return {}

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(produtos)")
        cols = {str(row[1]).lower() for row in cur.fetchall()}
        if "ncm" not in cols:
            return {}

        placeholders = ",".join("?" for _ in nomes_up)
        cur.execute(
            f"SELECT UPPER(COALESCE(nome,'')), COALESCE(ncm, '') FROM produtos WHERE UPPER(COALESCE(nome,'')) IN ({placeholders})",
            tuple(nomes_up),
        )
        return {str(row[0] or "").strip().upper(): somente_digitos(row[1])[:8] for row in cur.fetchall()}


def validar_pre_emissao_nota(
    *,
    cliente: dict[str, Any] | None,
    itens: list[dict[str, Any]] | None,
    tipo_documento: str = "nfe",
) -> list[str]:
    faltantes: list[str] = []
    dados_cliente = dict(cliente or {})

    if not documento_fiscal_valido(dados_cliente.get("cpf_cnpj")):
        faltantes.append("CPF/CNPJ do cliente válido")

    faltas_endereco = []
    if len(somente_digitos(dados_cliente.get("cep"))) != 8:
        faltas_endereco.append("CEP")
    if not str(dados_cliente.get("rua") or "").strip():
        faltas_endereco.append("logradouro")
    if not str(dados_cliente.get("numero") or "").strip():
        faltas_endereco.append("número")
    if not str(dados_cliente.get("cidade") or "").strip():
        faltas_endereco.append("cidade")
    if len(str(dados_cliente.get("estado") or "").strip()) != 2:
        faltas_endereco.append("UF")
    if faltas_endereco:
        faltantes.append("Endereço do cliente incompleto: " + ", ".join(faltas_endereco))

    itens_lista = list(itens or [])
    mapa_por_id = _ncm_produtos_por_id([int(item.get("produto_id") or 0) for item in itens_lista])
    mapa_por_nome = _ncm_produtos_por_nome([str(item.get("nome_produto") or "") for item in itens_lista])

    itens_sem_ncm = []
    for idx, item in enumerate(itens_lista, start=1):
        pid = int(item.get("produto_id") or 0)
        nome_item = str(item.get("nome_produto") or f"Item {idx}").strip()
        ncm_informado = somente_digitos(item.get("ncm"))[:8]

        if len(ncm_informado) == 8:
            continue
        if pid > 0 and len(mapa_por_id.get(pid, "")) == 8:
            continue

        nome_up = nome_item.upper()
        if nome_up and len(mapa_por_nome.get(nome_up, "")) == 8:
            continue

        if pid <= 0:
            itens_sem_ncm.append(f"{idx}. {nome_item} (sem produto cadastrado)")
        else:
            itens_sem_ncm.append(f"{idx}. {nome_item}")

    if itens_sem_ncm:
        faltantes.append("Itens sem NCM cadastrado: " + "; ".join(itens_sem_ncm))

    return faltantes


def formatar_mensagem_bloqueio_emissao(faltantes: list[str], tipo_documento: str = "nfe") -> str:
    _ = str(tipo_documento or "").strip().lower()
    return "Não é possível emitir nota. Faltam os seguintes dados:\n- " + "\n- ".join(list(faltantes or []))
