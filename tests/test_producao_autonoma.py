import json
import os
import unittest
from unittest import mock

import config
import mestre_build
import servidor
from version_info import VERSION


class ProducaoAutonomaTests(unittest.TestCase):
    def test_status_acesso_centralizado_tem_campos_essenciais(self):
        status = config.obter_status_acesso_centralizado()
        for chave in ["ativa", "bloqueada", "mensagem", "tipo", "validade"]:
            self.assertIn(chave, status)

    def test_health_endpoint_helper_retorna_blocos_principais(self):
        health = servidor._coletar_saude_sistema()
        for chave in ["versao", "licenca", "firebase", "backup", "producao_autonoma"]:
            self.assertIn(chave, health)

    def test_manifesto_version_json_existe(self):
        caminho = os.path.join(os.path.dirname(__file__), "..", "version.json")
        caminho = os.path.abspath(caminho)
        self.assertTrue(os.path.exists(caminho))
        with open(caminho, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("versao"), VERSION)

    def test_apk_distribuido_tem_integridade_minima(self):
        caminho_apk = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "..",
                "dist",
                "apk_celular",
                f"Oficina_Pesca_WebView_v{VERSION}.apk",
            )
        )
        info = mestre_build._validar_apk_gerado(caminho_apk)
        self.assertTrue(info["size"] > 256 * 1024)
        self.assertEqual(len(info["sha256"]), 64)

    def test_webview_js_tem_modal_update_e_bloqueio_firebase(self):
        caminho_js = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static", "ofp_firebase_sync.js"))
        with open(caminho_js, "r", encoding="utf-8") as f:
            conteudo = f.read()
        self.assertIn("showUpdateModal", conteudo)
        self.assertIn("license_bloqueada", conteudo)
        self.assertIn("checkLicenseStatus", conteudo)

    def test_listener_firebase_realtime_inicia_com_mock(self):
        class _FakeStream:
            def close(self):
                return None

        class _FakeRef:
            def __init__(self):
                self.updated_payloads = []

            def update(self, payload):
                self.updated_payloads.append(payload)

            def listen(self, callback):
                return _FakeStream()

            def set(self, _payload):
                return None

            def delete(self):
                return None

        fake_ref = _FakeRef()

        fake_db = mock.Mock()
        fake_db.reference.return_value = fake_ref

        with mock.patch.object(config, "_inicializar_firebase_admin", return_value=(True, "ok")), \
            mock.patch.object(config, "_firebase_sync_channel", return_value="bridge/test_scope"), \
            mock.patch.object(config, "firebase_db", fake_db), \
            mock.patch.object(config, "publicar_heartbeat_firebase", return_value=(True, "ok")):
            config._FIREBASE_LISTENER_STARTED = False
            config._FIREBASE_LISTENER_THREAD = None
            ok, _msg = config.iniciar_listener_firebase_realtime()
            self.assertTrue(ok)
            self.assertTrue(config._FIREBASE_LISTENER_STARTED)
            self.assertIsNotNone(config._FIREBASE_LISTENER_THREAD)


if __name__ == "__main__":
    unittest.main()
