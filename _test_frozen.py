import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")
print(f"sys.frozen: {getattr(sys, 'frozen', 'NOT SET')}")

from PyInstaller.isolated import Python
from PyInstaller.building.build_main import Analysis

BASE = os.path.dirname(os.path.abspath(__file__))

print("Testing Analysis with frozen=False...")

def run_analysis():
    """This runs inside the isolated subprocess."""
    import sys as _sys, os as _os, time as _time
    _sys.path.insert(0, _os.path.join(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL', '.venv', 'Lib', 'site-packages'))
    
    # Force frozen=False for testing
    _sys.frozen = False
    _sys._MEIPASS = None
    
    print(f"sys.frozen inside: {getattr(_sys, 'frozen', 'NOT SET')}")
    print(f"sys.argv: {_sys.argv[:3]}")
    
    # Import Analysis
    from PyInstaller.building.build_main import Analysis
    from PyInstaller import __main__ as _main
    from PyInstaller import configure
    from PyInstaller.config import CONF
    
    # Initialize CONF
    CONF['workpath'] = _os.path.join(r'C:\test_build2', 'build', 'Oficina_Pesca')
    CONF['specpath'] = r'C:\test_build2'
    CONF['specnm'] = 'Oficina_Pesca'
    _os.makedirs(CONF['workpath'], exist_ok=True)
    
    print(f"CONF initialized: workpath={CONF.get('workpath')}")
    
    BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
    
    t0 = _time.time()
    a = Analysis(
        [_os.path.join(BASE, 'login.py')],
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
    t1 = _time.time()
    return f"SUCCESS in {t1-t0:.1f}s: {len(a.scripts)} scripts"

try:
    with Python() as python:
        print("  Isolated Python started")
        result = python.call(run_analysis)
        print(f"  Result: {result}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nDone")
