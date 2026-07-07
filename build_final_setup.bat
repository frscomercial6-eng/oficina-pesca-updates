@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "SETUP_NAME=Setup_OficinaPesca_v1.0.27.1.exe"
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
if /I not "%PY_VER%"=="Python 3.12.13" (
  echo [ERRO] .venv com versao invalida.
  echo         Esperado: Python 3.12.13
  echo         Encontrado: %PY_VER%
  exit /b 1
)

echo [1.5/5] Rodando homologacao rapida ^(5 minutos^) antes do build...
"%VENV_PY%" "homologacao_5min.py" --build
if errorlevel 1 (
  echo [ERRO] Homologacao falhou. Build interrompido.
  exit /b 1
)

echo [2/5] Limpando build antigo (build, dist e .spec)...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Oficina_Pesca.spec" del /q "Oficina_Pesca.spec"

echo [3/5] Gerando build com PyInstaller (APK + instrucoes + contrato)...
if not exist "apk_celular_distribuicao\oficina_app_signed.apk" (
  echo [ERRO] Arquivo nao encontrado: apk_celular_distribuicao\oficina_app_signed.apk
  exit /b 1
)
if not exist "apk_celular_distribuicao\instrucoes_instalacao.txt" (
  echo [ERRO] Arquivo nao encontrado: apk_celular_distribuicao\instrucoes_instalacao.txt
  exit /b 1
)
if not exist "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf" (
  echo [ERRO] Arquivo de contrato nao encontrado: Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf
  exit /b 1
)

echo [3.1/5] Forcando contrato em codificacao ANSI (cp1252)...
"%VENV_PY%" -c "from pathlib import Path; p=Path('Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf'); raw=p.read_bytes().decode('latin-1', errors='ignore'); head=raw[:120]; raw = raw if '\\ansi' in head else raw.replace('{\\rtf1','{\\rtf1\\ansi\\ansicpg1252',1); p.write_bytes(raw.encode('cp1252', errors='ignore')); print('[OK] Contrato normalizado para ANSI cp1252.')"
if errorlevel 1 (
  echo [ERRO] Falha ao normalizar contrato para ANSI.
  exit /b 1
)

if not exist "client_secret_desktop.json" (
  echo [ERRO] Arquivo nao encontrado: client_secret_desktop.json
  exit /b 1
)

"%VENV_PY%" -m PyInstaller --noconfirm --onedir --windowed --collect-all "customtkinter" --add-data "apk_celular_distribuicao/oficina_app_signed.apk;apk_celular_distribuicao" --add-data "apk_celular_distribuicao/instrucoes_instalacao.txt;apk_celular_distribuicao" --add-data "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf;." --add-data "client_secret_desktop.json;." --add-data "client_secret_desktop.json;assets" --name "Oficina_Pesca" login.py
if errorlevel 1 (
  echo [ERRO] Falha no PyInstaller.
  exit /b 1
)

if exist "config.json" (
  copy /y "config.json" "dist\Oficina_Pesca\config.json" >nul
  if errorlevel 1 (
    echo [ERRO] Falha ao copiar config.json para o pacote onedir.
    exit /b 1
  )
  echo [OK] config.json copiado para dist\Oficina_Pesca (modulos editaveis sem rebuild).
) else (
  echo [AVISO] config.json nao encontrado na raiz. Fallback interno de modulos sera utilizado.
)

echo [4/5] Compilando instalador com Inno Setup...
if not exist "%ISCC_EXE%" (
  echo [ERRO] Inno Setup ISCC.exe nao encontrado em:
  echo        !ISCC_EXE!
  exit /b 1
)

"%ISCC_EXE%" "instalar.iss"
if errorlevel 1 (
  echo [ERRO] Falha ao compilar instalador (instalar.iss).
  exit /b 1
)

echo [5/5] Gerando ZIP portatil e validando saidas finais...
if exist "INSTALADOR_FINAL\%SETUP_NAME%" (
  echo [OK] EXE final gerado em INSTALADOR_FINAL\%SETUP_NAME%
) else (
  echo [ERRO] Instalador final nao encontrado em INSTALADOR_FINAL.
  exit /b 1
)

if not exist "Output" mkdir "Output"
if not exist "PACOTE_ENVIO" mkdir "PACOTE_ENVIO"
if exist "Output\Oficina_Pesca_Portatil.zip" del /q "Output\Oficina_Pesca_Portatil.zip"
if exist "PACOTE_ENVIO\Oficina_Pesca_Portatil.zip" del /q "PACOTE_ENVIO\Oficina_Pesca_Portatil.zip"
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Oficina_Pesca\*' -DestinationPath 'Output\Oficina_Pesca_Portatil.zip' -CompressionLevel Optimal"
if errorlevel 1 (
  echo [ERRO] Falha ao gerar ZIP portatil em Output\Oficina_Pesca_Portatil.zip.
  exit /b 1
)
copy /y "Output\Oficina_Pesca_Portatil.zip" "PACOTE_ENVIO\Oficina_Pesca_Portatil.zip" >nul
if errorlevel 1 (
  echo [ERRO] Falha ao copiar ZIP portatil para PACOTE_ENVIO.
  exit /b 1
)
copy /y "INSTALADOR_FINAL\%SETUP_NAME%" "PACOTE_ENVIO\Oficina_Pesca_Instalador.exe" >nul
if errorlevel 1 (
  echo [ERRO] Falha ao copiar instalador para PACOTE_ENVIO.
  exit /b 1
)

echo [OK] ZIP portatil gerado em Output\Oficina_Pesca_Portatil.zip
echo [OK] Pacote de envio atualizado em PACOTE_ENVIO

echo.
echo Build final concluido com sucesso.
exit /b 0
