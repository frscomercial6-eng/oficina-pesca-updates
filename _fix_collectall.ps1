# Remove *collect_all_args from cmd_build
$path = 'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\mestre_build.py'
$content = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
# Remove the *collect_all_args line from cmd_build
$content = $content -replace '\r?\n\s+\*collect_all_args,', ''
[System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::UTF8)
Write-Output 'OK: *collect_all_args removed'
