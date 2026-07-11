# -*- coding: utf-8 -*-
"""Adaptador para comunicação por arquivos com ACBrMonitor."""

import os
import time


def _base_runtime_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


PASTA_PADRAO_ACBR = os.path.join(_base_runtime_dir(), "config_fiscal", "acbr_monitor")
PASTA_ENTRADA = os.path.join(PASTA_PADRAO_ACBR, "ENT.txt")
PASTA_SAIDA = os.path.join(PASTA_PADRAO_ACBR, "SAI.txt")


def _resolver_caminhos(parametros: dict | None = None) -> tuple[str, str]:
    cfg = parametros if isinstance(parametros, dict) else {}

    entrada = str(cfg.get("acbr_entrada") or "").strip()
    saida = str(cfg.get("acbr_saida") or "").strip()
    pasta = str(cfg.get("acbr_monitor_path") or cfg.get("acbr_path") or "").strip()

    if pasta:
        if not entrada:
            entrada = os.path.join(pasta, "ENT.txt")
        if not saida:
            saida = os.path.join(pasta, "SAI.txt")

    entrada = entrada or os.environ.get("OFP_ACBR_ENTRADA", "").strip() or PASTA_ENTRADA
    saida = saida or os.environ.get("OFP_ACBR_SAIDA", "").strip() or PASTA_SAIDA
    return entrada, saida


def ler_ncm_produto(produto: dict) -> str:
    """Lê e normaliza o NCM de um produto para uso na comunicação fiscal."""
    ncm_bruto = str((produto or {}).get("ncm", "") or "")
    return "".join(ch for ch in ncm_bruto if ch.isdigit())[:8]


def enviar_comando_acbr_monitor(comando: str, parametros: dict | None = None, timeout_seg: float = 8.0) -> dict:
    """Envia um comando ao ACBrMonitor e tenta coletar o retorno no SAI.txt."""
    cmd = str(comando or "").strip()
    if not cmd:
        return {"ok": False, "motivo": "comando_vazio"}

    caminho_entrada, caminho_saida = _resolver_caminhos(parametros)

    pasta_destino = os.path.dirname(caminho_entrada)
    if pasta_destino:
        os.makedirs(pasta_destino, exist_ok=True)

    try:
        before_saida_mtime = os.path.getmtime(caminho_saida) if os.path.exists(caminho_saida) else 0.0
    except Exception:
        before_saida_mtime = 0.0

    with open(caminho_entrada, "w", encoding="utf-8") as arquivo_entrada:
        arquivo_entrada.write(cmd + "\n")

    limite = max(1.0, float(timeout_seg or 8.0))
    t0 = time.time()
    resposta = ""
    while (time.time() - t0) < limite:
        try:
            if os.path.exists(caminho_saida):
                atual_mtime = os.path.getmtime(caminho_saida)
                if atual_mtime >= before_saida_mtime:
                    with open(caminho_saida, "r", encoding="utf-8", errors="ignore") as arquivo_saida:
                        resposta = arquivo_saida.read().strip()
                    if resposta:
                        break
        except Exception:
            pass
        time.sleep(0.2)

    ok = bool(resposta) and "erro" not in resposta.lower()
    return {
        "ok": ok,
        "entrada": caminho_entrada,
        "saida": caminho_saida,
        "comando": cmd,
        "resposta": resposta,
        "motivo": "ok" if ok else "sem_resposta_ou_erro",
    }


def consultar_status_acbr_monitor(parametros: dict | None = None) -> dict:
    return enviar_comando_acbr_monitor("NFe.StatusServico", parametros=parametros)


def verificar_status_acbr() -> str:
    """Compatibilidade: mantém retorno antigo com caminho de entrada."""
    caminho_entrada, _ = _resolver_caminhos(None)
    pasta_destino = os.path.dirname(caminho_entrada)
    if pasta_destino:
        os.makedirs(pasta_destino, exist_ok=True)
    with open(caminho_entrada, "w", encoding="utf-8") as arquivo_entrada:
        arquivo_entrada.write("NFe.StatusServico\n")

    return caminho_entrada
