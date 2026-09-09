import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")

from PyInstaller.isolated import Python
from PyInstaller.building.build_main import Analysis

BASE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(BASE, '_analysis_isolated_out.txt')

print("Testing Analysis via isolated subprocess (no return)...")

def run_analysis():
    """This runs inside the isolated subprocess."""
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))
    
    from PyInstaller.building.build_main import Analysis
    BASE = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
    
    print("Analysis subprocess: starting...")
    
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
    
    print(f"Analysis complete: {len(a.scripts)} scripts")
    return "SUCCESS"

try:
    with Python() as python:
        print("  Isolated Python started OK")
        result = python.call(run_analysis)
        print(f"  Result: {result}")
        
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    # Check log file
    if os.path.exists(LOG):
        with open(LOG) as f:
            content = f.read()
        print(f"\nLog file ({len(content)} chars):")
        print(content[-2000:])

print("\nDone")
