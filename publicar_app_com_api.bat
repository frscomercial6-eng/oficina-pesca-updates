@echo off
setlocal
cd /d %~dp0

if "%~1"=="" (
  echo Uso: publicar_app_com_api.bat URL_DA_API_CLOUD_RUN
  echo Exemplo: publicar_app_com_api.bat https://oficina-pesca-api-xxxxx-ue.a.run.app
  exit /b 1
)

set "API_URL=%~1"

powershell -NoProfile -Command "$p='firebase_hosting/public/app-config.json'; $u='%API_URL%'.Trim().TrimEnd('/'); $obj=@{apiBaseUrl=$u}; $json=$obj|ConvertTo-Json -Depth 3; [System.IO.File]::WriteAllText($p,$json,[System.Text.UTF8Encoding]::new($false)); Write-Host ('app-config.json atualizado: ' + $u)"
if errorlevel 1 exit /b 1

firebase deploy --only hosting
if errorlevel 1 exit /b 1

echo Publicacao concluida com API em: %API_URL%
endlocal
