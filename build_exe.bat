@echo off
setlocal

cd /d "%~dp0"

set "APP_RELEASE=release\LenormandGroupBot"
set "BACKUP_DIR=%TEMP%\LenormandGroupBot_release_backup_%RANDOM%%RANDOM%"

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

if exist "%APP_RELEASE%" (
  echo Backing up existing release config, env, data and logs...
  if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
  if exist "%APP_RELEASE%\config.yaml" copy /y "%APP_RELEASE%\config.yaml" "%BACKUP_DIR%\config.yaml" >nul
  if exist "%APP_RELEASE%\.env" copy /y "%APP_RELEASE%\.env" "%BACKUP_DIR%\.env" >nul
  if exist "%APP_RELEASE%\data" xcopy /e /i /y "%APP_RELEASE%\data" "%BACKUP_DIR%\data" >nul
  if exist "%APP_RELEASE%\logs" xcopy /e /i /y "%APP_RELEASE%\logs" "%BACKUP_DIR%\logs" >nul
)

echo Cleaning old build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist release rmdir /s /q release

echo Building exe...
%PYTHON_CMD% -m PyInstaller --clean --noconfirm LenormandGroupBot.spec
if errorlevel 1 goto fail

echo Preparing release folder...
mkdir "%APP_RELEASE%"
copy /y dist\LenormandGroupBot.exe "%APP_RELEASE%\LenormandGroupBot.exe"
copy /y config.example.yaml "%APP_RELEASE%\config.example.yaml"
copy /y .env.example "%APP_RELEASE%\.env.example"
copy /y README.md "%APP_RELEASE%\README.md"
copy /y INSTRUCTION_RU.txt "%APP_RELEASE%\INSTRUCTION_RU.txt"
if not exist "%APP_RELEASE%\data" mkdir "%APP_RELEASE%\data"
if not exist "%APP_RELEASE%\logs" mkdir "%APP_RELEASE%\logs"

if exist "%BACKUP_DIR%" (
  echo Restoring existing release config, env, data and logs...
  if exist "%BACKUP_DIR%\config.yaml" copy /y "%BACKUP_DIR%\config.yaml" "%APP_RELEASE%\config.yaml" >nul
  if exist "%BACKUP_DIR%\.env" copy /y "%BACKUP_DIR%\.env" "%APP_RELEASE%\.env" >nul
  if exist "%BACKUP_DIR%\data" xcopy /e /i /y "%BACKUP_DIR%\data" "%APP_RELEASE%\data" >nul
  if exist "%BACKUP_DIR%\logs" xcopy /e /i /y "%BACKUP_DIR%\logs" "%APP_RELEASE%\logs" >nul
  rmdir /s /q "%BACKUP_DIR%"
)

echo.
echo Done. Release is here:
echo release\LenormandGroupBot\LenormandGroupBot.exe
echo.
if not defined NO_PAUSE pause
exit /b 0

:fail
echo.
echo Build failed.
if exist "%BACKUP_DIR%" rmdir /s /q "%BACKUP_DIR%"
if not defined NO_PAUSE pause
exit /b 1
