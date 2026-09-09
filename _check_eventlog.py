import subprocess, os
result = subprocess.run(
    ['powershell', '-Command', 
     'Get-WinEvent', '-FilterHashtable', 
     "@{LogName='Application';Level=2;StartTime=(Get-Date).AddMinutes(-30)}",
     '-MaxEvents', '5', '-ErrorAction', 'SilentlyContinue'],
    capture_output=True, text=True, timeout=10
)
with open(r'F:\PROGRAMA\OFICINA DE PESCA\OFICINA_PESCA_ORIGINAL\_event_log.txt', 'w') as f:
    f.write(f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}")
print("Done")
