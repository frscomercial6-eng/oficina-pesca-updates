import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")

from PyInstaller.isolated import Python

print("Testing isolated with firebase_admin.auth...")

def test_auth():
    import time
    print("Starting firebase_admin.auth import...")
    t0 = time.time()
    import firebase_admin.auth
    t1 = time.time()
    print(f"firebase_admin.auth imported in {t1-t0:.1f}s")
    return f"OK in {t1-t0:.1f}s"

try:
    with Python() as python:
        print("  Isolated Python started")
        result = python.call(test_auth)
        print(f"  Result: {result}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nDone")
