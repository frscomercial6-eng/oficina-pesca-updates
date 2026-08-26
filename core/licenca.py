# -*- coding: utf-8 -*-
"""Helpers de licença isolados para reduzir acoplamento do menu."""

from __future__ import annotations

from config import (
    obter_status_acesso_centralizado,
    obter_tipo_licenca,
)


def obter_info_licenca_visual(role: str = "") -> tuple[str, str]:
    """Retorna texto e cor padronizados para exibição de licença na UI."""
    try:
        status = obter_status_acesso_centralizado() or {}
        licenca_ativa = bool(status.get("licenca_ativa"))
        trial_ativo = bool(status.get("trial_ativo"))
        validade = str(status.get("validade") or "").strip().upper()

        if trial_ativo:
            tipo_exibicao = "Trial"
            cor = "#f1c40f"
        elif licenca_ativa:
            tipo_exibicao = "Permanente" if validade == "PERMANENTE" else "Mensal"
            cor = "#2ecc71"
        else:
            tipo = str(obter_tipo_licenca() or "").strip().upper()
            if tipo == "TRIAL":
                tipo_exibicao = "Trial"
                cor = "#f1c40f"
            elif tipo == "PERMANENTE":
                tipo_exibicao = "Permanente"
                cor = "#2ecc71"
            elif tipo in {"MENSAL", "ATIVA", "TOKEN"}:
                tipo_exibicao = "Mensal"
                cor = "#2ecc71"
            else:
                tipo_exibicao = "Inativa"
                cor = "#e74c3c"

        return f"Licença: {tipo_exibicao}", cor
    except Exception:
        return "Licença: indisponível", "#6b7280"
