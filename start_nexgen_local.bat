@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_nexgen_local.ps1"
set EXITCODE=%ERRORLEVEL%
if %EXITCODE% NEQ 0 (
  echo.
  echo NEXGEN baslatma BASARISIZ. Log: logs\nexgen_stderr.log
  pause
)
exit /b %EXITCODE%
