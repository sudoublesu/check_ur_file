@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  ╔══════════════════════════════════════╗
echo  ║     规划文件校对工具  正在启动...      ║
echo  ╚══════════════════════════════════════╝
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [错误] 未找到 Python，请先安装 Python 3.10 及以上版本。
    echo  下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查 Streamlit
python -m streamlit --version >nul 2>&1
if errorlevel 1 (
    echo  [提示] 未检测到 Streamlit，正在自动安装依赖...
    echo.
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  [错误] 依赖安装失败，请手动运行：pip install -r requirements.txt
        pause
        exit /b 1
    )
)

echo  本机访问：  http://localhost:8501
echo  局域网访问：http://%COMPUTERNAME%:8501  （或使用本机 IP）
echo  按 Ctrl+C 可停止服务
echo.

python -m streamlit run app.py ^
  --server.address 0.0.0.0 ^
  --server.headless true ^
  --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo  [错误] 启动失败，请检查上方错误信息。
    pause
)
