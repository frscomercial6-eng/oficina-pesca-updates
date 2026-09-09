import os, datetime
b = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
pkg = os.path.join(b, 'PACOTE_ENVIO', 'Oficina_Pesca_Instalador.exe')

files = [
    ('mestre_build.py', b),
    ('menu.py', b),
    ('tela_os.py', b),
    ('Oficina_Pesca_Instalador.exe', os.path.join(b, 'PACOTE_ENVIO')),
]

print("=== TIMESTAMPS ===")
for fname, dirpath in files:
    fp = os.path.join(dirpath, fname)
    if os.path.exists(fp):
        ts = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        size_mb = os.path.getsize(fp) / 1e6
        print(f"{fname}: {ts.strftime('%Y-%m-%d %H:%M')}  {size_mb:.1f} MB")
    else:
        print(f"{fname}: NOT FOUND")

print()
print("=== PACOTE_ENVIO CONTENTS ===")
pkg_dir = os.path.join(b, 'PACOTE_ENVIO')
if os.path.isdir(pkg_dir):
    for f in sorted(os.listdir(pkg_dir)):
        fp = os.path.join(pkg_dir, f)
        if os.path.isfile(fp):
            size_mb = os.path.getsize(fp) / 1e6
            ts = datetime.datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M')
            print(f"  {f}: {ts}  {size_mb:.1f} MB")
        else:
            print(f"  {f}/: (dir)")
