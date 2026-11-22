# -*- coding: utf-8 -*-
"""print 阶段「成品直通」护栏（2026-10-12，用户口径：第四步只做"上纸"排版）。

拼版 /「提交本次任务」的产物在**上一步就已经落成实体文件**，PDF 排版用
的就是那批文件——因此 ``run_print_stage`` 对 ``effect`` 为空的条目必须
**原路径直通**给 PDF 生成，不做任何解码/转码；暂存目录只在真有区域合成
条目时才创建。本模块直接在**进程内**调用 ``run_print_stage``（不走
QProcess，沙箱可跑），锁三条语义：

1. 纯直通（当前 GUI 常规形态）：出 PDF、页数正确、**不创建暂存目录**；
2. 混合（区域合成 + 直通）：两页都进 PDF、暂存目录按需创建且落了合成页；
3. 清单里有缺失文件：跳过该页、其余照常出 PDF（与 functions/print 同口径）。
"""

NAME = "print_passthrough"
DEPENDS: list[str] = []
TITLE = "print阶段成品直通"

import shutil
import tempfile
from pathlib import Path


def _mk(path: Path, color, size=(600, 800)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def run(ctx) -> None:
    import pymupdf

    from tests.selftests._context import ok

    from desktop.stages import print_stage as PS

    tmp = Path(tempfile.mkdtemp(prefix="guji_print_passthrough_"))
    try:
        src = tmp / "src"
        a = _mk(src / "0001.png", (200, 30, 30))
        b = _mk(src / "0002.png", (30, 160, 60))
        out_root = tmp / "out"

        def make_config(task_id: str, run_id: int, effects: list) -> dict:
            return {
                "task_id": task_id,
                "stage": "print",
                "run_id": run_id,
                "args": {
                    "output": str(out_root / task_id),
                    "pdf_name": "out.pdf",
                    "_effects": effects,
                },
            }

        def page_count(pdf: Path) -> int:
            doc = pymupdf.open(str(pdf))
            try:
                return doc.page_count
            finally:
                doc.close()

        # ---------------- 1) 纯直通（当前 GUI 常规形态）----------------
        cfg = make_config(
            "t-pass",
            1,
            [{"file": str(a), "effect": None}, {"file": str(b), "effect": None}],
        )
        rc = PS.run_print_stage(cfg)
        pdf = out_root / "t-pass" / "out.pdf"
        ok("纯直通运行成功且产出 PDF", rc == 0 and pdf.exists(), f"rc={rc}")
        ok("纯直通 PDF 页数 = 成品图张数", page_count(pdf) == 2, str(page_count(pdf)))
        ok(
            "纯直通运行**不创建暂存目录**（成品不再转手重编码）",
            not (PS.staging_root() / "t-pass-1").exists(),
            str(PS.staging_root() / "t-pass-1"),
        )

        # ---------------- 2) 混合：区域合成条目 + 直通条目 ----------------
        eff = {"boxes": [[0, 0, 600, 800]], "area": 2, "border": None}
        cfg2 = make_config(
            "t-mix",
            2,
            [
                {"file": str(a), "label": "合成页", "effect": eff},
                {"file": str(b), "effect": None},
            ],
        )
        rc2 = PS.run_print_stage(cfg2)
        pdf2 = out_root / "t-mix" / "out.pdf"
        ok("混合运行成功且产出 PDF", rc2 == 0 and pdf2.exists(), f"rc={rc2}")
        ok(
            "混合运行 PDF 页数一致（合成条目 + 直通条目各一页）",
            page_count(pdf2) == 2,
            str(page_count(pdf2)),
        )
        ok(
            "混合运行按需创建暂存目录并落了合成页",
            (PS.staging_root() / "t-mix-2" / "0001.png").is_file(),
        )

        # ---------------- 3) 清单里有缺失文件：跳过不崩 ----------------
        cfg3 = make_config(
            "t-miss",
            3,
            [
                {"file": str(a), "effect": None},
                {"file": str(src / "ghost.png"), "effect": None},
            ],
        )
        rc3 = PS.run_print_stage(cfg3)
        pdf3 = out_root / "t-miss" / "out.pdf"
        ok(
            "缺失文件被跳过且其余页照常出 PDF",
            rc3 == 0 and pdf3.exists() and page_count(pdf3) == 1,
            f"rc={rc3} pages={page_count(pdf3) if pdf3.exists() else '无PDF'}",
        )
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
