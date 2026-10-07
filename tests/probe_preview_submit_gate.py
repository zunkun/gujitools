# -*- coding: utf-8 -*-
"""探针：「去底色那一步，图片编辑必须提交才能传给下一步」是否真的成立。

规则（用户 2026-10-01）：第三步「去底色结果」被右键编辑后，必须点
「提交本次任务」才能影响第四步（生成 PDF / 图片拼版）。

本探针用**真实生产函数**复现（不打模型、不生成真 PDF）：
    提交一次 → 编辑 stages/rembgpreview（**不再提交**）
    → 第四步取图规格（``SubmitMixin._build_print_effects``）
    → 真跑 print 的合成输入看是哪张图。

用法：
    QT_QPA_PLATFORM=offscreen python tests/probe_preview_submit_gate.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# 测试临时文件统一落点：tests/tmp/（见 tests/tmpdir.py）。
from tests.tmpdir import install as _install_tmpdir  # noqa: E402

_install_tmpdir()


def _img(color: str, w: int = 64, h: int = 48):
    from PySide6.QtGui import QColor, QImage

    im = QImage(w, h, QImage.Format.Format_RGB32)
    im.fill(QColor(color))
    return im


def _pix(path) -> str:
    from PySide6.QtGui import QImage

    return QImage(str(path)).pixelColor(2, 2).name()


def main() -> int:
    from PySide6.QtGui import QGuiApplication

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841

    from desktop.components.viewers.image_zoom_dialog import overwrite_image_file
    from desktop.pages.taskdetail.submit import SubmitMixin
    from desktop.services.print_plan import entry_to_effect_spec, plan_rembg_submit_entries
    from desktop.stages import print_stage, rembg_stage

    tmp = Path(tempfile.mkdtemp(prefix="guji_gate_"))
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
        # ⚠️ type: ignore —— PySide6 把 QImage.save 的 format 标成 bytes 系，
        # 运行期却收 str。
        _img("#ffffff").save(str(page), "PNG")  # type: ignore[reportCallIssue]
        _img("#ffffff").save(str(preview / "0001.png"), "PNG")  # type: ignore[reportCallIssue]

        def result_path_for(stem):
            c = preview / f"{stem}.png"
            return c if c.exists() else None

        def entries_from_preview():
            return plan_rembg_submit_entries(
                manifest_paths=[page], result_path_for=result_path_for,
                boxes_for=lambda _p: [], area=1,
            )

        # ---------- ① 正常提交一次（白底） ----------
        rc = rembg_stage.run_rembg_submit_stage({
            "task_id": "t", "stage": "rembg_submit", "run_id": "r1",
            "args": {
                "_effects": [entry_to_effect_spec(e, None)
                             for e in entries_from_preview()],
                "output": str(rembg), "clean": True,
            },
        })
        check("提交 exit=0", rc == 0, f"rc={rc}")
        check("提交产物白底", _pix(rembg / "0001.png") == "#ffffff",
              _pix(rembg / "0001.png"))

        # ---------- ② 编辑去底色结果（红），**不再提交** ----------
        overwrite_image_file(_img("#cc0000"), preview / "0001.png")
        check("去底色结果已编辑为红（未提交）",
              _pix(preview / "0001.png") == "#cc0000")

        # ---------- ③ 第四步取图规格（真实生产方法） ----------
        # 第四步列表 = 提交产物（stages/rembg），这里就是它的条目
        list_entries = [{"file": str(rembg / "0001.png"), "label": "0001"}]
        effects = SubmitMixin._build_print_effects(
            cast("SubmitMixin", object()), list_entries)
        src = Path(effects[0]["file"]) if effects else None
        print(f"      第四步取图：{src}（{_pix(src)}）")
        check("第四步取图指向提交产物（不是被编辑的去底图）",
              src is not None and src.parent == rembg and src != preview,
              str(src))

        # ---------- ④ 真跑 print stage（拦 CLI，只看合成输入） ----------
        captured: dict = {}
        orig = print_stage.run_stage
        print_stage.run_stage = lambda inner: (captured.update(inner["args"]), 0)[1]
        try:
            print_stage.run_print_stage({
                "task_id": "t", "stage": "print", "run_id": "r2",
                "args": {
                    "_effects": effects, "input": str(task),
                    "output": str(task / "stages" / "print"),
                },
            })
        finally:
            print_stage.run_stage = orig
        staged = [Path(f) for f in captured.get("files", [])]
        got = _pix(staged[0]) if staged else "（无暂存页）"
        print(f"      生成 PDF 的合成输入：{got}")

        check("★ 未提交的去底色编辑没有漏进第四步（仍为白）",
              got == "#ffffff",
              f"实际 = {got}"
              + ("（漏了：编辑未经提交已生效）" if got == "#cc0000" else ""))

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
