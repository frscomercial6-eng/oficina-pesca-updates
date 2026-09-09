import subprocess, sys, os, time
LOG = r'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL\\build_v1064.log'

BASE = r'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL'

PY = os.path.join(BASE, '.venv\\Scripts\\python.exe')

SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')

os.chdir(BASE)

print('STARTING BUILD AT:', time.strftime('%H:%M:%S'))

f = open(LOG, 'w')

cmd = [PY, '-m', 'PyInstaller', SPEC, '--noconfirm']

print('CMD:', ' '.join(cmd))

p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, text=True)

while True:

    ret = p.poll()

    time.sleep(10)

    sz = os.path.getsize(LOG)

    print(f'RUNNING: ret={ret} log={sz}b')

    if ret is not None:

        print(f'EXIT: {ret}')

        break
f.close()

print('DONE')
