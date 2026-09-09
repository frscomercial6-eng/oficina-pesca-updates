# diagnostic runner
import subprocess, os, time
PY = r"F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe"
BASE = r"F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
LOG = os.path.join(BASE, "diag_results.txt")
F = 0x08000000
results = []
try:
    import psutil
    env = "RAM=%dGB DiskF=%dGB" % (psutil.virtual_memory().available//(1024**3), psutil.disk_usage("F:").free//(1024**3))
except:
    env = "?"
r1 = subprocess.run([PY, "--version"], capture_output=True, creationflags=F)
r2 = subprocess.run([PY, "-m", "PyInstaller", "--version"], capture_output=True, creationflags=F)
print("PY=%s PYI=%s %s" % (r1.stdout.decode().strip(), r2.stdout.decode().strip(), env))
with open(LOG, "w") as f:
    f.write("PY=%s PYI=%s %s\n\n" % (r1.stdout.decode().strip(), r2.stdout.decode().strip(), env))

def test(name, args):
    print("\n--- %s ---" % name)
    t0 = time.time()
    lp = os.path.join(BASE, "diag_%s.txt" % name)
    cmd = [PY, "-m", "PyInstaller", "--onedir", "--windowed", "--clean", "--noconfirm", "--paths=.", "--name", name] + args + ["login.py"]
    p = subprocess.Popen(cmd, cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, creationflags=F)
    try:
        out, _ = p.communicate(timeout=300)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        p.kill(); out = b"TIMEOUT"; rc = -999
    elapsed = time.time() - t0
    with open(lp, "w", encoding="utf-8") as lf:
        lf.write(out.decode("utf-8", errors="replace"))
    dist_ok = os.path.exists(os.path.join(BASE, "dist", name))
    status = "PASS" if rc == 0 and dist_ok else "FAIL"
    lines = [l for l in out.decode("utf-8", errors="replace").split("\n") if l.strip()]
    print("[%s] rc=%d %.0fs dist=%s" % (status, rc, elapsed, dist_ok))
    for l in lines[-5:]: print("  %s" % l[:120])
    results.append((name, status, rc, elapsed))
    with open(LOG, "a") as f:
        f.write("[%s] %s rc=%d %.0fs dist=%s\n" % (status, name, rc, elapsed, dist_ok))
    return rc == 0 and dist_ok

ok1 = test("T1_MINIMO", [])
if not ok1:
    print("T1_MINIMO FALHOU - parando")
else:
    ok2 = test("T2_CTK", ["--collect-all", "customtkinter"])
    if not ok2:
        print("T2_CTK FALHOU")
    else:
        ok3 = test("T3_FPDF", ["--collect-all", "customtkinter", "--collect-all", "fpdf", "--collect-all", "reportlab"])
        if not ok3:
            print("T3_FPDF FALHOU")


        else:
            ok4 = test("T4_GOOGLE", [
                "--collect-all", "customtkinter", "--collect-all", "fpdf", "--collect-all", "reportlab",
                "--collect-all", "googleapiclient", "--collect-all", "google_auth_oauthlib",
                "--collect-all", "google", "--collect-all", "google_auth",
                "--hidden-import", "firebase_admin", "--hidden-import", "googleapiclient",
                "--hidden-import", "googleapiclient.discovery", "--hidden-import", "googleapiclient.errors",
                "--hidden-import", "googleapiclient.http", "--hidden-import", "googleapiclient._auth",
                "--hidden-import", "google_auth_oauthlib", "--hidden-import", "google_auth_oauthlib.flow",
                "--hidden-import", "google.oauth2", "--hidden-import", "google.oauth2.credentials",
                "--hidden-import", "google.oauth2.service_account", "--hidden-import", "google.auth",
                "--hidden-import", "google.auth.transport", "--hidden-import", "google.auth.transport.requests",
                "--hidden-import", "google.auth.exceptions",
            ])
            if not ok4:
                print("T4_GOOGLE FALHOU")
            else:
                ok5 = test("T5_OAUTH", [
                    "--collect-all", "customtkinter", "--collect-all", "fpdf", "--collect-all", "reportlab",
                    "--collect-all", "googleapiclient", "--collect-all", "google_auth_oauthlib",
                    "--collect-all", "google", "--collect-all", "google_auth",
                    "--hidden-import", "firebase_admin", "--hidden-import", "googleapiclient",
                    "--hidden-import", "googleapiclient.discovery", "--hidden-import", "googleapiclient.errors",
                    "--hidden-import", "googleapiclient.http", "--hidden-import", "googleapiclient._auth",
                    "--hidden-import", "google_auth_oauthlib", "--hidden-import", "google_auth_oauthlib.flow",
                    "--hidden-import", "google.oauth2", "--hidden-import", "google.oauth2.credentials",
                    "--hidden-import", "google.oauth2.service_account", "--hidden-import", "google.auth",
                    "--hidden-import", "google.auth.transport", "--hidden-import", "google.auth.transport.requests",
                    "--hidden-import", "google.auth.exceptions",
                    "--hidden-import", "oauth2client", "--hidden-import", "oauth2client.client",
                    "--hidden-import", "oauth2client.file", "--hidden-import", "oauth2client.tools",
                    "--hidden-import", "httplib2", "--hidden-import", "urllib", "--hidden-import", "urllib.request",
                    "--hidden-import", "urllib.error", "--hidden-import", "ssl", "--hidden-import", "certifi",
                ])
                if not ok5:
                    print("T5_OAUTH FALHOU")
                else:
                    ok6 = test("T6_ASSETS", [
                        "--collect-all", "customtkinter", "--collect-all", "fpdf", "--collect-all", "reportlab",
                        "--collect-all", "googleapiclient", "--collect-all", "google_auth_oauthlib",
                        "--collect-all", "google", "--collect-all", "google_auth",
                        "--hidden-import", "firebase_admin", "--hidden-import", "googleapiclient",
                        "--hidden-import", "googleapiclient.discovery", "--hidden-import", "googleapiclient.errors",
                        "--hidden-import", "googleapiclient.http", "--hidden-import", "googleapiclient._auth",
                        "--hidden-import", "google_auth_oauthlib", "--hidden-import", "google_auth_oauthlib.flow",
                        "--hidden-import", "google.oauth2", "--hidden-import", "google.oauth2.credentials",
                        "--hidden-import", "google.oauth2.service_account", "--hidden-import", "google.auth",
                        "--hidden-import", "google.auth.transport", "--hidden-import", "google.auth.transport.requests",
                        "--hidden-import", "google.auth.exceptions",
                        "--hidden-import", "oauth2client", "--hidden-import", "oauth2client.client",
                        "--hidden-import", "oauth2client.file", "--hidden-import", "oauth2client.tools",
                        "--hidden-import", "httplib2", "--hidden-import", "urllib", "--hidden-import", "urllib.request",
                        "--hidden-import", "urllib.error", "--hidden-import", "ssl", "--hidden-import", "certifi",
                        "--add-data", "assets;assets",
                        "--add-data", "client_secret_desktop.json;.",
                        "--add-data", "client_secret_desktop.json;assets",
                        "--add-data", "dados_oficina.py;.",
                        "--add-data", "fundomenu.png;.",
                        "--add-data", "LOGO.bmp;.",
                        "--add-data", "icone_oficina.ico;.",
                        "--add-data", "config.cfg;.",
                        "--add-data", "versao.json;.",
                        "--add-data", "version.json;.",
                        "--add-data", "version.txt;.",
                        "--add-data", "Documentos/termos_de_uso.txt;Documentos",
                        "--add-data", "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf;.",
                        "--add-data", "Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf;.",
                        "--add-data", "Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf;.",
                        "--add-data", "locales;locales",
                        "--icon", "assets/seu_icone.ico",
                    ])

print("\n=== SUMMARY ===")
for name, status, rc, elapsed in results:
    print("  [%s] %s rc=%d %.0fs" % (status, name, rc, elapsed))
first = next(((n) for n, s, _, _ in results if s == "FAIL"), None)
if first:
    print("\nFIRST FAILURE: %s" % first)
print("\nLog: %s" % LOG)