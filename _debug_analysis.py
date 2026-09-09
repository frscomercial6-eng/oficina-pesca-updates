import os, subprocess, sys

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
PYI = os.path.join(BASE, '.venv_build', 'Scripts', 'python.exe')
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')
LOG = os.path.join(BASE, 'build_debug2.log')

os.chdir(BASE)

print(f"Python: {sys.executable}")
print(f"PyInstaller: ", end='')
sys.stdout.flush()
subprocess.run([PYI, '-m', 'PyInstaller', '--version'])

print(f"\nTesting Analysis with debug output...")
print(f"Timeout: 30 seconds")

r = subprocess.run(
    [PYI, '-m', 'PyInstaller', SPEC, '--noconfirm', '-v'],
    capture_output=True,
    text=True,
    timeout=30,
    env=dict(os.environ, PYINSTALLER_DEBUG='1'),
)

with open(LOG, 'w') as f:
    f.write(f"STDOUT ({len(r.stdout)} chars):\n")
    f.write(r.stdout)
    f.write(f"\n\nSTDERR ({len(r.stderr)} chars):\n")
    f.write(r.stderr)
    f.write(f"\n\nRETURNCODE: {r.returncode}")

print(f"Done. {len(r.stdout)} chars stdout, {len(r.stderr)} chars stderr.")
print(f"Return code: {r.returncode}")

lines = r.stdout.split('\n')
print(f"\nLast 10 lines of stdout:")
for line in lines[-10:]:
    print(f"  {line}")

if r.stderr:
    print(f"\nLast 5 lines of stderr:")
    err_lines = r.stderr.split('\n')
    for line in err_lines[-5:]:
        print(f"  {line}")
