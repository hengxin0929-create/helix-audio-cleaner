@echo off
chcp 65001 >nul
title HELIX音频清理工具 - Windows一键打包

echo ============================================
echo   HELIX音频清理工具 - Windows 一键打包
echo ============================================
echo.

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10 或更高版本
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

:: 安装依赖（mutagen 音频处理 / cryptography 授权验签 / pyinstaller 打包 / pillow 图标转换）
echo [3/5] 安装依赖...
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
)

:: 检查图标（已附 horse.ico；缺失时用 PIL 从 icns 转换）
echo [4/5] 检查图标...
if not exist horse.ico (
    python -c "from PIL import Image; img = Image.open('horse.icns'); img.save('horse.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if errorlevel 1 (
        echo [警告] 图标转换失败，将使用默认图标继续打包
    )
)

:: 打包
echo [5/5] 打包 exe（约 1-2 分钟）...
pyinstaller --windowed --name "HELIX音频清理工具" --icon horse.ico --collect-all mutagen --noconfirm --distpath dist --workpath build main.py
if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

:: 清理中间文件
rd /s /q build 2>nul
del /q "HELIX音频清理工具.spec" 2>nul

echo.
echo ============================================
echo   打包完成！
echo   产物: dist\HELIX音频清理工具.exe
echo ============================================
echo.
echo 提示1：首次在其他电脑上运行时，Windows 可能提示"未知发布者"，
echo        点"更多信息" -^> "仍要运行"即可。
echo 提示2：授权为"一机一码"，授权文件保存在
echo        C:\ProgramData\HELIX音频拼音\license.lic
echo        与 HELIX 拼音工具共用一个授权；激活需以管理员身份运行。
echo.
pause
