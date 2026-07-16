@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "APP_NAME=Oficina_Pesca"
set "DIST_DIR=dist\%APP_NAME%"
set "FINAL_SETUP=Setup_OficinaPesca_v1.0.42_FINAL.exe"
echo ============================================
echo  INSTALADOR FINAL - OFICINA DE PESCA
echo ============================================
echo.

if not exist "%VENV_PY%" (
  echo [ERRO] Python da venv nao encontrado: %VENV_PY%
  exit /b 1
)
powershell -NoProfile -Command "if (Test-Path '%ISCC_EXE%') { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [ERRO] Inno Setup nao encontrado.
  exit /b 1
)

if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "INSTALADOR_FINAL" (
  for /f "delims=" %%I in ('dir /b /a "INSTALADOR_FINAL"') do (
    if exist "INSTALADOR_FINAL\%%I\" (
      rmdir /s /q "INSTALADOR_FINAL\%%I"
    ) else (
      del /f /q "INSTALADOR_FINAL\%%I"
    )
  )
) else (
  mkdir "INSTALADOR_FINAL"
)

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

if exist "%DIST_DIR%\oficina.db" del /f /q "%DIST_DIR%\oficina.db"
if exist "config.json" copy /y "config.json" "%DIST_DIR%\config.json" >nul

powershell -NoProfile -Command "& '%ISCC_EXE%' '/DInstallerOutputName=Setup_OficinaPesca_v1.0.42_FINAL' 'instalar.iss'; exit $LASTEXITCODE"
if errorlevel 1 (
  echo [ERRO] Falha ao compilar instalador final.
  exit /b 1
)

for /f "delims=" %%I in ('dir /b /a "INSTALADOR_FINAL"') do (
  if /I not "%%I"=="%FINAL_SETUP%" del /f /q "INSTALADOR_FINAL\%%I" 2>nul
)

if not exist "INSTALADOR_FINAL\%FINAL_SETUP%" (
  echo [ERRO] Instalador final nao encontrado: INSTALADOR_FINAL\%FINAL_SETUP%
  exit /b 1
)

for %%F in ("INSTALADOR_FINAL\%FINAL_SETUP%") do echo [OK] Instalador final gerado: %%~fF ^(%%~zF bytes^)
exit /b 0
