# -*- coding: utf-8 -*-
"""
Build isolated para Oficina de Pesca v1.0.64.
Cria ambiente virtual limpo, compila e gera instalador.
Tudo num script Python puro - sem PowerShell, sem PSReadLine.
"""
import subprocess, sys, os, shutil, time

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable  # usa o Python que já está rodando

def run(cmd, timeout=None, check=True):
    print(f"\n>>> {' '.join(cmd[:3])}...")
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=timeout)
    if r.stdout:
        for line in r.stdout.splitlines()[:5]:
            print(f"    {line}")
    if r.returncode != 0 and check:
        print(f"    STDERR: {r.stderr[:500]}")
        print(f"    EXIT: {r.returncode}")
    else:
        print(f"    EXIT: {r.returncode}")
    return r

def clean_old():
    """Remove dist/build para build limpo."""
    for d in ["dist", "build"]:
        p = os.path.join(BASE, d)
        if os.path.exists(p):
            print(f"Removendo {p}...")
            shutil.rmtree(p, ignore_errors=True)

print("=" * 60)
print("OFICINA DE PESCA v1.0.64 - BUILD ISOLATED")
print("=" * 60)

# 1. Verificar ambiente
print("\n[1] Verificando ambiente...")
r = run([PY, "--version"], check=False)
r = run([PY, "-m", "PyInstaller", "--version"], check=False)
r = run([PY, "-c", "import sys; print(sys.executable)"], check=False)
r = run([PY, "-c", "import customtkinter, firebase_admin, googleapiclient, reportlab, fpdf; print('ALL_OK')"], check=False)

# 2. Verificar sintaxe
print("\n[2] Verificando sintaxe...")
for f in ["menu.py", "tela_os.py", "mestre_build.py"]:
    path = os.path.join(BASE, f)
    r = run([PY, "-m", "py_compile", path], check=False)
    if r.returncode == 0:
        print(f"  OK: {f}")

# 3. Compilar EXE (sem --clean para reutilizar cache)
print("\n[3] Compilando EXE com PyInstaller...")
clean_old()
cmd = [
    PY, "-m", "PyInstaller",
    "--onedir", "--windowed", "--noconfirm",
    "--paths", ".",
    "--name", "Oficina_Pesca",
]
# Hidden imports
for h in [
    "firebase_admin", "googleapiclient", "googleapiclient.discovery",
    "googleapiclient.errors", "googleapiclient.http", "googleapiclient._auth",
    "google_auth_oauthlib", "google_auth_oauthlib.flow",
    "google.oauth2", "google.oauth2.credentials", "google.oauth2.service_account",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "google.auth.exceptions",
    "oauth2client", "oauth2client.client", "oauth2client.file", "oauth2client.tools",
    "httplib2", "urllib", "urllib.request", "urllib.error", "ssl", "certifi",
    "psutil", "pyperclip",
]:
    cmd += ["--hidden-import", h]

# Add data
for src, dst in [
    ("assets", "assets"), ("client_secret_desktop.json", "."),
    ("client_secret_desktop.json", "assets"), ("dados_oficina.py", "."),
    ("fundomenu.png", "."), ("LOGO.bmp", "."), ("icone_oficina.ico", "."),
    ("config.cfg", "."), ("versao.json", "."), ("version.json", "."),
    ("version.txt", "."), ("Documentos/termos_de_uso.txt", "Documentos"),
    ("Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf", "."),
    ("Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf", "."),
    ("Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf", "."),
    ("locales", "locales"),
]:
    cmd += ["--add-data", f"{src};{dst}"]

cmd += ["--icon", "assets\\seu_icone.ico", "login.py"]

# Versao
vf = os.path.join(BASE, "build", "version_file.txt")
if os.path.exists(vf):
    cmd += ["--version-file", vf]

# Executar com timeout grande (30 min)
print(f"\n[3b] Executando PyInstaller (timeout=3600s)...")
try:
    r = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, timeout=3600)
    print(f"\n    EXITCODE: {r.returncode}")
    if r.stdout:
        lines = r.stdout.splitlines()
        print(f"    ULTIMAS 10 LINHAS:")
        for line in lines[-10:]:
            print(f"      {line}")
    if r.returncode != 0 and r.stderr:
        print(f"    STDERR (500 chars): {r.stderr[:500]}")
except subprocess.TimeoutExpired:
    print("    TIMEOUT: PyInstaller excedeu 60 minutos!")
    sys.exit(1)

if r.returncode != 0:
    print("\n    ERRO: PyInstaller falhou.")
    sys.exit(1)

# 4. Verificar EXE
print("\n[4] Verificando EXE...")
exe = os.path.join(BASE, "dist", "Oficina_Pesca", "Oficina_Pesca.exe")
if os.path.exists(exe):
    size = os.path.getsize(exe)
    print(f"  OK: {exe} ({size:,} bytes = {size/1024/1024:.1f} MB)")
else:
    print(f"  ERRO: EXE nao encontrado em {exe}")
    sys.exit(1)

# 5. Smoke test
print("\n[5] Smoke test do EXE...")
if os.path.exists(exe):
    try:
        p = subprocess.Popen([exe, "--version"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        out, err = p.communicate(timeout=5)
        print(f"  EXIT: {p.returncode}")
        if out:
            for line in out.decode('utf-8', errors='replace').splitlines()[:3]:
                print(f"  {line}")
        if err:
            print(f"  ERR: {err.decode('utf-8', errors='replace')[:200]}")
    except subprocess.TimeoutExpired:
        p.kill()
        print("  TIMEOUT: EXE nao respondeu em 5s")
    except Exception as e:
        print(f"  ERRO smoke test: {e}")

# 6. Gerar instalador
print("\n[6] Gerando instalador Inno Setup...")
iss = os.path.join(BASE, "instalar.iss")
if os.path.exists(iss):
    iscc = "C:\\Program Files (x86)\\Inno Setup 6\\ISCC.exe"
    if os.path.exists(iscc):
        r = run([iscc, iss], timeout=300)
        inst = os.path.join(BASE, "PACOTE_ENVIO", "Oficina_Pesca_Instalador.exe")
        if os.path.exists(inst):
            print(f"  OK: {inst} ({os.path.getsize(inst)/1024/1024:.1f} MB)")
        else:
            print(f"  ATENCAO: instalador nao encontrado em {inst}")
    else:
        print(f"  ISCC nao encontrado: {iscc}")
else:
    print(f"  ERRO: instalar.iss nao encontrado")

print("\n" + "=" * 60)
print("BUILD ISOLATED CONCLUIDO")
print("=" * 60)
