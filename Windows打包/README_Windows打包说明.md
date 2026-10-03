# HELIX音频清理工具 — Windows 打包说明

> 本文件夹自包含，拷到任何 Windows 电脑上双击 `build_windows.bat` 即可一键打包出 exe。

## 文件夹内容

| 文件 | 说明 |
|---|---|
| `main.py` | 主程序（含一机一码授权，与 HELIX 拼音工具**共用同一授权**） |
| `horse.ico` / `horse.icns` | 应用图标（已转换好 .ico，无需再处理） |
| `build_windows.bat` | 一键打包脚本（双击运行） |
| `requirements.txt` | 依赖清单（mutagen / cryptography / pyinstaller / pillow） |
| `test_logic.py` | 核心逻辑自测（可选运行） |
| `CHANGELOG.md` | 更新日志 |

## 一键打包步骤（在 Windows 电脑上）

1. **安装 Python 3.10 或更高版本**
   - 下载地址：https://www.python.org/downloads/
   - 安装时**务必勾选 “Add Python to PATH”**

2. 把本文件夹**整个拷贝**到 Windows 电脑（建议放到纯英文路径，如 `C:\HELIX打包`）

3. 双击 **`build_windows.bat`**

4. 脚本自动完成：创建虚拟环境 → 安装依赖 → 打包，全程无需手动操作

5. 打包完成后，产物在：**`dist\HELIX音频清理工具.exe`**（双击即可运行，可把 dist 整个目录发给客户）

## 授权说明（重要）

- **一机一码**：首次在客户电脑上运行时，会弹出激活窗口，显示机器码（可一键复制）；把机器码发给管理员，拿到授权凭证粘贴即可激活
- **授权文件位置**：`C:\ProgramData\HELIX音频拼音\license.lic`
- **与 HELIX 拼音处理工具共用一个授权**：同一台电脑只要激活过其中任意一个，另一个直接可用，无需重复激活
- **激活时请以管理员身份运行**（右键 exe → 以管理员身份运行），否则 Windows 可能写入失败

## 常见问题

| 问题 | 解决办法 |
|---|---|
| 提示“未找到 Python” | 安装 Python 3.10+ 并勾选 Add Python to PATH，重开命令窗口 |
| 依赖安装失败 | 检查网络，重新双击 bat（虚拟环境已建，会跳过已装依赖） |
| Windows 提示“未知发布者” | 点“更多信息” → “仍要运行”（未签名 exe 的正常提示） |
| 授权到期 | 启动时提示到期，粘贴新的授权凭证即可 |
| 打包出来的 exe 杀毒软件报毒 | PyInstaller 打包常见误报，可加白名单或发给杀软厂商申诉 |

## 自测（可选）

打包前想先验证逻辑，可运行：

```
venv\Scripts\python test_logic.py
```

全部显示“全部测试通过”即为正常。
