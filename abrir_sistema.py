# -*- coding: utf-8 -*-
"""
Abre diretamente o menu principal, sem passar pela autenticação do login.
Uso: python abrir_sistema.py
"""

import traceback


def main():
    try:
        import config
        config.inicializar_banco()

        import menu
        # Perfil ADMIN para liberar todos os modulos durante homologacao.
        menu.iniciar_sistema(usuario="HOMOLOG", role="ADMIN", senha_login="")
    except Exception as exc:
        print(f"Erro ao abrir menu direto: {exc}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
