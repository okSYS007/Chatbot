@echo off
cd /d "%~dp0"

if not exist LenormandGroupBot.exe (
  echo LenormandGroupBot.exe not found.
  echo This file must be in the same folder as setup_bot.bat.
  pause
  exit /b 1
)

LenormandGroupBot.exe --setup
pause
