# -*- coding: utf-8 -*-
"""框「类型」人工干预的共享交互流——任务流程第二步与独立检测页的唯一实现。

三条约定的落点（用户 2026-09-29 定）：

1. **删除不影响其他框的类型**：类型存在**槽位**里，不是"还剩几个框"推出来的；
2. **左右只在"双框页"上由框的中心位置决定**（``utils.box_geometry``），拖动跨过
   中线自动换边；**单框页**（只检出一侧——含「整幅」页，它同样只有一个框）
   由**用户指定**（存 ``boxes.json`` 的 ``side``）：单框页的中心压在中线上，
   位置判定没有意义（用户 2026-10-17）；
3. **整幅是显式类型**：用户选了就一直是整幅；整幅与半幅互斥、一页只能一个框，
   切整幅时若有其他框，**先问再删，绝不静默删框**。

这套"怎么问用户"此前在 ``pages/taskdetail/detect.py`` 与
``modules/detect/page.py`` 各写一份（靠注释约束同步），现在收进本类：
结果计算全部委托 ``utils.box_geometry`` 的纯函数，本类只管**交互顺序与文案**。

⚠️ **本模块不含任何 Qt**：确认框通过宿主的 :meth:`BoxKindHost.box_confirm`
回调弹（任务流程用 ``Dialog``、独立页用 ``MessageBox``——两侧各自的延迟导入
与自测替身机制因此原样保留）。宿主协议见 :class:`BoxKindHost`。
"""

from __future__ import annotations

from typing import Any

from utils.box_draw import box_kind_name
from utils.box_geometry import drop_box, set_box_full, set_box_half, set_box_side


#: ``box_commit(..., side=...)`` 的默认值：**不动**该页已有的左右指定。
#: 用字符串哨兵而不是 ``None``，因为 ``None`` 本身有含义（＝清除指定、退回半幅）。
SIDE_KEEP = "keep"


class BoxKindHost:
    """宿主协议（仅说明用；两侧以同名词缀 ``box_`` 前缀实现，避免撞名）。

    - ``box_viewer()``：预览控件——需要 ``box_kinds()`` / ``selected_index()``
      / ``select_box(i)``；
    - ``box_toast(kind, title, content)``：提示出口（任务流程是 ``_toast``、
      独立页是 ``toast``，语义相同）；
    - ``box_raw_slots(path_text)``：该页**槽位**表示（保留 null，形态在槽数里）；
    - ``box_page_is_full(path_text)``：当前页是否整幅形态（半幅页上点左/右
      只解释规则不给切换）；
    - ``box_page_half_candidate(path_text)``：当前页是否**够「半幅」**——整本书
      判定为单栏书 **且** 这页只有一个宽到横跨整页的框（判据
      :func:`utils.book_layout.is_single_wide_box`）。为真时左右**可指定**
      （中心压在中线上，位置判定没有意义）；
    - ``box_image_size(path_text)``：原始像素 ``(w, h)``，取不到给 ``None``；
    - ``box_commit(path_text, slots, select_box=None, side=SIDE_KEEP)``：落库 +
      重画——任务流程写 ``boxes.json`` + 内存缓存，独立页写内存表，各自实现。
      ``side`` 语义：``"left"``/``"right"`` 写入指定、``None`` 清除、
      ``"keep"``（默认）不动；
    - ``box_confirm(title, body, yes_text, cancel_text) -> bool``：确认框；
    - ``box_resync_kind(index)``：**按现值回填面板高亮**。类型操作结束时必调：
      有些点击是"无操作"的（普通半幅页点另一侧、整幅声明被取消），而分段控件
      在按下那一刻就把滑块移过去了——不回填就会停在"看起来切了、其实没切"的
      位置，用户再点一次才发现（用户 2026-10-17 报"切换有问题"）；
    - ``box_current_path_text()``：当前页路径（没有页时给空串）。
    """


class BoxKindEditor:
    """共享交互器：类型切换 / 选框 / 整幅互斥确认 / 删框。

    无状态（每次操作从宿主取现值），可安全地按需构造：
    ``BoxKindEditor(self).make_full(path, index)``。
    """

    def __init__(self, host: Any) -> None:
        self.host = host

    # ------------------------------------------------------------ 类型切换
    def set_kind(self, path_text: str, index: int, kind: str) -> None:
        """面板里点了「左框 / 右框 / 半幅 / 整幅」。

        没选中框时按用户要求 6 处理：**点类型即选中该类型的框**；选中了框
        则切换它的类型（整幅要过互斥检查）。

        ⚠️ **点哪段就是哪段**（用户 2026-10-17 第五轮：「四个按钮自由切换，
        直接改这张图的类型就行」）——不再按"当前是整幅页 / 半幅页"分两条路：

        - 「左框」「右框」：**单框页**（含当前是「整幅」的页）直接摆到该侧并
          记下 ``side``；**双框页**左右由中心位置决定，点另一侧没有可写的东西
          （把一侧"改成另一侧"等于交换两栏，不是标注）；
        - 「半幅」：摊成半幅 **2 槽** + 清除 ``side``（旧实现只清 ``side`` 不动
          槽数——从「整幅」点它就是空操作，用户 2026-10-17 报）；
        - 「整幅」：单槽 + 互斥确认（见 :meth:`make_full`）。

        ⚠️ 这三类点击都**不弹提示**（用户 2026-10-17）——结果直接体现在框的
        颜色/名称与面板高亮上。

        ⚠️ 落账后**一律回填面板**（``box_resync_kind``）：分段控件在按下那一
        刻就把滑块移到被点的段，而"普通半幅页点另一侧"这类点击本来就没有可
        写的东西——不回填就会停在假位置上（看起来切了，其实没切）。
        """
        if index < 0:
            self.select_box_of_kind(kind)
            return
        kinds = self.host.box_viewer().box_kinds()
        current = kinds[index] if index < len(kinds) else ""
        if kind == current:
            return  # 已经是这个类型（普通半幅页按位置判定，点了也是这个结果）
        if kind == "half":
            self.clear_side(path_text, index)
        elif kind == "full":
            self.make_full(path_text, index)
        else:
            self.make_half(path_text, index, kind)
        self._resync(index)

    def _resync(self, index: int) -> None:
        """按现值回填面板高亮（宿主没实现该钩子时静默跳过）。"""
        resync = getattr(self.host, "box_resync_kind", None)
        if callable(resync):
            resync(index)

    def clear_side(self, path_text: str, index: int) -> None:
        """点「半幅」：摊成半幅 **2 槽** + 清除「用户指定的左右」。

        ⚠️ **静默**（用户 2026-10-17：指定左/右/半幅都不需要提示）：点类型
        本身就是即时生效的操作，结果直接反映在框的颜色/名称与面板高亮上，
        再弹一条"已指定"只是噪音。

        ⚠️⚠️ **「整幅」页上点它也必须真的离开整幅**（用户 2026-10-17 报
        「当前是整幅，直接点半幅没有效果」）：整幅页是 **1 槽**，只清 ``side``
        不动槽数，形态还是整幅 ⇒ 看着什么都没发生。这里先按中心位置把它摊成
        半幅 2 槽（``set_box_half``）再清指定——「半幅」就是"半幅 2 槽且没有
        人工指定"。

        ⚠️ 只有**单框页**才有可清除的指定：双框页的左右由位置决定，没有
        ``side`` 可清（点了就当无操作，但必须回填面板）。
        """
        raw = self.host.box_raw_slots(path_text)
        boxes = [b for b in raw if b]
        if len(boxes) != 1 or not 0 <= index < len(boxes):
            self._resync(index)  # 没有可清除的指定 → 滑块拨回真实类型
            return
        if self.host.box_page_is_full(path_text):
            size = self.host.box_image_size(path_text) or (0, 0)
            self.host.box_commit(
                path_text, set_box_half(raw, index, size),
                select_box=boxes[index], side=None,
            )
            return
        self.host.box_commit(path_text, raw, select_box=boxes[index], side=None)

    def select_box_of_kind(self, kind: str) -> None:
        """没有选中框时，点类型＝选中该类框；该类型不存在则提示。"""
        for index, value in enumerate(self.host.box_viewer().box_kinds()):
            if value == kind:
                self.host.box_viewer().select_box(index)
                return
        self.host.box_toast(
            "info",
            f"没有「{box_kind_name(kind)}」",
            "当前页没有这个类型的框：可先在预览里画出文本框，或点已有框后切换类型。",
        )

    # ------------------------------------------------------------ 整幅互斥
    def make_full(self, path_text: str, index: int) -> None:
        """把第 index 个框设为「整幅」（整幅与半幅互斥、一页只能一个框）。"""
        raw = self.host.box_raw_slots(path_text)
        boxes = [b for b in raw if b]
        if not 0 <= index < len(boxes):
            return
        others = [b for i, b in enumerate(boxes) if i != index]
        if others:
            # 用户要求 4/5：整幅只能有一个框、且与左右半幅互斥 → 说清现状并
            # 让用户自己决定删不删。其他框的类型照实写出来：其中若已有
            # 「整幅」，用户一眼看到"已存在一个整幅"。
            kinds = self.host.box_viewer().box_kinds()
            labels = "、".join(
                f"「{box_kind_name(kinds[i])}」"
                for i in range(len(boxes))
                if i != index and i < len(kinds)
            )
            agreed = self.host.box_confirm(
                "整幅只能有一个框",
                f"当前页还有其他文本框（{labels}）。\n"
                "整幅与左右半幅互斥，且整幅一页只能有一个框。\n"
                "是否删除其他文本框，把当前框设为「整幅」？",
                "删除其他框并设为整幅",
                "取消",
            )
            if not agreed:
                self._resync(index)  # 回填面板高亮，别停在「整幅」
                return
        self.host.box_commit(
            path_text, set_box_full(raw, index), select_box=boxes[index], side=None
        )

    def make_half(self, path_text: str, index: int, kind: str) -> None:
        """点「左框」/「右框」：把第 index 个框**直接**摆到那一侧。

        ⚠️ 按**框的个数**分两种情况（用户 2026-10-17 第三/四/五轮修正）：

        - **单框页**（古籍最常见：只检出一侧，另一槽为空）→ **用户说了算**：
          把框摆到指定槽位并记下显式左右（``boxes.json`` 的 ``side``）。
          ⚠️ 这一条**与当前形态无关**——「整幅」页同样只有一个框，所以从
          「整幅」点「左框/右框」也必须**一步**到位（旧实现走"整幅→半幅"那条
          按**中心位置**落槽的分支，而整页框的中心恰好压在中线上 ⇒ 恒落右槽，
          用户点「左框」却得到「右框/半幅」，得再点一次——用户 2026-10-17 报）；
        - **双框页**（一页真有左右两页）→ 左右由**中心位置**决定，点另一侧
          没有可写的东西（把一侧"改成另一侧"等于交换两栏，不是标注）。

        ⚠️ 两条路都**静默**（用户 2026-10-17：「指定左框/右框/半幅不需要提示」）：
        框的颜色与名称、面板高亮本身就是结果，弹提示只是噪音。
        ⚠️ 无论哪条路都要**回填面板**：滑块在按下时已被移过去，不回填就停在
        假位置（看着切了、其实没切）。
        """
        raw = self.host.box_raw_slots(path_text)
        boxes = [b for b in raw if b]
        if not 0 <= index < len(boxes):
            return
        if len(boxes) == 1:
            # 单框页（含「整幅」页）：槽位摆到指定侧 + 记下显式左右
            # （重复点同一侧无副作用）
            self.host.box_commit(
                path_text, set_box_side(raw, index, kind),
                select_box=boxes[index], side=kind,
            )
        self._resync(index)

    # ---------------------------------------------------------------- 删框
    def delete_selected(self) -> None:
        """删除当前选中的文本框（与 Delete 键同一条路径）。"""
        path_text = self.host.box_current_path_text()
        if not path_text:
            return
        index = self.host.box_viewer().selected_index()
        if index < 0:
            self.host.box_toast("info", "未选中文本框", "先在预览里点一下要删除的框。")
            return
        raw = self.host.box_raw_slots(path_text)
        boxes = [b for b in raw if b]
        if not 0 <= index < len(boxes):
            return
        size = self.host.box_image_size(path_text) or (0, 0)
        self.host.box_commit(path_text, drop_box(raw, index, size), side=None)
        self.host.box_viewer().select_box(-1)
