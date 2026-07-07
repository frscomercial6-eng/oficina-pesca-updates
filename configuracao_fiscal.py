# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import ctypes
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


class EmissorFiscalACBr(InterfaceEmissorFiscal):
    _DLL_PRIORIDADE = (
        "ACBrLibNFe64.dll",
        "ACBrLibNFe32.dll",
        "ACBrNFe64.dll",
        "ACBrNFe32.dll",
    )

    def __init__(self, configuracao: ConfiguracaoFiscal):
        self.configuracao = configuracao

    def _resolver_pasta_acbr(self) -> str:
        parametros = self.configuracao.parametros_gerais if isinstance(self.configuracao.parametros_gerais, dict) else {}
        pasta = str(parametros.get("acbr_path") or "").strip()
        if pasta:
            return pasta
        return os.path.join(os.path.dirname(CAMINHO_BANCO), "acbr")

    def _bibliotecas_disponiveis(self) -> list[str]:
        pasta = self._resolver_pasta_acbr()
        if not os.path.isdir(pasta):
            return []
        try:
            return sorted(nome for nome in os.listdir(pasta) if nome.lower().endswith(".dll"))
        except Exception:
            return []

    def _resolver_dll(self, dlls: list[str]) -> str:
        pasta = self._resolver_pasta_acbr()
        mapa = {nome.lower(): nome for nome in dlls}
        for preferida in self._DLL_PRIORIDADE:
            nome = mapa.get(preferida.lower())
            if nome:
                return os.path.join(pasta, nome)
        if dlls:
            return os.path.join(pasta, dlls[0])
        return ""

    def _chamada_real_acbr(self, dll_path: str) -> dict[str, Any]:
        if os.name != "nt":
            return {
                "ok": False,
                "motivo": "acbr_suportado_apenas_windows",
                "dll_path": dll_path,
            }

        try:
            lib = ctypes.WinDLL(dll_path)
        except Exception as exc:
            return {
                "ok": False,
                "motivo": "falha_carregar_dll",
                "dll_path": dll_path,
                "erro": str(exc),
            }

        retorno: dict[str, Any] = {
            "ok": True,
            "dll_path": dll_path,
            "funcao_inicializar_encontrada": hasattr(lib, "NFE_Inicializar"),
            "funcao_finalizar_encontrada": hasattr(lib, "NFE_Finalizar"),
        }

        if not hasattr(lib, "NFE_Inicializar"):
            retorno["ok"] = False
            retorno["motivo"] = "funcao_nfe_inicializar_nao_encontrada"
            return retorno

        parametros = self.configuracao.parametros_gerais if isinstance(self.configuracao.parametros_gerais, dict) else {}
        ini_path = str(parametros.get("acbr_ini") or "").strip()
        crypt_key = str(parametros.get("acbr_crypt_key") or "").strip()

        inicializar = lib.NFE_Inicializar
        inicializar.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        inicializar.restype = ctypes.c_int

        ret_init = int(
            inicializar(
                ini_path.encode("utf-8") if ini_path else b"",
                crypt_key.encode("utf-8") if crypt_key else b"",
            )
        )
        retorno["ret_inicializar"] = ret_init

        if hasattr(lib, "NFE_Finalizar"):
            finalizar = lib.NFE_Finalizar
            finalizar.argtypes = []
            finalizar.restype = ctypes.c_int
            retorno["ret_finalizar"] = int(finalizar())

        retorno["ok"] = ret_init == 0
        if ret_init != 0:
            retorno["motivo"] = "nfe_inicializar_retorno_nao_zero"
        return retorno

    def enviar_venda(self, venda: dict[str, Any]) -> dict[str, Any]:
        payload = montar_payload_nota_fiscal(venda)
        dlls = self._bibliotecas_disponiveis()
        if not dlls:
            return {
                "ok": False,
                "modo": "acbr",
                "status": "erro",
                "motivo": "bibliotecas_acbr_ausentes",
                "sale_id": payload.get("sale_id"),
                "acbr_path": self._resolver_pasta_acbr(),
            }

        dll_path = self._resolver_dll(dlls)
        chamada = self._chamada_real_acbr(dll_path)
        ok = bool(chamada.get("ok"))

        return {
            "ok": ok,
            "modo": "acbr",
            "status": "chamada_real_ok" if ok else "erro",
            "sale_id": payload.get("sale_id"),
            "acbr_path": self._resolver_pasta_acbr(),
            "acbr_dll": dll_path,
            "acbr_dlls": dlls,
            "acbr_call": chamada,
            "payload": payload,
        }

    def cancelar_nota(self, referencia: str) -> dict[str, Any]:
        return {
            "ok": True,
            "modo": "acbr",
            "status": "pendente_cancelamento",
            "referencia": referencia,
            "acbr_path": self._resolver_pasta_acbr(),
        }

    def consultar_status(self, referencia: str) -> dict[str, Any]:
        return {
            "ok": True,
            "modo": "acbr",
            "status": "pendente_consulta",
            "referencia": referencia,
            "acbr_path": self._resolver_pasta_acbr(),
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


def _provedor_fiscal(configuracao: ConfiguracaoFiscal) -> str:
    parametros = configuracao.parametros_gerais if isinstance(configuracao.parametros_gerais, dict) else {}
    provedor = str(parametros.get("provedor") or "").strip().lower()
    return provedor


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
    if _provedor_fiscal(cfg) == "acbr":
        return EmissorFiscalACBr(cfg)

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
