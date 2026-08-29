# -*- coding: utf-8 -*-
"""Teste do launcher .cmd gerado por executar_atualizacao (config.py).

Replica a montagem de script_lines com valores de teste seguros:
- PARENT_PID inexistente (o launcher deve seguir direto para :pid_encerrado)
- PROCESS_NAMES com imagem inexistente (loops de lock devem passar rapidos)
- "instalador" = cmd.exe com /c exit 0 (start "" /wait deve retornar 0)
"""
import os
import subprocess
import tempfile

base_tmp = os.path.join(tempfile.gettempdir(), "ofp_launcher_test")
os.makedirs(base_tmp, exist_ok=True)
launcher_script = os.path.join(base_tmp, "run_update_forcado.cmd")

destino = r"C:\Windows\System32\cmd.exe"
inno_log = os.path.join(base_tmp, "inno_test.log")
launcher_err_log = os.path.join(base_tmp, "update_error.log")
pid_txt = "999999"  # PID que nao existe
nomes_processo_cmd = '"inexistente_teste.exe"'
app_exec = ""

args_txt = '/SP- /VERYSILENT /SUPPRESSMSGBOXES /NOCANCEL /NORESTART "/LOG=%s"' % inno_log

script_lines = [
    "@echo off",
    "setlocal EnableExtensions",
    f'set "INSTALLER={destino}"',
    f'set "APP_EXEC={app_exec}"',
    f'set "PARENT_PID={pid_txt}"',
    f'set "UPDATE_ERR_LOG={launcher_err_log}"',
    f'set "INNO_LOG={inno_log}"',
    f'set "PROCESS_NAMES={nomes_processo_cmd}"',
    'if not exist "%INSTALLER%" (',
    '  echo [%date% %time%] Instalador nao encontrado: %INSTALLER%>>"%UPDATE_ERR_LOG%"',
    '  exit /b 2',
    ')',
]
if pid_txt:
    script_lines.extend(
        [
            'rem 1) Aguarda o encerramento GRACIOSO do proprio aplicativo,',
            'rem    que se fecha sozinho apos disparar este launcher.',
            'for /l %%I in (1,1,30) do (',
            '  tasklist /FI "PID eq %PARENT_PID%" | find "%PARENT_PID%" >nul',
            '  if errorlevel 1 goto :pid_encerrado',
            '  ping 127.0.0.1 -n 2 >nul',
            ')',
            'echo [%date% %time%] Aplicativo ainda ativo apos espera graciosa; forcando encerramento do PID %PARENT_PID%>>"%UPDATE_ERR_LOG%"',
            'rem 2) Fallback: encerra forcadamente apenas se o app nao saiu sozinho.',
            'taskkill /PID %PARENT_PID% /T /F >nul 2>nul',
            'for /l %%I in (1,1,15) do (',
            '  tasklist /FI "PID eq %PARENT_PID%" | find "%PARENT_PID%" >nul',
            '  if errorlevel 1 goto :pid_encerrado',
            '  ping 127.0.0.1 -n 2 >nul',
            ')',
            ':pid_encerrado',
        ]
    )
script_lines.extend(
    [
        'for %%P in (%PROCESS_NAMES%) do (',
        '  taskkill /IM %%~P /T /F >nul 2>nul',
        ')',
        'for /l %%I in (1,1,8) do (',
        '  set "LOCK_FOUND=0"',
        '  for %%P in (%PROCESS_NAMES%) do (',
        '    tasklist /FI "IMAGENAME eq %%~P" | find /I "%%~P" >nul && set "LOCK_FOUND=1"',
        '  )',
        '  if "%LOCK_FOUND%"=="0" goto :processos_encerrados',
        '  ping 127.0.0.1 -n 2 >nul',
        ')',
        ':processos_encerrados',
        'for %%P in (%PROCESS_NAMES%) do (',
        '  tasklist /FI "IMAGENAME eq %%~P" | find /I "%%~P" >nul && echo [%date% %time%] Processo remanescente: %%~P>>"%UPDATE_ERR_LOG%"',
        ')',
    ]
)
script_lines.extend(
    [
        f'start "" /wait "{destino}" /c exit 7'.rstrip(),
        'set "UPD_EXIT=%ERRORLEVEL%"',
        'if not "%UPD_EXIT%"=="0" (',
        '  echo [%date% %time%] Falha na execucao do instalador. exit=%UPD_EXIT%>>"%UPDATE_ERR_LOG%"',
        ')',
        'if not "%APP_EXEC%"=="" if exist "%APP_EXEC%" start "" "%APP_EXEC%"',
        'exit /b %UPD_EXIT%',
    ]
)

with open(launcher_script, "w", encoding="utf-8") as fscript:
    fscript.write("\r\n".join(script_lines) + "\r\n")

p = subprocess.Popen(["cmd.exe", "/d", "/c", launcher_script], cwd=base_tmp, creationflags=subprocess.CREATE_NEW_CONSOLE)
rc = p.wait(timeout=60)
print("LAUNCHER_EXIT=", rc, "(esperado 7: start /wait repassa o exit do 'instalador')")
if os.path.exists(launcher_err_log):
    with open(launcher_err_log, encoding="utf-8", errors="replace") as fh:
        print("ERR_LOG:", fh.read().strip() or "(vazio)")
print("TESTE_LAUNCHER_OK" if rc == 7 else "TESTE_LAUNCHER_FALHOU")
