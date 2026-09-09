import os

BASE = 'F:/PROGRAMA/OFICINA DE PESCA/OFICINA_PESCA_ORIGINAL'
BUILD = os.path.join(BASE, 'build', 'Oficina_Pesca')
TOC = os.path.join(BUILD, 'Analysis-00.toc')

print(f"BASE: {BASE}")
print(f"BUILD: {BUILD}")
print(f"EXISTS: {os.path.exists(BUILD)}")

if os.path.exists(BUILD):
    items = os.listdir(BUILD)
    print(f"ITEMS: {len(items)}")
    for item in items[:30]:
        path = os.path.join(BUILD, item)
        if os.path.isdir(path):
            sub = os.listdir(path)[:3]
            print(f"  [DIR] {item}/ -> {sub}")
        else:
            size = os.path.getsize(path)
            print(f"  {item}: {size:,} bytes")
else:
    print("BUILD DIR DOES NOT EXIST")

print(f"\nTOC_EXISTS: {os.path.exists(TOC)}")
if os.path.exists(TOC):
    print(f"TOC_SIZE: {os.path.getsize(TOC):,} bytes")
