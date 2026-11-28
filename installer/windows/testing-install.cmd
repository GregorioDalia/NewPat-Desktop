@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-testing.ps1"
set "NEWPAT_EXIT=%ERRORLEVEL%"
if not "%NEWPAT_EXIT%"=="0" (
    echo.
    pause
)
exit /b %NEWPAT_EXIT%
