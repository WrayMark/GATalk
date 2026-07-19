@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-dev.ps1"
if errorlevel 1 (
  echo.
  echo SceneLens failed to start. Keep the error output above.
  pause
)
endlocal
