@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\run.ps1" gui
set "NEWPAT_EXIT=%ERRORLEVEL%"
if "%NEWPAT_EXIT%"=="85" exit /b 0
if not "%NEWPAT_EXIT%"=="0" pause
exit /b %NEWPAT_EXIT%
