import subprocess, os, sys, time
BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
py = os.path.join(BASE, r'.venv\Scripts\python.exe')
LOG = os.path.join(BASE, ruild_spec_test.txt')
proc = subprocess.Popen(
    [py, '-m', 'PyInstaller', 'Oficina_Pesca.spec', '--noconfirm'],
    cwd=BASE,
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    env=os.environ
)
while True:
    line = proc.stdout.readline()
    if not line and proc.poll() is not None:
        break
    if line:
        print(line.decode('utf-8', errors='replace'), end='')
        open(LOG,'ab').write(line)
open(LOG,'ab').write(f'EXIT: {proc.returncode}
'.encode())
print(f'EXIT: {proc.returncode}')
