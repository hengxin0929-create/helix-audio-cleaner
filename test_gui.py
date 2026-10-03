#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GUI 冒烟测试：启动窗口 → 设置文件夹 → 扫描 → 预览 → 自动关闭
覆盖：BPM 保留、(1) 误加 bug 修复、勾选取消"""
import os
import sys
import shutil
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import main as M  # noqa: E402

td = tempfile.mkdtemp(prefix="audio_gui_test_")
names = [
    "01 Crazy Frog-How Do You Do(Fox boot【taoqu98】.mp3",
    "03-138 She Got It x Ready【taoqu98】.mp3",
    "08-140 VIP-Stay Fly -ALLEN-Y3-Remix []【taoqu98】.wav",
    "Already Clean Song.mp3",  # 已清理过的文件，验证不会被误加 (1)
]
for n in names:
    with open(os.path.join(td, n), "wb") as f:
        f.write(b"\x00" * 1024)


def smoke():
    root = M.tk.Tk()
    app = M.App(root)

    app.folder.set(td)
    app.scan()
    assert len(app.audio_files) == 4, app.audio_files
    # 公共片段检测：前三个有【taoqu98】，第四个没有 → 所有文件共同片段为空
    assert app.detected_parts == [], app.detected_parts
    # 手动添加【taoqu98】作为要删除的片段
    app.manual_part.set("【taoqu98】")
    app._add_manual_part()

    app.preview()
    assert len(app.rows) == 4

    # 验证各文件预览结果
    by_name = {r.name: r for r in app.rows}
    assert by_name["01 Crazy Frog-How Do You Do(Fox boot【taoqu98】.mp3"].new_name == \
        "Crazy Frog-How Do You Do(Fox boot.mp3"
    # BPM 保留：03-138 → 138
    assert by_name["03-138 She Got It x Ready【taoqu98】.mp3"].new_name == \
        "138 She Got It x Ready.mp3", by_name["03-138 She Got It x Ready【taoqu98】.mp3"].new_name
    # BPM 保留 + 空括号删除：08-140 → 140
    assert by_name["08-140 VIP-Stay Fly -ALLEN-Y3-Remix []【taoqu98】.wav"].new_name == \
        "140 VIP-Stay Fly -ALLEN-Y3-Remix.wav"
    # 已清理文件：new_name 应等于原名，绝不能带 (1)
    assert by_name["Already Clean Song.mp3"].new_name == "Already Clean Song.mp3", \
        by_name["Already Clean Song.mp3"].new_name

    # 取消第 2 行（03-138 那个），验证不改名
    by_name["03-138 She Got It x Ready【taoqu98】.mp3"].checked = False

    app.clean_meta.set(False)
    app.clean_name.set(True)
    app.run()

    def check_done():
        if app.running:
            root.after(100, check_done)
            return
        final = sorted(os.listdir(td))
        print("处理后目录:", final)
        assert "Crazy Frog-How Do You Do(Fox boot.mp3" in final
        assert "03-138 She Got It x Ready【taoqu98】.mp3" in final  # 未勾选，保留
        assert "140 VIP-Stay Fly -ALLEN-Y3-Remix.wav" in final
        assert "Already Clean Song.mp3" in final  # 未改名，无 (1)
        assert not any("(1)" in f for f in final), f"出现误加的 (1): {final}"
        print("GUI 冒烟测试通过 ✔")
        shutil.rmtree(td, ignore_errors=True)
        root.destroy()

    root.after(100, check_done)
    root.mainloop()


if __name__ == "__main__":
    smoke()
