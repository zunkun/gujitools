# -*- coding: utf-8 -*-
# pylint: disable=no-name-in-module,assignment-from-no-return
"""弹窗收尾：覆盖确认 / 完成 / 释放缓冲。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QSizeF, Qt, Signal
from PySide6.QtGui import QImage, QKeySequence, QShortcut, QTransform
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QMessageBox, QVBoxLayout, QWidget,
)

from desktop.ui import theme as T
from desktop.ui.window_size import apply_window_size
from ..canvas import EditorCanvas
from ..consts import (
    ERASER_DEFAULT, HISTORY_ORIGIN_LABEL, TEXT_COLOR_DEFAULT, TEXT_DEFAULT,
)
from ..geometry import _trim_transparent_edges, _transparent_content_bounds

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._host import DialogHost
else:
    DialogHost = object



class FinishMixin(DialogHost):
    """弹窗收尾：覆盖确认 / 完成 / 释放缓冲。"""



    def _confirm_overwrite(self) -> bool:
        """「完成」前问一句"要不要覆盖原图"；用户取消返回 False。

        用户 2026-10-04 定的：图片编辑最后应用时**必须提醒会覆盖原图**。
        只在 ``save_back``（本页有真实文件可回写）时问——虚拟预览
        （区域合成/打印重排/PDF 页）压根不写盘，问了是假警报。

        ⚠️ 这不是"单步变更确认"：单步确认按钮已经全部删掉、编辑实时生效，
        唯一保留的确认是"覆盖磁盘原图"这件不可逆的事。

        ⚠️ 三个"不打扰"的短路，都走 ``return True``（当作用户同意）：

        1. **无图**：没有可覆盖的东西；
        2. **目标尚不存在**（``target_exists=False``，宿主回填）：整页组合
           第一次编辑写的是缓存区里新建的文件，没有旧内容可丢；
        3. **没改动**：``self._image == self._original``（QImage 逐像素相等）
           且没有待定裁剪。空跑一趟却弹"将覆盖原图"，用户只会觉得这框很蠢——
           真要改的话改动本身就在图上，一眼看得见。

        ⚠️ 延迟导入 ``MessageBox``（与 ``modules/detect/page.py`` 同款）：
        自测要能把它换成记录器，否则离屏跑会弹真模态把整个用例挂住。
        """
        if self._multi_layers:
            if any(self._layer_has_changes(layer) for layer in self._multi_layers):
                return self._ask_overwrite()
            return True
        if not self._save_back:
            return True
        if not getattr(self, "target_exists", True):
            return True
        if self._image is None or self._image.isNull():
            return True
        # ⚠️ **待定裁剪也算"改过了"**：它还没落到像素上（``_image`` 仍是原图），
        #    但「完成」马上就要把它裁掉并覆盖磁盘——只比 ``_image`` 的话，
        #    "只裁不改"的编辑会一声不吭地把原图裁小写回去。
        if getattr(self, "_pending_crop", None) is not None:
            return self._ask_overwrite()
        # ⚠️ **挂起的变换也算"改过了"**：统一变换松手只挂起预览（像素没动、
        #    ``_image`` 仍是原图，见 dialog_commit），但「完成」马上就要把
        #    变换烘焙进去并覆盖磁盘——只比 ``_image`` 的话，"只转了个角度"
        #    的编辑会一声不吭地覆盖原图（连确认框都不弹，2026-10-10）。
        if self.canvas.has_pending_transform():
            return self._ask_overwrite()
        try:
            unchanged = self._image == self._original
        except Exception:      # noqa: BLE001（比较失败就当"改过了"，宁可多问）
            unchanged = False
        if unchanged:
            return True
        return self._ask_overwrite()

    def _layer_has_changes(self, layer: dict) -> bool:
        if layer is self._multi_layers[self._active_layer]:
            if self.canvas.has_pending_transform() \
                    or getattr(self, "_pending_crop", None) is not None \
                    or any(block.toPlainText().strip()
                           for block in self.canvas.text_blocks()):
                return True
            state = self._capture_layer_state()
        else:
            # ⚠️ 非活动层的**挂起未烘焙变换**也算改过（切层不烘焙，
            #    2026-10-13）：判据 = 画布快照里"碰过变换且有预览数据"
            #    （``_xf_touched`` + rect/region）＝``transform_pending``
            #    的快照版——「完成」时这层会被补烘焙并写盘。
            canvas_state = layer.get("canvas_state") or {}
            if (canvas_state.get("_xf_touched")
                    and canvas_state.get("_xf_rect") is not None
                    and canvas_state.get("_xf_region") is not None):
                return True
            state = layer["state"]
        image = state.get("_image")
        original = state.get("_original")
        return image is not None and original is not None and image != original

    def _bake_inactive_pending(self) -> None:
        """「完成」前把**非活动层**挂着的未烘焙变换逐层落进像素。

        切层从不烘焙（2026-10-13 口径：切换要快、互不影响），挂起预览随层
        快照保存；但「完成」要写底片——不补烘的话那笔变换就**无声丢了**。
        逐层临时激活 → 恢复画布快照 → ``_commit_transform(force=True)``
        （大图走进度框，可取消）→ 快照写回层。烘焙失败/取消的层保持原样
        （像素与快照都不动，下次进来继续编辑）。
        """
        active_index = self._active_layer
        active_state = self._capture_layer_state()
        active_canvas = self.canvas.capture_transform_state()
        for index, layer in enumerate(self._multi_layers):
            if index == active_index:
                continue
            canvas_state = layer.get("canvas_state") or {}
            if not (canvas_state.get("_xf_touched")
                    and canvas_state.get("_xf_rect") is not None
                    and canvas_state.get("_xf_region") is not None):
                continue
            before_state = layer.get("state")
            self._load_layer(index)
            self.canvas.set_image(self._image, refit=False)
            self.canvas.restore_transform_state(canvas_state)
            if self._commit_transform(force=True, update_canvas=False):
                layer["state"] = self._capture_layer_state()
                layer["canvas_state"] = None
                layer["ghost"] = None
                layer["ghost_origin"] = None
            else:
                layer["state"] = before_state   # 取消/失败：原样保留
        layer = self._multi_layers[active_index]
        layer["state"] = active_state
        layer["canvas_state"] = active_canvas
        self._load_layer(active_index)
        self.canvas.set_image(self._image, refit=False)
        self.canvas.restore_transform_state(active_canvas)
        self._refresh_multi_canvas()

    def _save_multiple_images(self) -> bool:
        from desktop.components.viewers.image_zoom_dialog.io import (
            overwrite_image_file,
        )
        from ..content_quad import sync_content_quad

        self._multi_layers[self._active_layer]["state"] = self._capture_layer_state()
        active_index = self._active_layer
        layout_updates = []
        for index, layer in enumerate(self._multi_layers):
            state = layer["state"]
            image = state.get("_image")
            original = state.get("_original")
            if image is None or original is None or image == original:
                continue
            if not overwrite_image_file(image, Path(layer["file"])):
                if layout_updates:
                    self.multi_layout_saved.emit(layout_updates)
                self._load_layer(active_index)
                # ⚠️ 不用 QMessageBox.warning 静态方法：单按钮文字由系统语言
                #    决定（英文环境显示 "OK"，2026-11-17 用户报「弹窗是英文」）。
                box = QMessageBox(
                    QMessageBox.Icon.Warning, "保存失败",
                    f"无法保存「{layer['label']}」：{Path(layer['file']).name}",
                    QMessageBox.StandardButton.Ok, self,
                )
                box.button(QMessageBox.StandardButton.Ok).setText("知道了")
                box.exec()
                return False
            self._load_layer(index)
            sync_content_quad(layer["file"], self)
            self.multi_image_saved.emit(layer["file"], QImage(image))
            x, y, _width, _height = layer["rect"].getRect()
            scale_x, scale_y = self._layer_scale(layer)
            origin_x, origin_y = self._layer_origin(layer)
            # ⚠️⚠️ 回报给拼版页的 rect 必须是**可见内容**的框，不是整张像素图
            #    （2026-10-14 用户报障「弹窗里把图下移 200px，应用后拼版页左图
            #    变大了、左右不等高」）。裁剪"移动"把位移编码成**透明边距**，
            #    像素图因此变大（实测 1000 → 1200 高），而内容其实没变——直接
            #    回报 ``image.height()`` 就等于**把留白算进版面**，虚线框比图
            #    大一圈、底部多出一截。
            #    这里只报**内容框**，拼版侧据此摆框。
            # ⚠️⚠️ **位移 = 内容框在新画布里的偏移 ``content[0:2]`` ＋ 画布原点
            #    平移 ``layer["origin"]`` 之和**（2026-10-15 用户报障「弹窗里移动
            #    图片应用后，拼版页位置对不上」）。两项各管一类操作，缺一不可：
            #
            #    - ``content[0:2]``（内容框在新画布里的偏移）管**裁剪移动**——
            #      位移被烤进透明留白，``origin`` 恰好净零（``box.x + shift -
            #      pad``＝0），只有这一项能反映出"用户把图挪了多远"；
            #    - ``origin``（画布 (0,0) 相对**入口内容原点**的位移）管**纯裁剪 /
            #      变换**——新画布从裁掉的 ``box`` 起，剩下的内容在页面上整体
            #      左移/右移了 ``box``，内容框自身偏移为 0，只有这一项追踪得到。
            #
            #    只用 ``origin`` ⇒ 裁剪移动时位移整个丢失（图"弹回原位"，同日
            #    另一条报障）；只用 ``content[0:2]`` ⇒ 纯裁剪/变换后内容位置
            #    不回写（弹窗画布把那张图挪了、页面却没动，正是"位置对不上"）。
            #    页面 rect 锚在**入口内容原点**上（见 ``configure_multiple_images``
            #    的 origin 说明），两项之和才是内容相对该锚点的完整位移。
            content = _transparent_content_bounds(image)
            if content is None:
                offset_x, offset_y = 0.0, 0.0
                content_w, content_h = image.width(), image.height()
            else:
                offset_x, offset_y = float(content[0]), float(content[1])
                content_w, content_h = content[2], content[3]
            layout_updates.append({
                "index": layer["page_item_index"],
                "file": layer["file"],
                "rect": [
                    x + (offset_x + origin_x) * scale_x,
                    y + (offset_y + origin_y) * scale_y,
                    content_w * scale_x,
                    content_h * scale_y,
                ],
            })
        self._load_layer(active_index)
        self._refresh_multi_canvas()
        if layout_updates:
            self.multi_layout_saved.emit(layout_updates)
        return True


    def _ask_overwrite(self) -> bool:
        """弹一次"覆盖原图"确认；问不出来（无事件循环/测试替身）时按同意处理。

        延迟导入 ``MessageBox``（与 ``modules/detect/page.py`` 同款）：自测要能
        把它换成记录器，否则离屏跑会弹真模态把整个用例挂住。
        """
        try:
            from qfluentwidgets import MessageBox  # noqa: PLC0415

            name = str(getattr(self, "target_name", "") or "").strip()
            detail = f"「{name}」" if name else "原图片"
            # ⚠️ 正文**不用 markdown 粗体**（``**…**``）：MessageBox 的
            #    contentLabel 是普通 QLabel，``**`` 会原样显示成两个星号。
            box = MessageBox(
                "确定要覆盖原图吗？",
                f"应用这次编辑会覆盖掉{detail}的现有内容，"
                "磁盘上的原图将不再保留。\n\n"
                "若只是想先看看效果，请直接关闭本弹窗（本次编辑全部作废）。",
                self,
            )
            box.yesButton.setText("覆盖并应用")
            box.cancelButton.setText("返回继续编辑")
            return bool(box.exec())
        except Exception:      # noqa: BLE001（无 Qt 事件循环/替身无 exec）
            return True


    def _finish(self) -> None:
        """「完成」：待定裁剪/变换/未提交的文字一并落定，再应用全部编辑。

        ⚠️ 顺序有讲究：先落**裁剪**（它改画布尺寸）、再落变换（变换作用在
        裁完的图上）、最后写入文字块。变换**必须 ``force=True``**：松手只
        挂起预览（像素没动），不带 force 会被 :meth:`_commit_transform` 的
        "挂起跳过"分支原样退回 ⇒ 变换永远落不到实体图上——用户 2026-10-10
        报的正是这个（「统一变换不能落地到实体图片」，其它工具没挂起机制
        所以都正常）。这里不是"兜底"，是挂起机制下**唯一的烘焙时机**之一
        （另一个是离开变换工具，走 ``_set_tool`` 的 force=True）。

        ⚠️⚠️ **save_back 且有挂起变换时走后台应用**（``_begin_background_apply``
        返回 True 就直接 return，``accept()`` 在启动器里已经调了）：弹窗立刻
        关闭，烘焙 + 写底片在工作线程里跑，完成后经 ``apply_completed`` 通
        知宿主刷新。用户 2026-10-10 口径：「应用保存时页面上的数据可以不
        保存，只需要将数据存到相应的底片上」——此前整幅重采样（12 MP 约
        11 秒）+ 写盘全程把界面钉死，正是「应用卡顿」的来源。

        ⚠️ 烘焙被用户取消（进度框点取消）/ 失败时 ``_commit_transform``
        返回 ``False``：**中止收尾**、留在编辑器里继续改——绝不能往下
        ``accept()`` 把"没变换的图"当结果交出去（save_back 时那会无声
        覆盖磁盘原图）。（后台应用没有"留在编辑器"一说：取消/失败经
        ``apply_failed`` 告知宿主，底片未动。）

        ⚠️ ``_finishing`` 必须在**确认框之前**就置位：``MessageBox.exec()``
        自带事件循环，双击「完成」会在框弹出后再进一次这里⇒ 叠出第二个
        确认框。所以顺序是"先上锁 → 再问 → 不同意就退出并解锁"，
        不是"问完再上锁"。
        """
        if getattr(self, "_finishing", False):
            return
        self._finishing = True
        try:
            if not self._confirm_overwrite():
                return
            if self._multi_layers:
                # 非活动层的挂起变换逐层补烘焙（切层不烘焙，见
                # _bake_inactive_pending）——必须在写盘之前
                self._bake_inactive_pending()
            self._commit_crop()
            if self._begin_background_apply():
                return
            if not self._commit_transform(force=True, update_canvas=False):
                return
            self._commit_text_blocks()
            if self._multi_layers and not self._save_multiple_images():
                return
            self.accept()
        finally:
            self._finishing = False


    # ------------------------------------------------------------ 对外
    def release_buffers(self, keep_result: bool = False) -> None:
        """释放**整图级**缓冲（原图/当前图/撤销与重做快照/upright 缓存）。

        为什么必须有（2026-10-13「程序内存越来越大」）：编辑器的缓冲全是
        原分辨率整图——``_original`` + ``_image`` 两份，外加撤销栈最多
        ``UNDO_LIMIT`` 份整图快照（大图下可达 GB 级）。编辑器是 QDialog、
        由宿主长期持有，只 close 不销毁的话这些像素**一直驻留**，跨任务
        都不释放。宿主在结果消费完（或弹窗整体关闭）后调用本方法即可放掉。

        ``keep_result=True``：保留 ``_image``（后台应用完成链用——宿主约定
        「关窗后仍可取 ``result_image()``」，见 ``image_editor_saveback``
        自测）。其余整图缓冲照放：撤销栈 + 原图 + upright 才是大头。

        ⚠️ ``keep_result=False``（默认）时结果即作废：只能在"不再需要
        ``result_image()``"之后调用。
        """
        self._original = None
        if not keep_result:
            self._image = None
        self._undo = []
        self._redo = []
        self._labels = []
        # ⚠️ 双图编辑（拼版「编辑整图」）：每层的整图缓冲（``_image``/
        #    ``_original``/撤销栈/upright）也驻留在层字典里——两个图层就是
        #    双倍内存，宿主消费完结果放缓冲时必须一起放。``canvas_state``
        #    里的底图/浮层像素快照同理（换层捕获的整图拷贝）。
        for layer in getattr(self, "_multi_layers", None) or []:
            state = layer.get("state")
            if isinstance(state, dict):
                state["_image"] = None
                state["_original"] = None
                state["_undo"] = []
                state["_redo"] = []
                state["_undo_origins"] = []
                state["_redo_origins"] = []
                state["_content_upright"] = None
                state["_content_restore_params"] = None
            layer["canvas_state"] = None
            layer["ghost"] = None
            layer["ghost_origin"] = None
        # 内容节点 sidecar 的 upright 是另一份全分辨率反变换缓存，一并放掉
        self._content_upright = None
        self._content_restore_params = None

    def closeEvent(self, event) -> None:  # noqa: N802（Qt 回调）
        """关闭时清理画布引用。

        撤销栈是**整图快照**，大图下最多 12 份（见 ``UNDO_LIMIT``），
        关窗后必须释放，不能靠 Python GC（Qt 侧 C++ 对象不由引用计数托管）。

        ⚠️ 只有**未采纳**的关闭（X / Esc / reject）能在这里直接放缓冲：
        accept() 的关闭不触发 closeEvent，而调用方在 ``exec()`` 返回后还要
        读 ``result_image()``——采纳路径的释放由调用方消费完结果后显式调
        :meth:`release_buffers`（或后台应用链在 ``_on_async_apply_done``
        里兜底）。
        """
        self._finishing = True
        try:
            if self.result() != QDialog.DialogCode.Accepted:
                self.release_buffers()
            # EditorCanvas 无 clear（此调用在运行期恒抛 AttributeError，被下面
            # 吞掉，等价于不做事）；保留原样以免改变关闭时的清理行为。
            self.canvas.clear()  # type: ignore[attr-defined]
        except Exception:      # noqa: BLE001（销毁期清理不该再抛）
            pass
        super().closeEvent(event)


    def result_image(self) -> QImage | None:
        """编辑结果（无图时 None；是否采纳由调用方的 exec 结果决定）。"""
        if self._image is None or self._image.isNull():
            return None
        return self._image
