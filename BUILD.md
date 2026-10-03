# 跨平台打包说明

本文档说明如何为 **Mac Intel** 和 **Windows** 两个平台打包 HELIX音频清理工具。

> 所有平台均使用 Python 虚拟环境（venv）隔离依赖，不污染系统 Python。

---

## 目录结构

```
音频文件清理工具/
├── main.py                  # 主程序
├── horse.icns               # 应用图标（Mac）
├── build_mac_intel.sh       # Mac Intel 一键打包脚本
├── build_windows.bat        # Windows 一键打包脚本
├── .github/workflows/build.yml  # GitHub Actions 自动构建
├── venv_intel/              # Mac Intel 虚拟环境（打包脚本自动创建）
├── dist/                    # Mac Apple Silicon 版产物
├── dist_intel/              # Mac Intel 版产物
└── BUILD.md                 # 本文档
```

---

## 一、Mac Intel (x86_64) 版

### 前提条件
- Apple Silicon Mac（M1/M2/M3/M4）+ Rosetta 2，或直接在 Intel Mac 上运行
- Xcode Command Line Tools（提供 `/usr/bin/python3` universal binary）

### 一键打包

```bash
cd 音频文件清理工具
./build_mac_intel.sh
```

脚本会自动完成：
1. 检查/安装 Rosetta 2
2. 创建 x86_64 虚拟环境 `venv_intel/`
3. 安装 mutagen + pyinstaller
4. 打包为 `.app`
5. 输出到 `dist_intel/HELIX音频清理工具.app`

### 手动打包（逐条命令）

```bash
# 1. 创建 x86_64 虚拟环境
arch -x86_64 /usr/bin/python3 -m venv venv_intel

# 2. 安装依赖
arch -x86_64 ./venv_intel/bin/python -m pip install mutagen pyinstaller

# 3. 打包
arch -x86_64 ./venv_intel/bin/pyinstaller \
    --windowed --name "HELIX音频清理工具" \
    --icon horse.icns --collect-all mutagen \
    --distpath dist_intel --workpath build_intel main.py
```

### 验证架构

```bash
file dist_intel/HELIX音频清理工具.app/Contents/MacOS/HELIX音频清理工具
# 应输出: Mach-O 64-bit executable x86_64
```

---

## 二、Windows 版

Windows `.exe` 无法在 macOS 上直接打包，有两种方式：

### 方式 A：GitHub Actions 自动构建（推荐）

项目已包含 `.github/workflows/build.yml`，推送到 GitHub 后自动构建 Windows + Mac Intel 两个版本。

**使用步骤：**
1. 将项目推送到 GitHub 仓库
2. 进入仓库的 **Actions** 页面
3. 点击左侧 **构建跨平台安装包** → **Run workflow** → 选择分支 → 运行
4. 等待构建完成（约 3-5 分钟）
5. 在运行详情页的 **Artifacts** 区域下载：
   - `HELIX音频清理工具-Windows`（.exe）
   - `HELIX音频清理工具-MacIntel`（.app）

> 也可以推送 `v1.0.0` 格式的 tag 自动触发构建。

### 方式 B：在 Windows 电脑上本地打包

**前提条件：** Windows 10/11 + Python 3.9+（安装时勾选 "Add Python to PATH"）

**步骤：**
1. 将整个项目文件夹拷贝到 Windows 电脑
2. 双击运行 `build_windows.bat`
3. 脚本会自动创建虚拟环境、安装依赖、转换图标、打包
4. 产物在 `dist\HELIX音频清理工具.exe`

**手动打包（逐条命令）：**

```bat
python -m venv venv
venv\Scripts\activate
pip install mutagen pyinstaller pillow
python -c "from PIL import Image; img = Image.open('horse.icns'); img.save('horse.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
pyinstaller --windowed --name "HELIX音频清理工具" --icon horse.ico --collect-all mutagen --noconfirm main.py
```

---

## 三、虚拟环境说明

| 平台 | 虚拟环境目录 | Python 架构 | 创建方式 |
|------|------------|-----------|---------|
| Mac Apple Silicon | `venv/`（可选） | arm64 | `python3 -m venv venv` |
| Mac Intel | `venv_intel/` | x86_64 | `arch -x86_64 /usr/bin/python3 -m venv venv_intel` |
| Windows | `venv/` | x86_64 | `python -m venv venv` |

- 虚拟环境仅用于打包，运行已打包的 `.app` / `.exe` 不需要 Python 环境
- 如需重新打包，虚拟环境可复用，无需重复创建
- 删除虚拟环境不影响已打包的产物

---

## 四、常见问题

**Q: Mac Intel 版在 Apple Silicon Mac 上能运行吗？**
A: 能，通过 Rosetta 2 转译运行。但推荐使用 Apple Silicon 原生版（`dist/` 目录下的），性能更好。

**Q: Windows 版首次运行提示"未知发布者"？**
A: 正常现象。点击"更多信息" → "仍要运行"即可。如需消除提示，需要购买代码签名证书。

**Q: 打包后的文件体积多大？**
A: Mac 版约 10-30MB，Windows 版约 15-30MB（包含 Python 运行时 + mutagen）。

**Q: 如何更新图标？**
A: 替换 `horse.icns` 文件后重新打包即可。Windows 版会自动从 icns 转换为 ico。
