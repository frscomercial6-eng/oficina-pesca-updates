import os

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
SPEC = os.path.join(BASE, 'Oficina_Pesca.spec')

with open(SPEC, encoding='utf-8') as f:
    content = f.read()

# Add excludes to Analysis to prevent scanning huge directories
# that are NOT part of the application runtime
old_line = "    excludes=[],"
new_line = """    excludes=[
        '.backup_i18n',
        'api',
        'android_apk',
        'infra',
        'static',
        'templates',
        'tests',
        'tools',
    ],"""

if "excludes=[" not in content or ".backup_i18n" not in content:
    content = content.replace(old_line, new_line)

with open(SPEC, 'w', encoding='utf-8') as f:
    f.write(content)

print("Spec atualizado com excludes.")
print("Verificando...")

# Verify
with open(SPEC, encoding='utf-8') as f:
    new_content = f.read()

import ast
try:
    ast.parse(new_content, filename=SPEC)
    print("Sintaxe OK")
except SyntaxError as e:
    print(f"ERRO de sintaxe: {e}")
    exit(1)

# Show excludes section
lines = new_content.split('\n')
for i, line in enumerate(lines):
    if 'excludes=' in line or '.backup_i18n' in line:
        for j in range(max(0,i-1), min(len(lines), i+10)):
            print(f"  {j+1}: {lines[j]}")
        break

print("\nArquivos que serao escaneados:")
import os
py_count = 0
for root, dirs, files in os.walk(BASE):
    # Skip excluded dirs
    skip = False
    for d in ['.backup_i18n', 'api', 'android_apk', 'infra', 'static', 'templates', 'tests', 'tools', '.git', '__pycache__', '.venv', 'venv', 'site-packages', 'dist', 'build', 'PACOTE_ENVIO', 'INSTALADOR_FINAL', 'Output']:
        if d in root:
            skip = True
            break
    if skip:
        continue
    for f in files:
        if f.endswith('.py'):
            py_count += 1

print(f"  {py_count} arquivos Python (vs 32.721 antes)")
