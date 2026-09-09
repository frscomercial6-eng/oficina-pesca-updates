# Remove BOM from mestre_build.py
$path = 'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py'
$bytes = [System.IO.File]::ReadAllBytes($path)
if ($bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
    $clean = $bytes[3..($bytes.Length-1)]
    [System.IO.File]::WriteAllBytes($path, $clean)
    Write-Output "BOM removed."
} else {
    Write-Output "No BOM found."
}
# Also verify Python syntax
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
$temp = [System.IO.Path]::GetTempFileName() + '.py'
[System.IO.File]::WriteAllText($temp, $content, [System.Text.Encoding]::ASCII)
Write-Output "Check complete."
