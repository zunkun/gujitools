# -*- coding: utf-8 -*-
"""上游产物被「同名覆盖」后，下游步骤要自动加载最新的图片（2026-10-18）。

用户报障：任务 0018 最后一步「PDF排版」里的图片不是最新的——前一步「图片拼版」
的图片变了（成品页被后台重合成，``stages/imposition/0001.png`` 文件名一个字没变），
PDF排版却停在旧图上。用户把它推广成**通用规则**：

> 上一步如果图片发生变化，下一次切换当前步骤的时候，要自动加载最新的图片；
> 不止是 PDF 排版，而是这个流程中节点都是一样。

根因是"判据只比**目录路径**"：``_refresh_print_source`` 原先拿
``str(print_source_dir())`` 与缓存比对，同名覆盖时两者恒等 ⇒ 后台合成的收尾
回调（``_on_imposition_composed``）被判成"来源没换"直接跳过，列表永远停在旧图。
第一步/第二步的缩略图同理：条目图标解码一次就存进 ``QIcon``，清单不变就不重装。

本模块钉住两条修复后的语义：

1. **内容指纹**（``desktop.utils.files.dir_content_signature``）：目录 + 内容
   一起比——同名覆盖看得出变化，纯路径比对看不出；
2. **切步骤时按内容判强制重装**：上游产物内容变了才强制（``force=True``），
   没变则一个字都不重解（不白费几百页的解码）。

⚠️ 刻意**不**依赖 ``services.imposition.compose_doc`` / 后台 worker：这里直接往
成品目录写文件来制造"同名覆盖"，与真实合成落盘的结果在磁盘上完全等价，而
少一次线程/事件循环的时序不确定性。
"""

NAME = "stage_content_fresh"
DEPENDS: list[str] = []
TITLE = "上游产物覆盖后下游自动刷新"

import shutil
import tempfile
from pathlib import Path

from tests.selftests._context import make_pdf, ok, pump


def _mk(path: Path, color, size=(400, 600)) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
    return path


def run(ctx) -> None:
    from desktop.pages.taskdetail.page import TaskDetailPage
    from desktop.services import imposition as S
    from desktop.store import TaskStore
    from desktop.utils.files import dir_content_signature

    tmp = Path(tempfile.mkdtemp(prefix="guji_stage_fresh_"))
    page = None
    try:
        repo = TaskStore(tmp / "data")
        pdf = make_pdf(tmp / "新鲜度源.pdf", 2)
        tid = repo.create_task(pdf, "fresh-hash", "下游刷新测试")
        repo.copy_source_to_task(tid, pdf)
        src = repo.rembg_output_dir(tid)
        made = S.make_page([
            _mk(src / "1-r.png", (220, 40, 40)),
            _mk(src / "1-l.png", (30, 160, 60)),
        ])
        assert made is not None
        # 拼版生效三判据：图里有节点（默认模板自带）+ 区域模式=左右分开 + 勾选
        # ⚠️ 2026-10-22：area 归「检测文本框」（它决定第二步提交怎么裁图），
        #    所以暂存要写 detect 那一格。
        repo.save_draft(tid, "detect", {"area": 1})
        repo.save_imposition_doc(tid, {"enabled": True, "pages": [made]})

        page = TaskDetailPage(repo)
        page.resize(1080, 720)
        page.show()
        pump(ctx.app, times=12)
        ok("进入测试任务", page.set_task(tid))
        pump(ctx.app, times=8)
        assert page.task_id is not None
        ok("拼版当前是生效态", page.imposition_effective())

        # ---------------- 内容指纹：同名覆盖看得出、纯路径看不出 ----------------
        ok(
            "不存在的目录 → 指纹为 None（与空目录 (0,0,0) 区分）",
            dir_content_signature(tmp / "并不存在") is None,
        )
        empty = tmp / "空目录"
        empty.mkdir()
        ok("空目录的指纹是 (0, 0, 0)", dir_content_signature(empty) == (0, 0, 0))
        sig0 = dir_content_signature(empty)
        _mk(empty / "0001.png", (10, 10, 10))
        sig1 = dir_content_signature(empty)
        _mk(empty / "0001.png", (240, 240, 240))  # 同名覆盖
        ok(
            "同名覆盖后内容指纹变（路径一个字没变）",
            sig0 != sig1 != dir_content_signature(empty),
            f"{sig0} -> {sig1} -> {dir_content_signature(empty)}",
        )

        # ---------------- 第四步：拼版成品内容变了 → 列表当场重建 ----------------
        out_dir = repo.imposition_output_dir(tid)
        _mk(out_dir / "0001.png", (200, 60, 60))
        print_page = page.stack_index_of_step("print")
        assert print_page is not None
        page.preview_stack.setCurrentIndex(print_page)
        page._refresh_preview(print_page)
        ok(
            "第四步待打印列表初始 1 页（取拼版成品）",
            page.print_preview.count() == 1,
            str(page.print_preview.count()),
        )
        mark_before = page._print_source_mark()
        ok(
            "第四步取图来源是拼版成品目录",
            Path(mark_before[0]) == out_dir,
            str(mark_before[0]),
        )
        ok(
            "此刻缓存标记 == 当前内容标记（下一次同内容会走快路径）",
            page._print_source_cache == mark_before,
        )

        rebuilt: list[int] = []
        original_set_entries = page.print_preview.set_entries

        def spy(entries):
            rebuilt.append(len(entries))
            return original_set_entries(entries)

        page.print_preview.set_entries = spy  # type: ignore[method-assign]
        try:
            page._refresh_print_source()
            ok(
                "内容没变 → 不重建（不会每次刷新都白解一遍首图）",
                rebuilt == [],
                str(rebuilt),
            )

            # 同名覆盖：文件名与目录都没变，只有内容变了
            _mk(out_dir / "0001.png", (60, 60, 200))
            mark_after = page._print_source_mark()
            ok(
                "同名覆盖后：目录没变、内容标记变了",
                mark_after[0] == mark_before[0] and mark_after != mark_before,
                f"{mark_before} -> {mark_after}",
            )
            page._refresh_print_source()
            ok(
                "核心回归：拼版成品内容变了 → 第四步列表当场重建",
                rebuilt == [1],
                str(rebuilt),
            )

            # 后台合成收尾走的正是这条回调（拼版合成完成 → 刷新第四步）
            rebuilt.clear()
            _mk(out_dir / "0002.png", (20, 200, 20))
            page._on_imposition_composed(str(out_dir), 2)
            ok(
                "合成完成回调也把第四步刷到最新（多出的成品页立刻进列表）",
                rebuilt == [2],
                str(rebuilt),
            )

            # 第四步不可见时：只作废缓存，不原地重建（把重建留给进第四步那次）
            rebuilt.clear()
            away_page = page.stack_index_of_step("detect")
            assert away_page is not None
            page.preview_stack.setCurrentIndex(away_page)
            _mk(out_dir / "0003.png", (200, 200, 20))
            page._refresh_print_source()
            ok(
                "第四步不可见 → 只作废缓存、不重建",
                rebuilt == [] and page._print_source_cache is None,
                str(rebuilt),
            )
            page.preview_stack.setCurrentIndex(print_page)
            page._refresh_preview(print_page)
            ok(
                "再进第四步：列表按最新成品重建（3 页）",
                page.print_preview.count() == 3,
                str(page.print_preview.count()),
            )
        finally:
            page.print_preview.set_entries = original_set_entries  # type: ignore[method-assign]

        # ---------------- 逐页 rect：只对"画它时那张图"有效（用户 2026-10-18）----------------
        # 「上一步的输出归上一步，当前步 PDF排版，页面效果都要按照相关参数来调整」：
        # 图像被上游换掉（同名覆盖、像素尺寸变了）之后，那条按旧图摆的逐页坐标不再
        # 表达用户意图——继续套上去就是把新图拉成错的宽高，本步参数（纸张/方向/
        # 边距/原比例）等于没起作用。
        from desktop.services.print_plan import (
            ordered_page_record,
            rect_fits_image,
        )
        from desktop.utils.files import changed_images

        ok("rect 记录的像素尺寸与当前一致 → 仍适用",
           rect_fits_image([10, 10, 40, 60], (400, 600), (400, 600)))
        ok("rect 记录的像素尺寸变了 → 不再适用（宽高比凑巧相同也不行）",
           not rect_fits_image([10, 10, 40, 60], (300, 450), (400, 600)))
        ok("老数据没记尺寸：宽高比一致 → 仍适用",
           rect_fits_image([10, 10, 40, 60], (400, 600), None))
        ok("老数据没记尺寸：宽高比不一致 → 不再适用（半页 → 对开页）",
           not rect_fits_image([10, 10, 80, 60], (400, 600), None))
        ok("读不到图像尺寸 → 保留用户排版（无从判断，绝不误清）",
           rect_fits_image([10, 10, 40, 60], (0, 0))
           and rect_fits_image([10, 10, 40, 60], (None, None), None))
        base = {"a": (10, 1), "b": (20, 2)}
        ok("逐文件记录：没有基线 → 不把整目录报成「刚更新」",
           changed_images(None, base) == [])
        ok("逐文件记录：内容没变 → 空表", changed_images(base, dict(base)) == [])
        ok("逐文件记录：覆盖/新增的**只报那几张**",
           changed_images(base, {"a": (10, 1), "b": (99, 3), "c": (5, 4)})
           == ["b", "c"])

        # 造一份"用户在 A4 上摆过的版面"（老数据：只有 rect、没有 rect_size）
        p1, p2, p3 = (out_dir / f"{i:04d}.png" for i in (1, 2, 3))
        _mk(p1, (200, 60, 60))
        _mk(p2, (60, 200, 60))
        repo.save_print_doc(tid, {
            "rembg_snapshot": [str(p1), str(p2), str(p3)],
            "pages": [
                # 0001：框的宽高比 == 当前图 (400,600) → 还适用，保留
                {"file": str(p1), "label": "0001",
                 "rect": [100.0, 20.0, 113.33, 170.0]},
                # 0002：框是按**宽图**摆的（1.51），当前图是竖图 → 已失效
                {"file": str(p2), "label": "0002",
                 "rect": [20.0, 20.0, 257.0, 170.0]},
            ],
        })
        entries, _ = page._print_entries()
        by_name = {Path(e["file"]).name: e for e in entries}
        ok(
            "图像没换的页：用户摆的 rect 原样保留（不误清）",
            by_name["0001.png"].get("rect") == [100.0, 20.0, 113.33, 170.0],
            str(by_name["0001.png"]),
        )
        ok(
            "图像已换的页：旧 rect 被丢掉，改按当前 PDF排版参数自动排版",
            by_name["0002.png"].get("rect") is None,
            str(by_name["0002.png"]),
        )
        spec, _note = page.print_preview._print_spec(1, p2)
        ok(
            "被丢 rect 的那页：预览走自动排版（spec.rect 为 None）",
            spec is not None and spec["rect"] is None,
            str(spec),
        )
        log_text = page.log_view.toPlainText()
        ok(
            "「上一步更新了哪些图片」有记录（日志点名了那一页）",
            "图片已更新" in log_text and "0002.png" in log_text.split("图片已更新", 1)[1],
            log_text[-200:],
        )

        # 画布上拖一下 → 条目带上 rect_size（"这个框是按哪张图摆的"）
        page.print_preview._select_entry(0)
        page.print_preview._on_canvas_rect([120.0, 30.0, 100.0, 150.0])
        dragged = page.print_preview.entries()[0]
        ok(
            "拖过框的页：记下 rect_size（画框时的图像像素尺寸）",
            dragged.get("rect") == [120.0, 30.0, 100.0, 150.0]
            and dragged.get("rect_size") == [400, 600],
            str(dragged),
        )
        # 同比例、不同像素尺寸：新数据（有 rect_size）也要判过期
        _mk(p1, (200, 60, 60), size=(300, 450))
        entries, _ = page._print_entries()
        ok(
            "新数据：rect_size 与当前图像不符 → 旧框失效（同比例也不行）",
            entries[0].get("rect") is None,
            str(entries[0]),
        )
        ok(
            "落盘口径唯一：ordered_page_record 带着 rect + rect_size",
            ordered_page_record(dragged)
            == {"file": str(p1), "label": "0001",
                "rect": [120.0, 30.0, 100.0, 150.0], "rect_size": [400, 600]},
            str(ordered_page_record(dragged)),
        )

        # ---------------- 拼版成品：只重存"变了的那几页"（用户 2026-10-18）----------------
        # 「拼版图片变更，现在存储实体图片太慢，需要好几秒」的根因：版面一动就把
        # 整本 85+ 页全部重合成再重写一遍。用户口径：「不是所有图片都重新存储
        # 一份，只存储当前拼版的图片页」，并「通知下一步要变更的图片」。
        import json as _json

        from desktop.components.imposition.page_thumb import page_signature
        from desktop.services.imposition import compose_doc

        # 第二页（另一组源图）与两页的拼版文档（后面按"页"判增量）
        second = S.make_page([
            _mk(src / "3-r.png", (200, 180, 40)),
            _mk(src / "3-l.png", (40, 80, 200)),
        ])
        assert second is not None
        repo.save_imposition_doc(tid, {"enabled": True, "pages": [made, second]})
        doc2 = {"pages": [made, second]}
        only_dir = tmp / "only_out"
        compose_doc(doc2, only_dir)
        ok(
            "合成器：全量（默认）两页都落盘",
            (only_dir / "0001.png").is_file() and (only_dir / "0002.png").is_file(),
        )
        before = {
            i: (only_dir / f"{i:04d}.png").read_bytes() for i in (1, 2)
        }
        marks = {
            i: (only_dir / f"{i:04d}.png").stat().st_mtime_ns for i in (1, 2)
        }
        moved_doc = _json.loads(_json.dumps(doc2))
        moved_doc["pages"][1]["items"][0]["rect"][0] += 40  # 只动第 2 页的一张图
        compose_doc(moved_doc, only_dir, only=[1])
        ok(
            "合成器：only=[1] 只重写第 2 页（第 1 页字节与 mtime 都没动）",
            (only_dir / "0001.png").read_bytes() == before[1]
            and (only_dir / "0001.png").stat().st_mtime_ns == marks[1],
        )
        ok(
            "合成器：被判要重写的那页内容确实变了",
            (only_dir / "0002.png").read_bytes() != before[2],
        )

        # 增量判据：签名与版面一致 ⇒ 一页都不用重合成；只动一页 ⇒ 只那一页
        sigs_path = page._composed_sigs_path()
        assert sigs_path is not None
        page._composed_sigs_cache[str(sigs_path)] = {
            i: (page_signature(p) or "")
            for i, p in enumerate(page._imposition_pages())
        }
        ok(
            "增量判据：签名与版面一致 → 没有要重合成的页",
            page._stale_imposition_pages() == [],
            str(page._stale_imposition_pages()),
        )
        edited = _json.loads(_json.dumps(page._imposition_doc()))
        edited["pages"][1]["items"][0]["rect"][0] += 25
        repo.save_imposition_doc(tid, edited)
        ok(
            "增量判据：只动一页 → 只有那一页要重合成（不整本）",
            page._stale_imposition_pages() == [1],
            str(page._stale_imposition_pages()),
        )
        ok(
            "换任务要清签名（否则新任务被当成「已落盘」）",
            isinstance(page._imposition_page_sigs, dict),
        )

        # ---------------- 端到端：只调整一页 → 只重写 0002.png + 只通知那一条 ----------------
        # 用户 2026-10-18 的原话：「imposition 一张图片调整了，那么 stages/imposition
        # 要调整生成实时的那张图片，比如 0002.png，**其他图片不用重写**；同时通知
        # 下一步调整图片，**但是也只限于使用了 0002.png 的那张图片**，不影响其他的
        # 图片排版」。这一段整条走真实路径（判据 → worker → 收尾 → 通知）。
        sigs_path = page._composed_sigs_path()
        assert sigs_path is not None
        page._composed_sigs_cache[str(sigs_path)] = {
            0: page_signature(page._imposition_pages()[0]) or "",
            # 第 2 页故意留一个旧签名 → 它必须被重合成，其余页一个字节都不该动
            1: "stale-on-purpose",
        }
        # 对齐"文档页数 == 成品页数"：合成收尾会清掉多出来的编号（第 3 页不在文档里），
        # 不清的话这一步会因为"清单结构变了"走整列重建，掩盖住"只刷那一条"的判据。
        (out_dir / "0003.png").unlink(missing_ok=True)
        before_mtimes = {
            p.name: p.stat().st_mtime_ns
            for p in out_dir.iterdir() if p.is_file() and p.stem.isdigit()
        }
        page.preview_stack.setCurrentIndex(print_page)
        page._refresh_preview(print_page)  # 先把第四步条目与缓存对齐
        page.print_preview.strip.setCurrentRow(1)
        page.imposition_view.set_current(1)  # 用户正看着第 2 页
        rebuilt.clear()
        original_set_entries = page.print_preview.set_entries

        def spy_entries(entries):
            rebuilt.append(len(entries))
            return original_set_entries(entries)

        page.print_preview.set_entries = spy_entries  # type: ignore[method-assign]
        try:
            log_at = len(page.log_view.toPlainText())
            page._compose_imposition_async()  # 真实一轮（增量）
            pump(ctx.app, times=30)
        finally:
            page.print_preview.set_entries = original_set_entries  # type: ignore[method-assign]

        after_mtimes = {
            p.name: p.stat().st_mtime_ns
            for p in out_dir.iterdir() if p.is_file() and p.stem.isdigit()
        }
        ok(
            "只重写被调整的那一页（0002.png 变了）",
            after_mtimes.get("0002.png") != before_mtimes.get("0002.png"),
            f"{before_mtimes.get('0002.png')} -> {after_mtimes.get('0002.png')}",
        )
        untouched = [
            name for name, stamp in before_mtimes.items()
            if name != "0002.png" and after_mtimes.get(name) == stamp
        ]
        ok(
            "其他成品一个字节都没重写",
            len(untouched) == len(before_mtimes) - 1,
            f"未动={untouched} 全部={sorted(before_mtimes)}",
        )
        tail = page.log_view.toPlainText()[log_at:]
        ok(
            "日志点名只重存了第 2 页",
            "拼版成品已重存 1 页（第 2 页）" in tail,
            tail[-200:],
        )
        ok(
            "通知下一步：只刷 0002.png 那一条（不整列重建、不动当前页）",
            rebuilt == [] and page.print_preview.strip.currentRow() == 1,
            f"rebuilt={rebuilt} row={page.print_preview.strip.currentRow()}",
        )
        ok(
            "侧车记下了这一页（下次不再重合成它）",
            page._composed_sigs(sigs_path).get(1)
            == (page_signature(page._imposition_pages()[1]) or ""),
            str(page._composed_sigs(sigs_path)),
        )

        # ⚠️ 跨会话的关键：清空**内存**缓存后，仍要从侧车文件里读回签名
        page._composed_sigs_cache = {}
        page._imposition_page_sigs = {}
        reloaded = page._composed_sigs()
        ok(
            "记录落盘：内存缓存清空后仍读得到（新会话不再整本重合成）",
            reloaded.get(1) == (page_signature(page._imposition_pages()[1]) or ""),
            str(reloaded),
        )
        ok(
            "记录落盘后：没再动版面 → 一页都不用重合成",
            page._stale_imposition_pages() == [],
            str(page._stale_imposition_pages()),
        )

        # ---------------- 通用规则：切步骤时按内容判「要不要强制重装」----------------
        extract_dir = repo.extract_output_dir(tid)
        _mk(extract_dir / "1.png", (120, 120, 120))
        detect_index = page.bar_index_of_step("detect")
        assert detect_index is not None
        forced: list[bool] = []
        original_set_images = page.detect_viewer.set_images

        def spy_images(paths, boxes_map=None, force=False):
            forced.append(bool(force))
            return original_set_images(paths, boxes_map, force)

        page.detect_viewer.set_images = spy_images  # type: ignore[method-assign]
        try:
            page._select_stage(detect_index)  # 首次：记下这次的内容指纹
            forced.clear()
            page._select_stage(detect_index)  # 内容没变 → 不强制重装
            ok(
                "切换步骤：输入产物内容没变 → 不强制重装（省掉整条条目的重解码）",
                forced == [False],
                str(forced),
            )
            _mk(extract_dir / "1.png", (10, 200, 10))  # 同名覆盖
            forced.clear()
            page._select_stage(detect_index)
            ok(
                "切换步骤：上游产物被同名覆盖 → 强制重载最新图",
                forced == [True],
                str(forced),
            )
            tail = page.log_view.toPlainText().split("上游产物已更新", 1)
            ok(
                "切换步骤时把「上一步更新了哪些图片」记进日志",
                len(tail) > 1 and "1.png" in tail[1],
                tail[-1][:120],
            )
        finally:
            page.detect_viewer.set_images = original_set_images  # type: ignore[method-assign]

        page.deleteLater()
        pump(ctx.app, times=4)
        repo.delete_task(tid)
    finally:
        if page is not None:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(tmp, ignore_errors=True)
