import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '.venv', 'Lib', 'site-packages'))

print(f"Python: {sys.executable}")

from PyInstaller.isolated import Python

print("Testing isolated subprocess with .venv...")

try:
    with Python() as python:
        print("  Isolated Python started OK")
        result = python.call(lambda: 2+2)
        print(f"  2+2 = {result}")
        pid = python.call(lambda: __import__('os').getpid())
        print(f"  Child PID = {pid}")
        
        # Test importing firebase_admin
        try:
            result2 = python.call(lambda: __import__('firebase_admin').__version__)
            print(f"  firebase_admin version = {result2}")
        except Exception as e:
            print(f"  firebase_admin import error: {type(e).__name__}: {e}")
            
        # Test importing customtkinter
        try:
            result3 = python.call(lambda: __import__('customtkinter').__version__)
            print(f"  customtkinter version = {result3}")
        except Exception as e:
            print(f"  customtkinter import error: {type(e).__name__}: {e}")

except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\nDone")
