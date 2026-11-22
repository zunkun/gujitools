# -*- coding: utf-8 -*-
"""BPMN 编辑控件的对话框动作（``_DialogMixin``）：添加步骤 / 改名 / 删除确认。

Mixin 只在运行期与 ``BpmnEditor`` 组合；宿主面见 :mod:`._host`，本模块
**不 import** 主类 ``editor``，避免循环导入。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.components.bpmn_editor._qt import (
    QDialog,
    QGridLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CaptionLabel, PushButton

from desktop.ui import theme as T

if TYPE_CHECKING:
    from desktop.components.bpmn_editor._host import BpmnEditorHost as _Host
else:
    _Host = object


class _DialogMixin(_Host):
    """添加步骤 / 改名 / 删除确认（中文按钮）；宿主面见 TYPE_CHECKING。"""

    # ------------------------------------------------------------ 对话框动作
    def ask_add_node(self) -> None:
        """加一个**能被运行时认出来**的步骤（方块面板，点一下即加）。

        ⚠️ 不让用户直接敲名字：随手打的"新步骤"接不上任何阶段（
        :func:`stage_of_name` 认不出），加进去也**不参与运行**——用户会以为
        加了没生效。所以列出固定步骤让他点。

        ⚠️ 用户 2026-11-17 三条：下拉里的「提交检测结果」不需要（那是
        「检测文本框」的第二个动作 ``detect_submit``，不是独立步骤）、
        「其他（自定义名称）」不需要、下拉框改成**排列的方块**直接点选。
        条目 = 固定步骤表（:func:`palette_steps`）那一套——主链四步 +
        可选的「图片拼版」，别另写一份名单。
        """
        from desktop.components.bpmn_palette import (
            is_optional_step, palette_name, palette_steps,
        )
        from desktop.components.dialog_shell import shell_dialog

        chosen: list[str] = []
        holder: dict = {}       # 弹窗引用（按钮回调里要关它）

        content = QWidget()
        layout = QVBoxLayout(content)
        # ⚠️ own_chrome=True 的外壳把边距归零了，这里自己 pad 回来——
        #    不然提示字贴着左缘、按钮一直排到窗口边上（用户 2026-11-17：
        #    "添加步骤这个弹窗 ui 太丑"）。
        layout.setContentsMargins(
            T.SPACE_LG, T.SPACE_LG, T.SPACE_LG, T.SPACE_LG)
        layout.setSpacing(T.SPACE_MD)
        hint = CaptionLabel("点一个方块，加到画布（名称即为运行阶段）：")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(T.SPACE_MD)
        for index, token in enumerate(palette_steps()):
            name = palette_name(token, self.diagram(), self._name_source)
            if is_optional_step(token):
                name = f"{name}（可选）"
            button = PushButton(name)
            button.setMinimumHeight(44)
            button.setMinimumWidth(140)

            def _pick(_checked=False, _token=token):
                chosen.append(_token)
                dialog = holder.get("dlg")
                if dialog is not None:
                    dialog.accept()

            button.clicked.connect(_pick)
            grid.addWidget(button, index // 3, index % 3)
        layout.addWidget(grid_host)
        layout.addStretch()

        dialog = shell_dialog("添加步骤", content, self,
                              size=(520, 240), own_chrome=True)
        holder["dlg"] = dialog
        dialog.exec()
        if chosen:
            self.add_step(chosen[0])

    def _confirm_zh(self, title: str, text: str, *, yes_text: str = "删除",
                    no_text: str = "取消") -> bool:
        """中文按钮的删除确认框（``True`` = 点了"是"）。

        ⚠️ 不用 ``QMessageBox.question`` 静态方法：标准按钮文字由**系统语言**
        决定（英文环境下就是 "Yes"/"No"，2026-11-17 用户报「确认弹窗是英文」）。
        这里用实例并显式改按钮文字；离屏自测把本方法整体替掉即可，不弹真模态。
        """
        box = QMessageBox(
            QMessageBox.Icon.Question, title, text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            self,
        )
        box.button(QMessageBox.StandardButton.Yes).setText(yes_text)
        box.button(QMessageBox.StandardButton.No).setText(no_text)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def _input_text_zh(self, title: str, label: str, text: str = "") -> tuple[str, bool]:
        """中文按钮的单行输入框（``QInputDialog.getText`` 的按钮也是英文）。"""
        dlg = QInputDialog(self)
        dlg.setWindowTitle(title)
        dlg.setLabelText(label)
        dlg.setTextValue(text)
        for btn in dlg.findChildren(QPushButton):
            plain = btn.text().replace("&", "")
            if plain == "OK":
                btn.setText("确定")
            elif plain == "Cancel":
                btn.setText("取消")
        confirmed = dlg.exec() == QDialog.Accepted
        return dlg.textValue(), confirmed

    def ask_rename_selected(self) -> None:
        """给选中的（连线优先）改名。"""
        flow_id = self.selected_flow()
        if flow_id:
            flow = next((f for f in self.diagram().flows if f.id == flow_id), None)
            label, confirmed = self._input_text_zh(
                "连线文字", "这条线上写什么（如网关分支的「否」）：",
                text=flow.label if flow else "")
            if confirmed:
                self.rename_selected(label.strip())
            return
        node_id = self.selected()
        if not node_id:
            return
        item = self.diagram().node(node_id)
        name, confirmed = self._input_text_zh(
            "重命名节点",
            "节点名称（改成已知阶段名可切换步骤类型；其他名字只改显示，不影响运行）：",
            text=item.name if item else "")
        if confirmed and name.strip():
            self.rename_selected(name.strip())

    def ask_delete_selected(self) -> None:
        flow_id = self.selected_flow()
        if flow_id:
            flow = next((f for f in self.diagram().flows if f.id == flow_id), None)
            source = self.diagram().node(flow.source) if flow else None
            target = self.diagram().node(flow.target) if flow else None
            label = (f"{source.name if source else '?'} → "
                     f"{target.name if target else '?'}")
            if self._confirm_zh("删除连线", f"确定删除连线「{label}」？"):
                self.remove_flow(flow_id)
            return
        node_id = self.selected()
        if not node_id:
            return
        item = self.diagram().node(node_id)
        label = item.name if item else node_id
        # ⚠️ **成对删除**（用户2026-10-06）：「上传 PDF」与「提取图片」是一对，
        #   删掉任一个，另一个就**没有意义**（留着 startEvent 图上有个入口却
        #    不产出图片；留着 extract 则界面那个 PDF 图标会一直催你上传）。
        #    判据在 :func:`ports.paired_node_for_stage`，**不在这里写死**
        #    "extract↔startEvent"——那是流程模型的声明，不是编辑器的事。
        # ⚠️ **结束事件跟着删**（用户2026-10-07）：「生成PDF」附在「PDF排版」
        #   后面，删掉 PDF排版 它就一条入线不剩——图上写着"生成PDF"却不再
        #    产出 PDF，是句谎话。判据在 :func:`ports.orphaned_end_event_ids`。
        # ⚠️ **「是否拼版」网关跟着删**（用户2026-10-08）：网关依附「图片拼版」
        #   （"其实根本就没有判断这个组件"），拼版没了它就无所依附。
        #   判据在 :func:`ports.orphaned_gateway_ids`。
        from desktop.steps import ports

        partner_id = ports.paired_node_for_stage(self.diagram(), node_id)
        doomed = [node_id, *([partner_id] if partner_id else [])]
        orphan_ids = ports.orphaned_end_event_ids(self.diagram(), *doomed)
        gateway_ids = ports.orphaned_gateway_ids(self.diagram(), *doomed)
        partner = (self.diagram().node(partner_id) if partner_id else None)
        notes = []
        if partner is not None:
            notes.append(
                f"「{partner.name}」是它的**配套节点**（上传 PDF 与提取图片"
                f"必须成对存在）")
        for orphan_id in orphan_ids:
            orphan = self.diagram().node(orphan_id)
            notes.append(
                f"「{orphan.name if orphan else orphan_id}」是附在它后面的"
                "收尾事件，流程不再走到收尾")
        for gateway_id in gateway_ids:
            gateway = self.diagram().node(gateway_id)
            notes.append(
                f"「{gateway.name if gateway else gateway_id}」是依附它的"
                "「是否拼版」判断，拼版没了它也就没有意义")
        if notes:
            answer = self._confirm_zh(
                "删除节点",
                f"确定删除「{label}」？\n\n"
                f"{'；'.join(notes)}，会**一起删除**。")
        else:
            answer = self._confirm_zh(
                "删除节点",
                f"确定删除「{label}」？连到它的连线会一起删除。")
        if answer:
            self.remove_node(node_id)
            # ⚠️ **配对/收尾/网关节点跟着删**（正反两向都走这里，所以删哪个都
            #    成对消失）。用``remove_node`` 而不是直接改 diagram：它会连带
            #    清掉挂在这个节点上的连线、坐标、注释——漏一处就留下一堆悬空引用。
            for other in (partner_id, *orphan_ids, *gateway_ids):
                if other:
                    self.remove_node(other)


__all__ = ["_DialogMixin"]
