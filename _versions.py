import subprocess
PYI = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'
for p in ['firebase_admin','reportlab','googleapiclient','cryptography','psutil']:
    r = subprocess.run([PYI, '-m', 'pip', 'show', p], capture_output=True, text=True)
    if r.returncode == 0:
        for line in r.stdout.split('\n')[:3]:
            if line.strip():
                print(f"{p}: {line}")
    else:
        print(f"{p}: NOT INSTALLED")
    print()
