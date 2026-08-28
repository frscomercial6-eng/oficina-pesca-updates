# -*- coding: utf-8 -*-
"""Troca os módulos de regra de negócio pelos binários .pyd gerados pelo Nuitka
(pasta build_protegido) antes do PyInstaller, e restaura os .py depois do build.

Uso:
    python aplicar_protegido.py aplicar
    python aplicar_protegido.py restaurar

Deve ser executado com o diretório de trabalho igual à raiz do projeto
(OFICINA_PESCA_ORIGINAL), que é o que gerar_release.bat já garante via `cd /d`.
"""
import glob
import os
import shutil
import sys

ROOT = os.getcwd()
PROTEGIDO = os.path.join(os.path.dirname(ROOT), "build_protegido")

MODULOS = [
    "gestao_os.py", "tela_os.py", "tela_financeiro.py", "tela_planos.py", "clientes.py",
    "pdv.py", "util_recibo.py", "configuracao_fiscal.py", "adaptador_acbr.py",
    "migracao_fiscal_2027.py", "dados_oficina.py", "status_os.py", "validador_fiscal.py",
    "reforma_tributaria.py", "config.py", "gerador_licenca.py", "servidor.py",
    os.path.join("core", "gestao_os_repository.py"),
    os.path.join("core", "gestao_os_service.py"),
    os.path.join("core", "i18n.py"),
    os.path.join("core", "licenca.py"),
    os.path.join("core", "modulos.py"),
    os.path.join("core", "os_repository.py"),
    os.path.join("core", "os_service.py"),
    os.path.join("core", "sincronizacao.py"),
    os.path.join("core", "financeiro", "calculos.py"),
    os.path.join("core", "financeiro", "repository.py"),
    os.path.join("core", "financeiro", "service.py"),
]


def _pyd_no_protegido(modulo_rel: str):
    pasta = os.path.join(PROTEGIDO, os.path.dirname(modulo_rel))
    stem = os.path.splitext(os.path.basename(modulo_rel))[0]
    achados = glob.glob(os.path.join(pasta, f"{stem}.*.pyd"))
    return achados[0] if achados else None


def aplicar():
    if not os.path.isdir(PROTEGIDO):
        print(f"[ERRO] Pasta protegida nao encontrada: {PROTEGIDO}")
        sys.exit(1)
    aplicados = 0
    for modulo in MODULOS:
        py_path = os.path.join(ROOT, modulo)
        pyd_origem = _pyd_no_protegido(modulo)
        if not pyd_origem:
            print(f"[AVISO] Sem .pyd protegido para {modulo}; mantendo fonte .py.")
            continue
        if os.path.exists(py_path):
            shutil.move(py_path, py_path + ".bak")
        destino = os.path.join(ROOT, os.path.dirname(modulo), os.path.basename(pyd_origem))
        shutil.copy2(pyd_origem, destino)
        aplicados += 1
        print(f"[OK] {modulo} -> {os.path.basename(pyd_origem)}")
    print(f"Total de modulos protegidos aplicados: {aplicados}/{len(MODULOS)}")


def restaurar():
    restaurados = 0
    for modulo in MODULOS:
        py_path = os.path.join(ROOT, modulo)
        backup = py_path + ".bak"
        pasta = os.path.join(ROOT, os.path.dirname(modulo))
        stem = os.path.splitext(os.path.basename(modulo))[0]
        for pyd in glob.glob(os.path.join(pasta, f"{stem}.*.pyd")):
            os.remove(pyd)
        if os.path.exists(backup):
            if os.path.exists(py_path):
                os.remove(py_path)
            shutil.move(backup, py_path)
            restaurados += 1
    print(f"Total de modulos restaurados para .py original: {restaurados}/{len(MODULOS)}")


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else ""
    if acao == "aplicar":
        aplicar()
    elif acao == "restaurar":
        restaurar()
    else:
        print("Uso: aplicar_protegido.py [aplicar|restaurar]")
        sys.exit(1)
