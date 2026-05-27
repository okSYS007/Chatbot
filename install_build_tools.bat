@echo off
setlocal

cd /d "%~dp0"

echo This script prepares a clean Windows PC for building LenormandGroupBot.exe.
echo It is needed only for development/building, not for running the ready release.
echo.

set "PYTHON_CMD="
if defined PYTHON_EXE if exist "%PYTHON_EXE%" set "PYTHON_CMD=%PYTHON_EXE%"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo Python was not found.
  echo Trying to install Python with winget...
  where winget >nul 2>nul
  if errorlevel 1 (
    echo winget was not found.
    echo Install Python 3.11 or newer manually from https://www.python.org/downloads/
    pause
    exit /b 1
  )
  winget install --id Python.Python.3.13 -e --source winget
  if errorlevel 1 (
    echo Python installation failed.
    pause
    exit /b 1
  )
)

set "PYTHON_CMD="
if defined PYTHON_EXE if exist "%PYTHON_EXE%" set "PYTHON_CMD=%PYTHON_EXE%"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"

if not defined PYTHON_CMD (
  echo Python was installed, but this terminal cannot find it yet.
  echo Close this window, open it again, then run install_build_tools.bat once more.
  pause
  exit /b 1
)

echo Using Python: %PYTHON_CMD%

echo Upgrading pip...
%PYTHON_CMD% -m pip install --upgrade pip
if errorlevel 1 goto fail

echo Installing runtime dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo Installing build dependencies...
%PYTHON_CMD% -m pip install -r requirements-build.txt
if errorlevel 1 goto fail

echo.
echo Done. This PC is ready to build the exe.
echo Run build_exe.bat when you need a new release.
pause
exit /b 0

:fail
echo.
echo Failed to install build tools.
pause
exit /b 1
