@echo off
setlocal

set "ROOT=%~dp0"
set "BACKEND_DIR=%ROOT%backend"
set "API_PYTHON=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "NEXT_CMD=%ROOT%node_modules\.bin\next.cmd"

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
echo Both services are ready. Opening http://127.0.0.1:3000
start "" "http://127.0.0.1:3000"
echo You can close this window; keep the API and Web service windows running.
exit /b 0

:API_TIMEOUT
echo [ERROR] Backend API did not become ready on port 8000.
echo Check the API window for dependency, database migration, or port errors.
echo Follow backend\README.md to initialize or migrate the database if needed.
pause
exit /b 1

:START_TIMEOUT
echo [ERROR] Website did not become ready on port 3000.
echo Check the Web window for details.
pause
exit /b 1
