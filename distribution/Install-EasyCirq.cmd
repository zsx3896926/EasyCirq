@echo off
rem EasyCirq toolchain installer entry (double-click friendly).
rem All real work happens in Install-EasyCirq.ps1 -> easycirq_install.py.
setlocal
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set "PS=powershell"
where pwsh >nul 2>&1 && set "PS=pwsh"
%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-EasyCirq.ps1" %*
set "result=%errorlevel%"
echo.
pause
exit /b %result%
