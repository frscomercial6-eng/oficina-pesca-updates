import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

import PyInstaller.__main__

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, 'build_api.log')

os.chdir(BASE)

print(f"Python: {sys.executable}")
print(f"PyInstaller: {__import__('PyInstaller').__version__}")
print()

# Write spec
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
        'firebase_admin._auth_client',
        'firebase_admin._auth_utils',
        'firebase_admin._http_client',
        'firebase_admin._token_gen',
        'firebase_admin._user_identifier',
        'google.api_core',
        'google.api_core.exceptions',
        'google.auth',
        'google.auth.transport._requests',
        'google.auth.exceptions',
        'google.auth.credentials',
        'google.cloud.core',
        'google.cloud.firestore',
        'google.cloud.storage',
        'google.crc32c',
        'httpx',
        'anyio',
        'certifi',
        'fpdf',
        'reportlab',
        'psutil',
        'urllib',
        'urllib.request',
        'urllib.error',
        'ssl',
    ],
    excludes=[
        '.backup_i18n', 'api', 'android_apk', 'infra', 'static',
        'templates', 'tests', 'tools',
        'cryptography', 'googleapiclient', 'google_api_python_client',
        'oauth2client', 'google_auth_oauthlib', 'google_auth_httplib2', 'httplib2',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='Oficina_Pesca',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=['assets/seu_icone.ico'],
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[], name='Oficina_Pesca',
)
'''

spec_path = os.path.join(BASE, 'Oficina_Pesca.spec')
with open(spec_path, 'w', encoding='utf-8') as f:
    f.write(spec)
print(f"Spec: {spec_path}")

# Run via PyInstaller API
import io
from contextlib import redirect_stdout, redirect_stderr

log_file = open(LOG, 'w', encoding='utf-8')

class TeeOutput:
    def __init__(self, file):
        self.file = file
    def write(self, data):
        self.file.write(data)
        self.file.flush()
        sys.stdout.write(data)
        sys.stdout.flush()
    def flush(self):
        self.file.flush()

print("Starting PyInstaller build via API...")

# Capture output
old_stdout = sys.stdout
old_stderr = sys.stderr
sys.stdout = TeeOutput(log_file)
sys.stderr = TeeOutput(log_file)

try:
    PyInstaller.__main__.run([
        spec_path,
        '--noconfirm',
        '--log-level=INFO',
    ])
    print("BUILD COMPLETED SUCCESSFULLY")
except SystemExit as e:
    print(f"SystemExit: {e.code}")
except Exception as e:
    print(f"EXCEPTION: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
finally:
    sys.stdout = old_stdout
    sys.stderr = old_stderr
    log_file.close()

# Check results
print()
print("Checking results...")
dist_exe = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
if os.path.exists(dist_exe):
    size = os.path.getsize(dist_exe)
    print(f"EXE FOUND: {size:,} bytes ({size/1024/1024:.1f} MB)")
else:
    print("EXE NOT FOUND")
    
build_dir = os.path.join(BASE, 'build', 'Oficina_Pesca')
if os.path.exists(build_dir):
    items = os.listdir(build_dir)
    print(f"BUILD DIR: {len(items)} items -> {items[:10]}")
else:
    print("BUILD DIR: EMPTY OR NOT FOUND")

# Show log end
print()
print("Last 20 lines of log:")
with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
for l in lines[-20:]:
    print(f"  {l.rstrip()}")
