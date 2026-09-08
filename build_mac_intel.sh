#!/bin/bash
# ============================================
# HELIX音频清理工具 - Mac Intel (x86_64) 打包脚本
# 需要：Rosetta 2 + Xcode Command Line Tools
# 在 Apple Silicon (M1/M2/M3/M4) Mac 上通过 Rosetta 交叉打包 Intel 版
# ============================================
set -e
cd "$(dirname "$0")"

APP_NAME="HELIX音频清理工具"

echo "========================================"
echo "  Mac Intel (x86_64) 打包"
echo "========================================"

# 1. 检查并安装 Rosetta 2
if ! /usr/bin/pgrep -q oahd 2>/dev/null; then
    echo "[1/5] 安装 Rosetta 2..."
    softwareupdate --install-rosetta --agree-to-license
else
    echo "[1/5] Rosetta 2 已安装"
fi

# 2. 检查 universal Python
if ! file /usr/bin/python3 | grep -q "x86_64"; then
    echo "[错误] /usr/bin/python3 不支持 x86_64，请安装 Xcode Command Line Tools"
    echo "       执行: xcode-select --install"
    exit 1
fi
echo "[2/5] 检测到 universal Python（支持 x86_64）"

# 3. 创建 x86_64 虚拟环境
if [ ! -d venv_intel ]; then
    echo "[3/5] 创建 x86_64 虚拟环境..."
    arch -x86_64 /usr/bin/python3 -m venv venv_intel
else
    echo "[3/5] 虚拟环境已存在，跳过创建"
fi

# 4. 安装依赖
echo "[4/5] 安装依赖（mutagen / pyinstaller）..."
arch -x86_64 ./venv_intel/bin/python -m pip install --upgrade pip --quiet
arch -x86_64 ./venv_intel/bin/python -m pip install mutagen pyinstaller --quiet

# 5. 打包
echo "[5/5] 打包 .app（可能需要 1-2 分钟）..."
arch -x86_64 ./venv_intel/bin/pyinstaller \
    --windowed \
    --name "$APP_NAME" \
    --icon horse.icns \
    --collect-all mutagen \
    --noconfirm \
    --distpath dist_intel \
    --workpath build_intel \
    main.py

# 清理中间产物
rm -rf build_intel "dist_intel/$APP_NAME"

echo ""
echo "========================================"
echo "  打包完成！"
echo "  产物: dist_intel/$APP_NAME.app"
echo "  架构: $(file "dist_intel/$APP_NAME.app/Contents/MacOS/$APP_NAME" | grep -o 'x86_64')"
echo "========================================"
