from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import MethodType
from unittest.mock import patch

import config
import mestre_build
import tela_os


class FakeClipboardWindow:
    def __init__(self, value: str = ""):
        self.value = value
        self.callbacks = []
        self.saved_links = []
        self._modo_escuta_pdf_clipboard = MethodType(
            tela_os.FrmOS._modo_escuta_pdf_clipboard, self
        )

    def clipboard_get(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value

    def after(self, delay: int, callback):
        self.callbacks.append((delay, callback))

    def _salvar_pdf_silencioso(self, link: str):
        self.saved_links.append(link)


class TestStartupDatabaseSchema(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.database_path = Path(self.tempdir.name) / "oficina.db"

    def initialize_at_temp_database(self):
        with patch.object(config, "CAMINHO_BANCO", str(self.database_path)), patch.object(
            config,
            "_restaurar_banco_por_backup_se_necessario",
            return_value=(False, "Nenhum backup de teste."),
        ):
            config.inicializar_banco()
            config.inicializar_banco()

    def test_fresh_database_creates_config_and_whatsapp_schema_idempotently(self):
        self.initialize_at_temp_database()

        conn = sqlite3.connect(self.database_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(orcamentos_aguardo)")
            }
        finally:
            conn.close()

        self.assertIn("configuracoes", tables)
        self.assertIn("orcamentos_aguardo", tables)
        self.assertIn("telefone_cliente_whatsapp", columns)
        self.assertIn("resumo_equipamento_defeito", columns)

    def test_legacy_database_migration_preserves_existing_os_data(self):
        conn = sqlite3.connect(self.database_path)
        try:
            conn.execute(
                """
                CREATE TABLE orcamentos_aguardo (
                    id INTEGER PRIMARY KEY,
                    cliente TEXT,
                    equipamento TEXT,
                    defeito TEXT,
                    valor_total REAL,
                    sinal REAL,
                    saldo REAL,
                    status TEXT,
                    data TEXT,
                    itens_detalhes TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT INTO orcamentos_aguardo
                    (id, cliente, equipamento, defeito, valor_total, sinal, saldo, status, data, itens_detalhes)
                VALUES (701, 'Cliente preservado', 'Motor', 'Revisão', 120, 0, 120, 'ORÇAMENTO', '03/11/2026', '[]')
                """
            )
            conn.commit()
        finally:
            conn.close()

        self.initialize_at_temp_database()

        conn = sqlite3.connect(self.database_path)
        try:
            row = conn.execute(
                "SELECT id, cliente FROM orcamentos_aguardo WHERE id=701"
            ).fetchone()
            columns = {
                item[1] for item in conn.execute("PRAGMA table_info(orcamentos_aguardo)")
            }
        finally:
            conn.close()

        self.assertEqual(row, (701, "Cliente preservado"))
        self.assertIn("telefone_cliente_whatsapp", columns)
        self.assertIn("resumo_equipamento_defeito", columns)

    def test_corrupt_database_is_preserved_and_not_replaced_with_empty_database(self):
        self.database_path.write_bytes(b"not a sqlite database")
        existing_quarantine = Path(self.tempdir.name) / "oficina_corrompido_20200101_000000.db"
        existing_quarantine.write_bytes(b"older preserved backup")

        with patch.object(config, "CAMINHO_BANCO", str(self.database_path)), patch.object(
            config,
            "_restaurar_banco_por_backup_se_necessario",
            return_value=(False, "Nenhum backup válido."),
        ):
            with self.assertRaisesRegex(sqlite3.DatabaseError, "foi preservado"):
                config.inicializar_banco()

        self.assertFalse(self.database_path.exists())
        self.assertEqual(existing_quarantine.read_bytes(), b"older preserved backup")
        quarantined = list(Path(self.tempdir.name).glob("oficina_corrompido_*.db"))
        self.assertEqual(len(quarantined), 2)
        self.assertIn(b"not a sqlite database", {path.read_bytes() for path in quarantined})


class TestEscutaClipboard(unittest.TestCase):
    def test_uses_native_clipboard_and_does_not_repeat_same_pdf(self):
        window = FakeClipboardWindow("https://example.test/receipt.pdf")

        window._modo_escuta_pdf_clipboard()
        window._modo_escuta_pdf_clipboard()

        self.assertEqual(window.saved_links, ["https://example.test/receipt.pdf"])
        self.assertEqual([delay for delay, _ in window.callbacks], [2000, 2000])

    def test_empty_clipboard_is_not_logged_as_an_error(self):
        window = FakeClipboardWindow(tela_os.tk.TclError("no text available"))

        with patch.object(tela_os.logger, "warning") as warning:
            window._modo_escuta_pdf_clipboard()

        warning.assert_not_called()
        self.assertEqual(window.callbacks[0][0], 2000)

    def test_clipboard_failure_is_logged_once_and_retried_less_often(self):
        window = FakeClipboardWindow(RuntimeError("clipboard unavailable"))

        with patch.object(tela_os.logger, "warning") as warning:
            window._modo_escuta_pdf_clipboard()
            window._modo_escuta_pdf_clipboard()

        warning.assert_called_once()
        self.assertEqual([delay for delay, _ in window.callbacks], [10000, 10000])


class FakeDatabaseConnection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self

    def execute(self, *_args):
        return None

    def commit(self):
        return None


class TestDriveAuthenticationIsolation(unittest.TestCase):
    def test_local_valid_license_does_not_require_google_drive_authentication(self):
        with patch.object(
            config,
            "_extrair_licenca_de_arquivo",
            return_value=("local-license", "", "", ""),
        ), patch.object(
            config,
            "validar_chave_licenca",
            return_value=(True, "valid", {"val": "PERMANENTE", "cliente": "test", "tipo": "PERMANENTE"}),
        ), patch.object(
            config,
            "get_db_connection",
            return_value=FakeDatabaseConnection(),
        ), patch.object(
            config,
            "_obter_credenciais_google_drive_usuario",
            side_effect=AssertionError("Local license validation must not require Drive OAuth"),
        ):
            active, message, _customer, validity = config.obter_status_licenca()

        self.assertTrue(active)
        self.assertIn("válida", message.lower())
        self.assertEqual(validity, "PERMANENTE")

    def test_missing_drive_oauth_is_reported_as_optional_connection_state(self):
        with patch.object(config, "_token_google_drive_usuario_paths", return_value=[]), patch.object(
            config,
            "_verificar_arquivo_credenciais_google_drive",
            return_value=(True, "oauth-client-configured"),
        ):
            credentials, message = config._obter_credenciais_google_drive_usuario(
                interativo=False
            )

        self.assertIsNone(credentials)
        self.assertIn("não autenticado no Google Drive", message)
        self.assertNotIn("licença", message.lower())


class TestBuildCredentialValidation(unittest.TestCase):
    def test_build_rejects_missing_integration_credentials(self):
        with tempfile.TemporaryDirectory() as tempdir:
            oauth = Path(tempdir) / "client_secret_desktop.json"
            firebase = Path(tempdir) / "google-services.json"

            problems = mestre_build._validar_credenciais_integracoes(
                str(oauth),
                str(firebase),
            )

        self.assertEqual(len(problems), 2)
        self.assertTrue(all("ausente" in item.lower() for item in problems))

    def test_build_rejects_placeholder_integration_credentials(self):
        with tempfile.TemporaryDirectory() as tempdir:
            oauth = Path(tempdir) / "client_secret_desktop.json"
            firebase = Path(tempdir) / "google-services.json"
            oauth.write_text(
                '{"installed":{"client_id":"placeholder.apps.googleusercontent.com",'
                '"client_secret":"placeholder"}}',
                encoding="utf-8",
            )
            firebase.write_text(
                '{"project_info":{"project_id":"oficina-pesca-ci"},'
                '"client":[{"client_info":{"android_client_info":'
                '{"package_name":"com.frs.oficinadepesca"}},'
                '"api_key":[{"current_key":"placeholder"}]}]}',
                encoding="utf-8",
            )

            problems = mestre_build._validar_credenciais_integracoes(
                str(oauth),
                str(firebase),
            )

        self.assertEqual(len(problems), 2)
        self.assertTrue(all("placeholder" not in item.lower() for item in problems))

    def test_windows_preflight_does_not_require_android_firebase(self):
        with tempfile.TemporaryDirectory() as tempdir:
            oauth = Path(tempdir) / "client_secret_desktop.json"
            firebase = Path(tempdir) / "google-services.json"
            oauth.write_text(
                '{"installed":{"client_id":"desktop.apps.googleusercontent.com",'
                '"client_secret":"configured"}}',
                encoding="utf-8",
            )

            with patch.dict("os.environ", {"SUPABASE_URL": "", "SUPABASE_KEY": ""}):
                problems = mestre_build._validar_credenciais_integracoes(
                    str(oauth),
                    str(firebase),
                    target="windows",
                )

        self.assertEqual(problems, [])

    def test_android_preflight_does_not_require_desktop_oauth(self):
        with tempfile.TemporaryDirectory() as tempdir:
            oauth = Path(tempdir) / "client_secret_desktop.json"
            firebase = Path(tempdir) / "google-services.json"
            firebase.write_text(
                '{"project_info":{"project_id":"official-project"},'
                '"client":[{"client_info":{"android_client_info":'
                '{"package_name":"com.frs.oficinadepesca"}},'
                '"api_key":[{"current_key":"official-api-key"}]}]}',
                encoding="utf-8",
            )

            problems = mestre_build._validar_credenciais_integracoes(
                str(oauth),
                str(firebase),
                target="android",
            )

        self.assertEqual(problems, [])

    def test_windows_cleanup_preserves_android_distribution(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            build_dir = root / "build"
            desktop_dist = root / "dist" / mestre_build.APP_NAME
            apk_dist = root / "dist" / "apk_celular"
            for directory in (build_dir, desktop_dist, apk_dist):
                directory.mkdir(parents=True)
                (directory / "keep-or-remove.txt").write_text("test", encoding="utf-8")

            old_repo_root, old_build_root = mestre_build.REPO_ROOT, mestre_build.BUILD_ROOT
            try:
                mestre_build.REPO_ROOT = tempdir
                mestre_build.BUILD_ROOT = tempdir
                mestre_build._limpeza_total_pre_build("windows")
            finally:
                mestre_build.REPO_ROOT, mestre_build.BUILD_ROOT = old_repo_root, old_build_root

            self.assertFalse(build_dir.exists())
            self.assertFalse(desktop_dist.exists())
            self.assertTrue((apk_dist / "keep-or-remove.txt").is_file())

    def test_windows_distribution_validation_does_not_require_apk(self):
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            installer = root / "installer.exe"
            bootstrapper = root / "updater.exe"
            portable = root / "portable.zip"
            for path in (installer, bootstrapper, portable):
                path.write_bytes(b"test")

            old_distribution_dir = mestre_build.DISTRIBUTION_DIR
            old_portable_name = mestre_build.PORTABLE_ZIP_NAME
            try:
                mestre_build.DISTRIBUTION_DIR = tempdir
                mestre_build.PORTABLE_ZIP_NAME = portable.name
                mestre_build._validar_pacote_distribuicao(
                    str(installer),
                    str(bootstrapper),
                    include_android=False,
                )
            finally:
                mestre_build.DISTRIBUTION_DIR = old_distribution_dir
                mestre_build.PORTABLE_ZIP_NAME = old_portable_name

    def test_windows_installer_build_disables_android_payload(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output_dir = Path(tempdir)
            old_output_dir = mestre_build.INSTALLER_OUTPUT_DIR
            try:
                mestre_build.INSTALLER_OUTPUT_DIR = tempdir

                def compile_installer(command, check):
                    self.assertTrue(check)
                    self.assertIn("/DIncludeAndroidApkEnabled=0", command)
                    (output_dir / "Setup_OficinaPesca_v1.0.66.exe").write_bytes(b"setup")

                with patch.object(mestre_build, "_localizar_iscc", return_value="ISCC.exe"), \
                    patch.object(mestre_build, "_nome_instalador_final", return_value="Setup_OficinaPesca_v1.0.66.exe"), \
                    patch.object(mestre_build.subprocess, "run", side_effect=compile_installer):
                    result = mestre_build._compilar_instalador_final("1.0.66", include_android=False)
                self.assertTrue(Path(result).is_file())
            finally:
                mestre_build.INSTALLER_OUTPUT_DIR = old_output_dir


if __name__ == "__main__":
    unittest.main()
