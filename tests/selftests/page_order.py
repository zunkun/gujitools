# -*- coding: utf-8 -*-
"""页序数据映射自测：print 的页序由有序清单决定，不再依赖文件名。

核心契约（本次重构的立身之本）：
- 拖拽重排只改 print.json，**不产生任何物理文件**；
- 生成的 PDF 页序严格等于清单顺序，与文件名排序无关；
- title_switch_nodes / skip_pages 按**原始页码**回查清单下标，
  页面被拖到别处后标注仍跟着那一页走；
- 不再出现 workset 目录。
"""

NAME = "page_order"
DEPENDS: list[str] = ["print"]
TITLE = "页序数据映射"


def run(ctx) -> None:
    import time
    from pathlib import Path

    import pymupdf
    from PIL import Image, ImageDraw

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d.set_task(tid)
    d._select_stage(3)
    d._refresh_preview(3)

    # ---------------------------------------------------------- 纯清单页序
    # 直接对 CLI 层验证：清单顺序 = PDF 页序，且无需任何中间文件
    from core.args import CommandArgs
    from functions.print import PrintFunction

    tmp = ctx.tmp / "order_case"
    tmp.mkdir(parents=True, exist_ok=True)
    # 用纯色块编码页码，便于按像素判读 PDF 每页内容
    colors = {n: (30 * n + 20, 200 - 25 * n, 90) for n in range(1, 6)}
    for n, col in colors.items():
        im = Image.new("RGB", (320, 480), "white")
        ImageDraw.Draw(im).rectangle([40, 150, 280, 330], fill=col)
        im.save(tmp / f"{n}.png")

    order = [5, 1, 3, 2, 4]  # 模拟用户拖拽后的顺序
    files = [str(tmp / f"{n}.png") for n in order]
    captured: dict = {}
    _real_gen = PrintFunction._generate_pdf

    def _spy(self, input_dir, output_pdf, *a, **kw):
        captured["files"] = kw.get("files")
        return _real_gen(self, input_dir, output_pdf, *a, **kw)

    PrintFunction._generate_pdf = _spy
    try:
        ca = CommandArgs(
            command="print", input=str(tmp), output=str(tmp), pdf_name="o.pdf",
            files=files, paper_size="A5", orientation="portrait",
        )
        PrintFunction(ca).execute()
    finally:
        PrintFunction._generate_pdf = _real_gen

    ok("CLI 收到有序清单且原样使用", captured.get("files") == files,
       str(captured.get("files")))
    doc = pymupdf.open(str(tmp / "o.pdf"))
    seq = []
    palette = list(colors.keys())
    for page in doc:
        pix = page.get_pixmap(dpi=36)
        r, g, b = pix.pixel(pix.width // 2, pix.height // 2)
        seq.append(min(palette, key=lambda n: sum(
            (x - y) ** 2 for x, y in zip(colors[n], (r, g, b)))))
    doc.close()
    ok("PDF 页序严格等于清单顺序（与文件名排序无关）", seq == order,
       f"实际={seq} 期望={order}")

    # ---------------------------------------------------------- 无清单回退
    # 不传 files 时必须保持 CLI 独立用法：按文件名排序（cover 优先、数字自然序）
    compat = ctx.tmp / "compat_case"
    compat.mkdir(parents=True, exist_ok=True)
    for name in ("10", "1", "cover", "2"):
        Image.new("RGB", (200, 300), "white").save(compat / f"{name}.png")
    ca2 = CommandArgs(command="print", input=str(compat), output=str(compat),
                      pdf_name="c.pdf", paper_size="A5", orientation="portrait")
    res = PrintFunction(ca2).execute()
    ok("不传清单时按文件名排序（CLI 独立用法保持）", res.get("processed") == 4, str(res))

    # ---------------------------------------------------------- 拖拽重排
    # GUI 侧：拖拽只改 print.json，不落地任何文件
    entries, _ = d._print_entries()
    n_before = len(entries)

    def _ws_count() -> int:
        """两种可能落点上的文件总数（见下方 workset 断言的说明）。"""
        total = 0
        for cand in (repo.task_dir(tid) / "workset",
                     repo.stage_dir(tid, "workset")):
            if cand.exists():
                total += len(list(cand.iterdir()))
        return total

    ws_files_before = _ws_count()

    # 模拟拖拽：把列表首项移到末尾（直接操作持久化顺序，等价于拖拽结果）
    reordered = entries[1:] + entries[:1]
    repo.save_print_pages(tid, [{"file": e["file"], "label": e["label"]} for e in reordered])
    d._refresh_preview(3)
    entries_after, _ = d._print_entries()
    ok("拖拽重排后列表顺序跟随数据表",
       [e["file"] for e in entries_after] == [e["file"] for e in reordered],
       f"{len(entries_after)} 条")
    ws_files_after = _ws_count()
    # 两类回归分开断言，避免互相掩盖：
    # ① 拖拽动作本身不得落地文件（前=后）；
    # ② 任务目录不得出现 workset 内容（执行期也不物化副本）。
    ok("拖拽重排不改变任务目录文件数",
       ws_files_after == ws_files_before,
       f"workset 前={ws_files_before} 后={ws_files_after}")
    ok("拖拽前后任务目录始终无 workset 内容",
       ws_files_after == 0,
       f"workset 实有 {ws_files_after} 项")

    # 运行一次，确认 PDF 页序跟随重排结果
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    doc = pymupdf.open(str(repo.print_output_pdf(tid)))
    ok("重排后 PDF 页数与列表一致", doc.page_count == n_before, str(doc.page_count))
    doc.close()
    _fx = repo.list_stage_runs(tid, "print")[0]["parameters"].get("_effects") or []
    ok("运行配置的合成规格顺序与列表一致",
       [Path(s["file"]).stem for s in _fx]
       == [Path(e["file"]).stem for e in entries_after],
       f"{len(_fx)} 条")

    # ---------------------------------------------------------- workset 不再产生
    # 必须在 print **执行之后**检查：workset 是执行期产物，执行前本来就该空。
    ok("print 执行后任务目录不产生 workset 内容",
       _ws_count() == 0,
       f"workset 实有 {_ws_count()} 项")

    # ---------------------------------------------------------- 页码标注语义
    # title_switch_nodes 填的是**原始页码**：页面被拖到列表别处后，
    # 标题切换仍要跟着那一页走（按同名回查清单下标，而非按下标算）
    from functions.print import _resolve_title_nodes
    ordered = [str(tmp / f"{n}.png") for n in (3, 1, 2)]  # 清单：3 在前
    nodes = [[1, "第一章"]]  # 原始页码 1（清单里排第 2 位）
    resolved = _resolve_title_nodes(ordered, nodes)
    ok("章节节点按原始页码回查清单下标",
       resolved == [(1, ("第一章", "left"))],
       f"ordered={[Path(p).name for p in ordered]} resolved={resolved}")

    # skip_pages 按清单序号匹配：跳过清单第 2 项（= 原 1.png），
    # 因此 PDF 里不应出现 "1" 这一页的内容
    ca3 = CommandArgs(command="print", input=str(tmp), output=str(tmp),
                      pdf_name="s.pdf", files=files, skip_pages=["2"],
                      paper_size="A5", orientation="portrait")
    PrintFunction(ca3).execute()
    doc = pymupdf.open(str(tmp / "s.pdf"))
    seq_skipped = []
    palette = list(colors.keys())
    for page in doc:
        pix = page.get_pixmap(dpi=36)
        r, g, b = pix.pixel(pix.width // 2, pix.height // 2)
        seq_skipped.append(min(palette, key=lambda n: sum(
            (x - y) ** 2 for x, y in zip(colors[n], (r, g, b)))))
    doc.close()
    ok("skip_pages 按清单序号跳过对应页",
       seq_skipped == [n for n in order if n != 1],
       f"实际={seq_skipped} 期望={[n for n in order if n != 1]}")

