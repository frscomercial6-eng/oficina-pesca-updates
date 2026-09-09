# Fix indentation issue on line 1754
$path = 'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py'
$content = Get-Content $path -Raw -Encoding UTF8
# Fix the doubled indentation on --noconfirm line
$content = $content -replace '\{24}"--noconfirm"', '            "--noconfirm"'
Set-Content -Path $path -Value $content -Encoding UTF8 -NoNewline
Write-Output 'OK: indentation fixed'
