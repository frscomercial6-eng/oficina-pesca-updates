@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0..\.."
cd /d "%ROOT%"

set "VENV_PY=.venv\Scripts\python.exe"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "SETUP_NAME=Setup_OficinaPesca_v1.0.53.exe"
set "SETUP_BASE=Setup_OficinaPesca_v1.0.28"
set "ALT_OUTPUT_DIR=infra\build\artifacts\INSTALADOR_FINAL_RETRY"
set "OUTPUT_ROOT=infra\build\artifacts"
set "DIST_ROOT=infra\dist"
set "BUILD_ROOT=infra\build\temp"
set "RELEASE_ROOT=infra\releases"

if not exist "%OUTPUT_ROOT%" mkdir "%OUTPUT_ROOT%"
if not exist "%DIST_ROOT%" mkdir "%DIST_ROOT%"
if not exist "%BUILD_ROOT%" mkdir "%BUILD_ROOT%"
if not exist "%RELEASE_ROOT%" mkdir "%RELEASE_ROOT%"

echo ============================================
echo  BUILD FINAL - OFICINA DE PESCA
echo ============================================
echo.

echo [1/5] Validando ambiente Python (.venv 3.12.13)...
if not exist "%VENV_PY%" (
  echo [ERRO] Python do .venv nao encontrado em %VENV_PY%
  exit /b 1
)

set "PY_VER="
for /f "usebackq delims=" %%V in (`"%VENV_PY%" --version 2^>^&1`) do set "PY_VER=%%V"
if /I not "%PY_VER%"=="Python 3.12.13" if /I not "%PY_VER%"=="Python 3.14.4" (
  echo [ERRO] .venv com versao invalida.
  echo         Esperado: Python 3.12.13 ou Python 3.14.4
  echo         Encontrado: %PY_VER%
  exit /b 1
)

echo [2/5] Limpando artefatos antigos...
if exist "%BUILD_ROOT%\build" rmdir /s /q "%BUILD_ROOT%\build"
if exist "%DIST_ROOT%" rmdir /s /q "%DIST_ROOT%"
if exist "Oficina_Pesca.spec" echo [OK] Mantendo Oficina_Pesca.spec como referencia absoluta do PyInstaller.

if not exist "Oficina_Pesca.spec" (
  echo [ERRO] Arquivo de referencia absoluto nao encontrado: Oficina_Pesca.spec
  exit /b 1
)

"%VENV_PY%" -m PyInstaller --noconfirm --clean "Oficina_Pesca.spec"
if errorlevel 1 (
  echo [ERRO] Falha no PyInstaller.
  exit /b 1
)

if not exist "dist\Oficina_Pesca\_internal\menu.py" (
  echo [ERRO] menu.py nao foi incluído em dist\Oficina_Pesca\_internal.
  exit /b 1
)

if exist "config.json" (
  copy /y "config.json" "dist\Oficina_Pesca\config.json" >nul
)

if exist "instala" (
  if not exist "dist\Oficina_Pesca\instala" mkdir "dist\Oficina_Pesca\instala"
  xcopy /E /I /Y "instala\*" "dist\Oficina_Pesca\instala\" >nul
)

echo [3/5] Compilando instalador com Inno Setup...
if not exist "%ISCC_EXE%" (
  echo [ERRO] Inno Setup ISCC.exe nao encontrado em: %ISCC_EXE%
  exit /b 1
)

"%ISCC_EXE%" "instalar.iss"
if errorlevel 1 (
  echo [AVISO] Primeira compilacao do instalador falhou. Tentando fallback...
  if not exist "%ALT_OUTPUT_DIR%" mkdir "%ALT_OUTPUT_DIR%"
  "%ISCC_EXE%" /O"%ALT_OUTPUT_DIR%" /F"%SETUP_BASE%" "instalar.iss"
  if errorlevel 1 (
    echo [ERRO] Falha ao compilar instalador.
    exit /b 1
  )
)

echo [4/5] Copiando artefatos para infra...
if not exist "%OUTPUT_ROOT%" mkdir "%OUTPUT_ROOT%"
if exist "dist\Oficina_Pesca" xcopy /E /I /Y "dist\Oficina_Pesca\*" "%OUTPUT_ROOT%\" >nul
if exist "INSTALADOR_FINAL\%SETUP_NAME%" copy /y "INSTALADOR_FINAL\%SETUP_NAME%" "%OUTPUT_ROOT%\%SETUP_NAME%" >nul
if exist "Output\Oficina_Pesca_Portatil.zip" copy /y "Output\Oficina_Pesca_Portatil.zip" "%OUTPUT_ROOT%\Oficina_Pesca_Portatil.zip" >nul

echo [5/5] Build final concluido com sucesso.
exit /b 0
