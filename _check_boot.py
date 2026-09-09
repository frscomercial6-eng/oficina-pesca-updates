import sys, os
sys.path.insert(0, r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller')

boot_base = os.path.join(os.path.dirname(__import__('PyInstaller').__file__), 'bootloader')
print(f"Boot base: {boot_base}")
print(f"Exists: {os.path.exists(boot_base)}")

if os.path.exists(boot_base):
    dirs = os.listdir(boot_base)
    print(f"Subdirs: {dirs}")
    
    # Check Windows-64bit-intel
    boot_dir = os.path.join(boot_base, 'Windows-64bit-intel')
    if os.path.exists(boot_dir):
        files = os.listdir(boot_dir)
        print(f"\nWindows-64bit-intel files: {files}")
        for f in files:
            fpath = os.path.join(boot_dir, f)
            if not os.path.isdir(fpath):
                print(f"  {f}: {os.path.getsize(fpath):,} bytes")

# Check what PyInstaller expects
from PyInstaller.building.build_main import EXE
print(f"\nChecking EXE import: OK")

# Check bootloader module
from PyInstaller import bootloader
print(f"Bootloader module: {bootloader}")

# Check what OS name PyInstaller detects
import platform
print(f"\nPlatform: {platform.system()}")
print(f"Machine: {platform.machine()}")
print(f"Architecture: {platform.architecture()}")
