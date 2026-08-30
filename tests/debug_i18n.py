# -*- coding: utf-8 -*-
"""Debug: verifica strings hardcoded do pdv.py em falta no mapping."""
import re, json

with open("tests/i18n_mapping.json", encoding="utf-8") as f:
    m = json.load(f)

with open("pdv.py", encoding="utf-8") as f:
    content = f.read()

matches = re.findall(r'text\s*=\s*["\']([^"\']+)["\']', content)
for txt in sorted(set(matches)):
    in_map = txt in m
    if not in_map and len(txt.strip()) > 2 and not txt.startswith("#"):
        print(f"  pdv.py text: \"{txt}\" -> no mapping")

print(f"\nTotal chaves no mapping: {len(m)}")