# -*- coding: utf-8 -*-
"""第四步 PDF 兑现第二步「提交本次任务」的逐框裁剪产物（端到端）。

2026-10-22 起没有 area：检测出几个文本框，提交阶段就裁几张图
（半幅 ``-r`` / ``-l``，整幅页用页名）。这条链路上任何一环丢框，现象都
长得一样，所以必须端到端钉住，而不是各自测纯函数：

    detect 框 → plan_detect_submit_entries → entry_to_effect_spec
    → run_detect_submit_stage 逐框合成 → stages/detect 成品图
    → 后续去底色提交 → _build_print_effects（整图透传）→ run_print_stage → PDF

⚠️ 2026-10-01 用户口径「去底色那一步，必须提交才能传给下一步」：第四步
只排版「提交本次任务」的成品图。本模块守三件事：

1. **每个框在提交这一跳各自兑现**：双框页必须产出 ``-r`` / ``-l`` 两张，
   尺寸等于 ``compose_region_output(源页, [该框], "0")``；
2. **第四步只透传成品图**：取图规格的 file 全在 ``stages/rembg``、**绝不**指向
   ``stages/rembgpreview``（这就是"编辑去底图不提交不会漏进 PDF"的结构保证），
   worker 实际消费的运行配置同样如此；
3. **PDF 兑现这份成品图**：页数 == 列表条数，该页图片宽高比 == 成品图比例。

依赖 rembg 模块先跑过（DEPENDS）：第三步要有「生成预览」与提交产物。
"""

NAME = "print_area_border_e2e"
DEPENDS: list[str] = ["rembg"]
TITLE = "第四步 PDF 兑现逐框裁剪产物"

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
    _pages = d._manifest_paths()
    ok("（前置）有页面可测", len(_pages) > 0, str(len(_pages)))
    if not _pages:
        return
    _anchor_src = _pages[0]
    _anchor_stem = _anchor_src.stem
    _size = repo.image_size(tid, _anchor_stem) or (1000, 1400)
    _aw, _ah = int(_size[0]), int(_size[1])
    _bl = [round(_aw * 0.10), round(_ah * 0.10),
           round(_aw * 0.46), round(_ah * 0.90)]
    _br = [round(_aw * 0.54), round(_ah * 0.10),
           round(_aw * 0.90), round(_ah * 0.90)]
    repo.save_detect_boxes(tid, _anchor_stem, [_bl, _br], origin="manual")
    d.detect_cache[str(_anchor_src)] = [_bl, _br]

    from PySide6.QtGui import QImage

    from desktop.workers.preview_worker import compose_region_output

    _src = QImage(str(_anchor_src))
    ok("（前置）源页图可读", not _src.isNull(), str(_anchor_src))
    if _src.isNull():
        return

    # ---- 1. 每个框在第二步「提交本次任务」这一跳各自裁剪 ----
    from desktop.services.print_plan import (
        entry_to_effect_spec, plan_detect_submit_entries,
    )
    from desktop.stages import detect_stage

    _entries = plan_detect_submit_entries(
        manifest_paths=[_anchor_src],
        boxes_for=lambda _text: [_bl, _br],
    )
    _mine = [e for e in _entries if Path(e["file"]).stem == _anchor_stem]
    ok("双框页派生两条（-r / -l），各自带一个框",
       len(_mine) == 2
       and {e["label"] for e in _mine} == {f"{_anchor_stem}-r", f"{_anchor_stem}-l"}
       and all(len(e["boxes"]) == 1 for e in _mine),
       str(_mine))
    if len(_mine) != 2:
        return
    _out = Path(ctx.tmp) / "area_e2e" / "detect_final"
    _rc = detect_stage.run_detect_submit_stage({
        "task_id": tid, "stage": "detect_submit", "run_id": "e2e_boxes",
        "args": {
            "_effects": [entry_to_effect_spec(e, "0") for e in _entries],
            "output": str(_out), "clean": True,
        },
    })
    ok("真实提交阶段 exit=0", _rc == 0, f"rc={_rc}")
    for _entry, _box in zip(
        sorted(_mine, key=lambda e: e["label"]),
        sorted([_bl, _br], key=lambda b: b[0], reverse=True),
    ):
        _submitted = _out / f"{_entry['label']}.png"
        ok(f"提交产物存在：{_submitted.name}", _submitted.exists(),
           str(sorted(p.name for p in _out.glob("*.png"))))
        if not _submitted.exists():
            continue
        _ref = compose_region_output(_src, [_box], "0")
        _got = QImage(str(_submitted))
        ok(f"{_entry['label']} 的尺寸 == 该框的紧裁尺寸",
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
    _panel4 = d.control_stack.widget(3)
    _panel4.title_printing.setChecked(False)
    _panel4.pdf_name.setText("area2.pdf")
    d.store.save_print_doc(tid, {"rembg_snapshot": [], "pages": []})
    d._refresh_preview(3)
    d.set_task(tid)
    d._select_stage(d.bar_index_of_step("print"))
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
