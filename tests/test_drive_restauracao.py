import os
import sqlite3
import threading
from contextlib import closing

import pytest

import drive_restauracao


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Restauração segura usa API do Windows")


def criar_banco(caminho, valor):
    with closing(sqlite3.connect(caminho)) as conn:
        with conn:
            conn.executescript(
                "CREATE TABLE dados_oficina (valor TEXT);"
                "CREATE TABLE configuracoes (valor TEXT);"
                "CREATE TABLE orcamentos_aguardo (valor TEXT);"
            )
            conn.execute("INSERT INTO dados_oficina VALUES (?)", (valor,))


def ler_valor(caminho):
    with closing(sqlite3.connect(caminho)) as conn:
        return conn.execute("SELECT valor FROM dados_oficina").fetchone()[0]


def test_troca_preserva_copia_verificada(tmp_path):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    criar_banco(candidato, "restaurado")
    copia = drive_restauracao.aplicar_backup(candidato, banco)
    assert ler_valor(banco) == "restaurado"
    assert ler_valor(copia) == "original"


def test_conexao_ativa_impede_troca(tmp_path):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    criar_banco(candidato, "restaurado")
    conn = sqlite3.connect(banco)
    try:
        with pytest.raises(OSError, match="Banco em uso"):
            drive_restauracao.aplicar_backup(candidato, banco)
    finally:
        conn.close()
    assert ler_valor(banco) == "original"


def test_backup_invalido_e_cancelamento_preservam_original(tmp_path):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    candidato.write_bytes(b"arquivo invalido")
    with pytest.raises(sqlite3.DatabaseError):
        drive_restauracao.aplicar_backup(candidato, banco)
    candidato.unlink()
    criar_banco(candidato, "restaurado")
    cancelar = threading.Event()
    cancelar.set()
    with pytest.raises(InterruptedError):
        drive_restauracao.aplicar_backup(candidato, banco, cancelar)
    assert ler_valor(banco) == "original"


def test_falha_na_troca_preserva_original_e_copia(tmp_path, monkeypatch):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    criar_banco(candidato, "restaurado")
    monkeypatch.setattr(drive_restauracao, "_substituir", lambda *args: (_ for _ in ()).throw(OSError("simulado")))
    with pytest.raises(OSError, match="cópia anterior preservada"):
        drive_restauracao.aplicar_backup(candidato, banco)
    assert ler_valor(banco) == "original"
    copias = list((tmp_path / "backup_db").glob("pre_drive_restore_*.db"))
    assert len(copias) == 1 and ler_valor(copias[0]) == "original"


def test_falha_parcial_recupera_arquivo_original(tmp_path, monkeypatch):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    criar_banco(candidato, "restaurado")

    def falhar_apos_renomear(kernel, original, novo, copia_sistema):
        os.rename(original, copia_sistema)
        raise OSError(1177, "Falha parcial simulada")

    monkeypatch.setattr(drive_restauracao, "_substituir", falhar_apos_renomear)
    with pytest.raises(OSError, match="cópia anterior preservada"):
        drive_restauracao.aplicar_backup(candidato, banco)
    assert ler_valor(banco) == "original"


def test_falha_na_recuperacao_informa_copia_verificavel(tmp_path, monkeypatch):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    criar_banco(candidato, "restaurado")
    renomear = os.rename

    def falhar_apos_renomear(kernel, original, novo, copia_sistema):
        renomear(original, copia_sistema)
        raise OSError(1177, "Falha parcial simulada")

    def falhar_recuperacao(origem, destino):
        raise OSError("Recuperação simulada indisponível")

    monkeypatch.setattr(drive_restauracao, "_substituir", falhar_apos_renomear)
    monkeypatch.setattr(drive_restauracao.os, "rename", falhar_recuperacao)
    with pytest.raises(OSError, match="Falha na troca e recuperação automática"):
        drive_restauracao.aplicar_backup(candidato, banco)
    copias = list((tmp_path / "backup_db").glob("pre_drive_restore_*.db"))
    assert len(copias) == 1 and ler_valor(copias[0]) == "original"


def test_timeout_e_wal_preservam_original(tmp_path):
    banco, candidato = tmp_path / "banco.db", tmp_path / "candidato.db"
    criar_banco(banco, "original")
    criar_banco(candidato, "restaurado")
    with pytest.raises(TimeoutError):
        drive_restauracao.aplicar_backup(candidato, banco, timeout=0)
    wal = tmp_path / "banco.db-wal"
    wal.write_bytes(b"pendente sintetico")
    with pytest.raises(RuntimeError, match="pendente"):
        drive_restauracao.aplicar_backup(candidato, banco)
    wal.unlink()
    assert ler_valor(banco) == "original"
