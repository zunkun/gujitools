# -*- coding: utf-8 -*-
"""第三步「改参数 / 翻页实时调整当前页」自测。

用户口径（2026-11-04，取代 2026-10-22 那版）：

1. 上一步执行，下一步才有数据；
2. 检测文本框要「检测 + 提交」两步都执行，下游才有数据；
3. 去底色只是切缩略图/改参数时算出来的图**只能在去底色这一步查看**，不能进
   ``stages/rembg``、不能被拼版 / 第四步看到。

所以实时调整只写**预览草稿** ``tasks/<任务号>/preview/rembg[~节点]/<页名>.png``：

- 正式成品 ``stages/rembg[~节点]/<页名>.png`` **一个字节都不动**；
- 第四步缩略图缓存（``thumbnails/print``）、``rembg_methods`` 侧车也不动；
- 「执行去底色」开始时草稿整体清空，由正式阶段重写全部页。

本模块钉住：

1. 改参数触发防抖（不是每拖一格就重算）；
2. 防抖到期只算**当前页**，结果落**草稿目录**，正式成品与下游（第四步取图 /
   缩略图 / 方法侧车）都保持不变；
3. 草稿已是这份参数时不再重算；
4. 逐张 offset 记录（黑名单法）；切图按当前参数补算（已是最新则跳过，
   正式成品缺失时必算——否则中间大图停在原图）；
5. 改过之后再改回去：草稿会被重新算一遍（草稿可反复覆盖，正式成品始终不动）。
"""

NAME = "rembg_live"
DEPENDS: list[str] = ["rembg"]
TITLE = "去底色实时调整"

import time
from pathlib import Path


def _wait(app, cond, timeout: float = 25.0) -> bool:
    """驱动事件循环直到 cond 成立或超时。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def _mtime(path: Path) -> int | None:
    return path.stat().st_mtime_ns if path.is_file() else None


def run(ctx) -> None:
    from desktop.store.json_io import read_json
    from desktop.utils.files import list_stage_images
    from tests.selftests._context import ok, pump

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid

    d.set_task(tid)
    node = d.node_of_stage("rembg")
    # 起点干净：草稿目录清空（可能是上一个模块/上一次运行留下的）
    repo.clear_rembg_preview(tid, node)
    d._select_stage(2)
    pump(app, times=6)

    panel = d.control_stack.widget(2)
    entry_path = d.rembg_viewer.current_entry_path()
    ok("（前置）第三步有可调整的当前页", entry_path is not None, str(entry_path))
    if not entry_path:
        return
    stem = Path(entry_path).stem
    out_dir = Path(repo.rembg_output_dir(tid))
    formal = out_dir / f"{stem}.png"
    preview_dir = Path(repo.rembg_preview_dir(tid, node))
    preview = preview_dir / f"{stem}.png"
    ok("（前置）正式成品存在", formal.is_file(), str(formal))
    if not formal.is_file():
        return
    thumb = repo.rembg_thumbnails_dir(tid, node) / f"{stem}.jpg"
    pages_before = sorted(p.name for p in list_stage_images(out_dir))
    methods_path = repo.task_dir(tid) / "rembg_methods.json"
    methods_before = read_json(methods_path, {})
    # 清掉可能残留的逐张偏移，保证起点是 0（黑名单法：0 = 无记录）。
    scope = d._node_scope(d.current_node())
    repo.save_rembg_offset(tid, stem, 0, **scope)
    d._apply_current_image_offset()
    d._live_done.clear()
    pump(app, times=2)
    formal_mtime_before = formal.stat().st_mtime_ns
    thumb_mtime_before = _mtime(thumb)

    # ---- 1. 改参数 → 防抖 ----
    d._live_timer.stop()
    old_offset = panel.offset.value()
    panel.offset.setValue(old_offset + 17)
    pump(app, times=1, interval=0.0)
    ok("改 offset 触发防抖计时（不是每拖一格都重算）",
       d._live_timer.isActive())

    # ---- 2. 防抖到期只算当前页、落草稿目录（正式成品不动）----
    d._live_timer.stop()
    d._maybe_run_live_preview()
    _wait(app, lambda: stem in d._live_done, timeout=25)
    ok("实时调整只算当前页", len(d._live_done) == 1, str(d._live_done))
    ok("预览草稿已写入 preview 目录", preview.is_file(), str(preview))
    # 与「按当前面板参数跑一遍」的产物**逐字节相等** ⇒ 面板参数（含这张图自己的
    # offset）确实落进了草稿。⚠️ 不能只比"字节变了没有"：纯黑白页换个阈值可能
    # 输出完全一样，那样会把"已经写对了"误判成失败。
    from desktop.services.rembg_live import render_page

    # 参考产物必须与实时任务带**同一套上下文**（上游 detect 的 boxes.json +
    # 逐张算法表）：同页左右裁图合并阈值时，少传任一项都会算出不同阈值。
    ref_args = panel.get_args()
    _boxes_path = d.store.nearest_boxes_path(
        tid, node, d.imposition_effective()
    )
    if _boxes_path is not None:
        ref_args["_boxes_path"] = str(_boxes_path)
    ref_args["algorithms"] = d.store.load_rembg_algorithms(tid, **scope)
    ref = Path(render_page(
        str(entry_path), ref_args, ctx.tmp / "rembg_live_ref"
    ))
    ok("草稿内容 == 当前面板参数的结果（offset 已落实）",
       preview.is_file() and ref.read_bytes() == preview.read_bytes(),
       f"{ref} vs {preview}")
    ok("⚠️ 正式成品一个字节没动（预览不进 stages/rembg）",
       formal.stat().st_mtime_ns == formal_mtime_before, str(formal))
    ok("查看器优先显示这份草稿",
       d.rembg_viewer._result_full_image() == preview,
       str(d.rembg_viewer._result_full_image()))
    ok("该条目解析到去底色结果（中间大图用草稿）",
       d.rembg_viewer._resolve_source(d.rembg_viewer._entries[0])[2] is True,
       str(d.rembg_viewer._resolve_source(d.rembg_viewer._entries[0])))
    ok("正式成品目录没有多出/少掉页面（.part 临时文件已原子改名）",
       sorted(p.name for p in list_stage_images(out_dir)) == pages_before
       and not list(out_dir.glob("*.part")),
       str(sorted(p.name for p in out_dir.iterdir())))
    ok("⚠️ 第四步缩略图没有被预览刷新（下游数据不被草稿污染）",
       _mtime(thumb) == thumb_mtime_before, f"thumb={thumb}")
    ok("⚠️ rembg_methods 侧车没有被预览改写（草稿不算正式执行）",
       read_json(methods_path, {}) == methods_before, str(methods_before))
    entries_now, _doc = d._print_entries()
    mine = next((e for e in entries_now if Path(e["file"]).stem == stem), None)
    ok("⚠️ 第四步取图仍是正式成品（草稿不进下游）",
       mine is not None and Path(mine["file"]) == formal
       and preview not in [Path(e["file"]) for e in entries_now],
       f"mine={None if mine is None else mine['file']} n={len(entries_now)}")

    # ---- 3. 草稿已是这份参数 → 不再重算 ----
    token_before = d._live_token
    preview_mtime = preview.stat().st_mtime_ns
    d._live_timer.stop()
    d._maybe_run_live_preview()
    pump(app, times=2)
    ok("草稿已是这份参数 ⇒ 不再重算",
       d._live_token is token_before
       and preview.stat().st_mtime_ns == preview_mtime)

    # ---- 4. 逐张 offset 记录（黑名单法）----
    d._flush_pending_offset()
    ok("这张图的 offset 已记录",
       repo.rembg_offset(tid, stem, **scope) == old_offset + 17,
       str(repo.load_rembg_offsets(tid, **scope)))
    entries = d.rembg_viewer._entries
    ok("（前置）至少两张图片可切换", len(entries) >= 2, str(len(entries)))
    if len(entries) >= 2:
        other_path = entries[1]["path"]
        other_stem = Path(other_path).stem
        d.rembg_viewer._select_image(1, other_path)
        pump(app, times=6)
        ok("切到别的图片：offset 回到它自己的值（默认 0）",
           panel.offset.value() == 0, str(panel.offset.value()))
        ok("切图不触发二次去底色", other_stem not in d._live_done,
           str(sorted(d._live_done)))
        d.rembg_viewer._select_image(0, entry_path)
        pump(app, times=6)
        ok("切回原图：恢复它记录的 offset",
           panel.offset.value() == old_offset + 17, str(panel.offset.value()))
        ok("切回原图：显示的仍是它自己的草稿",
           d.rembg_viewer._result_full_image() == preview,
           str(d.rembg_viewer._result_full_image()))

        # ---- 4b. 逐张算法：改下拉 → 实时预览 → 落盘 → 切页回落 ----
        panel.algorithm.setCurrentIndex(panel.algorithm.findData("sauvola"))
        pump(app, times=1, interval=0.0)
        ok("改算法触发实时预览防抖", d._live_timer.isActive())
        d._live_timer.stop()
        d._maybe_run_live_preview()
        _wait(app, lambda: (d._live_done.get(stem) or {}).get("algorithm")
              == "sauvola", timeout=40)
        d._flush_pending_offset()
        ok("选中算法后实时预览用的是新算法",
           (d._live_done.get(stem) or {}).get("algorithm") == "sauvola",
           str(d._live_done.get(stem)))
        ok("逐张算法已落盘（只记当前这张图）",
           repo.rembg_algorithm(tid, stem, **scope) == "sauvola"
           and repo.rembg_algorithm(tid, other_stem, **scope) == "otsu",
           str(repo.load_rembg_algorithms(tid, **scope)))
        ok("⚠️ 预览不改正式执行记录（rembg_methods 保持上一轮全量的值）",
           read_json(methods_path, {}) == methods_before,
           str(read_json(methods_path, {})))
        d.rembg_viewer._select_image(1, other_path)
        pump(app, times=6)
        ok("切到没单独设过算法的页：回落默认 Otsu",
           panel._combo_value(panel.algorithm) == "otsu",
           str(panel._combo_value(panel.algorithm)))
        d.rembg_viewer._select_image(0, entry_path)
        pump(app, times=6)
        ok("切回原图：恢复它记录的算法",
           panel._combo_value(panel.algorithm) == "sauvola",
           str(panel._combo_value(panel.algorithm)))
        # 收尾：把这张图恢复成默认算法，避免影响后续模块的全量执行
        d.store.save_rembg_algorithm(tid, stem, "otsu", **scope)

        # 用户 2026-10-23：切到**没有成品**的页（新占位图 / 上游换了页名）
        # 必须按当前参数自动补算，否则中间大图停在原图、看不到去底色效果。
        # ⚠️ 2026-11-04：补出来的仍然是**草稿**——正式成品目录里依然没有这一页，
        # 下游也就不会凭空多出一张没人"执行"过的图。
        if len(entries) >= 3:
            page3 = entries[2]["path"]
            page3_stem = Path(page3).stem
            page3_formal = out_dir / f"{page3_stem}.png"
            page3_preview = preview_dir / f"{page3_stem}.png"
            ok("（前置）第三张有正式成品", page3_formal.is_file(), str(page3_formal))
            if page3_formal.is_file():
                page3_formal.unlink()
                d.rembg_viewer._select_image(1, other_path)
                pump(app, times=4)
                d.rembg_viewer._select_image(2, page3)
                _wait(app, lambda: page3_stem in d._live_done, timeout=40)
                ok("切到没有成品的页：自动按当前参数补算并落草稿",
                   page3_preview.is_file(), str(page3_preview))
                ok("⚠️ 补算后正式成品目录里依然没有这一页（草稿不是正式产物）",
                   not page3_formal.exists(), str(page3_formal))
                ok("补算后该条目解析到去底色结果（中间大图用草稿）",
                   d.rembg_viewer._resolve_source(entries[2])[2] is True,
                   str(d.rembg_viewer._resolve_source(entries[2])))
                d.rembg_viewer._select_image(0, entry_path)
                pump(app, times=6)

                # 改全局参数（type）后切图：目标页也必须按新参数重算，
                # 否则中间大图停在"上次全量执行"的旧成品上（实时效果不跟着走）。
                target_path = entries[1]["path"]
                target_stem = Path(target_path).stem
                target_formal = out_dir / f"{target_stem}.png"
                target_preview = preview_dir / f"{target_stem}.png"
                target_formal_mtime = _mtime(target_formal)
                old_type_index = panel.type.currentIndex()
                panel.type.setCurrentIndex(0 if old_type_index != 0 else 1)
                new_type = int(panel._combo_value(panel.type))
                pump(app, times=2)
                d.rembg_viewer._select_image(1, target_path)
                # ⚠️ 等**台账**落地而不是只等文件：文件由 worker 线程写，
                #    记账/刷新要等排队回主线程，只等文件会读到"还没记账"。
                _wait(app, lambda: target_stem in d._live_done, timeout=40)
                ok("改参数后切图：目标页按新参数重算（不是旧成品）",
                   target_stem in d._live_done and target_preview.is_file(),
                   f"{target_stem} in {sorted(d._live_done)}")
                ok("重算用的确实是新 type",
                   (d._live_done.get(target_stem) or {}).get("type") == new_type,
                   str(d._live_done.get(target_stem)))
                ok("⚠️ 目标页的正式成品同样没被预览覆盖",
                   _mtime(target_formal) == target_formal_mtime,
                   str(target_formal))
                panel.type.setCurrentIndex(old_type_index)
                d._live_timer.stop()
                d.rembg_viewer._select_image(0, entry_path)
                pump(app, times=6)

    # ---- 5. 改回去 → 草稿被重新算一遍（正式成品始终不动）----
    mid_mtime = preview.stat().st_mtime_ns
    snapshot = d._formal_snapshot_for(stem)
    ok("（前置）能取到该图上次全量执行的参数快照", snapshot is not None, str(snapshot))
    if snapshot is not None:
        # 模拟用户把 offset 拖回原值（走用户信号，才能验证 offset 0 的删除）
        panel.offset.setValue(int(snapshot.get("offset") or 0))
        pump(app, times=1, interval=0.0)
        d._live_timer.stop()
        d._maybe_run_live_preview()
        # ⚠️ 等**台账**落地而不是只等文件：文件由 worker 线程写，记账要等排队
        #    回主线程；只等 mtime 会读到"文件已新、台账还没更新"的中间态。
        _wait(app, lambda: (
            preview.stat().st_mtime_ns > mid_mtime
            and (d._live_done.get(stem) or {}) == d._live_snapshot(panel.get_args())
        ), timeout=40)
        d._flush_pending_offset()
        pump(app, times=4)
        ok("改回去：草稿按原参数重算（草稿可反复覆盖）",
           preview.stat().st_mtime_ns > mid_mtime, str(preview))
        ok("⚠️ 正式成品仍与预览无关（mtime 未动）",
           formal.stat().st_mtime_ns == formal_mtime_before, str(formal))
        ok("盘上台账已跟到新参数",
           d._live_done.get(stem) == d._live_snapshot(panel.get_args()),
           f"ledger={d._live_done.get(stem)} "
           f"panel={d._live_snapshot(panel.get_args())} "
           f"pending={d._live_pending} "
           f"log={d.log_view.toPlainText()[-400:]}")
        ok("offset 回到 0 后从黑名单里删除",
           repo.rembg_offset(tid, stem, **scope) == 0,
           str(repo.load_rembg_offsets(tid, **scope)))

    # 收尾：台账与草稿都别留给后续模块
    d._reset_rembg_live()
    repo.clear_rembg_preview(tid, node)
