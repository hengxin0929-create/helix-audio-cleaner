#!/bin/bash
# 音频文件清理工具 - 双击启动脚本
# 功能：自动检查 Python 环境与依赖，然后启动图形界面
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  osascript -e 'display alert "未找到 Python3" message "请先安装 Python3：https://www.python.org/downloads/"'
  echo "未找到 python3，请先安装：https://www.python.org/downloads/"
  exit 1
fi

if ! python3 -c "import mutagen" >/dev/null 2>&1; then
  echo "首次运行：正在安装依赖库 mutagen ..."
  pip3 install mutagen --quiet
  if ! python3 -c "import mutagen" >/dev/null 2>&1; then
    osascript -e 'display alert "依赖安装失败" message "请手动在终端执行：pip3 install mutagen"'
    echo "依赖安装失败，请手动执行：pip3 install mutagen"
    exit 1
  fi
fi

echo "正在启动音频文件清理工具 ..."
exec python3 main.py
