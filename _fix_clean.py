# -*- coding: utf-8 -*-
path=r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py'
with open(path, encoding='utf-8') as f:
    lines = f.readlines()
for i, l in enumerate(lines):
    if l.strip() == '"--clean",':
        print(f'Found --clean at line {i+1}')
        lines[i] = ''
        break
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Done. --clean removed from mestre_build.py')
