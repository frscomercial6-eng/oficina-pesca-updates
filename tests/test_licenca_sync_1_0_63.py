# -*- coding: utf-8 -*-
"""Testes locais da Fase 1 (v1.0.63) — fluxo licença Desktop -> Supabase -> API.

- Usa SQLite TEMPORÁRIO (OFP_DB_PATH) — não toca no banco do projeto.
- Usa Supabase FALSO em memória — nenhuma chamada de rede/produção.
- Cobre: seleção da API (P1/P2/P3), publicação idempotente, orquestrador de
  sincronização, bloqueios do repoint e detecção de pendência.

Execução (a partir da raiz do projeto):
    .venv\\Scripts\\python.exe tests\\test_licenca_sync_1_0_63.py -v
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Banco SQLite isolado — DEVE ser definido ANTES de importar config.
_TMP_DIR = tempfile.mkdtemp(prefix="ofp_test_licenca_1_0_63_")
os.environ["OFP_DB_PATH"] = str(Path(_TMP_DIR) / "oficina_teste.db")

# Segredo de licenca explicito e isolado para os testes.
# Necessario porque o sistema (desde a Fase A1/v1.0.64) NAO aceita mais
# segredos default/placeholder; este valor nunca e usado em producao.
os.environ.setdefault(
    "OFP_LICENCA_SECRET",
    "ofp-teste-licenca-secret-1.0.63-nao-usar-em-producao",
)

import config  # noqa: E402

# O projeto contém artefatos compilados (config.cp311-win_amd64.pyd) que têm
# precedência sobre config.py no import padrão. Para garantir que os testes
# validem o CÓDIGO-FONTE alterado, registramos explicitamente o módulo .py
# como "config" no sys.modules, reexecutando o spec se necessário.
if not hasattr(config, "supabase_create_client"):
    import importlib.util as _ilu

    _spec = _ilu.spec_from_file_location("config", str(PROJECT_ROOT / "config.py"))
    config = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(config)
    sys.modules["config"] = config

EMAIL_A = "cliente.a@teste.com"
EMAIL_B = "cliente.b@teste.com"


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeQuery:
    def __init__(self, fake, table):
        self._fake = fake
        self._table = table
        self._filters = []
        self._order_col = None
        self._order_desc = False
        self._limit = None
        self._pending_insert = None
        self._pending_update = None

    def select(self, *_cols):
        return self

    def insert(self, row):
        self._pending_insert = dict(row)
        return self

    def update(self, values):
        self._pending_update = dict(values)
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def order(self, col, desc=False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit = n
        return self

    def execute(self):
        self._fake.executes += 1
        rows = [dict(r) for r in self._fake.store.setdefault(self._table, [])]

        if self._pending_insert is not None:
            if self._fake.falhar_insert:
                raise RuntimeError("supabase offline (simulação de teste)")
            novo = dict(self._pending_insert)
            self._fake.id_seq += 1
            novo["id"] = self._fake.id_seq
            self._fake.store[self._table].append(novo)
            return _FakeResult([novo])

        if self._pending_update is not None:
            afetadas = []
            for row in self._fake.store[self._table]:
                if all(row.get(c) == v for c, v in self._filters):
                    row.update(self._pending_update)
                    afetadas.append(dict(row))
            return _FakeResult(afetadas)

        for col, valor in self._filters:
            rows = [r for r in rows if r.get(col) == valor]
        if self._order_col:
            rows.sort(key=lambda r: (r.get(self._order_col) or 0), reverse=self._order_desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResult(rows)


class FakeSupabase:
    """Cliente Supabase falso com histórico em memória e contadores de uso."""

    def __init__(self):
        self.store = {}
        self.executes = 0
        self.id_seq = 0
        self.falhar_insert = False

    def table(self, name):
        return _FakeQuery(self, name)

    def linhas(self, table="licencas_geradas"):
        return list(self.store.get(table, []))


def _patch_supabase(fake):
    return [
        patch.object(config, "supabase_create_client", lambda url, key: fake),
        patch.object(config, "_obter_cfg_supabase", return_value=("https://fake.supabase.co", "fake-key")),
    ]


def _criar_stubs_api():
    fastapi = ModuleType("fastapi")

    class _StubFastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def _decor(self, *args, **kwargs):
            return lambda fn: fn

        get = post = put = delete = on_event = _decor

    fastapi.FastAPI = _StubFastAPI
    fastapi.Depends = lambda *a, **k: None

    class _StubHTTPException(Exception):
        def __init__(self, status_code=400, detail=""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    fastapi.HTTPException = _StubHTTPException
    fastapi.status = SimpleNamespace(HTTP_201_CREATED=201, HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403)
    sys.modules["fastapi"] = fastapi

    security = ModuleType("fastapi.security")

    class _StubHTTPBearer:
        def __init__(self, auto_error=True):
            pass

    security.HTTPBearer = _StubHTTPBearer
    security.HTTPAuthorizationCredentials = object
    sys.modules["fastapi.security"] = security

    jose = ModuleType("jose")

    class _StubJWTError(Exception):
        pass

    class _StubJWT:
        @staticmethod
        def encode(payload, key, algorithm="HS256"):
            return "stub-token"

        @staticmethod
        def decode(token, key, algorithms=None):
            return {}

    jose.JWTError = _StubJWTError
    jose.jwt = _StubJWT()
    sys.modules["jose"] = jose

    passlib_pkg = ModuleType("passlib")
    passlib_pkg.__path__ = []
    passlib_context = ModuleType("passlib.context")

    class _StubCryptContext:
        def __init__(self, schemes=None, deprecated="auto"):
            pass

        def hash(self, password):
            return "stub-hash"

        def verify(self, plain, hashed):
            return False

    passlib_context.CryptContext = _StubCryptContext
    passlib_exc = ModuleType("passlib.exc")

    class _StubUnknownHashError(Exception):
        pass

    passlib_exc.UnknownHashError = _StubUnknownHashError
    sys.modules["passlib"] = passlib_pkg
    sys.modules["passlib.context"] = passlib_context
    sys.modules["passlib.exc"] = passlib_exc

    pydantic = ModuleType("pydantic")

    class _StubBaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    pydantic.BaseModel = _StubBaseModel
    sys.modules["pydantic"] = pydantic

    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: False
    sys.modules["dotenv"] = dotenv


def _importar_api_main():
    try:
        import fastapi  # noqa: F401
        import jose  # noqa: F401
        import passlib.context  # noqa: F401
        import pydantic  # noqa: F401
        import dotenv  # noqa: F401
        deps_reais = True
    except Exception:
        _criar_stubs_api()
        deps_reais = False

    import api.main as api_main

    return api_main, deps_reais


class TestApiSelecaoLicenca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api, cls.deps_reais = _importar_api_main()

    def setUp(self):
        self.fake = FakeSupabase()
        patcher = patch.object(self.api, "get_supabase_client_cached", lambda: self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    @staticmethod
    def _row(idx, validade, tipo="MENSAL", plano="MENSAL", cliente="CLI",
             data_geracao="2026-01-01T00:00:00", email=EMAIL_A):
        return {
            "id": idx,
            "email": email,
            "data_expiracao": validade,
            "cliente": cliente,
            "tipo": tipo,
            "plano": plano,
            "data_geracao": data_geracao,
        }

    def _hoje_mais(self, dias):
        return (date.today() + timedelta(days=dias)).isoformat()

    def _hoje_menos(self, dias):
        return (date.today() - timedelta(days=dias)).isoformat()

    def _consultar(self, email=EMAIL_A):
        return self.api._status_licenca_por_email(email)

    def test_permanente_vence_expirada_recente(self):
        self.fake.store["licencas_geradas"] = [
            self._row(11, self._hoje_menos(5), "MENSAL", "MENSAL"),
            self._row(10, "PERMANENTE", "PERMANENTE", "PERMANENTE"),
        ]
        resp = self._consultar()
        self.assertTrue(resp["ok"])
        self.assertTrue(resp["ativa"])
        self.assertEqual(resp["validade"], "PERMANENTE")

    def test_anual_valida_com_mensal_expirada_recente(self):
        self.fake.store["licencas_geradas"] = [
            self._row(11, self._hoje_menos(3), "MENSAL", "MENSAL"),
            self._row(10, self._hoje_mais(200), "ANUAL", "ANUAL"),
        ]
        resp = self._consultar()
        self.assertTrue(resp["ativa"])
        self.assertEqual(resp["validade"], self._hoje_mais(200))
        self.assertEqual(resp["tipo"], "ANUAL")

    def test_todas_expiradas(self):
        self.fake.store["licencas_geradas"] = [
            self._row(11, self._hoje_menos(2), "MENSAL", "MENSAL"),
            self._row(10, self._hoje_menos(60), "ANUAL", "ANUAL"),
        ]
        resp = self._consultar()
        self.assertFalse(resp["ativa"])
        self.assertIn("expirada", resp["mensagem"].lower())

    def test_duas_validas_escolhe_maior_data_expiracao(self):
        self.fake.store["licencas_geradas"] = [
            self._row(11, self._hoje_mais(30), "MENSAL", "MENSAL"),
            self._row(10, self._hoje_mais(200), "ANUAL", "ANUAL"),
        ]
        resp = self._consultar()
        self.assertTrue(resp["ativa"])
        self.assertEqual(resp["validade"], self._hoje_mais(200))

    def test_tipos_comerciais_validos(self):
        casos = [("MENSAL", 30), ("TRIMESTRAL", 90), ("SEMESTRAL", 180), ("ANUAL", 365)]
        for tipo, dias in casos:
            with self.subTest(tipo=tipo):
                self.fake.store["licencas_geradas"] = [
                    self._row(1, self._hoje_mais(dias), tipo, tipo)
                ]
                resp = self._consultar()
                self.assertTrue(resp["ativa"], msg=f"{tipo} deveria estar ativa")
                self.assertEqual(resp["tipo"], tipo)

    def test_mensal_expirada(self):
        self.fake.store["licencas_geradas"] = [self._row(1, self._hoje_menos(1))]
        resp = self._consultar()
        self.assertFalse(resp["ativa"])

    def test_email_inexistente(self):
        resp = self._consultar("ninguem@teste.com")
        self.assertTrue(resp["ok"])
        self.assertFalse(resp["ativa"])
        self.assertEqual(resp["mensagem"], "Nenhuma licenca encontrada para este e-mail.")

    def test_email_invalido(self):
        resp = self.api._status_licenca_por_email("sem-arroba")
        self.assertFalse(resp["ok"])
        self.assertFalse(resp["ativa"])
        self.assertEqual(resp["mensagem"], "E-mail invalido.")

    def test_defesa_trial(self):
        self.fake.store["licencas_geradas"] = [self._row(1, self._hoje_mais(30), "TRIAL", "TRIAL")]
        resp = self._consultar()
        self.assertFalse(resp["ativa"])

    def test_data_invalida_nao_e_valida(self):
        self.fake.store["licencas_geradas"] = [self._row(1, "data-lixo")]
        resp = self._consultar()
        self.assertFalse(resp["ativa"])
        self.assertIn("data-lixo", resp["mensagem"])

    def test_falha_de_consulta(self):
        def _quebra():
            raise RuntimeError("conexao falhou (teste)")

        with patch.object(self.api, "get_supabase_client_cached", _quebra):
            resp = self._consultar()
        self.assertFalse(resp["ok"])
        self.assertFalse(resp["ativa"])
        self.assertIn("Falha ao consultar", resp["mensagem"])


class TestDesktopSyncLicenca(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            config.inicializar_banco()
        except Exception:
            pass
        # Garante a tabela de configurações mesmo se inicializar_banco mudar.
        with config.get_db_connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS configuracoes (chave TEXT PRIMARY KEY, valor TEXT)"
            )
            conn.commit()

    def setUp(self):
        self.fake = FakeSupabase()
        self.patches = _patch_supabase(self.fake)
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        # Limpa estado de licença/sincronização entre testes.
        for chave_cfg in (
            "licenca_chave", "licenca_cliente", "licenca_validade", "licenca_tipo",
            "licenca_ja_ativada", "licenca_supabase_sync", "licenca_supabase_sync_msg",
            "licenca_sync_ultima_chave", "licenca_sync_ultimo_email",
        ):
            with config.get_db_connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM configuracoes WHERE chave = ?", (chave_cfg,))
                conn.commit()

    def _set_config(self, chave_cfg, valor):
        with config.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO configuracoes (chave, valor) VALUES (?, ?)",
                (chave_cfg, valor),
            )
            conn.commit()

    def _get_config(self, chave_cfg):
        with config.get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT valor FROM configuracoes WHERE chave = ?", (chave_cfg,))
            row = cur.fetchone()
        return str(row[0]) if row and row[0] is not None else ""

    def _gerar_chave(self, dias):
        return config.gerar_chave_licenca(
            cliente="",
            dias_validade=dias,
            chave_instalacao=config.obter_chave_instalacao(),
        )

    def _escrever_licenca_key(self, chave):
        """Simula ativação real: escreve licenca.key na raiz da instalação.

        obter_chave_licenca_ativa() lê o arquivo licenca.key (via
        _extrair_licenca_de_arquivo), não a tabela configuracoes.
        """
        tmp_dir = tempfile.mkdtemp(prefix="ofp_test_key_")
        with open(os.path.join(tmp_dir, "licenca.key"), "w", encoding="utf-8") as f:
            f.write(str(chave or "").strip())
        return tmp_dir

    # -- Fase 3: identidade estrita -------------------------------------------
    def test_email_estrito_valido(self):
        with patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            self.assertEqual(config.obter_email_licenca_para_sync(), EMAIL_A)

    def test_email_estrito_ausente_retorna_vazio_nunca_ofp_user(self):
        with patch.object(config, "obter_email_backup_nuvem", return_value=""):
            self.assertEqual(config.obter_email_licenca_para_sync(), "")
            self.assertNotEqual(config.obter_email_licenca_para_sync(), "ofp-user")

    def test_email_estrito_invalido_retorna_vazio(self):
        with patch.object(config, "obter_email_backup_nuvem", return_value="sem-arroba"):
            self.assertEqual(config.obter_email_licenca_para_sync(), "")


# -- Fase 4: publicação idempotente ---------------------------------------
    def test_publicar_sem_email_nao_insere_e_registra_pendencia(self):
        chave = self._gerar_chave(30)
        with patch.object(config, "obter_email_backup_nuvem", return_value=""):
            ok, msg = config.publicar_licenca_supabase(chave)
        self.assertFalse(ok)
        self.assertIn("Sincronização pendente", msg)
        self.assertEqual(self.fake.linhas(), [])

    def test_publicar_nunca_usa_ofp_user(self):
        chave = self._gerar_chave(30)
        with patch.object(config, "obter_email_backup_nuvem", return_value=""), \
                patch.object(config, "obter_user_id_token_padrao", return_value="ofp-user"):
            ok, msg = config.publicar_licenca_supabase(chave)
        self.assertFalse(ok)
        self.assertNotIn("ofp-user", msg)
        self.assertEqual(self.fake.linhas(), [])

    def test_publicar_com_email_insere_e_grava_estado(self):
        chave = self._gerar_chave(30)
        with patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok, msg = config.publicar_licenca_supabase(chave)
        self.assertTrue(ok)
        self.assertIn(EMAIL_A, msg)
        linhas = self.fake.linhas()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["email"], EMAIL_A)
        self.assertEqual(linhas[0]["chave"], chave)
        self.assertEqual(linhas[0]["tipo"], "MENSAL")
        self.assertEqual(self._get_config("licenca_sync_ultima_chave"), chave)
        self.assertEqual(self._get_config("licenca_sync_ultimo_email"), EMAIL_A)

    def test_publicar_idempotente_nao_duplica(self):
        chave = self._gerar_chave(30)
        with patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok1, _ = config.publicar_licenca_supabase(chave)
            ok2, msg2 = config.publicar_licenca_supabase(chave)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertIn("já sincronizada", msg2.lower())
        self.assertEqual(len(self.fake.linhas()), 1)

    def test_publicar_falha_supabase_nao_insere(self):
        chave = self._gerar_chave(30)
        self.fake.falhar_insert = True
        with patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok, msg = config.publicar_licenca_supabase(chave)
        self.assertFalse(ok)
        self.assertIn("Falha ao sincronizar", msg)
        self.assertEqual(self.fake.linhas(), [])
        self.assertEqual(self._get_config("licenca_sync_ultima_chave"), "")


# -- Fase 6: orquestrador -------------------------------------------------
    def test_orquestrador_trial_sem_chave_nao_chama_rede(self):
        executes_antes = self.fake.executes
        with patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok, msg = config.sincronizar_licenca_supabase_pendente()
        self.assertFalse(ok)
        self.assertIn("Nenhuma chave de licença ativa", msg)
        self.assertEqual(self.fake.executes, executes_antes)

    def test_orquestrador_chave_token_nada_a_sincronizar(self):
        tmp = self._escrever_licenca_key("TOKEN::arquivo")
        with patch.object(config, "DIRETORIO_ATUAL", tmp), \
                patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok, msg = config.sincronizar_licenca_supabase_pendente()
        self.assertFalse(ok)
        self.assertIn("Nada a sincronizar", msg)
        self.assertEqual(self.fake.linhas(), [])

    def test_orquestrador_sem_pendencia_nao_chama_rede(self):
        chave = self._gerar_chave(30)
        tmp = self._escrever_licenca_key(chave)
        with patch.object(config, "DIRETORIO_ATUAL", tmp), \
                patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok_pub, _ = config.publicar_licenca_supabase(chave)
            self.assertTrue(ok_pub)
            # Marca como sincronizado (o orquestrador exige licenca_supabase_sync=1).
            self._set_config("licenca_supabase_sync", "1")
            executes_antes = self.fake.executes
            ok, msg = config.sincronizar_licenca_supabase_pendente()
        self.assertTrue(ok)
        self.assertIn("Nenhuma pendência", msg)
        self.assertEqual(self.fake.executes, executes_antes)
        self.assertEqual(len(self.fake.linhas()), 1)

    def test_orquestrador_restauracao_detecta_pendencia(self):
        chave30 = self._gerar_chave(30)
        chave365 = self._gerar_chave(365)
        tmp = self._escrever_licenca_key(chave30)
        with patch.object(config, "DIRETORIO_ATUAL", tmp), \
                patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok1, _ = config.publicar_licenca_supabase(chave30)
            self.assertTrue(ok1)
            # Simula restauração: licenca.key agora contém outra chave.
            with open(os.path.join(tmp, "licenca.key"), "w", encoding="utf-8") as f:
                f.write(chave365)
            ok2, _ = config.sincronizar_licenca_supabase_pendente()
        self.assertTrue(ok2)
        linhas = self.fake.linhas()
        self.assertEqual(len(linhas), 2)
        self.assertEqual({l["chave"] for l in linhas}, {chave30, chave365})
        self.assertEqual(self._get_config("licenca_sync_ultima_chave"), chave365)


    def test_orquestrador_troca_de_email_publica_novo_sem_repoint_automatico(self):
        chave = self._gerar_chave(30)
        tmp = self._escrever_licenca_key(chave)
        with patch.object(config, "DIRETORIO_ATUAL", tmp), \
                patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok1, _ = config.publicar_licenca_supabase(chave)
            self.assertTrue(ok1)
            with patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_B):
                ok2, _ = config.sincronizar_licenca_supabase_pendente()
        self.assertTrue(ok2)
        linhas = self.fake.linhas()
        emails = sorted(l["email"] for l in linhas)
        # Histórico preservado: linha antiga (A) continua; nova linha para B.
        self.assertEqual(emails, [EMAIL_A, EMAIL_B])
        self.assertEqual(self._get_config("licenca_sync_ultimo_email"), EMAIL_B)

    # -- Fase 6: repoint PREPARADO porém BLOQUEADO -----------------------------
    def test_repoint_bloqueado_sem_confirmar(self):
        chave = self._gerar_chave(30)
        ok, msg = config.reapontar_historico_licenca_supabase(EMAIL_A, EMAIL_B, chave)
        self.assertFalse(ok)
        self.assertIn("bloqueado", msg.lower())
        self.assertEqual(self.fake.linhas(), [])

    def test_repoint_bloqueado_sem_variavel_de_ambiente(self):
        chave = self._gerar_chave(30)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OFP_PERMITIR_REPOINT_LICENCA", None)
            ok, msg = config.reapontar_historico_licenca_supabase(
                EMAIL_A, EMAIL_B, chave, confirmar=True
            )
        self.assertFalse(ok)
        self.assertIn("OFP_PERMITIR_REPOINT_LICENCA", msg)
        self.assertEqual(self.fake.linhas(), [])


    def test_repoint_executa_apenas_com_gate_completo(self):
        chave = self._gerar_chave(30)
        self.fake.store["licencas_geradas"] = [
            {"id": 1, "email": EMAIL_A, "chave": chave, "data_expiracao": "PERMANENTE",
             "cliente": EMAIL_A, "tipo": "MENSAL", "plano": "MENSAL", "data_geracao": "x"}
        ]
        env = {"OFP_PERMITIR_REPOINT_LICENCA": "1"}
        with patch.dict(os.environ, env, clear=False):
            ok, msg = config.reapontar_historico_licenca_supabase(
                EMAIL_A, EMAIL_B, chave, confirmar=True
            )
        self.assertTrue(ok)
        self.assertIn("1 registro", msg)
        linhas = self.fake.linhas()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["email"], EMAIL_B)

    # -- Fase 5: ativação (falha de Supabase NÃO invalida ativação local) ------
    def test_ativacao_publica_com_email_do_backup(self):
        chave = self._gerar_chave(30)
        tmp_dir = tempfile.mkdtemp(prefix="ofp_test_licenca_key_")
        with patch.object(config, "DIRETORIO_ATUAL", tmp_dir), \
                patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok, msg = config.ativar_licenca(chave)
        self.assertTrue(ok, msg)
        self.assertEqual(msg, "Licenca ativada com sucesso.")
        self.assertEqual(self._get_config("licenca_chave"), chave)
        self.assertEqual(self._get_config("licenca_supabase_sync"), "1")
        linhas = self.fake.linhas()
        self.assertEqual(len(linhas), 1)
        self.assertEqual(linhas[0]["email"], EMAIL_A)

    def test_ativacao_falha_supabase_mantem_licenca_local(self):
        chave = self._gerar_chave(30)
        tmp_dir = tempfile.mkdtemp(prefix="ofp_test_licenca_key_")
        self.fake.falhar_insert = True
        with patch.object(config, "DIRETORIO_ATUAL", tmp_dir), \
                patch.object(config, "obter_email_backup_nuvem", return_value=EMAIL_A):
            ok, msg = config.ativar_licenca(chave)
        self.assertTrue(ok)
        self.assertEqual(msg, "Licenca ativada com sucesso.")
        self.assertEqual(self._get_config("licenca_chave"), chave)
        self.assertEqual(self._get_config("licenca_supabase_sync"), "0")
        self.assertEqual(self.fake.linhas(), [])
        self.assertTrue(os.path.exists(os.path.join(tmp_dir, "licenca.key")))


if __name__ == "__main__":
    unittest.main(verbosity=2)


