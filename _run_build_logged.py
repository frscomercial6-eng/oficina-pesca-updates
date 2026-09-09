import os, subprocess, time, shutil, sys

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
PYI = os.path.join(BASE, '.venv_build', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, '_build_venv_build.log')
OUT = os.path.join(BASE, '_build_venv_out.txt')
ERR = os.path.join(BASE, '_build_venv_err.txt')

os.chdir(BASE)

# Clean old build
shutil.rmtree('build', ignore_errors=True)
shutil.rmtree('dist', ignore_errors=True)

print(f'Starting build at {time.strftime("%H:%M:%S")}')
print(f'PyInstaller: {subprocess.run([PYI, "-m", "PyInstaller", "--version"], capture_output=True, text=True).stdout.strip()}')

start = time.time()

with open(OUT, 'w') as fout, open(ERR, 'w') as ferr:
    proc = subprocess.Popen(
        [PYI, '-m', 'PyInstaller', 'Oficina_Pesca.spec', '--noconfirm'],
        stdout=fout, stderr=ferr, text=True
    )
    print(f'PID: {proc.pid}')
    
    rc = proc.wait(timeout=3600)
    elapsed = int(time.time() - start)
    
print(f'\nEXIT: {rc}')
print(f'Duration: {elapsed}s')
print(f'Log size: {os.path.getsize(LOG)}')
print(f'Out size: {os.path.getsize(OUT)}')

# Read last lines of output
with open(OUT, 'r', errors='replace') as f:
    lines = f.readlines()
print(f'\nLines in output: {len(lines)}')
print('Last 30 lines:')
for l in lines[-30:]:
    print(l.rstrip())

# Check EXE
EXE = os.path.join(BASE, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
print(f'\nEXE exists: {os.path.exists(EXE)}')
if os.path.exists(EXE):
    print(f'EXE size: {os.path.getsize(EXE):,} bytes')
