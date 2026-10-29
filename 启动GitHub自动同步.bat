@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist "workspace\cache" mkdir "workspace\cache"
if exist ".venv\Scripts\python.exe" goto venv
where py >nul 2>nul
if not errorlevel 1 goto py
where python >nul 2>nul
if not errorlevel 1 goto python
echo Python 3.10+ is required. Run the dependency installer first.
exit /b 1
:venv
".venv\Scripts\python.exe" -X utf8 "workspace\scripts\git_auto_sync.py" --start
exit /b %ERRORLEVEL%
:py
py -3 -X utf8 "workspace\scripts\git_auto_sync.py" --start
exit /b %ERRORLEVEL%
:python
python -X utf8 "workspace\scripts\git_auto_sync.py" --start
exit /b %ERRORLEVEL%
