import os, time
f='F:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL/_build_611.log'
print('SIZE:', os.path.getsize(f))
lines=open(f).readlines()
print('LINES:', len(lines))
print('LAST:', lines[-1].strip() if lines else 'EMPTY')
if len(lines) > 5:
    print('PREVIOUS 4:')
    for l in lines[-5:-1]:
        print(' ', l.strip())
