import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv_build', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")

from PyInstaller.isolated import Python

# Test basic isolated subprocess
print("Testing isolated subprocess...")
try:
    with Python() as python:
        print("  Isolated Python started OK")
        result = python.call(lambda: 2+2)
        print(f"  2+2 = {result}")
        result2 = python.call(lambda: __import__('os').getpid())
        print(f"  os.getpid() = {result2}")
        result3 = python.call(lambda: __import__('firebase_admin'))
        print(f"  firebase_admin = {result3}")
except Exception as e:
    print(f"  ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nDone")
