@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\installer\windows\install-zip.ps1" -BundleDirectory "%~dp0." -OpenWhenReady
set "NIPAT_EXIT=%ERRORLEVEL%"
if not "%NIPAT_EXIT%"=="0" (
    echo.
    pause
)
exit /b %NIPAT_EXIT%
