@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set OFP_SKIP_HOMOLOG=1
echo ============================================
echo  BUILD OFICINA DE PESCA v1.0.62
echo ============================================
echo.
echo Executando gerar_release.bat...
echo.
call "infra\build\scripts\gerar_release.bat" > "build_release.log" 2>&1
set BUILD_EXIT=%ERRORLEVEL%
echo.
echo Build finalizado com codigo: %BUILD_EXIT%
echo.
if %BUILD_EXIT% equ 0 (
    echo [OK] Build concluido com sucesso!
) else (
    echo [ERRO] Build falhou. Verifique build_release.log
)
exit /b %BUILD_EXIT%
