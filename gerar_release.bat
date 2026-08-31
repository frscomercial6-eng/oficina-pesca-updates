@echo off
setlocal
set "SCRIPT_DIR=%~dp0infra\build\scripts"
if exist "%SCRIPT_DIR%\gerar_release.bat" (
  call "%SCRIPT_DIR%\gerar_release.bat"
  exit /b %ERRORLEVEL%
) else (
  echo [ERRO] Script de release nao encontrado em %SCRIPT_DIR%
  exit /b 1
)

set "VENV_PY=.venv\Scripts\python.exe"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "APP_NAME=Oficina_Pesca"
set "DIST_DIR=dist\%APP_NAME%"
set "STAGE_DIR=INSTALADOR_FINAL\%APP_NAME%"
set "SETUP_NAME=Setup_OficinaPesca_v1.0.57.exe"
set "APK_FIXED=apk_celular_distribuicao\oficina_app_signed.apk"
set "APK_DEBUG=apk_celular_distribuicao\app-debug.apk"

echo ============================================
echo  RELEASE DEFINITIVO - OFICINA DE PESCA
echo ============================================
echo.

echo [1/9] Validando ambiente...
if not exist "%VENV_PY%" (
    echo [ERRO] Python da venv nao encontrado: %VENV_PY%
    exit /b 1
)
if not exist "%ISCC_EXE%" (
    echo [ERRO] Inno Setup nao encontrado: !ISCC_EXE!
    exit /b 1
)
if not exist "instalar.iss" (
    echo [ERRO] Script do Inno Setup nao encontrado: instalar.iss
    exit /b 1
)
if not exist "login.py" (
    echo [ERRO] Arquivo principal nao encontrado: login.py
    exit /b 1
)

echo [2/9] Validando dependencias Python...
"%VENV_PY%" -c "import customtkinter, reportlab, sqlite3, fpdf, PIL; print('Dependencias OK')"
if errorlevel 1 (
    echo [ERRO] Dependencias ausentes na venv.
    echo        Rode: .venv\Scripts\python.exe -m pip install customtkinter reportlab fpdf2 pillow
    exit /b 1
)

if /I "%OFP_SKIP_HOMOLOG%"=="1" (
    echo [2.5/9] Homologacao ignorada por OFP_SKIP_HOMOLOG=1 ^(build rapido^).
) else (
    echo [2.5/9] Rodando homologacao rapida ^(5 minutos^) antes do build...
    "%VENV_PY%" "homologacao_5min.py" --build
    if errorlevel 1 (
        echo [ERRO] Homologacao falhou. Build interrompido.
        exit /b 1
    )
)

echo [3/9] Limpeza total ^(build, dist, setup e specs antigos^)...
if exist "INSTALADOR_FINAL\Setup_OficinaPesca.exe" del /q "INSTALADOR_FINAL\Setup_OficinaPesca.exe"
if exist "INSTALADOR_FINAL\%SETUP_NAME%" del /q "INSTALADOR_FINAL\%SETUP_NAME%"
if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"
if exist "login.spec" del /q "login.spec"
if exist "oficina.spec" del /q "oficina.spec"
if exist "Oficina_Pesca.spec" del /q "Oficina_Pesca.spec"
if exist "Oficina_Pesca_FRS.spec" del /q "Oficina_Pesca_FRS.spec"
if exist "logs\oficina_debug.txt" del /q "logs\oficina_debug.txt"
if exist "logs\log_envio_meta.json" del /q "logs\log_envio_meta.json"
if exist "logs\ia_relatorios" rmdir /s /q "logs\ia_relatorios"
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"

echo [4/9] Preparando APK mobile...
if exist "%APK_FIXED%" (
    echo [OK] APK assinado encontrado.
) else (
    if exist "%APK_DEBUG%" (
        echo [AVISO] APK assinado nao encontrado. Usando app-debug.apk como fallback.
        copy /Y "%APK_DEBUG%" "%APK_FIXED%" >nul
        if errorlevel 1 (
            echo [ERRO] Falha ao preparar APK fallback.
            exit /b 1
        )
    ) else (
        echo [ERRO] Nenhum APK encontrado em apk_celular_distribuicao.
        exit /b 1
    )
)
if not exist "apk_celular_distribuicao\instrucoes_instalacao.txt" (
    if exist "TESTE_ OFICINA\apk_celular_distribuicao\instrucoes_instalacao.txt" (
        echo [AVISO] Instrucoes de instalacao ausentes na raiz. Copiando do pacote de teste.
        copy /Y "TESTE_ OFICINA\apk_celular_distribuicao\instrucoes_instalacao.txt" "apk_celular_distribuicao\instrucoes_instalacao.txt" >nul
    )
)
if not exist "apk_celular_distribuicao\instrucoes_instalacao.txt" (
    echo [ERRO] Arquivo nao encontrado: apk_celular_distribuicao\instrucoes_instalacao.txt
    exit /b 1
)
if not exist "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf" (
    if exist "Documentos\Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf" (
        echo [AVISO] Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf ausente na raiz. Copiando de Documentos.
        copy /Y "Documentos\Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf" "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf" >nul
    )
)
if not exist "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf" (
    echo [ERRO] Arquivo nao encontrado: Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf
    exit /b 1
)
if not exist "google_oauth_client_secret.json" (
    if exist "google_oauth_client_secret.json.json" (
        echo [AVISO] Corrigindo nome do client secret OAuth para google_oauth_client_secret.json.
        copy /Y "google_oauth_client_secret.json.json" "google_oauth_client_secret.json" >nul
    )
)

echo [5/9] Montando ativos opcionais para o bundle...
set "PYI_OPTIONAL="
if exist "images" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""images;images"""
if exist "fundomenu.png" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""fundomenu.png;."""
if exist "LOGO.bmp" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""LOGO.bmp;."""
if exist "icone_oficina.ico" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""icone_oficina.ico;."""
if exist "icone_app_chave_anzol.png" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""icone_app_chave_anzol.png;."""
if exist "config.cfg" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""config.cfg;."""
if exist "versao.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""versao.json;."""
if exist "licencas.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""licencas.json;."""
if exist "credentials.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""credentials.json;."""
if exist "client_secret_desktop.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""client_secret_desktop.json;."""
if exist "google-services.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""google-services.json;."""
if exist "google_oauth_client_secret.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""google_oauth_client_secret.json;."""
if exist "google_oauth_client_secret.json.json" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""google_oauth_client_secret.json.json;."""
if exist "templates" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""templates;templates"""
if exist "static" set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""static;static"""
if exist "oficina.db" (
    set "PYI_OPTIONAL=!PYI_OPTIONAL! --add-data ""oficina.db;."""
    echo [OK] SQLite local sera incluido no pacote.
) else (
    echo [AVISO] oficina.db nao encontrado agora. O banco sera criado em runtime ao lado do exe.
)

echo [6/9] Build PyInstaller ^(sem usar .spec legado^)...
"%VENV_PY%" -m PyInstaller ^
    --noconfirm --clean --onedir --windowed ^
    --name "%APP_NAME%" ^
    --icon "icone_oficina.ico" ^
    --collect-all customtkinter ^
    --collect-all reportlab ^
    --collect-all fpdf ^
    --hidden-import menu ^
    --hidden-import config ^
    --hidden-import tela_planos ^
    --hidden-import tela_os ^
    --hidden-import tela_financeiro ^
    --hidden-import clientes ^
    --hidden-import gestao_os ^
    --hidden-import util_recibo ^
    --hidden-import=core ^
    --hidden-import=core.modulos ^
    --hidden-import=core.financeiro ^
    --hidden-import=core.financeiro.calculos ^
    --hidden-import sqlite3 ^
    --hidden-import fpdf ^
    --hidden-import reportlab.graphics.shapes ^
    --hidden-import reportlab.platypus ^
    --hidden-import google.auth ^
    --hidden-import google.auth.transport.requests ^
    --hidden-import google.oauth2.credentials ^
    --hidden-import google_auth_oauthlib ^
    --hidden-import google_auth_oauthlib.flow ^
    --hidden-import googleapiclient ^
    --hidden-import googleapiclient.discovery ^
    --hidden-import googleapiclient.http ^
    --add-data "apk_celular_distribuicao\oficina_app_signed.apk;apk_celular_distribuicao" ^
    --add-data "apk_celular_distribuicao\instrucoes_instalacao.txt;apk_celular_distribuicao" ^
    --add-data "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf;." ^
    !PYI_OPTIONAL! ^
    login.py
if errorlevel 1 (
    echo [ERRO] Falha no PyInstaller.
    exit /b 1
)

echo [7/9] Validando artefatos do build...
if not exist "%DIST_DIR%\%APP_NAME%.exe" (
    echo [ERRO] Executavel nao encontrado em %DIST_DIR%\%APP_NAME%.exe
    exit /b 1
)
if exist "config.json" (
    copy /Y "config.json" "%DIST_DIR%\config.json" >nul
    echo [OK] config.json copiado para o pacote onedir ^(modulos editaveis sem rebuild^).
) else (
    echo [AVISO] config.json nao encontrado na raiz; usando fallback de modulos no executavel.
)
if not exist "%DIST_DIR%\_internal\apk_celular_distribuicao\oficina_app_signed.apk" (
    echo [ERRO] APK nao foi embutido no _internal.
    exit /b 1
)
if not exist "%DIST_DIR%\_internal\apk_celular_distribuicao\instrucoes_instalacao.txt" (
    echo [ERRO] Instrucoes mobile nao foram embutidas no _internal.
    exit /b 1
)

echo [8/9] Compilando instalador final com Inno Setup...
"%ISCC_EXE%" "instalar.iss"
if errorlevel 1 (
    echo [ERRO] Falha ao compilar instalador ^(instalar.iss^).
    exit /b 1
)

echo [9/9] Copiando app onedir para INSTALADOR_FINAL...
mkdir "%STAGE_DIR%" >nul 2>nul
xcopy /E /I /Y "%DIST_DIR%\*" "%STAGE_DIR%" >nul
if errorlevel 1 (
    echo [ERRO] Falha ao copiar app final para %STAGE_DIR%
    exit /b 1
)

echo.
echo ============================================
echo  RELEASE FINAL GERADO COM SUCESSO
echo ============================================
echo APP:   %STAGE_DIR%\%APP_NAME%.exe
echo SETUP: INSTALADOR_FINAL\%SETUP_NAME%
echo.
exit /b 0