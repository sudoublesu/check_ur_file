@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo  正在安装依赖包...
echo.

python -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo  [错误] 安装失败，请检查网络或手动执行：
    echo    pip install -r requirements.txt
) else (
    echo.
    echo  [完成] 依赖安装成功，现在可以双击「启动.bat」运行工具。
)

echo.
pause
