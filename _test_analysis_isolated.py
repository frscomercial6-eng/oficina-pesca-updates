import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")

from PyInstaller.isolated import Python
from PyInstaller.building.build_main import Analysis

BASE = os.path.dirname(os.path.abspath(__file__))

print("Testing Analysis via isolated subprocess...")

try:
    with Python() as python:
        print("  Isolated Python started OK")
        
        # Test importing PyInstaller's Analysis module
        result = python.call(lambda: __import__('PyInstaller.building.build_main').__version__)
        print(f"  PyInstaller version = {result}")
        
        # Test importing Analysis
        result2 = python.call(
            lambda: __import__('PyInstaller.building.build_main', fromlist=['Analysis']).Analysis,
        )
        print(f"  Analysis class: {result2}")
        
        # Now test running Analysis
        print("\n  Running Analysis (this might take a while)...")
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
        print(f"  Analysis SUCCESS! Scripts: {len(a.scripts)}")
        
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nDone")
