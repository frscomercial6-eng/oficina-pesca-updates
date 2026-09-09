import subprocess, os, time

log = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\build_v1064_log.txt'
py = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'
cwd = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
spec = os.path.join(cwd, 'Oficina_Pesca.spec')

print('=== BUILD v1.0.64 (spec file, no --clean) ===')
print('Started:', time.strftime('%H:%M:%S'), flush=True)

args = [py, '-m', 'PyInstaller', spec, '--noconfirm']

r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=cwd, timeout=7200)

with open(log, 'w', encoding='utf-8', errors='replace') as f:
    f.write(r.stdout)
    f.write('\n=== STDERR ===\n')
    f.write(r.stderr)

print('EXIT:', r.returncode, flush=True)
print('Done:', time.strftime('%H:%M:%S'), flush=True)
