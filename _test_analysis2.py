import sys, os, time

BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
LOG = os.path.join(BASE, '_analysis_out2.txt')

sys.path.insert(0, os.path.join(BASE, '.venv_build', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")

# Import Analysis in a way that avoids multiprocessing issues
# Patch multiprocessing BEFORE importing PyInstaller
import multiprocessing
import multiprocessing.spawn

# Save original spawn
_orig_spawn = multiprocessing.spawn.spawn

# Patch to avoid Analysis subprocess issues
def _safe_spawn(obj):
    print(f"[SPAWN] {obj}")
    return _orig_spawn(obj)

multiprocessing.spawn.spawn = _safe_spawn
multiprocessing.set_start_method = lambda *a, **k: None

# Now import and run Analysis
from PyInstaller.building.build_main import Analysis

log_file = open(LOG, 'w', encoding='utf-8')

t0 = time.time()
try:
    print("Starting Analysis...")
    a = Analysis(
        [os.path.join(BASE, 'login.py')],
        pathex=[BASE],
        binaries=[],
        datas=[],
        hiddenimports=['firebase_admin', 'firebase_admin.credentials'],
        excludes=['.backup_i18n', 'api', 'android_apk', 'infra', 'static', 'templates', 'tests', 'tools',
                  'cryptography', 'googleapiclient', 'google_api_python_client',
                  'oauth2client', 'google_auth_oauthlib', 'google_auth_httplib2', 'httplib2'],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        noarchive=False,
    )
    t1 = time.time()
    msg = f"SUCCESS in {t1-t0:.1f}s! Scripts: {len(a.scripts)}"
    print(msg)
    log_file.write(msg + '\n')
except Exception as e:
    t1 = time.time()
    msg = f"FAILED after {t1-t0:.1f}s: {type(e).__name__}: {e}"
    print(msg)
    log_file.write(msg + '\n')
    import traceback
    traceback.print_exc()
    traceback.print_exc(file=log_file)
finally:
    log_file.close()
