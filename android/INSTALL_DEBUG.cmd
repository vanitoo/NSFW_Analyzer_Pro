@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\build.ps1" -Task InstallDebug
exit /b %ERRORLEVEL%
