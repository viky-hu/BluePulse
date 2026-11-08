@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "API_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NEXT_CMD=%ROOT%node_modules\.bin\next.cmd"

rem Child processes inherit the same site origin and live worker settings.
if not defined BLUEPULSE_SITE_ORIGIN set "BLUEPULSE_SITE_ORIGIN=http://127.0.0.1:3000"
if not defined BLUEPULSE_COLLECT_ENABLED set "BLUEPULSE_COLLECT_ENABLED=1"
if not defined BLUEPULSE_MODEL_CALLS_ENABLED set "BLUEPULSE_MODEL_CALLS_ENABLED=1"
if not defined BLUEPULSE_MODEL_BUDGET_MINUTE set "BLUEPULSE_MODEL_BUDGET_MINUTE=300"
if not defined BLUEPULSE_MODEL_BUDGET_HOUR set "BLUEPULSE_MODEL_BUDGET_HOUR=6000"
if not defined BLUEPULSE_MODEL_BUDGET_DAY set "BLUEPULSE_MODEL_BUDGET_DAY=40000"

if not exist "%API_PYTHON%" (
  echo [ERROR] Backend Python environment not found:
  echo         %API_PYTHON%
  echo Follow backend\README.md to install the backend dependencies first.
  pause
  exit /b 1
)

if not exist "%NEXT_CMD%" (
  echo [ERROR] Frontend dependencies not found:
  echo         %NEXT_CMD%
  echo Run pnpm install in the project folder first.
  pause
  exit /b 1
)

pushd "%BACKEND_DIR%"
echo Checking BluePulse worker settings...
"%API_PYTHON%" -m bluepulse_backend.worker --check-config
if errorlevel 1 (
  popd
  goto WORKER_CONFIG_ERROR
)
if "%~1"=="--check-config" (
  popd
  exit /b 0
)
echo Preparing BluePulse database and source registry...
"%API_PYTHON%" -m bluepulse_backend.cli initialize
if errorlevel 1 (
  popd
  echo [ERROR] BluePulse database initialization failed.
  pause
  exit /b 1
)
popd

echo Checking BluePulse API...
curl.exe --silent --fail --connect-timeout 1 --max-time 2 --output nul http://127.0.0.1:8000/api/v1/health/ready
if not errorlevel 1 goto START_WEB

echo Starting BluePulse API...
start "BluePulse API - 8000" /D "%BACKEND_DIR%" "%API_PYTHON%" -m uvicorn bluepulse_backend.api:app --host 127.0.0.1 --port 8000
set /a ATTEMPTS=0

:WAIT_FOR_API
curl.exe --silent --fail --connect-timeout 1 --max-time 2 --output nul http://127.0.0.1:8000/api/v1/health/ready
if not errorlevel 1 goto START_WEB
set /a ATTEMPTS+=1
if %ATTEMPTS% geq 60 goto API_TIMEOUT
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
goto WAIT_FOR_API

:START_WEB
echo Starting BluePulse background worker...
start "BluePulse Worker" /D "%BACKEND_DIR%" "%API_PYTHON%" -m bluepulse_backend.worker
pushd "%BACKEND_DIR%"
"%API_PYTHON%" -m bluepulse_backend.worker --wait-ready
if errorlevel 1 (
  popd
  goto WORKER_TIMEOUT
)
popd

echo Checking BluePulse Web...
curl.exe --silent --fail --connect-timeout 1 --max-time 5 --output nul http://127.0.0.1:3000
if errorlevel 1 start "BluePulse Web - 3000" /D "%ROOT%" "%NEXT_CMD%" dev --hostname 127.0.0.1 --port 3000

echo Waiting for the website...
set /a ATTEMPTS=0

:WAIT_FOR_WEB
curl.exe --silent --fail --connect-timeout 1 --max-time 5 --output nul http://127.0.0.1:3000
if not errorlevel 1 goto OPEN_BROWSER
set /a ATTEMPTS+=1
if %ATTEMPTS% geq 90 goto START_TIMEOUT
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
goto WAIT_FOR_WEB

:OPEN_BROWSER
echo BluePulse API, Worker and Web are ready. Opening http://127.0.0.1:3000
start "" "http://127.0.0.1:3000"
echo You can close this window; keep the API, Web and Worker windows running.
exit /b 0

:API_TIMEOUT
echo [ERROR] Backend API did not become ready on port 8000.
echo Check the API window for dependency, database migration, or port errors.
echo Follow backend\README.md to initialize or migrate the database if needed.
pause
exit /b 1

:WORKER_CONFIG_ERROR
echo [ERROR] Check backend\.env and the model budgets in backend\README.md.
pause
exit /b 1

:WORKER_TIMEOUT
echo [ERROR] Worker did not become ready with the requested settings.
echo Check the Worker window. Close an older worker before changing its settings.
pause
exit /b 1

:START_TIMEOUT
echo [ERROR] Website did not become ready on port 3000.
echo Check the Web window for details.
pause
exit /b 1
