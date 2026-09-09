# Correcao do _build_isolated.py
import os
s = open("_build_isolated.py", encoding="utf-8").read()
old = 'cmd += ["--add-data", f\'"{src};{dst}"\']'
new = 'cmd += ["--add-data", f"{src};{dst}"]'
if old in s:
    s = s.replace(old, new)
    open("_build_isolated.py", "w", encoding="utf-8").write(s)
    print("OK: linha corrigida")
else:
    print("NAO ENCONTRADO:", repr(old[:50]))
    print("PRESENTE:", repr(s[s.find("add-data"):s.find("add-data")+60]))
