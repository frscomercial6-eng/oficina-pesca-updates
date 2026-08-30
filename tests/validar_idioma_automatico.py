# -*- coding: utf-8 -*-
"""Valida a seleção de idioma 100% automática e o EULA por idioma.

Uso: python tests/validar_idioma_automatico.py
"""
import io
import json
import os
import py_compile
import sys
import unittest
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

from core.eula import (  # noqa: E402
    caminho_eula,
    carregar_texto_eula,
    detectar_idioma_sistema,
    normalizar_locale,
    rtf_para_texto,
)
from core import i18n  # noqa: E402


class TestNormalizacao(unittest.TestCase):
    def test_variants_mapeiam_para_locales_suportados(self):
        casos = {
            "pt_BR": "pt_BR",
            "pt-br": "pt_BR",
            "Portuguese_Brazil.1252": "pt_BR",
            "en_US": "en_US",
            "en-US.utf8": "en_US",
            "English_United States.1252": "en_US",
            "es_UY": "es_UY",
            "es-419": "es_UY",
            "fr_FR": "",
            "": "",
            None: "",
        }
        for entrada, esperado in casos.items():
            self.assertEqual(normalizar_locale(entrada), esperado, f"entrada={entrada!r}")

    def test_deteccao_no_windows(self):
        idioma = detectar_idioma_sistema()
        self.assertIn(idioma, ("pt_BR", "en_US", "es_UY", ""))


class TestSetDefaultLocaleAutomatico(unittest.TestCase):
    def test_sem_argumento_usa_sistema_operacional(self):
        ambiente = {"OFICINA_LOCALE": ""}
        with mock.patch.dict(os.environ, ambiente, clear=False):
            with mock.patch.object(i18n, "detectar_idioma_sistema", return_value="en_US"):
                resultado = i18n.set_default_locale()
            self.assertEqual(resultado, "en_US")
            self.assertEqual(i18n.get_current_locale(), "en_US")
        i18n.set_default_locale()  # restaura pelo SO real

    def test_env_tem_prioridade_sobre_sistema(self):
        with mock.patch.dict(os.environ, {"OFICINA_LOCALE": "es_UY"}, clear=False):
            with mock.patch.object(i18n, "detectar_idioma_sistema", return_value="en_US"):
                resultado = i18n.set_default_locale()
            self.assertEqual(resultado, "es_UY")
        i18n.set_default_locale()

    def test_fallback_pt_br_quando_sistema_desconhecido(self):
        with mock.patch.dict(os.environ, {"OFICINA_LOCALE": ""}, clear=False):
            with mock.patch.object(i18n, "detectar_idioma_sistema", return_value=""):
                with mock.patch.object(i18n, "_ler_idioma_config_cfg", return_value=None):
                    resultado = i18n.set_default_locale()
            self.assertEqual(resultado, "pt_BR")
        i18n.set_default_locale()


class TestEulaPorIdioma(unittest.TestCase):
    def test_caminho_por_idioma(self):
        self.assertTrue(caminho_eula("pt_BR").lower().endswith("contrato_oficina_de_pesca_v3_maio_2026.rtf"))
        self.assertTrue(caminho_eula("en_US").lower().endswith("_en_us.rtf"))
        self.assertTrue(caminho_eula("es_UY").lower().endswith("_es_uy.rtf"))
        # Idioma sem contrato específico cai para o padrão pt_BR.
        self.assertTrue(caminho_eula("fr_FR").lower().endswith("contrato_oficina_de_pesca_v3_maio_2026.rtf"))

    def test_textos_em_cada_idioma(self):
        marcadores = {
            "pt_BR": "LICENCA",  # documento original escrito sem acentos
            "en_US": "LICENSE GRANT",
            "es_UY": "LICENCIA",
        }
        for idioma, marcador in marcadores.items():
            texto = carregar_texto_eula(idioma)
            self.assertTrue(texto, f"sem texto para {idioma}")
            self.assertIn(marcador, texto.upper(), f"marcador ausente no {idioma}")

    def test_rtf_convertido_para_texto_limpo(self):
        texto = carregar_texto_eula("en_US")
        self.assertNotIn("\\par", texto)
        self.assertNotIn("{\\rtf1", texto)
        self.assertNotIn("\\fs24", texto)
        self.assertIn("ACBr", texto)  # cláusula de software de terceiros presente


class TestArquivosECodigo(unittest.TestCase):
    def test_chaves_eula_nos_tres_idiomas(self):
        pastas = [
            os.path.join(RAIZ, "locales"),
            os.path.abspath(os.path.join(RAIZ, os.pardir, "build_protegido", "locales")),
        ]
        for pasta in pastas:
            for idioma in ("pt_BR", "en_US", "es_UY"):
                caminho = os.path.join(pasta, f"{idioma}.json")
                with open(caminho, "r", encoding="utf-8") as arquivo:
                    dados = json.load(arquivo)
                for chave in ("eula_titulo", "eula_aceitar", "eula_recusar", "eula_aviso"):
                    self.assertIn(chave, dados, f"{chave} ausente em {idioma}.json ({pasta})")

    def test_menu_fonte_sem_selecao_manual_de_idioma(self):
        with open(os.path.join(RAIZ, "menu.py"), "r", encoding="utf-8") as arquivo:
            codigo = arquivo.read()
        for proibido in ("_trocar_idioma", "_option_idioma", "label_idioma", "_locale_var", "_salvar_idioma_cfg"):
            self.assertNotIn(proibido, codigo, f"referência remanescente: {proibido}")
        self.assertIn("set_default_locale()", codigo)

    def test_login_fonte_com_fluxo_eula(self):
        with open(os.path.join(RAIZ, "login.py"), "r", encoding="utf-8") as arquivo:
            codigo = arquivo.read()
        self.assertIn("def _exibir_janela_eula", codigo)
        self.assertIn("_inicializar_fluxo_com_eula", codigo)
        self.assertIn("carregar_texto_eula", codigo)

    def test_installers_com_tres_idiomas(self):
        pastas = [
            RAIZ,
            os.path.abspath(os.path.join(RAIZ, os.pardir, "build_protegido")),
        ]
        for pasta in pastas:
            for nome in ("instalar.iss", "instalar_oficial_completo.iss"):
                caminho = os.path.join(pasta, nome)
                with open(caminho, "r", encoding="utf-8", errors="ignore") as arquivo:
                    conteudo = arquivo.read()
                self.assertIn('Name: "english"', conteudo, f"{nome} sem idioma inglês ({pasta})")
                self.assertIn('Name: "spanish"', conteudo, f"{nome} sem idioma espanhol ({pasta})")
                self.assertIn("_en_US.rtf", conteudo)
                self.assertIn("_es_UY.rtf", conteudo)
                self.assertIn("ShowLanguageDialog=no", conteudo)

    def test_spec_embute_contratos(self):
        for spec in (
            os.path.join(RAIZ, "Oficina_Pesca.spec"),
            os.path.join(RAIZ, os.pardir, "build_protegido", "Oficina_Pesca.spec"),
        ):
            with open(os.path.abspath(spec), "r", encoding="utf-8") as arquivo:
                conteudo = arquivo.read()
            self.assertIn("_en_US.rtf", conteudo, f"{spec} sem contrato em inglês")
            self.assertIn("_es_UY.rtf", conteudo, f"{spec} sem contrato em espanhol")

    def test_compilacao_dos_arquivos_alterados(self):
        alvos = [
            os.path.join(RAIZ, "menu.py"),
            os.path.join(RAIZ, "login.py"),
            os.path.join(RAIZ, "core", "i18n.py"),
            os.path.join(RAIZ, "core", "eula.py"),
            os.path.join(RAIZ, "mestre_build.py"),
            os.path.join(RAIZ, os.pardir, "build_protegido", "menu.py"),
            os.path.join(RAIZ, os.pardir, "build_protegido", "login.py"),
            os.path.join(RAIZ, os.pardir, "build_protegido", "core", "eula.py"),
            os.path.join(RAIZ, os.pardir, "build_protegido", "mestre_build.py"),
        ]
        for caminho in alvos:
            py_compile.compile(os.path.abspath(caminho), doraise=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    stream = io.StringIO()
    resultado = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    )
    print(stream.getvalue())
    sys.exit(0 if resultado.wasSuccessful() else 1)
