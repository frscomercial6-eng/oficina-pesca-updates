# -*- coding: utf-8 -*-
"""Correção final dos 4 problemas: aplica fix #4, valida #1, gera dumps #2/#3.

Uso: python tests/correcao_final_os.py   (idempotente)
"""
import os
import py_compile
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BP = os.path.normpath(os.path.join(RAIZ, os.pardir, "build_protegido"))
URL = "https://www.frssolutions.com.br/planos"
PASTA_DUMP = os.path.join(RAIZ, "tests", "_dumps_correcao")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

NOVO_CORPO = (
    "{i}def abrir_janela_planos(*_args, **_kwargs):\n"
    '{i}    """Abre a página de planos no navegador padrão (sem tela interna)."""\n'
    "{i}    try:\n"
    "{i}        import webbrowser\n"
    '{i}        webbrowser.open("{u}")\n'
    "{i}    except Exception:\n"
    "{i}        pass\n"
    "\n"
)

PAD_DEF = re.compile(r"^([ \t]*)def\s+abrir_janela_planos\s*\([^)]*\)[^:\n]*:", re.M)


def _corpo(ind):
    return NOVO_CORPO.format(i=ind, u=URL)


def _fim_do_corpo(codigo, inicio_def):
    trecho = codigo[inicio_def:]
    linhas = trecho.splitlines(keepends=True)
    ind_len = len(trecho) - len(trecho.lstrip(" \t"))
    fim = len(linhas[0])
    for ln in linhas[1:]:
        s = ln.strip()
        i2 = len(ln) - len(ln.lstrip(" \t"))
        if s and i2 <= ind_len and (s.startswith(("def ", "class ", "@")) or s.startswith("#")):
            break
        fim += len(ln)
    return fim


def corrigir_login(caminho):
    with open(caminho, "r", encoding="utf-8") as arq:
        codigo = arq.read().replace("\r\n", "\n")
    spans = []
    for m in PAD_DEF.finditer(codigo):
        spans.append((m.start(), _fim_do_corpo(codigo, m.start()), m.group(1)))
    for _inicio, fim, _ind in reversed(spans):
        pass
    resultado = codigo
    for inicio, fim, ind in reversed(spans):
        resultado = resultado[:inicio] + _corpo(ind) + resultado[fim:]
    resultado = re.sub(r"\bjanela_vendas\s*\(", "abrir_janela_planos(", resultado)
    alterado = resultado != codigo
    if alterado:
        with open(caminho, "w", encoding="utf-8", newline="\n") as arq:
            arq.write(resultado)
    return len(spans), alterado


def aplicar_fix4():
    for caminho in (os.path.join(RAIZ, "login.py"), os.path.join(BP, "login.py")):
        if not os.path.isfile(caminho):
            print("FIX4 AUSENTE", caminho)
            continue
        n, mudou = corrigir_login(caminho)
        print("FIX4", os.path.basename(os.path.dirname(caminho)), "defs=%d alterado=%s" % (n, mudou))


def validar_listagem():
    cod = (
        "import sys\n"
        "sys.path.insert(0, r'%s')\n"
        "from core.gestao_os_repository import listar_orcamentos_para_gestao as f\n"
        "try:\n"
        "    linhas = f() or []\n"
        "    print('REPO cols=%%d rows=%%d' %% (len(linhas[0]) if linhas else 0, len(linhas)))\n"
        "    if linhas:\n"
        "        print('AMOSTRA', str(linhas[0])[:200])\n"
        "except TypeError as e:\n"
        "    print('REPO_ARGS', e)\n"
        "except Exception as e:\n"
        "    print('REPO_ERRO', repr(e))\n"
        "try:\n"
        "    import core.gestao_os_service as s\n"
        "    for n in [x for x in dir(s) if x.startswith('listar')]:\n"
        "        fn = getattr(s, n)\n"
        "        try:\n"
        "            d = fn()\n"
        "            print('SVC', n, len(d) if hasattr(d, '__len__') else d)\n"
        "            if isinstance(d, list) and d and isinstance(d[0], dict):\n"
        "                print('SVC_CHAVES', sorted(d[0].keys()))\n"
        "        except TypeError as e:\n"
        "            print('SVC_SKIP', n, e)\n"
        "        except Exception as e:\n"
        "            print('SVC_ERRO', n, repr(e))\n"
        "except Exception as e:\n"
        "    print('SVC_IMPORT_ERRO', repr(e))\n"
    ) % RAIZ
    r = subprocess.run(
        [sys.executable, "-c", cod], cwd=RAIZ, capture_output=True, text=True, timeout=240
    )
    saida = (r.stdout or "").strip()
    if r.stderr:
        saida += "\n[stderr] " + r.stderr.strip()[-400:]
    return saida or "(sem saida)"


# --- PARTE B ---
