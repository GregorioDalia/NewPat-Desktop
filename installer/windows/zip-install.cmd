@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\installer\windows\install-zip.ps1" -BundleDirectory "%~dp0." -OpenWhenReady
set "NEWPAT_EXIT=%ERRORLEVEL%"
if not "%NEWPAT_EXIT%"=="0" (
    echo.
    pause
)
exit /b %NEWPAT_EXIT%
