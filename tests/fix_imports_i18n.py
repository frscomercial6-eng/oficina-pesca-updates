# -*- coding: utf-8 -*-
"""Corrige os 3 arquivos com import de t inserido incorretamente
dentro de blocos try/except. Remove a linha problemática e adiciona
o import no topo do arquivo."""
import re

ARQUIVOS = {
    "gestao_os.py": {
        "import_line": "from core.gestao_os_service import carregar_dados_orcamento, listar_orcamentos_gestao, mudar_status_orcamento\n",
        "new_import": "from core.gestao_os_service import carregar_dados_orcamento, listar_orcamentos_gestao, mudar_status_orcamento\nfrom core.i18n import t\n",
        "bad_line_pattern": r'^from core\.i18n import t\s*\n',
    },
    "tela_planos.py": {
        "import_line": None,
        "new_import": "from core.i18n import t\n",
        "bad_line_pattern": r'^from core\.i18n import t\s*\n',
    },
    "tela_os_teste.py": {
        "import_line": None,
        "new_import": "from core.i18n import t\n",
        "bad_line_pattern": r'^from core\.i18n import t\s*\n',
    },
}

for fname, cfg in ARQUIVOS.items():
    with open(fname, encoding="utf-8") as f:
        content = f.read()

    # Remove todas as ocorrencias do import problemático (fora do topo)
    # O import problemático esta sem indentacao
    bad_pattern = re.compile(cfg["bad_line_pattern"], re.MULTILINE)
    content = bad_pattern.sub("", content)

    # Verifica se ja tem import no topo
    if "from core.i18n import t" not in content:
        # Insere depois do bloco de imports iniciais
        lines = content.split("\n")
        insert_idx = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("import ") or s.startswith("from "):
                insert_idx = i + 1
        lines.insert(insert_idx, "from core.i18n import t")
        content = "\n".join(lines)

    with open(fname, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  {fname}: corrigido")