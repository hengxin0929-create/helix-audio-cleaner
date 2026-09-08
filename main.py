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
import threading
import traceback
from collections import OrderedDict

import tkinter as tk
from tkinter import filedialog, messagebox
import tkinter.ttk as ttk

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
APP_TITLE = "HELIX音频清理工具"

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

# 前导编号：匹配开头的曲目序号（1~2 位），其后可能跟分隔符 + 第二组数字。
# 第二组数字若为 3 位则视为 BPM（如 03-138 中的 138），予以保留；
# 否则视为曲目序号范围（如 05-18、20-31），整体删除。
_RE_LEADING_TRACK = re.compile(
    r"^(?P<num>\d{1,2})"        # 曲目序号
    r"(?P<sep>[-_.\s]+)?"       # 分隔符
    r"(?P<rest>\d{1,4})?"       # 可选第二组数字（BPM 或序号范围）
    r"(?P<tail>[-_.\s]*)"       # 尾部多余符号
)


def _strip_leading_track_number(stem: str) -> str:
    """
    删除文件名开头的曲目序号。
    - 序号后紧跟 3 位数字时，视为 BPM，保留 BPM 及其后内容（如 03-138 → 138）
    - 序号后为 1~2 位数字时，视为序号范围，整体删除（如 05-18 → 删除）
    - 纯序号直接删除（如 01、10、32 → 删除）
    """
    m = _RE_LEADING_TRACK.match(stem)
    if not m or not m.group("num"):
        return stem
    rest = m.group("rest")
    if rest and len(rest) == 3:
        # 保留 BPM：从 BPM 数字起始位置截取，保留其后原有的空格/符号
        return stem[m.start("rest"):]
    # 删除序号（含序号范围与尾部符号）
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


def detect_common_parts(names, min_len: int = 2):
    """
    自动检测所有文件名（不含扩展名）共同包含的连续片段。
    返回按长度降序、去重后的公共子串列表。
    """
    if len(names) < 2:
        return []
    stems = [os.path.splitext(n)[0] for n in names]
    common = stems[0]
    for s in stems[1:]:
        common = _lcs(common, s)
        if not common or len(common) < min_len:
            return []
    # 过滤：纯符号串（空格、-、_、.）不算
    if re.fullmatch(r"[\s\-_.、，,;；:：|/\\【】\[\]()（）]*", common):
        return []
    return [common]


def clean_filename(
    name: str,
    remove_parts=(),
    strip_leading_number: bool = True,
    remove_bracket_content: bool = False,
) -> str:
    """
    依据规则生成“新文件名”：
      1. 删除指定公共片段（如【taoqu】），按长度从长到短删除
      2. 删除前导编号（01、02、03-138 等，保留 3 位 BPM）
      3. （可选）删除括号及括号内全部内容（如 (Remix)、【tag】、（混音版））
      4. 删除空壳/纯编号括号（[]、【】、(01) 等）
      5. 清理开头/结尾的多余符号与连续空白
    扩展名保持不变。返回 '' 表示清理后文件名为空（无法使用）。
    """
    stem, ext = os.path.splitext(name)
    s = stem

    # 1. 公共片段（长片段先删，避免残留短片段）
    for part in sorted(set(remove_parts), key=len, reverse=True):
        if part:
            s = s.replace(part, "")

    # 2. 前导曲目序号（保留 3 位 BPM）
    if strip_leading_number:
        s = _strip_leading_track_number(s)

    # 3. 删除括号及括号内内容
    if remove_bracket_content:
        s = _RE_BRACKET_CONTENT.sub("", s)

    # 4. 空壳 / 纯编号括号
    s = _RE_EMPTY_BRACKET.sub("", s)

    # 4. 首尾多余符号清理（循环处理，直到稳定）
    while True:
        ns = s.strip(_RE_EDGE_CHARS)
        if ns == s:
            break
        s = ns

    # 5. 压缩连续空白、符号间多余空白
    s = re.sub(r"\s{2,}", " ", s)
    # 清理后可能出现的 “符号+空格+符号” 残渣：如 “ - ” 在首尾位置
    s = s.strip(_RE_EDGE_CHARS)

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
class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("960x680")
        root.minsize(780, 560)
        root.configure(bg="#1e1e1e")

        self.folder = tk.StringVar()
        self.clean_meta = tk.BooleanVar(value=True)
        self.clean_name = tk.BooleanVar(value=True)
        self.clean_brackets = tk.BooleanVar(value=False)
        self.manual_part = tk.StringVar()

        self.rows = []            # 当前预览行
        self.audio_files = []     # 当前文件夹音频文件
        self.detected_parts = []  # 自动检测到的公共片段
        self.running = False

        self._setup_theme()
        self._build_ui()
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

        ttk.Checkbutton(opt, text="清除音频文件属性（删除标签元数据：标题 / 歌手 / 专辑等）",
                        variable=self.clean_meta).grid(row=0, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(opt, text="清理文件名（去除编号、空括号与首尾多余符号）",
                        variable=self.clean_name).grid(row=1, column=0, sticky="w", padx=4, pady=3)
        ttk.Checkbutton(opt, text="清除括号及括号内全部内容（如 (Remix)、【tag】）",
                        variable=self.clean_brackets).grid(row=2, column=0, sticky="w", padx=4, pady=3)

        # 公共片段区
        part_frame = ttk.Frame(opt, style="Card.TFrame")
        part_frame.grid(row=3, column=0, sticky="ew", padx=4, pady=4)
        ttk.Label(part_frame, text="类似项（所有文件共同包含的片段，如【taoqu】）：",
                  style="Card.TLabel").pack(anchor="w", padx=6, pady=(5, 2))
        list_row = ttk.Frame(part_frame, style="Card.TFrame")
        list_row.pack(fill="x", padx=6, pady=(0, 5))
        self.parts_list = tk.Listbox(list_row, height=3, selectmode="multiple", exportselection=False,
                                      bg="#2d2d2d", fg="#e0e0e0", selectbackground="#375f8a",
                                      selectforeground="#ffffff", highlightthickness=0, borderwidth=0,
                                      activestyle="none")
        self.parts_list.pack(side="left", fill="x", expand=True)
        self.parts_list.bind("<<ListboxSelect>>", self._on_parts_select)

        # 手动输入
        manual = ttk.Frame(opt, style="Card.TFrame")
        manual.grid(row=4, column=0, sticky="w", padx=4, pady=4)
        ttk.Label(manual, text="手动输入要删除的片段：", style="Card.TLabel").pack(side="left", padx=6)
        ttk.Entry(manual, textvariable=self.manual_part, width=30).pack(side="left", padx=6, pady=5)
        ttk.Button(manual, text="添加", command=self._add_manual_part).pack(side="left", padx=(0, 6), pady=5)
        ttk.Button(manual, text="取消", command=self._remove_selected_part).pack(side="left", padx=(0, 6), pady=5)

        # 操作按钮
        btns = ttk.Frame(content, style="TFrame")
        btns.pack(fill="x", **pad)
        self.preview_btn = ttk.Button(btns, text="预览改动", command=self.preview)
        self.preview_btn.pack(side="left")
        self.run_btn = ttk.Button(btns, text="开始处理", command=self.run)
        self.run_btn.pack(side="left", padx=8)

        # 预览列表
        list_frame = ttk.LabelFrame(content, text="预览（点击行首可勾选/取消）", padding=4)
        list_frame.pack(fill="both", expand=True, **pad)
        cols = ("checked", "old", "new")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=10)
        self.tree.heading("checked", text="处理")
        self.tree.heading("old", text="原文件名")
        self.tree.heading("new", text="新文件名")
        self.tree.column("checked", width=60, anchor="center", stretch=False)
        self.tree.column("old", width=380)
        self.tree.column("new", width=380)
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("changed", foreground="#4ec9b0")
        self.tree.tag_configure("skipped", foreground="#666666")
        self.tree.bind("<Button-1>", self._on_tree_click)

        # 日志区
        log_frame = ttk.LabelFrame(content, text="日志", padding=4)
        log_frame.pack(fill="x", **pad)
        self.log_text = tk.Text(log_frame, height=7, state="disabled", wrap="word",
                                 bg="#1a1a1a", fg="#d4d4d4", insertbackground="#e0e0e0",
                                 borderwidth=0, highlightthickness=0)
        log_sb = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_sb.pack(side="right", fill="y")

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
        # 自动检测公共片段
        self.detected_parts = detect_common_parts(self.audio_files)
        self.parts_list.delete(0, "end")
        for i, p in enumerate(self.detected_parts):
            self.parts_list.insert("end", p)
            self.parts_list.selection_set(i)  # 默认选中，用户可取消
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
        parts = [self.parts_list.get(i) for i in self.parts_list.curselection()]
        manual = self.manual_part.get().strip()
        if manual:
            parts.append(manual)
        seen, out = set(), []
        for p in parts:
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _on_parts_select(self, _event=None):
        pass

    def _remove_selected_part(self):
        """从类似项列表中删除选中的项（选中后点“取消”）"""
        selected = list(self.parts_list.curselection())
        if not selected:
            self._log("请先在类似项列表中选中要移除的片段")
            return
        removed = []
        for i in sorted(selected, reverse=True):
            item = self.parts_list.get(i)
            self.parts_list.delete(i)
            if item in self.detected_parts:
                self.detected_parts.remove(item)
            removed.append(item)
        self._log(f"已从删除列表中移除：{'、'.join(repr(r) for r in removed)}")

    def _add_manual_part(self):
        text = self.manual_part.get().strip()
        if not text:
            return
        items = list(self.parts_list.get(0, "end"))
        if text not in items:
            self.parts_list.insert("end", text)
            self.parts_list.selection_set("end")
        else:
            # 已存在则直接选中它
            self.parts_list.selection_set(items.index(text))
        self._log(f"已添加手动片段：{text!r}")

    # ---------------- 预览 ----------------
    def preview(self):
        if not self.audio_files:
            messagebox.showwarning(APP_TITLE, "请先选择文件夹并扫描文件。")
            return
        folder = self.folder.get().strip()
        parts = self._selected_parts()
        strip_num = True
        # 重新计算全部新文件名
        plan = []
        used = set(self.audio_files)
        for name in self.audio_files:
            new_name = name
            if self.clean_name.get():
                raw = clean_filename(
                    name,
                    remove_parts=parts,
                    strip_leading_number=strip_num,
                    remove_bracket_content=self.clean_brackets.get(),
                )
                if raw:
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
        self._log("已生成预览。请核对新文件名，点击行可取消个别文件；确认后点“开始处理”。")

    def _render_rows(self):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            checked = "✔" if row.checked else "—"
            changed = bool(row.new_name) and row.new_name != row.name
            tags = ()
            if not row.checked:
                tags = ("skipped",)
            elif changed:
                tags = ("changed",)
            self.tree.insert(
                "", "end", iid=str(i),
                values=(checked, row.name, row.new_name),
                tags=tags,
            )

    def _on_tree_click(self, event):
        """点击行首列切换勾选状态"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        col = self.tree.identify_column(event.x)
        if col != "#1":
            return
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        idx = int(iid)
        self.rows[idx].checked = not self.rows[idx].checked
        self._render_rows()

    # ---------------- 执行 ----------------
    def run(self):
        if self.running:
            return
        if not self.rows:
            messagebox.showwarning(APP_TITLE, "请先点击“预览改动”。")
            return
        folder = self.folder.get().strip()
        do_meta = self.clean_meta.get()
        do_name = self.clean_name.get()
        if not do_meta and not do_name:
            messagebox.showwarning(APP_TITLE, "请至少勾选一项处理选项。")
            return

        pending = [r for r in self.rows if r.checked]
        if not pending:
            messagebox.showwarning(APP_TITLE, "没有勾选任何文件。")
            return

        self.running = True
        self.run_btn.config(state="disabled")
        self.preview_btn.config(state="disabled")

        def worker():
            try:
                self._process(pending, folder, do_meta, do_name)
            finally:
                self.root.after(0, self._finish_run)

        threading.Thread(target=worker, daemon=True).start()

    def _process(self, pending, folder, do_meta, do_name):
        ok = skip = fail = 0
        for row in pending:
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

            row.status = "；".join(msgs) if msgs else "未做任何改动"
            self.root.after(0, self._update_row_log, row)

        self.root.after(0, self._log,
                        f"处理完成：成功 {ok} 项，失败 {fail} 项，跳过 {skip} 项。")

    def _update_row_log(self, row):
        self._log(f"[{row.name}] {row.status}")

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

    # ---------------- 日志 ----------------
    def _log(self, msg):
        def _write():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        try:
            self.root.after(0, _write)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
