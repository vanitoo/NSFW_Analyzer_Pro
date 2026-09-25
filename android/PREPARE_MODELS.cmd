@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\scripts\prepare_models.ps1"
exit /b %ERRORLEVEL%
