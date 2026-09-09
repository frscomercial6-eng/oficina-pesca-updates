import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_v1064.log')

os.chdir(BASE)

print(f"PYI: {PYI}")
print(f"SPEC: {SPEC}")

# Remove old spec
if os.path.exists(SPEC):
    os.remove(SPEC)
time.sleep(0.5)

# Create minimal spec - ONLY actual imports from login.py
# Remove: googleapiclient, google_auth, oauth2client, httplib2
# These are NOT directly imported by login.py
spec = r'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['login.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('client_secret_desktop.json', '.'),
        ('client_secret_desktop.json', 'assets'),
        ('dados_oficina.py', '.'),
        ('fundomenu.png', '.'),
        ('LOGO.bmp', '.'),
        ('icone_oficina.ico', '.'),
        ('config.cfg', '.'),
        ('versao.json', '.'),
        ('version.json', '.'),
        ('version.txt', '.'),
        ('Documentos/termos_de_uso.txt', 'Documentos'),
        ('Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf', '.'),
        ('Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf', '.'),
        ('Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf', '.'),
        ('locales', 'locales'),
    ],
    hiddenimports=[
        'firebase_admin',
        'firebase_admin.credentials',
        'firebase_admin.db',
        'firebase_admin.auth',
        'firebase_admin.storage',
        'firebase_admin.messaging',
        'firebase_admin._auth_client',
        'firebase_admin._auth_utils',
        'firebase_admin._http_client',
        'firebase_admin._token_gen',
        'firebase_admin._user_identifier',
        'firebase_admin._utils',
        'google.api_core',
        'google.api_core.exceptions',
        'google.api_core.page_iterator',
        'google.api_core.retry',
        'google.auth',
        'google.auth.transport._requests',
        'google.auth.exceptions',
        'google.auth.credentials',
        'google.cloud.core',
        'google.cloud.firestore',
        'google.cloud.firestore_v1',
        'google.cloud.storage',
        'google.cloud.storage.blob',
        'google.cloud.storage.client',
        'google.crc32c',
        'httpx',
        'anyio',
        'certifi',
        'fpdf',
        'reportlab',
        'reportlab.lib.pagesizes',
        'reportlab.pdfgen',
        'reportlab.platypus',
        'psutil',
    ],
    excludes=[
        '.backup_i18n',
        'api',
        'android_apk',
        'infra',
        'static',
        'templates',
        'tests',
        'tools',
        'cryptography',
        'googleapiclient',
        'google_api_python_client',
        'oauth2client',
        'google_auth_oauthlib',
        'google_auth_httplib2',
        'httplib2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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
    name='Oficina_Pesca',
)
'''

with open(SPEC, 'w', encoding='utf-8') as f:
    f.write(spec)
print("Spec criado")

# Check syntax
import ast
try:
    ast.parse(spec, filename=SPEC)
    print("Sintaxe OK")
except SyntaxError as e:
    print(f"SINTAXE ERRO: {e}")
    exit(1)

# Install psutil
print("\nInstalando psutil...")
r = subprocess.run([PYI, '-m', 'pip', 'install', 'psutil'], capture_output=True, text=True)
print(r.stdout.strip())
if r.returncode != 0:
    print("PSUTIL INSTALL ERR:", r.stderr[:200])

# Now build
print("\nIniciando build...")
print()

log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', SPEC, '--noconfirm'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    text=True,
)

print(f"PID: {proc.pid}")

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    sys.stdout.write(line)
    sys.stdout.flush()

proc.wait()
log_file.close()

exit_code = proc.returncode
print(f"\nEXIT: {exit_code}")

with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
print(f"Log: {len(lines)} linhas")
if lines:
    print(f"ULTIMA: {lines[-1].strip()}")

dist_exe = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
if os.path.exists(dist_exe):
    size = os.path.getsize(dist_exe)
    print(f"EXE: {size:,} bytes ({size/1024/1024:.1f} MB)")
else:
    print("EXE: NAO ENCONTRADO")
    
build_dir = os.path.join(BASE, 'build', 'Oficina_Pesca')
if os.path.exists(build_dir):
    items = os.listdir(build_dir)
    print(f"BUILD: {len(items)} items -> {items[:10]}")
else:
    print("BUILD: VAZIO")
