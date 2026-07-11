# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import ctypes
import re
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from adaptador_acbr import consultar_status_acbr_monitor
from config import CAMINHO_BANCO, get_db_connection
from migracao_fiscal_2027 import executar_migracao_fiscal_2027


def _base_runtime_dir() -> str:
    if os.environ.get("OFP_BASE_RUNTIME_DIR", "").strip():
        return os.environ.get("OFP_BASE_RUNTIME_DIR", "").strip()
    return os.path.dirname(CAMINHO_BANCO)


def _diretorio_config_fiscal() -> str:
    return os.path.join(_base_runtime_dir(), "config_fiscal")


def _arquivo_config_fiscal_json() -> str:
    return os.path.join(_diretorio_config_fiscal(), "config_fiscal.json")


def _arquivo_setup_monitor_txt() -> str:
    return os.path.join(_diretorio_config_fiscal(), "acbr_monitor_setup.txt")


def _arquivo_log_erros_fiscais() -> str:
    pasta_logs = os.path.join(_base_runtime_dir(), "logs")
    os.makedirs(pasta_logs, exist_ok=True)
    return os.path.join(pasta_logs, "erros_fiscais.log")


def _registrar_erro_fiscal(contexto: str, retorno_bruto: dict[str, Any]) -> None:
    try:
        linha = {
            "data_hora": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "contexto": str(contexto or "fiscal"),
            "retorno": retorno_bruto,
        }
        with open(_arquivo_log_erros_fiscais(), "a", encoding="utf-8") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _extrair_motivo_bruto(retorno: dict[str, Any]) -> str:
    monitor = retorno.get("monitor") if isinstance(retorno.get("monitor"), dict) else {}
    acbr_call = retorno.get("acbr_call") if isinstance(retorno.get("acbr_call"), dict) else {}

    candidatos = [
        str(retorno.get("motivo") or "").strip(),
        str(retorno.get("erro") or "").strip(),
        str(monitor.get("resposta") or "").strip(),
        str(monitor.get("motivo") or "").strip(),
        str(acbr_call.get("erro") or "").strip(),
        str(acbr_call.get("motivo") or "").strip(),
    ]
    for item in candidatos:
        if item:
            return item
    return "falha_na_comunicacao_fiscal"


def _limpar_codigo_tecnico(motivo_bruto: str) -> str:
    txt = str(motivo_bruto or "").strip()
    if not txt:
        return ""
    txt = re.sub(r"\berro\s*\d+\b[:\-\s]*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\brejei[cç][aã]o\s*\d+\b[:\-\s]*", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def _mensagem_amigavel_erro_fiscal(retorno: dict[str, Any]) -> str:
    motivo_bruto = _extrair_motivo_bruto(retorno)
    motivo_legivel = _limpar_codigo_tecnico(motivo_bruto) or "detalhes técnicos indisponíveis"
    motivo_low = motivo_bruto.lower()

    if any(chave in motivo_low for chave in ["timeout", "time out", "sem_resposta", "sem resposta", "indispon", "fora do ar", "statusservico"]):
        return (
            "Atenção: A SEFAZ está temporariamente fora do ar. "
            "Verifique sua internet ou tente novamente mais tarde"
        )

    if "rejei" in motivo_low:
        return f"Atenção: Nota rejeitada. O motivo é: {motivo_legivel}"

    if any(chave in motivo_low for chave in ["certificado", "a1", "pfx", "p12"]):
        return (
            "Atenção: Não foi possível validar o certificado digital. "
            "Confirme o certificado A1 e tente novamente"
        )

    return f"Atenção: Não foi possível concluir a operação fiscal. Motivo: {motivo_legivel}"


def _normalizar_retorno_fiscal(contexto: str, retorno: dict[str, Any]) -> dict[str, Any]:
    saida = dict(retorno or {})
    if bool(saida.get("ok")):
        return saida

    msg = str(saida.get("mensagem") or "").strip() or _mensagem_amigavel_erro_fiscal(saida)
    saida["mensagem"] = msg
    _registrar_erro_fiscal(contexto, retorno)
    return saida


def _garantir_arquivo_ini_acbr(caminho_ini: str, cfg: dict[str, Any]) -> None:
    if os.path.exists(caminho_ini):
        return
    conteudo = (
        "[ACBrMonitor]\n"
        f"PastaMonitor={cfg.get('acbr_monitor_path', '')}\n"
        f"ArquivoENT={cfg.get('acbr_entrada', '')}\n"
        f"ArquivoSAI={cfg.get('acbr_saida', '')}\n\n"
        "[Fiscal]\n"
        f"Modalidade={cfg.get('modalidade_fiscal', 'nfe')}\n"
        f"CNPJ={cfg.get('emitente_cnpj', '')}\n"
        f"IE={cfg.get('emitente_ie', '')}\n"
        f"CertificadoA1={cfg.get('acbr_certificado_a1_path', '')}\n"
    )
    with open(caminho_ini, "w", encoding="utf-8") as f:
        f.write(conteudo)


def _garantir_arquivo_setup_txt(cfg: dict[str, Any]) -> None:
    caminho = _arquivo_setup_monitor_txt()
    conteudo = (
        "CONFIGURACAO PADRAO ACBrMonitor\n"
        "================================\n"
        f"Pasta monitor: {cfg.get('acbr_monitor_path', '')}\n"
        f"ENT (entrada): {cfg.get('acbr_entrada', '')}\n"
        f"SAI (saida): {cfg.get('acbr_saida', '')}\n"
        f"INI ACBr: {cfg.get('acbr_ini', '')}\n"
        f"Modalidade fiscal: {cfg.get('modalidade_fiscal', 'nfe')}\n"
    )
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)


def _garantir_estrutura_fiscal(parametros: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = dict(parametros or {})
    base = _diretorio_config_fiscal()
    pasta_acbr = str(cfg.get("acbr_path") or os.path.join(base, "acbr")).strip()
    pasta_monitor = str(cfg.get("acbr_monitor_path") or os.path.join(base, "acbr_monitor")).strip()

    os.makedirs(base, exist_ok=True)
    os.makedirs(pasta_acbr, exist_ok=True)
    os.makedirs(pasta_monitor, exist_ok=True)

    cfg["provedor"] = str(cfg.get("provedor") or "acbr").strip().lower()
    cfg["acbr_modo"] = str(cfg.get("acbr_modo") or "monitor").strip().lower()
    cfg["modalidade_fiscal"] = str(cfg.get("modalidade_fiscal") or "nfe").strip().lower()
    cfg["acbr_path"] = pasta_acbr
    cfg["acbr_monitor_path"] = pasta_monitor
    cfg["acbr_entrada"] = str(cfg.get("acbr_entrada") or os.path.join(pasta_monitor, "ENT.txt")).strip()
    cfg["acbr_saida"] = str(cfg.get("acbr_saida") or os.path.join(pasta_monitor, "SAI.txt")).strip()
    cfg["acbr_ini"] = str(cfg.get("acbr_ini") or os.path.join(base, "acbrlib.ini")).strip()
    cfg["acbr_certificado_a1_path"] = str(
        cfg.get("acbr_certificado_a1_path") or cfg.get("certificado_a1_path") or ""
    ).strip()
    cfg["certificado_a1_path"] = str(cfg.get("acbr_certificado_a1_path") or "").strip()
    cfg["emitente_cnpj"] = str(cfg.get("emitente_cnpj") or "").strip()
    cfg["emitente_ie"] = str(cfg.get("emitente_ie") or "").strip()
    cfg["acbr_token"] = str(cfg.get("acbr_token") or "").strip()
    _garantir_arquivo_ini_acbr(cfg["acbr_ini"], cfg)
    _garantir_arquivo_setup_txt(cfg)
    return cfg


def _carregar_json_config_fiscal() -> dict[str, Any]:
    caminho = _arquivo_config_fiscal_json()
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _salvar_json_config_fiscal(payload: dict[str, Any]) -> None:
    os.makedirs(_diretorio_config_fiscal(), exist_ok=True)
    caminho = _arquivo_config_fiscal_json()
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def inicializar_motor_fiscal(configuracao: ConfiguracaoFiscal | None = None) -> ConfiguracaoFiscal:
    cfg = configuracao or carregar_configuracao_fiscal()
    params = cfg.parametros_gerais if isinstance(cfg.parametros_gerais, dict) else {}
    cfg.parametros_gerais = _garantir_estrutura_fiscal(params)
    return cfg


def verificar_status_motor_fiscal(configuracao: ConfiguracaoFiscal | None = None) -> dict[str, Any]:
    cfg = inicializar_motor_fiscal(configuracao or carregar_configuracao_fiscal())
    params = cfg.parametros_gerais if isinstance(cfg.parametros_gerais, dict) else {}
    provedor = str(params.get("provedor") or "acbr").strip().lower()
    if provedor != "acbr":
        return {
            "ok": True,
            "mensagem": "Provedor fiscal não usa ACBrMonitor.",
            "provedor": provedor,
            "monitor": None,
        }

    monitor = consultar_status_acbr_monitor(params)
    ok = bool(monitor.get("ok"))
    return {
        "ok": ok,
        "mensagem": (
            "Motor fiscal detectado e ativo."
            if ok
            else "Motor fiscal não detectado. Verifique se o ACBrMonitor está aberto"
        ),
        "provedor": provedor,
        "monitor": monitor,
        "parametros": params,
    }


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

    def _status_monitor(self) -> dict[str, Any]:
        parametros = self.configuracao.parametros_gerais if isinstance(self.configuracao.parametros_gerais, dict) else {}
        retorno = consultar_status_acbr_monitor(parametros)
        return {
            "ok": bool(retorno.get("ok")),
            "modo": "acbr_monitor",
            "acbr_path": self._resolver_pasta_acbr(),
            "monitor": retorno,
        }

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
        parametros = self.configuracao.parametros_gerais if isinstance(self.configuracao.parametros_gerais, dict) else {}
        modo_forcado = str(parametros.get("acbr_modo") or "").strip().lower()

        if modo_forcado == "monitor":
            status_monitor = self._status_monitor()
            ok_monitor = bool(status_monitor.get("ok"))
            return {
                "ok": ok_monitor,
                "modo": "acbr_monitor",
                "status": "monitor_ok" if ok_monitor else "erro",
                "sale_id": payload.get("sale_id"),
                "acbr_path": self._resolver_pasta_acbr(),
                "monitor": status_monitor.get("monitor"),
                "payload": payload,
            }

        dlls = self._bibliotecas_disponiveis()
        if not dlls:
            status_monitor = self._status_monitor()
            if status_monitor.get("ok"):
                return {
                    "ok": True,
                    "modo": "acbr_monitor",
                    "status": "monitor_ok",
                    "sale_id": payload.get("sale_id"),
                    "acbr_path": self._resolver_pasta_acbr(),
                    "monitor": status_monitor.get("monitor"),
                    "payload": payload,
                }
            return {
                "ok": False,
                "modo": "acbr",
                "status": "erro",
                "motivo": "bibliotecas_acbr_ausentes",
                "sale_id": payload.get("sale_id"),
                "acbr_path": self._resolver_pasta_acbr(),
                "monitor": status_monitor.get("monitor"),
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
        "fiscal_tipo": str(venda_fiscal.get("fiscal_tipo") or "nfe").strip().lower(),
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
    row = ("", "", "homologacao", "{}")
    if _tabela_configuracao_fiscal_existe():
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
            row = cursor.fetchone() or row

    try:
        parametros_db = json.loads(str(row[3] or "{}").strip() or "{}")
        if not isinstance(parametros_db, dict):
            parametros_db = {}
    except Exception:
        parametros_db = {}

    parametros_json = _carregar_json_config_fiscal()
    parametros = dict(parametros_db)
    parametros.update(parametros_json)

    cfg = ConfiguracaoFiscal(
        api_key_plugnotas=str(row[0] or "").strip(),
        api_key_focusnfe=str(row[1] or "").strip(),
        ambiente=str(row[2] or "homologacao").strip().lower() or "homologacao",
        parametros_gerais=parametros,
    )
    return inicializar_motor_fiscal(cfg)


def salvar_configuracao_fiscal(configuracao: ConfiguracaoFiscal) -> None:
    configuracao = inicializar_motor_fiscal(configuracao)
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

    try:
        payload_json = {
            "api_key_plugnotas": str(configuracao.api_key_plugnotas or "").strip(),
            "api_key_focusnfe": str(configuracao.api_key_focusnfe or "").strip(),
            "ambiente": str(configuracao.ambiente or "homologacao").strip().lower(),
        }
        payload_json.update(configuracao.parametros_gerais if isinstance(configuracao.parametros_gerais, dict) else {})
        _salvar_json_config_fiscal(payload_json)
    except Exception:
        pass


def configuracao_fiscal_esta_pronta(configuracao: ConfiguracaoFiscal | None = None) -> bool:
    cfg = configuracao or carregar_configuracao_fiscal()
    tem_api = bool(cfg.api_key_plugnotas or cfg.api_key_focusnfe)
    ambiente_ok = str(cfg.ambiente or "").strip().lower() in {"homologacao", "producao", "produção"}
    return tem_api and ambiente_ok


def obter_emissor_fiscal(configuracao: ConfiguracaoFiscal | None = None) -> InterfaceEmissorFiscal:
    cfg = inicializar_motor_fiscal(configuracao or carregar_configuracao_fiscal())
    if _provedor_fiscal(cfg) == "acbr":
        return EmissorFiscalACBr(cfg)

    if not configuracao_fiscal_esta_pronta(cfg):
        return EmissorFiscalStandalone()

    # Interface preparada para PlugNotas/FocusNFe.
    # Integracao ativa sera plugada depois via adaptadores concretos.
    return EmissorFiscalStandalone()


def _resultado_motor_inativo() -> dict[str, Any]:
    return {
        "ok": False,
        "modo": "acbr_monitor",
        "status": "bloqueado_motor_fiscal",
        "motivo": "motor_fiscal_inativo",
        "mensagem": "Motor fiscal não detectado. Verifique se o ACBrMonitor está aberto",
    }


def _gate_motor_fiscal() -> dict[str, Any]:
    status = verificar_status_motor_fiscal()
    if bool(status.get("ok")):
        return {"ok": True, "status": status}
    retorno = _resultado_motor_inativo()
    retorno["monitor"] = status.get("monitor")
    return retorno


def tentar_enviar_venda(venda: dict[str, Any]) -> dict[str, Any]:
    try:
        gate = _gate_motor_fiscal()
        if not bool(gate.get("ok")):
            bloqueio = dict(gate)
            bloqueio["sale_id"] = venda.get("sale_id") if isinstance(venda, dict) else None
            return _normalizar_retorno_fiscal("emitir_nota", bloqueio)
        cfg = carregar_configuracao_fiscal()
        emissor = obter_emissor_fiscal(cfg)
        retorno = emissor.enviar_venda(venda)
        return _normalizar_retorno_fiscal("emitir_nota", retorno if isinstance(retorno, dict) else {"ok": False, "motivo": "retorno_fiscal_invalido"})
    except Exception as exc:
        retorno_erro = {
            "ok": False,
            "modo": "standalone",
            "status": "erro",
            "motivo": str(exc),
            "sale_id": venda.get("sale_id") if isinstance(venda, dict) else None,
        }
        return _normalizar_retorno_fiscal("emitir_nota", retorno_erro)


def consultar_nota_fiscal(referencia: str) -> dict[str, Any]:
    ref = str(referencia or "").strip()
    if not ref:
        return {
            "ok": False,
            "modo": "standalone",
            "status": "erro",
            "motivo": "referencia_vazia",
            "mensagem": "Informe uma referência de nota para consulta.",
        }
    try:
        gate = _gate_motor_fiscal()
        if not bool(gate.get("ok")):
            bloqueio = dict(gate)
            bloqueio["referencia"] = ref
            return _normalizar_retorno_fiscal("consultar_nota", bloqueio)
        cfg = carregar_configuracao_fiscal()
        emissor = obter_emissor_fiscal(cfg)
        retorno = emissor.consultar_status(ref)
        if isinstance(retorno, dict):
            retorno.setdefault("referencia", ref)
        retorno = retorno if isinstance(retorno, dict) else {"ok": False, "motivo": "retorno_fiscal_invalido", "referencia": ref}
        return _normalizar_retorno_fiscal("consultar_nota", retorno)
    except Exception as exc:
        retorno_erro = {
            "ok": False,
            "modo": "standalone",
            "status": "erro",
            "motivo": str(exc),
            "referencia": ref,
        }
        return _normalizar_retorno_fiscal("consultar_nota", retorno_erro)


def imprimir_danfe_fiscal(venda: dict[str, Any], pasta_saida: str | None = None) -> dict[str, Any]:
    try:
        gate = _gate_motor_fiscal()
        if not bool(gate.get("ok")):
            bloqueio = dict(gate)
            bloqueio["sale_id"] = venda.get("sale_id") if isinstance(venda, dict) else None
            return _normalizar_retorno_fiscal("imprimir_danfe", bloqueio)

        payload = montar_payload_nota_fiscal(venda)
        base_saida = pasta_saida or os.path.join(_base_runtime_dir(), "fiscais")
        os.makedirs(base_saida, exist_ok=True)
        arquivo = os.path.join(
            base_saida,
            f"DANFE_{int(payload.get('sale_id') or 0):05d}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )

        linhas = [
            "DANFE SIMPLIFICADO",
            "=================",
            f"Tipo Fiscal: {str(payload.get('fiscal_tipo') or 'nfe').upper()}",
            f"Referência: {payload.get('sale_id')}",
            f"Data: {payload.get('date')}",
            f"Total: {float(payload.get('total') or 0):.2f}",
            "",
            "Itens:",
        ]
        for idx, item in enumerate(payload.get("items") or [], start=1):
            linhas.append(
                f"{idx}. {item.get('nome_produto')} | Qtd: {item.get('quantidade')} | "
                f"Unit: {float(item.get('preco_unitario') or 0):.2f} | "
                f"Total: {float(item.get('total_item') or 0):.2f} | NCM: {item.get('ncm')}"
            )

        with open(arquivo, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")

        return {
            "ok": True,
            "modo": "acbr",
            "status": "danfe_gerado",
            "sale_id": payload.get("sale_id"),
            "arquivo": arquivo,
            "mensagem": "DANFE gerado com sucesso.",
        }
    except Exception as exc:
        retorno_erro = {
            "ok": False,
            "modo": "standalone",
            "status": "erro",
            "motivo": str(exc),
            "sale_id": venda.get("sale_id") if isinstance(venda, dict) else None,
            "mensagem": "Falha ao gerar DANFE.",
        }
        return _normalizar_retorno_fiscal("imprimir_danfe", retorno_erro)
