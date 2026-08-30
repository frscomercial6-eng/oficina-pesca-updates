# -*- coding: utf-8 -*-
"""Verifica chaves de i18n usadas no codigo em falta no pt_BR.json.

Usa regex precisa para capturar apenas chamadas reais de t() e get_text(),
excluindo variaveis, loops e strings literais de log.
"""
import re, json, glob

# Captura t("chave") ou t('chave') apenas como chamada de funcao (t isolado)
# e get_text("chave"). Exclui matches dentro de comentarios e onde o "t"
# faz parte de palavra maior (ex: item, start, get_text ja tratado).
PATTERNS = [
    re.compile(r"""(?<![A-Za-z0-9_])t\(['"]([^'"]+)['"]\)"""),           # t("chave") isolado
    re.compile(r"""get_text\(['"]([^'"]+)['"]\)"""),                      # get_text("chave")
]

# Prefixos/padroes que claramente nao sao chaves de i18n
IGNORE_PREFIXES = (
    "/api/", "/web/", "/static", "/app", "/version", "/sw.js", "/manifest",
    "OFP_", "GEMINI_", "GOOGLE_", "LOCALAPPDATA", "Content-", "File",
    "InternalName", "CompanyName", "FiscalSale", "HttpClient",
    "⚠️", "✅", "❌", "📦", "📎", "📝", "🚀", "🛠️", "🤖", "🧰", "🧼", "🔎", "🔖",
)

used_keys = set()
for f in sorted(glob.glob("*.py")):
    with open(f, encoding="utf-8") as fh:
        for line in fh:
            # Pula linhas de log/comentario
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("print(") or stripped.startswith("logging"):
                continue
            for pat in PATTERNS:
                for m in pat.finditer(line):
                    key = m.group(1).strip()
                    if not key:
                        continue
                    if any(key.startswith(p) or key == p.rstrip() for p in IGNORE_PREFIXES):
                        continue
                    # Exclui strings que parecem paths, comandos, logs
                    if "/" in key and not key.replace("/", "").replace("_", "").isalnum():
                        continue
                    if key.isupper() and len(key) > 3 and " " in key:
                        continue
                    used_keys.add(key)

with open("locales/pt_BR.json", encoding="utf-8") as fh:
    pt_data = json.load(fh)
    pt_keys = set(pt_data.keys())
with open("locales/en_US.json", encoding="utf-8") as fh:
    en_data = json.load(fh)
    en_keys = set(en_data.keys())

missing = sorted(used_keys - pt_keys)
print(f"Chaves USADAS no codigo: {len(used_keys)}")
print(f"Chaves em pt_BR.json: {len(pt_keys)}")
print(f"Chaves FALTANDO em pt_BR.json: {len(missing)}")
print("--- FALTANDO (chave  [en_US]) ---")
for k in missing:
    in_en = "YES" if k in en_keys else "NO"
    en_txt = en_data.get(k, "") if in_en == "YES" else ""
    print(f"  {k} [{in_en}] {en_txt}")