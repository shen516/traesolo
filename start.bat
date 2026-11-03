@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ========================================
echo  足球量化分析工具 - Windows 启动脚本
echo ========================================
echo.

REM ---- 定位后端 Python（优先 .venv，兼容 venv）----
set "PYTHON_EXE="
if exist "%~dp0backend\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0backend\.venv\Scripts\python.exe"
) else if exist "%~dp0backend\venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0backend\venv\Scripts\python.exe"
)

if not defined PYTHON_EXE (
    echo [错误] 未找到后端虚拟环境。
    echo        请先执行：
    echo          cd backend
    echo          python -m venv .venv
    echo          .venv\Scripts\activate.bat
    echo          pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "%~dp0frontend\node_modules\" (
    echo [错误] 未找到前端依赖 frontend\node_modules。
    echo        请先执行：
    echo          cd frontend
    echo          npm install
    echo.
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 node，请安装 Node.js 18+ 并重新打开终端。
    echo.
    pause
    exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 npm，请确认 Node.js 安装完整且已加入 PATH。
    echo.
    pause
    exit /b 1
)

echo [1/2] 启动后端 API  ^> http://localhost:8000
start "Football-Backend" /D "%~dp0backend" cmd /k ""%PYTHON_EXE%" main.py"

REM 稍等后端起来，再开前端
timeout /t 3 /nobreak >nul

echo [2/2] 启动前端开发服 ^> http://localhost:5173
start "Football-Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

echo.
echo ----------------------------------------
echo  已在两个新窗口中启动服务：
echo    后端窗口标题: Football-Backend
echo    前端窗口标题: Football-Frontend
echo.
echo  访问地址:
echo    前端  http://localhost:5173
echo    后端  http://localhost:8000
echo    接口文档 http://localhost:8000/docs
echo.
echo  停止方式: 关闭对应窗口，或在窗口内按 Ctrl+C
echo ----------------------------------------
echo.
pause
endlocal
