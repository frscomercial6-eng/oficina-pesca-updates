# -*- coding: utf-8 -*-
"""Cria ZIP limpo do projeto para transferencia de build."""
import os, zipfile

SRC = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
DST = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_v1.0.64_BUILD.zip'

EXCLUIR = {'.venv', '__pycache__', 'dist', 'build', 'PACOTE_ENVIO',
    'INSTALADOR_FINAL', 'Output', 'BACKUPS_OFP', 'BACKUPS_B3',
    '.git', 'node_modules', '.vscode', '.idea', '.backup_i18n',
    'BACKUPS_B3'}

ARQ_EXCLUIR = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib',
    'Thumbs.db', '.DS_Store', 'desktop.ini'}

total = 0
arqs = 0
zf = zipfile.ZipFile(DST, 'w', zipfile.ZIP_DEFLATED, compresslevel=1)
try:
    for raiz, dirs, arquivos in os.walk(SRC):
        dirs[:] = [d for d in dirs if d not in EXCLUIR]
        for nome in arquivos:
            if any(nome.endswith(e) for e in ARQ_EXCLUIR):
                continue
            caminho = os.path.join(raiz, nome)
            arco = os.path.relpath(caminho, SRC).replace(os.sep, '/')
            zf.write(caminho, arco)
            total += os.path.getsize(caminho)
            arqs += 1
finally:
    zf.close()
print(f'ZIP: {arqs} arquivos, {total/1024/1024:.1f} MB')
print(f'Arquivo: {DST}')
