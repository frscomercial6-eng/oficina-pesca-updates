@echo off
setlocal
cd /d %~dp0

set GCLOUD=.tools\gcloud\google-cloud-sdk\bin\gcloud.cmd
if not exist "%GCLOUD%" (
  echo [ERRO] gcloud local nao encontrado em %GCLOUD%
  exit /b 1
)

set PROJECT_ID=oficinapescasystem
set REGION=southamerica-east1
set SERVICE_NAME=oficina-pesca-api

"%GCLOUD%" config set project %PROJECT_ID%
"%GCLOUD%" config set run/region %REGION%

"%GCLOUD%" run deploy %SERVICE_NAME% ^
  --source . ^
  --region %REGION% ^
  --project %PROJECT_ID% ^
  --allow-unauthenticated ^
  --port 8080 ^
  --cpu 1 ^
  --memory 1Gi ^
  --timeout 300 ^
  --set-env-vars OFP_DB_PATH=/tmp/oficina.db

"%GCLOUD%" run services describe %SERVICE_NAME% --region %REGION% --project %PROJECT_ID% --format="value(status.url)"

endlocal
