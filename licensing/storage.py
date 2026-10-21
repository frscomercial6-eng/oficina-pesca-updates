"""Armazenamento local atômico do licenciamento (separado do oficina.db).

A raiz é informada pelo chamador (config.py passa o diretório de dados do
usuário). O padrão, quando ausente, segue ``APPDATA/OficinaDePesca/licensing``
— sem importar ``config`` (evita import circular).
"""
from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from .canonical_json import canonical_json_text
from .errors import StorageError


def _default_root() -> Path:
    env = str(os.environ.get("OFP_LICENSING_DIR", "")).strip()
    if env:
        return Path(env)
    base = (
        os.environ.get("APPDATA")
        or os.environ.get("LOCALAPPDATA")
        or os.environ.get("TEMP")
        or str(Path(__file__).resolve().parent.parent)
    )
    return Path(base) / "OficinaDePesca" / "licensing"


class LicenseStorage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root else _default_root()
        self.license_path = self.root / "license.json"
        self.challenge_path = self.root / "challenge.json"
        self.clock_path = self.root / "clock.json"
        self.installation_path = self.root / "installation_id"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def _atomic_write_text(self, path: Path, text: str) -> None:
        self.ensure()
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(self.root)
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(str(temp_path), str(path))
        except Exception as exc:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise StorageError(f"Falha ao gravar {path.name}.") from exc

    def write_json(self, path: Path, payload: Any) -> None:
        self._atomic_write_text(path, canonical_json_text(payload) + "\n")

    def read_json(self, path: Path) -> dict:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except Exception as exc:
            raise StorageError(f"Arquivo inválido: {path.name}.") from exc
        if not isinstance(value, dict):
            raise StorageError(f"Estrutura inválida: {path.name}.")
        return value

    def save_license(self, text: str) -> None:
        self._atomic_write_text(self.license_path, str(text).strip() + "\n")

    def load_license(self) -> str | None:
        try:
            return self.license_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        except Exception as exc:
            raise StorageError(f"Arquivo de licença corrompido: {self.license_path.name}.") from exc

    def save_challenge(self, payload: dict) -> None:
        self.write_json(self.challenge_path, payload)

    def load_challenge(self) -> dict:
        return self.read_json(self.challenge_path)

    def get_or_create_installation_id(self) -> str:
        """Identidade estável da instalação (legada OFP-INST, decidida em E0)."""
        from .machine_identity import legacy_installation_key
        return legacy_installation_key()
