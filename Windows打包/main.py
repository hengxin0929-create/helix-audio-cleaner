#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音频文件清理工具
================
功能：
  1. 选择指定文件夹
  2. 清除文件夹内所有音频文件的属性（标签元数据：标题/歌手/专辑等）
  3. 清除文件名中的无效信息：前导序号（01、02、03-138 等）与多余符号
  4. 清除多个文件名中的类似项（例如所有文件都带有的【taoqu】）

运行方式：
  python3 main.py
  （或双击同目录下的 启动音频文件清理工具.command）

依赖：
  pip3 install mutagen
"""

import os
import re
import sys
import json
import time
import uuid
import ctypes
import hashlib
import subprocess
import threading
import traceback
from collections import OrderedDict
from datetime import datetime

import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.ttk as ttk

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
APP_TITLE = "HELIX音频清理工具"

# ================= 一机一码授权（与 HELIX 拼音工具共用同一授权） =================
PUB_KEY_PEM = """
-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzO6bMhiR93Iel3XGV6l
scjdy8e5g3IHEcbgOrQz1DSO+QmZmofxO9C5kVaeZ21DGS/JfSUraeIO8KV6QDq9
uQbqP9tHOT+AV7yYo8sj+PYMLDfywzRpv4aTgEto5mmj/m+vdt+GeZDiawtk6bkm
Ew1MeAOaQPJQdrH9cwzeQ1VLRXLkFJSaJwLpmTGFeLHftNvMiqy98YVIy8Yp2FPv
sSi9SLxa4h//LVU6QcstD5dFQJ7w6+lSYjUPN2GTbYPA+tnNUQ2u2jqGrD+YLNEf
rhN2N5dRpKNZdmfq709JH5vNGire0M+J043l3rCX7ipzAuWT1K18UAKhnKW0lhwc
IwIDAQAB
-----END PUBLIC KEY-----
"""
CLIENT_PUB_KEY = serialization.load_pem_public_key(PUB_KEY_PEM.encode("utf-8"))

def _sp_kwargs():
    """Windows 下隐藏子进程控制台黑窗；Mac/Linux 返回空。"""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

# Windows 高 DPI 感知：必须在创建任何 Tk 窗口之前调用
if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

def is_admin() -> bool:
    if sys.platform == "win32":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            return False
    return True

# 授权目录与 HELIX 拼音工具保持一致 → 两台工具共用同一个 license.lic 授权
if sys.platform == "win32":
    BASE_DIR = os.environ["PROGRAMDATA"]
else:
    BASE_DIR = os.path.expanduser("~/Library/Application Support")
LIC_FOLDER = os.path.join(BASE_DIR, "HELIX音频拼音")
LICENSE_SAVE_PATH = os.path.join(LIC_FOLDER, "license.lic")

_MACHINE_CACHE_FILE = os.path.join(LIC_FOLDER, "machine_code.cache")

def get_machine_code():
    """生成一机一码（同一台机器上与拼音工具完全一致）。"""
    if os.path.exists(_MACHINE_CACHE_FILE):
        try:
            with open(_MACHINE_CACHE_FILE, "r", encoding="utf-8") as _f:
                _cached = _f.read().strip()
            if len(_cached) == 32:
                return _cached
        except Exception:
            pass
    parts = []
    sys_type = sys.platform
    if sys_type == "darwin":
        try:
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                stderr=subprocess.DEVNULL, text=True, timeout=10
            )
            m_uuid = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', out)
            if m_uuid:
                parts.append(f"uuid:{m_uuid.group(1).strip()}")
        except Exception:
            pass
        if not parts:
            try:
                mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
                parts.append(f"mac:{mac}")
            except Exception:
                pass
    else:
        try:
            mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
            parts.append(f"mac:{mac}")
        except Exception:
            pass
        if sys_type == "win32":
            try:
                out = subprocess.check_output(
                    'wmic cpu get ProcessorId', shell=True, text=True, errors="ignore",
                    **_sp_kwargs()
                )
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                if len(lines) >= 2:
                    cpu_id = lines[1]
                    if cpu_id and cpu_id.upper() != "TO BE FILLED BY O.E.M.":
                        parts.append(f"cpu:{cpu_id}")
            except Exception:
                pass
            try:
                out = subprocess.check_output(
                    'wmic baseboard get SerialNumber', shell=True, text=True, errors="ignore",
                    **_sp_kwargs()
                )
                lines = [l.strip() for l in out.splitlines() if l.strip()]
                if len(lines) >= 2:
                    board_sn = lines[1]
                    if board_sn and board_sn.upper() != "TO BE FILLED BY O.E.M.":
                        parts.append(f"board:{board_sn}")
            except Exception:
                pass
    if len(parts) > 0:
        raw_str = "|".join(parts)
        code = hashlib.md5(raw_str.encode("utf-8")).hexdigest().upper()
    else:
        code = "UNKNOWN_DEVICE"
    try:
        os.makedirs(LIC_FOLDER, exist_ok=True)
        with open(_MACHINE_CACHE_FILE, "w", encoding="utf-8") as _f:
            _f.write(code)
    except Exception:
        pass
    return code

def verify_license_token(machine_code: str, token: str):
    """校验授权凭证：RSA-PSS 验签 + 机器码匹配。返回 (ok, 说明, expire_ts)。"""
    try:
        payload_hex, sig_hex = token.strip().split("||SIG||")
        payload_part = bytes.fromhex(payload_hex)
        sig_part = bytes.fromhex(sig_hex)
        data = json.loads(payload_part.decode("utf-8"))
        if data.get("machine_code") != machine_code:
            return False, "机器码不匹配，该授权属于别的电脑", 0
        CLIENT_PUB_KEY.verify(
            sig_part, payload_part,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256()
        )
        return True, "授权合法", data.get("expire", 0)
    except Exception as e:
        return False, f"授权凭证校验失败:{repr(e)}", 0

def check_license():
    """读取共用授权文件并校验。返回 (ok, 说明, expire_ts)。"""
    mc = get_machine_code()
    try:
        os.makedirs(LIC_FOLDER, exist_ok=True)
    except Exception:
        pass
    if os.path.exists(LICENSE_SAVE_PATH):
        try:
            with open(LICENSE_SAVE_PATH, "r", encoding="utf-8") as f:
                token = f.read().strip()
            return verify_license_token(mc, token)
        except Exception as e:
            return False, f"授权文件读取失败:{repr(e)}", 0
    return False, "未检测到授权文件，请激活软件", 0

# 常见音频扩展名
AUDIO_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus",
    ".wma", ".ape", ".wv", ".aiff", ".aif", ".m4b", ".m4p", ".mp2",
}

# 清理文件名时，可整体删除的“空壳/纯编号”括号串（【01】、[]、() 等）
_RE_EMPTY_BRACKET = re.compile(
    r"[\[【（(]\s*[\]】）)]"                     # 空壳括号：【】、[]、()、（） 及组合
    r"|"                                        # 或
    r"[\[【（(]\s*\d{1,4}\s*[\]】）)]"           # 括号内只有数字编号：【01】、(02) 等
)

# 括号及内容删除：支持 ()（）[]【】{}｛｝，括号内不嵌套同类括号
_RE_BRACKET_CONTENT = re.compile(
    r"[\[【（(｛{][^\[\]【】（）()｛｝]*[\]】）)｛}]"
)

# 未闭合的左半括号：左括号之后直到文件末尾都没有对应的右括号（如 “(Fatik & Ark”）
_RE_HALF_BRACKET = re.compile(r"[\[【（(｛{][^\]】）)｝}]*$")

# 前导编号：匹配文件名开头的数字串（曲目序号 / 序号范围 / 3 位 BPM）。
# 数字串之间可能用 -、.、_、空格 分隔；数字串之后必须不是数字（长数字不处理）。
_RE_LEADING = re.compile(
    r"^\s*(\d{1,3})"                          # 第一组数字
    r"(?:([\-._\u2013\u2014\s]+)(\d{1,3}))?"  # 分隔符 + 可选第二组数字
    r"(?![0-9])"
)


def _is_bpm(s: str) -> bool:
    """
    判定一个数字段是否为 BPM：
    - 3 位、不以 0 开头（排除 002/003 这类前导零序号）
    - 且在合理 DJ BPM 范围内（60~250）
    满足则为 True，否则视为曲目序号。
    """
    return (
        len(s) == 3
        and s[0] != "0"
        and 60 <= int(s) <= 250
    )


def _strip_leading_track_number(stem: str) -> str:
    """
    删除文件名开头的曲目序号，同时保留 3 位 BPM。
    - 开头为 3 位 BPM（如 138 / 140 / 128）且其后为分隔或结尾：保留
    - 开头为 1~2 位数字（如 01 / 32）：曲目序号，删除
    - 开头为 3 位前导零（如 002 / 003 / 009）：曲目序号，删除
    - “序号 + 3 位 BPM”（如 004.130、03-128、008.138）：保留 BPM（130 / 128 / 138）
    - “序号 + 序号”（如 05-18、20-31）：序号范围，整体删除
    - 其余形态（如 4 位以上长数字）：原样保留
    """
    m = _RE_LEADING.match(stem)
    if not m:
        return stem
    first = m.group(1)
    second = m.group(3)
    if second is not None:
        if _is_bpm(second):
            # 序号 + BPM（004.130 → 保留 130 及后续）
            return stem[m.start(3):]
        # 序号范围（05-18 / 20-31）——整体删除
        return stem[m.end():]
    if _is_bpm(first):
        # 纯 3 位 BPM（138 / 128 等）——保留
        return stem
    # 纯序号（01 / 32 / 002 等）——删除
    return stem[m.end():]

# 行首行尾多余符号（- _ . 空格 等），以及连续重复符号
_RE_EDGE_CHARS = " -_.、，,;；:：|/\\"


# ---------------------------------------------------------------------------
# 文件收集
# ---------------------------------------------------------------------------
def is_audio_file(name: str) -> bool:
    """按扩展名判断是否为音频文件（不区分大小写）"""
    return os.path.splitext(name)[1].lower() in AUDIO_EXTS


def collect_audio_files(folder: str):
    """收集文件夹（仅当前层，不含子文件夹）内的音频文件，按文件名排序。"""
    items = []
    for name in sorted(os.listdir(folder)):
        path = os.path.join(folder, name)
        if os.path.isfile(path) and is_audio_file(name):
            items.append(name)
    return items


# ---------------------------------------------------------------------------
# 文件名清理
# ---------------------------------------------------------------------------
def _lcs(a: str, b: str) -> str:
    """两个字符串的最长公共子串"""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    best, end = 0, 0
    for i in range(1, m + 1):
        ai = a[i - 1]
        row = dp[i]
        prev = dp[i - 1]
        for j in range(1, n + 1):
            if ai == b[j - 1]:
                v = prev[j - 1] + 1
                row[j] = v
                if v > best:
                    best = v
                    end = i
            else:
                row[j] = 0
    return a[end - best:end]


def detect_common_parts(names, min_len: int = 2, min_ratio: float = 0.6):
    """
    自动检测大多数文件（默认 ≥60%，至少 2 个文件）共同包含的连续片段。

    返回按长度降序、去重后的公共子串列表。
    说明：不再要求“所有文件”共同包含——只要极少数文件没有该片段
    （例如 32/33 个文件都带【taoqu98】），公共片段依然能被检测出来。
    """
    if len(names) < 2:
        return []
    stems = [os.path.splitext(n)[0] for n in names]
    n = len(stems)
    # 采样保护：文件很多时只取前 80 个做两两组合，避免组合爆炸
    pool = stems if n <= 80 else stems[:80]
    # 收集两两最长公共子串作为候选
    cand = set()
    plen = len(pool)
    for i in range(plen):
        si = pool[i]
        for j in range(i + 1, plen):
            sub = _lcs(si, pool[j])
            if len(sub) >= min_len:
                cand.add(sub)
    if not cand:
        return []
    # 过滤：纯符号串（空格、-、_、. 等）不算
    cand = {
        c for c in cand
        if not re.fullmatch(r"[\s\-_.、，,;；:：|/\\【】\[\]()（）]*", c)
    }
    if not cand:
        return []

    # 统计每个候选在多少个文件中出现
    def _count(c):
        return sum(1 for s in stems if c in s)

    limit = max(2, int(round(n * min_ratio)))
    scored = [(c, _count(c), len(c)) for c in cand]
    ok = [x for x in scored if x[1] >= limit]
    if not ok:
        return []
    # 长度降序、频次降序
    ok.sort(key=lambda x: (-x[2], -x[1], x[0]))
    # 去重：较短的片段若已被较长的结果包含，则跳过
    result = []
    for c, freq, ln in ok:
        if any(c in r for r in result):
            continue
        result.append(c)
        if len(result) >= 3:
            break
    return result


def clean_filename(
    name: str,
    remove_parts=(),
    strip_leading_number: bool = True,
    remove_bracket_content: bool = False,
    protect_parts=(),
) -> str:
    """
    依据规则生成“新文件名”，三个步骤各自独立开关（对应处理选项第 1、3、4 项）：
      1. remove_parts  —— 清理类似项：删除指定公共片段（如【taoqu】），按长度从长到短
      2. strip_leading_number —— 清理序号：删除前导曲目序号（01、02、05-18 等），保留 3 位 BPM（138）
      3. remove_bracket_content —— 清理括号及括号内全部内容（如 (Remix)、【tag】），
         同时合并处理空壳/纯编号括号、未闭合半括号、首尾多余符号与连续空白
    扩展名保持不变。返回 '' 表示清理后文件名为空（无法使用）。

    protect_parts：需要“保护”的类似项片段（如公共片段【taoqu】）。第 3 项清理括号时
    会跳过这些片段，避免把【taoqu】这类公共标签当作普通括号误删——它们只应由
    第 4 项（清理类似项 remove_parts）删除。
    """
    stem, ext = os.path.splitext(name)
    s = stem

    # 1. 类似项（长片段先删，避免残留短片段）
    for part in sorted(set(remove_parts), key=len, reverse=True):
        if part:
            s = s.replace(part, "")

    # 2. 清理序号（保留 3 位 BPM；删除后清掉序号残留的分隔符/空白）
    if strip_leading_number:
        s = _strip_leading_track_number(s)
        s = s.strip(" -._")

    # 3. 清理括号及括号内全部内容（含空括号、多余符号、连续空白）
    if remove_bracket_content:
        # 3.0 先把需要保护的类似项替换为占位符，避免被括号清理误删
        protected = {}
        for i, part in enumerate(protect_parts):
            if part and part in s:
                ph = f"\x00PRT{i}\x00"
                s = s.replace(part, ph)
                protected[ph] = part
        s = _RE_BRACKET_CONTENT.sub("", s)
        # 未闭合的左半括号及其后全部内容（如 “(Fatik & Ark”）
        half = _RE_HALF_BRACKET.search(s)
        if half:
            s = s[:half.start()]
        # 空壳 / 纯编号括号
        s = _RE_EMPTY_BRACKET.sub("", s)
        # 首尾多余符号清理（循环处理，直到稳定）
        while True:
            ns = s.strip(_RE_EDGE_CHARS)
            if ns == s:
                break
            s = ns
        # 压缩连续空白、符号间多余空白
        s = re.sub(r"\s{2,}", " ", s)
        # 清理后可能出现的 “符号+空格+符号” 残渣：如 “ - ” 在首尾位置
        s = s.strip(_RE_EDGE_CHARS)
        # 3.9 还原被保护的类似项，并清理其前后可能残留的多余空格
        for ph, part in protected.items():
            s = s.replace(ph, part)
            s = re.sub(r"\s*" + re.escape(part) + r"\s*", part, s)

    new_name = s + ext
    return new_name if s else ""


def unique_name(folder: str, wanted: str) -> str:
    """若 wanted 与已有文件冲突，自动追加 (1)、(2)…… 生成不重名的新名。"""
    stem, ext = os.path.splitext(wanted)
    candidate = wanted
    i = 1
    while os.path.exists(os.path.join(folder, candidate)):
        candidate = f"{stem} ({i}){ext}"
        i += 1
    return candidate


# ---------------------------------------------------------------------------
# 元数据清除
# ---------------------------------------------------------------------------
def strip_metadata(path: str):
    """
    清除音频文件的标签元数据（ID3 / MP4 / FLAC / Vorbis / WAVE INFO 等）。
    返回 (ok, 说明)。mutagen 无法识别的格式返回 (False, 原因)。
    """
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return False, "缺少 mutagen 库，请先执行：pip3 install mutagen"

    ext = os.path.splitext(path)[1].lower()
    try:
        audio = MutagenFile(path)
    except Exception:
        audio = None  # 自动探测失败，转按扩展名回退

    # 回退 1：按扩展名直接构造类型
    if audio is None:
        try:
            if ext == ".mp3":
                from mutagen.id3 import ID3
                try:
                    ID3(path).delete()
                except Exception as exc:  # 无标签时抛 ID3NoHeaderError / NoID3Error
                    no_tag = (
                        "NoID3Error" in type(exc).__name__
                        or "ID3NoHeaderError" in type(exc).__name__
                    )
                    if no_tag:
                        return True, "文件本就没有标签"
                    raise
                return True, "已清除 ID3 标签"
            if ext in (".wav", ".wave"):
                from mutagen.wave import WAVE
                w = WAVE(path)
                if getattr(w, "tags", None) is None:
                    return True, "文件本就没有标签"
                w.delete()
                return True, "已清除 WAVE 标签"
            if ext == ".flac":
                from mutagen.flac import FLAC
                FLAC(path).delete()
                return True, "已清除 FLAC 标签"
            if ext in (".m4a", ".m4b", ".m4p", ".aac"):
                from mutagen.mp4 import MP4
                MP4(path).delete()
                return True, "已清除 MP4 标签"
            if ext in (".ogg", ".oga", ".opus"):
                from mutagen.oggvorbis import OggVorbis
                OggVorbis(path).delete()
                return True, "已清除 OGG 标签"
            return False, "mutagen 无法识别该文件格式，已跳过"
        except PermissionError:
            return False, "无写入权限（文件可能被锁定或只读）"
        except Exception as exc:  # noqa: BLE001
            return False, f"失败：{exc}"

    try:
        if hasattr(audio, "delete"):
            audio.delete()
            # 部分格式 delete 后需要显式保存
            if getattr(audio, "filename", None):
                try:
                    audio.save()
                except Exception:
                    pass
        else:
            return False, "该格式不支持清除标签"
        return True, "已清除标签元数据"
    except PermissionError:
        return False, "无写入权限（文件可能被锁定或只读）"
    except Exception as exc:  # noqa: BLE001
        return False, f"失败：{exc}"


# ---------------------------------------------------------------------------
# 添加封面
# ---------------------------------------------------------------------------
def add_cover(path: str, cover_path: str):
    """
    给音频文件写入专辑封面（MP3 / WAV 的 ID3 APIC、M4A 的 covr、FLAC 的 Picture）。
    返回 (ok, 说明)。封面仅支持 JPG / PNG。
    """
    try:
        ext = os.path.splitext(path)[1].lower()
        cext = os.path.splitext(cover_path)[1].lower()
        mime = None
        if cext in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif cext == ".png":
            mime = "image/png"
        if mime is None:
            return False, "封面格式仅支持 JPG / PNG"
        with open(cover_path, "rb") as _f:
            img_bytes = _f.read()

        if ext == ".mp3":
            from mutagen.id3 import ID3, APIC
            try:
                audio = ID3(path)
            except Exception:
                audio = ID3()  # 无标签时创建空 ID3（清理元数据后常见）
            audio.delall("APIC")
            audio.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=img_bytes))
            audio.save(path)
            return True, "已添加封面（MP3）"
        if ext in (".wav", ".wave"):
            # WAV 通过 RIFF 内嵌 ID3 块（id3 chunk）写入 APIC 封面
            from mutagen.wave import WAVE
            from mutagen.id3 import APIC
            audio = WAVE(path)
            if getattr(audio, "tags", None) is None:
                audio.add_tags()
            audio.tags.delall("APIC")
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=img_bytes))
            audio.save()
            return True, "已添加封面（WAV）"
        if ext in (".m4a", ".m4b", ".m4p", ".aac"):
            from mutagen.mp4 import MP4, MP4Cover
            fmt = MP4Cover.FORMAT_JPEG if mime == "image/jpeg" else MP4Cover.FORMAT_PNG
            audio = MP4(path)
            audio.tags["covr"] = [MP4Cover(img_bytes, imageformat=fmt)]
            audio.save()
            return True, "已添加封面（M4A）"
        if ext == ".flac":
            from mutagen.flac import FLAC, Picture
            pic = Picture()
            pic.type = 3
            pic.mime = mime
            pic.desc = "Cover"
            pic.data = img_bytes
            audio = FLAC(path)
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
            return True, "已添加封面（FLAC）"
        return False, "该格式暂不支持添加封面"
    except Exception as exc:  # noqa: BLE001
        return False, f"添加封面失败：{exc}"


# ---------------------------------------------------------------------------
# 预览与执行结果模型
# ---------------------------------------------------------------------------
class FileRow:
    """预览列表中的一行。"""

    __slots__ = ("name", "new_name", "checked", "status")

    def __init__(self, name, new_name="", checked=True):
        self.name = name          # 原文件名
        self.new_name = new_name  # 新文件名（'' 表示不改名）
        self.checked = checked    # 是否参与处理
        self.status = ""          # 执行结果描述


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------
class ChipList(tk.Frame):
    """
    横向排列的片段标签（chip）列表：每个片段一个标签，横向排布、自动换行，
    可看到全部内容；点选高亮，←/→ 方向键逐项移动选中。
    """

    BG = "#252526"
    CHIP_BG = "#2d2d2d"
    CHIP_FG = "#e0e0e0"
    SEL_BG = "#375f8a"
    SEL_FG = "#ffffff"

    def __init__(self, master, height=34, **kw):
        super().__init__(master, bg=self.BG,
                         highlightthickness=1, highlightbackground="#4a4a4a",
                         bd=0, **kw)
        self.configure(height=height)
        self.pack_propagate(False)  # 固定高度：内容少时也保持完整框体
        self._chips = {}        # text -> tk.Label
        self._selected = set()  # 选中的 text
        self._focus = None      # 键盘焦点 chip（text）
        self._wrap_row = 0      # 自动换行：当前行 / 当前列
        self._wrap_col = 0
        self._row_widths = {0: 0}

    # ---- 查询 ----
    def get_all(self):
        """全部片段（按添加顺序）。"""
        return list(self._chips.keys())

    def get_selected(self):
        """当前选中的片段。"""
        return [t for t in self._chips if t in self._selected]

    def size(self):
        return len(self._chips)

    # ---- 增删 ----
    def add(self, text, select=False):
        if not text or text in self._chips:
            return
        lab = tk.Label(self, text=text, bg=self.CHIP_BG, fg=self.CHIP_FG,
                       padx=8, pady=3, cursor="hand2", font=("Helvetica", 11))
        lab.bind("<Button-1>", lambda e, t=text: self._on_click(t))
        lab.bind("<Left>", lambda e, t=text: self._on_arrow(-1))
        lab.bind("<Right>", lambda e, t=text: self._on_arrow(1))
        self._chips[text] = lab
        # 放到当前行末尾；若超出可用宽度则换行
        self._place_chip(lab)
        if select:
            self._select(text, True)

    def _place_chip(self, lab):
        """把 chip 放到当前行；超宽则自动换到下一行。"""
        avail = max(self.winfo_width() - 8, 80)
        req = lab.winfo_reqwidth()
        if self._row_widths.get(self._wrap_row, 0) + req > avail and self._wrap_col > 0:
            self._wrap_row += 1
            self._wrap_col = 0
            self._row_widths[self._wrap_row] = 0
        lab.grid(row=self._wrap_row, column=self._wrap_col, padx=2, pady=2, sticky="w")
        self._row_widths[self._wrap_row] = self._row_widths.get(self._wrap_row, 0) + req
        self._wrap_col += 1

    def _relayout(self):
        """移除后重排全部 chip（自动换行重新计算）。"""
        self._wrap_row = 0
        self._wrap_col = 0
        self._row_widths = {0: 0}
        for lab in self._chips.values():
            lab.grid_remove()
        for lab in list(self._chips.values()):
            self._place_chip(lab)

    def remove(self, texts):
        for t in texts:
            lab = self._chips.pop(t, None)
            if lab:
                lab.destroy()
            self._selected.discard(t)
            if self._focus == t:
                self._focus = None
        self._relayout()

    def clear(self):
        self.remove(list(self._chips.keys()))

    # ---- 选中交互 ----
    def _select(self, text, on):
        lab = self._chips.get(text)
        if not lab:
            return
        if on:
            self._selected.add(text)
            lab.config(bg=self.SEL_BG, fg=self.SEL_FG)
        else:
            self._selected.discard(text)
            lab.config(bg=self.CHIP_BG, fg=self.CHIP_FG)

    def _on_click(self, text):
        self._focus = text
        self._select(text, text not in self._selected)

    def _on_arrow(self, direction):
        """←/→ 移动选中：-1 左 / +1 右（只选中移动到的项）。"""
        all_t = list(self._chips.keys())
        if not all_t:
            return "break"
        if self._focus is None:
            idx = 0
        else:
            idx = all_t.index(self._focus)
        ni = idx + direction
        if 0 <= ni < len(all_t):
            self._focus = all_t[ni]
            # 移动式选中：清除其它选中，只保留当前项
            for t in list(self._selected):
                self._select(t, False)
            self._select(all_t[ni], True)
        return "break"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.withdraw()  # 先隐藏窗口，避免启动时先出现在屏幕左侧再跳向中间
        root.title(APP_TITLE)
        root.geometry("780x840")
        root.minsize(700, 760)
        root.configure(bg="#1e1e1e")
        # 启动时窗口居中显示
        root.update_idletasks()
        _sw = root.winfo_screenwidth()
        _sh = root.winfo_screenheight()
        _sx = max((_sw - 780) // 2, 0)
        _sy = max((_sh - 840) // 2, 0)
        root.geometry(f"780x840+{_sx}+{_sy}")

        self.folder = tk.StringVar()
        self.clean_track = tk.BooleanVar(value=True)    # 1 清理序号
        self.clean_meta = tk.BooleanVar(value=True)     # 2 清理标签元数据
        self.clean_brackets = tk.BooleanVar(value=False) # 3 清理括号及内容（含空括号、多余符号）
        self.clean_parts = tk.BooleanVar(value=True)    # 4 清理类似项
        self.clean_cover = tk.BooleanVar(value=False)   # 添加封面
        self.manual_part = tk.StringVar()   # 手动输入：要删除的片段
        self.add_part = tk.StringVar()      # 手动输入：要增加的片段

        self.rows = []            # 当前预览行
        self.audio_files = []     # 当前文件夹音频文件
        self.detected_parts = []  # 自动检测到的公共片段
        self.add_parts = []       # 手动添加的要增加到文件名中的片段（作为后缀）
        self.cover_path = ""      # 封面图片路径
        self.running = False

        self._setup_theme()
        self._build_ui()
        root.deiconify()  # 窗口构建完成后直接以居中位置显示，无跳变
        self._log("就绪：请选择文件夹并点击“扫描文件”。")

    # ---------------- 主题 ----------------
    def _setup_theme(self):
        """配置深色主题（clam 主题 + 自定义配色，与 HELIX 系列工具一致）"""
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        BG = "#1e1e1e"
        CARD = "#252526"
        BORDER = "#3c3c3c"
        TEXT = "#e0e0e0"
        INPUT = "#2d2d2d"
        BTN = "#3c3c3c"
        BTN_HOVER = "#4c4c4c"
        ACCENT = "#375f8a"

        style.configure(".", background=BG, foreground=TEXT,
                        fieldbackground=INPUT, bordercolor=BORDER)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("Count.TLabel", background=BG, foreground="#6a9955")

        style.configure("TButton", background=BTN, foreground=TEXT,
                        bordercolor=BORDER, focusthickness=0,
                        padding=(14, 6), font=("Helvetica", 11))
        style.map("TButton",
                  background=[("active", BTN_HOVER), ("pressed", "#2c2c2c")],
                  foreground=[("active", "#ffffff")])

        style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT,
                        insertcolor=TEXT, bordercolor=BORDER, padding=5)

        style.configure("TCheckbutton", background=CARD, foreground=TEXT,
                        font=("Helvetica", 11))
        style.map("TCheckbutton", background=[("active", CARD)])

        style.configure("TLabelframe", background=CARD, bordercolor=BORDER,
                        relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=CARD, foreground="#ffffff",
                        font=("Helvetica", 11, "bold"))

        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        foreground=TEXT, rowheight=26, bordercolor=BORDER, borderwidth=0)
        style.configure("Treeview.Heading", background="#333333", foreground="#ffffff",
                        bordercolor=BORDER, font=("Helvetica", 11, "bold"), padding=5)
        style.map("Treeview",
                  background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.map("Treeview.Heading", background=[("active", "#3a3a3a")])

        style.configure("Vertical.TScrollbar", background=BTN, troughcolor=BG,
                        bordercolor=BG, arrowcolor=TEXT, relief="flat")
        style.map("Vertical.TScrollbar", background=[("active", BTN_HOVER)])

    # ---------------- UI ----------------
    def _build_ui(self):
        BG = "#1e1e1e"
        CARD = "#252526"

        # ===== 顶部栏：左侧标题 + 右侧微信 =====
        header = tk.Frame(self.root, bg=BG, height=46)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        left_wrap = tk.Frame(header, bg=BG)
        left_wrap.pack(side="left", padx=(16, 0))
        tk.Frame(left_wrap, bg="#c93838", width=3, height=20).pack(side="left", pady=13)
        tk.Label(left_wrap, text="HELIX音频清理工具", bg=BG, fg="#ffffff",
                 font=("Helvetica", 14, "bold")).pack(side="left", padx=(8, 0))

        tk.Label(header, text="制作人微信：helix_music", bg="#3a1f1f", fg="#e0a0a0",
                 font=("Helvetica", 10), padx=12, pady=5).pack(side="right", padx=16)

        # ===== 内容区 =====
        content = ttk.Frame(self.root, style="TFrame")
        content.pack(fill="both", expand=True, padx=10, pady=(4, 10))
        pad = {"padx": 2, "pady": 4}

        # 顶栏：选择文件夹
        top = ttk.Frame(content, style="TFrame")
        top.pack(fill="x", **pad)
        ttk.Button(top, text="选择文件夹…", command=self.choose_folder).pack(side="left")
        ttk.Entry(top, textvariable=self.folder).pack(side="left", fill="x", expand=True, padx=8)
        self.count_var = tk.StringVar(value="尚未扫描")
        ttk.Label(top, textvariable=self.count_var, style="Count.TLabel").pack(side="left", padx=8)

        # 处理选项
        opt = ttk.LabelFrame(content, text="处理选项", padding=8)
        opt.pack(fill="x", **pad)
        opt.columnconfigure(0, weight=1)

        ttk.Checkbutton(opt, text="清理序号（01、02、03 等曲目序号）",
                        variable=self.clean_track).grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(opt, text="清理标签元数据（封面 / 歌手 / 专辑等）",
                        variable=self.clean_meta).grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(opt, text="清理括号及括号内全部内容（如 Remix）",
                        variable=self.clean_brackets).grid(row=2, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(opt, text="清理类似项（所有文件共同包含的片段，如【taoqu】）",
                        variable=self.clean_parts).grid(row=3, column=0, sticky="w", padx=4, pady=2)

        # 手动输入（要删除的片段）：下方框对应删除的片段（自动检测 + 手动添加）
        manual = ttk.Frame(opt, style="Card.TFrame")
        manual.grid(row=4, column=0, sticky="ew", padx=4, pady=4)
        ttk.Label(manual, text="手动输入要删除的片段：", style="Card.TLabel").pack(side="left", padx=6)
        ttk.Entry(manual, textvariable=self.manual_part, width=30).pack(side="left", padx=6, pady=5)
        ttk.Button(manual, text="添加", width=5, command=self._add_manual_part).pack(side="left", padx=(0, 6), pady=5)
        ttk.Button(manual, text="取消", width=5, command=self._remove_selected_part).pack(side="left", padx=(0, 6), pady=5)

        # 删除片段列表框（自动检测的公共片段默认选中，可点击取消）
        part_frame = ttk.Frame(opt, style="Card.TFrame")
        part_frame.grid(row=5, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.parts_chips = ChipList(part_frame)
        self.parts_chips.pack(side="left", fill="x", expand=True, padx=4, pady=2)

        # 手动输入（要增加的片段）：作为后缀加到扩展名前（.mp3/.wav 之前）
        add_manual = ttk.Frame(opt, style="Card.TFrame")
        add_manual.grid(row=6, column=0, sticky="ew", padx=4, pady=4)
        ttk.Label(add_manual, text="手动输入要增加的片段：", style="Card.TLabel").pack(side="left", padx=6)
        ttk.Entry(add_manual, textvariable=self.add_part, width=30).pack(side="left", padx=6, pady=5)
        ttk.Button(add_manual, text="添加", width=5, command=self._add_manual_add_part).pack(side="left", padx=(0, 6), pady=5)
        ttk.Button(add_manual, text="取消", width=5, command=self._remove_selected_add_part).pack(side="left", padx=(0, 6), pady=5)

        # 增加片段列表框
        add_list_row = ttk.Frame(opt, style="Card.TFrame")
        add_list_row.grid(row=7, column=0, sticky="ew", padx=4, pady=(0, 4))
        self.add_chips = ChipList(add_list_row)
        self.add_chips.pack(side="left", fill="x", expand=True, padx=4, pady=2)

        # 添加封面
        cover_row = ttk.Frame(opt, style="Card.TFrame")
        cover_row.grid(row=8, column=0, sticky="ew", padx=4, pady=4)
        ttk.Checkbutton(cover_row, text="添加封面（给音频文件写入专辑封面）",
                        variable=self.clean_cover).pack(side="left", padx=6)
        ttk.Button(cover_row, text="选择封面图片…", command=self._choose_cover).pack(side="left", padx=4)
        self.cover_label = ttk.Label(cover_row, text="未选择封面", style="Card.TLabel")
        self.cover_label.pack(side="left", padx=6)

        # 操作按钮
        btns = ttk.Frame(content, style="TFrame")
        btns.pack(fill="x", **pad)
        self.preview_btn = ttk.Button(btns, text="预览改动", command=self.preview)
        self.preview_btn.pack(side="left")
        self.run_btn = ttk.Button(btns, text="开始处理", command=self.run)
        self.run_btn.pack(side="left", padx=8)

        # 进度条（开始处理后显示进度，与进度文字并排一行，紧凑）
        prog_frame = ttk.Frame(content, style="TFrame")
        prog_frame.pack(fill="x", **pad)
        self.progress = ttk.Progressbar(prog_frame, orient="horizontal",
                                        mode="determinate", maximum=100)
        self.progress.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.progress_var = tk.StringVar(value="")
        ttk.Label(prog_frame, textvariable=self.progress_var,
                  style="Count.TLabel").pack(side="left")

        # 预览表格（点“预览改动”后显示：分左右区、有颜色）
        list_frame = ttk.LabelFrame(content, text="预览", padding=4)
        list_frame.pack(fill="both", expand=True, **pad)
        cols = ("old", "new")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=7)
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.column("old", width=280, stretch=True)
        self.tree.column("new", width=280, stretch=True)
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("changed", foreground="#4ec9b0")
        self.tree.tag_configure("skipped", foreground="#888888")

    # ---------------- 动作 ----------------
    def choose_folder(self):
        folder = filedialog.askdirectory(title="选择包含音频文件的文件夹")
        if folder:
            self.folder.set(folder)
            self.scan()

    def scan(self):
        folder = self.folder.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning(APP_TITLE, "请先选择一个有效文件夹。")
            return
        self.audio_files = collect_audio_files(folder)
        self.count_var.set(f"找到 {len(self.audio_files)} 个音频文件")
        self.rows = []
        self.tree.delete(*self.tree.get_children())
        self._clear_log()
        # 自动检测公共片段
        self.detected_parts = detect_common_parts(self.audio_files)
        self.parts_chips.clear()
        for p in self.detected_parts:
            self.parts_chips.add(p, select=True)  # 默认选中，用户可点击取消
        if self.detected_parts:
            self._log(
                f"已自动检测到公共片段：{'、'.join(repr(p) for p in self.detected_parts)}"
            )
        else:
            self._log("未检测到所有文件共同包含的类似项（也可手动输入片段）。")
        if not self.audio_files:
            self._log("该文件夹下没有发现音频文件（当前层，不含子文件夹）。")

    def _selected_parts(self):
        """当前选中的公共片段 + 手动输入的片段（去重）"""
        parts = self.parts_chips.get_selected()
        manual = self.manual_part.get().strip()
        if manual:
            parts.append(manual)
        seen, out = set(), []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _choose_cover(self):
        """选择封面图片（JPG / PNG）。"""
        path = filedialog.askopenfilename(
            title="选择封面图片（JPG / PNG）",
            filetypes=[("图片", "*.jpg *.jpeg *.png"), ("所有文件", "*.*")],
        )
        if path:
            self.cover_path = path
            self.cover_label.config(text=os.path.basename(path))
            self._log(f"已选择封面图片：{path}")

    def _remove_selected_part(self):
        """移除删除列表中选中的片段（点击选中后点“取消”）"""
        selected = self.parts_chips.get_selected()
        if not selected:
            self._log("请先点击选中要移除的片段（再点「取消」）")
            return
        for item in selected:
            if item in self.detected_parts:
                self.detected_parts.remove(item)
        self.parts_chips.remove(selected)
        self._log(f"已从删除列表中移除：{'、'.join(repr(r) for r in selected)}")

    def _add_manual_part(self):
        """把输入框中的片段加入删除列表（支持用 ；/ 分隔多个片段，自动去重）。"""
        raw = self.manual_part.get().strip()
        if not raw:
            return
        items_list = self.parts_chips.get_all()
        added, dup = [], []
        for p in [x.strip() for x in re.split(r"[；;/，,、]", raw) if x.strip()]:
            if p not in items_list:
                self.parts_chips.add(p, select=True)  # 手动添加的删除片段默认选中
                items_list.append(p)
                added.append(p)
            else:
                dup.append(p)
        if added:
            self._log(f"已添加删除片段：{'、'.join(repr(a) for a in added)}")
        if dup:
            self._log(f"已在列表中，跳过：{'、'.join(repr(d) for d in dup)}")
        self.manual_part.set("")

    # ---------- 手动输入：要增加的片段 ----------
    def _add_manual_add_part(self):
        """把输入框中的片段加入“要增加”列表（支持用 ；/ 分隔多个片段，自动去重）。"""
        raw = self.add_part.get().strip()
        if not raw:
            return
        items = [p.strip() for p in re.split(r"[；;/，,、]", raw) if p.strip()]
        added, dup = [], []
        for p in items:
            if p not in self.add_parts:
                self.add_parts.append(p)
                added.append(p)
            else:
                dup.append(p)
        self._refresh_add_list()
        if added:
            self._log(f"已添加要增加的片段：{'、'.join(repr(a) for a in added)}（将作为文件名后缀）")
        if dup:
            self._log(f"已在列表中，跳过：{'、'.join(repr(d) for d in dup)}")
        self.add_part.set("")

    def _remove_selected_add_part(self):
        """移除“要增加”列表中选中的片段。"""
        selected = self.add_chips.get_selected()
        if not selected:
            self._log("请先点击选中要移除的片段（再点「取消」）")
            return
        self.add_parts = [p for p in self.add_parts if p not in selected]
        self.add_chips.remove(selected)
        self._log(f"已移除要增加的片段：{'、'.join(repr(r) for r in selected)}")

    def _refresh_add_list(self):
        """刷新“要增加片段”横向标签显示。"""
        self.add_chips.clear()
        for p in self.add_parts:
            self.add_chips.add(p)

    def _add_parts_suffix(self, new_name):
        """把要增加的片段拼接到文件名末尾（后缀，即扩展名前，如 .mp3 / .wav 之前）。"""
        if not self.add_parts:
            return new_name
        stem, ext = os.path.splitext(new_name)
        return stem + "".join(self.add_parts) + ext

    # ---------------- 预览 ----------------
    def preview(self):
        if not self.audio_files:
            messagebox.showwarning(APP_TITLE, "请先选择文件夹并扫描文件。")
            return
        folder = self.folder.get().strip()
        parts = self._selected_parts() if self.clean_parts.get() else []
        # 需要保护的类似项（自动检测 + 手动添加的全部片段），第 3 项清理括号时跳过，避免误删
        protect = self.parts_chips.get_all()
        manual = self.manual_part.get().strip()
        if manual:
            protect.append(manual)
        protect = [p for p in protect if p]
        # 重新计算全部新文件名
        plan = []
        used = set(self.audio_files)
        for name in self.audio_files:
            new_name = name
            if (self.clean_track.get() or self.clean_brackets.get()
                    or self.clean_parts.get() or self.add_parts):
                raw = clean_filename(
                    name,
                    remove_parts=parts,
                    strip_leading_number=self.clean_track.get(),
                    remove_bracket_content=self.clean_brackets.get(),
                    protect_parts=protect,
                )
                if raw:
                    # 追加手动输入的要增加的片段（作为后缀，扩展名前）
                    raw = self._add_parts_suffix(raw)
                    if raw == name:
                        # 文件本身无需改名，跳过防重名检测（避免把自己当冲突误加 (1)）
                        new_name = name
                    else:
                        new_name = unique_name(folder, raw)
                        # 防止两个文件算出的新名相同
                        base = new_name
                        k = 1
                        while new_name in used and new_name != name:
                            stem, ext = os.path.splitext(base)
                            new_name = f"{stem} ({k}){ext}"
                            k += 1
            used.add(new_name)
            plan.append(FileRow(name, new_name, True))

        self.rows = plan
        self._render_rows()
        changed_n = sum(1 for r in plan if r.new_name != r.name)
        self._log(f"已生成预览：共 {len(plan)} 个文件，其中 {changed_n} 个将被改名。确认后点“开始处理”。")

    def _render_rows(self):
        """把预览计划渲染到预览表格（原文件名 | 新文件名，改动的标绿）。"""
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            changed = bool(row.new_name) and row.new_name != row.name
            tags = ("changed",) if changed else ("skipped",)
            self.tree.insert(
                "", "end", iid=str(i),
                values=(row.name, row.new_name),
                tags=tags,
            )

    # ---------------- 执行 ----------------
    def run(self):
        if self.running:
            return
        if not self.rows:
            self.preview()  # 自动生成计划并写入日志（原“预览改动”按钮已并入）
        folder = self.folder.get().strip()
        do_meta = self.clean_meta.get()
        do_name = (self.clean_track.get() or self.clean_brackets.get()
                   or self.clean_parts.get() or bool(self.add_parts))
        do_cover = self.clean_cover.get() and bool(self.cover_path)
        if not do_meta and not do_name and not do_cover:
            messagebox.showwarning(APP_TITLE, "请至少勾选一项处理选项。")
            return

        pending = [r for r in self.rows if r.checked]
        if not pending:
            messagebox.showwarning(APP_TITLE, "没有可处理的文件。")
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.preview_btn.config(state="disabled")
        self._clear_log()
        self._log("开始处理……")
        self.progress["maximum"] = max(len(pending), 1)
        self.progress["value"] = 0
        self.progress_var.set(f"处理进度：0 / {len(pending)}")

        def worker():
            try:
                self._process(pending, folder, do_meta, do_name, do_cover)
            finally:
                self.root.after(0, self._finish_run)

        threading.Thread(target=worker, daemon=True).start()

    def _process(self, pending, folder, do_meta, do_name, do_cover):
        ok = skip = fail = 0
        total = max(len(pending), 1)
        for idx, row in enumerate(pending, start=1):
            path = os.path.join(folder, row.name)
            msgs = []

            # 1) 清除元数据
            if do_meta:
                meta_ok, meta_msg = strip_metadata(path)
                if meta_ok:
                    ok += 1
                    msgs.append(meta_msg)
                else:
                    fail += 1
                    msgs.append(meta_msg)

            # 2) 改名
            if do_name and row.new_name and row.new_name != row.name:
                new_path = os.path.join(folder, row.new_name)
                try:
                    if os.path.exists(new_path):
                        raise OSError(f"目标文件已存在：{row.new_name}")
                    os.rename(path, new_path)
                    msgs.append(f"已重命名 → {row.new_name}")
                    row.name = row.new_name  # 改名成功后同步
                except Exception as exc:  # noqa: BLE001
                    fail += 1
                    msgs.append(f"重命名失败：{exc}")

            # 3) 添加封面（改名后执行，写入最新文件名）
            if do_cover:
                cover_ok, cover_msg = add_cover(os.path.join(folder, row.name), self.cover_path)
                if cover_ok:
                    ok += 1
                    msgs.append(cover_msg)
                else:
                    fail += 1
                    msgs.append(cover_msg)

            row.status = "；".join(msgs) if msgs else "未做任何改动"
            # 进度更新
            self.root.after(0, self._update_progress, idx, total)

        self.root.after(0, self._log,
                        f"处理完成：成功 {ok} 项，失败 {fail} 项，跳过 {skip} 项。")

    def _update_progress(self, done, total):
        self.progress["value"] = done
        self.progress_var.set(f"处理进度：{done} / {total}")

    def _finish_run(self):
        self.running = False
        self.run_btn.config(state="normal")
        self.preview_btn.config(state="normal")
        # 改名后刷新文件夹内文件列表，避免重复处理旧名
        folder = self.folder.get().strip()
        if folder and os.path.isdir(folder):
            self.audio_files = collect_audio_files(folder)
            self.count_var.set(f"找到 {len(self.audio_files)} 个音频文件")
            self.rows = []
            self.tree.delete(*self.tree.get_children())
            self._log("已刷新文件夹内文件列表。")

    # ---------------- 状态提示 ----------------
    def _clear_log(self):
        try:
            self.root.after(0, lambda: self.progress_var.set(""))
        except Exception:
            pass

    def _log(self, msg):
        """在进度条旁的状态文字中显示一条提示（不再使用独立日志区）。"""
        try:
            self.root.after(0, lambda: self.progress_var.set(msg))
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 授权激活窗口
# ---------------------------------------------------------------------------
def launch_license_window(root, machine_code):
    """未授权/授权过期时弹出的激活窗口：显示机器码、粘贴授权凭证。"""
    license_win = tk.Toplevel(root)
    license_win.title("软件授权激活")
    license_win.geometry("560x380")
    license_win.configure(bg="#1e1e1e")
    try:
        license_win.attributes('-topmost', True)
    except Exception:
        pass

    def copy_machine_code():
        license_win.clipboard_clear()
        license_win.clipboard_append(machine_code)
        messagebox.showinfo("复制成功", "机器码已复制到剪贴板！")

    tk.Label(license_win, text="请输入授权凭证", fg="#E0E0E0", bg="#1e1e1e",
             font=("Helvetica", 12, "bold")).pack(pady=15)
    tk.Label(license_win, text=f"本机机器码: {machine_code}", fg="#57B78A", bg="#1e1e1e",
             font=("Helvetica", 9), wraplength=520).pack(pady=4)
    tk.Label(license_win, text="复制机器码发给管理员获取授权凭证",
             fg="#D9534F", bg="#1e1e1e", font=("Helvetica", 9)).pack(pady=4)
    tk.Button(license_win, text="一键复制机器码", command=copy_machine_code,
              bg="#3c3c3c", fg="#e0e0e0", activebackground="#4c4c4c",
              activeforeground="#ffffff").pack(pady=6)
    entry_var = tk.StringVar()
    entry = tk.Entry(license_win, textvariable=entry_var, width=62, justify="center",
                     font=("Helvetica", 9), bg="#2d2d2d", fg="#e0e0e0",
                     insertbackground="#e0e0e0")
    entry.pack(pady=12)
    entry.focus()

    def close_without_activate():
        license_win.destroy()
        root.destroy()

    license_win.protocol("WM_DELETE_WINDOW", close_without_activate)

    def do_activate():
        user_token = entry_var.get().strip()
        ok_token, msg_token, exp_token = verify_license_token(machine_code, user_token)
        now_t = time.time()
        if ok_token and now_t > exp_token:
            exp_day = datetime.fromtimestamp(exp_token).strftime("%Y-%m-%d")
            messagebox.showerror("激活失败", f"该授权已于 {exp_day} 到期，无法激活")
            return
        if not ok_token:
            messagebox.showerror("激活失败", msg_token)
            return
        if sys.platform == "win32" and not is_admin():
            messagebox.showerror("权限不足", "⚠️Windows激活请右键【以管理员身份运行软件】！")
            return
        try:
            os.makedirs(LIC_FOLDER, exist_ok=True)
            with open(LICENSE_SAVE_PATH, "w", encoding="utf-8") as f:
                f.write(user_token)
            if not os.path.isfile(LICENSE_SAVE_PATH):
                messagebox.showerror("保存失败", "写入完成，但磁盘找不到授权文件！")
                return
        except Exception as e:
            messagebox.showerror("授权写入异常", f"保存授权文件失败:\n{str(e)}")
            return
        messagebox.showinfo("激活成功", f"授权已持久化保存\n路径:{LICENSE_SAVE_PATH}")
        license_win.destroy()
        App(root)
        root.mainloop()

    activate_btn = tk.Button(license_win, text="激活", command=do_activate,
                             bg="#3c3c3c", fg="#e0e0e0", activebackground="#4c4c4c",
                             activeforeground="#ffffff", width=16)
    activate_btn.pack(pady=8)
    entry.bind("<Return>", lambda _e: do_activate())


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    ok, msg, expire_ts = check_license()
    machine_code = get_machine_code()
    now_ts = time.time()
    if ok and now_ts > expire_ts:
        expire_day = datetime.fromtimestamp(expire_ts).strftime("%Y-%m-%d")
        messagebox.showwarning(APP_TITLE, f"授权已于 {expire_day} 到期，请粘贴新的授权凭证继续使用")
        ok = False
    if not ok:
        launch_license_window(root, machine_code)
    else:
        App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
