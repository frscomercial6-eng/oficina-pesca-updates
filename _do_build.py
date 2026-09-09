import subprocess, os, sys, time

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
PY = os.path.join(BASE, '.venv', 'Scripts', 'python.exe')
PYI = os.path.join(BASE, '.venv', 'Scripts', 'Scripts', 'pyinstaller.exe')

log = os.path.join(BASE, 'build_v1064.log')
out_file = open(log, 'w', encoding='utf-8', buffering=1)

args = [
    PY,
    'mestre_build.py',
    '--no-bump', '--nome', 'Oficina_Pesca', '--auto', '--no-git'
]

out_file.write('BUILD STARTED at ' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n')
out_file.write(' '.join(args) + '\n')
out_file.flush()

env = os.environ.copy()
env['PYTHONPATH'] = BASE

proc = subprocess.Popen(
    [sys.executable] + args,
    cwd=BASE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=env,
    bufsize=1,
    universal_newlines=True,
)
for line in proc.stdout:
    out_file.write(line)
    out_file.flush()
proc.wait()
rc = proc.returncode
out_file.write('\nEXITCODE=' + str(rc) + '\n')
out_file.write('DONE at ' + time.strftime('%Y-%m-%d %H:%M:%S') + '\n')
out_file.close()
print('BUILD FINISHED, exitcode=' + str(rc))
sys.exit(rc)
