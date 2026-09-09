import subprocess 
import sys 
import os 

pyinstaller_path = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\pyinstaller.exe' 
os.chdir(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL') 

cmd = [ 
    pyinstaller_path, 
    '--name=Oficina_Pesca', 
    '--windowed', 
    '--onefile', 
    '--clean', 
    '--log-level=DEBUG', 
    '--hidden-import=firebase_admin', 
    '--hidden-import=firebase_admin.credentials', 
    '--hidden-import=firebase_admin.db', 
    '--hidden-import=firebase_admin.auth', 
    'login.py' 
] 

result = subprocess.run(cmd, capture_output=True, text=True) 
print(result.stdout) 
print(result.stderr) 
print('Return code:', result.returncode) 
