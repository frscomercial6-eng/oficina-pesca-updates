import subprocess, sys

PYI = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'

pkgs = ['firebase_admin', 'reportlab', 'googleapiclient', 'google-auth', 'cryptography', 
        'PIL', 'fpdf', 'fpdf2', 'psutil', 'pyperclip', 'httplib2']

for pkg in pkgs:
    r = subprocess.run([PYI, '-m', 'pip', 'show', pkg], capture_output=True, text=True)
    if r.returncode == 0:
        lines = r.stdout.split('\n')
        for line in lines:
            if 'Version:' in line or 'Name:' in line:
                print(line.strip())
    else:
        print(f"{pkg}: NOT FOUND")

print()
print("Checking PyInstaller hooks for reportlab and firebase_admin:")
hooks = ['hook-reportlab.py', 'hook-firebase_admin.py', 'hook-PIL.py', 'hook-PIL.Image.py']
for hook in hooks:
    r = subprocess.run([PYI, '-c', f"import os; p=r'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL\\.venv\\Lib\\site-packages\\PyInstaller\\hooks\\{hook}'; print('EXISTS:', os.path.exists(p))"], capture_output=True, text=True)
    print(f"  {hook}: {r.stdout.strip()}")
    
# Check what's in firebase_admin
r = subprocess.run([PYI, '-c', "import firebase_admin; print('firebase_admin OK:', firebase_admin.__version__); import firebase_admin._sse_app; print('_sse_app OK')"], capture_output=True, text=True)
print(f"\nfirebase_admin details: {r.stdout.strip()}")

# Check reportlab 
r = subprocess.run([PYI, '-c', "import reportlab; print('reportlab OK:', reportlab.Version)"], capture_output=True, text=True)
print(f"reportlab: {r.stdout.strip()}")
