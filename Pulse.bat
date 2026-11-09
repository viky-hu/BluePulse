@echo off
setlocal
set "MODE=production"
if "%~1"=="--dev" set "MODE=dev"
if "%~1"=="--check-config" set "MODE=check"
if "%~1"=="--check-health" set "MODE=health"
if "%~1"=="--probe-model" set "MODE=probe"
if "%~1"=="--copy-admin-password" set "MODE=clipboard"
if "%~1"=="--stop" set "MODE=stop"
if not "%~1"=="" if "%MODE%"=="production" (
  echo Usage: Pulse.bat [--dev ^| --check-config ^| --check-health ^| --probe-model ^| --copy-admin-password ^| --stop]
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-pulse.ps1" -Mode %MODE%
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" if "%~1"=="" if not "%BLUEPULSE_LAUNCH_NO_BROWSER%"=="1" pause
exit /b %RESULT%
