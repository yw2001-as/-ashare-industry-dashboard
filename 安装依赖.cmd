@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 goto py
where python >nul 2>nul
if not errorlevel 1 goto python
echo 请先安装Python 3.10或以上版本，并勾选Add Python to PATH。
pause
exit /b 1
:py
py -3 -m venv .venv
goto install
:python
python -m venv .venv
:install
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo 安装完成。请双击“启动实时看板.cmd”。
pause
exit /b 0
:failed
echo 安装未完成，请检查Python版本及网络连接。
pause
exit /b 1
