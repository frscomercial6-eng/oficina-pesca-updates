import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_v1064.log')

os.chdir(BASE)

print(f"CWD: {os.getcwd()}")
print(f"PYI: {PYI}")
print()

# Remove old spec
if os.path.exists(SPEC):
    os.remove(SPEC)
    print("Old spec removed")

time.sleep(1)

# Create clean spec WITH cryptography excluded
spec_content = r'''# -*- mode: python ; coding: utf-8 -*-

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
        'googleapiclient',
        'googleapiclient.discovery',
        'googleapiclient.errors',
        'googleapiclient.http',
        'googleapiclient._auth',
        'google_auth_oauthlib',
        'google_auth_oauthlib.flow',
        'google.oauth2',
        'google.oauth2.credentials',
        'google.oauth2.service_account',
        'google.auth',
        'google.auth.transport',
        'google.auth.transport.requests',
        'google.auth.exceptions',
        'oauth2client',
        'oauth2client.client',
        'oauth2client.file',
        'oauth2client.tools',
        'httplib2',
        'urllib',
        'urllib.request',
        'urllib.error',
        'ssl',
        'certifi',
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
    f.write(spec_content)

print(f"Spec criado com cryptography excluido: {SPEC}")

# Now build
print()
print("Starting build...")

log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', SPEC, '--noconfirm'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    bufsize=1,
    text=True,
)

print(f"Started PID: {proc.pid}")

for line in proc.stdout:
    log_file.write(line)
    log_file.flush()
    sys.stdout.write(line)
    sys.stdout.flush()

proc.wait()
log_file.close()

exit_code = proc.returncode

print()
print(f"EXIT CODE: {exit_code}")

with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    print(f"LOG LINES: {len(lines)}")
    if lines:
        print(f"LAST LINE: {lines[-1].strip()}")

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
    print("BUILD DIR: NOT FOUND")
