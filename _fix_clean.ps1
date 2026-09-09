# Remove --clean from mestre_build.py
$path = 'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py'
$content = Get-Content $path -Raw -Encoding UTF8
if ($content -match '\"--clean\"') {
    $newContent = $content -replace '\"--clean\",?\r?\n', ''
    Set-Content -Path $path -Value $newContent -Encoding UTF8 -NoNewline
    Write-Output 'OK: --clean removed from mestre_build.py'
} else {
    Write-Output 'WARNING: --clean not found in mestre_build.py'
}
