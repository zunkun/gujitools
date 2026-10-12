# -*- coding: utf-8 -*-
"""「生成PDF」前的拼版新鲜度护栏（2026-10-12 冻结修复）。

用户报障：拼版生效时点「生成PDF」，界面立刻冻结。真因是
``_compose_imposition_now`` **无条件**在 GUI 主线程把全部拼版页同步
重合成一遍（几百页 = 冻结几十秒），而绝大多数点击时版面根本没改过。

修复后的三层语义（见 ``imposition_layout._compose_imposition_now``）：
1. **磁盘新鲜度快路径**：成品已覆盖落盘版面（页数相符 + 最旧成品 mtime ≥
   文档 mtime）→ 一个字节都不碰——本模块最核心的回归锁；
2. 拼版未生效 → 不白合成（第四步根本不读拼版目录）；
3. 真要合成 → 后台线程 + 事件循环等待收敛（跨会话陈旧也能兜住）。

⚠️ ``ImpositionComposeWorker.run`` 是**函数内** ``from … import compose_doc``，
所以打桩 ``desktop.services.imposition.compose_doc`` 对后台线程同样生效——
计数器按这个口径换。
"""

NAME = "imposition_fresh"
DEPENDS: list[str] = []
TITLE = "生成PDF前拼版新鲜度"

import os
import shutil
import tempfile
import time
from pathlib import Path

from tests.selftests._context import make_pdf, ok, pump


def _mk(path: Path, color, size=(400, 600)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def _product_count(out_dir: Path) -> int:
    """按 compose 的命名形态数成品（``NNNN.png``，别把杂物数进去）。"""
    if not out_dir.is_dir():
        return 0
    return sum(
        1
        for entry in out_dir.iterdir()
        if entry.is_file()
        and entry.suffix == ".png"
        and entry.stem.isdigit()
        and len(entry.stem) == 4
    )


def run(ctx) -> None:
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.services import imposition as S
    from desktop.store import TaskStore

    tmp = Path(tempfile.mkdtemp(prefix="guji_imposition_fresh_"))
    page = None
    calls = {"compose": 0}
    original_compose = S.compose_doc
    try:
        repo = TaskStore(tmp / "data")
        pdf = make_pdf(tmp / "新鲜度源.pdf", 2)
        tid = repo.create_task(pdf, "fresh-hash", "拼版新鲜度测试")
        repo.copy_source_to_task(tid, pdf)
        src = repo.rembg_output_dir(tid)
        a = _mk(src / "1-r.png", (220, 40, 40))
        b = _mk(src / "1-l.png", (30, 160, 60))
        made = S.make_page([a, b])
        assert made is not None
        # 拼版生效三判据：图里有节点（默认模板自带）+ 区域模式=左右分开 + 勾选
        repo.save_draft(tid, "rembg", {"area": 1})
        repo.save_imposition_doc(tid, {"enabled": True, "pages": [made]})

        page = TaskDetailPage(repo)
        page.resize(1080, 720)
        page.show()
        pump(ctx.app, times=12)
        ok("进入测试任务", page.set_task(tid))
        pump(ctx.app, times=8)
        assert page.task_id is not None
        ok("拼版当前是生效态", page.imposition_effective())

        def counting_compose(doc, dest, report=None):
            calls["compose"] += 1
            return original_compose(doc, dest, report)

        out_dir = repo.imposition_output_dir(tid)
        doc_path = repo.imposition_doc_path(tid)

        # ---------------- 快路径判据本身 ----------------
        ok("还没有成品时判为不新鲜", not page._imposition_products_fresh())

        S.compose_doc = counting_compose
        try:
            # ---------------- 首次：不新鲜 → 后台合成收敛后返回 ----------------
            page._compose_imposition_now()
            pump(ctx.app, times=8)
            ok(
                "首次调用完成了一轮合成（成品落盘 1 页）",
                calls["compose"] == 1 and _product_count(out_dir) == 1,
                f"calls={calls['compose']} products={_product_count(out_dir)}",
            )
            ok("合成后判为新鲜", page._imposition_products_fresh())

            # ---------------- 核心回归：已新鲜 → 零合成 ----------------
            page._compose_imposition_now()
            ok(
                "磁盘已新鲜 → 第二次调用零合成（不再冻结界面）",
                calls["compose"] == 1,
                f"calls={calls['compose']}",
            )

            # ---------------- 跨会话陈旧：内存脏标记已丢也兜得住 ----------------
            # ⚠️ 把**成品** mtime 拨到过去（别把文档拨到未来：重合成后成品
            #    拿的是真实当前时间，永远追不上未来的文档 mtime，断言必假红）
            past = time.time() - 1000
            for product in out_dir.glob("*.png"):
                os.utime(product, (past, past))
            ok("成品 mtime 比文档旧 → 判为不新鲜", not page._imposition_products_fresh())
            page._compose_imposition_now()
            pump(ctx.app, times=8)
            ok(
                "跨会话陈旧被兜住：重合成后恢复新鲜",
                calls["compose"] == 2 and page._imposition_products_fresh(),
                f"calls={calls['compose']}",
            )

            # ---------------- 页数不符（多出来的旧编号）----------------
            (out_dir / "0009.png").write_bytes(b"junk")
            ok("成品页数与文档不符 → 判为不新鲜", not page._imposition_products_fresh())
            (out_dir / "0009.png").unlink()

            # ---------------- 拼版未生效：不白合成 ----------------
            past = time.time() - 1000
            for product in out_dir.glob("*.png"):
                os.utime(product, (past, past))  # 先弄陈旧
            repo.save_imposition_doc(tid, {"enabled": False, "pages": [made]})
            page._compose_imposition_now()
            ok(
                "拼版未生效 → 即使陈旧也不合成（第四步不读拼版目录）",
                calls["compose"] == 2,
                f"calls={calls['compose']}",
            )
        finally:
            S.compose_doc = original_compose

        page.deleteLater()
        pump(ctx.app, times=4)
        repo.delete_task(tid)
    finally:
        S.compose_doc = original_compose
        if page is not None:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(tmp, ignore_errors=True)
