import subprocess
PYI = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'

# Check firebase_admin structure
r = subprocess.run([PYI, '-c', 
    "import firebase_admin; import os; print('FA_PATH:', firebase_admin.__file__); "
    "fa_dir = os.path.dirname(firebase_admin.__file__); "
    "files = os.listdir(fa_dir); "
    "print('FILES:', [f for f in files if not f.startswith('_py')][:30])"
], capture_output=True, text=True)
print("firebase_admin structure:")
print(r.stdout)
if r.stderr:
    print("STDERR:", r.stderr)

print()

# Check if firebase-admin command is available
r2 = subprocess.run([PYI, '-c', 
    "import firebase_admin._sse_app; print('_sse_app OK')"
], capture_output=True, text=True)
print("SSE app:", r2.stdout, r2.stderr)

print()

# Check what modules firebase_admin imports
r3 = subprocess.run([PYI, '-c', 
    "import firebase_admin; import sys; mods = [m for m in sys.modules.keys() if 'firebase' in m.lower()]; print('Firebase mods:', mods)"
], capture_output=True, text=True)
print("Firebase modules:", r3.stdout)

print()

# Check reportlab
r4 = subprocess.run([PYI, '-c', 
    "import reportlab; from reportlab.lib.pagesizes import A4; print('reportlab OK:', reportlab.Version)"
], capture_output=True, text=True)
print("ReportLab:", r4.stdout, r4.stderr)

print()

# Check what's actually imported by login.py
print("Checking imports of login.py...")
r5 = subprocess.run([PYI, '-c', 
    "import ast; "
    "with open('F:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/login.py') as f: "
    "tree = ast.parse(f.read()); "
    "imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)] + "
    "[n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]; "
    "print('ALL IMPORTS:', sorted(set(imports)))"
], capture_output=True, text=True)
print("login.py imports:", r5.stdout)
