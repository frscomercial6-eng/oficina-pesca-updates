# -*- coding: utf-8 -*-
path = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\Oficina_Pesca.spec'
with open(path, encoding='utf-8') as f:
    content = f.read()

original = content

# Fix 1: pyperclip -> remove
content = content.replace("'pyperclip'", "'PYPERCLIP_REMOVED'")

# Fix 2: upx=True -> upx=False
content = content.replace('upx=True', 'upx=False')

if content == original:
    print('NO CHANGES NEEDED')
else:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('SPEC CORRIGIDO')
    print('pyperclip: ' + ('REMOVIDO' if "'PYPERCLIP_REMOVED'" in content else 'NAO ENCONTRADO'))
    print('upx=False: ' + ('OK' if 'upx=False' in content else 'FALHOU'))
