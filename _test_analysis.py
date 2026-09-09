import sys, os, time

# Use the .venv_build Python which has PyInstaller installed
sys.path.insert(0, r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv_build\Lib\site-packages')

print(f"Python: {sys.executable}")
print(f"Python version: {sys.version}")

# Don't use multiprocessing in Analysis - set env var
os.environ['PYINSTALLER_NO_MP'] = '1'

# Patch multiprocessing to not use spawn
import multiprocessing.spawn
original_spawn = multiprocessing.spawn.spawn
def patched_spawn(obj):
    print(f"[MULTIPROC PATCH] spawn called for {obj}")
    return original_spawn(obj)
multiprocessing.spawn.spawn = patched_spawn

from PyInstaller.building.build_main import Analysis
import PyInstaller.log

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
LOG = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\_analysis_test.log'

print("Creating Analysis...")
print()

log_file = open(LOG, 'w', encoding='utf-8')
log_file.write(f"Analysis test started at {time.time()}\n")
log_file.flush()

try:
    t0 = time.time()
    a = Analysis(
        [os.path.join(BASE, 'login.py')],
        pathex=[BASE],
        binaries=[],
        datas=[],
        hiddenimports=[
            'firebase_admin',
            'firebase_admin.credentials',
        ],
        excludes=[
            '.backup_i18n', 'api', 'android_apk', 'infra', 'static',
            'templates', 'tests', 'tools',
            'cryptography', 'googleapiclient', 'google_api_python_client',
            'oauth2client', 'google_auth_oauthlib', 'google_auth_httplib2', 'httplib2',
        ],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        noarchive=False,
    )
    t1 = time.time()
    print(f"SUCCESS! Analysis completed in {t1-t0:.1f}s")
    print(f"Scripts: {len(a.scripts)}")
    log_file.write(f"SUCCESS in {t1-t0:.1f}s\n")
except Exception as e:
    t1 = time.time()
    print(f"FAILED after {t1-t0:.1f}s: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    log_file.write(f"FAILED: {type(e).__name__}: {e}\n")
    traceback.print_exc(file=log_file)
finally:
    log_file.close()
