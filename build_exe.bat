@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_CMD="
if defined PYTHON_EXE if exist "%PYTHON_EXE%" set "PYTHON_CMD=%PYTHON_EXE%"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
if not defined PYTHON_CMD where py >nul 2>nul && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD where python >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
  echo Python was not found. Install Python 3.11+ or set PYTHON_EXE to python.exe path.
  goto fail
)

echo Using Python: %PYTHON_CMD%

echo Installing runtime dependencies...
%PYTHON_CMD% -m pip install -r requirements.txt
if errorlevel 1 goto fail

echo Installing build dependencies...
%PYTHON_CMD% -m pip install -r requirements-build.txt
if errorlevel 1 goto fail

echo Cleaning old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release

echo Building exe...
%PYTHON_CMD% -m PyInstaller --clean --noconfirm LenormandGroupBot.spec
if errorlevel 1 goto fail

echo Preparing release folder...
mkdir release
xcopy /e /i /y dist\LenormandGroupBot release\LenormandGroupBot
copy /y config.example.yaml release\LenormandGroupBot\config.example.yaml
copy /y .env.example release\LenormandGroupBot\.env.example
copy /y README.md release\LenormandGroupBot\README.md
copy /y setup_bot.bat release\LenormandGroupBot\setup_bot.bat
copy /y start_bot.bat release\LenormandGroupBot\start_bot.bat
if not exist release\LenormandGroupBot\data mkdir release\LenormandGroupBot\data
if not exist release\LenormandGroupBot\logs mkdir release\LenormandGroupBot\logs

echo.
echo Done. Release is here:
echo release\LenormandGroupBot\LenormandGroupBot.exe
echo.
pause
exit /b 0

:fail
echo.
echo Build failed.
pause
exit /b 1
