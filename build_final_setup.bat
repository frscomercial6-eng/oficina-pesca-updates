@echo off
setlocal
set "SCRIPT_DIR=%~dp0infra\build\scripts"
if exist "%SCRIPT_DIR%\build_final_setup.bat" (
  call "%SCRIPT_DIR%\build_final_setup.bat"
  exit /b %ERRORLEVEL%
) else (
  echo [ERRO] Script de build nao encontrado em %SCRIPT_DIR%
  exit /b 1
)
