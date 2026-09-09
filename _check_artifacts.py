import os, datetime
base = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\PACOTE_ENVIO'
if os.path.exists(base):
    for n in sorted(os.listdir(base)):
        p = os.path.join(base, n)
        if os.path.isfile(p):
            mb = os.path.getsize(p) // 1024 // 1024
            ts = datetime.datetime.fromtimestamp(os.path.getmtime(p)).strftime('%Y-%m-%d %H:%M')
            print(f'{mb:>4}MB  {ts}  {n}')
else:
    print('PACOTE_ENVIO not found')
print()
dist = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\dist'
if os.path.exists(dist):
    for n in sorted(os.listdir(dist)):
        p = os.path.join(dist, n)
        if os.path.isdir(p):
            exe = os.path.join(p, n + '.exe')
            if os.path.exists(exe):
                mb = os.path.getsize(exe) // 1024 // 1024
                ts = datetime.datetime.fromtimestamp(os.path.getmtime(exe)).strftime('%Y-%m-%d %H:%M')
                print(f'EXE:  {mb:>4}MB  {ts}  {exe}')
else:
    print('dist/ not found')
