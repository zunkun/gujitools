# -*- coding: utf-8 -*-
"""缺源提示：入口输入类型判定、页内提示层、页头按钮红框高亮。"""

from __future__ import annotations

from desktop.ui import theme as T
from desktop.ui.widgets import mark_input_entry
from desktop.utils.files import list_stage_images
from typing import TYPE_CHECKING, Any, Callable, cast


#: 页头红字：缺哪种输入就说哪件事（键与 ``_missing_input_kind`` 的返回值对应）。
#: ⚠️ **两套文案不能混用**（用户 2026-10-06）：对"流程第一步是检测"的用户说
#: "请上传 PDF"是错的引导——他该去放图。
_MISSING_INPUT_TEXT = {
    "pdf": "尚未选择源文件：本流程需要 PDF/DjVu 源文件，请点右侧「选择源文件」"
    "上传后才能执行各步骤。",
    "images": "本流程第一步需要图片：请点右侧的图片按钮上传，"
    "或把图片/图片文件夹放进任务目录下的 stages/input。",
}


def _set_tool_highlight(button, on: bool) -> None:
    """给页头某个工具按钮加/去「该点这里」的**红框高亮**。

    ⚠️ 用样式表而不是换成 ``PrimaryPushButton``：那会让这一排工具按钮
    **尺寸**变掉（文字按钮比图标按钮宽），把页头撑变形。qfluentwidgets 的
    按钮本来就是整串 setStyleShell 进去的（见 ``desktop/ui/widgets.py``
    里的 ``bold_button`` 说明），追加边框/底色是安全的。
    ⚠️ 去掉时必须设成**空串**：留着上一次的红框会让"已经不缺了"看起来
    还缺。
    """
    if button is None:
        return
    on = bool(on)
    # ⚠️ **状态没变就别重复 setStyleSheet**（2026-11-21「内存越用越大」）：
    #    qfluentwidgets 的 StyleSheetManager 每设一次就给控件挂一对 watcher
    #    （CustomStyleSheetWatcher / DirtyStyleSheetWatcher），旧的不解绑；切
    #    步骤/刷新清单都会走到这里，反复设置就会一路堆着（实测每轮上百个）。
    if getattr(button, "_tool_hl_on", None) is on:
        return
    button._tool_hl_on = on  # type: ignore[attr-defined]
    if on:
        button.setStyleSheet(
            f"ToolButton {{ border: 1.5px solid {T.DANGER};"
            f" border-radius: 6px; background-color: {T.DANGER_SOFT}; }}"
            f"ToolButton:hover {{ background-color: {T.DANGER_SOFT}; }}"
        )
    else:
        button.setStyleSheet("")


class ManifestSourcePromptMixin:
    """缺源提示层与入口工具按钮高亮。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _content_top: Any
        _is_aggregate_task: Any
        _on_pick_source: Any
        _on_source_prompt_dismissed: Any
        insert_pages: Any
        insert_pages_from_folder: Any
        source_path: Any
        store: Any
        task_id: Any

    def _entry_input_kind(self) -> str:
        """本任务流程**入口那一步**要用户提供什么：``"pdf"/"images"/""``。

        ⚠️ 判据只有一份：:func:`desktop.steps.ports.flow_entry_input_kind`
        （用户 2026-10-06 三条规则的唯一实现处——①「图片提取」打头只显示
        PDF；②检测/排版/去底色/PDF排版 打头只显示图片+文件夹；③非第一个
        流程节点不配输入控件）。没有任务时按**默认流程**给（入口是
        「图片提取」⇒ ``"pdf"``），与 :meth:`flow_slots` 的兜底同源。

        ⚠️ **聚合任务恒 ``""``**：它的入口输入由成员产物汇集而来，不是用户
        上传的——显示"选择图片/文件夹"按钮只会让人以为这台任务要自己喂图。
        """
        if self._is_aggregate_task():
            return ""
        from desktop.steps.ports import flow_entry_input_kind

        task_id = getattr(self, "task_id", None)
        if not task_id:
            from desktop.steps.scheduler import load_default_diagram

            return flow_entry_input_kind(load_default_diagram())
        return flow_entry_input_kind(self.store.task_diagram(task_id))

    def _missing_source(self) -> bool:
        """这个任务**现在缺源 PDF 吗**（该催用户补 PDF）。

        ⚠️ 两个条件都要满足，缺一不可：
        ①**流程入口要 PDF**（``_entry_input_kind() == "pdf"``）。2026-10-06
        新口径：输入控件只跟着**第一个流程节点**走——「图片提取」不是入口
        时页头连 PDF 按钮都不显示，红字/提示自然也不能催 PDF，否则指向一个
        不存在的按钮（旧判据 ``flow_needs_source_pdf`` 问"流程里**任何**一步
        要不要 PDF"，extract 挪到中间时就会催一个藏起来的按钮）；
        ②**这个任务确实没有**（``source_path is None``，即"还没选"而不是
        "文件丢了"——文件丢了是另一条错误提示，不该混进这条）。

        ⚠️ "缺 PDF"与"缺入口图片"是**两件不同的事**（用户 2026-10-06）：
        自定义流程把「检测文本框」放第一步时压根不碰 PDF，这时该催的是
        "往输入目录放图"。合并判据见 :meth:`_missing_input_kind`。
        """
        if self.source_path is not None:
            return False
        return self._entry_input_kind() == "pdf"

    def _missing_entry_images(self) -> bool:
        """这个任务**现在缺入口图片吗**（该催用户上传图）。

        场景（用户 2026-10-06）：「非图片提取节点如果做第一个节点」——自定义
        流程第一步是「检测文本框」这类**不吃 PDF** 的步骤，它的 ``pages`` 输入
        沿图回溯不到上游，回落到入口图片目录 ``stages/input/``
        （见 :func:`desktop.steps.ports.resolve_input_with_entry`）。那个目录
        空着的话，第一步就无从下手——而界面一点提示都没有，用户只能对着空的
        预览区猜。

        判据 = **流程入口要图片**（``_entry_input_kind() == "images"``，与
        ``flow_needs_entry_images`` 同判：入口阶段不吃源 PDF）**且入口目录里
        确实没有图**。⚠️ 两个都要：用户放过图之后就不该再被催。
        """
        if not self.task_id:
            return False
        if self._entry_input_kind() != "images":
            return False
        return not self._entry_dir_has_images()

    def _entry_dir_has_images(self) -> bool:
        """入口图片目录（``stages/input/``）里有没有可用的图。"""
        task_id = self.task_id
        assert task_id is not None, "入口目录检查只会在任务态出现"
        try:
            directory = self.store.task_input_dir(task_id)
        except ValueError:
            return False
        # ⚠️ 用现成的 ``list_stage_images``（同一套后缀表+ 自然排序，
        #    入口目录和阶段输出目录"什么算一张图"必须一致）。
        return bool(list_stage_images(directory))

    def _missing_input_kind(self) -> str:
        """当前缺哪种输入：``"pdf"`` / ``"images"`` / ``""``（什么都不缺）。

        ⚠️ 入口只吃一样东西（:meth:`_entry_input_kind`），所以两种缺
        **互斥**：入口要 PDF 就只可能缺 PDF，要图片就只可能缺图片。
        （"PDF 优先"的旧排序已随"判据跟着入口走"作废——extract 不在入口
        时连 PDF 按钮都不显示，不存在"两种都缺"。）

        ⚠️ 界面**所有**"缺输入"的表现都走这一个判据（按钮高亮 / 页头红字 /
        提示层文案）——散成两处各判各的，漂移起来就是"红字说缺图、弹窗说缺
        PDF"（用户 2026-10-06 报过文案重复/矛盾的类似问题）。
        """
        if self._missing_source():
            return "pdf"
        if self._missing_entry_images():
            return "images"
        return ""

    def _source_prompt_content(self) -> dict:
        """提示层文案：按缺的是 PDF 还是入口图片给**两套**说法。

        ⚠️ 不能一套文案通吃："这个任务还没有 PDF"对"流程第一步是检测"的
        用户是**错的引导**——他该去放图，不是去找 PDF。文案与按钮文案都跟着
        判据走（用户 2026-10-06：「应该提醒上传输入目录或者图片」）。
        """
        from desktop.steps.ports import flow_entry_stage, stage_label

        if self._missing_input_kind() != "images":
            return {}
        # ⚠️ 只有任务态才会判成"缺入口图片"（见 _missing_entry_images）
        task_id = self.task_id
        assert task_id is not None, "缺入口图片提示只会在任务态出现"
        try:
            entry_stage = flow_entry_stage(self.store.task_diagram(task_id))
            entry = stage_label(entry_stage) if entry_stage else "第一步"
        except (OSError, ValueError):
            entry = "第一步"
        return {
            "title": "这个流程的第一步需要图片",
            "body": (
                f"当前流程的第一步是「{entry}」，"
                "需要你提供图片作为输入。\n\n"
                "· 选择图片目录 → 选一个文件夹，里面的图片会整批放进"
                "本任务的输入目录；\n"
                "· 稍后再说 → 也可以直接点页头右上角那两个红框按钮"
                "（插图片 / 选文件夹），或把图片拷进任务目录下的 stages/input。"
            ),
            "hint": "内容区暂时不可操作，页头与右上角按钮照常可用。",
            "later_text": "稍后再说",
            # ⚠️ 按钮**直接选目录**（用户 2026-10-06："改成选择图片目录"）：
            #    一个任务一两百页图，逐张多选不现实，而"把整本扫描结果的文件夹
            #    丢进来"才是最自然的用法。⚠️ 文件对话框（``getOpenFileNames``）
            #    **选不了目录**，所以必须是 ``getExistingDirectory`` 那条路。
            "pick_text": "选择图片目录",
            # ⚠️ 告诉宿主点了要开**目录**框（而不是文件框）——组件自己不决定
            #    打开哪种对话框，只把意图传出去。
            "pick_kind": "folder",
        }

    def _refresh_source_actions(self) -> None:
        """按**流程入口要什么输入**调页头三颗按钮的显隐 + 高亮 + 红字 + 提示语。

        用户 2026-10-06 的三条规则，判据唯一来源 :meth:`_entry_input_kind`：
          ①「图片提取」打头 ⇒ **只显示 PDF 按钮**——提取的输入是源 PDF，
            摆着图片/目录入口会让人以为这一步要喂图；
          ②检测/排版/去底色/PDF排版 打头 ⇒ **PDF 按钮整颗藏起来**，只留
            图片 + 文件夹两个红框入口（用户："不显示 pdf，只显示图片输入
            和文件输入"）；
          ③这些输入控件只属于**第一个流程节点**——没有功能入口（打头的
            节点没接功能）⇒ 三颗全藏；预览区左下角的「＋/📁」也只在入口
            那一步的查看器上出现（见 :meth:`_sync_viewer_input_entries`）。

        ⚠️ **显隐与"缺不缺"是两回事**：按钮在不缺时也得住着（补选/换 PDF、
        再补几张图都靠它），高亮和红字才跟着 :meth:`_missing_input_kind`
        走。判据搞反的话，空壳任务（还没选 PDF 但流程要）会把补救入口一起
        藏掉，用户就再也没法自己补了。
        """
        button = getattr(self, "source_button", None)
        insert = getattr(self, "insert_button", None)
        insert_dir = getattr(self, "insert_dir_button", None)
        # ⚠️ **所有"缺输入"的表现都读这一个判据**（``_missing_input_kind``）。
        #    缺的不只是 PDF：自定义流程第一步是「检测文本框」时该催的是
        #    "上传图片"（用户 2026-10-06），那时高亮的必须是**图片按钮**。
        kind = self._missing_input_kind()
        entry_kind = self._entry_input_kind()
        # ---- 聚合任务专属的「重新汇集」（入口输入按钮对它全藏）----
        agg_button = getattr(self, "aggregate_refresh_button", None)
        if agg_button is not None:
            agg_button.setVisible(self._is_aggregate_task())
        # ---- 显隐：入口要 PDF ⇒ 只亮 PDF；要图片 ⇒ 只亮两个图片入口 ----
        needs_pdf = entry_kind == "pdf"
        needs_images = entry_kind == "images"
        if button is not None:
            button.setVisible(needs_pdf)
        if insert is not None:
            insert.setVisible(needs_images)
        if insert_dir is not None:
            insert_dir.setVisible(needs_images)
        # ---- 高亮：缺什么亮什么 ----
        _set_tool_highlight(button, needs_pdf and kind == "pdf")
        # ⚠️⚠️ 图片入口**同时**带"常驻红框"（入口标识）与"缺图片时高亮"
        #    （动态提醒），而 ``_set_tool_highlight(button, False)`` 会
        #    ``setStyleSheet("")`` ——**把常驻红框一起抹掉**（用户 2026-10-06
        #    要求"都是红色框住"，那红框不能只在缺图时才出现）。
        #    所以：先按动态判据走一遍，**再无条件重贴常驻红框**。
        #    ⚠️ 别"优化"成两者只用一个——那会退回"入口看不出该点哪儿"。
        #    （选目录按钮原先没进这套——它同样是图片入口，缺图时一样该亮。）
        for entry_button in (insert, insert_dir):
            _set_tool_highlight(entry_button, kind == "images")
            if entry_button is not None:
                mark_input_entry(entry_button)
        # ---- 按钮提示语：跟着"缺什么"变（不变会指错方向）----
        if button is not None:
            button.setToolTip(
                "这个任务还没有 PDF，点此选择源文件"
                if kind == "pdf"
                else "更换这个任务的 PDF 源文件"
            )
        if insert is not None:
            insert.setToolTip(
                "本流程第一步需要图片，点此选择图片（放进输入目录）"
                if kind == "images"
                else "为本任务插入图片（放到入口图片目录）"
            )
        # ---- 页头红字：缺文件时一直显示，直到补上（toast 会自己消失）----
        warning = getattr(self, "source_warning", None)
        if warning is not None:
            warning.setText(_MISSING_INPUT_TEXT.get(kind, ""))
            warning.setVisible(bool(kind))
        # ⚠️ 不缺了就收提示层（补上文件的路径不都经过 _apply_source，
        #    比如 store 侧直接改的）
        if not kind:
            self._dismiss_source_prompt()
        # ---- 左下角「＋/📁」跟随同一个入口判据（规则③）----
        self._sync_viewer_input_entries()

    def _sync_viewer_input_entries(self) -> None:
        """预览区左下角「＋/📁」跟随流程入口（用户 2026-10-06 规则③）。

        这些按钮与页头那对是**同一个动作**（都往任务清单插图片），过滤口径
        必须一致：只在**入口那一步**的查看器上出现，且入口得吃图片——

        - 入口是「图片提取」⇒ 提取页的输入是 PDF（规则①），它自己那页
          **不显示**图片入口；
        - 入口不是某一步 ⇒ 那一步的查看器**不存在**这些输入控件（规则③），
          它的输入来自上游产物；
        - 入口是「检测文本框」这类吃图的 ⇒ 只有它的查看器亮出「＋/📁」。

        ⚠️ 步骤→查看器走 ``StepSpec.preview_attr``（与方向键翻页同一份映射），
        这里别再写第二份 ``stage → 控件属性名`` 表。
        ⚠️ 空态文案只改**非入口**步骤的查看器：入口那一步的文案在构造处
        已经说对了该干什么（extract「执行本步骤」/ detect「点下方＋」），
        用"等上游"去覆盖反而指错方向——入口没有上游。
        """
        from desktop.steps.ports import flow_entry_stage, spec_for_stage

        #: 入口步骤自己的空态文案（与 view.py 构造处一致；入口不该被改写）
        entry_hints = {
            "extract": "尚未提取，点击右侧「提取文档图片」",
            "detect": "暂无图片，请点下方「＋」插入图片或整个文件夹，"
            "或把图片放进本任务的输入目录",
        }
        entry_kind = self._entry_input_kind()
        task_id = getattr(self, "task_id", None)
        diagram = self.store.task_diagram(task_id) if task_id else None
        entry = flow_entry_stage(diagram) if diagram is not None else None
        for stage in ("extract", "detect"):
            spec = spec_for_stage(stage)
            attr = spec.preview_attr if spec else ""
            viewer = getattr(self, attr, None) if attr else None
            if viewer is None:
                continue
            visible = entry_kind == "images" and stage == entry
            if hasattr(viewer, "set_insert_visible"):
                viewer.set_insert_visible(visible)
            if hasattr(viewer, "set_empty_hint"):
                if stage == entry:
                    # 入口那一步：恢复构造时的说法（要图就说点＋，要 PDF
                    # 就说去执行）——它没有"上游"可等
                    viewer.set_empty_hint(entry_hints.get(stage, ""))
                else:
                    # 输入入口藏起来后，"请点下方「＋」插入图片"就指错方向
                    # 了：非入口步骤的图来自上游，话术跟着换成"等上游执行"。
                    viewer.set_empty_hint(
                        "暂无图片：这一步的输入来自上游步骤，"
                        "执行上游后这里会显示结果"
                    )

    def _prompt_missing_source(self) -> None:
        """进任务详情时**提示**该上传 PDF（用户 2026-10-06）。

        用 :class:`MissingSourcePrompt`（页内**非模态**提示层）而不是
        ``MessageBox``，三个原因都是被用户截图逼出来的（见该组件的模块头）：
        库里遮罩的尺寸只在**构造那一刻**取一次（于是只盖住页面左上角一小块）、
        它铺满 parent 所以**留不下页头**、它是模态的所以**按钮点了没反应**。

        ⚠️ **每次进入都弹**（用户 2026-10-06："没有选择源文件，为何弹窗也没有了，
        每次进入都要检测"）。⚠️ 别学我上一轮加的"提示层已存在就不再弹"——
        那看着像省事，实际是**第二次进同一个任务时提示再也不出现**，而用户
        恰恰是忘了才要重新进来提醒他一下的。
        已建过的提示层**复用**（重建会丢信号连接与拖动位置），只是重新显示 +
        重铺几何。
        """
        if not self._missing_input_kind():
            self._dismiss_source_prompt()
            return
        prompt = getattr(self, "_source_prompt", None)
        if prompt is None:
            from desktop.components.missing_source_prompt import (
                MissingSourcePrompt,
            )

            prompt = MissingSourcePrompt(self, self._content_top)
            # ⚠️ 「现在选择」按缺的东西分派：缺 PDF 去选文件、缺图去选图片。
            #    ⚠️**连的是信号**（``connect`` 那一刻就绑定了当时的槽），
            #    所以宿主这边换实现不会影响它——别用"替换页面方法"的方式
            #    去做这件事（自测踩过：替换属性对已连信号完全无效）。
            prompt.picked.connect(self._on_prompt_pick_input)
            prompt.dismissed.connect(self._on_source_prompt_dismissed)
            self._source_prompt = prompt
        # ⚠️ 每次显示前**刷文案**：同一个提示层对象会被复用（重建会丢信号
        #    连接与拖动位置），而缺的东西可能变了——上一次说"缺 PDF"、
        #    这一次说"缺图片"，文案不刷就会对着错的目标催人。
        prompt.configure(**self._source_prompt_content())
        prompt.show_prompt()

    def _on_prompt_pick_input(self, kind: str = "") -> None:
        """提示层那个主按钮：按缺的是什么 **+ 按钮要哪种对话框** 去动作。

        :param kind: ``"folder"``＝要**目录**（缺入口图片时的默认，用户
            2026-10-06："改成选择图片目录"）；空/``"files"``＝要文件。

        ⚠️ 目录框与文件框是**两个不同的 QFileDialog 调用**
        （``getExistingDirectory`` vs ``getOpenFileNames``），后者**选不了
        目录**，所以这个分流不能省。
        """
        if self._missing_input_kind() == "images":
            if kind == "folder":
                self.insert_pages_from_folder()
            else:
                self.insert_pages()
        else:
            self._on_pick_source()

    def _dismiss_source_prompt(self) -> None:
        """收掉提示层（如果有）。切任务/ 返回/ 补上文件后都要调。"""
        prompt = getattr(self, "_source_prompt", None)
        if prompt is not None:
            prompt.hide()
