import subprocess, os
log = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\b_mini.txt'
py = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'
cwd = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
args = [py, '-m', 'PyInstaller', '--noconfirm', '--name', 'MINI', 'login.py']
cmd_str = ' '.join(args)
print('Running: ' + cmd_str, flush=True)
r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=cwd, timeout=300)
with open(log, 'w', encoding='utf-8', errors='replace') as f:
    f.write(r.stdout)
    f.write('\n=== STDERR ===\n')
    f.write(r.stderr)
print('EXIT: ' + str(r.returncode), flush=True)
print('Done', flush=True)

import subprocess, os

log = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\b_mini.txt'
py = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'
cwd = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'

args = [py, '-m', 'PyInstaller', '--noconfirm', '--name', 'MINI', 'login.py']

print(f'Running: {\" \".join(args)}', flush=True)
r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=cwd, timeout=300)

with open(log, 'w', encoding='utf-8', errors='replace') as f:
    f.write(r.stdout)
    f.write('\n=== STDERR ===\n')
    f.write(r.stderr)

print(f'EXIT: {r.returncode}', flush=True)
print(f'Log written to {log}', flush=True)
