import os, subprocess, sys, shutil, time

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, '_build_short.log')

DEST = r'C:\test_build'
SPEC = os.path.join(DEST, 'Oficina_Pesca.spec')

os.chdir(BASE)
print(f"Python: {PYI}")

# Remove dest if exists
if os.path.exists(DEST):
    print(f"Removing {DEST}...")
    shutil.rmtree(DEST, ignore_errors=True)
    time.sleep(1)

# Create destination
print(f"Creating {DEST}...")
os.makedirs(DEST, exist_ok=True)

# Copy only necessary files
NEEDED = [
    'login.py', 'menu.py', 'tela_os.py', 'config.py', 'dados_oficina.py',
    'versao.json', 'version.txt', 'assets', 'Documentos',
    'client_secret_desktop.json', 'fundomenu.png', 'LOGO.bmp', 'icone_oficina.ico',
    'config.cfg', 'locales',
    'Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf',
    'Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf',
    'Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf',
    'core', 'shutdown_utils.py', 'version_info.py',
    'tela_planos.py', 'FrmProdutos.py', 'FrmPdv.py', 'FrmEstoque.py',
]

for item in NEEDED:
    src = os.path.join(BASE, item)
    dst = os.path.join(DEST, item)
    if os.path.exists(src):
        if os.path.isdir(src):
            print(f"  Copying dir: {item}")
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            print(f"  Copying file: {item}")
            shutil.copy2(src, dst)

# Create spec
spec = r'''# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['login.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'firebase_admin',
        'firebase_admin.credentials',
    ],
    excludes=[],
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
    icon=[],
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
print(f"Spec criado: {SPEC}")

# Build
print("\nIniciando build no caminho curto...")
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

print(f"\nEXIT: {proc.returncode}")
with open(LOG, 'r', encoding='utf-8') as f:
    lines = f.readlines()
print(f"Log: {len(lines)} linhas")
for l in lines[-20:]:
    print(f"  {l.rstrip()}")

exe_path = os.path.join(DEST, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
if os.path.exists(exe_path):
    print(f"EXE: {os.path.getsize(exe_path):,} bytes")
else:
    print("EXE: NAO ENCONTRADO")
