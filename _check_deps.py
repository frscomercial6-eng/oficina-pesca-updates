import subprocess
PYI = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'

# Check if googleapiclient is installed
r = subprocess.run([PYI, '-m', 'pip', 'show', 'google-api-python-client'], capture_output=True, text=True)
print("google-api-python-client (googleapiclient):")
print(r.stdout[:300])
print(r.stderr[:100])
print()

# Check what login.py imports for authentication
print("Checking login.py imports:")
with open(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\login.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
import_lines = [l.strip() for l in content.split('\n') 
                if ('import ' in l or 'from ' in l) and not l.strip().startswith('#')]
for line in import_lines[:50]:
    print(f"  {line}")

print()
# Check if Supabase is installed
r2 = subprocess.run([PYI, '-m', 'pip', 'show', 'supabase'], capture_output=True, text=True)
print("Supabase:")
print(r2.stdout[:300])

print()
# Check firebase_admin version and what's needed
r3 = subprocess.run([PYI, '-c', 
    "import firebase_admin; "
    "from firebase_admin import credentials; "
    "from firebase_admin import auth; "
    "from firebase_admin import db; "
    "print('firebase_admin modules OK')"], capture_output=True, text=True)
print("Firebase modules:", r3.stdout, r3.stderr)
