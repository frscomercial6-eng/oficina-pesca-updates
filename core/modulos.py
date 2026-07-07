# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""Gerenciador simples de feature flags por módulo.

Lê as permissões a partir de um arquivo config.json na raiz do projeto.
Enquanto o arquivo não existir, mantém um fallback compatível com o cenário
atual: módulo Oficina habilitado e módulo PDV desabilitado.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FeatureFlagManager:
    """Consulta módulos habilitados a partir do config.json."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parent.parent
        self.config_path = Path(config_path) if config_path else base_dir / "config.json"

    def _default_flags(self) -> dict[str, bool]:
        return {
            "oficina": True,
            "pdv": False,
        }

    def _normalize_bool(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "sim", "yes", "on", "habilitado"}
        return default

    def _load_raw_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}

        try:
            with self.config_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def get_flags(self) -> dict[str, bool]:
        defaults = self._default_flags()
        raw_config = self._load_raw_config()
        modulos = raw_config.get("modulos", {})
        if not isinstance(modulos, dict):
            modulos = {}

        return {
            "oficina": self._normalize_bool(
                modulos.get("oficina", raw_config.get("modulo_oficina", defaults["oficina"])),
                default=defaults["oficina"],
            ),
            "pdv": self._normalize_bool(
                modulos.get("pdv", raw_config.get("modulo_pdv", defaults["pdv"])),
                default=defaults["pdv"],
            ),
        }

    def tem_modulo_oficina(self) -> bool:
        return self.get_flags()["oficina"]

    def tem_modulo_pdv(self) -> bool:
        return self.get_flags()["pdv"]

    def tem_acesso(self, nome_modulo: str) -> bool:
        chave = str(nome_modulo or "").strip().lower()
        return self.get_flags().get(chave, False)


def obter_modulos_habilitados(config_path: str | Path | None = None) -> dict[str, bool]:
    return FeatureFlagManager(config_path=config_path).get_flags()


def usuario_tem_modulo_oficina(config_path: str | Path | None = None) -> bool:
    return FeatureFlagManager(config_path=config_path).tem_modulo_oficina()


def usuario_tem_modulo_pdv(config_path: str | Path | None = None) -> bool:
    return FeatureFlagManager(config_path=config_path).tem_modulo_pdv()