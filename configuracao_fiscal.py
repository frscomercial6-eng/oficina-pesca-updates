# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from config import CAMINHO_BANCO, get_db_connection
from migracao_fiscal_2027 import executar_migracao_fiscal_2027


def _normalizar_ncm(valor: Any) -> str:
    return "".join(ch for ch in str(valor or "") if ch.isdigit())


@dataclass
class ConfiguracaoFiscal:
    api_key_plugnotas: str = ""
    api_key_focusnfe: str = ""
    ambiente: str = "homologacao"
    parametros_gerais: dict[str, Any] | None = None

    def to_db(self) -> tuple[str, str, str, str]:
        parametros = self.parametros_gerais if isinstance(self.parametros_gerais, dict) else {}
        return (
            str(self.api_key_plugnotas or "").strip(),
            str(self.api_key_focusnfe or "").strip(),
            str(self.ambiente or "homologacao").strip().lower(),
            json.dumps(parametros, ensure_ascii=False),
        )


class InterfaceEmissorFiscal(ABC):
    @abstractmethod
    def enviar_venda(self, venda: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def cancelar_nota(self, referencia: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def consultar_status(self, referencia: str) -> dict[str, Any]:
        raise NotImplementedError


class EmissorFiscalStandalone(InterfaceEmissorFiscal):
    def enviar_venda(self, venda: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "modo": "standalone",
            "status": "ignorado",
            "motivo": "configuracao_fiscal_incompleta_ou_sem_adaptador",
            "sale_id": venda.get("sale_id"),
        }


def enriquecer_venda_com_ncm(venda: dict[str, Any]) -> dict[str, Any]:
    venda_saida = dict(venda or {})
    itens = [dict(item) for item in list(venda_saida.get("items") or [])]
    produto_ids = [int(item.get("produto_id") or 0) for item in itens if int(item.get("produto_id") or 0) > 0]

    mapa_ncm: dict[int, str] = {}
    if produto_ids:
        placeholders = ",".join("?" for _ in produto_ids)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT id, COALESCE(ncm, '') FROM produtos WHERE id IN ({placeholders})",
                tuple(produto_ids),
            )
            mapa_ncm = {int(row[0]): _normalizar_ncm(row[1]) for row in cursor.fetchall()}

    itens_saida = []
    for item in itens:
        pid = int(item.get("produto_id") or 0)
        ncm_item = _normalizar_ncm(item.get("ncm") or mapa_ncm.get(pid, ""))
        item["ncm"] = ncm_item
        itens_saida.append(item)

    venda_saida["items"] = itens_saida
    return venda_saida


def montar_payload_nota_fiscal(venda: dict[str, Any]) -> dict[str, Any]:
    venda_fiscal = enriquecer_venda_com_ncm(venda)
    itens_payload = []

    for item in list(venda_fiscal.get("items") or []):
        ncm = _normalizar_ncm(item.get("ncm"))
        if len(ncm) != 8:
            raise ValueError(f"NCM obrigatório e inválido para o item: {item.get('nome_produto') or item.get('produto_id')}")
        itens_payload.append(
            {
                "produto_id": int(item.get("produto_id") or 0),
                "nome_produto": str(item.get("nome_produto") or "").strip(),
                "quantidade": int(item.get("quantidade") or 0),
                "preco_unitario": float(item.get("preco_unitario") or 0),
                "total_item": float(item.get("total_item") or 0),
                "ncm": ncm,
            }
        )

    return {
        "sale_id": venda_fiscal.get("sale_id"),
        "date": venda_fiscal.get("date"),
        "total": float(venda_fiscal.get("total") or 0),
        "payment_method": venda_fiscal.get("payment_method"),
        "items": itens_payload,
    }

    def cancelar_nota(self, referencia: str) -> dict[str, Any]:
        return {
            "ok": True,
            "modo": "standalone",
            "status": "ignorado",
            "motivo": "adaptador_fiscal_nao_configurado",
            "referencia": referencia,
        }

    def consultar_status(self, referencia: str) -> dict[str, Any]:
        return {
            "ok": True,
            "modo": "standalone",
            "status": "indisponivel",
            "motivo": "adaptador_fiscal_nao_configurado",
            "referencia": referencia,
        }


def _tabela_configuracao_fiscal_existe() -> bool:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'configuracao_fiscal' LIMIT 1"
        )
        return cursor.fetchone() is not None


def carregar_configuracao_fiscal() -> ConfiguracaoFiscal:
    if not _tabela_configuracao_fiscal_existe():
        return ConfiguracaoFiscal()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                COALESCE(api_key_plugnotas, ''),
                COALESCE(api_key_focusnfe, ''),
                COALESCE(ambiente, 'homologacao'),
                COALESCE(parametros_gerais, '{}')
            FROM configuracao_fiscal
            WHERE id = 1
            """
        )
        row = cursor.fetchone() or ("", "", "homologacao", "{}")

    try:
        parametros = json.loads(str(row[3] or "{}").strip() or "{}")
        if not isinstance(parametros, dict):
            parametros = {}
    except Exception:
        parametros = {}

    return ConfiguracaoFiscal(
        api_key_plugnotas=str(row[0] or "").strip(),
        api_key_focusnfe=str(row[1] or "").strip(),
        ambiente=str(row[2] or "homologacao").strip().lower() or "homologacao",
        parametros_gerais=parametros,
    )


def salvar_configuracao_fiscal(configuracao: ConfiguracaoFiscal) -> None:
    executar_migracao_fiscal_2027(CAMINHO_BANCO)
    api_plug, api_focus, ambiente, parametros = configuracao.to_db()

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE configuracao_fiscal
            SET api_key_plugnotas = ?,
                api_key_focusnfe = ?,
                ambiente = ?,
                parametros_gerais = ?
            WHERE id = 1
            """,
            (api_plug, api_focus, ambiente, parametros),
        )
        conn.commit()


def configuracao_fiscal_esta_pronta(configuracao: ConfiguracaoFiscal | None = None) -> bool:
    cfg = configuracao or carregar_configuracao_fiscal()
    tem_api = bool(cfg.api_key_plugnotas or cfg.api_key_focusnfe)
    ambiente_ok = str(cfg.ambiente or "").strip().lower() in {"homologacao", "producao", "produção"}
    return tem_api and ambiente_ok


def obter_emissor_fiscal(configuracao: ConfiguracaoFiscal | None = None) -> InterfaceEmissorFiscal:
    cfg = configuracao or carregar_configuracao_fiscal()
    if not configuracao_fiscal_esta_pronta(cfg):
        return EmissorFiscalStandalone()

    # Interface preparada para PlugNotas/FocusNFe.
    # Integracao ativa sera plugada depois via adaptadores concretos.
    return EmissorFiscalStandalone()


def tentar_enviar_venda(venda: dict[str, Any]) -> dict[str, Any]:
    try:
        cfg = carregar_configuracao_fiscal()
        emissor = obter_emissor_fiscal(cfg)
        return emissor.enviar_venda(venda)
    except Exception as exc:
        return {
            "ok": False,
            "modo": "standalone",
            "status": "erro",
            "motivo": str(exc),
            "sale_id": venda.get("sale_id") if isinstance(venda, dict) else None,
        }
