import unittest
from unittest.mock import patch

from core import licenca, sincronizacao


class TestCoreMenuServices(unittest.TestCase):
    def test_obter_info_licenca_visual_uses_status_acesso_centralizado(self):
        with patch("config.obter_status_acesso_centralizado", return_value={"licenca_ativa": True, "trial_ativo": False, "validade": "PERMANENTE"}), patch(
            "config.obter_tipo_licenca", return_value="PERMANENTE"
        ):
            texto, cor = licenca.obter_info_licenca_visual()

        self.assertEqual(texto, "Licença: Permanente")
        self.assertEqual(cor, "#2ecc71")

    def test_checar_status_firebase_false_when_no_config(self):
        with patch("config.obter_firebase_web_config", return_value={}), patch("requests.get", side_effect=Exception("fail")):
            self.assertFalse(sincronizacao.checar_status_firebase())


if __name__ == "__main__":
    unittest.main()
