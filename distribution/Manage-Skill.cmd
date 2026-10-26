@echo off
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python3
py -3 "%~dp0skill_update.py" menu %*
set "result=%errorlevel%"
goto finish
:try_python3
python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto try_python
python3 "%~dp0skill_update.py" menu %*
set "result=%errorlevel%"
goto finish
:try_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if errorlevel 1 goto missing_python
python "%~dp0skill_update.py" menu %*
set "result=%errorlevel%"
goto finish
:missing_python
echo Python 3.10+ required: https://www.python.org/downloads/
set result=2
:finish
echo.
pause
exit /b %result%
