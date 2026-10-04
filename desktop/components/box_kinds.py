# -*- coding: utf-8 -*-
"""框「类型」人工干预的共享交互流——任务流程第二步与独立检测页的唯一实现。

三条约定的落点（用户 2026-09-29 定）：

1. **删除不影响其他框的类型**：类型存在**槽位**里，不是"还剩几个框"推出来的；
2. **半幅的左/右由框的中心位置决定**（``utils.box_geometry``），拖动跨过中线
   自动换边——所以半幅页上点「左框/右框」不给切换、只解释规则；
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
from utils.box_geometry import drop_box, set_box_full, set_box_half


class BoxKindHost:
    """宿主协议（仅说明用；两侧以同名词缀 ``box_`` 前缀实现，避免撞名）。

    - ``box_viewer()``：预览控件——需要 ``box_kinds()`` / ``selected_index()``
      / ``select_box(i)``；
    - ``box_toast(kind, title, content)``：提示出口（任务流程是 ``_toast``、
      独立页是 ``toast``，语义相同）；
    - ``box_raw_slots(path_text)``：该页**槽位**表示（保留 null，形态在槽数里）；
    - ``box_page_is_full(path_text)``：当前页是否整幅形态（半幅页上点左/右
      只解释规则不给切换）；
    - ``box_image_size(path_text)``：原始像素 ``(w, h)``，取不到给 ``None``；
    - ``box_commit(path_text, slots, select_box=None)``：落库 + 重画——任务
      流程写 ``boxes.json`` + 内存缓存，独立页写内存表，各自实现；
    - ``box_confirm(title, body, yes_text, cancel_text) -> bool``：确认框；
    - ``box_full_declined(index)``：用户拒绝"删除其他框并设为整幅"后的回填
      钩子（把面板高亮从「整幅」拨回去）；
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
        """面板里点了「左框 / 右框 / 整幅」。

        没选中框时按用户要求 6 处理：**点类型即选中该类型的框**；选中了框
        则切换它的类型（整幅要过互斥检查）。
        """
        if index < 0:
            self.select_box_of_kind(kind)
            return
        kinds = self.host.box_viewer().box_kinds()
        current = kinds[index] if index < len(kinds) else ""
        if kind == current:
            return  # 已经是这个类型（左/右按位置判定，点了也是这个结果）
        if kind == "full":
            self.make_full(path_text, index)
        else:
            self.make_half(path_text, index, kind)

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
                "整幅与左右半框互斥，且整幅一页只能有一个框。\n"
                "是否删除其他文本框，把当前框设为「整幅」？",
                "删除其他框并设为整幅",
                "取消",
            )
            if not agreed:
                self.host.box_full_declined(index)  # 回填面板高亮，别停在「整幅」
                return
        self.host.box_commit(
            path_text, set_box_full(raw, index), select_box=boxes[index]
        )

    def make_half(self, path_text: str, index: int, kind: str) -> None:
        """把第 index 个框改成半幅（左/右）。"""
        raw = self.host.box_raw_slots(path_text)
        boxes = [b for b in raw if b]
        if not 0 <= index < len(boxes):
            return
        if not self.host.box_page_is_full(path_text):
            # 半幅页里左/右是**位置**决定的（用户要求 2），点不出另一种来
            side = box_kind_name(kind)
            self.host.box_toast(
                "info",
                f"「{side}」由框的位置决定",
                f"左框/右框按框的中心位置自动判定：把这个框拖到页面的另一半，"
                f"它就会变成{side}。",
            )
            return
        # 整幅 → 半幅：一个框也能是半幅（漏检一侧的情形），按中心位置定左右
        size = self.host.box_image_size(path_text) or (0, 0)
        self.host.box_commit(
            path_text, set_box_half(raw, index, size), select_box=boxes[index]
        )

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
        self.host.box_commit(path_text, drop_box(raw, index, size))
        self.host.box_viewer().select_box(-1)
