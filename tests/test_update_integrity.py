from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import config


class FakeResponse:
    def __init__(self, content: bytes, url: str, headers: dict[str, str] | None = None):
        self.content = content
        self.url = url
        self.headers = headers or {}
        self.offset = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self.content) - self.offset
        chunk = self.content[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return self.url


class TestUpdateIntegrity(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.url = (
            "https://github.com/frscomercial6-eng/oficina-pesca-updates/"
            "releases/download/v1.0.66/Oficina_Pesca_Instalador.exe"
        )

    def release_response(self, digest: str) -> FakeResponse:
        release = {
            "tag_name": "v1.0.66",
            "assets": [
                {
                    "name": "Oficina_Pesca_Instalador.exe",
                    "browser_download_url": self.url,
                    "digest": f"sha256:{digest}",
                }
            ],
        }
        return FakeResponse(
            json.dumps(release).encode("utf-8"),
            "https://api.github.com/repos/frscomercial6-eng/oficina-pesca-updates/releases/tags/v1.0.66",
        )

    def test_release_digest_is_resolved_for_the_exact_official_asset(self):
        expected = "a" * 64
        with patch.object(
            config.urllib.request,
            "urlopen",
            return_value=self.release_response(expected),
        ):
            actual = config._obter_sha256_release_download("1.0.66", self.url)

        self.assertEqual(actual, expected)

    def test_version_check_uses_published_release_asset_digest(self):
        expected = "b" * 64
        response = self.release_response(expected)
        with patch.object(
            config.urllib.request,
            "urlopen",
            return_value=response,
        ):
            info = config.obter_info_nova_versao()

        self.assertEqual(info["versao"], "1.0.66")
        self.assertEqual(info["url_download"], self.url)
        self.assertEqual(info["sha256"], expected)

    def test_installer_hash_mismatch_blocks_execution(self):
        installer = b"MZ" + b"x" * (1024 * 1024)
        response_download = FakeResponse(
            installer,
            self.url,
            {"Content-Length": str(len(installer))},
        )
        state_file = Path(self.tempdir.name) / "update_state.json"
        fake_logger = Mock()
        with patch.object(config, "ARQUIVO_ESTADO_UPDATE", str(state_file)), patch.object(
            config.tempfile, "gettempdir", return_value=self.tempdir.name
        ), patch.object(
            config, "limpar_cache_instalacao_update", return_value=(True, "ok")
        ), patch.object(
            config, "bloqueio_loop_update_ativo", return_value=False
        ), patch.object(
            config, "get_logger", return_value=fake_logger
        ), patch.object(
            config, "_obter_sha256_release_download", return_value="a" * 64
        ), patch.object(
            config.urllib.request, "urlopen", return_value=response_download
        ), patch.object(
            config.subprocess, "Popen", side_effect=AssertionError("Installer must not launch")
        ) as launch:
            ok, message = config.executar_atualizacao(
                self.url,
                versao_alvo="1.0.66",
            )

        self.assertFalse(ok)
        self.assertIn("SHA-256", message)
        launch.assert_not_called()
        updater_root = Path(self.tempdir.name) / "oficina_pesca_update"
        self.assertEqual(list(updater_root.rglob("*.exe")), [])


if __name__ == "__main__":
    unittest.main()
