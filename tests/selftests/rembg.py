# -*- coding: utf-8 -*-
"""rembg 阶段自测：**一步**执行去底色（无预览、无提交）。

2026-10-22 用户口径：

> 「生成预览」改成「执行去底色」，直接去底色到 rembg，不再需要预览了。

本模块守三件事：

1. **只有一个动作**：第三步主按钮是「执行去底色」，没有提交按钮；
2. **产物直接落 stages/rembg**：张数与输入图一致、一进一出同名；
3. **第四步直接消费它**：取图规格透传成品图（effect 全 None）。
"""

NAME = "rembg"
DEPENDS: list[str] = ["detect"]
TITLE = "rembg"


def run(ctx) -> None:
    from pathlib import Path
    from typing import Any, cast

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QPushButton, QWidget

    from desktop.ui.widgets import SegmentedToggle
    from desktop.workers import ImageListWorker
    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    img = ctx.inserted_img

    d.set_task(tid)
    # ⚠️ 去底色的输入是「检测文本框」**提交后**的裁图（stages/detect）。
    #    进第三步之前先替用户点一次第二步的「提交本次任务」。
    d._select_stage(1)
    d.run_detect_submit()
    wait_worker(d, app, timeout=300)
    _det_runs = repo.list_stage_runs(tid, "detect_submit")
    ok("（前置）检测提交成功，去底色的输入就位",
       bool(_det_runs) and _det_runs[0].get("status") == "success",
       str(_det_runs[:1]))
    _crop_dir = repo.task_dir(tid) / "stages" / "detect"
    ok("（前置）裁好的图落在 stages/detect",
       _crop_dir.is_dir() and any(_crop_dir.iterdir()), str(_crop_dir))

    d._select_stage(2)
    ok("步骤三主按钮为『执行去底色』", d.run_button.text() == "执行去底色",
       d.run_button.text())
    ok("第三步没有『提交本次任务』按钮（去底色只有一步）",
       d.submit_button.isHidden())

    # --- offset 必须能设成负值（阈值 = Otsu + offset）---
    _p3 = d.control_stack.widget(2)
    ok("offset 可设为负值（下限 < 0）", _p3.offset.minimum() < 0,
       f"min={_p3.offset.minimum()}")
    _p3.offset.setValue(-20)
    ok("offset 取到负值", _p3.offset.value() == -20, str(_p3.offset.value()))
    ok("get_args 透传负 offset", _p3.get_args()["offset"] == -20,
       str(_p3.get_args().get("offset")))
    _p3.apply_args({"offset": -35})
    ok("历史参数回填负 offset 不丢", _p3.offset.value() == -35,
       str(_p3.offset.value()))
    _p3.apply_args({})
    ok("复位后 offset 回到 0", _p3.offset.value() == 0,
       str(_p3.offset.value()))
    # 逐张 offset 会随用户改动落盘（黑名单法）：这里显式落一次 0，避免把
    # 测试过程中的临时偏移留给后续模块。
    d._note_offset_pending()
    d._flush_pending_offset()

    # --- 第二步面板没有 area（2026-10-22 起 area 已从整个项目移除）---
    _p2 = d.control_stack.widget(1)
    ok("第二步面板没有 area 控件", not hasattr(_p2, "area"))
    ok("第二步 get_args 为空（默认值不在表单里）",
       _p2.get_args() == {}, str(_p2.get_args()))

    final_dir = repo.rembg_output_dir(tid)
    ok("执行前 stages/rembg 为空",
       not final_dir.exists() or not any(final_dir.glob("*.png")))

    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["rembg"]
    ok("去底色执行成功", state["status"] == "success", str(state))

    # rembg 直接处理**输入目录里的全部图片**（＝第二步提交裁好的那批），
    # 一条输入对应一条成品，文件名沿用页名（不裁剪、不缩放）。
    _inputs = sorted(_crop_dir.glob("*.png"), key=lambda p: p.name)
    _finals = sorted(final_dir.glob("*.png"), key=lambda p: p.name)
    ok("成品图落在 stages/rembg（张数 == 输入张数）",
       len(_finals) == len(_inputs) > 0,
       f"finals={len(_finals)} inputs={len(_inputs)}")
    ok("成品图与输入图一一同名（整图去底色，不裁剪）",
       [p.stem for p in _finals] == [p.stem for p in _inputs],
       f"{[p.name for p in _finals][:5]} vs {[p.name for p in _inputs][:5]}")

    # ⚠️ 执行时必须顺手生成第四步缩略图（不再对每条目现解码 6000px 原图）
    _s4_thumbs = sorted(repo.rembg_thumbnails_dir(tid).glob("*.jpg"))
    ok("执行时生成第四步缩略图（数量与成品图一致且不旧于成品图）",
       len(_s4_thumbs) == len(_finals) > 0
       and all(
           t.stat().st_mtime >= (final_dir / f"{t.stem}.png").stat().st_mtime
           for t in _s4_thumbs
       ),
       f"thumbs={len(_s4_thumbs)} finals={len(_finals)}")
    ok("第四步 provider 对成品图返回缩略图",
       all(
           d._print_thumb_provider(str(p)) is not None
           and Path(d._print_thumb_provider(str(p))).stem == p.stem
           for p in _finals
       ),
       str([d._print_thumb_provider(str(p)) for p in _finals[:2]]))

    # --- 去底色查看器：**一张输入图 = 一个条目**，整图显示 ---
    _rv = d.rembg_viewer
    _manifest = d._manifest_paths()
    ok("去底色条目数 == 输入图张数",
       len(_rv._entries) == len(_manifest),
       f"entries={len(_rv._entries)} inputs={len(_manifest)}")
    ok("条目名就是输入页名（没有 -l/-r 后缀）",
       {e["label"] for e in _rv._entries} == {p.stem for p in _manifest},
       str(sorted(e["label"] for e in _rv._entries))[:120])
    ok("条目不再带区域合成参数（整图显示）",
       all(e.get("box") is None for e in _rv._entries),
       str([e.get("box") for e in _rv._entries][:3]))

    # 缩略图也不该再走区域合成（crops 恒 None、effects 恒 None/空）
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
    ok("去底色缩略图不再走区域合成（crops=None、effects 全空）",
       _last_call["crops"] is None
       and not any(_last_call["effects"] or []),
       f"crops={_last_call['crops']} effects={(_last_call['effects'] or [])[:2]}")

    # --- 「去底色结果 / 原图」分段开关（主题色、对比度、点击行为）---
    _tg = _rv.toggle
    ok("去底色预览用分段开关切换「去底色结果 / 原图」",
       isinstance(_tg, SegmentedToggle)
       and [text for _key, text in _tg._items] == ["去底色结果", "原图"],
       str(getattr(_tg, "_items", None)))
    ok("分段开关固定高与控件常量一致",
       _tg.height() == SegmentedToggle.HEIGHT == 30, f"{_tg.height()}")
    _seg_widths = _tg._segment_widths()
    _old_size = _tg.size()
    _tg.resize(_tg.minimumSizeHint())
    app.processEvents()
    _shot = _tg.grab().toImage()
    _track_px = _shot.pixelColor(2 + _seg_widths[0] + _seg_widths[1] // 2, 4)
    _thumb_px = _shot.pixelColor(2 + 10, SegmentedToggle.HEIGHT // 2)
    _tg.resize(_old_size)
    _track_rgb = cast(Any, _track_px.getRgb())[:3]
    _thumb_rgb = cast(Any, _thumb_px.getRgb())[:3]
    _gap = (sum(_thumb_rgb) - sum(_track_rgb)) // 3
    ok("分段开关轨道比选中滑块明显更深（选中态有对比度）",
       _gap >= 12 and min(_thumb_rgb) >= 250,
       f"轨道 {_track_px.name()} / 滑块 {_thumb_px.name()}，平均亮度差 {_gap}")
    ok("有去底色结果时「去底色结果」项可用且默认选中（结果优先）",
       _tg.is_item_enabled("result") and _tg.current() == "result",
       f"enabled={_tg.is_item_enabled('result')} current={_tg.current()}")
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
    QTest.mouseClick(_tg, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier, QPoint(5, 15))
    app.processEvents()
    ok("点回「去底色结果」", _rv._mode == "result" and _tg.current() == "result",
       f"mode={_rv._mode} current={_tg.current()}")
    _stray = [w for w in _rv.findChildren(QWidget)
              if "0078d4" in (w.styleSheet() or "")]
    ok("去底色预览没有按钮化切换、也没有硬编码蓝色样式表",
       not _rv.findChildren(QPushButton) and not _stray,
       f"别处残留 {len(_stray)} 个硬编码样式")

    # --- 第四步只排版这一步的成品图 ---
    # ⚠️ 批内前面的模块可能把共享任务上的「图片拼版」开关打开过；这里显式关掉，
    #    否则第四步来源会切到 stages/imposition（空目录），测不到本步产物。
    d._set_imposition_checked(False)
    _entries, _ = d._print_entries()
    _fx = d._build_print_effects(_entries)
    ok("第四步取图 = 成品图整图透传（与列表一一对应、effect 全 None）",
       len(_fx) == len(_entries) > 0
       and all(e["effect"] is None for e in _fx)
       and all(Path(e["file"]).parent == final_dir for e in _fx),
       str([Path(e["file"]).name for e in _fx]))
    ok("第四步取图来源阶段就是 rembg",
       d.print_source_stage() == "rembg", d.print_source_stage())

    # 外部插入图整图透传；指向不存在文件的条目被过滤（不生成空页）
    _mixed = _entries + [{"file": str(img), "label": "external_page"}]
    _stale = {"file": str(final_dir / "999-r.png"), "label": "999-r"}
    _fx_mix = d._build_print_effects(_mixed + [_stale])
    ok("外部插入图透传、丢失的条目被过滤",
       any(e["file"] == str(img) and e["effect"] is None for e in _fx_mix)
       and not any(Path(e["file"]).name == "999-r.png" for e in _fx_mix))
