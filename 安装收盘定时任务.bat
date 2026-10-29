@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -File "workspace\scripts\install_closing_task.ps1"
if errorlevel 1 pause
