@echo off
cd /d "F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
"F:\PROGRAMA\.venv_oficina_pesca_build\Scripts\python.exe" -m PyInstaller test_min_tkinter.spec --log-level=ERROR > test_min_log.txt 2>&1
echo EXIT CODE: %ERRORLEVEL% >> test_min_log.txt
