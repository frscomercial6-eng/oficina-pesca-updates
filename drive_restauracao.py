"""Aplicação segura de backups SQLite no Windows."""
import ctypes
import os
import sqlite3
import tempfile
import time
import uuid
from ctypes import wintypes
from pathlib import Path


def _verificar_cancelamento(cancelar, prazo):
    if cancelar is not None and cancelar.is_set():
        raise InterruptedError("Restauração cancelada.")
    if prazo is not None and time.monotonic() >= prazo:
        raise TimeoutError("Tempo de restauração excedido.")


def _validar_banco(caminho, cancelar=None, prazo=None):
    uri = Path(caminho).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        def interromper():
            return int((cancelar is not None and cancelar.is_set()) or
                       (prazo is not None and time.monotonic() >= prazo))

        conn.set_progress_handler(interromper, 1000)
        try:
            integridade = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.OperationalError:
            _verificar_cancelamento(cancelar, prazo)
            raise
        _verificar_cancelamento(cancelar, prazo)
        if integridade != ("ok",):
            raise ValueError("O backup não passou na verificação de integridade SQLite.")
        tabelas = {linha[0] for linha in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if not {"dados_oficina", "configuracoes", "orcamentos_aguardo"} <= tabelas:
            raise ValueError("O arquivo não contém as tabelas essenciais da Oficina.")
    finally:
        conn.close()


def _substituir(kernel, banco, candidato, copia_sistema):
    if not kernel.ReplaceFileW(banco, candidato, copia_sistema, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def aplicar_backup(candidato, banco, cancelar=None, timeout=30):
    """Valida e troca o banco apenas quando nenhum processo o mantém aberto."""
    if os.name != "nt":
        raise RuntimeError("Restauração segura indisponível neste sistema operacional.")
    prazo = time.monotonic() + timeout if timeout is not None else None
    candidato = os.path.abspath(candidato)
    banco = os.path.abspath(banco)
    _verificar_cancelamento(cancelar, prazo)
    _validar_banco(candidato, cancelar, prazo)
    _verificar_cancelamento(cancelar, prazo)
    if os.path.dirname(candidato) != os.path.dirname(banco):
        raise ValueError("O backup preparado precisa estar no mesmo diretório do banco.")

    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.ReplaceFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID,
    ]
    kernel.ReplaceFileW.restype = wintypes.BOOL
    handle = kernel.CreateFileW(banco, 0x80000000, 4, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise OSError("Banco em uso ou inacessível; feche as outras conexões antes de restaurar.")
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except Exception:
        kernel.CloseHandle(handle)
        raise
    copia_sistema = None
    copia = None
    try:
        with os.fdopen(fd, "rb") as origem:
            for sufixo in ("-wal", "-shm", "-journal"):
                if os.path.exists(banco + sufixo):
                    raise RuntimeError(f"Arquivo SQLite pendente ({sufixo}); restauração não aplicada.")
            pasta = os.path.join(os.path.dirname(banco), "backup_db")
            os.makedirs(pasta, exist_ok=True)
            fd_copia, copia = tempfile.mkstemp(prefix="pre_drive_restore_", suffix=".db", dir=pasta)
            try:
                with os.fdopen(fd_copia, "wb") as destino:
                    while True:
                        _verificar_cancelamento(cancelar, prazo)
                        bloco = origem.read(1024 * 1024)
                        if not bloco:
                            break
                        destino.write(bloco)
                    destino.flush()
                    os.fsync(destino.fileno())
                _validar_banco(copia, cancelar, prazo)
            except Exception:
                os.remove(copia)
                raise
            _verificar_cancelamento(cancelar, prazo)
            copia_sistema = os.path.join(pasta, f"pre_drive_original_{uuid.uuid4().hex}.db")
            _substituir(kernel, banco, candidato, copia_sistema)
            return copia
    except (InterruptedError, TimeoutError):
        raise
    except OSError as erro:
        if copia_sistema and os.path.exists(copia_sistema) and not os.path.exists(banco):
            try:
                os.rename(copia_sistema, banco)
            except OSError as recuperacao:
                raise OSError(
                    f"Falha na troca e recuperação automática: {recuperacao}. "
                    f"Cópia anterior preservada em {copia}."
                ) from erro
        if copia:
            raise OSError(f"Falha ao trocar o banco; cópia anterior preservada em {copia}: {erro}") from erro
        raise
