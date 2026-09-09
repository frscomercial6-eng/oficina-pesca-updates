import os, subprocess, sys, time, shutil

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, '_build_611.log')

os.chdir(BASE)

print(f"Python: {PYI}")
r = subprocess.run([PYI, '-m', 'PyInstaller', '--version'], capture_output=True, text=True)
print(f"PyInstaller: {r.stdout.strip()}")

# Remove old build
for path in [os.path.join(BASE, 'Oficina_Pesca.spec'),
              os.path.join(BASE, 'build'),
              os.path.join(BASE, 'dist')]:
    if os.path.exists(path):
        print(f"Removing: {path}")
        shutil.rmtree(path, ignore_errors=True)
time.sleep(1)

# Create spec
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
        'urllib',
        'urllib.request',
        'urllib.error',
        'ssl',
    ],
    excludes=[
        '.backup_i18n', 'api', 'android_apk', 'infra', 'static',
        'templates', 'tests', 'tools',
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

with open(os.path.join(BASE, 'Oficina_Pesca.spec'), 'w', encoding='utf-8') as f:
    f.write(spec)

print("Spec created. Starting build...")
log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

proc = subprocess.Popen(
    [PYI, '-m', 'PyInstaller', os.path.join(BASE, 'Oficina_Pesca.spec'), '--noconfirm'],
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

print(f"\nEXIT: {proc.returncode}")

with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
print(f"Log: {len(lines)} linhas")
for l in lines[-20:]:
    print(f"  {l.rstrip()}")

exe_path = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
print(f"EXE: {os.path.exists(exe_path)}")
if os.path.exists(exe_path):
    print(f"Size: {os.path.getsize(exe_path):,} bytes")
