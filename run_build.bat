@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set VENV_PY=.venv\Scripts\python.exe
set PYTHONIOENCODING=utf-8
set OFP_SKIP_HOMOLOG=1
echo ============================================
echo  BUILD OFICINA DE PESCA v1.0.62
echo ============================================
echo.
echo [1/3] Executando mestre_build.py...
"%VENV_PY%" mestre_build.py "oficina de pesca" 1.0.62 --auto --no-bump > build_output.log 2>&1
set BUILD_EXIT=%ERRORLEVEL%
echo.
echo Build finalizado com codigo: %BUILD_EXIT%
echo.
if %BUILD_EXIT% equ 0 (
    echo [OK] Build concluido com sucesso!
) else (
    echo [ERRO] Build falhou. Verifique build_output.log
)
exit /b %BUILD_EXIT%
