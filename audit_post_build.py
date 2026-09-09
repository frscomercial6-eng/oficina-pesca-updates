import os, hashlib, json, subprocess

p = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'

print('=== AUDITORIA PÓS-BUILD ===')
print(f'Path: {p}')

# 1. dist exists
dist_dir = os.path.join(p, 'dist')
print(f'1. dist existe: {os.path.isdir(dist_dir)}')

# 2. Oficina_Pesca dir exists
of_dir = os.path.join(dist_dir, 'Oficina_Pesca')
print(f'2. dist\\Oficina_Pesca existe: {os.path.isdir(of_dir)}')

# 3. exe exists
exe_path = os.path.join(of_dir, 'Oficina_Pesca_FRS.exe')
exe_exists = os.path.isfile(exe_path)
print(f'3. Oficina_Pesca_FRS.exe existe: {exe_exists}')

# 4. version 1.0.63
ver_path = os.path.join(p, 'version.txt')
ver_content = open(ver_path).read().strip() if os.path.isfile(ver_path) else 'N/A'
print(f'4. Versão: {ver_content}')

# 5. estrutura do pacote
if os.path.isdir(of_dir):
    items = sorted(os.listdir(of_dir))
    print(f'5. Estrutura do pacote (primeiros 20 itens): {items[:20]}')

# 6. nenhum .env
env_files = []
if os.path.isdir(of_dir):
    for root, dirs, files in os.walk(of_dir):
        for f in files:
            if '.env' in f.lower():
                env_files.append(f)
print(f'6. Arquivos .env encontrados: {env_files if env_files else "Nenhum"}')

# 7. client_secret_desktop.json
cs_path = os.path.join(of_dir, 'client_secret_desktop.json')
print(f'7. client_secret_desktop.json existe: {os.path.isfile(cs_path)}')

# 8. instalador exclui *.pyd
pyd_count = 0
if os.path.isdir(of_dir):
    for root, dirs, files in os.walk(of_dir):
        for f in files:
            if f.endswith('.pyd'):
                pyd_count += 1
print(f'8. .pyd no dist (devem ser 0): {pyd_count}')

# 9. 52 .pyd da .venv
venv_path = r'F:\PROGRAMA\.venv'
venv_pyd_count = 0
if os.path.isdir(venv_path):
    for root, dirs, files in os.walk(venv_path):
        for f in files:
            if f.endswith('.pyd'):
                venv_pyd_count += 1
print(f'9. .pyd na .venv (esperado 52): {venv_pyd_count}')

# 10. SHA-256 do executável
if exe_exists:
    sha = hashlib.sha256()
    with open(exe_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha.update(chunk)
    print(f'10. SHA-256: {sha.hexdigest()}')
else:
    print('10. SHA-256: N/A (exe não encontrado)')

# 11. git status
try:
    result = subprocess.run(['git', 'status', '--short'], capture_output=True, text=True, cwd=p, timeout=10)
    git_lines = result.stdout.strip().split('\n') if result.stdout.strip() else []
    print(f'11. Git status: {len(git_lines)} arquivos modificados')
    for line in git_lines[:10]:
        print(f'    {line}')
except Exception as e:
    print(f'11. Git status: Erro - {e}')