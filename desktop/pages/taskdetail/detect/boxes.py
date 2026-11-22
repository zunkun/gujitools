# -*- coding: utf-8 -*-
"""检测框的人工干预、落库与上屏（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtCore import QSize
from PySide6.QtGui import QImageReader

from desktop.components.box_kinds import BoxKindEditor, manual_hint_text
from utils.book_layout import full_to_half_slots, is_single_wide_half
from utils.box_geometry import half_slots, is_full_content, present_boxes

from desktop.pages.taskdetail.detect.constants import ORIGIN_SUFFIX

if TYPE_CHECKING:
    from desktop.pages.taskdetail.detect._host import DetectHost
else:
    DetectHost = object


class DetectBoxesMixin(DetectHost):
    """检测框：类型协议、槽位读写、上屏与信息条。"""
    @staticmethod
    def _valid_boxes(boxes) -> list:
        """过滤存储中的 null 框（左右身份占位）。

        等价于 :func:`utils.box_geometry.present_boxes`——独立「检测文本框」
        模块页直接用那个纯函数，这里保留这个名字是因为本文件里到处都是它。
        """
        return present_boxes(boxes)

    # ------------------------------------------------------- 框类型（人工干预）
    #
    # 三条约定的落点（用户 2026-09-29 定）：类型在槽位里、半幅左右由位置决定、
    # 整幅显式且互斥。**交互顺序与文案的唯一实现在
    # `desktop/components/box_kinds.py::BoxKindEditor`**（与独立检测页共用）；
    # 本 Mixin 只提供宿主协议（预览控件 / 提示出口 / 落库 / 确认框）。

    def _box_editor(self) -> BoxKindEditor:
        """共享交互器（无状态，按需构造；宿主协议见下面 box_ 前缀一组）。"""
        return BoxKindEditor(self)

    # ---- BoxKindHost 协议（box_ 前缀，避免与页面其他成员撞名）----
    def box_viewer(self):
        return self.detect_viewer

    def box_toast(self, kind: str, title: str, content: str) -> None:
        self._toast(kind, title, content)

    def box_raw_slots(self, path_text: str) -> list:
        return self._raw_boxes_for(path_text)

    def box_page_is_full(self, _path_text: str) -> bool:
        # 查看器的整幅标志即当前页形态（编辑动作都发生在当前显示页上）
        return bool(self.detect_viewer.box_full_mode())

    def box_image_size(self, path_text: str):
        return self._image_size_for(path_text)

    def box_commit(self, path_text: str, slots: list, select_box=None,
                   side="keep") -> None:
        """落库 + 重画；``side`` 按需写入/清除这页的人工左右指定。

        ``side`` 语义（见 ``components.box_kinds.SIDE_KEEP``）：``"left"`` /
        ``"right"`` 写入、``None`` 清除、``"keep"`` 不动。

        ⚠️ **先写 side、再上屏**：``_store_slots`` → ``_apply_boxes`` 会读这一页
        的指定值来决定标签/面板高亮（``box_kinds``）。反过来（先上屏后写）第一次
        点击上屏用的还是**旧 side**，界面看着没切换，必须再点一次才生效——用户
        2026-10-17 报的「第一下只是把按钮点亮、等一小会点第二下才切」就是这个。
        """
        self._write_side_override(path_text, side)
        self._store_slots(path_text, slots, "manual", select_box=select_box)

    def box_page_half_candidate(self, path_text: str) -> bool:
        """这页是否**够「半幅」**（只有一个横跨整页的框）。

        判据本体在 ``utils.book_layout.is_single_wide_half``；这里只取数。
        ⚠️ 页级判据（用户 2026-10-23，任务 0004）：不要求整本书是单栏书。
        """
        raw = self._raw_boxes_for(path_text)
        width = self._page_width_of(Path(path_text))
        return is_single_wide_half(raw, width)

    def _write_side_override(self, path_text: str, side) -> None:
        """写/清人工左右指定（``"keep"`` = 不动）。"""
        if side == "keep" or not self.task_id:
            return
        writer = getattr(self.store, "set_box_side_override", None)
        if not callable(writer):
            return
        writer(
            self.task_id, Path(path_text).stem, side,
            **self._node_scope(self.node_of_stage("detect")),
        )

    def box_confirm(self, title: str, body: str, yes_text: str, cancel_text: str) -> bool:
        # ⚠️ 延迟导入必须留在方法体内：自测靠替换 qfluentwidgets.Dialog 记录确认
        from qfluentwidgets import Dialog  # noqa: PLC0415

        dialog = Dialog(title, body, self.window())
        dialog.yesButton.setText(yes_text)
        dialog.cancelButton.setText(cancel_text)
        return bool(dialog.exec())

    def box_resync_kind(self, index: int) -> None:
        """按现值回填面板的「选中框类型」高亮（类型操作结束后必调）。

        ⚠️ 分段控件在按下那一刻就把滑块移到了被点的段，而有些点击本来就不会
        改数据（普通半幅页点另一侧、整幅声明被取消）——不回填就会停在"看起来
        切了、其实没切"的位置（用户 2026-10-17 报「切换有问题」）。
        """
        self._on_box_selection_changed(index)

    def box_current_path_text(self) -> str:
        path = self.detect_viewer.current_path()
        return str(path) if path else ""

    # ---- 旧入口：保留名字（自测按这些签名钉行为），实现委托共享交互器 ----
    def _box_kinds(self) -> list:
        """预览里每个框当前的类型（"left"/"right"/"full"）。"""
        return self.detect_viewer.box_kinds()

    def _on_box_selection_changed(self, index: int) -> None:
        """预览里选中态变化 → 回填面板的「选中框类型」与删除按钮。"""
        panel = self.panel_host_of_step("detect")
        setter = getattr(panel, "set_box_selection", None)
        if not callable(setter):
            return
        kinds = self._box_kinds()
        kind = kinds[index] if 0 <= index < len(kinds) else ""
        setter(index, kind)

    def _on_box_edit_rejected(self, message: str) -> None:
        """框数已达上限（整幅 1 / 半幅 2）→ 弹出可操作的提示。"""
        self._toast("warning", "框数已达上限", message)

    def _on_box_too_small(self, message: str) -> None:
        """手绘的框太小（宽/高低于 ``box_geometry.min_box_sides`` 合格线）
        → 不入库并即时提示。

        用户 2026-11-16：「太小的话不生效、不显示，可以即时消息提示画框太小不生效」。
        """
        self._toast("warning", "画框太小", message)

    def _set_selected_box_kind(self, kind: str) -> None:
        """面板里点了「左框 / 右框 / 整幅 / 半幅」→ 切换选中框的类型。"""
        path = self.detect_viewer.current_path()
        if path is None or not self.task_id:
            return
        self._box_editor().set_kind(
            str(path), self.detect_viewer.selected_index(), kind
        )

    def _select_box_of_kind(self, kind: str) -> None:
        """没有选中框时，点类型＝选中该类框；该类型不存在则提示。"""
        self._box_editor().select_box_of_kind(kind)

    def _make_box_full(self, path_text: str, index: int) -> None:
        """把第 index 个框设为「整幅」（整幅与半幅互斥、一页只能一个框）。"""
        self._box_editor().make_full(path_text, index)

    def _make_box_half(self, path_text: str, index: int, kind: str) -> None:
        """把第 index 个框改成半幅（左/右）。"""
        self._box_editor().make_half(path_text, index, kind)

    def _delete_selected_box(self) -> None:
        """删除当前选中的框（与 Delete 键同一条路径）。"""
        self._box_editor().delete_selected()

    def _side_override_of(self, path_text: str, raw=None) -> str | None:
        """某页的**用户指定左右**（``"left"``/``"right"``/None）。

        只在「半幅」页上有意义：那种框横跨整页、中心压在中线上，按位置判左右
        没有意义，由用户点左/右指定（存 boxes.json 的 ``side``）。

        ⚠️ **只有「半幅单框」的页才可能带指定**：双框页/整幅页直接返回 None，
        连 boxes.json 都不读——否则每次切换类型都要整份解析一次文件（2000 页
        约 4ms，切换是高频动作）。

        ⚠️ 走 ``getattr`` 兜底：替身 store 可能没有 ``box_side_at``，取不到就
        当"没指定"（退回自动判定的半幅），不该让上屏中断。
        """
        slots = list(raw if raw is not None else self._raw_boxes_for(path_text))
        present = [b for b in slots if b]
        if len(slots) != 2 or len(present) != 1:
            return None
        getter = getattr(self.store, "box_side_at", None)
        if not callable(getter) or not self.task_id:
            return None
        try:
            return cast(Callable[[Any, str], str | None], getter)(
                self._boxes_write_path(), Path(path_text).stem
            )
        except Exception:  # noqa: BLE001 - 取不到就按"没指定"
            return None
    def _raw_boxes_for(self, path_text: str) -> list:
        """某页**槽位**表示（保留 null，形态信息就在槽数里）。"""
        raw = self.detect_cache.get(str(path_text))
        if raw is None and self.task_id:
            entry = self.store.boxes_entry_at(
                self._boxes_write_path(), Path(path_text).stem
            )
            raw = entry[0] if entry else []
        return list(raw or [])

    def _store_slots(self, path_text: str, raw: list, origin: str, select_box=None) -> None:
        """把槽位结果落库 + 进缓存 + 刷预览（人工编辑与类型切换共用一条路径）。

        ``select_box`` 给定某个框时，重新上屏后仍选中**同一个框**（按坐标找回）——
        切换类型 / 整理槽位会改变框在列表里的次序，按下标保持会选错框。
        """
        image_key = Path(path_text).stem
        self.detect_cache[str(path_text)] = list(raw)
        if self.task_id:
            self.store.save_detect_boxes(
                self.task_id, image_key, list(raw), origin=origin,
                **self._node_scope(self.node_of_stage("detect")),
            )
        shown = self._valid_boxes(raw)
        index = -1
        if select_box is not None:
            target = list(select_box)
            index = next((i for i, b in enumerate(shown) if list(b) == target), -1)
        self._apply_boxes(path_text, raw, origin, select_index=index)
        self._refresh_reference_boxes()
        # 拖动/删框/切类型都会改这一页的形态 → 右侧统计**立即**重算
        # （不走节流：用户正盯着这页改，错一拍就是错的）
        self._refresh_stats_now()

    def _apply_boxes(self, path_text: str, raw, origin: str | None = None, select_index: int = -1) -> None:
        """把某页的槽位结果画到大图上。

        显示用的名称/颜色**由控件按中心位置现算**（`image_view.box_styles`），
        这里只把 ``full``（整幅页）标志、一行文案与要选中的下标交给它——
        规则不抄第二份。

        两种识别方式的上屏完全一样（人工标注画的框与自动识别的框在文件里
        同构：都是槽位），差别只在"框从哪来"。
        """
        from desktop.components.viewers.image_view import box_names  # noqa: PLC0415

        size = self._image_size_for(path_text)
        # 全书统计判定「这页的整幅其实像半幅」→ 上屏按半幅显示（用户 2026-10-26，
        # 任务 0023）。人工框不参与，避免用户显式改的类型被自动翻回去。
        half_width = getattr(self, "_half_width_median", None)
        manual = getattr(self, "_manual_stems", set()) or set()
        stem = Path(path_text).stem
        if (
            half_width is not None
            and size
            and origin != "manual"
            and stem not in manual
        ):
            corrected = full_to_half_slots(raw, size[0], half_width)
            if corrected != raw:
                raw = corrected
        shown = self._valid_boxes(raw)
        full = is_full_content(raw)
        qsize = QSize(size[0], size[1]) if size else QImageReader(str(path_text)).size()
        # ⚠️ 单栏书里这个横跨整页的框叫「半幅」，不叫左框/右框——整本书的结论
        #    来自 profile_book（见 _refresh_detect_stats 写入 viewer 的那一份），
        #    这里读 viewer 的现值以保证「标签」与「面板高亮」同一口径。
        # ⚠️ 若用户在半幅页上**指定过**左/右，标签就用指定值（优先级见 box_styles）。
        side = self._side_override_of(path_text, raw)
        setter = getattr(self.detect_viewer, "set_side_override", None)
        if callable(setter):
            # ⚠️ rerender=False：下面紧接着 apply_boxes 会重绘一次，这里再画一遍
            #    就是一次切换类型画两遍（用户报的卡顿）。取不到 rerender 形参的
            #    替身按老签名调（自测替身只实现被断言用到的方法）。
            try:
                setter(side, False)
            except TypeError:
                setter(side)
        names = box_names(shown, size, full, self._single_column_display(), side)
        info = self._describe_boxes(shown, names) + ORIGIN_SUFFIX.get(origin or "", "")
        self._show_boxes_info(shown, origin, names=names)
        self._set_box_editable(True)
        self.detect_viewer.apply_boxes(
            shown,
            qsize,
            info,
            full=full,
            selected=select_index,
        )
        self._sync_box_hint(shown)
    def _sync_box_hint(self, shown) -> None:
        """画布顶部那条红框提示（用户 2026-11-12）：告诉用户**能手动改框**。

        随"这页有没有框 / 是不是人工标注"换文案（文案本体的唯一实现在
        ``box_kinds.manual_hint_text``）。⚠️ 走 ``getattr`` 兜底：自测的 viewer
        替身只实现被断言用到的方法，缺这个方法不该把整次上屏打断。
        """
        setter = getattr(self.detect_viewer, "set_hint_banner", None)
        if not callable(setter):
            return
        if self.detect_viewer.current_path() is None:
            setter("")
            return
        setter(manual_hint_text(has_boxes=bool(shown), manual=self._detect_manual()))
    # ------------------------------------------------------------ 页面几何
    def _image_size_for(self, path_text: str):
        """页面图片原始尺寸 (w, h)：优先 sizes.json，回退读图头。

        ⚠️ 尺寸基准按**产出这张图的节点**取（B 方案）：两个「图片提取」节点
        用不同 zoom/dpi 时页面尺寸不同，按主节点那份缩放会让副本节点的框错位。
        """
        if self.task_id:
            size = self.store.image_size(
                self.task_id, Path(path_text).stem,
                **self._scope_of(self._size_node_for(path_text)),
            )
            if size and size[0] > 0 and size[1] > 0:
                return int(size[0]), int(size[1])
        head = QImageReader(str(path_text)).size()
        if head.isValid() and head.width() > 0:
            return head.width(), head.height()
        return None
    def _detect_image_selected(self, index: int, path_text: str) -> None:
        """选中图片：只展示已有标注，绝不自动执行检测（重负载操作需用户触发）。

        **人工标注 + 「自动使用上一个文本框标注」**（用户 2026-11-16）在这里
        补一件事：本页还没有任何标注、而**上一个停留的页面**画过框时，把上一页
        的框带到本页（规则见 :meth:`_inherit_boxes_from_prev`）。
        """
        path = Path(path_text)
        key = str(path)
        prev = getattr(self, "_detect_prev_path", None)
        # 先记下"这一页就是下一次切页时的上一页"，再判沿用——
        # 用"上一个停留的页面"而不是"清单里的前一页"：用户跳着翻页时，
        # 他心里的"上一页"是刚才看的那一页，不是页码减一。
        self._detect_prev_path = key
        self.detect_viewer.set_reference_boxes([])
        if self._inherit_boxes_from_prev(key, prev):
            self._refresh_reference_boxes()
            return
        if key in self.detect_cache:
            raw = self.detect_cache[key] or []
            if self._valid_boxes(raw):
                self._apply_boxes(key, raw)
            else:
                self._show_boxes_info([])
                # ⚠️ 无框时也要把预览的形态复位：否则上一页如果是整幅页，
                #    本页会沿用「整幅」的框数上限（只能画一个框）。
                self.detect_viewer.apply_boxes(
                    [],
                    QImageReader(key).size(),
                    self._describe_boxes([]),
                    full=is_full_content(raw),
                )
                # 框可以随时手绘（两种识别方式都一样）
                self._set_box_editable(True)
                # 顶部提示跟着换文案（这页没框："拖一下就能手画一个"）
                self._sync_box_hint([])
            self._refresh_reference_boxes()
            return
        # 优先使用库里的框（含手动调整过的）
        entry = (
            self.store.boxes_entry_at(self._boxes_write_path(), path.stem)
            if self.task_id else None
        )
        if entry is not None:
            boxes, origin = entry
            self.detect_cache[key] = boxes
            self._apply_boxes(key, boxes, origin)
            self._refresh_reference_boxes()
            return
        self.detect_viewer.info_label.setText(
            "尚未检测：点底部「检测文本框」批量检测，或直接在这页手画框"
            if not self._detect_manual()
            else "人工标注：在图上拖一下画出这一页的文本框"
        )
        self._sync_box_hint(self._raw_boxes_for(key))
    def _set_box_editable(self, editable: bool) -> None:
        """开关「在预览上手绘/拖动框」（两种识别方式都开着）。

        走 ``getattr`` 兜底：自测的 viewer 替身只实现被断言用到的方法，缺这个
        不该把整次上屏打断。``_detect_boxes_editable`` 是控件建出来时的口径
        （接线时记下）：本来就是只读预览时永远别再打开编辑。
        """
        view = getattr(self.detect_viewer, "view", None)
        setter = getattr(view, "set_boxes_editable", None)
        if callable(setter):
            allowed = bool(getattr(self, "_detect_boxes_editable", True))
            setter(bool(editable) and allowed)
    def _refresh_reference_boxes(self) -> None:
        """清掉参考层并同步第三步预览。

        ⚠️ 「保留框外空白」现在**把扩展框直接画成实线框**（见 ``_apply_boxes``），
        不再需要"橙色虚线"那层参考框——留着反而与实线重影。参考层本身仍保留在
        控件里（``set_reference_boxes`` 是 ImageView 的公开 API），只是本步不用。
        """
        self.detect_viewer.set_reference_boxes([])
        # rembg 预览的区域同步刷新（显示范围跟随检测框）
        # ⚠️ **只在本步就是「图片去底色」时才刷**（用户 2026-10-17 报「切换
        #    左/右/半幅/整幅卡顿」）：``refresh_display`` 会重建全部条目并重新
        #    解码 + 合成当前页的大图（12MP 扫描件几十到几百毫秒），而第二步
        #    根本看不见那个控件。进第三步时 ``_show_stage`` 会 ``set_images``
        #    重建一次，所以这里跳过不会读到旧框。
        if self.current_stage() == "rembg":
            self.rembg_viewer.refresh_display()

    def _show_boxes_info(self, boxes, origin: str | None = None, names=None,
                         extra: str = "") -> None:
        if boxes is None:
            self.detect_viewer.info_label.setText("正在检测文本框位置...")
            return
        suffix = ORIGIN_SUFFIX.get(origin or "", "")
        self.detect_viewer.info_label.setText(
            self._describe_boxes(boxes, names) + suffix + extra
        )

    @staticmethod
    def _describe_boxes(boxes, names=None) -> str:
        """框列表 → 一行说明；names 与 boxes 对齐（整幅页显示「整幅」）。

        names 缺失时回退到「左框/右框」（旧的按序号命名）。
        """
        if not boxes:
            return "未检测到文本框"
        labels = list(names) if names else []
        return "  ｜  ".join(
            f"{(labels[i] if i < len(labels) else ('左框', '右框')[i % 2])}" f"({b[0]},{b[1]},{b[2]},{b[3]})"
            for i, b in enumerate(boxes)
        )
    def _save_manual_boxes(self, path_text: str, boxes) -> None:
        """预览区编辑线框后保存到库（origin=manual），不生成任何文件。

        存的是**槽位**表示，不是"用户画了几个框"：
        - 整幅页 → 1 槽 ``[整幅]``；
        - 半幅页 → **恒 2 槽** ``[左, 右]``（缺失侧 null）。

        这样删到一个不剩或只剩一侧时，形态都不会从半幅变成整幅——用户报的
        "删掉整幅框后，右边的框自动变成了整幅" 就是按元素个数推断类型的后果。
        """
        if not self.task_id:
            return
        normalized = [[int(round(float(v))) for v in box] for box in boxes]
        size = self._image_size_for(path_text) or (0, 0)
        sel = self.detect_viewer.selected_index()
        sel_box = normalized[sel] if 0 <= sel < len(normalized) else None
        if not normalized:
            raw: list = []
        elif self.detect_viewer.box_full_mode() and len(normalized) == 1:
            raw = [normalized[0]]  # 整幅：只允许一个框（控件侧已按 max_boxes 拦住）
        else:
            # 半幅：恒 2 槽。⚠️ 万一"整幅页"却拿到多个框（不该发生），按半幅存——
            # 宁可形态变半幅，也不能悄悄丢掉用户画出来的框。
            raw = half_slots(normalized, size)
        self._store_slots(path_text, raw, "manual", select_box=sel_box)
