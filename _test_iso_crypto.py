import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")
print(f"Version: {sys.version_info}")

from PyInstaller.isolated import Python

print("Testing isolated subprocess with cryptography...")

try:
    with Python() as python:
        print("  Isolated Python started OK")
        result = python.call(lambda: 2+2)
        print(f"  2+2 = {result}")
        
        # Test importing cryptography
        try:
            result2 = python.call(lambda: __import__('cryptography').__version__)
            print(f"  cryptography version = {result2}")
        except Exception as e:
            print(f"  cryptography import error: {type(e).__name__}: {e}")
        
        # Test cryptography's Fernet
        try:
            test_code = '''
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
print("cryptography OK")
'''
            result3 = python.call(lambda: __import__('types').SimpleNamespace())
            print(f"  cryptography test: {result3}")
        except Exception as e:
            print(f"  cryptography test error: {type(e).__name__}: {e}")

except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nDone")
