@echo off
chcp 65001 >nul
title HELIX音频清理工具 - Windows打包脚本

echo ========================================
echo   HELIX音频清理工具 - Windows 打包
echo ========================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.9 或更高版本
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)

:: 创建虚拟环境（隔离依赖，不污染系统 Python）
if not exist venv (
    echo [1/5] 创建虚拟环境 venv...
    python -m venv venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
) else (
    echo [1/5] 虚拟环境已存在，跳过创建
)

:: 激活虚拟环境
echo [2/5] 激活虚拟环境...
call venv\Scripts\activate.bat

:: 安装依赖
echo [3/5] 安装依赖（mutagen / pyinstaller / pillow）...
python -m pip install --upgrade pip
pip install mutagen pyinstaller pillow
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

:: 转换图标 icns -^> ico
echo [4/5] 转换图标...
python -c "from PIL import Image; img = Image.open('horse.icns'); img.save('horse.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
if errorlevel 1 (
    echo [警告] 图标转换失败，将使用默认图标继续打包
)

:: 打包
echo [5/5] 打包 exe（这可能需要 1-2 分钟）...
pyinstaller --windowed --name "HELIX音频清理工具" --icon horse.ico --collect-all mutagen --noconfirm main.py
if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   打包完成！
echo   产物: dist\HELIX音频清理工具.exe
echo ========================================
echo.
echo 提示：首次在其他电脑上运行时，Windows 可能提示"未知发布者"，
echo       点击"更多信息" -^> "仍要运行"即可。
echo.
pause
