@echo off
setlocal

set "ROOT=%~dp0"
set "NEXT_CMD=%ROOT%node_modules\.bin\next.cmd"

if not exist "%NEXT_CMD%" (
  echo [ERROR] Frontend dependencies not found:
  echo         %NEXT_CMD%
  echo Run pnpm install in the project folder first.
  pause
  exit /b 1
)

echo Starting BluePulse Web...
curl.exe --silent --fail --output nul http://127.0.0.1:3000
if errorlevel 1 start "BluePulse Web - 3000" /D "%ROOT%" "%NEXT_CMD%" dev --hostname 127.0.0.1 --port 3000

echo Waiting for the website...
set /a ATTEMPTS=0

:WAIT_FOR_WEB
curl.exe --silent --fail --output nul http://127.0.0.1:3000
if not errorlevel 1 goto OPEN_BROWSER
set /a ATTEMPTS+=1
if %ATTEMPTS% geq 90 goto START_TIMEOUT
powershell.exe -NoProfile -Command "Start-Sleep -Seconds 2" >nul 2>&1
goto WAIT_FOR_WEB

:OPEN_BROWSER
echo Website is ready. Opening http://localhost:3000
start "" "http://localhost:3000"
echo You can close this window; keep the Web window running.
exit /b 0

:START_TIMEOUT
echo [ERROR] Website did not become ready within 3 minutes.
echo Check the Web window for details.
pause
exit /b 1
