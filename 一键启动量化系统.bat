@echo off
chcp 936 >nul
setlocal enabledelayedexpansion
title QuantAI ����Ͷ��ϵͳ - һ������

set "BACKEND_DIR=%~dp0quant-invest-server-py"
set "FRONTEND_DIR=%~dp0quant-invest-vue"

echo ============================================================
echo    QuantAI ��������Ͷ��ϵͳ - һ������
echo ============================================================
echo    ��˷��� : http://localhost:3000   ��Python FastAPI��
echo    ǰ��ҳ�� : http://localhost:5189
echo ============================================================
echo.

rem ---- ��λ Python�����ȱ���·�����Ҳ����ٴ� PATH �� ----
set "PYTHON_EXE="
if exist "D:\math\python\python.exe" set "PYTHON_EXE=D:\math\python\python.exe"
if not defined PYTHON_EXE (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE (
    echo [����] δ�ҵ� Python ���л������밲װ Python �����ԡ�
    pause
    exit /b 1
)

rem ---- ��λ Node�����ȱ���·�����Ҳ����ٴ� PATH �� ----
set "NODE_EXE="
if exist "C:\Users\77018\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\node\node.exe" set "NODE_EXE=C:\Users\77018\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\vm\tools\node\node.exe"
if not defined NODE_EXE (
    where node >nul 2>&1 && set "NODE_EXE=node"
)
if not defined NODE_EXE (
    echo [����] δ�ҵ� Node.js ���л��������Ȱ�װ Node.js��
    pause
    exit /b 1
)

rem ---- ���������Լ�� ----
if not exist "%BACKEND_DIR%\main.py" (
    echo [����] δ�ҵ��������ļ� main.py��
    echo        %BACKEND_DIR%\main.py
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules\vite\bin\vite.js" (
    echo [����] ǰ������δ��װ������ִ�У�
    echo        cd /d %FRONTEND_DIR%
    echo        npm install
    echo.
    pause
    exit /b 1
)

echo [1/3] ��鲢������˷��񣨶˿� 3000��...
netstat -ano | findstr ":3000 " | findstr "LISTENING" >nul 2>&1
if !errorlevel!==0 (
    echo        ��˷����������У�����������
) else (
    pushd "%BACKEND_DIR%"
    start "QuantAI-���-3000" /MIN "%PYTHON_EXE%" -s main.py
    popd
    echo        ��˷�����������
)

echo [2/3] ��鲢����ǰ�˷��񣨶˿� 5189��...
netstat -ano | findstr ":5189 " | findstr "LISTENING" >nul 2>&1
if !errorlevel!==0 (
    echo        ǰ�˷����������У�����������
) else (
    pushd "%FRONTEND_DIR%"
    start "QuantAI-ǰ��-5189" /MIN "%NODE_EXE%" node_modules\vite\bin\vite.js
    popd
    echo        ǰ�˷�����������
)

echo [3/3] �ȴ�����������������...
timeout /t 3 /nobreak >nul
start "" http://localhost:5189

echo.
echo ============================================================
echo    ������ɣ���������Զ��� http://localhost:5189
echo    ������л�����Python (FastAPI)  -  �˿� 3000
echo    ֹͣ���񣺹رն�Ӧ�����������д��ڣ�
echo             ��˫����ֹͣ����ϵͳ.bat��
echo ============================================================
echo.
pause