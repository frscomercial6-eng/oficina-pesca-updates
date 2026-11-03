"""Carregamento seguro da chave pública Ed25519 confiável do Oficina.

A chave pública oficial está embutida neste módulo como fonte de confiança
definitiva. O aplicativo pode validar licenças mesmo quando o arquivo
``trusted_keys.json`` não estiver disponível externamente.

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

# Chave pública oficial embutida — fonte definitiva de confiança
# Esta chave não deve ser alterada sem nova versão do aplicativo
EMBEDDED_PUBLIC_KEY_BASE64 = "XH+K6813ys86Tq3JfQTdxh++idsO5JqL4agad4skM2s="
EMBEDDED_KEY_ID = "frs-oficina-license-official-v1"

_TRUSTED_KEYS_FILE = Path(__file__).with_name("trusted_keys.json")


def load_trusted_keys(path: str | Path | None = None) -> dict[str, str]:
    """Carrega chaves públicas do arquivo externo (opcional).

    O arquivo ``trusted_keys.json`` não é mais obrigatório para validação,
    pois a chave embutida serve como fonte oficial. Contudo, continua disponível
    para compatibilidade com chaves adicionais ou rotação futura.
    """
    target = Path(path) if path else _TRUSTED_KEYS_FILE
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        # Arquivo não existente não é erro crítico se chave embutida existir
        raise KeyConfigurationError("Lista de chaves públicas não encontrada.") from exc
    except Exception as exc:
        raise KeyConfigurationError("Lista de chaves públicas inválida.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keys"), dict):
        raise KeyConfigurationError("Estrutura de chaves públicas inválida.")
    return {str(k): str(v) for k, v in payload["keys"].items() if str(v).strip()}


def _get_key_from_embedding(key_id: str) -> Ed25519PublicKey:
    """Obtém chave a partir do embedding interno (fonte oficial)."""
    if str(key_id).strip() != EMBEDDED_KEY_ID.strip():
        raise KeyConfigurationError(f"Chave pública confiável não encontrada: {key_id}")
    try:
        raw = base64.b64decode(EMBEDDED_PUBLIC_KEY_BASE64, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise KeyConfigurationError(f"Chave pública inválida: {key_id}") from exc


def get_public_key(
    key_id: str, trusted_keys: dict[str, str] | None = None
) -> Ed25519PublicKey:
    """Obtém chave pública pelo key_id.

    Primeiro tenta a chave embutida (fonte oficial, não depende de arquivo externo).
    Fallback para o arquivo ``trusted_keys.json`` apenas se o key_id for diferente
    do oficial ou se houver chaves extras solicitadas.
    """
    # Tenta chave embutida primeiro (fonte oficial, não depende de arquivo externo)
    try:
        return _get_key_from_embedding(key_id)
    except KeyConfigurationError:
        pass

    # Fallback para arquivo confiáveis se a chave embutida não corresponder
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
    """Retorna a chave pública oficial embutida do Oficina.

    Esta é a fonte definitiva de confiança para verificação de licenças.
    Funciona independentemente da existência do arquivo ``trusted_keys.json``.
    """
    return _get_key_from_embedding(LICENSE_KEY_ID)
