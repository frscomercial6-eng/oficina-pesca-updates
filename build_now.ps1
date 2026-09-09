# Script de Build para Oficina de Pesca v1.0.64
$ErrorActionPreference = "Continue"

Write-Host "=== BUILD OFICINA DE PESCA v1.0.64 ===" -ForegroundColor Cyan
Write-Host "Iniciando em: $(Get-Date)"

$py = 'F:\PROGRAMA\.venv_oficina_pesca_build\Scripts\python.exe'
$workDir = 'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL'
Set-Location $workDir

# Limpar builds anteriores
Remove-Item "dist\Oficina_Pesca" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "build\Oficina_Pesca" -Recurse -Force -ErrorAction SilentlyContinue

# Comando PyInstaller
$cmd = @(
    $py, "-m", "PyInstaller",
    "--onedir", "--windowed", "--noconfirm",
    "--add-data", "assets;assets",
    "--add-data", "locales;locales",
    "--add-data", "static;static",
    "--add-data", "templates;templates",
    "--add-data", "Documentos;Documentos",
    "--add-data", "versao.json;.",
    "--add-data", "version.json;.",
    "--add-data", "version.txt;.",
    "--add-data", "config.cfg;.",
    "--add-data", "client_secret_desktop.json;.",
    "--add-data", "Contrato_Oficina_de_Pesca_V3_Maio_2026.rtf;.",
    "--add-data", "Contrato_Oficina_de_Pesca_V3_Maio_2026_en_US.rtf;.",
    "--add-data", "Contrato_Oficina_de_Pesca_V3_Maio_2026_es_UY.rtf;.",
    "--add-data", "fundomenu.png;.",
    "--add-data", "LOGO.bmp;."
)

# Hidden imports principais
$hiddenImports = @(
    "firebase_admin", "googleapiclient", "googleapiclient.discovery",
    "google_auth_oauthlib", "google.oauth2", "google.auth",
    "oauth2client", "httplib2", "urllib", "cryptography", "certifi",
    "PIL", "fpdf", "reportlab", "customtkinter", "tkinter", "psutil",
    "google.cloud.firestore", "adaptador_acbr", "clientes", "config",
    "configuracao_fiscal", "dados_oficina", "gestao_os", "menu",
    "login", "migracao_fiscal_2027", "pdv", "shutdown_utils",
    "tela_financeiro", "tela_os", "tela_planos", "util_recibo", "core.i18n"
)

foreach ($h in $hiddenImports) {
    $cmd += "--hidden-import"
    $cmd += $h
}

# Collect-all
$collectAll = @("googleapiclient", "google.cloud.firestore", "firebase_admin", "google.auth", "google.oauth2", "oauth2client", "reportlab", "PIL", "customtkinter")
foreach ($c in $collectAll) {
    $cmd += "--collect-all"
    $cmd += $c
}

$cmd += "--name", "Oficina_Pesca"
$cmd += "login.py"

Write-Host "Executando PyInstaller..."
Write-Host "Total de argumentos: $($cmd.Count)"

# Executar e capturar saída
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $cmd[0]
$psi.Arguments = $cmd[1..($cmd.Count-1)] -join " "
$psi.WorkingDirectory = $workDir
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
$process.Start() | Out-Null

$stdout = $process.StandardOutput.ReadToEnd()
$stderr = $process.StandardError.ReadToEnd()
$process.WaitForExit()

Write-Host ""
Write-Host "=== FIM DO BUILD ===" -ForegroundColor Cyan
Write-Host "Exit Code: $($process.ExitCode)"

# Salvar logs
$stdout | Out-File -FilePath "build_stdout.log" -Encoding UTF8
$stderr | Out-File -FilePath "build_stderr.log" -Encoding UTF8

# Verificar resultado
if ($process.ExitCode -eq 0) {
    if (Test-Path "dist\Oficina_Pesca\Oficina_Pesca.exe") {
        $size = [math]::Round((Get-Item "dist\Oficina_Pesca\Oficina_Pesca.exe").Length / 1MB, 2)
        Write-Host "SUCESSO! EXE: dist\Oficina_Pesca\Oficina_Pesca.exe ($size MB)" -ForegroundColor Green
    } else {
        Write-Host "Build terminou com código 0, mas EXE não encontrado!" -ForegroundColor Yellow
    }
} else {
    Write-Host "Build FALHOU com código $($process.ExitCode)" -ForegroundColor Red
    Write-Host "Verifique build_stderr.log para detalhes"
}