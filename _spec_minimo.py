import os

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
SPEC = os.path.join(BASE, 'Oficina_Pesca_minimo.spec')

# Mínimo: apenas login.py + customtkinter + firebase_admin
# Sem google, sem cryptography, sem heavy deps
content = '''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['login.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('client_secret_desktop.json', '.'),
        ('dados_oficina.py', '.'),
        ('fundomenu.png', '.'),
        ('LOGO.bmp', '.'),
        ('icone_oficina.ico', '.'),
        ('config.cfg', '.'),
        ('versao.json', '.'),
        ('version.txt', '.'),
        ('Documentos/termos_de_uso.txt', 'Documentos'),
        ('Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf', '.'),
        ('locales', 'locales'),
    ],
    hiddenimports=[
        'firebase_admin',
        'firebase_admin.credentials',
        'firebase_admin.initialize_app',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Oficina_Pesca_Min',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets/seu_icone.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Oficina_Pesca_Min',
)
'''

with open(SPEC, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Spec mínimo criado: {SPEC}")

import ast
ast.parse(content, filename=SPEC)
print("Sintaxe OK")
