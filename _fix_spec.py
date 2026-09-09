import os
spec = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\Oficina_Pesca.spec'
s = open(spec, encoding='utf-8').read()
s = s.replace("'ssl', 'certifi']", "'ssl', 'certifi', 'psutil', 'pyperclip']")
open(spec, 'w', encoding='utf-8').write(s)
print('OK: psutil e pyperclip adicionados ao spec')
