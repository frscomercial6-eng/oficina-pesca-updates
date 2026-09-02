# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets'), ('client_secret_desktop.json', '.'), ('client_secret_desktop.json', 'assets'), ('dados_oficina.py', '.'), ('fundomenu.png', '.'), ('LOGO.bmp', '.'), ('icone_oficina.ico', '.'), ('config.cfg', '.'), ('versao.json', '.'), ('version.json', '.'), ('version.txt', '.'), ('Documentos/termos_de_uso.txt', 'Documentos'), ('Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf', '.'), ('Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf', '.'), ('Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf', '.'), ('locales', 'locales')]
binaries = []
hiddenimports = ['adaptador_acbr', 'clientes', 'config', 'configuracao_fiscal', 'dados_oficina', 'gestao_os', 'menu', 'login', 'migracao_fiscal_2027', 'pdv', 'shutdown_utils', 'tela_financeiro', 'tela_os', 'tela_planos', 'util_recibo', 'core.i18n', 'firebase_admin', 'googleapiclient', 'googleapiclient.discovery', 'googleapiclient.errors', 'googleapiclient.http', 'googleapiclient._auth', 'google_auth_oauthlib', 'google_auth_oauthlib.flow', 'google.oauth2', 'google.oauth2.credentials', 'google.oauth2.service_account', 'google.auth', 'google.auth.transport', 'google.auth.transport.requests', 'google.auth.exceptions', 'oauth2client', 'oauth2client.client', 'oauth2client.file', 'oauth2client.tools', 'httplib2', 'urllib', 'urllib.request', 'urllib.error', 'ssl', 'certifi']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('fpdf')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('googleapiclient')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google_auth_oauthlib')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google_auth')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('google_api_python_client')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('reportlab')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['login.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name='Oficina_Pesca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='build/version_file.txt',
    icon=['icone_oficina.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Oficina_Pesca',
)
