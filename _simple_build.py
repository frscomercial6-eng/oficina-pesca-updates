import os, subprocess, time, shutil
BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
PYI = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
LOG = os.path.join(BASE, '_simple_build.log')
os.chdir(BASE)
shutil.rmtree('build', ignore_errors=True)
shutil.rmtree('dist', ignore_errors=True)
time.sleep(2)
r = subprocess.run([PYI, '-m', 'PyInstaller', '--version'], capture_output=True, text=True)
print('PyInstaller:', r.stdout.strip())
r = subprocess.run([PYI, '-m', 'PyInstaller', 'Oficina_Pesca.spec', '--noconfirm'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3600)
with open(LOG, 'w') as f: f.write(r.stdout)
print('EXIT:', r.returncode)
print('LOG lines:', len(r.stdout.splitlines()))
