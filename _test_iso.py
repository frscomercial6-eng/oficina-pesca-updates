# -*- coding: utf-8 -*-
"""Test isolated subprocess for cryptography hook"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyInstaller.isolated import decorate

@decorate
def check_crypto_openssl():
    from cryptography.hazmat.backends.openssl.backend import backend
    ver = backend.openssl_version_number()
    print(f"OPENSSL_VER: {ver}")
    return ver

print("Testing isolated cryptography subprocess...")
sys.stdout.flush()
sys.stderr.flush()

try:
    result = check_crypto_openssl()
    print(f"SUCCESS: {result}")
except Exception as e:
    print(f"FAILED: {e}")

print("DONE")
sys.stdout.flush()
