@echo off
cd /d "F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"
"F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\.venv_build\Scripts\python.exe" "_test_analysis.py" > "_analysis_out.txt" 2>&1
echo Exit code: %ERRORLEVEL%
