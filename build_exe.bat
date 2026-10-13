@echo off
setlocal
cd /d "%~dp0"

rem This wrapper never deletes or modifies release, build, dist, data or logs.

set "REQUESTED_PYTHON=%PYTHON_EXE%"
set "PYTHON_EXE="
set "PYTHON_ARGS="
if defined REQUESTED_PYTHON if exist "%REQUESTED_PYTHON%" set "PYTHON_EXE=%REQUESTED_PYTHON%"
if not defined PYTHON_EXE if exist ".venv-build\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv-build\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYTHON_EXE=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYTHON_EXE where py >nul 2>nul && set "PYTHON_EXE=py" && set "PYTHON_ARGS=-3"
if not defined PYTHON_EXE where python >nul 2>nul && set "PYTHON_EXE=python"
if not defined PYTHON_EXE (
  echo Python was not found. Install Python 3.11+ or set PYTHON_EXE to python.exe path.
  exit /b 1
)

echo Using Python: %PYTHON_EXE% %PYTHON_ARGS%

echo Building into outputs\<version>\LenormandGroupBot. Existing release, data and logs are untouched.
call "%PYTHON_EXE%" %PYTHON_ARGS% tools\build_release.py %*
if errorlevel 1 exit /b 1
if not defined NO_PAUSE pause
exit /b 0
