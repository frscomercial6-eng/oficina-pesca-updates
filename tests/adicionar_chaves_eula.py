# -*- coding: utf-8 -*-
"""Adiciona as chaves do EULA (primeiro acesso) aos 3 arquivos de idioma.

Atualiza ``locales/*.json`` do código-fonte e do build protegido.
Uso: python tests/adicionar_chaves_eula.py
"""
import json
import os

CHAVES = {
    "eula_titulo": {
        "pt_BR": "Contrato de Licença de Uso",
        "en_US": "Software License Agreement",
        "es_UY": "Contrato de Licencia de Uso",
    },
    "eula_aceitar": {
        "pt_BR": "Aceitar e Continuar",
        "en_US": "Accept and Continue",
        "es_UY": "Aceptar y Continuar",
    },
    "eula_recusar": {
        "pt_BR": "Recusar e Sair",
        "en_US": "Decline and Exit",
        "es_UY": "Rechazar y Salir",
    },
    "eula_aviso": {
        "pt_BR": "Leia o contrato abaixo. Para utilizar o sistema, é necessário aceitar os termos.",
        "en_US": "Read the agreement below. Acceptance of the terms is required to use the system.",
        "es_UY": "Lea el contrato a continuación. Para utilizar el sistema, es necesario aceptar los términos.",
    },
    "eula_aceite_obrigatorio_titulo": {
        "pt_BR": "Aceite obrigatório",
        "en_US": "Acceptance required",
        "es_UY": "Aceptación obligatoria",
    },
    "eula_aceite_obrigatorio_msg": {
        "pt_BR": "Você precisa aceitar o Contrato de Licença para utilizar o sistema. Deseja encerrar?",
        "en_US": "You must accept the License Agreement to use the system. Do you want to exit?",
        "es_UY": "Debe aceptar el Contrato de Licencia para utilizar el sistema. ¿Desea salir?",
    },
    "eula_indisponivel": {
        "pt_BR": "Contrato indisponível no momento.",
        "en_US": "Agreement unavailable at the moment.",
        "es_UY": "Contrato no disponible en este momento.",
    },
}

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINOS = [
    os.path.join(RAIZ, "locales"),
    os.path.normpath(os.path.join(RAIZ, os.pardir, "build_protegido", "locales")),
]

IDOMAS = ("pt_BR", "es_UY", "en_US")


def main() -> int:
    falhas = 0
    for pasta in DESTINOS:
        for idioma in IDOMAS:
            caminho = os.path.join(pasta, f"{idioma}.json")
            if not os.path.isfile(caminho):
                print(f"[AVISO] Arquivo ausente: {caminho}")
                falhas += 1
                continue
            with open(caminho, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            antes = len(dados)
            for chave, traducoes in CHAVES.items():
                dados[chave] = traducoes[idioma]
            with open(caminho, "w", encoding="utf-8", newline="\n") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2, sort_keys=True)
                arquivo.write("\n")
            print(f"[OK] {caminho}: {antes} -> {len(dados)} chaves")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
