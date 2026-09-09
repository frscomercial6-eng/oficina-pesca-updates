# Fix the 24-space --noconfirm line
$path = 'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py'
$lines = [System.IO.File]::ReadAllLines($path, [System.Text.Encoding]::UTF8)
$found = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s{20,}"--noconfirm"') {
        $leading = $lines[$i] -replace '^\s+', ''
        $indent = '            '
        $lines[$i] = $indent + $leading
        $found = $true
        Write-Output "Fixed line $($i+1): now $($lines[$i])"
    }
}
if ($found) {
    [System.IO.File]::WriteAllLines($path, $lines, [System.Text.Encoding]::UTF8)
    Write-Output 'Saved.'
} else {
    Write-Output 'No fix needed.'
}
