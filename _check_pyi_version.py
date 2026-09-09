import sys, os

# Check the system Python version
system_py = r'C:\Users\User\AppData\Local\Programs\Python\Python311\python.exe'
print(f"System Python: {system_py}")
print(f"Exists: {os.path.exists(system_py)}")

if os.path.exists(system_py):
    import subprocess
    r = subprocess.run([system_py, '--version'], capture_output=True, text=True)
    print(f"Version: {r.stdout.strip()}")
    
    # Check the Python DLL
    dll = r'C:\Users\User\AppData\Local\Programs\Python\Python311\python311.dll'
    print(f"DLL: {dll}")
    print(f"DLL Exists: {os.path.exists(dll)}")
    if os.path.exists(dll):
        import stat
        size = os.path.getsize(dll)
        print(f"DLL Size: {size:,} bytes ({size/1024/1024:.1f} MB)")
        
        # Check file info
        import subprocess
        r2 = subprocess.run(['powershell', '-Command', 
            f'Get-Item "{dll}" | Select-Object LastWriteTime, CreationTime'], 
            capture_output=True, text=True)
        print(f"DLL Info:\n{r2.stdout}")

# Check the venv Python
venv_py = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Scripts\python.exe'
print(f"\nVenv Python: {venv_py}")
print(f"Exists: {os.path.exists(venv_py)}")

if os.path.exists(venv_py):
    import subprocess
    r = subprocess.run([venv_py, '--version'], capture_output=True, text=True)
    print(f"Version: {r.stdout.strip()}")
    
    # Check Python DLL used
    print(f"\nPython DLL from sys:")
    r2 = subprocess.run([venv_py, '-c', 'import sys; print(sys.dllhandle, sys.executable)'], 
        capture_output=True, text=True)
    print(f"Handle and executable:\n{r2.stdout}")

# Check multiprocessing spawn
print(f"\nChecking multiprocessing.spawn in system Python:")
r3 = subprocess.run([system_py, '-c', 
    'import multiprocessing.spawn as m; print(dir(m))'], 
    capture_output=True, text=True)
print(f"multiprocessing.spawn attributes: {r3.stdout}")
