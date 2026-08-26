from __future__ import annotations

from core.os_service import _subtotal_equipamento_payload, montar_payload_os


def test_subtotal_equipamento_payload_ignores_reprovados() -> None:
    equipamento = {
        "itens": [
            ["peça", "desc", "tipo", 10, "ATIVO"],
            ["peça", "desc", "tipo", 20, "REPROVADO"],
        ],
        "desconto": 5,
        "frete": 3,
        "opcional": 2,
    }

    assert _subtotal_equipamento_payload(equipamento) == 10


def test_montar_payload_os_calcula_total_e_status() -> None:
    payload = montar_payload_os(
        os_id=7,
        cliente="joão",
        telefone="11999999999",
        endereco="rua x",
        equipamentos=[
            {
                "equipamento": "celular",
                "defeito": "tela quebrada",
                "itens": [["p1", "d1", "tipo", 50, "ATIVO"]],
                "desconto": 0,
                "frete": 0,
                "opcional": 0,
            }
        ],
        status="APROVADO",
        forma_pagamento="vista",
    )

    assert payload["total"] == 50.0
    assert payload["status"] == "APROVADO"
    assert payload["sinal"] == 25.0
    assert payload["saldo"] == 25.0
