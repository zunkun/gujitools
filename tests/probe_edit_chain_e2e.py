# -*- coding: utf-8 -*-
"""探针：图片编辑跨步骤链路端到端验证（真实 stage 函数，不打模型、不生成真 PDF）。

链路：去底色结果(stages/rembgpreview) → 提交产物(stages/rembg) → 生成 PDF 合成输入

用法：
    QT_QPA_PLATFORM=offscreen python tests/probe_edit_chain_e2e.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _img(color: str, w: int = 64, h: int = 48):
    from PySide6.QtGui import QColor, QImage

    im = QImage(w, h, QImage.Format_RGB32)
    im.fill(QColor(color))
    return im


def _pix(path, x=2, y=2, tol=40) -> str:
    from PySide6.QtGui import QImage

    return QImage(str(path)).pixelColor(x, y).name()


def _is(path, expected: str, tol=40) -> bool:
    from PySide6.QtGui import QColor, QImage

    got = QImage(str(path)).pixelColor(2, 2)
    want = QColor(expected)
    return (
        abs(got.red() - want.red()) <= tol
        and abs(got.green() - want.green()) <= tol
        and abs(got.blue() - want.blue()) <= tol
    )


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841

    from desktop.components.viewers.image_zoom_dialog import overwrite_image_file
    from desktop.pages.taskdetail.submit import SubmitMixin
    from desktop.services.print_plan import (
        entry_to_effect_spec, plan_rembg_submit_entries,
    )
    from desktop.stages import print_stage, rembg_stage

    tmp = Path(tempfile.mkdtemp(prefix="guji_edit_chain_"))
    results: list[tuple[str, bool, str]] = []

    def check(name, ok, detail=""):
        results.append((name, ok, detail))
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
              + (f"  —— {detail}" if detail else ""))

    try:
        task = tmp / "task"
        extract = task / "stages" / "extract"
        preview = task / "stages" / "rembgpreview"
        rembg = task / "stages" / "rembg"
        for d in (extract, preview, rembg):
            d.mkdir(parents=True)
        page = extract / "0001.png"
        _img("#ffffff").save(str(page), "PNG")
        _img("#ffffff").save(str(preview / "0001.png"), "PNG")
        _img("#ffffff").save(str(rembg / "0001.png"), "PNG")

        # ============ ① 第三步「去底色结果」右键编辑 → 覆盖 rembgpreview
        check("编辑前 rembgpreview 是白底",
              _is(preview / "0001.png", "#ffffff"))
        overwrite_image_file(_img("#cc0000"), preview / "0001.png")
        check("右键编辑去底色结果 → 文件真的变红",
              _is(preview / "0001.png", "#cc0000"))

        # ============ ② 走「提交本次任务」真实 stage 函数
        def result_path_for(stem):
            c = preview / f"{stem}.png"
            return c if c.exists() else None

        entries = plan_rembg_submit_entries(
            manifest_paths=[page], result_path_for=result_path_for,
            boxes_for=lambda _p: [], area=1,
        )
        rc = rembg_stage.run_rembg_submit_stage({
            "task_id": "t", "stage": "rembg_submit", "run_id": "r1",
            "args": {
                "_effects": [entry_to_effect_spec(e, None) for e in entries],
                "output": str(rembg), "clean": True,
            },
        })
        check("提交本次任务 exit=0", rc == 0, f"rc={rc}")
        check("提交产物（stages/rembg）带上了编辑结果（红）",
              _is(rembg / "0001.png", "#cc0000"),
              _pix(rembg / "0001.png"))

        # ============ ③ 第四步「生成 PDF」真实合成（拦掉 CLI，只看合成输入）
        captured: dict = {}
        orig_run_stage = print_stage.run_stage
        print_stage.run_stage = lambda inner: (captured.update(inner["args"]), 0)[1]
        try:
            # 第四步列表 = 提交产物（2026-10-01 起取图只透传它）
            list_entries = [{"file": str(rembg / "0001.png"), "label": "0001"}]
            effects = SubmitMixin._build_print_effects(object(), list_entries)
            print_stage.run_print_stage({
                "task_id": "t", "stage": "print", "run_id": "r2",
                "args": {
                    "_effects": effects, "input": str(task),
                    "output": str(task / "stages" / "print"),
                },
            })
        finally:
            print_stage.run_stage = orig_run_stage

        staged = [Path(f) for f in captured.get("files", [])]
        check("print 合成确实产出了暂存页", bool(staged), str(staged))
        if staged:
            check("★ 编辑过的去底色结果 → 真的进了 PDF 合成输入（红）",
                  _is(staged[0], "#cc0000"), _pix(staged[0]))
            print("      print 合成读的源文件：",
                  effects[0]["file"] if effects else "—")

        # ============ ④ 反例：在第四步右键编辑「待打印图」（stages/rembg）
        overwrite_image_file(_img("#0000cc"), rembg / "0001.png")
        check("第四步待打印图被编辑成蓝",
              _is(rembg / "0001.png", "#0000cc"))
        captured2: dict = {}
        print_stage.run_stage = lambda inner: (captured2.update(inner["args"]), 0)[1]
        try:
            print_stage.run_print_stage({
                "task_id": "t", "stage": "print", "run_id": "r3",
                "args": {
                    "_effects": effects,      # 与上一轮同一份效果规格
                    "input": str(task),
                    "output": str(task / "stages" / "print"),
                },
            })
        finally:
            print_stage.run_stage = orig_run_stage
        staged2 = [Path(f) for f in captured2.get("files", [])]
        got_blue = bool(staged2) and _is(staged2[0], "#0000cc")
        check("★ 第四步编辑待打印图（stages/rembg）是否影响 PDF 合成输入",
              got_blue,
              ("第二轮的暂存页 = " + (_pix(staged2[0]) if staged2 else "无"))
              + "（期望 #0000cc 蓝）")

        print()
        bad = [n for n, ok, _ in results if not ok]
        print(f"共 {len(results)} 项，失败 {len(bad)} 项")
        for n in bad:
            print("  ✗", n)
        return 1 if bad else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
