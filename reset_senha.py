# -*- coding: utf-8 -*-
"""
Script utilitario para listar usuarios e redefinir senha no banco local.

Como usar:
1) python reset_senha.py
2) Escolha um usuario pelo ID ou nome
3) Informe a nova senha (ou Enter para usar 123)
"""

import sqlite3
import sys
from getpass import getpass

import config


def conectar_banco() -> sqlite3.Connection:
    config.inicializar_banco()
    return sqlite3.connect(config.CAMINHO_BANCO)


def listar_usuarios(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT id, usuario, role FROM usuarios ORDER BY id")
    rows = cur.fetchall()

    print("=" * 70)
    print("BANCO:", config.CAMINHO_BANCO)
    print("USUARIOS CADASTRADOS:")
    if not rows:
        print("- Nenhum usuario encontrado.")
    else:
        for uid, usuario, role in rows:
            print(f"- ID={uid} | usuario={usuario} | role={role}")
    print("=" * 70)
    return rows


def buscar_usuario(conn: sqlite3.Connection, identificador: str):
    cur = conn.cursor()

    if identificador.isdigit():
        cur.execute(
            "SELECT id, usuario, role FROM usuarios WHERE id = ? LIMIT 1",
            (int(identificador),),
        )
        row = cur.fetchone()
        if row:
            return row

    cur.execute(
        "SELECT id, usuario, role FROM usuarios WHERE UPPER(usuario)=UPPER(?) LIMIT 1",
        (identificador.strip(),),
    )
    return cur.fetchone()


def redefinir_senha(conn: sqlite3.Connection, usuario_id: int, nova_senha: str):
    senha_hash = config.hash_password(nova_senha)
    cur = conn.cursor()
    cur.execute("UPDATE usuarios SET senha = ? WHERE id = ?", (senha_hash, usuario_id))
    conn.commit()


def main():
    try:
        conn = conectar_banco()
    except Exception as exc:
        print(f"ERRO: nao foi possivel abrir o banco: {exc}")
        sys.exit(1)

    try:
        rows = listar_usuarios(conn)
        if not rows:
            print("Sem usuarios no banco. Crie um usuario ADMIN primeiro pelo login.py.")
            sys.exit(2)

        identificador = input("Digite o ID ou nome do usuario para resetar senha: ").strip()
        if not identificador:
            print("Operacao cancelada: usuario nao informado.")
            sys.exit(3)

        alvo = buscar_usuario(conn, identificador)
        if not alvo:
            print("Usuario nao encontrado.")
            sys.exit(4)

        uid, usuario, role = alvo
        print(f"Usuario selecionado: ID={uid} | usuario={usuario} | role={role}")

        print("\nNova senha:")
        print("- Pressione Enter sem digitar nada para usar senha padrao 123")
        senha1 = getpass("Digite a nova senha: ").strip()
        if not senha1:
            senha1 = "123"
            print("Senha padrao aplicada: 123")
        senha2 = getpass("Confirme a nova senha: ").strip()
        if not senha2:
            senha2 = senha1

        if senha1 != senha2:
            print("ERRO: as senhas nao coincidem.")
            sys.exit(5)

        redefinir_senha(conn, uid, senha1)

        print("\nOK: senha redefinida com sucesso.")
        print(f"Login: usuario={usuario}")
        print("Agora voce ja pode abrir o sistema e entrar com essa senha.")

    except KeyboardInterrupt:
        print("\nOperacao cancelada pelo usuario.")
        sys.exit(130)
    except Exception as exc:
        print(f"ERRO inesperado: {exc}")
        sys.exit(9)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
