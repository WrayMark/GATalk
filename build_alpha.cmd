@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build-alpha.ps1"
if errorlevel 1 (
  echo.
  echo GATalk build failed. Keep the error output above.
  pause
)
endlocal
