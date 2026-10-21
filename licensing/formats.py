"""Envelope assinado Ed25519 de 4 campos — produto Oficina de Pesca.

Envelope: ``{schema, key_id, payload, signature}``. Mensagem assinada =
``canonical_json({schema, key_id, payload})``; ``signature`` nunca entra.
"""
from __future__ import annotations

import base64
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from ._produto import LICENSE_KEY_ID, LICENSE_SCHEMA
from .canonical_json import canonical_json_bytes
from .errors import InvalidLicenseError

_ENVELOPE_FIELDS = {"schema", "key_id", "payload", "signature"}


def parse_document(text_or_bytes: str | bytes) -> dict[str, Any]:
    try:
        raw = text_or_bytes.decode("utf-8") if isinstance(text_or_bytes, bytes) else text_or_bytes
        payload = json.loads(str(raw).strip())
    except Exception as exc:
        raise InvalidLicenseError("Documento de licença não é um JSON válido.") from exc
    if not isinstance(payload, dict):
        raise InvalidLicenseError("Documento de licença deve ser um objeto JSON.")
    return payload


def signature_message(schema: str, key_id: str, payload: dict[str, Any]) -> bytes:
    return canonical_json_bytes({"schema": schema, "key_id": key_id, "payload": payload})


def verify_envelope(
    envelope: dict[str, Any],
    public_key: Ed25519PublicKey,
) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise InvalidLicenseError("Envelope de licença deve ser um objeto.")
    if set(envelope) != _ENVELOPE_FIELDS:
        raise InvalidLicenseError("Envelope contém campos não assinados ou ausentes.")
    schema = str(envelope.get("schema") or "").strip()
    key_id = str(envelope.get("key_id") or "").strip()
    payload = envelope.get("payload")
    signature = str(envelope.get("signature") or "").strip()
    if schema != LICENSE_SCHEMA:
        raise InvalidLicenseError(f"Schema inválido: {schema or 'ausente'}.")
    if key_id != LICENSE_KEY_ID:
        raise InvalidLicenseError("Licença emitida com chave de outro produto.")
    if not isinstance(payload, dict) or not signature:
        raise InvalidLicenseError("Envelope de licença incompleto.")
    try:
        raw_signature = base64.b64decode(signature, validate=True)
    except Exception as exc:
        raise InvalidLicenseError("Assinatura não está em Base64 válido.") from exc
    try:
        public_key.verify(raw_signature, signature_message(schema, key_id, payload))
    except InvalidSignature as exc:
        raise InvalidLicenseError("Assinatura da licença inválida.") from exc
    except Exception as exc:
        raise InvalidLicenseError("Não foi possível verificar a assinatura.") from exc
    return dict(payload)


def encode_envelope(envelope: dict[str, Any]) -> str:
    return json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
