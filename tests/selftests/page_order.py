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
    d._select_stage(d.bar_index_of_step("print"))
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
    # ⚠️ 与界面同一份文件：print.json 按节点隔离（主节点原名 / 副本 ``print~<节点>``），
    #    写盘也必须带上当前节点作用域，否则界面读的是另一份、顺序不跟随。
    repo.save_print_pages(
        tid,
        [{"file": e["file"], "label": e["label"]} for e in reordered],
        **d._node_scope(),
    )
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
    # ⚠️ 读 worker 实际消费的运行配置（run-<run_id>.json），不查 runs.json：
    #    2026-09-26 起入史前剥离 _effects/files/page_rects（写放大治理，
    #    见 desktop/store/runs.py 的 _RUN_STRIP_KEYS）
    import json as _json

    _run_id = repo.list_stage_runs(tid, "print")[0]["run_id"]
    _run_cfg = _json.loads(
        (repo.runs_config_dir(tid) / f"run-{_run_id}.json").read_text(encoding="utf-8")
    )
    _fx = _run_cfg["args"].get("_effects") or []
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

    # ---------------------------------------------------------- 插入任意位置
    # 用户反馈（2026-10-30）：以前「插入图片」只能追加到末尾。现在落点是
    # 左侧列表的**当前选中页之后**——选中第 2 页再插，就应该排在第 3 位。
    # 且每次插入都复制进 tasks/<号>/inserted/ 并给唯一文件名，同一张图能重复插。
    from tests.selftests._context import wait_until

    extra = ctx.tmp / "insert_case"
    extra.mkdir(parents=True, exist_ok=True)
    new_img = extra / "inserted.png"
    Image.new("RGB", (200, 300), "white").save(new_img)

    def _fake_insert(files):
        """以选中行为落点插入 files，等后台复制完成；返回 (插入前清单, 落点行)。

        ⚠️ 插入入口现在是**弹窗**（``PrintInsertPanel`` 的恢复/新上传两页签），
        离屏自测不能真弹窗，故直接喂 ``_apply_print_insert`` 期望的结果形状
        ——这正是弹窗 ``result_data()`` 的契约。
        """
        before, _ = d._print_entries()
        row = 1 if len(before) > 1 else -1
        d.print_preview.strip.setCurrentRow(row)
        d._apply_print_insert(
            {"position": "after", "deleted": [], "files": [str(p) for p in files]},
            row,
        )
        # ⚠️ 复制在后台线程（扫描图不在主线程 copy2）：必须等回调把条目写进列表
        wait_until(
            app, lambda: len(d._print_entries()[0]) > len(before), timeout=15.0
        )
        return before, row

    inserted_dir = repo.task_dir(tid) / "inserted"
    base, target_row = _fake_insert([new_img])
    base_files = [e["file"] for e in base]
    after, _ = d._print_entries()
    got = [e["file"] for e in after]
    added = [p for p in got if p not in base_files]
    if added:
        # 选中行 row → 落点 row+1；未选中（row=-1）→ 追加末尾（= 0 条时下标 0）
        expect_at = 0 if target_row < 0 else target_row + 1
        ok("插入图片落在当前选中页之后（不再固定追加末尾）",
           len(added) == 1 and got.index(added[0]) == expect_at,
           f"选中行={target_row} 实际位置={got.index(added[0])} "
           f"顺序={[Path(p).name for p in got]}")
        ok("插入的图片复制进任务目录 inserted/（源文件不被改动）",
           Path(added[0]).parent == inserted_dir and Path(new_img).exists(),
           str(added[0]))

    # 同一张图插第二次：必须出现**两条**（按 file 路径去重不能把重复吞掉）
    before_dup, _ = d._print_entries()
    before_dup_files = [e["file"] for e in before_dup]
    _fake_insert([new_img])
    after_dup, _ = d._print_entries()
    copies = [
        e["file"] for e in after_dup if Path(e["file"]).parent == inserted_dir
    ]
    dup_added = [p for p in (e["file"] for e in after_dup)
                 if p not in before_dup_files]
    ok("同一张图片可以插入多次（每次复制成唯一文件名）",
       len(dup_added) == 1
       and len(copies) >= 2 and len(set(copies)) == len(copies),
       f"本次新增={[Path(p).name for p in dup_added]} "
       f"inserted 副本={[Path(p).name for p in copies]}")

    # ---------------------------------------------------------- 软删除 + 恢复
    # 用户 2026-10-31：右键「删除当前图片」要**保留文件**并记进 deleted_pages，
    # 之后能在「插入图片 → 恢复图片」里重新放回；恢复要能多选、一次放回。
    before_del, _ = d._print_entries()
    victim_row = 1
    victim = before_del[victim_row]
    d.print_preview.strip.clearSelection()
    d.print_preview.strip.item(victim_row).setSelected(True)
    d.print_preview.remove_selected()
    doc_del = repo.load_print_doc(tid, **d._node_scope()) or {}
    deleted_files = {
        str(p.get("file")) for p in (doc_del.get("deleted_pages") or [])
    }
    remaining, _ = d._print_entries()
    ok("删除后条目从列表消失",
       all(e["file"] != victim["file"] for e in remaining),
       f"仍有 {sum(e['file'] == victim['file'] for e in remaining)} 条")
    ok("删除是软删除：原文件仍在磁盘上（可恢复）",
       Path(victim["file"]).exists(), victim["file"])
    ok("删除记进 print.json 的 deleted_pages",
       victim["file"] in deleted_files, str(sorted(deleted_files)))

    # 恢复：宿主吃的是弹窗 result_data() 的形状（position + 勾选的 deleted 条目）
    d._apply_print_insert(
        {"position": "after", "deleted": [victim], "files": []}, victim_row - 1
    )
    restored, _ = d._print_entries()
    doc_restored = repo.load_print_doc(tid, **d._node_scope()) or {}
    ok("恢复后条目回到待打印列表",
       any(e["file"] == victim["file"] for e in restored),
       f"{len(restored)} 条")
    ok("恢复后从 deleted_pages 移除（不会重复记录）",
       victim["file"] not in {
           str(p.get("file")) for p in (doc_restored.get("deleted_pages") or [])
       },
       str(doc_restored.get("deleted_pages")))


