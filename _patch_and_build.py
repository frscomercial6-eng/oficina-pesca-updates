# -*- coding: utf-8 -*-
from pathlib import Path
import subprocess
import sys
import time
import os

os.chdir(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL')

# Step 1: Patch mestre_build.py - remove --collect-all
p = Path('mestre_build.py')
s = p.read_text(encoding='utf-8')
for x in [
    '--collect-all customtkinter',
    '--collect-all fpdf',
    '--collect-all googleapiclient',
    '--collect-all google_auth_oauthlib',
    '--collect-all google',
    '--collect-all google_auth',
    '--collect-all google_api_python_client',
    '--collect-all reportlab',
]:
    s = s.replace(x, '')
p.write_text(s, encoding='utf-8')
print('Patch OK: --collect-all removed')

# Step 2: Run the build
log_file = open('build_v1063.log', 'w', encoding='utf-8', buffering=1)
proc = subprocess.Popen(
    [sys.executable, 'mestre_build.py', '--no-bump', '--nome', 'Oficina_Pesca', '--auto', '--no-git'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
)
for line in proc.stdout:
    print(line, end='')
    log_file.write(line)
    log_file.flush()
proc.wait()
log_file.close()

print(f'\n=== EXIT CODE: {proc.returncode} ===')

# Step 3: Check results
dist_exe = Path('dist/Oficina_Pesca/Oficina_Pesca.exe')
pacote_inst = Path('PACOTE_ENVIO/Oficina_Pesca_Instalador.exe')
pacote_zip = Path('PACOTE_ENVIO/Oficina_Pesca_Portatil.zip')

print(f'\nEXE: {dist_exe.exists()} - {dist_exe.stat().st_size / 1024 / 1024:.1f} MB' if dist_exe.exists() else '\nEXE: NOT FOUND')
print(f'INSTALADOR: {pacote_inst.exists()} - {pacote_inst.stat().st_size / 1024 / 1024:.1f} MB' if pacote_inst.exists() else '\nINSTALADOR: NOT FOUND')
print(f'ZIP: {pacote_zip.exists()} - {pacote_zip.stat().st_size / 1024 / 1024:.1f} MB' if pacote_zip.exists() else '\nZIP: NOT FOUND')
