# FRS OFICINA DE PESCA - Setup .venv_build limpo v1.0.64
$ErrorActionPreference = "Stop"
Set-Location "F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL"

Write-Host "=== KILL OLD PROCESSES ==="
Get-Process python,pythonw -EA SilentlyContinue |
    Where-Object { $_.Path -like "*OFICINA_PESCA_ORIGINAL*" -or $_.Path -like "*.venv_build*" } |
    Stop-Process -Force -EA SilentlyContinue
Write-Host "Killed."

Write-Host "=== REMOVE OLD VENV_BUILD ==="
if (Test-Path ".\.venv_build") {
    Remove-Item ".\.venv_build" -Recurse -Force -EA SilentlyContinue
    Write-Host "Removed."
} else {
    Write-Host "Not found (OK)."
}

Write-Host "=== CREATE NEW VENV_BUILD ==="
py -3.11 -m venv ".\.venv_build"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: nao foi possivel criar .venv_build"
    exit 1
}
Write-Host "Created."

Write-Host "=== UPGRADE PIP ==="
.\.venv_build\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: upgrade pip falhou"
    exit 1
}

Write-Host "=== INSTALL REQUIREMENTS ==="
.\.venv_build\Scripts\python.exe -m pip install -r ".\requirements.txt"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: requirements.txt falhou"
    exit 1
}

Write-Host "=== INSTALL PYINSTALLER ==="
.\.venv_build\Scripts\python.exe -m pip install "pyinstaller==6.22.2"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: pyinstaller falhou"
    exit 1
}

Write-Host ""
Write-Host "=== VERSOES ==="
.\.venv_build\Scripts\python.exe --version
.\.venv_build\Scripts\python.exe -m PyInstaller --version

Write-Host ""
Write-Host "=== VALIDAR IMPORTS ==="
.\.venv_build\Scripts\python.exe -c "import sys,customtkinter,PyInstaller; print('PYTHON_OK'); print('CUSTOMTKINTER_OK'); print('PYINSTALLER_OK')"

Write-Host ""
Write-Host "=== VALIDAR SINTAXE ==="
.\.venv_build\Scripts\python.exe -c "import ast; [ast.parse(open(f,encoding='utf-8').read()) for f in ['menu.py','tela_os.py','mestre_build.py']]; print('AST_OK')"

Write-Host ""
Write-Host "=============================================="
Write-Host "AMBIENTE .venv_build PRONTO"
Write-Host "=============================================="
