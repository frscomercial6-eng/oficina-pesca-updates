import subprocess
PYI = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'

# Check firebase_admin's own dependencies
r = subprocess.run([PYI, '-m', 'pip', 'show', 'firebase-admin'], capture_output=True, text=True)
print("firebase-admin package:")
print(r.stdout[:500])
print()

# Check what firebase_admin imports
r2 = subprocess.run([PYI, '-c', 
    "import sys; sys.path.insert(0, 'F:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL'); "
    "import firebase_admin; "
    "print('firebase_admin imported OK')"
], capture_output=True, text=True, cwd=r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL')
print("Firebase import:", r2.stdout, r2.stderr)

print()

# Check googleapiclient
r3 = subprocess.run([PYI, '-c', 
    "import googleapiclient; print('googleapiclient OK')"
], capture_output=True, text=True)
print("googleapiclient:", r3.stdout, r3.stderr)

print()

# Check psutil
r4 = subprocess.run([PYI, '-c', 
    "import psutil; print('psutil OK:', psutil.__version__)"
], capture_output=True, text=True)
print("psutil:", r4.stdout, r4.stderr)

print()

# Check what firebase_admin/__init__.py imports
with open(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\firebase_admin\__init__.py') as f:
    content = f.read()
print("firebase_admin/__init__.py imports:")
for line in content.split('\n')[:50]:
    if 'import' in line.lower() and not line.strip().startswith('#'):
        print(f"  {line.strip()}")

print()

# Check if googleapiclient or psutil are in the hidden imports
print("Checking if googleapiclient exists anywhere:")
r5 = subprocess.run(['python', '-c', 
    "import os; p='F:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/.venv/Lib/site-packages'; "
    "items = [n for n in os.listdir(p) if 'googleapiclient' in n.lower() or 'google_api' in n.lower()]; "
    "print('Found:', items)"], capture_output=True, text=True)
print(r5.stdout)

# Check what's in googleapiclient
r6 = subprocess.run(['python', '-c',
    "import os; p='F:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/.venv/Lib/site-packages'; "
    "items = [n for n in os.listdir(p) if n.startswith('google')]; "
    "print('Google packages:', items)"], capture_output=True, text=True)
print(r6.stdout)
