@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title VideoTools

rem ================================================================
rem  启动 VideoTools（源码运行）
rem  1. 自动寻找已经装好 PyQt6 的 Python
rem  2. 找不到就提示并可一键安装依赖 (requirements.txt)
rem  3. 用 pythonw 启动，不留黑色命令行窗口
rem ================================================================

set "PY="
for %%P in (
    "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    "%ProgramFiles%\Python313\python.exe"
    "%ProgramFiles%\Python312\python.exe"
) do (
    if not defined PY if exist "%%~P" (
        "%%~P" -c "import PyQt6" >nul 2>&1 && set "PY=%%~P"
    )
)

if not defined PY (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PY (
            "%%P" -c "import PyQt6" >nul 2>&1 && set "PY=%%P"
        )
    )
)

if not defined PY (
    set "BASEPY="
    for /f "delims=" %%P in ('where python 2^>nul') do if not defined BASEPY set "BASEPY=%%P"
    if not defined BASEPY (
        echo [错误] 没有找到 Python。请先安装 Python 3.12 或 3.13: https://www.python.org/downloads/
        echo        安装时勾选 "Add python.exe to PATH"。
        pause
        exit /b 1
    )
    echo 当前 Python 缺少运行依赖 ^(PyQt6 等^): !BASEPY!
    choice /m "是否现在自动安装依赖 (requirements.txt)"
    if errorlevel 2 exit /b 1
    "!BASEPY!" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
    set "PY=!BASEPY!"
)

set "PYW=%PY:python.exe=pythonw.exe%"
if not exist "%PYW%" set "PYW=%PY%"

start "" "%PYW%" "%~dp0main\main.py"
exit /b 0
