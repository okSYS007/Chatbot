@echo off
cd /d "%~dp0"

tasklist /FI "IMAGENAME eq LenormandGroupBot.exe" | find /I "LenormandGroupBot.exe" >nul
if errorlevel 1 (
  echo Bot is not running.
  pause
  exit /b 0
)

echo Stopping LenormandGroupBot.exe...
taskkill /IM LenormandGroupBot.exe /F
if errorlevel 1 (
  echo Failed to stop bot.
  pause
  exit /b 1
)

echo Bot stopped.
pause
