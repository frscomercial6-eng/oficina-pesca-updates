"""Carregamento seguro da chave pública Ed25519 confiável do Oficina.

O cliente nunca carrega chave privada. Lista distribuída junto do aplicativo;
pode ser ampliada em rotação futura sem alterar o schema.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ._produto import LICENSE_KEY_ID
from .errors import KeyConfigurationError

_TRUSTED_KEYS_FILE = Path(__file__).with_name("trusted_keys.json")


def load_trusted_keys(path: str | Path | None = None) -> dict[str, str]:
    target = Path(path) if path else _TRUSTED_KEYS_FILE
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise KeyConfigurationError("Lista de chaves públicas não encontrada.") from exc
    except Exception as exc:
        raise KeyConfigurationError("Lista de chaves públicas inválida.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), dict):
        raise KeyConfigurationError("Estrutura de chaves públicas inválida.")
    return {str(k): str(v) for k, v in payload["keys"].items() if str(v).strip()}


def get_public_key(
    key_id: str, trusted_keys: dict[str, str] | None = None
) -> Ed25519PublicKey:
    keys = trusted_keys if trusted_keys is not None else load_trusted_keys()
    encoded = str(keys.get(str(key_id or "").strip()) or "").strip()
    if not encoded:
        raise KeyConfigurationError(f"Chave pública confiável não encontrada: {key_id}")
    try:
        raw = base64.b64decode(encoded, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise KeyConfigurationError(f"Chave pública inválida: {key_id}") from exc


def public_key_oficial() -> Ed25519PublicKey:
    return get_public_key(LICENSE_KEY_ID)
