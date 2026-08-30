# -*- coding: utf-8 -*-
"""Verifica quais arquivos importam t() de core.i18n."""
import re

FILES = ["login.py", "menu.py", "pdv.py", "clientes.py",
         "tela_financeiro.py", "tela_os.py", "tela_os_teste.py"]

for f in FILES:
    try:
        with open(f, encoding="utf-8") as fh:
            content = fh.read()
        has_import = bool(re.search(r'from\s+core\.i18n\s+import.*\bt\b', content))
        uses_t = len(re.findall(r"""(?<![A-Za-z0-9_])t\(['"]""", content))
        print(f"  {f}: import t={has_import}, chamadas t()={uses_t}")
    except FileNotFoundError:
        print(f"  {f}: ARQUIVO NAO ENCONTRADO")