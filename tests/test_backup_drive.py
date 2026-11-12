import json
import sqlite3
import threading
import time
from types import SimpleNamespace

import customtkinter as ctk
import pytest

import config
import menu


class ErroGoogle(Exception):
    def __init__(self, status, reason, mensagem):
        super().__init__(mensagem)
        self.resp = SimpleNamespace(status=status)
        self.content = json.dumps({
            "error": {"message": mensagem, "errors": [{"reason": reason}]}
        }).encode()


@pytest.mark.parametrize(
    ("erro", "trechos"),
    [
        (ErroGoogle(403, "accessNotConfigured", "Drive API disabled"), ("403", "accessNotConfigured", "API")),
        (ErroGoogle(403, "insufficientFilePermissions", "Cannot write folder"), ("403", "insufficientFilePermissions", "pasta")),
        (ErroGoogle(401, "authError", "Invalid credentials"), ("401", "autoriza")),
        (TimeoutError("timed out"), ("Tempo", "internet")),
        (ConnectionError("offline"), ("conectar", "internet")),
    ],
)
def test_erro_drive_informa_causa_sem_presumir_token_expirado(erro, trechos):
    mensagem = config._mensagem_erro_backup_drive(erro)
    assert all(trecho.lower() in mensagem.lower() for trecho in trechos)
    if getattr(getattr(erro, "resp", None), "status", None) == 403:
        assert "token expirado" not in mensagem.lower()


def test_backup_inclui_wal_e_nao_atualiza_arquivos_existentes(tmp_path, monkeypatch):
    banco = tmp_path / "fonte.db"
    origem = sqlite3.connect(banco)
    origem.execute("PRAGMA journal_mode=WAL")
    origem.execute("CREATE TABLE teste (valor TEXT)")
    origem.execute("INSERT INTO teste VALUES ('somente dado sintetico')")
    origem.commit()
    enviados = []

    class Resultado:
        def __init__(self, resposta):
            self.resposta = resposta

        def execute(self):
            return self.resposta

        def next_chunk(self, **kwargs):
            return None, self.resposta

    class Arquivos:
        def list(self, **kwargs):
            return Resultado({"files": [{"id": "pasta-teste"}]})

        def create(self, body, media_body, **kwargs):
            con = sqlite3.connect(f"file:{media_body._filename}?mode=ro", uri=True)
            try:
                enviados.extend(con.execute("SELECT valor FROM teste").fetchall())
            finally:
                con.close()
            assert body["parents"] == ["pasta-teste"]
            return Resultado({"id": "arquivo-novo"})

        def update(self, **kwargs):
            raise AssertionError("Backup não pode sobrescrever arquivos existentes")

    service = SimpleNamespace(files=lambda: Arquivos())
    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_servico_drive_com_timeout", lambda creds, timeout: service)
    try:
        ok, mensagem = config.enviar_backup_banco_para_drive_usuario(timeout=5, credenciais=object())
    finally:
        origem.close()
    assert ok, mensagem
    assert enviados == [("somente dado sintetico",)]
    assert not list(tmp_path.glob("oficina_backup_temporario_*.db"))


def test_cancelar_antes_do_upload_nao_cria_arquivo(tmp_path, monkeypatch):
    banco = tmp_path / "fonte.db"
    sqlite3.connect(banco).close()
    cancelamento = threading.Event()

    class Arquivos:
        def list(self, **kwargs):
            cancelamento.set()
            return SimpleNamespace(execute=lambda: {"files": [{"id": "pasta-teste"}]})

        def create(self, **kwargs):
            raise AssertionError("Não deve criar arquivo após cancelar")

    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_servico_drive_com_timeout", lambda creds, timeout: SimpleNamespace(files=lambda: Arquivos()))
    ok, mensagem = config.enviar_backup_banco_para_drive_usuario(timeout=5, cancelar=cancelamento, credenciais=object())
    assert not ok and "cancelada" in mensagem


def test_falha_403_simulada_do_servico_preserva_motivo(tmp_path, monkeypatch):
    banco = tmp_path / "fonte.db"
    sqlite3.connect(banco).close()

    def falhar():
        raise ErroGoogle(403, "accessNotConfigured", "Drive API disabled")

    arquivos = SimpleNamespace(list=lambda **kwargs: SimpleNamespace(execute=falhar))
    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_servico_drive_com_timeout", lambda creds, timeout: SimpleNamespace(files=lambda: arquivos))
    ok, mensagem = config.enviar_backup_banco_para_drive_usuario(timeout=5, credenciais=object())
    assert not ok
    assert "403" in mensagem and "accessNotConfigured" in mensagem and "Drive API disabled" in mensagem


def test_credencial_expirada_renova_com_timeout(tmp_path, monkeypatch):
    token = tmp_path / "token-teste.json"
    token.write_text("{}", encoding="utf-8")
    chamadas = []

    class Credenciais:
        expired = True
        refresh_token = "sintetico"
        valid = False
        granted_scopes = [config.GOOGLE_DRIVE_USER_SCOPES[0]]

        def refresh(self, request):
            request("endereco-sintetico")
            self.valid = True

    class Request:
        def __call__(self, _url, timeout=None):
            chamadas.append(timeout)

    creds = Credenciais()
    monkeypatch.setattr(config, "_token_google_drive_usuario_paths", lambda: [str(token)])
    monkeypatch.setattr(config, "GoogleCredentials", SimpleNamespace(from_authorized_user_file=lambda *args: creds))
    monkeypatch.setattr(config, "GoogleAuthRequest", Request)
    monkeypatch.setattr(config, "_salvar_token_google_drive_usuario", lambda valor: chamadas.append("salvo"))
    recebido, msg = config._obter_credenciais_google_drive_usuario(timeout=7)
    assert recebido is creds and msg == "OK"
    assert chamadas == [7, "salvo"]


def test_credencial_sem_escopo_nao_envia_nem_apaga_token(tmp_path, monkeypatch):
    token = tmp_path / "token-teste.json"
    token.write_text("teste", encoding="utf-8")
    creds = SimpleNamespace(expired=False, refresh_token=None, valid=True, granted_scopes=["openid"])
    monkeypatch.setattr(config, "_token_google_drive_usuario_paths", lambda: [str(token)])
    monkeypatch.setattr(config, "GoogleCredentials", SimpleNamespace(from_authorized_user_file=lambda *args: creds))
    recebido, msg = config._obter_credenciais_google_drive_usuario(timeout=7)
    assert recebido is None and "Escopos insuficientes" in msg
    assert token.read_text(encoding="utf-8") == "teste"


@pytest.mark.parametrize("erro", [
    SimpleNamespace(error="access_denied"),
    config.google_auth_oauthlib.flow.WSGITimeoutError("Timed out"),
])
def test_autorizacao_recusada_ou_sem_retorno_orienta_testador(monkeypatch, erro):
    class ErroAutorizacao(Exception):
        error = "access_denied"

    class Fluxo:
        @classmethod
        def from_client_secrets_file(cls, *args):
            return cls()

        def run_local_server(self, **kwargs):
            if isinstance(erro, SimpleNamespace):
                raise ErroAutorizacao()
            raise erro

    monkeypatch.setattr(config, "_token_google_drive_usuario_paths", lambda: [])
    monkeypatch.setattr(config, "_verificar_arquivo_credenciais_google_drive", lambda: (True, "sintetico"))
    monkeypatch.setattr(config, "InstalledAppFlow", Fluxo)
    creds, mensagem = config._obter_credenciais_google_drive_usuario(interativo=True, timeout=5)
    assert creds is None
    assert "testadora" in mensagem and "access_denied" in mensagem


@pytest.fixture(scope="module")
def raiz_gui():
    raiz = ctk.CTk()
    raiz.withdraw()
    yield raiz
    raiz.destroy()


@pytest.fixture
def janela_backup(monkeypatch, raiz_gui):
    monkeypatch.setattr(menu.FrmDadosOficina, "_inicializar_status_fiscal_em_background", lambda self: None)
    monkeypatch.setattr(menu.FrmDadosOficina, "carregar", lambda self: None)
    raiz = raiz_gui
    janela = menu.FrmDadosOficina(raiz)
    yield janela, raiz
    if janela.winfo_exists():
        janela.destroy()


def aguardar(raiz, condicao, tempo=3):
    prazo = time.monotonic() + tempo
    while not condicao() and time.monotonic() < prazo:
        raiz.update()
        time.sleep(0.01)
    assert condicao()


def test_backup_tk_responsivo_e_cancelavel(janela_backup, monkeypatch):
    janela, raiz = janela_backup
    inicio_worker = threading.Event()
    liberar = threading.Event()

    def credenciais(**kwargs):
        inicio_worker.set()
        liberar.wait(3)
        return None, "Operação cancelada."

    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", credenciais)
    try:
        inicio = time.monotonic()
        janela.backup_para_drive_manual()
        assert time.monotonic() - inicio < 0.3
        assert inicio_worker.wait(1)
        chamada = []
        raiz.after(10, lambda: chamada.append(True))
        aguardar(raiz, lambda: bool(chamada), 1)
        janela._cancelar_backup_drive()
        liberar.set()
        aguardar(raiz, lambda: janela.btn_backup_drive.cget("state") == "normal")
        assert "Cancelado" in janela.lbl_status_backup.cget("text")
    finally:
        liberar.set()


@pytest.mark.parametrize("erro", [
    ErroGoogle(403, "storageQuotaExceeded", "Quota exceeded"),
    ErroGoogle(401, "authError", "Invalid credentials"),
    TimeoutError("timed out"),
    ConnectionError("offline"),
])
def test_falha_libera_interface_e_exibe_motivo(janela_backup, monkeypatch, erro):
    janela, raiz = janela_backup
    avisos = []
    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", lambda **kwargs: (object(), "OK"))
    monkeypatch.setattr(menu, "enviar_backup_banco_para_drive_usuario",
                        lambda **kwargs: (False, config._mensagem_erro_backup_drive(erro)))
    monkeypatch.setattr(menu.messagebox, "showwarning", lambda *args, **kwargs: avisos.append(args[1]))
    janela.backup_para_drive_manual()
    aguardar(raiz, lambda: bool(avisos))
    assert janela.btn_backup_drive.cget("state") == "normal"
    assert avisos[0] == config._mensagem_erro_backup_drive(erro)


def test_autorizacao_do_backup_nao_inicia_sincronizacao_da_oficina(janela_backup, monkeypatch):
    janela, raiz = janela_backup
    chamadas = []

    def credenciais(**kwargs):
        return ((object(), "OK") if chamadas else
                (None, "Usuário ainda não autenticado no Google Drive."))

    def conectar(**kwargs):
        chamadas.append(kwargs)
        return True, "OK", ""

    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", credenciais)
    monkeypatch.setattr(menu, "conectar_google_drive_usuario", conectar)
    monkeypatch.setattr(menu, "enviar_backup_banco_para_drive_usuario", lambda **kwargs: (True, "Teste sintético"))
    monkeypatch.setattr(menu.messagebox, "showinfo", lambda *args, **kwargs: None)
    monkeypatch.setattr(menu, "garantir_banco_no_drive_usuario", lambda: pytest.fail("Sincronização não autorizada"))
    monkeypatch.setattr(menu, "iniciar_sincronizacao_hibrida_nuvem", lambda: pytest.fail("Sincronização não autorizada"))
    janela.backup_para_drive_manual()
    aguardar(raiz, lambda: janela.btn_autorizar_backup.cget("state") == "normal")
    janela.btn_autorizar_backup.invoke()
    aguardar(raiz, lambda: janela.btn_backup_drive.cget("state") == "normal")
    assert chamadas[0]["timeout"] == 15
    assert "Backup concluído" in janela.lbl_status_backup.cget("text")


@pytest.mark.parametrize("cancelar", [False, True])
def test_conexao_independente_nao_bloqueia_interface(janela_backup, monkeypatch, cancelar):
    janela, raiz = janela_backup
    iniciou = threading.Event()
    liberar = threading.Event()
    avisos = []

    def conectar(**kwargs):
        assert kwargs["timeout"] == 15
        iniciou.set()
        liberar.wait(3)
        if kwargs["cancelar"].is_set():
            return False, "Operação cancelada.", ""
        return True, "Autorização concluída.", ""

    monkeypatch.setattr(menu, "conectar_google_drive_usuario", conectar)
    monkeypatch.setattr(menu, "garantir_banco_no_drive_usuario", lambda: pytest.fail("Sincronização insegura"))
    monkeypatch.setattr(menu, "iniciar_sincronizacao_hibrida_nuvem", lambda: pytest.fail("Sincronização insegura"))
    monkeypatch.setattr(menu.messagebox, "showinfo", lambda *args, **kwargs: avisos.append(args[1]))
    try:
        janela.conectar_google_drive_oficial()
        assert iniciou.wait(1)
        respostas = []
        raiz.after(10, lambda: respostas.append(True))
        aguardar(raiz, lambda: bool(respostas))
        if cancelar:
            janela._cancelar_backup_drive()
        liberar.set()
        aguardar(raiz, lambda: janela.btn_google.cget("state") == "normal")
        if cancelar:
            assert "Cancelado" in janela.lbl_status_backup.cget("text")
            assert not avisos
        else:
            assert "desativada" in avisos[0]
    finally:
        liberar.set()


def test_sincronizacao_hibrida_nao_sobrescreve_banco_local(tmp_path, monkeypatch):
    banco = tmp_path / "ativo.db"
    banco.write_bytes(b"banco sintetico original")
    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario",
                        lambda **kwargs: pytest.fail("Rede não deve iniciar"))
    for operacao in (config.sincronizar_hibrido_banco_drive, config.iniciar_sincronizacao_hibrida_nuvem):
        ok, msg = operacao()
        assert not ok and "bloqueada" in msg
    assert banco.read_bytes() == b"banco sintetico original"


def test_sincronizacao_antiga_nao_baixa_nem_altera_banco(tmp_path, monkeypatch):
    banco = tmp_path / "ativo.db"
    banco.write_bytes(b"banco sintetico original")
    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario",
                        lambda **kwargs: pytest.fail("Rede não deve iniciar"))
    ok, msg = config.sincronizar_dados_da_nuvem("sintetico", "sintetico")
    assert not ok and "bloqueada" in msg
    assert banco.read_bytes() == b"banco sintetico original"


def test_prazo_total_cancela_e_informa_expiracao(janela_backup, monkeypatch):
    janela, raiz = janela_backup

    def credenciais(**kwargs):
        kwargs["cancelar"].wait(3)
        return None, "Operação cancelada."

    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", credenciais)
    janela.backup_para_drive_manual()
    janela._backup_prazo = time.monotonic() - 1
    aguardar(raiz, lambda: janela.btn_backup_drive.cget("state") == "normal")
    assert "Tempo total excedido" in janela.lbl_status_backup.cget("text")


def test_fechar_janela_invalida_backup_e_preserva_timer_do_menu(janela_backup, monkeypatch):
    janela, raiz = janela_backup
    iniciou = threading.Event()
    encerrou = threading.Event()

    def credenciais(**kwargs):
        iniciou.set()
        kwargs["cancelar"].wait(3)
        encerrou.set()
        return None, "Operação cancelada."

    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", credenciais)
    janela.backup_para_drive_manual()
    assert iniciou.wait(1)
    menu_respondeu = []
    raiz.after(20, lambda: menu_respondeu.append(True))
    janela.destroy()
    aguardar(raiz, lambda: bool(menu_respondeu))
    assert encerrou.wait(1)


def test_listagem_restauro_responsiva_e_cancelavel(janela_backup, monkeypatch):
    janela, raiz = janela_backup
    iniciou = threading.Event()
    liberar = threading.Event()

    def listar(**kwargs):
        iniciou.set()
        liberar.wait(3)
        return False, [], "Operação cancelada."

    monkeypatch.setattr(menu, "listar_backups_banco_drive_usuario", listar)
    try:
        janela.restaurar_do_drive_manual()
        assert iniciou.wait(1)
        chamadas = []
        raiz.after(10, lambda: chamadas.append(True))
        aguardar(raiz, lambda: bool(chamadas), 1)
        janela._cancelar_backup_drive()
        liberar.set()
        aguardar(raiz, lambda: janela.btn_restaurar_drive.cget("state") == "normal")
        assert "cancelada" in janela.lbl_status_backup.cget("text").lower()
    finally:
        liberar.set()


def test_fechar_durante_restauro_cancela_e_aguarda_worker(janela_backup, monkeypatch):
    janela, raiz = janela_backup
    iniciou = threading.Event()
    liberar = threading.Event()

    def listar(**kwargs):
        iniciou.set()
        liberar.wait(3)
        return False, [], "Operação cancelada."

    monkeypatch.setattr(menu, "listar_backups_banco_drive_usuario", listar)
    try:
        janela.restaurar_do_drive_manual()
        assert iniciou.wait(1)
        janela.destroy()
        assert janela.winfo_exists()
        assert janela._restauro_cancelamento.is_set()
        liberar.set()
        aguardar(raiz, lambda: not janela.winfo_exists())
    finally:
        liberar.set()


def test_restauro_na_interface_fica_bloqueado_ate_garantir_inatividade(janela_backup, monkeypatch):
    janela, raiz = janela_backup
    avisos = []
    monkeypatch.setattr(menu, "listar_backups_banco_drive_usuario",
                        lambda **kwargs: (True, [{"id": "sintetico", "name": "teste.db"}], "OK"))
    monkeypatch.setattr(janela, "_selecionar_backup_drive", lambda dados: dados[0])
    monkeypatch.setattr(menu.messagebox, "askyesno", lambda *args, **kwargs: True)
    monkeypatch.setattr(menu.messagebox, "showwarning", lambda *args, **kwargs: avisos.append(args[1]))
    monkeypatch.setattr(config, "restaurar_backup_banco_drive_usuario",
                        lambda *args, **kwargs: pytest.fail("Restauração insegura foi iniciada"))
    janela.restaurar_do_drive_manual()
    aguardar(raiz, lambda: bool(avisos))
    assert "bloqueada" in avisos[0]
    assert janela.btn_restaurar_drive.cget("state") == "normal"


@pytest.mark.skipif(__import__("os").name != "nt", reason="Troca segura requer Windows")
@pytest.mark.parametrize("conteudo_valido", [True, False])
def test_restauro_drive_baixa_e_valida_antes_da_troca(tmp_path, monkeypatch, conteudo_valido):
    banco = tmp_path / "ativo.db"
    candidato = tmp_path / "origem.db"
    for caminho, valor in [(banco, "original"), (candidato, "restaurado")]:
        conn = sqlite3.connect(caminho)
        try:
            conn.executescript(
                "CREATE TABLE dados_oficina(valor TEXT);"
                "CREATE TABLE configuracoes(valor TEXT);"
                "CREATE TABLE orcamentos_aguardo(valor TEXT);"
            )
            conn.execute("INSERT INTO dados_oficina VALUES (?)", (valor,))
            conn.commit()
        finally:
            conn.close()
    conteudo = candidato.read_bytes() if conteudo_valido else b"backup invalido"

    class Download:
        def __init__(self, arquivo, request, chunksize):
            self.arquivo = arquivo

        def next_chunk(self, **kwargs):
            self.arquivo.write(conteudo)
            return None, True

    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", lambda **kwargs: (object(), "OK"))
    monkeypatch.setattr(config, "_servico_drive_com_timeout",
                        lambda *args: SimpleNamespace(files=lambda: SimpleNamespace(get_media=lambda **kwargs: object())))
    monkeypatch.setattr(config, "MediaIoBaseDownload", Download)
    ok, msg = config.restaurar_backup_banco_drive_usuario("sintetico", "teste.db", timeout=5)
    assert ok == conteudo_valido, msg
    with sqlite3.connect(banco) as conn:
        valor = conn.execute("SELECT valor FROM dados_oficina").fetchone()[0]
    assert valor == ("restaurado" if conteudo_valido else "original")
    assert not list(tmp_path.glob("oficina_restore_temporario_*.db"))


@pytest.mark.parametrize("situacao", ["timeout", "cancelamento"])
def test_restauro_nao_aplica_se_download_falhar(tmp_path, monkeypatch, situacao):
    banco = tmp_path / "ativo.db"
    banco.write_bytes(b"banco sintetico original")
    cancelar = threading.Event()

    class Download:
        def __init__(self, arquivo, request, chunksize):
            self.arquivo = arquivo

        def next_chunk(self, **kwargs):
            self.arquivo.write(b"dados parciais")
            if situacao == "timeout":
                raise TimeoutError("timed out")
            cancelar.set()
            return None, False

    monkeypatch.setattr(config, "CAMINHO_BANCO", str(banco))
    monkeypatch.setattr(config, "_obter_credenciais_google_drive_usuario", lambda **kwargs: (object(), "OK"))
    monkeypatch.setattr(config, "_servico_drive_com_timeout",
                        lambda *args: SimpleNamespace(files=lambda: SimpleNamespace(get_media=lambda **kwargs: object())))
    monkeypatch.setattr(config, "MediaIoBaseDownload", Download)
    ok, msg = config.restaurar_backup_banco_drive_usuario("sintetico", timeout=5, cancelar=cancelar)
    assert not ok
    assert ("Tempo" if situacao == "timeout" else "cancelada") in msg
    assert banco.read_bytes() == b"banco sintetico original"
    assert not list(tmp_path.glob("oficina_restore_temporario_*.db"))
