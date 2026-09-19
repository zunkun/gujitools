# -*- coding: utf-8 -*-
"""第四步生成的 PDF 必须兑现第三步的 area/border（端到端，不只测纯函数）。

背景：用户报「第三步 area=2、第四步预览也是 area=2，生成出来的 PDF 却是
area=1 的效果」。这条链路上任何一环丢参数，现象都长得一样——所以必须端到端
钉住，而不是各自测纯函数：

    rembg 面板 area/border → _build_print_effects → args["_effects"]
    → run_print_stage 子进程内 compose_region_output 实时合成
    → files 覆盖 → CLI print 排版成 PDF

本模块守三件事：
1. **area 真传到合成规格**：单框 + area=2 → ``effect.area == 2``（走对称画布）；
   改 border 无需重新提交即生效；
2. **PDF 里的图片就是按这份规格合成的**：用 ``compose_region_output`` 现场算出
   参考图，比对 PDF 中该页图片的**宽高比**（排版保比例，故比例必须一致）。
   若 area 被写成 1，合成结果不同 → 比例对不上 → 断言红；
3. **页序不丢**：PDF 页数 == 列表条数。

依赖 rembg 注入的检测框 ``ctx.injected_boxes`` 与 ``ctx.preview_dir``。
"""

NAME = "print_area_border_e2e"
DEPENDS: list[str] = ["rembg"]
TITLE = "第四步 PDF 兑现第三步 area/border"

import time


def run(ctx) -> None:
    from pathlib import Path

    import pymupdf

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    preview_dir = repo.rembg_preview_output_dir(tid)

    d.set_task(tid)
    d._select_stage(3)

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
    _injected = [round(_aw * 0.10), round(_ah * 0.10),
                 round(_aw * 0.55), round(_ah * 0.90)]
    repo.save_detect_boxes(tid, _anchor_stem, [_injected, None],
                           origin="manual")
    _anchor_src = next(p for p in d._manifest_paths()
                       if p.stem == _anchor_stem)
    d.detect_cache[str(_anchor_src)] = [_injected, None]

    _fx_area1 = d._build_print_effects(d._print_entries()[0], 1, None)
    _anchor = next(
        (s for s in _fx_area1
         if Path(s["file"]).stem == _anchor_stem and s.get("effect")),
        None,
    )
    ok("（前置）注入的检测框进了合成规格",
       _anchor is not None and _anchor["effect"]["boxes"] == [_injected],
       str([s.get("effect") for s in _fx_area1])[:200])
    if _anchor is None:
        return

    # ---- 1. 双框页：area 决定"分不分栏"（用户报的就是这条）----
    # 单框走对称画布，双框才是真正的「分栏」语义：area=1 拆左右两条，
    # area=2/3 并成一条。只测单框会完全漏掉用户报的现象。
    _manifest = d._manifest_paths()
    _other_src = next(
        (p for p in _manifest
         if p.stem != _anchor_stem
         and (repo.rembg_preview_output_dir(tid) / f"{p.stem}.png").exists()),
        None)
    ok("（前置）拿得到另一页做双框注入", _other_src is not None)
    if _other_src is not None:
        _ostem = _other_src.stem
        _osize = repo.image_size(tid, _ostem) or (1000, 1400)
        _ow, _oh = int(_osize[0]), int(_osize[1])
        _bl = [round(_ow * 0.08), round(_oh * 0.15),
               round(_ow * 0.48), round(_oh * 0.85)]
        _br = [round(_ow * 0.52), round(_oh * 0.15),
               round(_ow * 0.92), round(_oh * 0.85)]
        repo.save_detect_boxes(tid, _ostem, [_bl, _br], origin="manual")
        d.detect_cache[str(_other_src)] = [_bl, _br]
        _entries_x, _ = d._print_entries()

        _fx_a1 = d._build_print_effects(_entries_x, 1, "30")
        _o1 = [s for s in _fx_a1
               if Path(s["file"]).stem == _ostem
               and s.get("effect")]
        ok("双框 + area=1 → 拆成左右两条（页序里出现 2 条）",
           len(_o1) == 2
           and {s["label"] for s in _o1} == {f"{_ostem}-r", f"{_ostem}-l"},
           f"{len(_o1)} 条 labels={[s['label'] for s in _o1]}")

        # ⚠️ 真正的判据不是"boxes 长什么样"，而是**合成结果必须与第三步
        # 预览一致、且只有一张**。曾把双框 area=2/3 记成"并集框 + area=1"，
        # 条目数同样是对的（1 条），但 border 为空时会被紧裁成框——而预览
        # 走的是「整页画布 + 内容写回原位」，于是 PDF 看着像 area=1。
        from PySide6.QtGui import QImage

        from desktop.workers.preview_worker import compose_region_output

        _src2 = QImage(str(preview_dir / f"{_ostem}.png"))
        ok("（前置）双框页源图可读", not _src2.isNull(),
           str(preview_dir / f"{_ostem}.png"))

        for _area, _label in ((2, "area=2"), (3, "area=3")):
            _fx = d._build_print_effects(_entries_x, _area, "30")
            _o = [s for s in _fx
                  if Path(s["file"]).stem == _ostem and s.get("effect")]
            if not _o:
                ok(f"双框 + {_label} → 并成一条", False, "0 条")
                continue
            # 第三步预览语义：原始框 + 原始 area
            _ref = compose_region_output(_src2, [_bl, _br], _area, "30")
            _eff = _o[0]["effect"]
            _got = compose_region_output(
                _src2, _eff["boxes"], _eff["area"], _eff["border"])
            ok(f"双框 + {_label} → 并成一条且与第三步预览同尺寸",
               len(_o) == 1 and len(_got) == 1 and len(_ref) == 1
               and (_got[0].width(), _got[0].height())
               == (_ref[0].width(), _ref[0].height()),
               f"{len(_o)} 条 got={[(o.width(), o.height()) for o in _got]} "
               f"ref={[(o.width(), o.height()) for o in _ref]}")
            ok(f"双框 + {_label} 的合成规格携带原始 area（不是降级成 1）",
               _eff["area"] == _area and len(_eff["boxes"]) == 2,
               str(_eff))

        # ---- 1b. border 为空才是用户实际踩到的分支：整页而非紧裁 ----
        _fx_none = d._build_print_effects(_entries_x, 2, None)
        _on = [s for s in _fx_none
               if Path(s["file"]).stem == _ostem and s.get("effect")]
        if _on:
            _ref_n = compose_region_output(_src2, [_bl, _br], 2, None)
            _en = _on[0]["effect"]
            _got_n = compose_region_output(
                _src2, _en["boxes"], _en["area"], _en["border"])
            # border 为空时 area=2 的语义就是「整页画布 + 内容写回原位」，
            # 所以画布尺寸应当等于**整页去底图**本身，而不是被紧裁成框。
            # （别拿并集宽当参照：注入框按另一份尺寸算，可能比图还宽。）
            ok("双框 + area=2 + 无 border → 整页写回原位（不是紧裁成并集框）",
               len(_got_n) == 1
               and (_got_n[0].width(), _got_n[0].height())
               == (_src2.width(), _src2.height()),
               f"got={(_got_n[0].width(), _got_n[0].height())} "
               f"整页={(_src2.width(), _src2.height())}")

    # ---- 2. 单框页：area / border 真传到合成规格 ----
    _fx2 = d._build_print_effects(d._print_entries()[0], 2, "30")
    _a2 = next(s for s in _fx2 if Path(s["file"]).stem == _anchor_stem)
    ok("area=2 时合成规格携带 area=2（单框走对称画布）",
       _a2["effect"]["area"] == 2 and _a2["effect"]["boxes"] == [_injected]
       and _a2["effect"]["border"] == "30", str(_a2["effect"]))
    ok("area=2 合成规格的源图仍是 rembgpreview 去底图",
       Path(_a2["file"]).parent == preview_dir, str(_a2["file"]))
    ok("area 改回 1 合成规格随即变回 1",
       next(s for s in d._build_print_effects(
           d._print_entries()[0], 1, "30")
           if Path(s["file"]).stem == _anchor_stem)["effect"]["area"] == 1)

    # ---- 2. 按 area=2 + border=30 真跑一次 print ----
    _rembg_panel = d.control_stack.widget(2)
    _rembg_panel.area.setCurrentIndex(1)  # area=2
    _rembg_panel.border.setText("30")
    app.processEvents()
    _panel4 = d.control_stack.widget(3)
    _panel4.title_printing.setChecked(False)
    _panel4.pdf_name.setText("area2.pdf")
    d.store.save_print_doc(tid, {"rembg_snapshot": [], "pages": []})
    d._refresh_preview(3)
    d.set_task(tid)
    d._select_stage(3)
    _rembg_panel = d.control_stack.widget(2)
    _rembg_panel.area.setCurrentIndex(1)
    _rembg_panel.border.setText("30")
    app.processEvents()
    _entries_now, _ = d._print_entries()
    ok("（前置）待打印列表非空", len(_entries_now) > 0, str(len(_entries_now)))

    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    _state = repo.stage_states(tid)["print"]
    ok("area=2 的 print 执行成功", _state["status"] == "success", str(_state))
    for _ in range(15):
        app.processEvents()
        time.sleep(0.1)

    _saved = repo.list_stage_runs(tid, "print")[0]["parameters"]
    _saved_fx = _saved.get("_effects") or []
    ok("print 运行配置携带 area=2 / border=30 的实时合成规格",
       any(s.get("effect") and s["effect"].get("area") == 2
           and s["effect"].get("border") == "30" for s in _saved_fx),
       str([s.get("effect") for s in _saved_fx])[:300])

    # ---- 3. PDF 里的图就是按这份规格合成的（比宽高比）----
    from PySide6.QtGui import QImage

    from desktop.workers.preview_worker import compose_region_output

    _spec = next((s for s in _saved_fx
                  if s.get("effect")
                  and Path(s["file"]).stem == _anchor_stem), None)
    ok("PDF 合成规格里仍有注入框那一页", _spec is not None,
       str([Path(s["file"]).stem for s in _saved_fx]))
    if _spec is None:
        return
    _src = QImage(_spec["file"])
    ok("（前置）源图可读", not _src.isNull(), _spec["file"])
    _ref = compose_region_output(
        _src, _spec["effect"]["boxes"],
        int(_spec["effect"]["area"]), _spec["effect"]["border"],
    )[0]
    _idx = _saved_fx.index(_spec)

    _pdf = d._latest_print_pdf_path()
    ok("生成了 PDF", _pdf is not None and _pdf.exists(), str(_pdf))
    if _pdf is None or not _pdf.exists():
        return
    _doc = pymupdf.open(str(_pdf))
    ok("PDF 页数与列表一致", _doc.page_count == len(_saved_fx),
       f"{_doc.page_count} vs {len(_saved_fx)}")
    _info = _doc[_idx].get_image_info()
    ok("PDF 该页含图片", len(_info) >= 1, str(len(_info)))
    if _info:
        _bbox = _info[0]["bbox"]
        _pw = _bbox[2] - _bbox[0]
        _ph = _bbox[3] - _bbox[1]
        ok("PDF 图片宽高比 == 按 area/border 合成结果的宽高比（兑现第三步设置）",
           _pw > 0 and _ph > 0
           and abs((_pw / _ph) - (_ref.width() / _ref.height())) < 0.02,
           f"pdf={_pw:.1f}x{_ph:.1f} ref={_ref.width()}x{_ref.height()}")
    _doc.close()
