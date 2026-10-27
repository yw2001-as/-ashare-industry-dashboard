@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto venv
where py >nul 2>nul
if not errorlevel 1 goto py
where python >nul 2>nul
if not errorlevel 1 goto python
echo 请先安装Python 3.10或以上版本，并勾选Add Python to PATH。
pause
exit /b 1
:venv
".venv\Scripts\python.exe" "workspace\scripts\launch_dashboard.py"
goto done
:py
py -3 "workspace\scripts\launch_dashboard.py"
goto done
:python
python "workspace\scripts\launch_dashboard.py"
:done
if errorlevel 1 pause
