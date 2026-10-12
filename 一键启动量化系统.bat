@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title Iktsuarpok 智能量化投资系统 - 一键启动

set "BACKEND_DIR=%~dp0quant-invest-server-py"
set "FRONTEND_DIR=%~dp0quant-invest-vue"

echo ============================================================
echo    Iktsuarpok 智能量化投资系统 - 一键启动
echo ============================================================
echo    后端服务 : http://localhost:3000   (Python FastAPI)
echo    前端页面 : http://localhost:5189
echo ============================================================
echo.

rem ---- 定位 Python 解释器（优先项目虚拟环境 .venv） ----
set "VENV_PY=%~dp0.venv\Scripts\python.exe"
set "PYTHON_EXE="
if exist "%VENV_PY%" set "PYTHON_EXE=%VENV_PY%"
if not defined PYTHON_EXE (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    echo [错误] 未找到 Python，请先安装 Python 并配置环境变量。
    pause
    exit /b 1
)

if not exist "%VENV_PY%" (
    echo [提示] 未检测到项目虚拟环境 .venv，将回退使用：%PYTHON_EXE%
    echo        建议先创建虚拟环境并安装依赖：
    echo            python -m venv .venv
    echo            .venv\Scripts\python.exe -m pip install -r quant-invest-server-py\requirements.txt
    echo.
)

rem ---- 定位 Node（优先使用指定路径，找不到再回退 PATH） ----
set "NODE_EXE=%~dp0..\..\nodejs\node.exe"
for %%i in ("%NODE_EXE%") do set "NODE_EXE=%%~fi"
if not exist "%NODE_EXE%" set "NODE_EXE="
if not defined NODE_EXE (
    for /f "delims=" %%i in ('where node 2^>nul') do if not defined NODE_EXE set "NODE_EXE=%%i"
)
if not defined NODE_EXE (
    echo [错误] 未找到 Node.js，请先安装 Node.js。
    pause
    exit /b 1
)

rem ---- 检查项目文件 ----
if not exist "%BACKEND_DIR%\main.py" (
    echo [错误] 未找到后端入口文件 main.py：
    echo        %BACKEND_DIR%\main.py
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" (
    echo [错误] 前端依赖未安装，请先执行：
    echo        cd /d %FRONTEND_DIR%
    echo        npm install
    echo.
    pause
    exit /b 1
)

echo [0/4] 使用 Python 解释器：%PYTHON_EXE%
echo.
echo [1/4] 使用 Node ：%NODE_EXE%
echo.
echo [2/4] 启动后端服务（端口 3000）...
netstat -ano | findstr ":3000 " | findstr "LISTENING" >nul 2>&1
if !errorlevel!==0 (
    echo        后端服务已在运行，跳过。
) else (
    pushd "%BACKEND_DIR%"
    start "Iktsuarpok-后端-3000" /MIN "%PYTHON_EXE%" -s main.py
    popd
    echo        后端服务已启动。
)

echo [3/4] 启动前端服务（端口 5189）...
netstat -ano | findstr ":5189 " | findstr "LISTENING" >nul 2>&1
if !errorlevel!==0 (
    echo        前端服务已在运行，跳过。
) else (
    pushd "%FRONTEND_DIR%"
    start "Iktsuarpok-前端-5189" /MIN "%NODE_EXE%" node_modules\vite\bin\vite.js
    popd
    echo        前端服务已启动。
)

echo [4/4] 打开浏览器...
timeout /t 3 /nobreak >nul
start "" http://localhost:5189

echo.
echo ============================================================
echo    欢迎访问 : http://localhost:5189
echo    感谢使用 Python (FastAPI)  -  端口 3000
echo    停止服务：关闭对应服务窗口，或双击停止量化系统.bat
echo ============================================================
echo.
pause