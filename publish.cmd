@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo  Publish Blog
echo  Folder: %CD%
echo ========================================
echo.

if /I "%~1"=="--test" goto test_mode

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish.ps1"
set "EXITCODE=%ERRORLEVEL%"
goto finished

:test_mode
echo [TEST] Build and check only. Nothing will be committed or pushed.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0build.ps1"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" goto finished
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0check.ps1"
set "EXITCODE=%ERRORLEVEL%"
goto finished

:finished
echo.
if "%EXITCODE%"=="0" (
    echo [SUCCESS] Process finished successfully.
) else (
    echo [FAILED] Exit code: %EXITCODE%
    echo Keep this window open and send the output above for diagnosis.
)
echo.
pause
exit /b %EXITCODE%