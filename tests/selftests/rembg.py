# -*- coding: utf-8 -*-
"""rembg 阶段自测：生成预览/提交、分段开关、实时合成规格。

产出跨模块状态：``ctx.injected_boxes``（注入的确定性检测框）与
``ctx.preview_dir``（预览目录），print 模块的合成断言依赖二者。
"""

NAME = "rembg"
DEPENDS: list[str] = ["detect"]
TITLE = "rembg"


def run(ctx) -> None:
    import os
    import time
    from pathlib import Path
    from typing import Any, cast

    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtGui import QImage
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

    from desktop.pages.taskdetail.submit import SUBMIT_TEXT
    from desktop.ui.widgets import SegmentedToggle
    from desktop.workers import ImageListWorker
    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    img = ctx.inserted_img

    d.set_task(tid)
    # ⚠️ 2026-10-22：去底色的输入是「检测文本框」**提交后**的裁图
    #    （stages/detect）。所以进第三步之前，先替用户点一次第二步的
    #    「提交本次任务」——否则第三步的输入根本没就位。
    d._select_stage(1)
    d.run_detect_submit()
    wait_worker(d, app, timeout=300)
    # ⚠️ ``stage_states`` 只按 STAGES（四个主链步骤）出表，提交动作不在里面
    #    ——直接问运行记录。
    _det_runs = repo.list_stage_runs(tid, "detect_submit")
    ok("（前置）检测提交成功，去底色的输入就位",
       bool(_det_runs) and _det_runs[0].get("status") == "success",
       str(_det_runs[:1]))
    _crop_dir = repo.task_dir(tid) / "stages" / "detect"
    ok("（前置）裁好的图落在 stages/detect",
       _crop_dir.is_dir() and any(_crop_dir.iterdir()), str(_crop_dir))
    d._select_stage(2)
    ok("步骤三主按钮为生成预览", d.run_button.text() == "生成预览")

    # 「生成预览 / 提交本次任务」并排一行（2026-10-04）：两者是同一段动作的
    # 前后两跳，竖排会被读成两个步骤 ⇒ 包进 action_row 各占一半；没有提交
    # 按钮的步骤（1/2/4）里 submit 单独藏起、run 自动占满整行。
    _row_layout = d.action_row.layout()
    _run_index = _row_layout.indexOf(d.run_button)
    _submit_index = _row_layout.indexOf(d.submit_button)
    ok("生成预览与提交按钮并排一行（同一 HBox、各占 stretch=1）",
       isinstance(_row_layout, QHBoxLayout)
       and _run_index >= 0 and _submit_index >= 0
       and _row_layout.stretch(_run_index) == 1
       and _row_layout.stretch(_submit_index) == 1,
       f"run@{_run_index} submit@{_submit_index}")
    ok("第三步两按钮都在行内显示，顺序为「生成预览 | 提交本次任务」",
       not d.run_button.isHidden() and not d.submit_button.isHidden()
       and _run_index < _submit_index)

    # --- offset 必须能设成负值（阈值 = Otsu + offset，负数让文字更细更淡）---
    # 曾出错：SpinBox 下限写死 0，界面完全无法输入负数，而 CLI/functions 一直支持。
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

    # --- 第二步面板没有 area（2026-10-22 起 area 已从整个项目移除）---
    _p2 = d.control_stack.widget(1)
    ok("第二步面板没有 area 控件", not hasattr(_p2, "area"))
    ok("第二步 get_args 为空（默认值不在表单里）",
       _p2.get_args() == {}, str(_p2.get_args()))

    ok("未生成预览前提交按钮禁用", not d.submit_button.isEnabled())
    d.run_rembg_submit()  # 直接调用也必须被拦截，不启动子进程
    ok("未成功生成预览时提交不启动", d.process is None)
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["rembg"]
    ok("rembg 预览成功", state["status"] == "success", str(state))
    preview_dir = repo.rembg_preview_output_dir(tid)
    ctx.preview_dir = preview_dir
    # rembg 直接处理**输入目录里的全部图片**（＝第二步提交裁好的那批）。
    _input_count = len(list(_crop_dir.iterdir()))
    ok("预览图落在 stages/rembgpreview（张数 == 输入张数）",
       preview_dir.exists()
       and len(list(preview_dir.glob("*.png"))) == _input_count,
       str(sorted(p.name for p in preview_dir.glob("*.png")))
       if preview_dir.exists() else str(preview_dir))
    final_dir = repo.rembg_output_dir(tid)
    ok("提交前 stages/rembg 为空",
       not final_dir.exists() or not any(final_dir.glob("*.png")))
    ok("预览成功后提交按钮可用", d.submit_button.isEnabled())
    ok("预览成功即提示有新版本待提交（文案收敛为按钮加粗 + 下方红字提示）",
       d._submit_version_state("rembg") == "new_version"
       and d.submit_button.text() == SUBMIT_TEXT
       and d.submit_button.font().bold()
       and not d.submit_hint.isHidden() and "#c0392b" in d.submit_hint.styleSheet())

    # --- 去底色查看器：**一张输入图 = 一个条目**（2026-10-22） ---
    # 以前按 area 拆 -l/-r 并叠加区域合成；现在裁剪在第二步提交时已经完成，
    # 这一步只做整图去底色，所以条目必须与产物一一对应、不再有左右后缀。
    _rv = d.rembg_viewer
    _inputs = d._manifest_paths()
    ok("去底色条目数 == 输入图张数（不再按 area 拆左右）",
       len(_rv._entries) == len(_inputs),
       f"entries={len(_rv._entries)} inputs={len(_inputs)}")
    ok("条目名就是输入页名（没有 -l/-r 后缀）",
       {e["label"] for e in _rv._entries} == {p.stem for p in _inputs},
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
    _track_rgb = cast(Any, _track_px.getRgb())[:3]
    _thumb_rgb = cast(Any, _thumb_px.getRgb())[:3]
    _gap = (sum(_thumb_rgb) - sum(_track_rgb)) // 3
    ok("分段开关轨道比选中滑块明显更深（选中态有对比度）",
       _gap >= 12 and min(_thumb_rgb) >= 250,
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

    # 最近一次预览失败/中断：即使目录里残留图片也不允许提交
    bad_run = repo.create_stage_run(tid, "rembg", {"type": 1})
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
       and d._submit_version_state("rembg") == "new_version")

    # 面板去底参数改了但没重新生成 → preview_stale（提示先重新生成预览）
    panel3 = d.control_stack.widget(2)
    _old_offset = panel3.offset.value()
    panel3.offset.setValue(_old_offset + 1)
    d._update_submit_button(False)
    ok("改去底参数未重跑预览 → preview_stale",
       d._submit_version_state("rembg") == "preview_stale"
       and "#b8860b" in d.submit_hint.styleSheet())
    panel3.offset.setValue(_old_offset)

    # 提交本次任务：预览图按 area/border 合成为最终图片到 stages/rembg
    d.run_rembg_submit()
    wait_worker(d, app, timeout=300)
    state = repo.list_stage_runs(tid, "rembg_submit")[0]
    ok("提交成功", state["status"] == "success", str(state))
    ok("最终图落在 stages/rembg（张数 == 输入张数）",
       final_dir.exists()
       and len(list(final_dir.glob("*.png"))) == _input_count,
       str(final_dir))
    # ⚠️ 提交必须顺手生成第四步缩略图（2026-09-27：缩略条不再现解码原图）
    _s4_thumbs = sorted(repo.rembg_thumbnails_dir(tid).glob("*.jpg"))
    _s4_finals = sorted(final_dir.glob("*.png"))
    ok("提交时生成第四步缩略图（数量与最终图一致且不旧于最终图）",
       len(_s4_thumbs) == len(_s4_finals) > 0
       and all(
           t.stat().st_mtime >= (final_dir / f"{t.stem}.png").stat().st_mtime
           for t in _s4_thumbs
       ),
       f"thumbs={len(_s4_thumbs)} finals={len(_s4_finals)}")
    # 第四步 provider 命中这些缩略图（不再回落原图解码）
    ok("第四步 provider 对提交产物返回缩略图",
       all(
           d._print_thumb_provider(str(p)) is not None
           and Path(d._print_thumb_provider(str(p))).stem == p.stem
           for p in _s4_finals
       ),
       str([d._print_thumb_provider(str(p)) for p in _s4_finals[:2]]))
    ok("提交成功后版本状态为最新、按钮徽标消失",
       d._submit_version_state("rembg") == "up_to_date"
       and d.submit_button.text() == "提交本次任务"
       and "#3a8a3e" in d.submit_hint.styleSheet())
    # 去底色结果被编辑（参数没变、也没重新生成预览）也必须改口提示重新提交：
    # 提交产物是"提交那一刻"的合成结果，不重新提交就传不到第四步
    # （用户 2026-10-01「去底色那一步，必须提交才能传给下一步」）。
    _pv_edit = next(
        iter(sorted(repo.rembg_preview_output_dir(tid).glob("*.png"))))
    _pv_mtime = _pv_edit.stat().st_mtime
    _stamp = time.time() + 5
    os.utime(_pv_edit, (_stamp, _stamp))  # 模拟"提交之后又被编辑过"
    d._update_submit_button(False)
    ok("编辑去底色结果后按钮改口：待重新提交（不再是绿色『已是最新版本』）",
       d._submit_version_state("rembg") == "new_version"
       and d.submit_button.font().bold()
       and "#c0392b" in d.submit_hint.styleSheet(),
       "{} / {}".format(d._submit_version_state("rembg"), d.submit_button.text()))
    os.utime(_pv_edit, (_pv_mtime, _pv_mtime))  # 还原 mtime，别影响后续模块
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
       d._submit_version_state("rembg") == "new_version"
       and d.submit_button.font().bold())

    # --- 第四步只排版「提交本次任务」的成品图 ---
    # 用户 2026-10-01 口径：「去底色那一步，必须提交才能传给下一步」。所以
    # 第四步**不再**拿去底图（stages/rembgpreview）按当前 area/border 现算。
    # 给一页注入确定性检测框（单框），模拟 YOLO 检出
    _comp0 = d._submit_entries()
    _anchor = next((c for c in _comp0 if c.get("box") is None), _comp0[0])
    _anchor_stem = Path(_anchor["file"]).stem
    _anchor_page = Path(_anchor["file"])
    _aw, _ah = d._image_size_for(str(_anchor_page))
    _injected = [round(_aw * 0.10), round(_ah * 0.10),
                 round(_aw * 0.55), round(_ah * 0.90)]
    ctx.injected_boxes = _injected
    repo.save_detect_boxes(tid, _anchor_stem, [_injected, None], origin="manual")
    _anchor_src = next(p for p in d._manifest_paths() if p.stem == _anchor_stem)
    d.detect_cache[str(_anchor_src)] = [_injected, None]

    _entries_b, _ = d._print_entries()
    _fx10 = d._build_print_effects(_entries_b)
    ok("第四步取图 = 提交产物整图透传（与列表一一对应、effect 全 None）",
       len(_fx10) == len(_entries_b) > 0
       and all(e["effect"] is None for e in _fx10)
       and all(Path(e["file"]).parent == final_dir for e in _fx10),
       str([Path(e["file"]).name for e in _fx10]))
    # 仅改去底参数 **不再**「即时生效」——必须重新提交（按钮会提示）
    _panel3b = d.control_stack.widget(2)
    _panel3b.type.setCurrentIndex(0)
    _fx25 = d._build_print_effects(d._print_entries()[0])
    ok("改去底参数不重新提交 → 取图规格不变（仍指向同一批成品图）",
       [e["file"] for e in _fx25] == [e["file"] for e in _fx10]
       and all(e["effect"] is None for e in _fx25),
       str([Path(e["file"]).name for e in _fx25]))
    # 外部插入图整图透传；指向不存在文件的条目被过滤（不生成空页）
    _mixed = _entries_b + [{"file": str(img), "label": "external_page"}]
    _stale = {"file": str(repo.rembg_output_dir(tid) / "999-r.png"),
              "label": "999-r"}
    _fx_mix = d._build_print_effects(_mixed + [_stale])
    ok("外部插入图透传、丢失的条目被过滤",
       any(e["file"] == str(img) and e["effect"] is None for e in _fx_mix)
       and not any(Path(e["file"]).name == "999-r.png" for e in _fx_mix))
