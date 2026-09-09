# -*- coding: utf-8 -*-
import os, sys, shutil, subprocess

DIV = '=' * 50
VERSAO = '1.0.64'
APP_NAME = 'Oficina_Pesca'
ENTRY_SCRIPT = 'login.py'
INSTALLER_SCRIPT = 'instalar.iss'
INSTALLER_OUTPUT_DIR = 'INSTALADOR_FINAL'

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BUILD_BASE_DIR = os.path.join(os.path.dirname(REPO_ROOT), '.build_temp')
BUILD_VENV_PY = r"C:\\Users\\User\\AppData\\Local\\Programs\\Python\\Python311\\python.exe"

AUTO_MODE = '--auto' in sys.argv

def _bd(v): d=os.path.join(BUILD_BASE_DIR,f'v{v}'); os.makedirs(d,exist_ok=True); return d

def _copiar_fontes(build_dir):
    fontes=os.path.join(build_dir,'fontes')
    if os.path.exists(fontes): shutil.rmtree(fontes,ignore_errors=True)
    os.makedirs(fontes)
    exclui={'.venv','venv','.git','build_protegido','BACKUPS','build','dist','__pycache__','.build_temp','PACOTE_ENVIO'}
    itens=[ENTRY_SCRIPT,'menu.py','config.py','configuracao_fiscal.py','dados_oficina.py','servidor.py','core','config.json','config.cfg','versao.json','version.json','version.txt','version_info.py','client_secret_desktop.json','assets','locales','Documentos','templates','static','fundomenu.png','LOGO.bmp','icone_oficina.ico','iniciar_servidor.bat',INSTALLER_SCRIPT,'instalar_oficial_completo.iss','Atualizador.exe','android_apk','apk_celular_distribuicao','Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf','Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf','Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf']
    c=0
    for item in itens:
        if any(e in item for e in exclui): continue
        src=os.path.join(REPO_ROOT,item)
        if not os.path.exists(src): continue
        dst=os.path.join(fontes,item)
        try:
            if os.path.isdir(src): shutil.copytree(src,dst,dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst),exist_ok=True)
                shutil.copy2(src,dst)
            c+=1
        except: pass
    print(f'   -> {c} itens copiados')
    return fontes

def _nuitka(fontes,versao):
    print(DIV); print('NUITKA: Compilando com protecao'); print(DIV)
    dist=os.path.join(_bd(versao),'dist')
    if os.path.exists(dist): shutil.rmtree(dist,ignore_errors=True)
    os.makedirs(dist)
    entry=os.path.join(fontes,ENTRY_SCRIPT)
    cmd=[BUILD_VENV_PY,'-m','nuitka','--standalone','--follow-imports','--windows-console-mode=disable',f'--output-dir={dist}',f'--output-filename={APP_NAME}.exe',f'--include-data-dir={os.path.join(fontes,"assets")}=assets',f'--include-data-dir={os.path.join(fontes,"locales")}=locales',f'--include-data-dir={os.path.join(fontes,"Documentos")}=Documentos',entry]
    icone=os.path.join(fontes,'icone_oficina.ico')
    if os.path.exists(icone): cmd.insert(-1,f'--windows-icon-from-ico={icone}')
    print('Nuitka em andamento...')
    try:
        r=subprocess.run(cmd,cwd=fontes,capture_output=False,timeout=3600)
        if r.returncode!=0: print(f'Nuitka falhou: {r.returncode}'); return ''
    except subprocess.TimeoutExpired: print('Timeout 1h'); return ''
    except Exception as ex: print(f'Erro: {ex}'); return ''
    exe=os.path.join(dist,APP_NAME+'.exe')
    if not os.path.exists(exe):
        for root,_,files in os.walk(dist):
            if APP_NAME+'.exe' in files: exe=os.path.join(root,APP_NAME+'.exe'); break
    if os.path.exists(exe): print(f'OK: Executavel {os.path.getsize(exe)/(1024*1024):.1f} MB'); return dist
    print('Executavel nao encontrado'); return ''

def _recursos(bundle,fontes):
    dist=bundle
    if not os.path.exists(os.path.join(dist,APP_NAME+'.exe')):
        cand=os.path.join(os.path.dirname(bundle),APP_NAME+'.dist')
        if os.path.exists(cand): dist=cand
    for r in ['config.cfg','versao.json','version.json','version.txt','config.json','client_secret_desktop.json','iniciar_servidor.bat','Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf']:
        src=os.path.join(fontes,r)
        if os.path.exists(src): shutil.copy2(src,os.path.join(dist,os.path.basename(src)))

def _iscc():
    for p in [r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',r'C:\Program Files\Inno Setup 6\ISCC.exe']:
        if os.path.exists(p): return p
    return 'ISCC'

def _inno(versao):
    print('Inno Setup...')
    iss=os.path.join(REPO_ROOT,INSTALLER_SCRIPT)
    if not os.path.exists(iss): print('ISS nao encontrado'); return ''
    out=f'Oficina_Pesca_v{versao}_Setup.exe'
    cmd=[_iscc(),iss,f'/O{INSTALLER_OUTPUT_DIR}',f'/F{out}']
    try:
        subprocess.run(cmd,check=True,cwd=REPO_ROOT,timeout=600)
        inst=os.path.join(INSTALLER_OUTPUT_DIR,out)
        if os.path.exists(inst): print(f'OK: {inst}'); return inst
    except Exception as ex: print(f'Erro Inno: {ex}')
    return ''

def print_header():
    print(DIV); print('MESTRE BUILD v1.0.64 - CADEIA NUITKA'); print('='*50)
    print(f'   Projeto: {APP_NAME}'); print(f'   Versao: {VERSAO}'); print(f'   Build: {_bd(VERSAO)}'); print(DIV)

def smoke_test():
    print('Smoke test...')
    try:
        subprocess.run([sys.executable,'-c','import login; print("OK")'],cwd=REPO_ROOT,check=True,timeout=30)
        print('OK'); return True
    except Exception as ex: print(f'Falhou: {ex}'); return False

def limpar_pastas():
    for p in ['build','dist','fontes']:
        x=os.path.join(_bd(VERSAO),p)
        if os.path.exists(x): shutil.rmtree(x,ignore_errors=True); print(f'Limpo: {x}')

def main():
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass
    print_header()
    proj=input('Projeto: ').strip() or APP_NAME
    ver=input(f'Versao [{VERSAO}]: ').strip() or VERSAO
    print(DIV); print('RESUMO'); print(f'   Projeto: {proj}'); print(f'   Versao: {ver}'); print('   Compilador: NUITKA'); print(DIV)
    if not AUTO_MODE:
        if input('Continuar? [S/n]: ').strip().lower()=='n': print('Cancelado'); return
    if not smoke_test(): print('Abortado'); sys.exit(1)
    limpar_pastas()
    bd=_bd(ver)
    fontes=_copiar_fontes(bd)
    dist=_nuitka(fontes,ver)
    if not dist: print('Build Nuitka falhou'); sys.exit(1)
    _recursos(dist,fontes)
    inst=_inno(ver)
    print(DIV); print('BUILD CONCLUIDO'); print(f'   Dist: {dist}'); print(f'   Instalador: {inst}'); print(DIV)

if __name__=='__main__': main()
