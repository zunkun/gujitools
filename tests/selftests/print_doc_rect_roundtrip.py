# -*- coding: utf-8 -*-
"""print.json 逐图 rect 随条目往返：plan_print_entries 携带 rect。

背景：第四步版面编辑后，每张图的 [x,y,w,h] mm 坐标要落进 print.json 的
pages[].rect，并在「复用已保存列表 / 重新进入第四步」时原样带回，不能丢。
plan_print_entries 是 GUI 各阶段共享的列表派生事实来源，必须保证 rect 透传。
"""

NAME = "print_doc_rect_roundtrip"
DEPENDS: list[str] = []
TITLE = "print.json 逐图 rect 随条目往返"

import shutil
import tempfile
from pathlib import Path

from tests.selftests._context import ok


def run(ctx) -> None:
    from desktop.services.print_plan import plan_print_entries

    tmp = tempfile.mkdtemp(prefix="guji_rect_")
    a = Path(tmp) / "a.png"
    b = Path(tmp) / "b.png"
    a.write_text("")  # 仅测"条目是否保留 rect"，不读像素内容
    b.write_text("")

    rembg = [a, b]
    doc = {
        "rembg_snapshot": [str(a), str(b)],
        "pages": [
            {"file": str(a), "label": "a", "rect": [10, 10, 50, 50]},
            {"file": str(b), "label": "b"},
        ],
    }

    entries, new_doc = plan_print_entries(rembg, doc)
    ok("带 rect 的条目保留 rect", entries[0].get("rect") == [10, 10, 50, 50],
       str(entries[0]))
    ok("无 rect 的条目不含 rect 键", "rect" not in entries[1], str(entries[1]))
    ok("new_doc.pages 携带 rect", new_doc["pages"][0].get("rect") == [10, 10, 50, 50],
       str(new_doc["pages"][0]))

    # snapshot 一致时复用用户列表 → rect 必须带回（不重算、不丢）
    entries2, _ = plan_print_entries(rembg, new_doc)
    ok("snapshot 一致时沿用用户 rect", entries2[0].get("rect") == [10, 10, 50, 50],
       str(entries2[0]))

    # rembg 产物集合变化（缺少 b）→ 外部插入的 b 仍应保留 rect（若它原本有）
    doc_ext = {
        "rembg_snapshot": [str(a)],
        "pages": [{"file": str(a), "label": "a", "rect": [1, 2, 3, 4]}],
    }
    entries3, _ = plan_print_entries([a], doc_ext)
    ok("产物集合变化后仍保留已存 rect",
       entries3 and entries3[0].get("rect") == [1, 2, 3, 4], str(entries3))

    shutil.rmtree(tmp, ignore_errors=True)
