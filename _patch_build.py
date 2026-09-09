from pathlib import Path

p = Path(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py')
s = p.read_text(encoding='utf-8')

OLD = '''PYINSTALLER_COLLECT_ALL = [
    "customtkinter",
    "fpdf",
    "googleapiclient",
    "google_auth_oauthlib",
    "google",
    "google_auth",
    "google_api_python_client",
    "reportlab",
]'''

NEW = '''PYINSTALLER_COLLECT_ALL = []  # collect-all removidos'''

if OLD not in s:
    print('ERRO: texto nao encontrado')
    raise SystemExit(1)

s = s.replace(OLD, NEW)
p.write_text(s, encoding='utf-8')
print('OK: PYINSTALLER_COLLECT_ALL esvaziado')
