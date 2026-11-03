import base64
import json
import os
import sqlite3
import subprocess
import sys
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

import config
import mestre_build
from licensing._produto import INSTAL_PREFIX, LICENSE_KEY_ID, LICENSE_SCHEMA, PRODUCT
from licensing.formats import encode_envelope, signature_message
from licensing.keys import EMBEDDED_KEY_ID, EMBEDDED_PUBLIC_KEY_BASE64
from licensing.machine_identity import MachineIdentity


def _must_not_call_remote_license_service(*args, **kwargs):
    raise AssertionError("Desktop activation must not call a remote license service")


def _license_text(private_key, storage, identity, plan, expires_at):
    now = datetime.now(timezone.utc)
    payload = {
        "license_id": str(uuid.uuid4()),
        "product": PRODUCT,
        "customer_id": "test-customer",
        "installation_id": storage.get_or_create_installation_id(),
        "machine_binding": identity.as_dict(),
        "edition": "standard",
        "features": [],
        "issued_at": now.isoformat(),
        "not_before": (now - timedelta(minutes=1)).isoformat(),
        "expires_at": expires_at,
        "issuer": "local-test",
        "plano": plan,
    }
    signature = base64.b64encode(
        private_key.sign(signature_message(LICENSE_SCHEMA, LICENSE_KEY_ID, payload))
    ).decode("ascii")
    return encode_envelope(
        {
            "schema": LICENSE_SCHEMA,
            "key_id": LICENSE_KEY_ID,
            "payload": payload,
            "signature": signature,
        }
    )


def _configure_isolated_activation(tmp_path, monkeypatch, plan, expires_at):
    from licensing import LicenseStorage
    import licensing.license_verifier as verifier

    private_key = Ed25519PrivateKey.generate()
    identity = MachineIdentity(
        component_hashes={"machine_guid": "test-guid", "node_identity": "test-node"},
        required_components=("machine_guid", "node_identity"),
        minimum_matches=2,
    )
    storage_root = tmp_path / "user-data" / "licensing"
    storage = LicenseStorage(storage_root)
    license_text = _license_text(private_key, storage, identity, plan, expires_at)

    database_path = tmp_path / "test.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE configuracoes (chave TEXT PRIMARY KEY, valor TEXT)"
        )

    @contextmanager
    def isolated_db_connection():
        connection = sqlite3.connect(database_path)
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    install_dir = tmp_path / "install"
    install_dir.mkdir()
    monkeypatch.setattr(config, "_caminho_dados_licenca", lambda: str(storage_root))
    monkeypatch.setattr(config, "DIRETORIO_ATUAL", str(install_dir))
    monkeypatch.setattr(config, "get_db_connection", isolated_db_connection)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(config, "publicar_licenca_supabase", _must_not_call_remote_license_service)
    monkeypatch.setattr(config, "publicar_licenca_drive", _must_not_call_remote_license_service)
    monkeypatch.setattr(config, "obter_user_id_token_padrao", lambda: "")
    monkeypatch.setattr(verifier, "get_public_key", lambda _key_id, _trusted=None: private_key.public_key())
    monkeypatch.setattr(verifier, "collect_machine_identity", lambda *_args, **_kwargs: identity)
    return license_text, storage_root, install_dir, private_key, identity, database_path


def test_permanent_license_activation_persists_outside_install_directory(tmp_path, monkeypatch):
    expires_at = "9999-12-31T23:59:59+00:00"
    license_text, storage_root, install_dir, _private_key, _identity, _database_path = _configure_isolated_activation(
        tmp_path, monkeypatch, "PERMANENTE", expires_at
    )

    activated, message = config.ativar_licenca(license_text)

    assert activated, message
    assert not (install_dir / "licenca.key").exists()
    assert (storage_root / "license.json").read_text(encoding="utf-8").strip() == license_text
    active, _message, _customer, validity = config.obter_status_licenca()
    assert active
    assert validity == "PERMANENTE"
    assert config.obter_tipo_licenca() == "PERMANENTE"
    assert config.obter_chave_licenca_ativa() == license_text


def test_monthly_license_keeps_expiration_and_type_after_reload(tmp_path, monkeypatch):
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    expected_expiration = expires_at[:10]
    license_text, storage_root, install_dir, _private_key, _identity, _database_path = _configure_isolated_activation(
        tmp_path, monkeypatch, "MENSAL", expires_at
    )

    activated, message = config.ativar_licenca(license_text)

    assert activated, message
    assert not (install_dir / "licenca.key").exists()
    assert (storage_root / "license.json").read_text(encoding="utf-8").strip() == license_text
    active, _message, _customer, validity = config.obter_status_licenca()
    assert active
    assert validity == expected_expiration
    assert config.obter_tipo_licenca() == "MENSAL"
    assert config.obter_chave_licenca_ativa() == license_text


def test_activated_license_is_recognized_after_process_restart(tmp_path, monkeypatch):
    expires_at = "9999-12-31T23:59:59+00:00"
    license_text, storage_root, _install_dir, private_key, identity, database_path = (
        _configure_isolated_activation(tmp_path, monkeypatch, "PERMANENTE", expires_at)
    )
    activated, message = config.ativar_licenca(license_text)
    assert activated, message

    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    for name in (
        "SUPABASE_URL",
        "SUPABASE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "OFP_SUPABASE_URL",
        "OFP_SUPABASE_KEY",
    ):
        env.pop(name, None)
    env["OFP_DB_PATH"] = str(database_path)
    env["TEST_LICENSING_ROOT"] = str(storage_root)
    env["TEST_PUBLIC_KEY"] = base64.b64encode(
        private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    ).decode("ascii")
    env["TEST_MACHINE_IDENTITY"] = json.dumps(identity.as_dict())

    script = """
import base64
import json
import os
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from licensing.machine_identity import MachineIdentity
import licensing.license_verifier as verifier

public_key = Ed25519PublicKey.from_public_bytes(
    base64.b64decode(os.environ["TEST_PUBLIC_KEY"])
)
machine_data = json.loads(os.environ["TEST_MACHINE_IDENTITY"])
machine_identity = MachineIdentity(
    component_hashes=machine_data["component_hashes"],
    required_components=tuple(machine_data["required_components"]),
    minimum_matches=machine_data["minimum_matches"],
    binding_algorithm=machine_data["binding_algorithm"],
)
verifier.get_public_key = lambda *_args, **_kwargs: public_key
verifier.collect_machine_identity = lambda *_args, **_kwargs: machine_identity
import config
config._caminho_dados_licenca = lambda: os.environ["TEST_LICENSING_ROOT"]
active, message, _customer, validity = config.obter_status_licenca()
print("RESTART_STATUS=" + json.dumps({
    "active": active,
    "message": message,
    "validity": validity,
    "type": config.obter_tipo_licenca(),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result_line = next(
        (line for line in completed.stdout.splitlines() if line.startswith("RESTART_STATUS=")),
        "",
    )
    assert result_line
    result = json.loads(result_line.split("=", 1)[1])
    assert result["active"]
    assert result["validity"] == "PERMANENTE"
    assert result["type"] == "PERMANENTE"


def test_invalid_license_is_rejected_without_supabase_or_drive(tmp_path, monkeypatch):
    expires_at = "9999-12-31T23:59:59+00:00"
    license_text, storage_root, _install_dir, _private_key, _identity, _database_path = _configure_isolated_activation(
        tmp_path, monkeypatch, "PERMANENTE", expires_at
    )
    altered = json.loads(license_text)
    signature = altered["signature"]
    altered["signature"] = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered_text = encode_envelope(altered)

    activated, _message = config.ativar_licenca(tampered_text)

    assert not activated
    assert not (storage_root / "license.json").exists()


def test_license_cannot_be_activated_with_a_tampered_signature(tmp_path, monkeypatch):
    expires_at = "9999-12-31T23:59:59+00:00"
    license_text, storage_root, _install_dir, _private_key, _identity, _database_path = _configure_isolated_activation(
        tmp_path, monkeypatch, "PERMANENTE", expires_at
    )
    altered = json.loads(license_text)
    altered["payload"]["customer_id"] = "tampered-customer"
    tampered_text = encode_envelope(altered)

    activated, _message = config.ativar_licenca(tampered_text)

    assert not activated
    assert not (storage_root / "license.json").exists()


def test_official_build_explicitly_includes_the_license_verifier(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)

    hidden_imports = mestre_build._hidden_import_args()
    required_modules = (
        "licensing",
        "licensing._produto",
        "licensing.formats",
        "licensing.keys",
        "licensing.machine_identity",
        "licensing.storage",
        "licensing.license_verifier",
        "licensing.service",
        "cryptography.hazmat.primitives.asymmetric.ed25519",
    )
    included_modules = {
        hidden_imports[index + 1]
        for index, value in enumerate(hidden_imports[:-1])
        if value == "--hidden-import"
    }

    for module in required_modules:
        assert module in included_modules
    assert "cryptography" in mestre_build.PYINSTALLER_COLLECT_ALL


def test_desktop_build_resources_do_not_include_license_signing_keys():
    forbidden_fragments = (
        "license_private",
        "license_signing",
        "private_key.pem",
        "license_private_key",
    )
    packaged_paths = [
        source.lower()
        for source, _destination in mestre_build.RESOURCE_SPECS
    ] + [
        source.lower()
        for _module, source in mestre_build.LOCAL_HIDDEN_IMPORTS
    ]
    assert not any(
        fragment in packaged_path
        for fragment in forbidden_fragments
        for packaged_path in packaged_paths
    )
    assert not any(path.endswith((".pem", ".p8", ".key")) for path in packaged_paths)
    key_module = (Path(__file__).resolve().parents[1] / "licensing" / "keys.py").read_text(
        encoding="utf-8"
    )
    assert "Ed25519PrivateKey" not in key_module
    assert "BEGIN PRIVATE KEY" not in key_module


def test_official_license_identity_and_public_key_are_preserved():
    assert PRODUCT == "FRS-Oficina-Pesca"
    assert LICENSE_SCHEMA == "FRS-OFICINA-LICENSE"
    assert LICENSE_KEY_ID == "frs-oficina-license-official-v1"
    assert EMBEDDED_KEY_ID == LICENSE_KEY_ID
    assert EMBEDDED_PUBLIC_KEY_BASE64 == "XH+K6813ys86Tq3JfQTdxh++idsO5JqL4agad4skM2s="
    assert INSTAL_PREFIX == "OFP-INST-"


def test_desktop_startup_and_activation_have_no_automatic_license_sync():
    repo_root = Path(__file__).resolve().parents[1]
    for relative_path in ("login.py", "menu.py"):
        source = (repo_root / relative_path).read_text(encoding="utf-8")
        assert "sincronizar_licenca_supabase_pendente" not in source
        assert "publicar_licenca_drive" not in source
