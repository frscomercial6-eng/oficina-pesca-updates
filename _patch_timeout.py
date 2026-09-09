import os, sys

# Patch the isolated module's timeout
pyi_dir = r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv\Lib\site-packages\PyInstaller'

parent_file = os.path.join(pyi_dir, 'isolated', '_parent.py')
with open(parent_file, 'r') as f:
    content = f.read()

print(f"File size: {len(content)}")
print(f"Has timeout=5: {'timeout=5' in content}")
print(f"Has timeout=15: {'timeout=15' in content}")

# Patch timeouts from 5 to 300 (5 minutes)
new_content = content.replace('timeout=5', 'timeout=300').replace('timeout=15', 'timeout=300')

if new_content != content:
    with open(parent_file, 'w') as f:
        f.write(new_content)
    print("PATCHED timeouts from 5s/15s to 300s!")
    print("Checking patch:")
    with open(parent_file, 'r') as f:
        patched = f.read()
    print(f"  timeout=5: {'timeout=5' in patched}")
    print(f"  timeout=300: {'timeout=300' in patched}")
else:
    print("No timeout found to patch!")
