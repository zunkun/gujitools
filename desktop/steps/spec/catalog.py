# -*- coding: utf-8 -*-
"""步骤清单 :data:`SPECS` 及由它派生的主链 / 可选节点 / 导航清单。"""

from __future__ import annotations

from desktop.steps.spec.constants import IMAGE_FILTER, PDF_FILTER
from desktop.steps.spec.step_spec import StepSpec

#: 左侧导航 / 任务流程共用的步骤清单（顺序即界面顺序）。
#:
#: ⚠️ 这里是**步骤元数据的唯一事实来源**：新增一个步骤 = 加一条 + 写它的 job，
#: 壳层、模块页、任务流程都不需要各自再写一份文案/过滤串/输出规则。
SPECS: tuple[StepSpec, ...] = (
    # ---- 流程主链 · 第 1 步 ----
    StepSpec(
        key="extract",
        role="stage",
        command="extract",
        title="图片提取",
        stage_title="提取图片",
        short="提取",
        nav=True,
        # 导航文案与 ``title`` 分开：这一列回答"这一步干什么"，页头仍是
        # 完整的「图片提取」（用户 2026-10-03 要求导航统一带对象名）。
        nav_title="PDF/DjVu提取",
        nav_tooltip="从 PDF 或 DjVu 提取页面图片",
        # ⚠️ 别用 ZIP_FOLDER：那是"压缩包/解压"，用户会以为这步跟压缩文件
        #    有关；这步的真实语义是"从源文件把图导出来"。
        nav_icon="IMAGE_EXPORT",
        subtitle="选择一个 PDF 或 DjVu，把每页渲染成图片",
        panel="ExtractPanel",
        pick_label="选择 PDF/DjVu",
        # ⚠️ 单位是"页"不是"PDF"：这一步处理的是 PDF 里的每一页。
        progress_noun="页",
        run_label="开始提取",
        # 详情页按钮文案（用户 2026-11-17）：按钮直接说出这一步干什么，
        # 不再用通用的默认文案。独立任务页仍用上面的 ``run_label``。
        run_button_text="提取文档图片",
        file_filter=PDF_FILTER,
        flat_output=True,
        output_suffix="_提取",
        inputs=("pdf",),
        outputs=("pages",),
        preview_attr="extract_result_viewer",
        # ⚠️ ``pages`` 是「续跑」时按缺失页**派生**的一次性参数，不是用户意图：
        #    自动回填它会让下一次点执行只跑那一小段页码（用户看到"只提取了一半"）。
        #    只在**自动**回填时跳过；手动挑历史仍原样回填（那是"照那次再跑一遍"）。
        auto_fill_skip=("pages",),
        drop_icon="svg:PDF_FILE",
        drop_title="把 PDF/DjVu 拖到这里",
        drop_hint="也可以点这里选择一个 PDF 或 DjVu 文件",
        # ⚠️ **只支持文件**（用户 2026-10-03：「PDF 只支持文件」）。
        #    extract 之前允许整个文件夹：里面每个 PDF 各自一个子目录摆图。
        #    但那与本模块「选一个 PDF → 看它的每一页」的用法不符——一次拖一
        #    摞书进来，用户在预览里根本分不清哪张图属于哪本书，而单 PDF 的
        #    平铺收尾（`flat_output`）本来也只对"一个 PDF"设计。
        #    `accepts_dir=False` 同时让大输入区不摆「选择文件夹」按钮
        #    （摆一个注定被拒的入口是骗人，见 source_zone._build_buttons）。
        accepts_dir=False,
    ),
    # ---- 流程主链 · 第 2 步 ----
    StepSpec(
        key="detect",
        role="stage",
        command="detect",
        title="检测文本框",
        short="检测",
        nav=True,
        nav_title="检测文本框",
        nav_tooltip="检测每页的内容框并导出坐标",
        # ⚠️ 别用 SEARCH：放大镜会被读成"查找"。这步是"框出页面内容"，
        #    内置图标没有这个图形，用自绘的取景框 + 文本行（``svg:`` 前缀 →
        #    ``desktop.ui.icons.CustomIcon``，壳层经 resolve_nav_icon 解析）。
        nav_icon="svg:SCAN_TEXT_BOX",
        subtitle="拖入图片或图片文件夹，检测每页的内容框；可在图上手绘修正后导出坐标 JSON",
        panel="DetectPanel",
        pick_label="选择图片",
        progress_noun="张",
        file_filter=IMAGE_FILTER,
        output_suffix="_检测",
        # ⚠️ **两个动作**（用户 2026-10-22）：
        #    · 「检测文本框」= 只检测、只出框（``boxes.json``），供预览标注与人工修正；
        #    · 「分割图片」（原「提交本次任务」，用户 2026-11-17 改名）= 把**每个
        #      检测框**各自裁成一张图，落 ``stages/detect``（``pages`` 端口）。
        #    所以这一格既是 ``boxes`` 的产出方，也是 ``pages`` 的产出方——
        #    去底色吃的是**提交后的裁图**，不再是原始页 + 检测框。
        #    没提交就不算这一步完成：下一步的输入目录里没有东西，自然转不过去。
        inputs=("pages",),
        outputs=("boxes", "pages"),
        preview_attr="detect_viewer",
        # detect 无表单参数、历史回填没用武之地，右栏改显「检测结果统计」。
        panel_extra="detect_stats",
        # 按钮文案：用户 2026-10-22 定（不再用通用的默认文案，那个说不清这一步干什么）
        run_button_text="检测文本框",
        has_submit=True,
        drop_icon="PHOTO",
    ),
    # ---- 流程主链 · 第 3 步 ----
    StepSpec(
        key="rembg",
        role="stage",
        command="rembg",
        title="去底色",
        stage_title="图片去底色",
        short="去底",
        nav=True,
        nav_title="图片去底色",
        nav_tooltip="整图去底色 / 二值化 / 保留印章",
        # ⚠️ 别用 PALETTE：调色板会被读成"调色/取色"；这步的主语义是
        #    "把底色擦掉"（二值化/保留印章是它的模式），橡皮擦更直白。
        nav_icon="ERASE_TOOL",
        subtitle="拖入图片或图片文件夹，批量去底色 / 二值化（可保留印章）",
        panel="RembgPanel",
        pick_label="选择图片",
        progress_noun="张",
        run_label="开始去底色",
        file_filter=IMAGE_FILTER,
        output_suffix="_去底",
        # ⚠️ 2026-10-22 用户口径：**去底色直接整个图片去底色**。
        #    这一步没有 area/border，按检测框裁图改由「检测文本框」的
        #    「分割图片」完成（见 detect 那条的说明）。因此这里只吃
        #    上游的图片——默认流程里就是 detect 提交后的裁图。
        #    事实依据：``functions/rembg.py`` 从来只按整张图算阈值。
        inputs=("pages",),
        outputs=("pages",),
        preview_attr="rembg_viewer",
        # ⚠️ 2026-10-22 用户口径：去底色**只有一步**——点主按钮直接把
        #    整图去底色结果落到 ``stages/rembg``，不再有「生成预览 → 提交」。
        #    按钮文案（用户 2026-11-17）：「执行去底色」→「图片去底色」。
        run_button_text="图片去底色",
        has_submit=False,
        drop_icon="PHOTO",
        drop_title="把图片拖到这里",
        drop_hint="也可以点这里选图片或整个文件夹（一张、一批都行）",
    ),
    # ---- 流程主链 · 第 4 步 ----
    StepSpec(
        key="print",
        role="stage",
        command="print",
        # ⚠️ 步骤名 = 「PDF排版」，**不是**「生成PDF」（用户 2026-10-07）：
        #    默认流程图 ``static/task_default.bpmn`` 里那格本来就叫「PDF排版」
        #    （用户自己在 bpmn.io 上起的名），而「生成PDF」是挂在它后面的**结束
        #    事件**。以前步骤名与图上叫法各说各话，于是流程条/面板/进度写
        #    「生成 PDF」、图上写「PDF排版」，同一件事两个名字。现在统一成图上的
        #    叫法：`title`/`nav_title`/`stage_title` 都是「PDF排版」，
        #    `ports.stage_label("print")` 派生的 `STAGE_LABELS`、BPM 调色板新节点
        #    的默认名也就自动与流程图一致了。
        #    而**动作按钮仍叫「生成PDF」**（`run_label` / `run_button_text`）——
        #    「PDF排版」是这一步的**名字**，「生成PDF」是这一下**按下去做的事**，
        #    两者刻意分开（`run_button_text` 与 `title` 本来就是两组字段）。
        title="PDF排版",
        # 流程条 / BPMN 节点名（用户 2026-10-07 与流程图统一）：见上面那段。
        # 显式写出来而不是靠 `stage_title` 为空回落到 `title`——这一格有
        # endEvent 叫「生成PDF」，两处的区别正是本条注释在说的事，值得钉住。
        stage_title="PDF排版",
        short="PDF",
        nav=True,
        nav_title="PDF排版",
        # 排到导航**最后**（用户 2026-10-03）：这一步吃的是前几步的产物，
        # 出书是收尾动作。流程条上的第4 步位置不受影响（那是 FLOW_STAGES）。
        nav_order=100,
        nav_tooltip="把成品图按版面合成 PDF",
        nav_icon="svg:PDF_FILE",
        subtitle="拖入成品图文件夹，按版面合成 PDF（页序按文件名）",
        panel="PrintPanel",
        pick_label="选择图片",
        progress_noun="页",
        # ⚠️ 按钮文案**刻意**留在「生成PDF」：它是这一下按下去做的事，不是这一步
        #    的名字（步骤名见上面的 ``title``/``stage_title`` =「PDF排版」）。
        run_label="生成PDF",
        file_filter=IMAGE_FILTER,
        artifact_is_file=True,
        output_suffix="_成书",
        inputs=("pages",),
        outputs=("pdf",),
        preview_attr="print_preview",
        run_button_text="生成PDF",
        # 第四步参数最多（版面/页码/字体…），右栏要更宽才不挤。
        control_width=(400, 580),
        # pdf_name / title_text 始终从源 PDF 名派生：历史里存的是旧值或用户
        # 曾经填的自定义名，**不应覆盖**当前任务的规则值（手动挑历史也不回填）。
        history_skip=("pdf_name", "title_text"),
        drop_icon="PHOTO",
        drop_title="把成品图拖到这里",
        drop_hint="也可以点这里选图片或整个文件夹（页序按文件名排序）",
    ),
    # ---- 流程条上的可选节点（有独立模块页，但不在 STAGES 里）----
    StepSpec(
        key="imposition",
        role="optional",
        command=None,
        title="拼图",
        stage_title="图片拼版",
        short="拼版",
        nav=True,
        nav_title="图片拼版",
        nav_tooltip="多页图片拼版与版式调整",
        # ⚠️ 别用 PHOTO：一张照片表达不出"多页拼成一版"，而且 PHOTO 同时是
        #    好几个步骤大输入区的图标，导航里再用就没辨识度。TILES 的
        #    四块平铺正是"多页拼版"的形状。
        nav_icon="TILES",
        subtitle="拖入一批图片，拼版后导出成品图（每两张一页）",
        panel="desktop.components.imposition:ImpositionPanel",
        pick_label="选择图片",
        progress_noun="页",
        file_filter=IMAGE_FILTER,
        allow_multi=True,
        output_name="拼图成品",
        inputs=("pages",),
        outputs=("pages",),
        drop_icon="PHOTO",
        drop_title="把这批图片拖到这里",
        drop_hint="也可以点这里选一批图片，或直接拖一个图片文件夹进来",
    ),
)

#: 全部步骤 key（顺序同 :data:`SPECS`）
STEP_KEYS: tuple[str, ...] = tuple(spec.key for spec in SPECS)

#: 默认流程**主链**的步骤 key（顺序即执行顺序）——即 ``desktop.store.STAGES``
#: 的事实来源。⚠️ 只取 ``role == "stage"``：可选节点（拼版）不在主链上。
FLOW_STAGES: tuple[str, ...] = tuple(spec.key for spec in SPECS if spec.role == "stage")

#: 流程条上的**可选节点** key（排在主链之后的下标处，见
#: ``desktop.store.IMPOSITION_INDEX``）。目前只有拼版一个，故用元组而非单值，
#: 将来加第二个可选节点时不用改调用方。
OPTIONAL_STEPS: tuple[str, ...] = tuple(spec.key for spec in SPECS if spec.role == "optional")

#: 每个 spec 在 ``SPECS`` 里的书写次序（按身份取 key，不依赖 ``__eq__``）——
#: :data:`NAV_STEPS` 排序的次键，见那里的说明。
_nav_written_index: dict[int, int] = {id(spec): i for i, spec in enumerate(SPECS)}

#: 有独立模块页、要进左侧导航的步骤 key——即 ``desktop.modules.MODULES``
#: 的事实来源。
#:
#: 排序 = ``(nav_order, 书写次序)``：显式给了 ``nav_order`` 的按它排、没给的
#: （``0``）保持书写次序兜底。**显式带序号作次键**——只按 ``nav_order`` 排的话
#: Python 的 ``sorted`` 恰好是稳定排序、原序即 ``SPECS`` 书写序，本就是想要的
#: 兜底；把序号写出来是为了让"没声明的维持原位"这条规则**读得出来**，而不是要读者
#: 知道 ``sorted`` 的稳定性质。
NAV_STEPS: tuple[str, ...] = tuple(
    spec.key
    for spec in sorted(
        (s for s in SPECS if s.nav),
        key=lambda s: (s.nav_order, _nav_written_index[id(s)]),
    )
)


def spec_by_key(key: str) -> StepSpec | None:
    """按 key 取步骤元数据；不存在返回 ``None``。"""
    for spec in SPECS:
        if spec.key == key:
            return spec
    return None
