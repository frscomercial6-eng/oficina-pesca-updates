# -*- coding: utf-8 -*-
"""Substitui strings literais hardcoded (text=... e placeholder_text=...)
por chamadas t('chave') usando o mapeamento. Versao apenas substituicao."""
import re
import json
import os

MAPPING_PATH = "tests/i18n_mapping.json"
FILES = ["gestao_os.py", "tela_planos.py", "tela_os_teste.py"]

with open(MAPPING_PATH, encoding="utf-8") as fh:
    mapping = json.load(fh)

PATTERN = re.compile(r'(text|placeholder_text)\s*=\s*(["\'])([^"\']*)\2')


def substituir_arquivo(filepath):
    with open(filepath, encoding="utf-8") as fh:
        lines = fh.readlines()

    new_lines = []
    substituted = False
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("#"):
            new_lines.append(line)
            continue

        def replace_fn(match):
            nonlocal substituted
            prefix = match.group(1)
            quote = match.group(2)
            txt = match.group(3).strip()
            if txt in mapping:
                key = mapping[txt]
                substituted = True
                return f'{prefix}=t({quote}{key}{quote})'
            return match.group(0)

        new_line = PATTERN.sub(replace_fn, line)
        new_lines.append(new_line)

    if substituted:
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.writelines(new_lines)
        return True
    return False


total = 0
for f in FILES:
    if os.path.exists(f):
        if substituir_arquivo(f):
            total += 1
            print(f"  {f}: substituido")
        else:
            print(f"  {f}: sem substituicoes")

print(f"\nTotal de arquivos modificados: {total}")