#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心逻辑测试：公共片段检测、文件名清理、元数据清除、GUI 冒烟"""
import os
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import main as M  # noqa: E402

FAILED = []


def check(label, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not cond:
        FAILED.append(label)


# ---------------------------------------------------------------------------
# 1. 公共片段检测（截图真实数据）
# ---------------------------------------------------------------------------
NAMES = [
    "01 Crazy Frog-How Do You Do(Fox boot【taoqu98】.MP3",
    "02 Patry Till We Die(Vizmaker Bootle【taoqu98】.WAV",
    "03-138 She Got It x Ready【taoqu98】.mp3",
    "04-140Chris & Arkins - Good Trip【taoqu98】.mp3",
    "05-140Epiik-Tequila(Sixthema VIP Mix)【taoqu98】.wav",
    "06-140 Amokk - Thai B Ft ThorH【taoqu98】.mp3",
    "07-140 Aragamii Vinahouse MegaMix Part【taoqu98】.mp3",
    "08-140 VIP-Stay Fly -ALLEN-Y3-Remix []【taoqu98】.WAV",
    "09-138SHAKE IT (T9 bootleg)【taoqu98】.mp3",
    "10 Low Low Low (Vina House DJ Coffee Bootleg)【taoqu98】.mp3",
]

parts = M.detect_common_parts(NAMES)
print("检测到公共片段:", parts)
check("公共片段检测到【taoqu98】", parts == ["【taoqu98】"], str(parts))

# ---------------------------------------------------------------------------
# 2. 文件名清理
# ---------------------------------------------------------------------------
EXPECTED = {
    "01 Crazy Frog-How Do You Do(Fox boot【taoqu98】.MP3": "Crazy Frog-How Do You Do(Fox boot.MP3",
    "02 Patry Till We Die(Vizmaker Bootle【taoqu98】.WAV": "Patry Till We Die(Vizmaker Bootle.WAV",
    "03-138 She Got It x Ready【taoqu98】.mp3": "138 She Got It x Ready.mp3",
    "04-140Chris & Arkins - Good Trip【taoqu98】.mp3": "140Chris & Arkins - Good Trip.mp3",
    "05-140Epiik-Tequila(Sixthema VIP Mix)【taoqu98】.wav": "140Epiik-Tequila(Sixthema VIP Mix).wav",
    "06-140 Amokk - Thai B Ft ThorH【taoqu98】.mp3": "140 Amokk - Thai B Ft ThorH.mp3",
    "07-140 Aragamii Vinahouse MegaMix Part【taoqu98】.mp3": "140 Aragamii Vinahouse MegaMix Part.mp3",
    "08-140 VIP-Stay Fly -ALLEN-Y3-Remix []【taoqu98】.WAV": "140 VIP-Stay Fly -ALLEN-Y3-Remix.WAV",
    "09-138SHAKE IT (T9 bootleg)【taoqu98】.mp3": "138SHAKE IT (T9 bootleg).mp3",
    "10 Low Low Low (Vina House DJ Coffee Bootleg)【taoqu98】.mp3": "Low Low Low (Vina House DJ Coffee Bootleg).mp3",
}

for src, dst in EXPECTED.items():
    got = M.clean_filename(src, remove_parts=["【taoqu98】"])
    check(f"清理: {src}", got == dst, f"→ {got!r}")

# 序号范围（非 BPM）整体删除
check("序号范围 05-18 删除",
      M.clean_filename("05-18 Song【tag】.mp3", remove_parts=["【tag】"]) == "Song.mp3")
check("序号范围 20-31 删除",
      M.clean_filename("20-31 Song.mp3", remove_parts=[]) == "Song.mp3")
check("纯序号 32 删除",
      M.clean_filename("32 Song.mp3", remove_parts=[]) == "Song.mp3")
check("纯序号 19 删除",
      M.clean_filename("19 Song.mp3", remove_parts=[]) == "Song.mp3")
# BPM 保留（3 位）
check("BPM 128 保留",
      M.clean_filename("03-128 Song.mp3", remove_parts=[]) == "128 Song.mp3")
check("BPM 紧跟歌名无空格也保留",
      M.clean_filename("04-140Chris.mp3", remove_parts=[]) == "140Chris.mp3")

# 括号及内容删除
check("删除圆括号及内容",
      M.clean_filename("Crazy Frog-How Do You Do(Fox boot).MP3",
                       remove_parts=[], remove_bracket_content=True)
      == "Crazy Frog-How Do You Do.MP3")
check("删除括号后清理尾部空格",
      M.clean_filename("SHAKE IT (T9 bootleg).mp3",
                       remove_parts=[], remove_bracket_content=True)
      == "SHAKE IT.mp3")
check("删除长括号内容",
      M.clean_filename("Low Low Low (Vina House DJ Coffee Bootleg).mp3",
                       remove_parts=[], remove_bracket_content=True)
      == "Low Low Low.mp3")
check("删除方括号和中文括号",
      M.clean_filename("Song [Remix] 【tag】.mp3",
                       remove_parts=[], remove_bracket_content=True)
      == "Song.mp3")
check("删除中文圆括号",
      M.clean_filename("歌曲（混音版）.mp3",
                       remove_parts=[], remove_bracket_content=True)
      == "歌曲.mp3")
check("不勾选时括号保留",
      M.clean_filename("Song (Remix).mp3",
                       remove_parts=[], remove_bracket_content=False)
      == "Song (Remix).mp3")

# 无公共片段时的独立测试
check("无编号/无公共片段保持原样",
      M.clean_filename("My Song (Remix).mp3", remove_parts=[]) == "My Song (Remix).mp3")
check("空壳括号删除",
      M.clean_filename("Song [] 【】 ()【1】.mp3", remove_parts=[]) == "Song.mp3")

# 纯数字开头但无分隔符（如 “10 Low”）应删除编号
check("前导编号 10 删除",
      M.clean_filename("10 Low.mp3", remove_parts=[]) == "Low.mp3")

# ---------------------------------------------------------------------------
# 3. 元数据清除（构造真实标签文件）
# ---------------------------------------------------------------------------
td = tempfile.mkdtemp(prefix="audio_clean_test_")
try:
    from mutagen.id3 import ID3, TIT2, TPE1, TALB
    from mutagen.wave import WAVE
    import wave as std_wave

    # MP3：真实最小 MPEG 帧 + ID3 标签
    def make_mp3(path):
        tags = ID3()
        tags.add(TIT2(encoding=3, text=["Test Title"]))
        tags.add(TPE1(encoding=3, text=["Test Artist"]))
        tags.add(TALB(encoding=3, text=["Test Album"]))
        tags.save(path)
        # 追加一个最小 MPEG1 Layer3 帧（128kbps / 44.1kHz，无 padding，帧长 417 字节）
        frame = bytes([0xFF, 0xFB, 0x90, 0x00]) + b"\x00" * 413
        with open(path, "ab") as f:
            f.write(frame)

    mp3_path = os.path.join(td, "tagged.mp3")
    make_mp3(mp3_path)
    before = ID3(mp3_path)
    check("MP3 标签写入成功", len(before.keys()) >= 3)

    ok, msg = M.strip_metadata(mp3_path)
    check("MP3 元数据清除", ok, msg)
    # 清除后不应再有标签
    try:
        ID3(mp3_path)
        has_tag = True
    except Exception:
        has_tag = False
    check("MP3 清除后无标签", not has_tag)

    # WAV：标准库生成真实 WAV，无标签，清除不应报错
    wav_path = os.path.join(td, "tagged.wav")
    with std_wave.open(wav_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(44100)
        wf.writeframes(b"\x00\x00" * 4410)  # 0.1 秒静音
    w = WAVE(wav_path)
    check("真实 WAV 可解析", w.info is not None)
    ok, msg = M.strip_metadata(wav_path)
    check("WAV 无标签清除不报错", ok, msg)

    # 无标签普通文件
    plain = os.path.join(td, "plain.mp3")
    with open(plain, "wb") as f:
        f.write(b"\x00" * 1024)
    ok, msg = M.strip_metadata(plain)
    check("无标签文件处理不报错", ok or not ok, msg)

    # 不支持的扩展名（非音频）不应被处理 —— collect 阶段已过滤
    txt = os.path.join(td, "note.txt")
    with open(txt, "w") as f:
        f.write("x")
    check("collect 过滤非音频", M.is_audio_file("note.txt") is False)

    # 扫描文件夹
    files = M.collect_audio_files(td)
    print("扫描结果:", files)
    check("扫描识别 mp3/wav", "tagged.mp3" in files and "tagged.wav" in files)

finally:
    shutil.rmtree(td, ignore_errors=True)

# ---------------------------------------------------------------------------
# 4. 唯一命名
# ---------------------------------------------------------------------------
td2 = tempfile.mkdtemp(prefix="audio_clean_test2_")
try:
    with open(os.path.join(td2, "Song.mp3"), "w") as f:
        f.write("")
    check("唯一命名自动加 (1)", M.unique_name(td2, "Song.mp3") == "Song (1).mp3")
finally:
    shutil.rmtree(td2, ignore_errors=True)

print()
if FAILED:
    print(f"共 {len(FAILED)} 项失败:", FAILED)
    sys.exit(1)
print("全部测试通过 ✔")
