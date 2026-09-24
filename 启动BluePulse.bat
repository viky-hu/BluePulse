@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "API_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NEXT_CMD=%ROOT%node_modules\.bin\next.cmd"

if not exist "%API_PYTHON%" (
  echo [ERROR] Backend Python environment not found:
  echo         %API_PYTHON%
  echo Set up the backend dependencies first.
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

echo Starting BluePulse API...
curl.exe --silent --fail --output nul http://127.0.0.1:8000/api/v1/health/ready
if errorlevel 1 start "BluePulse API - 8000" /D "%BACKEND_DIR%" "%API_PYTHON%" -m uvicorn bluepulse_backend.main:app --reload --host 127.0.0.1 --port 8000

echo Starting BluePulse Web...
curl.exe --silent --fail --output nul http://127.0.0.1:3000
if errorlevel 1 start "BluePulse Web - 3000" /D "%ROOT%" "%NEXT_CMD%" dev --hostname 127.0.0.1 --port 3000

echo Waiting for both services to become ready...
set /a ATTEMPTS=0

:WAIT_FOR_SERVICES
curl.exe --silent --fail --output nul http://127.0.0.1:8000/api/v1/health/ready
if errorlevel 1 goto RETRY
curl.exe --silent --fail --output nul http://127.0.0.1:3000
if errorlevel 1 goto RETRY
goto OPEN_BROWSER

:RETRY
set /a ATTEMPTS+=1
if %ATTEMPTS% geq 90 goto START_TIMEOUT
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
goto WAIT_FOR_SERVICES

:OPEN_BROWSER
echo Services are ready. Opening http://localhost:3000
start "" "http://localhost:3000"
echo You can close this window; keep the two service windows running.
exit /b 0

:START_TIMEOUT
echo [ERROR] Services did not become ready within 3 minutes.
echo Check the API and Web windows for details.
pause
exit /b 1
