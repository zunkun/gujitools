# -*- coding: utf-8 -*-
"""第四步 PDF 兑现第三步的 area/border —— 经由「提交本次任务」（端到端）。

背景：用户报「第三步 area=2、第四步预览也是 area=2，生成出来的 PDF 却是
area=1 的效果」。这条链路上任何一环丢参数，现象都长得一样，所以必须端到端
钉住，而不是各自测纯函数：

    rembg 面板 area/border → plan_rembg_submit_entries → entry_to_effect_spec
    → run_rembg_submit_stage 合成 → stages/rembg 成品图
    → _build_print_effects（整图透传）→ run_print_stage → PDF

⚠️ 2026-10-01 用户口径「去底色那一步，必须提交才能传给下一步」：第四步
**不再**拿去底图（``stages/rembgpreview``）按**当前** area/border 现场合成，
只排版「提交本次任务」的成品图。本模块守三件事：

1. **area/border 在提交这一跳兑现**：用真实提交阶段函数按 area=2 + border=30
   合成，成品图尺寸必须等于 ``compose_region_output(去底图, 原双框, 2, "30")``
   （area 被写成 1 会紧裁，尺寸不同 → 断言红）；
2. **第四步只透传成品图**：取图规格的 file 全在 ``stages/rembg``、**绝不**指向
   ``stages/rembgpreview``（这就是"编辑去底图不提交不会漏进 PDF"的结构保证），
   worker 实际消费的运行配置同样如此；
3. **PDF 兑现这份成品图**：页数 == 列表条数，该页图片宽高比 == 成品图比例。

依赖 rembg 模块先跑过（DEPENDS）：第三步要有「生成预览」与提交产物。
"""

NAME = "print_area_border_e2e"
DEPENDS: list[str] = ["rembg"]
TITLE = "第四步 PDF 兑现提交产物的 area/border"

import time


def run(ctx) -> None:
    from pathlib import Path

    import pymupdf

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    preview_dir = repo.rembg_preview_output_dir(tid)
    final_dir = repo.rembg_output_dir(tid)

    d.set_task(tid)
    d._select_stage(d.bar_index_of_step("print"))

    # ⚠️ 检测框必须**本模块自己注入**：ctx.injected_boxes 是 rembg 模块留下的
    # 跨模块状态，全量跑时会被其它模块（detect 注入的确定性框）覆盖，
    # 依赖它就会出现「单独跑绿、全量跑红」这种最难查的假绿。
    _comp0 = d._rembg_submit_entries(1, None)
    ok("（前置）有待提交条目", len(_comp0) > 0, str(len(_comp0)))
    if not _comp0:
        return
    _anchor_stem = Path(_comp0[0]["file"]).stem
    _size = repo.image_size(tid, _anchor_stem) or (1000, 1400)
    _aw, _ah = int(_size[0]), int(_size[1])
    # 双框（半幅页两栏）：用户报的正是「双框 + area=2」这条——单框走的是
    # 对称画布那条分支，只测单框会完全漏掉现象。
    _bl = [round(_aw * 0.10), round(_ah * 0.10),
           round(_aw * 0.46), round(_ah * 0.90)]
    _br = [round(_aw * 0.54), round(_ah * 0.10),
           round(_aw * 0.90), round(_ah * 0.90)]
    repo.save_detect_boxes(tid, _anchor_stem, [_bl, _br], origin="manual")
    _anchor_src = next(p for p in d._manifest_paths()
                       if p.stem == _anchor_stem)
    d.detect_cache[str(_anchor_src)] = [_bl, _br]

    from PySide6.QtGui import QImage

    from desktop.workers.preview_worker import compose_region_output

    _src = QImage(str(preview_dir / f"{_anchor_stem}.png"))
    ok("（前置）去底图可读", not _src.isNull(),
       str(preview_dir / f"{_anchor_stem}.png"))
    if _src.isNull():
        return

    # ---- 1. area/border 在「提交本次任务」这一跳兑现 ----
    # ⚠️ 用**临时输出目录**跑真实提交阶段函数：本模块与其它模块共用 ctx.tid，
    # 真去提交会把共享的 stages/rembg 换掉，影响后面模块的页数断言。
    from desktop.services.print_plan import entry_to_effect_spec
    from desktop.stages import rembg_stage

    _entries_a2 = d._rembg_submit_entries(2, "30")
    _anchor_entry = next(
        (e for e in _entries_a2 if Path(e["file"]).stem == _anchor_stem), None)
    ok("（前置）area=2 的派生条目带原始双框（不是并集降级）",
       _anchor_entry is not None and len(_anchor_entry["boxes"]) == 2
       and _anchor_entry["parea"] == 2, str(_anchor_entry))
    if _anchor_entry is None:
        return
    _out = Path(ctx.tmp) / "area_border_e2e" / "rembg_final"
    _rc = rembg_stage.run_rembg_submit_stage({
        "task_id": tid, "stage": "rembg_submit", "run_id": "e2e_area2",
        "args": {
            "_effects": [entry_to_effect_spec(e, "30") for e in _entries_a2],
            "output": str(_out), "clean": True,
        },
    })
    ok("真实提交阶段 exit=0", _rc == 0, f"rc={_rc}")
    _submitted = _out / f"{_anchor_stem}.png"  # area=2 双框并成一条，无后缀
    ok("双框 + area=2 → 成品图并成一条（不带 -l/-r 后缀）",
       _submitted.exists(), str(sorted(p.name for p in _out.glob("*.png"))))
    if not _submitted.exists():
        return
    # 第三步预览语义：原始框 + 原始 area（与 entry_to_effect_spec 同源）
    _ref = compose_region_output(_src, [_bl, _br], 2, "30")
    _got = QImage(str(_submitted))
    ok("成品图尺寸 == 按 area=2/border=30 合成的尺寸（area 没被降级成 1）",
       len(_ref) == 1
       and (_got.width(), _got.height()) == (_ref[0].width(), _ref[0].height()),
       f"got={(_got.width(), _got.height())} "
       f"ref={(_ref[0].width(), _ref[0].height())}")

    # ---- 2. 第四步只透传成品图（「必须提交才传给下一步」的结构保证）----
    _entries, _doc = d._print_entries()
    _fx = d._build_print_effects(_entries)
    ok("第四步取图规格 = 提交产物整图透传（effect 全 None）",
       len(_fx) == len(_entries) > 0
       and all(e["effect"] is None for e in _fx),
       str([e["effect"] for e in _fx][:2]))
    ok("取图全在提交产物目录、绝不指向去底图"
       "（编辑去底色结果不提交就不会漏进 PDF）",
       {str(Path(e["file"]).parent) for e in _fx} == {str(final_dir)}
       and all(str(Path(e["file"]).parent) != str(preview_dir) for e in _fx),
       str(sorted({str(Path(e["file"]).parent) for e in _fx})))

    # ---- 3. 真跑一次 print：PDF 的图就是提交产物 ----
    _panel3 = d.control_stack.widget(2)
    _panel3.area.setCurrentIndex(1)   # area=2（若旧实现按当前参数现算，比例会变）
    _panel3.border.setText("30")
    app.processEvents()
    _panel4 = d.control_stack.widget(3)
    _panel4.title_printing.setChecked(False)
    _panel4.pdf_name.setText("area2.pdf")
    d.store.save_print_doc(tid, {"rembg_snapshot": [], "pages": []})
    d._refresh_preview(3)
    d.set_task(tid)
    d._select_stage(d.bar_index_of_step("print"))
    _panel3 = d.control_stack.widget(2)
    _panel3.area.setCurrentIndex(1)
    _panel3.border.setText("30")
    app.processEvents()
    _entries_now, _ = d._print_entries()
    ok("（前置）待打印列表非空", len(_entries_now) > 0, str(len(_entries_now)))

    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    _state = repo.stage_states(tid)["print"]
    ok("print 执行成功", _state["status"] == "success", str(_state))
    for _ in range(15):
        app.processEvents()
        time.sleep(0.1)

    # ⚠️ 读 worker 实际消费的运行配置（run-<run_id>.json），不查 runs.json：
    #    2026-09-26 起入史前剥离 _effects/files/page_rects（写放大治理）
    import json as _json

    _run_id = repo.list_stage_runs(tid, "print")[0]["run_id"]
    _run_cfg = _json.loads(
        (repo.runs_config_dir(tid) / f"run-{_run_id}.json").read_text(encoding="utf-8")
    )
    _saved_fx = _run_cfg["args"].get("_effects") or []
    ok("worker 消费的取图 = 提交产物（不再携带区域合成规格）",
       bool(_saved_fx)
       and all(s.get("effect") is None for s in _saved_fx)
       and {str(Path(s["file"]).parent) for s in _saved_fx} == {str(final_dir)},
       f"effects={[s.get('effect') for s in _saved_fx][:2]} "
       f"dirs={sorted({str(Path(s['file']).parent) for s in _saved_fx})}")
    _spec = next(
        (s for s in _saved_fx if Path(s["file"]).stem == _anchor_stem), None)
    ok("PDF 取图里仍有注入框那一页", _spec is not None,
       str([Path(s["file"]).stem for s in _saved_fx][:5]))
    if _spec is None:
        return
    _idx = _saved_fx.index(_spec)

    _pdf = d._latest_print_pdf_path()
    ok("生成了 PDF", _pdf is not None and _pdf.exists(), str(_pdf))
    if _pdf is None or not _pdf.exists():
        return
    _pdfdoc = pymupdf.open(str(_pdf))
    ok("PDF 页数与列表一致", _pdfdoc.page_count == len(_saved_fx),
       f"{_pdfdoc.page_count} vs {len(_saved_fx)}")
    _info = _pdfdoc[_idx].get_image_info()
    ok("PDF 该页含图片", len(_info) >= 1, str(len(_info)))
    if _info:
        _bbox = _info[0]["bbox"]
        _pw = _bbox[2] - _bbox[0]
        _ph = _bbox[3] - _bbox[1]
        _final_img = QImage(_spec["file"])
        ok("PDF 图片宽高比 == 提交产物比例（用提交成品图，而非按当前参数现算）",
           _pw > 0 and _ph > 0 and not _final_img.isNull()
           and abs((_pw / _ph)
                   - (_final_img.width() / _final_img.height())) < 0.02,
           f"pdf={_pw:.1f}x{_ph:.1f} "
           f"final={_final_img.width()}x{_final_img.height()}")
    _pdfdoc.close()
