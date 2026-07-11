import json
import os
import unittest

import config
import mestre_build
import servidor


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
        self.assertEqual(data.get("versao"), "1.0.29")

    def test_apk_distribuido_tem_integridade_minima(self):
        caminho_apk = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dist", "apk_celular", "Oficina_Pesca_WebView_v1.0.29.apk"))
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


if __name__ == "__main__":
    unittest.main()
