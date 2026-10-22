# -*- coding: utf-8 -*-
"""详情页结构自测：四个阶段的标签页/步骤条/面板/预览区结构。

含「窗口压缩守卫」：控制面板表单统一装在滚动区里，可视区不足时纵向滚动
而不是被静默裁剪（rembg 表单行曾因卡片高度不足而挤进相邻行）。

注意：这些断言必须在**真正显示**详情页之后做。藏在 QStackedWidget 里
未选中的页面从未参与布局，qfluentwidgets ScrollArea 是懒构建的，未显示
时 layout() 为 None、viewport/inner 都是 480x640 的脏默认值——据此算出
的「有没有滚动条」全是假的（详见 _context.show_detail 的说明）。
"""

from typing import Any

NAME = "detail_structure"
DEPENDS: list[str] = ["tasklist"]
TITLE = "详情页结构"


def run(ctx) -> None:
    from qfluentwidgets import ScrollArea

    from desktop.ui import theme as T
    from tests.selftests._context import ok, pump, show_detail

    app, w, d = ctx.app, ctx.w, ctx.d

    # ⚠️ 2026-10-09 合并双标签（用户：只保留一份缩略图）：extract 预览是
    #    ExtractPreviewWidget 单控件——左栏 PDF 页缩略图，切页按需提取显示
    #    产物；不再有 extract_tabs。
    from desktop.components.viewers import ExtractPreviewWidget

    ok("extract 单缩略图预览（双标签已合并）",
       isinstance(d.extract_result_viewer, ExtractPreviewWidget)
       and getattr(d, "extract_tabs", None) is None)
    ok("步骤条 4 步", len(d.step_bar.buttons) == 4)
    # 控制栈/预览栈第 5 位 = 「图片拼版」伪步骤的占位详情（不占步骤条按钮位）
    ok("控制面板 4 个阶段面板 + 拼版占位", d.control_stack.count() == 5)
    ok("预览区 4 个阶段预览 + 拼版占位", d.preview_stack.count() == 5)

    # ---- 流程条「图片拼版」可选节点（判据 = **流程图**）----
    # ⚠️ 2026-10-05 口径变更：可见性看**本任务的流程图**，**不再是**第三步的
    #    区域模式（旧的 area==1）。旧判据既语义错配（area=1 是"每个框各自
    #    外扩"的裁剪方式，与拼版无关），又与用户画的图打架（图上把这一格删了、
    #    area 还是 1，照样冒出来）。
    # ⚠️ isVisible 系列断言必须真显示之后才有意义（见文件头说明），先亮出详情页
    show_detail(ctx, stage=0)
    # 默认模板（task_default.bpmn）里画了「图片拼版」→ 节点出现（虚线、未选择）
    ok("默认流程里画了「图片拼版」→ 拼版节点显示（无需配任何参数）",
       d.step_bar.imposition_node.isVisible() and d._imposition_node_visible())
    ok("拼版节点默认未选择（图上有这一格 ≠ 一定要跑）",
       not d.step_bar.imposition_node.is_selected())
    # 反向钉子：改第三步面板参数**不再**影响可见性（判据只看流程图）
    d.store.save_draft(d.task_id, "rembg", {"type": 2})
    d._refresh_imposition_node()
    pump(app)
    ok("改第三步面板参数**不影响**拼版节点（判据只看流程图）",
       d._imposition_node_visible())
    d.store.clear_draft(d.task_id, "rembg")
    d._refresh_imposition_node()
    pump(app)
    # 箭头顺序：节点前是「去底色→拼版」连接线、后是「拼版→PDF」连接线
    # （回归钉子：插入下标算错时节点会跑到箭头前面，用户截图报过）
    # ⚠️ 流程条里放的是节点的**等宽槽位**（imposition_slot），虚线框在槽位内靠左
    #     贴合文字——两者分开才能同时满足"间距均分"和"框不拉宽"。
    from desktop.components.step_bar import _Connector

    row = d.step_bar.layout()
    node_pos = row.indexOf(d.step_bar.imposition_slot)
    ok("拼版节点夹在两条连接线之间（虚线前面有箭头）",
       node_pos > 0
       and isinstance(row.itemAt(node_pos - 1).widget(), _Connector)
       and isinstance(row.itemAt(node_pos + 1).widget(), _Connector),
       f"pos={node_pos}")
    d.step_bar.imposition_node.clicked.emit()
    pump(app)
    ok("点拼版节点进占位详情", d.control_stack.currentIndex() == 4
       and d.preview_stack.currentIndex() == 4)
    ok("占位详情隐藏执行按钮组",
       not d.run_button.isVisible() and not d.submit_button.isVisible()
       and not d.resume_button.isVisible() and not d.cancel_button.isVisible())
    # ---- 流程条上这一格 = "这一步处理到哪了"（2026-10-18 用户口径）----
    # ⚠️ 判据是**本节点有没有拼版页**，**不是**"在流程中启用图片拼版"这个开关
    #    ——那是**流程级**条件（流程图上「是否拼版」网关问的就是它）。勾了开关但
    #    一页都没拼时这一格仍是"未选择"：没运行过的东西不该亮成"已处理"。
    d.imposition_enabled_checkbox.setChecked(True)
    pump(app)
    ok("勾选启用但还没拼页 → 节点仍「未选择」（没运行过不该亮）",
       not d.step_bar.imposition_node.is_selected())
    from desktop.store import IMPOSITION_STAGE
    # ⚠️ 查表拿格序，别用 ``IMPOSITION_INDEX``（= len(STAGES) = 4）：BPM 驱动后
    # 步骤条格序含可选节点占位，拼版在第 3 格，写死会切到 print 那一格。
    imposition_bar = d.bar_index_of_step(IMPOSITION_STAGE)
    assert imposition_bar is not None     # ⚠️ 图里有「图片拼版」这一格
    d._select_stage(imposition_bar)
    pump(app)
    ok("重新进入拼版详情回填勾选状态", d.imposition_enabled_checkbox.isChecked())
    # 拼了一页 ⇒ 这一格变「已选择」（= 这一步"运行过"）
    # ⚠️ 直接写文档 + 刷流程条（不走 ``_save_imposition_pages``）：那条路会顺带
    #    起后台合成 worker，自测里没必要、还容易在收尾时抓到半跑的线程。
    _scope = d._imposition_scope()
    _doc = d.store.load_imposition_doc(d.task_id, **_scope)
    _doc["pages"] = [{
        "items": [{
            "file": "not-exist-0001.png",
            "rect": [0.0, 0.0, 10.0, 10.0],
            "rotation": 0.0,
        }],
    }]
    d.store.save_imposition_doc(d.task_id, _doc, **_scope)
    d._sync_imposition_step_bar()
    pump(app)
    ok("拼了一页 → 这一格变「已选择」（= 这一格运行过）",
       d.step_bar.imposition_node.is_selected())
    _doc["pages"] = []
    d.store.save_imposition_doc(d.task_id, _doc, **_scope)
    d._sync_imposition_step_bar()
    pump(app)
    ok("把页删光 → 这一格回到「未选择」",
       not d.step_bar.imposition_node.is_selected())

    # ---- 所有节点统一默认宽度（用户 2026-09-30：生效/不生效样式统一）----
    # 旧断言「节点贴着文字、比胶囊窄」已按新口径替代：所有节点（真实步骤
    # 胶囊 + 拼版节点）都有 _NODE_MIN_W 统一下限，状态变化不改变宽度；
    # 节点仍不许被槽位拉宽（Maximum 策略，宽度 = max(sizeHint, 默认宽度)）。
    from desktop.components.step_bar import _NODE_MIN_W
    node = d.step_bar.imposition_node
    ok("所有节点都有统一默认宽度（胶囊与拼版节点 ≥ _NODE_MIN_W）",
       all(it.pill.width() >= _NODE_MIN_W - 2 for it in d.step_bar.buttons)
       and node.width() >= _NODE_MIN_W - 2,
       f"胶囊 {[it.pill.width() for it in d.step_bar.buttons]} 节点 {node.width()}")
    ok("拼版节点不被槽位拉宽（宽度 = max(sizeHint, 默认宽度)）",
       node.width() <= max(node.sizeHint().width(), _NODE_MIN_W) + 2,
       f"节点 {node.width()} vs sizeHint {node.sizeHint().width()}")
    slot = d.step_bar.imposition_slot
    ok("拼版槽位与真实步骤等宽（步骤间距均分）",
       abs(slot.width() - d.step_bar.buttons[0].width()) <= 2,
       f"槽位 {slot.width()} vs 步骤 {[it.width() for it in d.step_bar.buttons]}")

    # ---- 未生效的拼版支路：两侧灰色虚线 + 主线绕行（用户 2026-09-30）----
    # 「拼版不生效 → 画一条线从 rembg 到 print，绕开拼版节点；拼版节点的线
    # 都是灰色的虚线」。连线是否点亮由**启用开关**驱动（2026-10-23 口径：
    # 流向只看开关，第四步从哪取图就是哪条线），与节点的「已选择」外观
    # （set_imposition_selected）互相独立。
    # ⚠️ 上面第 84 行为了验"勾了但没拼页也不亮"把开关勾上了，这里必须先取消
    #    ——否则按新口径流向就是"经过拼版"，绕行线不会出现。
    d.imposition_enabled_checkbox.setChecked(False)
    pump(app)
    # 连接线由 StepBar 底层统一画、从节点框后面穿过（2026-09-30 节点框改
    # 实线 border），状态在 ``_connector_segments()`` 里现算——按
    # (左框 is 节点框, 右框 is 节点框) 认出前端/后端两段。
    bar = d.step_bar
    # ⚠️ 上一段断言停在「拼版详情」里（当前步就是拼版），先挪回第三步
    bar.set_current(2)
    pump(app)
    from PySide6.QtCore import QPoint

    def _impo_segs():
        front = back = None
        for seg in bar._connector_segments():
            if seg[1] is bar.imposition_node:
                front = seg
            elif seg[0] is bar.imposition_node:
                back = seg
        return front, back

    def _plain_tail():
        """节点隐藏口径的普通段（最后一段 = 去底色 → PDF）。"""
        return bar._connector_segments()[-1]

    front, back = _impo_segs()
    ok("未生效 → 前端连接线压灰", front is not None and not front[2],
       f"front={front}")
    ok("未生效 → 前端连接线是虚线", front is not None and front[3])
    ok("未生效 → 后端连接线压灰虚线", back is not None and not back[2] and back[3],
       f"back={back}")
    ok("未生效 → 绕行线存在（去底色→PDF 从节点上方走）",
       bar._bypass_points() is not None)
    points = bar._bypass_points()
    ok("绕行线全部横平竖直（管道式直角折线，无斜线）",
       points is not None and len(points) == 6 and all(
           a[0] == b[0] or a[1] == b[1] for a, b in zip(points, points[1:])
       ), str(points))
    ok("绕行线从节点上方越过（顶边高于节点框）",
       points is not None
       and all(p[1] < bar.imposition_node.mapTo(bar, QPoint(0, 0)).y()
               for p in points[2:4]))
    # 用户 2026-09-30 两条反馈：实线左侧悬空（有一段虚线没被盖住）、
    # 拐弯贴着拼版按钮边缘。起点必须是去底色胶囊中心（实线整段盖住虚线，
    # 胶囊框内那截被实底遮住）；上下竖线离节点左右缘至少 20px。
    left_pill = bar.buttons[-2].pill
    lc = left_pill.mapTo(bar, QPoint(left_pill.width() // 2, left_pill.height() // 2))
    ok("绕行线从去底色胶囊中心出发（实线整段盖住虚线，不再悬空）",
       points is not None and points[0] == (float(lc.x()), float(lc.y())),
       f"points[0]={points[0] if points else None} 胶囊中心=({lc.x()}, {lc.y()})")
    node_tl = bar.imposition_node.mapTo(bar, QPoint(0, 0))
    ok("绕行线上竖线离拼版节点左缘 ≥20px（不贴着按钮拐弯）",
       points is not None and node_tl.x() - points[1][0] >= 20,
       f"x_in={points[1][0] if points else None} 节点左缘={node_tl.x()}")
    ok("绕行线下竖线离拼版节点右缘 ≥20px（不贴着按钮拐弯）",
       points is not None
       and points[3][0] - (node_tl.x() + bar.imposition_node.width()) >= 20,
       f"x_out={points[3][0] if points else None} "
       f"节点右缘={node_tl.x() + bar.imposition_node.width()}")
    bar.set_imposition_selected(True)
    pump(app)
    front, back = _impo_segs()
    ok("只勾「已选择」未生效 → 连接线仍是灰色虚线（外观与流向分离）",
       front is not None and not front[2] and front[3]
       and back is not None and not back[2] and back[3])
    # 用户 2026-09-30：生效/选择**不压蓝底**——高亮底色只属于当前步，
    # 非当前步的拼版节点跟其他节点一样白底。
    ok("选中但不是当前步 → 节点白底（无高亮）",
       bar.imposition_node._background is None,
       f"bg={bar.imposition_node._background}")
    bar.set_imposition_active(True)
    pump(app)
    front, back = _impo_segs()
    ok("生效后前端连接线回到常规规则（去底色完成即绿）",
       front is not None
       and front[2] == (len(bar.buttons) - 2 in bar._completed),
       f"front={front} 去底色完成={len(bar.buttons) - 2 in bar._completed}")
    ok("生效后端连接线点亮", back is not None and back[2])
    ok("生效后连接线恢复实线", front is not None and not front[3]
       and back is not None and not back[3])
    ok("生效后节点徽标转对勾（与真实步骤同款）",
       bar.imposition_node.badge._status == "success",
       f"status={bar.imposition_node.badge._status}")
    # ⚠️ 2026-10-23 口径：徽标跟「这一格处理过没有」（已选择）走，**不跟流向**
    #    走——关掉启用开关后流程图要绕行，但处理过的绿勾照旧（用户在详情页
    #    关掉「在流程图中启用图片拼版」时，PDF排版取上一步的数据，流程图上
    #    这一支不该再经过，但也不该把"处理过"抹掉）。
    bar.set_imposition_active(False)
    ok("退回未生效 → 连接线灰虚线、绕行线回来（流向跟开关走）",
       bar._bypass_points() is not None)
    ok("退回未生效 → 徽标仍是绿勾（徽标跟「已选择/处理过」走）",
       bar.imposition_node.badge._status == "success"
       and bar.imposition_node.is_selected(),
       f"status={bar.imposition_node.badge._status} "
       f"symbol={bar.imposition_node.badge._symbol}")
    bar.set_imposition_selected(False)
    ok("取消「已选择」→ 徽标恢复灰色「＋」",
       bar.imposition_node.badge._status == "pending"
       and bar.imposition_node.badge._symbol == "＋",
       f"status={bar.imposition_node.badge._status} "
       f"symbol={bar.imposition_node.badge._symbol}")
    bar.set_current(bar.imposition_index)      # 当前就停在拼版详情（未生效）
    pump(app)
    ok("当前步是拼版 → 才有高亮底色（与其他节点当前步一致）",
       bar.imposition_node._background is not None,
       f"bg={bar.imposition_node._background}")
    front, back = _impo_segs()
    ok("当前是拼版但未生效 → 前端仍是灰色虚线（不再有当前步例外）",
       front is not None and not front[2] and front[3], f"front={front}")
    ok("当前是拼版但未生效 → 后端仍压灰", back is not None and not back[2])
    bar.set_current(2)
    bar.set_imposition_selected(False)
    pump(app)
    front, back = _impo_segs()
    ok("离开拼版且未生效 → 前端保持灰虚线",
       front is not None and not front[2] and front[3])

    # ---- 节点框语言（用户 2026-09-30 定稿）：所有节点同一套外观，选中/生效
    # 只有背景色差异、没有边框差异；状态表达在徽标（＋/对勾）与副标题上。
    # 连接线由 StepBar 底层画、从节点框后面穿过：框**外**能看到线（真的画了），
    # 线伸进框**内**的部分被节点 SURFACE 实底遮住——渲染成像素来验。
    ok("拼版节点默认未选择", not node.is_selected())
    ok("未生效节点徽标是灰色「＋」（不是对勾）",
       node.badge._status == "pending" and node.badge._symbol == "＋",
       f"status={node.badge._status} symbol={node.badge._symbol}")

    def _near(c, rgb, tol=18):
        return all(abs(a - b) <= tol for a, b in zip((c.red(), c.green(), c.blue()), rgb))

    grab = bar.grab().toImage()
    pill1 = bar.buttons[1].pill.mapTo(bar, QPoint(0, 0))
    pill2 = bar.buttons[2].pill.mapTo(bar, QPoint(0, 0))
    mid_y = pill1.y() + bar.buttons[1].pill.height() // 2
    outside = grab.pixelColor(
        pill1.x() + bar.buttons[1].pill.width() + 6, mid_y
    )
    inside = grab.pixelColor(pill2.x() + 5, mid_y)
    ok("连接线在节点框外可见（线真的画出来了）",
       _near(outside, (0xD6, 0xD6, 0xD6)) or _near(outside, (0x0F, 0x7B, 0x3F)),
       f"outside={outside.name()}")
    ok("连接线伸进节点框的部分被实底遮住（从框后面出发）",
       not _near(inside, (0xD6, 0xD6, 0xD6), 10), f"inside={inside.name()}")
    bar.set_imposition_visible(False)
    pump(app)
    tail = _plain_tail()
    ok("节点隐藏 → 前端那格回归「去底色→PDF」常规段（点亮看完成态）",
       tail[0] is bar.buttons[-2].pill and tail[1] is bar.buttons[-1].pill
       and tail[2] == (len(bar.buttons) - 2 in bar._completed) and not tail[3],
       f"tail={tail}")
    ok("节点隐藏 → 段数回到 3（没有拼版段）",
       len(bar._connector_segments()) == len(bar.buttons) - 1)
    bar.set_imposition_visible(True)
    pump(app)
    ok("节点恢复 → 段数回到 4（拼版两段 + 常规两段）",
       len(bar._connector_segments()) == len(bar.buttons),)

    # ---- 窗口压缩守卫：真显示后再量 ----
    # rembg 表单行最多，可视区最紧张，压缩最先在它身上显形
    rembg_panel = show_detail(ctx, stage=2)
    scroll = rembg_panel.findChild(ScrollArea)
    ok("rembg 表单装在可滚动容器里",
       scroll is not None and scroll.widgetResizable())
    if scroll is None:
        return

    inner = scroll.widget()
    natural = inner.minimumSizeHint().height()
    viewport_h = scroll.viewport().height()
    vb = scroll.verticalScrollBar()

    # 前置：确实触发了压缩场景（可视区装不下表单自然高度）
    ok("可视区装不下表单自然高度（压缩场景成立）",
       viewport_h < natural, f"可视区 {viewport_h} vs 表单 {natural}")
    # 核心：表单不被压扁——内容保持自然高度，高度差交给滚动
    ok("表单保持自然高度而非被压扁",
       inner.height() >= natural - 2, f"{inner.height()} vs {natural}")
    ok("可视区不足时提供纵向滚动（无滚动=被静默裁剪）",
       vb.maximum() == natural - viewport_h,
       f"max={vb.maximum()} 期望 {natural - viewport_h}")

    # 滚到底：底部内容能完整进入可视区
    vb.setValue(vb.maximum())
    pump(app)
    ok("滚到底后底部控件完整可见",
       inner.height() - vb.value() <= viewport_h + 2,
       f"{inner.height()} - {vb.value()} vs {viewport_h}")

    ok("滚动条宽度取自主题常量（细滚动条样式生效）",
       0 < T.SCROLLBAR_WIDTH < 16, f"{T.SCROLLBAR_WIDTH}")

    # 复原：滚回顶部，切回第一步
    vb.setValue(0)
    d._select_stage(0)
    pump(app)

    # ---- 流程图上"画了但没功能"的节点：界面上看得见、点了有解释 ----
    # ⚠️ 用户能在 bpmn.io 里随手加一个「OCR 识别」。以前它被静默丢掉（界面上
    #    根本找不到那一格）＝"改了流程图程序没反应"。现在它占一格、画成灰的
    #    并标注「未接入」，点了告诉你怎么接上或怎么删。
    #    用**独立 store + 独立页面**，不碰 ctx.d（共享详情页）与它的任务。
    from desktop.pages.taskdetail.page import TaskDetailPage as _TDP
    from desktop.steps.bpmn_diagram import (
        KIND_TASK, NO_PAGE, DiagramFlow, DiagramNode, FlowDiagram,
        default_size, stage_of_name,
    )
    from desktop.store import TaskStore as _TS

    probe_store = _TS(ctx.tmp / "unmapped_probe")
    names = ["提取图片", "检测文本框", "OCR 识别", "图片去底色", "PDF排版"]
    nodes, flows, boxes = [], [], []
    for index, name in enumerate(names):
        w, h = default_size(KIND_TASK)
        nodes.append(DiagramNode(f"u{index}", KIND_TASK, name,
                                 stage=stage_of_name(name)))
        boxes.append((40.0 + index * 150.0, 40.0, w, h))
        if index:
            flows.append(DiagramFlow(f"uf{index}", f"u{index - 1}",
                                     f"u{index}"))
    ghost_tid = probe_store.create_task(
        ctx.pdf, "unmapped-probe", "带未知节点",
        diagram=FlowDiagram(nodes=tuple(nodes), flows=tuple(flows),
                            boxes={f"u{i}": b for i, b in enumerate(boxes)}))
    probe = _TDP(probe_store)
    probe.resize(1280, 800)
    probe.show()
    pump(app, times=8)
    probe.set_task(ghost_tid)
    pump(app, times=10)

    ghost_index = probe.bar_index_of_step("OCR 识别")
    ok("图上没功能的节点在步骤条上有那一格（不再凭空消失）",
       ghost_index is not None, str(ghost_index))
    titles = [b.title_label.text() for b in probe.step_bar.buttons]
    ok("它的标题就是图上写的节点名（不被后缀挤掉）",
       "OCR 识别" in titles, str(titles))
    # ⚠️ 「未接入」标在**副标题**上：标题那格宽度有限，后缀会被省略号截成
    #    "（未接…"，反而看不出是什么步骤。
    details = [b.detail_label.text() for b in probe.step_bar.buttons]
    ok("它标注为「未接入」（副标题）",
       any("未接入" in text for text in details), str(details))
    ok("它的栈页号是 NO_PAGE（两个栈里本来就没有它的页）",
       probe.stack_index_of_step("OCR 识别") == NO_PAGE,
       str(probe.stack_index_of_step("OCR 识别")))
    # 点它：停在原地 + 不被记成"上次停留"
    detect_index = probe.bar_index_of_step("detect")
    assert detect_index is not None      # ⚠️ 默认流程里有「检测」这一格
    probe._select_stage(detect_index)
    pump(app, times=4)
    before = probe.step_bar._current
    assert ghost_index is not None       # ⚠️ 上一段已判过那一格存在
    probe._select_stage(ghost_index)
    pump(app, times=4)
    ok("点灰节点不会跳走（仍停在原来那一步）",
       probe.step_bar._current == before,
       f"{before} -> {probe.step_bar._current}")
    ok("也不会被记成上次停留（下次打开不会落到这一步）",
       probe.store.load_last_stage(ghost_tid) != "OCR 识别",
       str(probe.store.load_last_stage(ghost_tid)))
    # 真实步骤照常切
    print_index = probe.bar_index_of_step("print")
    assert print_index is not None        # ⚠️ 默认流程里有「生成PDF」这一格
    probe._select_stage(print_index)
    pump(app, times=6)
    ok("同一张图里真实步骤照常切（灰节点不干扰其它步骤）",
       probe.current_stage() == "print", probe.current_stage())
    ok("灰节点不进控制栈/预览栈（两个栈页数不变）",
       probe.control_stack.count() == 5 and probe.preview_stack.count() == 5,
       f"{probe.control_stack.count()}/{probe.preview_stack.count()}")
    probe.deleteLater()
    pump(app, times=4)

    # ---- 红色虚线框（RedDashFrame，2026-10-13 用户）----
    # 两处动态引导：① 第三步「提交本次任务」预览成功未提交（NEW_VERSION）；
    # ② 拼版面板「在流程中启用图片拼版」可勾未勾且左侧有可拼图。
    from desktop.ui.widgets import RedDashFrame, set_red_frame

    def _frame_of(widget: Any) -> Any:
        """取红框的 Python 强引用（见 ``set_red_frame`` 的 ``_red_dash_frame_ref``）。

        ⚠️ 不用 ``widget.property("_red_dash_frame")``：类型存根把返回值判成
        ``Any | None``，后面每次访问都会被 pyright 报空引用。
        """
        return getattr(widget, "_red_dash_frame_ref")

    # 单元：挂框 → 覆盖层挂在**父控件**上、四周外扩 PAD（不贴身，2026-10-13
    # 用户：「线框高一些，不要紧贴着」）；摘框 → 隐藏（控件复用不重建）；幂等
    from pathlib import Path as _Path

    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtWidgets import QWidget as _QW
    from qfluentwidgets import PushButton

    _submit_src = (_Path(__file__).resolve().parents[2]
                   / "desktop/pages/taskdetail/submit.py").read_text(encoding="utf-8")
    _impo_src = (_Path(__file__).resolve().parents[2]
                 / "desktop/pages/taskdetail/imposition.py").read_text(encoding="utf-8")
    ok("提交按钮红框走 NEW_VERSION 判据（源码护栏）",
       "set_red_frame(self.submit_button, version == NEW_VERSION)" in _submit_src)
    ok("拼版启用开关红框 = 可用+未勾+左侧有拼版页（源码护栏）",
       "set_red_frame(checkbox, frame_on)" in _impo_src
       and "imposition_has_pages()" in _impo_src)

    _host = _QW()
    _host.resize(320, 200)
    probe_button = PushButton("红框探针", _host)
    probe_button.move(40, 60)
    probe_button.resize(160, 36)
    _host.show()
    pump(app, times=2)
    set_red_frame(probe_button, True)
    # ⚠️ 用 ``_red_dash_frame_ref``（Python 强引用）而不是动态属性：
    #    ``property()`` 在类型存根里是 ``None``，pyright 会把后续访问判成空引用。
    frame = _frame_of(probe_button)
    _want = probe_button.geometry().adjusted(-5, -5, 5, 5)
    ok("挂框：覆盖层存在、可见、鼠标穿透、外扩 5px 不贴身",
       frame.isVisible()
       and frame.testAttribute(_Qt.WidgetAttribute.WA_TransparentForMouseEvents)
       and frame.parentWidget() is _host
       and frame.geometry() == _want,
       f"frame={frame.geometry()} want={_want}")
    set_red_frame(probe_button, True)
    ok("重复挂框幂等（不重建第二个覆盖层）",
       _frame_of(probe_button) is frame)
    probe_button.move(80, 100)
    probe_button.resize(200, 40)
    pump(app, times=2)
    ok("宿主挪动/缩放后框跟随（eventFilter 重适配）",
       frame.geometry() == probe_button.geometry().adjusted(-5, -5, 5, 5))
    set_red_frame(probe_button, False)
    ok("摘框：覆盖层隐藏（留控件复用）", not frame.isVisible())
    ok("强制画一次框（grab 不抛异常）",
       not probe_button.grab().isNull())
    # 紧身行容器（高度==按钮高度）：外扩框直接父控件装不下 → 必须爬到
    # 装得下的祖先，否则整框被父控件裁剪得一行不剩（提交按钮框"不显示"
    # 正是这个场景，2026-10-13 用户截图报的）
    from PySide6.QtCore import QRect as _QRect

    _tight = _QW(_host)
    _tight.setGeometry(10, 10, 220, 40)
    _tight.show()
    _btn2 = PushButton("提交探针", _tight)
    _btn2.move(10, 2)
    _btn2.resize(140, 36)
    _btn2.show()
    pump(app, times=2)
    set_red_frame(_btn2, True)
    _frame2 = _frame_of(_btn2)
    _want2 = _QRect(
        _btn2.mapTo(_host, _btn2.rect().topLeft()),
        _btn2.mapTo(_host, _btn2.rect().bottomRight()),
    ).adjusted(-5, -5, 5, 5)
    ok("紧身行：框爬到装得下的祖先（不被父控件裁剪得看不见）",
       _frame2.isVisible()
       and _frame2.parentWidget() is _host
       and _frame2.geometry() == _want2,
       f"parent={_frame2.parentWidget()} geo={_frame2.geometry()} want={_want2}")
    set_red_frame(_btn2, False)

    # 祖先挪动 / 显隐（用户 2026-10-23 报「切步骤节点返回后，提交按钮外的
    # 红框定位不准确」）：目标被父布局整体搬走时**它自己收不到 Move**，
    # 只有祖先收到；框必须盯着整条祖先链，否则停在旧位置（实测差 24px）。
    # 祖先被整组隐藏时（拼版伪步骤）框也必须一起藏，不能浮在别的面板上。
    _row3 = _QW(_host)
    _row3.setGeometry(10, 20, 260, 40)   # 紧身行：外扩框装不下 → 宿主爬到 _host
    _row3.show()
    _btn3 = PushButton("祖先挪动探针", _row3)
    _btn3.setGeometry(10, 2, 160, 36)
    _btn3.show()
    pump(app, times=2)

    def _want3() -> "_QRect":
        return _QRect(
            _btn3.mapTo(_host, _btn3.rect().topLeft()),
            _btn3.mapTo(_host, _btn3.rect().bottomRight()),
        ).adjusted(-5, -5, 5, 5)

    set_red_frame(_btn3, True)
    _frame3 = _frame_of(_btn3)
    ok("祖先挪动前：框位置正确",
       _frame3.geometry() == _want3(),
       f"geo={_frame3.geometry()} want={_want3()}")
    _row3.move(10, 120)
    pump(app, times=2)
    ok("祖先整体挪动后框跟随（目标自身收不到 Move）",
       _frame3.geometry() == _want3(),
       f"geo={_frame3.geometry()} want={_want3()}")
    _row3.hide()
    pump(app, times=2)
    ok("祖先隐藏时框一起隐藏（不浮在别的步骤面板上）",
       not _frame3.isVisible())
    _row3.show()
    pump(app, times=2)
    ok("祖先重新显示后框回到原位并恢复显示",
       _frame3.isVisible() and _frame3.geometry() == _want3(),
       f"visible={_frame3.isVisible()} geo={_frame3.geometry()} want={_want3()}")
    set_red_frame(_btn3, False)
    ok("摘框后即使在显示中也保持隐藏（业务状态与可见性分开）",
       not _frame3.isVisible())
    _host.deleteLater()
    pump(app, times=2)
