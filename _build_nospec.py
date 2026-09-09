import os, subprocess, sys, time

BASE = os.path.dirname(os.path.abspath(__file__))
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, 'build_nospec.log')

os.chdir(BASE)

print(f"PYI: {PYI}")
print()

# Build WITHOUT spec file - pure command line
cmd = [
    PYI, '-m', 'PyInstaller',
    '--name=Oficina_Pesca',
    '--windowed',
    '--onedir',
    '--noconfirm',
    '--log-level=INFO',
    '--exclude-module', 'cryptography',
    '--exclude-module', 'googleapiclient',
    '--exclude-module', 'google_api_python_client',
    '--exclude-module', 'oauth2client',
    '--exclude-module', 'google_auth_oauthlib',
    '--exclude-module', 'httplib2',
    '--exclude-module', 'google_auth_httplib2',
    '--exclude-module', 'nacl',
    '--exclude-module', 'enchant',
    '--exclude-module', 'fpect',
    # Data files
    '--add-data', 'assets;assets',
    '--add-data', 'client_secret_desktop.json;assets',
    '--add-data', 'dados_oficina.py;.',
    '--add-data', 'config.cfg;.',
    '--add-data', 'versao.json;.',
    '--add-data', 'version.json;.',
    '--add-data', 'version.txt;.',
    '--add-data', 'Documentos;Documentos',
    '--add-data', 'Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf;.',
    '--add-data', 'Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf;.',
    '--add-data', 'Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf;.',
    '--add-data', 'locales;locales',
    '--icon', 'assets/seu_icone.ico',
    '--hidden-import=firebase_admin',
    '--hidden-import=firebase_admin.credentials',
    '--hidden-import=firebase_admin.db',
    '--hidden-import=firebase_admin.auth',
    '--hidden-import=firebase_admin._auth_client',
    '--hidden-import=firebase_admin._auth_utils',
    '--hidden-import=firebase_admin._http_client',
    '--hidden-import=firebase_admin._token_gen',
    '--hidden-import=firebase_admin._user_identifier',
    '--hidden-import=google.api_core',
    '--hidden-import=google.api_core.exceptions',
    '--hidden-import=google.auth',
    '--hidden-import=google.auth.transport._requests',
    '--hidden-import=google.auth.exceptions',
    '--hidden-import=google.auth.credentials',
    '--hidden-import=google.cloud.core',
    '--hidden-import=google.cloud.firestore',
    '--hidden-import=google.cloud.firestore_v1',
    '--hidden-import=google.cloud.storage',
    '--hidden-import=google.crc32c',
    '--hidden-import=httpx',
    '--hidden-import=anyio',
    '--hidden-import=certifi',
    '--hidden-import=fpdf',
    '--hidden-import=reportlab',
    '--hidden-import=psutil',
    '--hidden-import=urllib',
    '--hidden-import=urllib.request',
    '--hidden-import=urllib.error',
    '--hidden-import=ssl',
    'login.py',
]

print("CMD:", ' '.join(cmd[:10]) + '...')
print()

log_file = open(LOG, 'w', encoding='utf-8', buffering=1)

proc = subprocess.Popen(
    cmd,
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

dist_dir = os.path.join(BASE, 'dist', 'Oficina_Pesca')
if os.path.exists(dist_dir):
    exe = os.path.join(dist_dir, 'Oficina_Pesca.exe')
    if os.path.exists(exe):
        size = os.path.getsize(exe)
        print(f"EXE: {exe} ({size:,} bytes, {size/1024/1024:.1f} MB)")
    else:
        print("DIR EXISTS but no EXE")
        print("DIR CONTENTS:", os.listdir(dist_dir)[:10])
else:
    print("DIST DIR: NAO ENCONTRADO")
