import subprocess, os, time
LOG = r\x27F:\x5cPROGRAMA\x5cOFICINA DE PESCA\x5cOFICINA_PESCA_ORIGINAL\x5cbuild_v1064.log\x27
BASE = r\x27F:\x5cPROGRAMA\x5cOFICINA DE PESCA\x5cOFICINA_PESCA_ORIGINAL\x27
PY = os.path.join(BASE, \x27.venv\x27, \x27Scripts\x27, \x27python.exe\x27)
SPEC = os.path.join(BASE, \x27Oficina_Pesca.spec\x27)
os.chdir(BASE)
print(\x27START:\x27, time.strftime(\x27%H:%M:%S\x27))
f = open(LOG, \x27w\x27)
cmd = [PY, \x27-u\x27, \x27-m\x27, \x27PyInstaller\x27, SPEC, \x27--noconfirm\x27]
print(\x27CMD:\x27, cmd)
p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
last_sz = 0
while True:
    line = p.stdout.readline()
    if line:
        decoded = line.decode(\x27utf-8\x27, errors=\x27replace\x27)
        f.write(decoded)
        f.flush()
        print(decoded.rstrip())
    ret = p.poll()
    time.sleep(5)
    sz = os.path.getsize(LOG)
    print(f\x27  [monitor] ret={ret} log={sz}b (delta={sz-last_sz})\x27)
    last_sz = sz
    if ret is not None:
        print(f\x27EXIT: {ret}\x27)
        break
f.close()
print(\x27DONE\x27)
