# -*- coding: utf-8 -*-
"""「从这张图片开始自动拼版」复选框（用户 2026-10-01：恰好勾 1 张 / 用户 2026-11-16：**取消\"删除图片/删除恢复\"整套** / 真实产物形态：第三步提交产物是「白底透明」的 1bit 调色板 PNG / 6. 详情页接线：取图来源切换 / 启用开关的可用性跟着**流程图**走（2026-10-05 口径） / 自定义流程：拼版在去底色**之前**，选图只看连线（2026-11-03）"""

from typing import Any


def run(st: Any) -> None:
    from ._helpers import BLUE, GREEN, RED, YELLOW, _count_non_white, _mk, _names
    from desktop.components.imposition.picker import (
        DIALOG_H,
        DIALOG_W,
        THUMB_H,
        THUMB_W,
        ImpositionPickerDialog,
    )
    from desktop.steps.bpmn_diagram import (
        DiagramFlow,
        DiagramNode,
        FlowDiagram,
        KIND_TASK,
    )
    from desktop.store import IMPOSITION_STAGE, TaskStore
    from desktop.components.imposition.view import ImpositionViewWidget
    from pathlib import Path
    from PySide6.QtCore import QPointF, QSize, Qt
    from desktop.pages.taskdetail.page import TaskDetailPage
    import desktop.components.imposition.picker as _ipick
    from tests.selftests._context import make_pdf, ok, pump
    import numpy as np
    from utils.transparent_png import save_white_as_transparent
    ok(
        "只勾 1 张：下方出现「从这张图片开始自动拼版」复选框（默认未勾）",
        st.dialog.auto_checkbox.isVisibleTo(st.dialog)
        and not st.dialog.auto_checkbox.isChecked(),
        f"visible={not st.dialog.auto_checkbox.isHidden()} "
        f"checked={st.dialog.auto_checkbox.isChecked()}",
    )
    ok(
        "复选框没勾时「开始拼版」也可点（单张单独成页）",
        st.dialog.ok_button.isEnabled(),
    )
    st.dialog.auto_checkbox.setChecked(True)
    ok("勾上自动拼版后「开始拼版」可点", st.dialog.ok_button.isEnabled())
    _auto_file = st.dialog.auto_mode_file()
    ok(
        "auto_mode_file = 勾选的那张",
        _auto_file is not None and _auto_file.name == "2-r.png",
        str(_auto_file),
    )
    ok(
        "auto_sequence = 从勾选那张起到候选末尾（源清单顺序）",
        _names(st.dialog.auto_sequence()) == ["2-r.png", "2-l.png"],
        str(_names(st.dialog.auto_sequence())),
    )
    st.dialog.cards[1].toggle()
    ok(
        "勾到 2 张：复选框隐藏并复位（走手动拼一页）",
        not st.dialog.auto_checkbox.isVisibleTo(st.dialog)
        and not st.dialog.auto_checkbox.isChecked()
        and st.dialog.ok_button.isEnabled(),
    )
    st.dialog.cards[1].toggle()
    ok(
        "回到只勾 1 张：复选框重新出现（未勾），「开始拼版」可点",
        st.dialog.auto_checkbox.isVisibleTo(st.dialog)
        and not st.dialog.auto_checkbox.isChecked()
        and st.dialog.ok_button.isEnabled(),
    )
    st.dialog.deleteLater()

    # 勾 3 张：可以勾，但「开始拼版」不可点（用户 2026-09-30：最多 2 张）
    third = ImpositionPickerDialog([st.a, st.b, st.c])
    ok("三张候选时全部可勾", third.count() == 3)
    third.cards[0].toggle()
    third.cards[1].toggle()
    third.cards[2].toggle()
    ok(
        "勾 3 张 → 「开始拼版」不可点，提示最多勾 2 张",
        len(third.checked_files()) == 3
        and not third.ok_button.isEnabled()
        and "最多勾 2 张" in third.status.text(),
        f"勾中 {_names(third.checked_files())} / {third.status.text()}",
    )
    third.cards[1].toggle()
    ok(
        "回到勾 2 张 → 可点，提示拼成一页",
        third.ok_button.isEnabled() and "拼成一页" in third.status.text(),
        third.status.text(),
    )
    third.deleteLater()

    # 1 张整幅：单独成页可点，自动拼版选项同样出现（用户 2026-10-01：
    # 不再限制半幅，整幅起自动 = 整幅单独一页后继续往下配）
    full_only = ImpositionPickerDialog([st.full])
    full_only.cards[0].toggle()
    ok(
        "只勾 1 张整幅：「开始拼版」可点、自动拼版选项同样出现",
        full_only.ok_button.isEnabled()
        and full_only.auto_checkbox.isVisibleTo(full_only)
        and "整幅" in full_only.status.text(),
        full_only.status.text(),
    )
    full_only.auto_checkbox.setChecked(True)
    ok(
        "勾上后整幅也能走自动拼版（auto_mode_file 生效）",
        full_only.auto_mode_file() == st.full,
        str(full_only.auto_mode_file()),
    )
    full_only.deleteLater()
    one_list = ImpositionPickerDialog([st.a, st.b, st.c, st.d])
    ok(
        "「确定」按钮已改为「开始拼版」",
        one_list.ok_button.text() == "开始拼版",
        one_list.ok_button.text(),
    )
    ok(
        "弹窗没有页签 / 删除按钮 / 恢复按钮（只有一个列表）",
        not hasattr(one_list, "toggle")
        and not hasattr(one_list, "delete_button")
        and not hasattr(one_list, "restore_button")
        and not hasattr(one_list, "removed_cards")
        and not hasattr(one_list, "removed_files"),
    )
    ok(
        "候选池里的图**全部**列出（不再有黑名单）",
        one_list.count() == 4,
        str(one_list.count()),
    )
    one_list.deleteLater()
    pump(st.ctx.app, times=10)
    import numpy as np

    from utils.transparent_png import save_white_as_transparent

    rgb = np.full((600, 400, 3), 255, dtype=np.uint8)
    rgb[80:520, 120:220] = 20
    transparent = st.tmp / "transparent-1-r.png"
    save_white_as_transparent(rgb, transparent)
    real = ImpositionPickerDialog([transparent])
    real.resize(DIALOG_W, DIALOG_H)
    real.show()
    pump(st.ctx.app, times=20)
    card_real = real.cards[0]
    ink = (
        _count_non_white(card_real._pixmap.toImage())
        if (card_real._pixmap.size() == QSize(THUMB_W, THUMB_H))
        else -1
    )
    ok(
        "白底透明 PNG（1bit 调色板 + tRNS）也能正常出缩略图",
        ink > 20,
        f"缩略图={card_real._pixmap.size()} 非白采样={ink}",
    )
    ok(
        "缩略图与卡片尺寸是固定值（不受源图尺寸影响）",
        card_real.thumb.size() == QSize(THUMB_W, THUMB_H)
        and card_real.size().width() >= 180,
        f"thumb={card_real.thumb.size()} card={card_real.size()}",
    )
    real.deleteLater()
    st.repo = TaskStore(st.tmp / "data")
    st.pdf = make_pdf(st.tmp / "拼版源.pdf", 2)
    st.tid = st.repo.create_task(st.pdf, "imposition-hash", "拼版测试")
    st.repo.copy_source_to_task(st.tid, st.pdf)
    # 拼版节点是否在流程里**只看流程图**（2026-10-05 口径）：默认模板里
    # 画了「图片拼版」，所以这里不必再配置区域模式来"让它出现"
    # （旧口径：area=1 才显示，否则 _select_stage(拼版) 会被退回第一步）。
    # 第三步去底色产物（拼版的源图 = 「提交本次任务」的成品图）
    st.rembg_dir = st.repo.rembg_output_dir(st.tid)
    for name, color in (
        ("1-r", RED),
        ("1-l", GREEN),
        ("2-r", BLUE),
        ("2-l", YELLOW),
    ):
        _mk(st.rembg_dir / f"{name}.png", color)
    # 新契约（2026-11-03）：上游的**产出动作**必须执行成功，下游才看得到
    # 这批成品图（否则只算"实时预览的半成品"）。这里补一条去底色成功记录。
    rembg_node = st.repo.task_diagram(st.tid).primary_of("rembg")
    run_id = st.repo.create_stage_run(st.tid, "rembg", {}, node_id=rembg_node)
    st.repo.finish_stage(st.tid, run_id, "success")
    # 顺带铺好上游夹具（提取清单 / 检测框）：它们已不参与第四步合成
    # （只透传去底色成品），但保留成"真实任务该有的样子"，
    # 免得测试跑在空目录上。
    extract = st.repo.extract_output_dir(st.tid)
    boxes = []
    for stem, color in (("1", RED), ("2", BLUE)):
        item = _mk(extract / f"{stem}.png", color)
        boxes.append({"file": str(item), "label": stem})
    st.repo.save_pages(st.tid, boxes)
    st.repo.save_detect_boxes(st.tid, "1", [[20, 40, 390, 560], [410, 40, 780, 560]])
    st.repo.save_detect_boxes(st.tid, "2", [[20, 40, 390, 560], [410, 40, 780, 560]])

    st.page = TaskDetailPage(st.repo)
    st.page.resize(1080, 720)
    st.page.show()
    pump(st.ctx.app, times=12)
    ok("进入拼版测试任务", st.page.set_task(st.tid))
    # ⚠️ 下面按任务目录取缓存/产物的调用都要 task_id，set_task 过才有
    assert st.page.task_id is not None
    pump(st.ctx.app, times=8)

    ok(
        "详情页控制栈/预览栈都多了拼版这一位",
        st.page.control_stack.count() == 5 and st.page.preview_stack.count() == 5,
    )
    ok(
        "默认未启用拼版时，第四步取图 = 第三步去底色",
        st.page.print_source_dir() == st.rembg_dir and not st.page.imposition_active(),
    )
    ok(
        "图里有「图片拼版」→ 启用开关可用（不再依赖区域模式）",
        st.page.imposition_enabled_checkbox.isEnabled(),
        st.page.imposition_enabled_checkbox.toolTip(),
    )
    # 用**独立页面实例 + 独立任务**验"图里没有"这一侧：直接换掉上面那个
    # page 的流程图会连累后面所有断言（它们都按默认模板的图算）。
    from desktop.steps.bpmn_diagram import (
        DiagramFlow,
        DiagramNode,
        FlowDiagram,
        KIND_TASK,
    )

    fog_task = st.repo.create_task(st.pdf, "imposition-fogless", "无拼版流程")
    st.repo.save_task_diagram(
        fog_task,
        FlowDiagram(
            nodes=tuple(
                DiagramNode(f"q{i}", KIND_TASK, name)
                for i, name in enumerate(
                    ("提取图片", "检测文本框", "图片去底色", "PDF排版")
                )
            ),
            flows=tuple(
                DiagramFlow(f"qf{i}", f"q{i - 1}", f"q{i}") for i in range(1, 4)
            ),
        ),
    )
    fog = TaskDetailPage(st.repo)
    fog.resize(1080, 720)
    fog.show()
    pump(st.ctx.app, times=12)
    fog.set_task(fog_task)
    pump(st.ctx.app, times=8)
    ok(
        "流程图里没有「图片拼版」→ 启用开关置灰（勾了也不会生效）",
        not fog.imposition_enabled_checkbox.isEnabled(),
    )
    ok(
        "置灰时说明原因，不是静默失效",
        "没有" in fog.imposition_enabled_checkbox.toolTip()
        and "生效" in fog.imposition_enabled_checkbox.toolTip(),
        fog.imposition_enabled_checkbox.toolTip(),
    )
    ok(
        "图里没有拼版 → 步骤条上也没有那一格",
        not fog._imposition_node_visible()
        and fog.step_bar.imposition_node.isHidden(),
    )
    ok(
        "图里没有拼版时，即便勾过开关也不生效（取图按图回退）",
        not str(
            st.repo.stage_input(fog_task, "print", "pages", imposition_active=True)
        ).endswith("imposition"),
        str(st.repo.stage_input(fog_task, "print", "pages", imposition_active=True)),
    )
    fog.deleteLater()
    pump(st.ctx.app, times=4)
    # ⚠️ **必须把它删掉**：本模块后面的断言用 ``rows[0]``（任务列表的
    #    第一行）来找本测试的任务，多一个任务留在列表里就会把那一行抢走
    #    （曾因此让"启用拼版：列表多一个节点"假红）。
    st.repo.delete_task(fog_task)
    order_task = st.repo.create_task(st.pdf, "imposition-before-rembg", "拼版在前")
    st.repo.save_task_diagram(
        order_task,
        FlowDiagram(
            nodes=tuple(
                DiagramNode(f"o{i}", KIND_TASK, name)
                for i, name in enumerate(
                    ("提取图片", "检测文本框", "图片拼版", "图片去底色", "PDF排版")
                )
            ),
            flows=tuple(
                DiagramFlow(f"of{i}", f"o{i - 1}", f"o{i}") for i in range(1, 5)
            ),
        ),
    )
    _mk(st.repo.task_dir(order_task) / "stages" / "detect" / "o-1.png", RED)
    _mk(st.repo.task_dir(order_task) / "stages" / "detect" / "o-2.png", GREEN)
    _mk(st.repo.task_dir(order_task) / "stages" / "rembg" / "o-3.png", BLUE)
    # 新契约（2026-11-03）：上游的**产出动作**必须执行成功，下游才拿得到
    # 输入。这里直接造一条"检测已提交"的成功记录（模拟上游真的跑过），
    # 否则本用例测的是"选哪个上游"，不该被"上游还没跑"挡住。
    run_id = st.repo.create_stage_run(order_task, "detect_submit", {}, node_id="o1")
    st.repo.finish_stage(order_task, run_id, "success")
    order_page = TaskDetailPage(st.repo)
    order_page.resize(1080, 720)
    order_page.show()
    pump(st.ctx.app, times=12)
    ok("进入拼版在前的任务", order_page.set_task(order_task))
    pump(st.ctx.app, times=8)

    def _order_sources() -> list[str]:
        return sorted(Path(p).name for p in order_page.imposition_source_files())

    ok(
        "未启用拼版时，选图来源 = 上游检测产物（不是下游去底色）",
        _order_sources() == ["o-1.png", "o-2.png"],
        str(_order_sources()),
    )
    order_page.imposition_enabled_checkbox.setChecked(True)
    pump(st.ctx.app, times=6)
    ok(
        "启用拼版后，选图来源仍是同一上游（与开关无关）",
        _order_sources() == ["o-1.png", "o-2.png"],
        str(_order_sources()),
    )
    order_page.deleteLater()
    pump(st.ctx.app, times=4)
    # ⚠️ 同 fog_task：留在列表里会抢 ``rows[0]``，必须删。
    st.repo.delete_task(order_task)

    # ⚠️ **判据只看流程图**：面板参数不再影响拼版节点可见性
    before_visible = st.page._imposition_node_visible()
    st.repo.save_draft(st.tid, "rembg", {"type": 2})
    st.page._refresh_imposition_node()
    pump(st.ctx.app, times=4)
    ok(
        "改第三步面板参数不影响拼版节点**显不显示**（那由流程图决定）",
        st.page._imposition_node_visible() == before_visible,
        f"{before_visible} -> {st.page._imposition_node_visible()}",
    )
    st.repo.clear_draft(st.tid, "rembg")
    st.page._refresh_imposition_node()
    pump(st.ctx.app, times=4)

    # ⚠️ **不能再用写死下标**：BPM 驱动后步骤条格序含可选节点占位
    # （默认流程 extract=0/detect=1/rembg=2/imposition=3/print=4），
    # 而 ``IMPOSITION_INDEX = len(STAGES) = 4`` 落在 **print** 那一格——
    # 传进去切到的是第四步，不是拼版。两个下标各查各的表，别混。
    imposition_bar = st.page.bar_index_of_step(IMPOSITION_STAGE)
    ok(
        "拼版的格序是 3（可选节点占位，≠ len(STAGES)=4）",
        imposition_bar == 3,
        str(imposition_bar),
    )
    assert imposition_bar is not None  # ⚠️ 图里有这一格
    st.page._select_stage(imposition_bar)
    pump(st.ctx.app, times=8)
    # 栈页号与格序**不再相等**：两个栈按"真实步骤 + 伪步骤占最后一位"建页
    imposition_stack = st.page.stack_index_of_step(IMPOSITION_STAGE)
    ok("拼版的栈页号是 4（≠ 格序 3）", imposition_stack == 4, str(imposition_stack))
    ok(
        "切到拼版详情：两栈都在第 %d 位" % imposition_stack,
        st.page.control_stack.currentIndex() == imposition_stack
        and st.page.preview_stack.currentIndex() == imposition_stack,
        f"control={st.page.control_stack.currentIndex()} "
        f"preview={st.page.preview_stack.currentIndex()}",
    )
    ok(
        "拼版详情隐藏执行按钮组",
        not st.page.run_button.isVisible()
        and not st.page.submit_button.isVisible(),
    )
    ok(
        "详情里的拼版视图就是刚验证的那个控件",
        isinstance(st.page.imposition_view, ImpositionViewWidget),
    )

    # 未生效时：第四步也只排版第三步「提交本次任务」的成品图（整图透传）。
    # 2026-10-01 起不再拿去底图按 area/border 现算——见 submit.py。
    base_entries, _doc = st.page._print_entries()
    base_effects = st.page._build_print_effects(base_entries)
    ok(
        "未生效时也整图透传提交产物（不再按 area/border 现算）",
        len(base_effects) == 4
        and all(e["effect"] is None for e in base_effects)
        and {str(Path(e["file"]).parent) for e in base_effects} == {str(st.rembg_dir)},
        str(base_effects[:1]),
    )

    pages = None
    import desktop.components.imposition.picker as _ipick

    st.real_dialog = _ipick.ImpositionPickerDialog

    class _FakeDialog:
        """替身弹窗：直接认下前两张候选（真实弹窗是模态的，测试里不能 exec）。"""

        def __init__(self, files, parent=None, mode="pick",
                     thumb_provider=None, **kwargs):
            # ⚠️ 必须跟真实弹窗的签名对齐（``mode`` / ``thumb_provider`` /
            #    插入落点三项）：控制器会按 mode/position 传参，少一个参数就是
            #    "点了没反应"。2026-11-16 起弹窗没有 ``removed_files``。
            self.files = list(files)
            self.mode = mode
            self.thumb_provider = thumb_provider
            self.position_default = kwargs.get("position", "after")
            self.current_row = kwargs.get("current_row", -1)
            self.total = kwargs.get("total", 0)

        def exec(self) -> int:
            return 1

        def picked_files(self):
            return self.files[:2]

        def auto_mode_file(self):
            return None
    st._FakeDialog = _FakeDialog

    class _FakeManyDialog(st._FakeDialog):
        """替身弹窗：勾选全部候选——「开始拼版」按每两张一页配对。"""

        def picked_files(self):
            return list(self.files)
    st._FakeManyDialog = _FakeManyDialog

    class _FakeOneDialog(st._FakeDialog):
        """替身弹窗：只勾一张——单张单独成页（用户 2026-09-30）。"""

        def picked_files(self):
            return self.files[:1]
    st._FakeOneDialog = _FakeOneDialog

