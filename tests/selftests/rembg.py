# -*- coding: utf-8 -*-
"""rembg 阶段自测：生成预览/提交、分段开关、area=1 拆分契约、实时合成规格。

产出跨模块状态：``ctx.injected_boxes``（注入的确定性检测框）与
``ctx.preview_dir``（预览目录），print 模块的合成断言依赖二者。
"""

NAME = "rembg"
DEPENDS: list[str] = ["detect"]
TITLE = "rembg"


def run(ctx) -> None:
    from pathlib import Path

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton, QWidget

    from desktop.ui.widgets import SegmentedToggle
    from desktop.workers import ImageListWorker
    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    img = ctx.inserted_img

    d.set_task(tid)
    d._select_stage(2)
    ok("步骤三主按钮为生成预览", d.run_button.text() == "生成预览")
    ok("未生成预览前提交按钮禁用", not d.submit_button.isEnabled())
    d.run_rembg_submit()  # 直接调用也必须被拦截，不启动子进程
    ok("未成功生成预览时提交不启动", d.process is None)
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["rembg"]
    ok("rembg 预览成功", state["status"] == "success", str(state))
    preview_dir = repo.rembg_preview_output_dir(tid)
    ctx.preview_dir = preview_dir
    # rembg 直接处理 extract 目录里的**全部**图片：6 张原页 + pages 模块
    # 插入的 1 张（已被复制进 extract）。注意 pages 模块删掉的那一页只是
    # 从清单移除，物理文件仍在目录里，因此这里数是 7 而非清单的 6。
    ok("预览图落在 stages/rembgpreview",
       preview_dir.exists() and len(list(preview_dir.glob("*.png"))) == 7,
       str(sorted(p.name for p in preview_dir.glob("*.png")))
       if preview_dir.exists() else str(preview_dir))
    final_dir = repo.rembg_output_dir(tid)
    ok("提交前 stages/rembg 为空",
       not final_dir.exists() or not any(final_dir.glob("*.png")))
    ok("预览成功后提交按钮可用", d.submit_button.isEnabled())
    ok("预览成功即提示有新版本待提交",
       d._rembg_submit_version_state() == "new_version"
       and "有新版本" in d.submit_button.text()
       and not d.submit_hint.isHidden() and "#c0392b" in d.submit_hint.styleSheet())

    # --- 第三步条目缩略图必须按 area=1 拆分，只显示所属半页 ---
    # 曾出错：_page_thumb_for 返回 {"path","effect"}，而 RembgPreviewWidget 读的是
    # spec["crop"]（永远为 None），于是 -r/-l 两条缩略图都退化成整页。
    # 自测页面是空白页（pymupdf 默认字体渲染不出中文），像素比对分不出左右半页，
    # 所以这里校验数据契约：provider 必须给 effect，查看器必须把 effect 交给合成器。
    _last_page = d._manifest_paths()[-1]
    _orig_entry = repo.detect_boxes_entry(tid, _last_page.stem)
    _lw, _lh = repo.image_size(tid, _last_page.stem)
    _lbox = [0, 0, _lw // 2, _lh]
    _rbox = [_lw // 2, 0, _lw, _lh]
    repo.save_detect_boxes(tid, _last_page.stem, [_lbox, _rbox], origin="manual")
    d.detect_cache[str(_last_page)] = [_lbox, _rbox]
    # 走真实的「改 area → 面板联动 → refresh_display」链路（label 随之变化才重建）
    _rembg_panel = d.control_stack.widget(2)
    _rembg_panel.area.setCurrentIndex(1)  # area=2 → 该页合成单条
    app.processEvents()
    _rembg_panel.area.setCurrentIndex(0)  # area=1 → 拆成 -r / -l 两条
    app.processEvents()

    _rv = d.rembg_viewer
    _pair = [(i, e) for i, e in enumerate(_rv._entries)
             if e["path"] == str(_last_page)]
    ok("area=1 该页拆成 -r/-l 两条目",
       [e["label"] for _, e in _pair] == [f"{_last_page.stem}-r", f"{_last_page.stem}-l"],
       str([e["label"] for _, e in _pair]))

    # provider 给出的 effect 必须只覆盖该条目自己那一半（而非整页/并集）
    _spec_r = d._page_thumb_for(str(_last_page), _rbox, 1, None)
    _thumb_size = QImage(_spec_r["path"]).size()
    _box_r = _spec_r["effect"]["boxes"][0]
    ok("area=1 缩略图 effect 只覆盖所属半页",
       abs(_box_r[0] - _thumb_size.width() / 2) <= 2
       and abs(_box_r[2] - _thumb_size.width()) <= 2,
       f"框 {_box_r} / 缩略图 {_thumb_size.width()}x{_thumb_size.height()}")

    # 查看器必须把 effect 交给 ImageListWorker 走区域合成，而不是传像素裁剪 crops
    _seen: list[dict] = []
    _real_init = ImageListWorker.__init__

    def _spy_init(self, paths, edge=96, effects=None, crops=None):
        _seen.append({"n": len(paths), "effects": effects, "crops": crops})
        _real_init(self, paths, edge=edge, effects=effects, crops=crops)

    ImageListWorker.__init__ = _spy_init
    try:
        _rv._load_page_thumbs(_rv._entries)
    finally:
        ImageListWorker.__init__ = _real_init
    _last_call = _seen[-1]
    ok("area=1 缩略图交给合成器的是 effect（不是 crops）",
       _last_call["crops"] is None
       and _last_call["effects"] is not None
       and len(_last_call["effects"]) == len(_rv._entries)
       and all(e and e.get("boxes") for e in
               (_last_call["effects"][i] for i, _e in _pair)),
       f"crops={_last_call['crops']} effects={_last_call['effects']}")

    # --- 第三步「去底色结果 / 原图」改用分段开关，不再用两个硬编码蓝按钮 ---
    # 原先是一对 PushButton + 一段写死 #0078d4 的样式表，和主题色（深青）打架，
    # 两个按钮之间还有缝，看着像两颗不相干的按钮而不是一组开关。
    _tg = _rv.toggle
    ok("去底色预览用分段开关切换「去底色结果 / 原图」",
       isinstance(_tg, SegmentedToggle)
       and [text for _key, text in _tg._items] == ["去底色结果", "原图"],
       str(getattr(_tg, "_items", None)))
    ok("分段开关固定高与控件常量一致（未 show 也能取到真实高度）",
       _tg.height() == SegmentedToggle.HEIGHT == 30, f"{_tg.height()}")
    # 选中态必须一眼看得出：轨道要比白滑块明显更深。曾用 SURFACE_SOFT 当轨道，
    # 近白轨道 + 白滑块几乎分不出哪边是选中的（用户反馈「要有对比度」）。
    # 直接离屏渲染采样像素：段宽由控件自己算，取「未选中段靠上沿」和
    # 「选中段左侧避开文字」两点，比平均亮度。
    _seg_widths = _tg._segment_widths()
    _old_size = _tg.size()
    _tg.resize(_tg.minimumSizeHint())
    app.processEvents()
    _shot = _tg.grab().toImage()
    _track_px = _shot.pixelColor(2 + _seg_widths[0] + _seg_widths[1] // 2, 4)
    _thumb_px = _shot.pixelColor(2 + 10, SegmentedToggle.HEIGHT // 2)
    _tg.resize(_old_size)
    _gap = (sum(_thumb_px.getRgb()[:3]) - sum(_track_px.getRgb()[:3])) // 3
    ok("分段开关轨道比选中滑块明显更深（选中态有对比度）",
       _gap >= 12 and min(_thumb_px.getRgb()[:3]) >= 250,
       f"轨道 {_track_px.name()} / 滑块 {_thumb_px.name()}，平均亮度差 {_gap}")
    ok("有去底色结果时「去底色结果」项可用且默认选中（结果优先）",
       _tg.is_item_enabled("result") and _tg.current() == "result",
       f"enabled={_tg.is_item_enabled('result')} current={_tg.current()}")
    # 无结果：禁用该项并停在「原图」，但用户的偏好（_mode）不能被改写——
    # 否则结果一生成就会停在原图上，丢掉「默认看去底色结果」的行为
    _saved_dir = _rv._rembg_dir
    _rv._rembg_dir = None
    _rv._sync_toggle(_rv._result_full_image() is not None)
    ok("无去底色结果时分段开关禁用「去底色结果」并回落「原图」且不改写偏好",
       not _tg.is_item_enabled("result") and _tg.current() == "original"
       and _rv._mode == "result",
       f"current={_tg.current()} mode={_rv._mode}")
    _rv._rembg_dir = _saved_dir
    _rv._sync_toggle(_rv._result_full_image() is not None)
    ok("结果恢复后分段开关自动回到用户偏好项",
       _tg.is_item_enabled("result") and _tg.current() == "result", _tg.current())
    # 点击：发一次信号、_mode 跟随；程序化 set_current 不发信号（否则回流递归）
    _clicked: list[str] = []
    _rv.toggle.current_changed.connect(_clicked.append)
    _x2 = 2 + _tg._segment_widths()[0] + 10
    QTest.mouseClick(_tg, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(_x2, 15))
    app.processEvents()
    ok("点击分段开关切到原图：发一次信号且 _mode 跟随",
       _clicked == ["original"] and _rv._mode == "original"
       and _tg.current() == "original",
       f"clicked={_clicked} mode={_rv._mode}")
    _clicked.clear()
    _tg.set_current("original")
    ok("程序化 set_current 不发信号", _clicked == [], str(_clicked))
    QTest.mouseClick(_tg, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(5, 15))
    app.processEvents()
    ok("点回「去底色结果」", _rv._mode == "result" and _tg.current() == "result",
       f"mode={_rv._mode} current={_tg.current()}")
    # 回归守卫：切换行里不能再出现按钮，也不能再有脱离主题的硬编码色
    _stray = [w for w in _rv.findChildren(QWidget)
              if "0078d4" in (w.styleSheet() or "")]
    ok("去底色预览没有按钮化切换、也没有硬编码蓝色样式表",
       not _rv.findChildren(QPushButton) and not _stray,
       f"别处残留 {len(_stray)} 个硬编码样式")

    # 还原该页检测框，避免影响后续 print 合成用例
    repo.save_detect_boxes(
        tid, _last_page.stem,
        _orig_entry[0] if _orig_entry else [],
        origin=_orig_entry[1] if _orig_entry else "manual",
    )
    d.detect_cache[str(_last_page)] = _orig_entry[0] if _orig_entry else []

    # 最近一次预览失败/中断：即使目录里残留图片也不允许提交
    bad_run = repo.create_stage_run(tid, "rembg", {"area": 1})
    repo.finish_stage(tid, bad_run, "failed")
    d._refresh_stage_views()
    ok("预览失败后提交按钮禁用（有旧图也不行）", not d.submit_button.isEnabled())
    d.run_rembg_submit()
    ok("预览失败时提交不启动", d.process is None)
    # 模拟用当前面板参数重新生成预览并成功 → 新版本提示恢复
    ok_run = repo.create_stage_run(
        tid, "rembg", d.control_stack.widget(2).get_args()
    )
    repo.finish_stage(tid, ok_run, "success")
    d._refresh_stage_views()
    ok("重新生成预览成功后提交恢复可用并提示新版本",
       d.submit_button.isEnabled()
       and d._rembg_submit_version_state() == "new_version")

    # 面板去底参数改了但没重新生成 → preview_stale（提示先重新生成预览）
    panel3 = d.control_stack.widget(2)
    _old_offset = panel3.offset.value()
    panel3.offset.setValue(_old_offset + 1)
    d._update_submit_button(False)
    ok("改去底参数未重跑预览 → preview_stale",
       d._rembg_submit_version_state() == "preview_stale"
       and "#b8860b" in d.submit_hint.styleSheet())
    panel3.offset.setValue(_old_offset)

    # 提交本次任务：预览图按 area/border 合成为最终图片到 stages/rembg
    d.run_rembg_submit()
    wait_worker(d, app, timeout=300)
    state = repo.list_stage_runs(tid, "rembg_submit")[0]
    ok("提交成功", state["status"] == "success", str(state))
    ok("最终图落在 stages/rembg",
       final_dir.exists() and len(list(final_dir.glob("*.png"))) == 6,
       str(final_dir))
    ok("提交成功后版本状态为最新、按钮徽标消失",
       d._rembg_submit_version_state() == "up_to_date"
       and d.submit_button.text() == "提交本次任务"
       and "#3a8a3e" in d.submit_hint.styleSheet())
    # 提交记录了所基于的预览版本号（不加载 YOLO，纯框坐标合成）
    _sub = next(r for r in repo.list_stage_runs(tid, "rembg_submit")
                if r["status"] == "success")
    ok("提交记录包含预览版本号",
       _sub["parameters"].get("_preview_run_id") == ok_run)
    # 再次「生成预览」成功（新版本）→ 又提示需要提交
    newer = repo.create_stage_run(
        tid, "rembg", d.control_stack.widget(2).get_args()
    )
    repo.finish_stage(tid, newer, "success")
    d._refresh_stage_views()
    ok("再次生成预览后重新提示新版本",
       d._rembg_submit_version_state() == "new_version"
       and "有新版本" in d.submit_button.text())

    # --- 生成 PDF 时第三步 area/border 实时生效（无需重新提交）---
    # 给一页注入确定性检测框（单框），模拟 YOLO 检出
    _comp0 = d._rembg_submit_entries(1, None)
    _anchor = next((c for c in _comp0 if c.get("box") is None), _comp0[0])
    _anchor_stem = Path(_anchor["file"]).stem
    _aw, _ah = repo.image_size(tid, _anchor_stem)
    _injected = [round(_aw * 0.10), round(_ah * 0.10),
                 round(_aw * 0.55), round(_ah * 0.90)]
    ctx.injected_boxes = _injected
    repo.save_detect_boxes(tid, _anchor_stem, [_injected, None], origin="manual")
    _anchor_src = next(p for p in d._manifest_paths() if p.stem == _anchor_stem)
    d.detect_cache[str(_anchor_src)] = [_injected, None]

    panel3.border.setText("10")
    _entries_b, _ = d._print_entries()
    _fx10 = d._build_print_effects(_entries_b, 1, "10")
    ok("print 合成规格与列表一一对应且源为 rembgpreview 去底图",
       len(_fx10) == 6
       and all(Path(s["file"]).parent == preview_dir for s in _fx10),
       str([Path(s["file"]).name for s in _fx10]))
    _a_spec = next(s for s in _fx10
                   if Path(s["file"]).stem == _anchor_stem)
    ok("print 合成规格携带检测框/area/border",
       _a_spec["effect"] == {"boxes": [_injected], "area": 1, "border": "10"},
       str(_a_spec))
    # 仅改 border 不重新提交：合成规格立即变为新值
    panel3.border.setText("25")
    _fx25 = d._build_print_effects(d._print_entries()[0], 1, "25")
    _a25 = next(s for s in _fx25 if Path(s["file"]).stem == _anchor_stem)
    ok("调整 border 后无需重新提交即生效",
       _a25["effect"]["border"] == "25"
       and _a25["effect"]["boxes"] == [_injected],
       str(_a25))
    # 外部插入图整图透传；area 结构变更后旧提交图被丢弃、新条目补尾
    _mixed = _entries_b + [{"file": str(img), "label": "external_page"}]
    _stale = {"file": str(repo.rembg_output_dir(tid) / "999-r.png"),
              "label": "999-r"}
    _fx_mix = d._build_print_effects(_mixed + [_stale], 1, "25")
    ok("外部插入图透传、旧 area 提交图不混入 PDF",
       any(s["file"] == str(img) and s["effect"] is None for s in _fx_mix)
       and not any(Path(s["file"]).name == "999-r.png" for s in _fx_mix))
    panel3.border.setText("10")  # 正式 print 使用 10mm
