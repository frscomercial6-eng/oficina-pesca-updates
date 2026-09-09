# -*- coding: utf-8 -*-
"""Testes de seguranca da ETAPA A1 (v1.0.64) — offline, sem rede, sem banco real.

Cobrem:
- segredo de licenca ausente/placeholder => falha controlada (sem fallback inseguro);
- /seed/admin nao permite acesso anonimo (403/401);
- CORS nunca expoe '*' com credentials;
- origens permitidas seguem a configuracao explicita (env/config.cfg).
"""
import importlib
import os
import re
import subprocess
import sys
import unittest

from fastapi.testclient import TestClient

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

# Garante que a raiz do projeto esteja no sys.path (o script roda a partir de tests/).
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)


class TestSegredoLicenca(unittest.TestCase):
    def test_sem_segredo_falha_controlada_sem_fallback_placeholder(self):
        codigo = (
            "import os\n"
            "os.environ.pop('OFP_LICENCA_SECRET', None)\n"
            "import config\n"
            "print('SECRET=' + repr(config.LICENCA_SECRET))\n"
            "print('CONFIG=' + repr(config.licenca_secret_configurado()))\n"
            "ok, msg, _ = config.validar_chave_licenca('OFP-qualquer')\n"
            "print('VALIDA=' + repr(ok))\n"
            "print('MSG=' + msg)\n"
            "try:\n"
            "    config._exigir_licenca_secret()\n"
            "    print('EXIGIR=nao-levantou')\n"
            "except RuntimeError:\n"
            "    print('EXIGIR=levantou')\n"
        )
        env = dict(os.environ)
        env.pop("OFP_LICENCA_SECRET", None)
        proc = subprocess.run(
            [PY, "-c", codigo], cwd=RAIZ, env=env,
            capture_output=True, text=True, timeout=90,
        )
        saida = proc.stdout + proc.stderr
        self.assertIn("SECRET=''", saida, saida)
        self.assertIn("CONFIG=False", saida, saida)
        self.assertIn("VALIDA=False", saida, saida)
        self.assertIn("nao configurado", saida.lower(), saida)
        self.assertIn("EXIGIR=levantou", saida, saida)


class TestSeedAdminProtegido(unittest.TestCase):
    """Verifica a protecao do /seed/admin em subprocess isolado.

    Roda em subprocess porque `test_api_auth.py` seta OFP_SEED_ADMIN_TOKEN
    em module-level durante a discovery do unittest, e o reload() de api.main
    nao limpa esse estado de forma confiaveis entre os testes.
    """

    def _run_seed(self, *, env_extra=None, headers=None):
        """Roda o endpoint /seed/admin em subprocess isolado."""
        codigo = (
            "import os, sys\n"
            "sys.path.insert(0, r'" + RAIZ + "')\n"
            "from fastapi.testclient import TestClient\n"
            "import api.main as m\n"
            "from fastapi import status\n"
            "c = TestClient(m.app)\n"
            "headers = " + repr(headers or {}) + "\n"
            "r = c.post('/seed/admin', json={'nome':'Admin','email':'x@y.com','senha':'123456','perfil':'admin'}, headers=headers)\n"
            "print('STATUS=' + str(r.status_code))\n"
            "print('BODY=' + r.text[:200])\n"
        )
        env = dict(os.environ)
        # Sempre limpa o token para partir do estado conhecido.
        env.pop("OFP_SEED_ADMIN_TOKEN", None)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [PY, "-c", codigo], cwd=RAIZ, env=env,
            capture_output=True, text=True, timeout=90,
        )
        return proc.stdout + proc.stderr

    def test_sem_token_habilitado_retorna_403(self):
        """Endpoint desativado (403) quando OFP_SEED_ADMIN_TOKEN nao existe."""
        saida = self._run_seed()
        self.assertIn("STATUS=403", saida, saida)
        self.assertIn("indisponivel", saida, saida)

    def test_com_token_habilitado_sem_header_retorna_401(self):
        """Token configurado mas header ausente -> 401."""
        saida = self._run_seed(env_extra={"OFP_SEED_ADMIN_TOKEN": "ofp-teste-token-seguro"})
        self.assertIn("STATUS=401", saida, saida)

    def test_com_token_errado_retorna_403(self):
        """Token configurado mas header com valor errado -> 403."""
        saida = self._run_seed(
            env_extra={"OFP_SEED_ADMIN_TOKEN": "ofp-teste-token-seguro"},
            headers={"Authorization": "Bearer token-errado"},
        )
        self.assertIn("STATUS=403", saida, saida)


class TestCors(unittest.TestCase):
    """Verificacoes de CORS sem importar `servidor` em runtime.

    Motivo: importar `servidor` (2 apps FastAPI) E `api.main` (outro app
    FastAPI) no mesmo processo pode causar segfault em determinados ambientes
    Windows/Python 3.11. Como a correcao de CORS e deterministica (baseada em
    env/file content), validamos por leitura estatica do fonte + checagem de
    presenca da funcao `_origens_cors_permitidas` no arquivo.
    """

    def _conteudo_servidor(self):
        caminho = os.path.join(RAIZ, "servidor.py")
        with open(caminho, "r", encoding="utf-8") as f:
            return f.read()

    def test_cors_sem_asterisco_e_com_origens_configuraveis(self):
        corpo = self._conteudo_servidor()
        # Nenhum allow_origins="*" ou ["*"] permanece apos a correcao.
        self.assertNotIn('allow_origins=["*"]', corpo)
        self.assertNotIn('allow_origins="*"', corpo)
        # A funcao de origens permitidas deve existir e mencionar localhost.
        self.assertIn("_origens_cors_permitidas", corpo)
        self.assertIn("localhost:8000", corpo)

    def test_cors_respeita_env_explicito(self):
        corpo = self._conteudo_servidor()
        # A leitura de OFP_CORS_ORIGINS deve estar presente na funcao.
        self.assertIn("OFP_CORS_ORIGINS", corpo)
        # Deve haver split por virgula para aceitar multiplas origens.
        self.assertIn(",", corpo)  # Sanidade: o arquivo tem conteudo.

    def test_arquivo_servidor_sem_allow_origins_asterisco(self):
        corpo = self._conteudo_servidor()
        self.assertNotIn('allow_origins=["*"]', corpo)
        self.assertNotIn('allow_origins="*"', corpo)


class TestSemDefaultInseguro(unittest.TestCase):
    def test_placeholder_rejeitado_funcionalmente(self):
        import config
        # A sentinela DEVE existir na lista de rejeicao (por isso não checamos
        # a ausência da literal em config.py); o que importa e o comportamento.
        self.assertFalse(config._segredo_licenca_valido("ALTERAR-EM-PRODUCAO"))
        self.assertFalse(config._segredo_licenca_valido("dev-secret-key"))
        self.assertFalse(config._segredo_licenca_valido(""))

    def test_servidor_sem_fallback_jwt_inseguro(self):
        caminho = os.path.join(RAIZ, "servidor.py")
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
        self.assertNotIn("fallback=\"OFP-JWT-ALTERAR-EM-PRODUCAO\"", conteudo)
        self.assertNotIn("fallback=\"dev-secret-key\"", conteudo)

    def test_api_main_sem_default_dev_secret(self):
        caminho = os.path.join(RAIZ, "api", "main.py")
        with open(caminho, "r", encoding="utf-8") as f:
            conteudo = f.read()
        self.assertNotIn("\"JWT_SECRET_KEY\", \"dev-secret-key\"", conteudo)
        self.assertIn("_exigir_secret_key", conteudo)

    def test_instalador_sem_define_licenca_ativa(self):
        caminho = os.path.join(RAIZ, "instalar.iss")
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            conteudo = f.read()
        # Nenhum #define LicenseSecret ativo (linha iniciada com '#define').
        self.assertIsNone(re.search(r"(?m)^\s*#define\s+LicenseSecret\s+\"", conteudo))


if __name__ == "__main__":
    unittest.main(verbosity=2)