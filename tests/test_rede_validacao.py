import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "runtime_test_isolado" / "20261112_1015"


def _executar(codigo, **alteracoes):
    env = os.environ.copy()
    env.update({
        "OFP_VALIDACAO_ISOLADA": "1",
        "OFP_DB_PATH": str(DATA / "oficina_v1.0.66_test.db"),
        "LOCALAPPDATA": str(DATA / "user_data"),
        "APPDATA": str(DATA / "user_data"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    env.update(alteracoes)
    return subprocess.run(
        [sys.executable, "-c", codigo], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=15,
    )


def test_isolamento_bloqueia_rede_processos_e_preserva_acesso_tecnico():
    resultado = _executar("""
import socket, sys, threading
import rede_validacao as r
r.iniciar_se_solicitado()
def bloqueado(evento, *args):
    try:
        sys.audit(evento, *args)
    except PermissionError:
        return
    raise AssertionError(evento + ' não bloqueado')
for evento, args in (
    ('socket.getaddrinfo', ('example.test', 443, 0, 0, 0)),
    ('socket.connect', (None, ('127.0.0.1', 443))),
    ('socket.sendto', (None, ('127.0.0.1', 443))),
    ('subprocess.Popen', ('cmd', ['cmd'], None, None)),
    ('os.startfile', ('https://example.test', None)),
):
    bloqueado(evento, *args)
try:
    socket.getaddrinfo('127.0.0.1', 443)
except PermissionError:
    pass
else:
    raise AssertionError('getaddrinfo não bloqueado')
s = socket.socket()
try:
    try:
        s.connect_ex(('127.0.0.1', 9))
    except PermissionError:
        pass
    else:
        raise AssertionError('connect_ex não bloqueado')
finally:
    s.close()
erros = []
@r.rede_tecnica
def acesso_tecnico():
    sys.audit('socket.connect', None, ('127.0.0.1', 443))
    assert socket.getaddrinfo('127.0.0.1', 443)
    def outra_thread():
        try:
            bloqueado('socket.connect', None, ('127.0.0.1', 443))
        except AssertionError as exc:
            erros.append(str(exc))
    t = threading.Thread(target=outra_thread)
    t.start()
    t.join()
acesso_tecnico()
assert not erros, erros
bloqueado('socket.connect', None, ('127.0.0.1', 443))
@r.navegador_usuario
def abrir_link():
    sys.audit('os.startfile', 'https://example.test', None)
abrir_link()
bloqueado('os.startfile', 'https://example.test', None)
sys.audit('subprocess.Popen', sys.executable, [sys.executable, '-u', r._worker_pdf, '--worker'], None, None)
""")
    assert resultado.returncode == 0, resultado.stderr


def test_isolamento_recusa_banco_diferente_antes_de_ativar():
    resultado = _executar("import rede_validacao as r; r.iniciar_se_solicitado()", OFP_DB_PATH="outro.db")
    assert resultado.returncode != 0
    assert "banco e os diretórios de teste autorizados" in resultado.stderr


def test_analise_pdf_em_processo_funciona_com_isolamento():
    resultado = _executar("""
import io, threading
import pypdfium2 as pdfium
import rede_validacao as r
r.iniciar_se_solicitado()
import busca_vista_pdf
pdf = pdfium.PdfDocument.new()
pagina = pdf.new_page(100, 100)
pagina.close()
saida = io.BytesIO()
pdf.save(saida)
pdf.close()
resultado = busca_vista_pdf.analisar_em_processo(
    saida.getvalue(), 'https://example.test/diagrama.pdf', 'SHIMANO', 'CURADO', threading.Event()
)
assert resultado['status'] == 'scanned' and resultado['pages'] == 1, resultado
""")
    assert resultado.returncode == 0, resultado.stderr


def test_busca_e_visualizador_permanecem_autorizados_sem_rede_real():
    resultado = _executar("""
import sys, threading
from unittest.mock import patch
import rede_validacao as r
r.iniciar_se_solicitado()
import busca_vista_defeitos as d
import busca_vista_visualizador as v
import tela_os
class Resposta:
    headers = {'Content-Type': 'text/html; charset=utf-8'}
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, *args): return b'<html>teste</html>'
    def geturl(self): return 'https://example.test/threads/teste/'
def abrir(*args, **kwargs):
    sys.audit('socket.connect', None, ('127.0.0.1', 443))
    return Resposta()
with patch.object(d, 'urlopen', side_effect=abrir):
    assert 'teste' in d._buscar_html('https://example.test/threads/teste/', 1)[0]
with patch.object(tela_os, 'urlopen', side_effect=abrir):
    assert 'teste' in tela_os.FrmOS._buscar_pagina_tecnica(None, 'https://example.test/', 1)[0]
class Pdf(Resposta):
    def read(self, *args):
        if hasattr(self, 'lido'): return b''
        self.lido = True
        return b'%PDF-1.4 teste'
def abrir_pdf(*args, **kwargs):
    sys.audit('socket.connect', None, ('127.0.0.1', 443))
    return Pdf()
with patch.object(v, 'urlopen', side_effect=abrir_pdf):
    assert v.baixar_pdf('https://example.test/a.pdf', threading.Event()).startswith(b'%PDF')
""")
    assert resultado.returncode == 0, resultado.stderr
