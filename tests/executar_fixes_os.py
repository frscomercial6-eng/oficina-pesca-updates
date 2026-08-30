# -*- coding: utf-8 -*-
"""Fixes O.S. (idempotente): #4 link externo, #1 validacao, #3 verificacao, #2 dump."""
import os, re, shutil, sys, py_compile

B = r'f:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
BP = r'f:\PROGRAMA\OFICINA DE PESCA\build_protegido'
R = []

def log(m):
    R.append(str(m))

CORPO = [
    '"""Abre a pagina oficial de planos no navegador padrao."""',
    'import webbrowser',
    '',
    'url = "https://www.frssolutions.com.br/planos"',
    'webbrowser.open(url)',
]

def corpo_funcao(caminho, nome):
    linhas = open(caminho, encoding='utf-8').readlines()
    for i, l in enumerate(linhas):
        m = re.match(r'^(\s*)def ' + nome + r'\s*\(', l)
        if m:
            fim = len(linhas)
            for j in range(i + 1, len(linhas)):
                s = linhas[j]
                if s.strip() and (len(s) - len(s.lstrip())) <= len(m.group(1)):
                    fim = j
                    break
            return linhas, i, fim, m.group(1)
    return linhas, -1, -1, ''

def aplicar(caminho, nome):
    linhas, ini, fim, ind = corpo_funcao(caminho, nome)
    if ini < 0:
        log('[F4] NAO ENCONTRADO: %s em %s' % (nome, caminho))
        return
    atual = ''.join(linhas[ini:fim])
    if 'frssolutions.com.br/planos' in atual:
        log('[F4] ja aplicado: %s' % caminho)
        return
    shutil.copyfile(caminho, caminho + '.bak_fix4')
    novo = [(ind + '    ' + c).rstrip() + '\n' for c in CORPO]
    linhas[ini + 1:fim] = novo
    open(caminho, 'w', encoding='utf-8', newline='').writelines(linhas)
    log('[F4] OK corpo %s -> link externo (%s) [%d -> %d linhas]' % (
        nome, os.path.basename(caminho), fim - ini, len(novo) + 1))

def limpar_janela_vendas(caminho):
    src = open(caminho, encoding='utf-8').read()
    usos = len(re.findall(r'janela_vendas\s*\(', src))
    linhas, ini, fim, ind = corpo_funcao(caminho, 'janela_vendas')
    if usos <= 1 and ini >= 0:
        del linhas[ini:fim]
        open(caminho, 'w', encoding='utf-8', newline='').writelines(linhas)
        log('[F4] janela_vendas removida (uso unico) em %s' % os.path.basename(caminho))
    else:
        log('[F4] janela_vendas mantida (%d usos) em %s' % (usos, os.path.basename(caminho)))

# ---- FIX 4: botao de licenca abre o link externo direto
for p in (os.path.join(B, 'login.py'), os.path.join(BP, 'login.py')):
    aplicar(p, 'abrir_janela_planos')
for p in (os.path.join(B, 'login.py'), os.path.join(BP, 'login.py')):
    limpar_janela_vendas(p)

# ---- FIX 1: validacao estatica + runtime
sys.path.insert(0, B)
try:
    from core.gestao_os_repository import listar_orcamentos_para_gestao as fn1
    rows = fn1()
    log('[F1] RUNTIME repository: %d linhas; largura=%s' % (
        len(rows), (len(rows[0]) if rows else 'sem dados')))
except Exception as e:
    log('[F1] RUNTIME repository ERRO: %r' % e)
try:
    import core.gestao_os_service as svc
    nome_svc = next(n for n in dir(svc) if n.lower().startswith('listar'))
    rows2 = getattr(svc, nome_svc)()
    log('[F1] RUNTIME service %s: largura=%s' % (
        nome_svc, (len(rows2[0]) if rows2 else 'sem dados')))
except Exception as e:
    log('[F1] RUNTIME service ERRO: %r' % e)

g = open(os.path.join(B, 'gestao_os.py'), encoding='utf-8').read().splitlines()
for i, l in enumerate(g):
    if 'dados_adicionais' in l and '=' in l and l.count(',') >= 10:
        log('[F1] UI unpack linha %d: %d nomes' % (i + 1, l.count(',') + 1))
        break

# ---- FIX 3: verificacao do salvamento
t = open(os.path.join(B, 'tela_os.py'), encoding='utf-8').read()
log('[F3] INSERT INTO orcamentos_aguardo presente: %s' % ('INSERT INTO orcamentos_aguardo' in t))
log('[F3] status_entrega presente: %s' % ('status_entrega' in t))
log('[F3] carregar_proximo_numero: %d ocorrencias' % t.count('carregar_proximo_numero'))

# ---- FIX 2: dumps persistidos (sobrevivem a compactacao)
menu = open(os.path.join(B, 'menu.py'), encoding='utf-8').read().splitlines()
gs = open(os.path.join(B, 'gestao_os.py'), encoding='utf-8').read().splitlines()
to = open(os.path.join(B, 'tela_os.py'), encoding='utf-8').read().splitlines()
rp = open(os.path.join(B, 'core', 'gestao_os_repository.py'), encoding='utf-8').readlines()
dump = open(os.path.join(B, 'tests', '_dump_painel2.txt'), 'w', encoding='utf-8')
for nome, arr, janelas in (
    ('menu', menu, [(2770, 2812), (3021, 3110), (3260, 3480)]),
    ('gestao_os', gs, [(280, 360)]),
    ('tela_os', to, [(740, 880), (3883, 3995)]),
    ('repository', rp, [(1, 60)]),
):
    for a, b in janelas:
        dump.write('===== %s.py %d-%d =====\n' % (nome, a, b))
        for i in range(a - 1, min(b, len(arr))):
            dump.write('%d\t%s\n' % (i + 1, arr[i].rstrip('\n')))
dump.close()

# ---- compilacao de tudo
for rel in ('gestao_os.py', 'menu.py', 'tela_os.py', 'login.py',
            'core/gestao_os_repository.py', 'core/gestao_os_service.py'):
    py_compile.compile(os.path.join(B, rel), doraise=True)
py_compile.compile(os.path.join(BP, 'login.py'), doraise=True)
log('[OK] compilacao: fonte completo + build_protegido/login.py')

open(os.path.join(B, 'tests', '_relatorio_os_fixes.txt'), 'w', encoding='utf-8').write('\n'.join(R))
print('\n'.join(R))
