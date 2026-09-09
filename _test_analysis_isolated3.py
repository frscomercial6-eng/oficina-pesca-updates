import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_test_a3_log.txt')
log = open(LOG, 'w')

from PyInstaller.isolated import Python
from PyInstaller.building.build_main import Analysis

BASE = os.path.dirname(os.path.abspath(__file__))

def run_analysis():
    """Run inside isolated subprocess."""
    import os, sys, time
    from PyInstaller.building.build_main import Analysis
    
    BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
    
    # Check Python version
    print(f"Analysis Python: {sys.executable}")
    print(f"Python version: {sys.version_info}")
    
    # List some modules
    try:
        import firebase_admin
        print(f"firebase_admin: {firebase_admin.__version__}")
    except ImportError as e:
        print(f"firebase_admin import error: {e}")
    
    print("Starting Analysis...")
    t0 = time.time()
    
    a = Analysis(
        [os.path.join(BASE, 'login.py')],
        pathex=[BASE],
        binaries=[],
        datas=[],
        hiddenimports=['firebase_admin', 'firebase_admin.credentials'],
        excludes=['.backup_i18n', 'api', 'android_apk', 'infra', 'static', 'templates', 'tests', 'tools'],
        hookspath=[],
        hooksconfig={},
        runtime_hooks=[],
        noarchive=False,
    )
    
    t1 = time.time()
    return f"Analysis complete in {t1-t0:.1f}s: {len(a.scripts)} scripts"

try:
    with Python() as python:
        print("  Isolated Python started")
        result = python.call(run_analysis)
        print(f"  Result: {result}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

log.close()
print("\nDone")
