@echo off
cd /d "F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
(
echo === CORE DIR ===
dir /b core
echo.
echo === CORE\FINANCEIRO ===
dir /b core\financeiro 2>&1
echo.
echo === RAIZ PY ===
dir /b *.py
echo.
echo === STATUS_OS? ===
if exist status_os.py (echo HAS) else (echo MISSING)
if exist dados_oficina.py (echo HAS_DADOS) else (echo MISSING_DADOS)
if exist reforma_tributaria.py (echo HAS_REFORMA) else (echo MISSING_REFORMA)
if exist validador_fiscal.py (echo HAS_VALIDADOR) else (echo MISSING_VALIDADOR)
if exist tela_planos.py (echo HAS_PLANOS) else (echo MISSING_PLANOS)
if exist util_recibo.py (echo HAS_RECIBO) else (echo MISSING_RECIBO)
) > "F:\PROGRAMA\_diag12_output.txt" 2>&1
echo DONE