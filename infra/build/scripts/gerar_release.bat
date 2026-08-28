@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0..\..\.."
cd /d "%ROOT%"

set "VENV_PY=.venv\Scripts\python.exe"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "APP_NAME=Oficina_Pesca"
set "DIST_DIR=dist\%APP_NAME%"
set "STAGE_DIR=infra\releases\%APP_NAME%"
set "SETUP_NAME=Setup_OficinaPesca_v1.0.54.exe"
set "APK_FIXED=apk_celular_distribuicao\oficina_app_signed.apk"
set "APK_DEBUG=apk_celular_distribuicao\app-debug.apk"
set "ARTIFACT_ROOT=infra\build\artifacts"

if not exist "%ARTIFACT_ROOT%" mkdir "%ARTIFACT_ROOT%"
if not exist "%STAGE_DIR%" mkdir "%STAGE_DIR%"

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
    exit /b 1
)

echo [3/9] Limpeza total...
if exist "%ARTIFACT_ROOT%\Setup_OficinaPesca.exe" del /q "%ARTIFACT_ROOT%\Setup_OficinaPesca.exe"
if exist "%ARTIFACT_ROOT%\%SETUP_NAME%" del /q "%ARTIFACT_ROOT%\%SETUP_NAME%"
if exist "%STAGE_DIR%" rmdir /s /q "%STAGE_DIR%"
if exist "login.spec" del /q "login.spec"
if exist "Oficina_Pesca.spec" del /q "Oficina_Pesca.spec"
if exist "logs\oficina_debug.txt" del /q "logs\oficina_debug.txt"
if exist "logs\log_envio_meta.json" del /q "logs\log_envio_meta.json"
if exist "logs\ia_relatorios" rmdir /s /q "logs\ia_relatorios"
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"

mkdir "%STAGE_DIR%" >nul 2>nul

echo [4/9] Preparando APK mobile...
if exist "%APK_FIXED%" (
    echo [OK] APK assinado encontrado.
) else (
    if exist "%APK_DEBUG%" (
        echo [AVISO] APK assinado nao encontrado. Usando app-debug.apk como fallback.
        copy /Y "%APK_DEBUG%" "%APK_FIXED%" >nul
    ) else (
        echo [ERRO] Nenhum APK encontrado em apk_celular_distribuicao.
        exit /b 1
    )
)

echo [5/9] Aplicando codigo protegido (Nuitka) dos modulos de negocio...
"%VENV_PY%" "%~dp0aplicar_protegido.py" aplicar
if errorlevel 1 (
    echo [ERRO] Falha ao aplicar modulos protegidos.
    exit /b 1
)

echo [6/9] Build PyInstaller...
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
    login.py
set "PYI_ERRORLEVEL=%ERRORLEVEL%"

echo [6b/9] Restaurando fontes .py originais (pos-build)...
"%VENV_PY%" "%~dp0aplicar_protegido.py" restaurar

if not "%PYI_ERRORLEVEL%"=="0" (
    echo [ERRO] Falha no PyInstaller.
    exit /b 1
)

echo [7/9] Compilando instalador final com Inno Setup...
"%ISCC_EXE%" "instalar.iss"
if errorlevel 1 (
    echo [ERRO] Falha ao compilar instalador.
    exit /b 1
)

echo [8/9] Copiando app onedir para infra\releases...
xcopy /E /I /Y "%DIST_DIR%\*" "%STAGE_DIR%\" >nul
if errorlevel 1 (
    echo [ERRO] Falha ao copiar app final para %STAGE_DIR%
    exit /b 1
)

if exist "INSTALADOR_FINAL\%SETUP_NAME%" copy /y "INSTALADOR_FINAL\%SETUP_NAME%" "%ARTIFACT_ROOT%\%SETUP_NAME%" >nul
if exist "Output\Oficina_Pesca_Portatil.zip" copy /y "Output\Oficina_Pesca_Portatil.zip" "%ARTIFACT_ROOT%\Oficina_Pesca_Portatil.zip" >nul

echo.
echo ============================================
echo  RELEASE FINAL GERADO COM SUCESSO
echo ============================================
echo APP:   %STAGE_DIR%\%APP_NAME%.exe
echo SETUP: %ARTIFACT_ROOT%\%SETUP_NAME%
echo.
exit /b 0
