"""Licenciamento Ed25519 fail-closed do Oficina de Pesca.

Pacote de VERIFICACAO distribuido junto do aplicativo. Contem somente a chave
PUBLICA de confianca (``trusted_keys.json``); nenhuma chave privada de emissao
existe ou e importada aqui. A emissao acontece no Gerador Unico FRS, offline.

Identidade legada ``OFP-INST`` preservada (decisao E0 n.3); vinculo
multi-componente compativel com o protocolo do FRS Mercado.
"""
from .errors import (
    ClockRollbackError,
    ExpiredLicenseError,
    KeyConfigurationError,
    LicenseError,
    MachineMismatchError,
    RevokedLicenseError,
)
from .license_verifier import LicenseValidation, LicenseVerifier
from .machine_identity import legacy_installation_key
from .service import LicenseService, LicenseStatus, verificar_para_app
from .storage import LicenseStorage

__all__ = [
    "ClockRollbackError",
    "ExpiredLicenseError",
    "KeyConfigurationError",
    "LicenseError",
    "LicenseService",
    "LicenseStatus",
    "LicenseStorage",
    "LicenseValidation",
    "LicenseVerifier",
    "MachineMismatchError",
    "RevokedLicenseError",
    "legacy_installation_key",
    "verificar_para_app",
]
