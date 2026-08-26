# -*- coding: utf-8 -*-
"""Regras de negócio de O.S. isoladas da interface gráfica."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from config import enviar_registro_os_central_silencioso, get_logger
from core.financeiro.calculos import OSCalculator
from core.os_repository import salvar_orcamento_aguardo_oficial
from status_os import STATUS_ORCAMENTO, normalizar_status_orcamento

logger = get_logger()


def _subtotal_equipamento_payload(equipamento: dict[str, Any]) -> float:
    itens_ativos: list[float] = []
    for item in (equipamento.get("itens") or []):
        if not isinstance(item, (list, tuple)) or len(item) < 4:
            continue
        status_item = str(item[4] if len(item) > 4 else "ATIVO").strip().upper()
        if status_item == "REPROVADO":
            continue
        itens_ativos.append(float(item[3] or 0))

    return OSCalculator.calcular_total(
        itens=itens_ativos,
        desconto=equipamento.get("desconto", 0),
        frete=equipamento.get("frete", 0),
        adicional=equipamento.get("opcional", 0),
    )


def montar_payload_os(
    os_id: int,
    cliente: str,
    telefone: str,
    endereco: str,
    equipamentos: list[dict[str, Any]],
    status: str = STATUS_ORCAMENTO,
    forma_pagamento: str | None = None,
) -> dict[str, Any]:
    """Monta o payload completo de uma O.S. sem depender da interface."""
    cliente_final = str(cliente or "").strip().upper()
    telefone_final = str(telefone or "").strip()
    endereco_final = str(endereco or "").strip()
    equipamentos_validos = [
        eq for eq in (equipamentos or [])
        if isinstance(eq, dict) and (eq.get("equipamento") or eq.get("defeito") or eq.get("itens"))
    ]

    if not cliente_final:
        cliente_final = "CLIENTE NÃO INFORMADO"

    itens_flat: list[list[str]] = []
    total_os = 0.0
    for eq in equipamentos_validos:
        total_os += _subtotal_equipamento_payload(eq)
        for item in eq.get("itens") or []:
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                status_item = str(item[4] if len(item) > 4 else "ATIVO").strip().upper()
                itens_flat.append([str(item[0]), str(item[1]), str(item[2]), str(item[3]), status_item])

    primeiro_item = equipamentos_validos[0] if equipamentos_validos else {}
    resumo_equipamento_defeito = f"{str(primeiro_item.get('equipamento', '') or '').strip().upper()} - {str(primeiro_item.get('defeito', '') or '').strip().upper()}".strip(" -")
    status_final = normalizar_status_orcamento(status)

    sinal = OSCalculator.calcular_sinal_por_forma(total_os, forma_pagamento) if status_final == "APROVADO" else 0.0
    saldo = float(total_os - sinal)

    return {
        "cliente": cliente_final,
        "telefone_cliente_whatsapp": telefone_final,
        "equipamento": primeiro_item.get("equipamento", ""),
        "defeito": primeiro_item.get("defeito", ""),
        "resumo_equipamento_defeito": resumo_equipamento_defeito,
        "total": total_os,
        "status": status_final,
        "data": datetime.now().strftime("%d/%m/%Y"),
        "itens_json": json.dumps(itens_flat),
        "dados_adicionais": json.dumps({
            "modo_os_por_cliente": True,
            "cliente_telefone": telefone_final,
            "cliente_endereco": endereco_final,
            "resumo_equipamento_defeito": resumo_equipamento_defeito,
            "equipamentos": equipamentos_validos,
            "equipamento_ativo_idx": None,
            "historico_itens_reprovados": [],
            "opcional": float(primeiro_item.get("opcional", 0.0)),
            "frete": float(primeiro_item.get("frete", 0.0)),
            "desconto": float(primeiro_item.get("desconto", 0.0)),
            "prazo": str(primeiro_item.get("prazo", "7 dias úteis")),
            "obs": str(primeiro_item.get("obs", "")),
            "forma_de_pagamento": forma_pagamento,
        }),
        "sinal": sinal,
        "saldo": saldo,
    }


def salvar_os_completa(
    os_id: int,
    cliente: str,
    telefone: str,
    endereco: str,
    equipamentos: list[dict[str, Any]],
    status: str = STATUS_ORCAMENTO,
    forma_pagamento: str | None = None,
    on_save_callback=None,
) -> dict[str, Any]:
    """Salva uma O.S. completa usando a camada de serviço isolada."""
    dados = montar_payload_os(
        os_id=os_id,
        cliente=cliente,
        telefone=telefone,
        endereco=endereco,
        equipamentos=equipamentos,
        status=status,
        forma_pagamento=forma_pagamento,
    )

    salvar_orcamento_aguardo_oficial(os_id, dados, sinal=dados["sinal"], saldo=dados["saldo"])

    try:
        enviar_registro_os_central_silencioso(
            {
                "id": int(os_id),
                "cliente": dados["cliente"],
                "status": dados["status"],
                "total": float(dados["total"]),
            },
            operacao="upsert",
        )
    except Exception:
        logger.exception("Falha ao enfileirar sincronização central da O.S. %s.", os_id)

    if callable(on_save_callback):
        on_save_callback()

    return dados
