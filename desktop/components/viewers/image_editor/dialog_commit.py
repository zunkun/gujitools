# -*- coding: utf-8 -*-
"""``ImageEditorDialog`` Mixin：**工具提交**。

把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。（从 ``image_editor/dialog.py`` 拆出，2026-10-07；方法体逐字未改）。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor
from utils.perspective import rectify_qimage
from .bake import _bake_cage_work, _bake_puppet_work, run_with_progress, wait_cursor
from .geometry import bake_transform, clamp_rect, draw_text
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from ._host import DialogHost
else:
    DialogHost = object


class CommitMixin(DialogHost):
    """把画布上的临时状态烘焙进当前图像（含后台烘焙与失败提示）。"""

    # ------------------------------------------------------------ 应用
    def _selection(self) -> QRectF | None:
        rect = self.canvas.selection()
        if rect is None:
            return None
        return clamp_rect(rect, self.canvas.image_rect())


    def _apply_crop(self) -> None:
        rect = self._selection()
        if rect is None or self._image is None:
            return
        self._push_undo()
        self._image = self._image.copy(rect.toRect())
        self.canvas.set_image(self._image)


    # ------------------------------------------------------------ 变换
    def _commit_transform(self) -> None:
        """把未应用的变换烘焙进图片（一个撤销点）；没有变换就只清预览。

        「应用变换」按钮、切走工具、「完成」都走这里——预览即所见，
        烘焙结果与浮层显示一致（原区域填白 + 变换后的选区内容）。
        """
        if not hasattr(self, "canvas"):
            return
        pending = self.canvas.transform_pending()
        if pending is None:
            self.canvas.reset_transform()
            return
        rect, xf, region = pending
        self._push_undo()
        # grow：旋转/倾斜把选区送出原边界时不截，画布放大到「原图 ∪ 变换后」
        image, _origin = bake_transform(self._image, rect, xf, region, grow=True)
        self._image = image
        self.canvas.set_image(self._image)


    # ------------------------------------------------------------ 变形
    def _commit_deform(self) -> None:
        """把未应用的**变形**烘焙进图片（一个撤销点），图钉留在原地。

        「应用变形」按钮、切走工具、「完成」都走这里。形变是 ARAP 网格逐像素
        重映射（PS 操控变形口径，见 ``utils.puppet_warp``），按**全分辨率**算
        ——大图上要秒级到分钟级，所以放到**后台线程**跑并显示进度对话框
        （用户 2026-10-01 报"卡死/崩溃"：同步跑会把主线程钉死、界面假死）；
        并且**防重入**——本函数在"切走到非变形工具"时也会被调，重入会把已经
        形变过的图再形变一次，白丢一个撤销点、结果也不对。
        """
        if not hasattr(self, "canvas") or self._deform_busy:
            return
        pending = self.canvas.pins_pending()
        if pending is None or self._image is None or self._image.isNull():
            # 没有未应用的形变：预览浮层本来就不存在（它只伴随形变出现），
            # 什么都不用清——这里**刻意不调** reset_pins：本函数在"切走到
            # 非变形工具"时也会被调，那时清空图钉纯属白干
            return
        vertices, moved, triangles = pending
        self._push_undo()
        # ⚠️ set_image 换图会把 _pins 清空，所以**先**快照图钉顶点下标，
        #    烘焙完再原样钉回新网格（见 adopt_pins 的说明）
        pin_vertices = list(self.canvas.pins())
        self._deform_busy = True
        try:
            baked = run_with_progress(
                self, "应用变形", "正在把操控变形烘焙进图片……",
                _bake_puppet_work,
                {"image": self._image, "vertices": vertices,
                 "moved": moved, "triangles": triangles})
        except Exception as exc:      # noqa: BLE001（要提示用户，不是吞掉）
            # 烘焙失败（内存不足 / 方程组退化）：退回撤销点并**明确报错**。
            # ⚠️ 绝不能静默返回——用户点了 20 秒却什么都没发生、连按钮都
            #   没反应，只会以为程序卡了（这正是用户报过的现象）。
            self._undo.pop()
            self._sync_undo_buttons()
            self._report_bake_error(exc)
            return
        finally:
            self._deform_busy = False
        if baked is None:
            # 用户取消：不落地，退回撤销点（等于什么都没发生）
            self._undo.pop()
            self._sync_undo_buttons()
            return
        # grow：返回 (QImage, (ox, oy))；换图后网格按新图重建，坐标天然对齐
        image, _origin = baked
        self._image = image
        self.canvas.set_image(self._image)
        # 形变已烧进像素，图钉**留在原地**：古籍褶皱往往要来回试几次，
        # 每次应用后都清空的话用户得重新钉一遍
        self.canvas.adopt_pins(pin_vertices)


    def _commit_cage(self) -> None:
        """把未应用的**变换笼**形变烘焙进图片（一个撤销点），把手留在原地。

        「应用形态」按钮、切走工具、「完成」都走这里。笼形变是 RBF 位移场
        逐像素重映射（GIMP 变换笼口径的**局部**实现，见 ``utils.cage_warp``），
        按**全分辨率**算——虽然影响是局部的（只重采样影响框内），大图上仍是
        秒级，所以挂等待光标；并且**防重入**——等待光标前那一下
        ``processEvents`` 会派发排队事件，不防的话一次点击可能触发两遍。
        """
        if not hasattr(self, "canvas") or self._cage_busy:
            return
        pending = self.canvas.cage_pending()
        if pending is None or self._image is None or self._image.isNull():
            # 没有未应用的形变：预览浮层本来就不存在。**刻意不调** reset_cage：
            # 本函数在"切走到非笼工具"时也会被调，那时清空把手纯属白干。
            return
        src, dst = pending
        self._push_undo()
        self._cage_busy = True
        try:
            baked = run_with_progress(
                self, "应用形态", "正在把变换笼形变烘焙进图片……",
                _bake_cage_work,
                {"image": self._image,
                 "src": [(p.x(), p.y()) for p in src],
                 "dst": [(p.x(), p.y()) for p in dst]})
        except Exception as exc:      # noqa: BLE001（要提示用户，不是吞掉）
            # 同 _commit_deform：失败必须**明确报错**，不能静默当成取消
            self._undo.pop()
            self._sync_undo_buttons()
            self._report_bake_error(exc)
            return
        finally:
            self._cage_busy = False
        if baked is None:
            # 用户取消（或退化）：不落地，退回撤销点（等于什么都没发生）
            self._undo.pop()
            self._sync_undo_buttons()
            return
        # grow 模式下结果是 (QImage, (ox, oy))：(ox, oy) = 新画布左上角在原
        # 坐标系里的位置（可为负）。换图后笼按**新图**重建，坐标天然对齐，
        # 不需要手动平移——但要把"是否扩大过"记下来（见下）。
        image, origin = baked
        self._image = image
        self.canvas.set_image(self._image)
        # 形变已烧进像素：笼回到贴图边原位（重置即身份），可以接着拖第二次。
        # ⚠️ set_image 换图会把笼清空，所以这里必须显式重建，否则切回来时
        #    画布上无笼可拖。
        if self.canvas._tool == "cage":
            self.canvas.reset_cage()


    def _commit_rectify(self) -> None:
        """把四角框住的区域透视摆正，替换整图（一个撤销点）。

        ⚠️ 与「变形」不同：校正**改变图片尺寸**（摆正后是目标矩形），
        所以这里是"换一张图"而不是"在原图上重采样"。换图后四角回到新图的
        四角（原位），可以接着校第二次。「应用校正」按钮、切走工具都走这里。
        """
        if not hasattr(self, "canvas") or self._rectify_busy:
            return
        pending = self.canvas.quad_pending()
        if pending is None or self._image is None or self._image.isNull():
            return
        quad, mode = pending
        self._push_undo()
        self._rectify_busy = True
        try:
            with wait_cursor():
                done = rectify_qimage(self._image, quad, mode=mode)
        except ValueError:
            # ⚠️ 四角退化（完全共线 / 两点重合 / 极细长）时 ``rectify_qimage``
            #   **抛 ValueError 而不是返回 null 图**（实测三种退化输入都抛）。
            #   这里若不接住：异常一路逸出 Qt 槽函数，且更隐蔽的是——
            #   **上面压入的撤销点永远不会被弹出**，撤销历史从此错位
            #   （用户按一次 Ctrl+Z 会"什么都没发生"）。必须成对处理。
            self._undo.pop()
            return
        finally:
            self._rectify_busy = False
        if done.isNull():
            # 退化（四角近似共线）：不落地，退回撤销点（等于什么都没发生）
            self._undo.pop()
            return
        self._image = done
        self.canvas.set_image(self._image)   # 换图 → 四角按新图重建


    # ------------------------------------------------------------ 文字
    def _spawn_text_block(self, pos: QPointF) -> None:
        """文字工具点击落点 → 画布上生成文字块就地编辑（光标可见）。"""
        if self._image is None or self._image.isNull():
            return
        self.canvas.add_text_block(
            pos, self._text_size, QColor(self._text_color),
            self._text_family,
        )


    def _commit_text_blocks(self) -> None:
        """把画布上非空文字块写进图片（一个批次一个撤销点），然后清块。"""
        if not hasattr(self, "canvas"):
            return
        blocks = self.canvas.text_blocks()
        payload = [
            (b.pos(), b.toPlainText(), b.font().pixelSize(),
             QColor(b.defaultTextColor()), b.font().family())
            for b in blocks if b.toPlainText().strip()
        ]
        self.canvas.clear_text_blocks()
        if not payload or self._image is None or self._image.isNull():
            return
        self._push_undo()
        for pos, text, px, color, family in payload:
            self._image = draw_text(
                self._image, pos, text, px, color, family)
        self.canvas.replace_image(self._image)


    # ------------------------------------------------------------ 撤销
    def _report_bake_error(self, exc: Exception) -> None:
        """把烘焙失败转成**用户能看懂**的提示（InfoBar），并把技术细节打到日志。

        为什么不静默：烘焙失败时若什么都不说，界面看起来就是"点了没反应"
        ——用户已经报过好几次"程序卡死/崩溃"，而这类静默失败会让他们更加
        确信程序崩了。宁可多弹一条提示。

        常见原因换成人话（``MemoryError`` 是大图下最常见的，见
        ``_bake_puppet_work`` 的内存说明）：

        - ``MemoryError``：图片太大，内存不够——建议先裁剪或缩小再处理；
        - ``LinAlgError`` / 奇异：把图钉或把手分开一点再试；
        - ``ValueError``：当前形状退化（如四角共线），换个操作。
        """
        if isinstance(exc, MemoryError):
            title = "图片太大，处理失败"
            content = ("这张图按全分辨率处理需要的内存超出可用量，"
                       "操作没有生效。可以先裁剪到需要处理的区域，或缩小后重试。")
        elif type(exc).__name__ == "LinAlgError":
            title = "形状退化，操作没有生效"
            content = "当前的控制点重合或共线，解不出结果。把它们分开一点再试。"
        else:
            title = "操作失败"
            content = f"没有生效：{type(exc).__name__}。详细信息见日志。"
        try:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        except Exception:      # noqa: BLE001（日志失败绝不能连带崩掉提示）
            pass
        try:
            from qfluentwidgets import InfoBar, InfoBarPosition
            InfoBar.error(title=title, content=content, parent=self,
                          position=InfoBarPosition.BOTTOM_RIGHT, duration=5000)
        except Exception:      # noqa: BLE001（无宿主/组件缺失时降级为控制台）
            print(f"[图片编辑] {title}：{exc}")
