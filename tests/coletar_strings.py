# -*- coding: utf-8 -*-
"""Regenera o mapeamento de strings hardcoded -> chaves i18n e aplica
substituicao em texto= e placeholder_text= em todas as telas.

Estratégia:
1. Coleta TODAS as strings literais (text="...", placeholder_text="...")
   de todos os arquivos .py (exceto strings que ja usam t()).
2. Gera chaves unicas para textos nao existentes no pt_BR.json.
3. Adiciona ao pt_BR.json, en_US.json, es_UY.json.
4. Substitui text="STRING" -> text=t("CHAVE") no codigo.
5. Garante import de t em cada arquivo.
"""
import re
import json
import os

LOCALES_DIR = "locales"
MAPPING_PATH = "tests/i18n_mapping.json"
FILES = ["login.py", "menu.py", "pdv.py", "clientes.py",
         "tela_financeiro.py", "tela_os.py", "tela_os_teste.py",
         "gestao_os.py", "tela_planos.py"]

SKIP_FONTS = {"Arial", "Segoe UI", "bold", "normal", "TkFixedFont"}

# Carrega JSONs
jsons = {}
for lang in ("pt_BR", "en_US", "es_UY"):
    p = os.path.join(LOCALES_DIR, f"{lang}.json")
    with open(p, encoding="utf-8") as fh:
        jsons[lang] = json.load(fh)

# Coleta todas as strings hardcoded unicas
all_strings = {}  # texto -> (arquivo, linha)
PATTERN = re.compile(r'(text|placeholder_text)\s*=\s*["\']([^"\']+)["\']')

for f in FILES:
    if not os.path.exists(f):
        continue
    with open(f, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            # Pula linhas de comentario
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            for m in PATTERN.finditer(line):
                txt = m.group(2).strip()
                if not txt:
                    continue
                if txt in SKIP_FONTS:
                    continue
                if txt.startswith("#"):
                    continue
                if txt.startswith("{") and txt.endswith("}"):
                    continue
                # Pula strings que ja usam t()
                if f"t(" in line[m.start():m.end()]:
                    continue
                # Pula textos muito curtos ou codigo
                if len(txt) <= 1:
                    continue
                # Pula strings numericas/puro formato
                if re.match(r'^[\d/\.\-:, ]+$', txt):
                    continue
                # Pula se ja e uma chave existente no pt_BR
                if re.match(r'^[a-z_]+$', txt) and txt in jsons["pt_BR"]:
                    continue
                if txt not in all_strings:
                    all_strings[txt] = (f, i)

print(f"Strings hardcoded total: {len(all_strings)}")

# Gera chaves para textos nao no JSON
def make_key(text):
    k = "ui_" + re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:60]
    base = k
    n = 1
    while k in jsons["pt_BR"] or k in new_keys:
        k = f"{base}_{n}"
        n += 1
    return k

new_keys = {}
for txt, (f, ln) in all_strings.items():
    # Verifica se texto ja existe como valor em pt_BR
    existing_key = None
    for k, v in jsons["pt_BR"].items():
        if v == txt:
            existing_key = k
            break
    if existing_key:
        new_keys[txt] = existing_key
    else:
        key = make_key(txt)
        new_keys[txt] = key
        jsons["pt_BR"][key] = txt
        jsons["en_US"][key] = txt  # en_US mantem texto original
        jsons["es_UY"][key] = txt  # es_UY mantem texto original

# Salva JSONs ordenados
for lang in ("pt_BR", "en_US", "es_UY"):
    p = os.path.join(LOCALES_DIR, f"{lang}.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(jsons[lang], fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")

# Salva mapping texto -> chave
with open(MAPPING_PATH, "w", encoding="utf-8") as fh:
    json.dump(new_keys, fh, ensure_ascii=False, indent=2)

print(f"Chaves geradas/usadas: {len(new_keys)}")
print(f"Total pt_BR.json: {len(jsons['pt_BR'])}")
print(f"Novas chaves adicionadas: {len(jsons['pt_BR']) - 227}")