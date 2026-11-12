"""Isolamento de rede opt-in para a validação local da DEV."""
from __future__ import annotations

import functools
import os
import subprocess
import sys
import threading

_local = threading.local()
_ativo = False
_base = os.path.dirname(os.path.abspath(__file__))
_banco = os.path.join(_base, "runtime_test_isolado", "20261112_1015", "oficina_v1.0.66_test.db")
_dados = os.path.join(_base, "runtime_test_isolado", "20261112_1015", "user_data")
_worker_pdf = os.path.join(_base, "busca_vista_pdf.py")


def ativo():
    return _ativo


def _mesmo_caminho(valor, esperado):
    return bool(valor) and os.path.normcase(os.path.realpath(valor)) == os.path.normcase(os.path.realpath(esperado))


def _worker_permitido(args):
    if len(args) < 4 or args[2] is not None or args[3] is not None:
        return False
    comando = args[1]
    esperado = [sys.executable, "-u", _worker_pdf, "--worker"]
    if args[0] is not None and not _mesmo_caminho(args[0], sys.executable):
        return False
    if isinstance(comando, str):
        return comando == subprocess.list2cmdline(esperado)
    return isinstance(comando, (list, tuple)) and list(comando) == esperado


def _auditar(evento, args):
    if evento in {"socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                  "socket.gethostbyaddr", "socket.sendto", "socket.sendmsg"}:
        if not getattr(_local, "rede_tecnica", False):
            raise PermissionError("Rede bloqueada durante a validação isolada.")
    elif evento in {"subprocess.Popen", "os.startfile", "os.startfile/2", "os.system",
                    "os.spawn", "os.exec", "os.posix_spawn"}:
        if evento == "subprocess.Popen" and _worker_permitido(args):
            return
        if not getattr(_local, "navegador_usuario", False):
            raise PermissionError("Processo externo bloqueado durante a validação isolada.")


def iniciar_se_solicitado():
    global _ativo
    if os.environ.get("OFP_VALIDACAO_ISOLADA") != "1":
        return
    if _ativo:
        return
    if (not _mesmo_caminho(os.environ.get("OFP_DB_PATH"), _banco)
            or not os.path.isfile(_banco)
            or not _mesmo_caminho(os.environ.get("LOCALAPPDATA"), _dados)
            or not _mesmo_caminho(os.environ.get("APPDATA"), _dados)):
        raise RuntimeError("Validação isolada exige o banco e os diretórios de teste autorizados.")
    sys.addaudithook(_auditar)
    _ativo = True


def _permitir(nome):
    def decorar(funcao):
        @functools.wraps(funcao)
        def executar(*args, **kwargs):
            if not _ativo:
                return funcao(*args, **kwargs)
            anterior = getattr(_local, nome, False)
            setattr(_local, nome, True)
            try:
                return funcao(*args, **kwargs)
            finally:
                setattr(_local, nome, anterior)
        return executar
    return decorar


rede_tecnica = _permitir("rede_tecnica")
navegador_usuario = _permitir("navegador_usuario")
