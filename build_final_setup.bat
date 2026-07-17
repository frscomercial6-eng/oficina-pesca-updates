@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "ISCC_EXE=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set "SETUP_NAME=Setup_OficinaPesca_v1.0.49.exe"
set "SETUP_BASE=Setup_OficinaPesca_v1.0.28"
set "ALT_OUTPUT_DIR=INSTALADOR_FINAL_RETRY"
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

echo [1.5/5] Rodando homologacao rapida ^(5 minutos^) antes do build...
if exist "homologacao_5min.py" (
  "%VENV_PY%" "homologacao_5min.py" --build
  if errorlevel 1 (
    echo [ERRO] Homologacao falhou. Build interrompido.
    exit /b 1
  )
) else (
  echo [AVISO] homologacao_5min.py nao encontrado. Prosseguindo sem homologacao automatica.
)

echo [2/5] Limpando build antigo (build, dist e .spec)...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "Oficina_Pesca.spec" echo [OK] Mantendo Oficina_Pesca.spec como referencia absoluta do PyInstaller.

echo [2.1/5] Removendo residuos de teste/log do pacote final...
if exist "logs\oficina_debug.txt" del /q "logs\oficina_debug.txt"
if exist "logs\log_envio_meta.json" del /q "logs\log_envio_meta.json"
if exist "logs\ia_relatorios" rmdir /s /q "logs\ia_relatorios"
if exist "__pycache__" rmdir /s /q "__pycache__"
if exist ".pytest_cache" rmdir /s /q ".pytest_cache"

echo [3/5] Gerando build com PyInstaller (APK + instrucoes + contrato)...
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
if not exist "dist\Oficina_Pesca\_internal\pdv.py" (
  echo [ERRO] pdv.py nao foi incluído em dist\Oficina_Pesca\_internal.
  exit /b 1
)
if not exist "dist\Oficina_Pesca\_internal\tela_os.py" (
  echo [ERRO] tela_os.py nao foi incluído em dist\Oficina_Pesca\_internal.
  exit /b 1
)
if not exist "dist\Oficina_Pesca\_internal\configuracao_fiscal.py" (
  echo [ERRO] configuracao_fiscal.py nao foi incluído em dist\Oficina_Pesca\_internal.
  exit /b 1
)

if exist "config.json" (
  copy /y "config.json" "dist\Oficina_Pesca\config.json" >nul
  if errorlevel 1 (
    echo [ERRO] Falha ao copiar config.json para o pacote onedir.
    exit /b 1
  )
  echo [OK] config.json copiado para dist\Oficina_Pesca. Modulos editaveis sem rebuild.
) else (
  echo [AVISO] config.json nao encontrado na raiz. Fallback interno de modulos sera utilizado.
)

if exist "instala" (
  if not exist "dist\Oficina_Pesca\instala" mkdir "dist\Oficina_Pesca\instala"
  xcopy /E /I /Y "instala\*" "dist\Oficina_Pesca\instala\" >nul
  if errorlevel 1 (
    echo [ERRO] Falha ao copiar pasta instala para o pacote onedir.
    exit /b 1
  )
  echo [OK] Pasta instala copiada para dist\Oficina_Pesca\instala.
) else (
  echo [AVISO] Pasta instala nao encontrada na raiz.
)

echo [4/5] Compilando instalador com Inno Setup...
if not exist "%ISCC_EXE%" (
  echo [ERRO] Inno Setup ISCC.exe nao encontrado em:
  echo        !ISCC_EXE!
  exit /b 1
)

"%ISCC_EXE%" "instalar.iss"
if errorlevel 1 (
  echo [AVISO] Primeira compilacao do instalador falhou. Tentando fallback em pasta alternativa...
  if not exist "%ALT_OUTPUT_DIR%" mkdir "%ALT_OUTPUT_DIR%"
  "%ISCC_EXE%" /O"%CD%\%ALT_OUTPUT_DIR%" /F"%SETUP_BASE%" "instalar.iss"
  if errorlevel 1 (
    echo [ERRO] Falha ao compilar instalador ^(instalar.iss^) inclusive no fallback.
    exit /b 1
  )
  if exist "%ALT_OUTPUT_DIR%\%SETUP_NAME%" (
    if not exist "INSTALADOR_FINAL" mkdir "INSTALADOR_FINAL"
    copy /y "%ALT_OUTPUT_DIR%\%SETUP_NAME%" "INSTALADOR_FINAL\%SETUP_NAME%" >nul
    if errorlevel 1 (
      echo [ERRO] Falha ao copiar setup do fallback para INSTALADOR_FINAL.
      exit /b 1
    )
  ) else (
    echo [ERRO] Setup nao encontrado no fallback: %ALT_OUTPUT_DIR%\%SETUP_NAME%
    exit /b 1
  )
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
copy /y "INSTALADOR_FINAL\%SETUP_NAME%" "%SETUP_NAME%" >nul
if errorlevel 1 (
  echo [ERRO] Falha ao copiar o setup versionado para a raiz do projeto.
  exit /b 1
)

echo [OK] ZIP portatil gerado em Output\Oficina_Pesca_Portatil.zip
echo [OK] Pacote de envio atualizado em PACOTE_ENVIO

echo.
echo Build final concluido com sucesso.
exit /b 0
