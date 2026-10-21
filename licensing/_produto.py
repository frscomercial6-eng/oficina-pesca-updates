"""Constantes do produto Oficina de Pesca para o pacote de licenciamento.

Pacote de VERIFICACAO distribuido junto do aplicativo. Contem somente a chave
PUBLICA de confianca; nenhuma chave privada existe ou e importada aqui.
"""
from __future__ import annotations

PRODUCT = "FRS-Oficina-Pesca"
LICENSE_SCHEMA = "FRS-OFICINA-LICENSE"
CHALLENGE_SCHEMA = "FRS-OFICINA-CHALLENGE"
REVOCATION_SCHEMA = "FRS-OFICINA-REVOCATIONS"
TRUSTED_KEYS_SCHEMA = "FRS-OFICINA-TRUSTED-KEYS-V1"
LICENSE_KEY_ID = "frs-oficina-license-official-v1"
BINDING_ALGORITHM = "FRS-MACHINE-V1"
MACHINE_MATERIAL_PREFIX = "FRS-OFICINA-MACHINE"
#: Identidade legada preservada (decisao E0 n.3): OFP-INST- + 24 hex.
INSTAL_PREFIX = "OFP-INST-"
