# -*- coding: utf-8 -*-
"""BPMN 模型的常量：命名空间、元素类型、默认尺寸、排版容差、节点别名。"""

from __future__ import annotations

# ---------------------------------------------------------------- 命名空间
BPMN_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMNDI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
GUJI_NS = "https://guji.tools/bpmn/2025"

# ---------------------------------------------------------------- 元素类型
KIND_START = "startEvent"
KIND_END = "endEvent"
KIND_TASK = "task"
KIND_EXCLUSIVE = "exclusiveGateway"
KIND_PARALLEL = "parallelGateway"
KIND_INCLUSIVE = "inclusiveGateway"
KIND_INTERMEDIATE = "intermediateCatchEvent"

#: 网关家族（都画成菱形，只是中心符号不同）
GATEWAY_KINDS = frozenset({KIND_EXCLUSIVE, KIND_PARALLEL, KIND_INCLUSIVE})
#: 事件家族（都画成圆，结束/中断事件是双圈）
EVENT_KINDS = frozenset({KIND_START, KIND_END, KIND_INTERMEDIATE})

#: 本模块认识的元素类型（其余类型照旧保留 id/name，绘图时降级成矩形）。
KNOWN_KINDS = frozenset({KIND_TASK, *GATEWAY_KINDS, *EVENT_KINDS})

#: 各类元素的默认尺寸（BPMN 惯例值）——文件里没有 DI 段时按这个排。
DEFAULT_SIZE = {
    KIND_TASK: (100.0, 80.0),
    KIND_START: (36.0, 36.0),
    KIND_END: (36.0, 36.0),
    KIND_INTERMEDIATE: (36.0, 36.0),
    KIND_EXCLUSIVE: (50.0, 50.0),
    KIND_PARALLEL: (50.0, 50.0),
    KIND_INCLUSIVE: (50.0, 50.0),
}
FALLBACK_SIZE = (100.0, 80.0)

#: 自动排版时的横向/纵向间距（仅用于「文件没有 DI 段」的兜底）。
AUTO_GAP_X = 60.0
AUTO_GAP_Y = 150.0
AUTO_PADDING = 24.0
#: 「自动排版」（:meth:`FlowDiagram.relayout`）的层间距/同层行距。
#: 比兜底排版紧凑些——主链要一屏放得下。
LAYOUT_GAP_X = 80.0
LAYOUT_GAP_Y = 56.0
#: 自动排版时注释框与**宿主节点**的间距（注释一律重挂到宿主正下方）。
LAYOUT_NOTE_GAP = 30.0
#: 注释互相压住时的让位步长（往下一格再试）。
LAYOUT_NOTE_STEP = 12.0
#: 连线两端"近似共线"的容差（px）：小于它就直接拉直线，不画L 形台阶。
#: 同一节点的多条出入边要沿边摊开，出口与入口差几像素是常态。
ROUTE_ALIGN_TOLERANCE = 8.0
#: 网关分支"算同一格"的容差（px）：对端中心落在网关中心这个范围内就算
#: 正前方/正下方，否则按九宫格分区（`_corner_pick`）。
CORNER_CELL_EPS = 12.0

#: ``StageSlot.stack_index`` 的哨兵：**两个栈里没有这一页**。
#:
#: 用于"图上画了、但本程序还没有对应功能"的节点（见
#: :meth:`FlowDiagram.stage_slots`）。它们在步骤条上有格子、能点，但点下去
#: 不会切到任何面板——页面据此拦下并解释，而不是拿 ``-1`` 去
#: ``QStackedWidget.setCurrentIndex``（那会静默跳到最后一页，看起来像"点了
#: 跳到别的步骤"，比不跳更难解释）。
NO_PAGE = -1

#: 节点名 → 运行阶段。用于把「人画的中文名」接回程序里的阶段 key。
#:
#: ⚠️ 只在**没有** ``guji:stage`` 属性时才查这张表（属性是显式声明，优先）。
#: 用户用 bpmn.io 画图时不会写扩展属性，只能靠名字接——所以别名要写全
#: （"图片拼版"/"古籍拼版" 都指 ``imposition``）。匹配时先去掉所有空白，
#: 避免"生成 PDF"与"生成PDF"不一致。
#:
#: ⚠️「生成pdf」这个别名**留着**（用户 2026-10-07 之前画的老流程图上，那格就叫
#: 这个名；现在步骤名已统一成「PDF排版」，见 ``StepSpec.stage_title``，但老图
#: 还得认）。删了它，那些老任务的 ``print`` 阶段会掉回"认不出"——节点还在图上，
#: 却不参与运行。
STAGE_ALIASES: dict[str, str] = {
    "提取图片": "extract",
    "提取pdf图片": "extract",
    "提取pdf": "extract",
    "检测文本框": "detect",
    "检测文本": "detect",
    "图片去底色": "rembg",
    "去底色": "rembg",
    "生成pdf": "print",
    "输出pdf": "print",
    "pdf排版": "print",
    "排版": "print",
    "图片拼版": "imposition",
    # ⚠️ 下一行的「拼板」别名**留着**（2026-10-12 统一用字前，模板与导航都
    #    用那个写法；老任务的 flow.bpmn 还得认，删了它们会"认不出"）。
    "图片拼板": "imposition",
    "古籍拼版": "imposition",
    "拼版": "imposition",
}

#: 注释正文里一个字符的平均宽度/行高（px）。注释按 9pt 渲染，中文约 13px宽。
NOTE_CHAR_W = 13.0
NOTE_LINE_H = 16.0
#: 注释框的文字区内边距 + 左侧开口方括号占的宽度（与 bpmn_view 的画法对齐）。
NOTE_CHROME_W = 26.0
#: 注释框单行时的最小/最大宽度（免得短句太空、长句溢出画布）。
NOTE_MIN_W, NOTE_MAX_W = 110.0, 200.0
NOTE_MIN_H = 30.0
