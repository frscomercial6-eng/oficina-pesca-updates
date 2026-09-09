import subprocess, time, os

log = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\build_v1064.log'
base = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'

while True:
    r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq python*'], capture_output=True, text=True)
    python_running = 'python.exe' in r.stdout
    if os.path.exists(log):
        lines = open(log, encoding='utf-8', errors='replace').readlines()
        last = lines[-1].strip() if lines else 'EMPTY'
    else:
        lines = []; last = 'NO_LOG'
    dist_exe = os.path.join(base, 'dist', 'Oficina_Pesca', 'Oficina_Pesca.exe')
    dist_exists = os.path.exists(dist_exe)
    print(f'RUNNING={python_running} LINES={len(lines)} LAST={last[:80]} DIST={dist_exists}')
    if not python_running:
        print('DONE')
        break
    time.sleep(30)