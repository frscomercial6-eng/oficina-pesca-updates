"""Identidade de instalação e componentes fortes do Windows (Oficina).

Manti a identidade legada ``OFP-INST`` (decisao E0 n.3) e adiciona vinculo
multi-componente compativel com o protocolo do FRS Mercado. O material de cada
hash e prefixado por ``FRS-OFICINA-MACHINE``; o componente ``node_identity`` e
sempre presente e deriva da mesma base do Hardware ID legado.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import uuid
from dataclasses import dataclass

from ._produto import BINDING_ALGORITHM, INSTAL_PREFIX, MACHINE_MATERIAL_PREFIX
from .errors import LicenseError

_INVALID_VALUES = {
    "", "0", "00000000-0000-0000-0000-000000000000",
    "BASE BOARD SERIAL NUMBER", "DEFAULT STRING", "FILL BY O.E.M.",
    "NOT APPLICABLE", "NOT AVAILABLE", "NOT SPECIFIED", "NONE",
    "SYSTEM SERIAL NUMBER", "TO BE FILLED BY O.E.M.", "UNKNOWN", "DEFAULT",
}

_COMPONENTES_WINDOWS = (
    "machine_guid", "smbios_uuid", "bios_serial", "baseboard_serial",
    "tpm_ek_public_hash",
)


@dataclass(frozen=True)
class MachineIdentity:
    component_hashes: dict[str, str]
    required_components: tuple[str, ...]
    minimum_matches: int
    binding_algorithm: str = BINDING_ALGORITHM

    def as_dict(self) -> dict:
        return {
            "binding_algorithm": self.binding_algorithm,
            "component_hashes": dict(sorted(self.component_hashes.items())),
            "required_components": list(self.required_components),
            "minimum_matches": self.minimum_matches,
        }


def legacy_node_material() -> str:
    """Base deterministica herdada do Hardware ID legado (uuid.getnode|node)."""
    try:
        node = str(uuid.getnode())
    except Exception:
        node = ""
    try:
        host = platform.node() or ""
    except Exception:
        host = ""
    return f"{node}|{host}"


def legacy_installation_key() -> str:
    """Identidade legada ``OFP-INST-`` + 24 hex (igual ao obter_chave_instalacao)."""
    digest = hashlib.sha256(legacy_node_material().encode("utf-8")).hexdigest().upper()
    return f"{INSTAL_PREFIX}{digest[:24]}"


def _normalize_component(name: str, value: object) -> str | None:
    raw = str(value or "").strip().upper()
    text = re.sub(r"[\s-]+", "", raw)
    invalid = {re.sub(r"[\s-]+", "", item) for item in _INVALID_VALUES}
    if not text or text in invalid or text == "0" * len(text):
        return None
    if name == "machine_guid":
        try:
            return str(uuid.UUID(text)).upper()
        except Exception:
            return None
    return text or None


def _component_hash(name: str, normalized: str) -> str:
    material = f"{MACHINE_MATERIAL_PREFIX}:{name}:{normalized}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _windows_components() -> dict[str, str]:
    if os.name != "nt":
        raise LicenseError("Identidade robusta está disponível apenas no Windows.")
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$machineGuid = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid
$product = Get-CimInstance Win32_ComputerSystemProduct
$bios = Get-CimInstance Win32_BIOS
$board = Get-CimInstance Win32_BaseBoard
$tpm = Get-CimInstance -Namespace root\CIMV2\Security\MicrosoftTpm -ClassName Win32_Tpm
$tpmPublic = $null
if ($tpm -and $tpm.PSObject.Properties.Name -contains 'PublicKey') { $tpmPublic = $tpm.PublicKey }
[pscustomobject]@{
  machine_guid = $machineGuid
  smbios_uuid = $product.UUID
  bios_serial = $bios.SerialNumber
  baseboard_serial = $board.SerialNumber
  tpm_ek_public_hash = $tpmPublic
} | ConvertTo-Json -Compress
"""
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=25, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = json.loads(completed.stdout or "{}")
    except Exception as exc:
        raise LicenseError("Não foi possível coletar a identidade do Windows.") from exc
    if not isinstance(raw, dict):
        raise LicenseError("Resposta de identidade do Windows inválida.")
    return {str(k): str(v) for k, v in raw.items()}


def collect_machine_identity(
    component_collector=None,
) -> MachineIdentity:
    raw = component_collector() if component_collector else _windows_components()
    hashes: dict[str, str] = {}
    # Componente sempre presente: identidade legada (node|host).
    hashes["node_identity"] = _component_hash(
        "node_identity", legacy_node_material().upper()
    )
    for name in _COMPONENTES_WINDOWS:
        normalized = _normalize_component(name, raw.get(name))
        if normalized:
            hashes[name] = _component_hash(name, normalized)

    hardware = [n for n in _COMPONENTES_WINDOWS if n in hashes]
    if "tpm_ek_public_hash" in hashes:
        required = ("tpm_ek_public_hash", *hardware[:2], "node_identity")
        minimum = 2
    elif len(hardware) >= 2:
        required = (*hardware[:3], "node_identity")
        minimum = 2
    else:
        required = ("node_identity", *hardware)
        minimum = 2
    return MachineIdentity(hashes, tuple(required), minimum)

