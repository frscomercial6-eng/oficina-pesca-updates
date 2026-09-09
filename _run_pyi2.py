import subprocess, sys, os, time
py=r'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL\\.venv\\Scripts\\python.exe'
cmd=[py,'-m','PyInstaller','--exclude-module','googleapiclient','--exclude-module','google_auth','--exclude-module','google.auth','--exclude-module','google_api_python_client','login.py','--name','TESTE_EXCL','--windowed','--noconfirm','--paths','.']
log=r'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL\\build_v1064_b10.txt'
logf=open(log,'w',encoding='utf-8')
print('START:',time.strftime('%H:%M:%S'))
logf.write('START: '+time.strftime('%H:%M:%S')+'\\n')
logf.flush()
p=subprocess.Popen(cmd,cwd=r'F:\\PROGRAMA\\OFICINA DE PESCA\\OFICINA_PESCA_ORIGINAL',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,universal_newlines=True,bufsize=1)
for line in p.stdout:
    logf.write(line)
    logf.flush()
    if line.strip(): print(line.rstrip())
p.wait()
logf.write('EXIT:'+str(p.returncode)+'\\n')
logf.close()
print('EXIT CODE:',p.returncode)
