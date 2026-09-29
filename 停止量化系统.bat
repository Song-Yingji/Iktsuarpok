@echo off
setlocal enabledelayedexpansion
chcp 936 >nul
title Iktsuarpok 量化投资系统 - 停止服务

echo ============================================================
echo    Iktsuarpok 智能量化投资系统 - 停止服务
echo ============================================================
echo.

echo [1/2] 停止后端服务（端口 3000）...
set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    set "FOUND=1"
    echo        已停止后端进程 PID=%%a
)
if "!FOUND!"=="0" echo        后端服务未在运行。

echo [2/2] 停止前端服务（端口 5189）...
set "FOUND=0"
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5189 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
    set "FOUND=1"
    echo        已停止前端进程 PID=%%a
)
if "!FOUND!"=="0" echo        前端服务未在运行。

echo.
echo 完成。
echo.
pause
