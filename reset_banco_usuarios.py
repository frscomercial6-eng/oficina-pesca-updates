# -*- coding: utf-8 -*-
"""
reset_banco_usuarios.py

Objetivo:
- Limpar somente a tabela de usuarios.
- Manter o restante do banco intacto.
- Permitir que o login.py detecte banco sem usuarios e abra a tela
  de criacao do primeiro ADMIN automaticamente.
"""

import os
import shutil
import sqlite3
from datetime import datetime

import config


def criar_backup_banco(caminho_banco: str) -> str | None:
    if not os.path.exists(caminho_banco):
        return None

    pasta_backup = os.path.join(os.path.dirname(caminho_banco), "backup_db")
    os.makedirs(pasta_backup, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(pasta_backup, f"oficina_antes_reset_usuarios_{timestamp}.db")
    shutil.copy2(caminho_banco, destino)
    return destino


def resetar_tabela_usuarios():
    # Garante que schema/tabelas existem
    config.inicializar_banco()

    caminho_banco = config.CAMINHO_BANCO
    backup_path = criar_backup_banco(caminho_banco)

    conn = sqlite3.connect(caminho_banco)
    try:
        cur = conn.cursor()

        # Limpa somente usuarios
        cur.execute("DELETE FROM usuarios")

        # Opcional: reseta sequencia de IDs da tabela usuarios
        cur.execute("DELETE FROM sqlite_sequence WHERE name = 'usuarios'")

        conn.commit()
    finally:
        conn.close()

    print("=" * 72)
    print(f"Banco alvo: {caminho_banco}")
    if backup_path:
        print(f"Backup criado em: {backup_path}")
    print("Tabela 'usuarios' limpa com sucesso.")
    print("Agora rode: python login.py")
    print("=" * 72)


if __name__ == "__main__":
    resetar_tabela_usuarios()
