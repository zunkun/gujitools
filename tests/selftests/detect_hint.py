# -*- coding: utf-8 -*-
"""画布顶部「能手动改框」红框提示的自测（用户 2026-11-12）。

需求原话："检测文本框区域，可以红线提示用户可以手动调整框类型和画框，
可以放在中间图片顶部"。

守三件事：

1. 文案按情况分岔（有框 / 没框 / 人工标注），且**只有一份实现**
   （``box_kinds.manual_hint_text``，任务流程与独立检测页共用）；
2. 提示条真的在**图片上方**（不是压在图上、也不是跑到图下面去），
   没文案时**不占位**（其它步骤的预览区高度不受影响）；
3. 用户点 × 之后**不再打扰**（后续怎么刷新上屏都不许把它顶回来）。
"""

from __future__ import annotations

from pathlib import Path

from desktop.components.box_kinds import manual_hint_text
from desktop.components.viewers.hint_banner import HintBanner
from desktop.components.viewers.image_viewer import ImageViewerWidget
from desktop.pages.taskdetail.detect import DetectMixin

NAME = "detect_hint"
DEPENDS: list[str] = []
TITLE = "检测文本框：画布顶部可手动改框提示"

#: 各分支必须出现的关键词（用户最需要被告知的动作）
WANT_BOX_KINDS = "框类型"
WANT_DRAW = "手画"
WANT_MANUAL = "人工标注"


class _ViewerStub:
    """只实现 ``_sync_box_hint`` 用到的那两个方法。"""

    def __init__(self, path: str | None):
        self.path = path
        self.hint: str | None = None

    def current_path(self):
        return Path(self.path) if self.path else None

    def set_hint_banner(self, text: str) -> None:
        self.hint = text


class _HostStub(DetectMixin):
    """把 ``_sync_box_hint`` 单独挂在最小宿主上（其余成员它不碰）。"""

    def __init__(self, path: str | None, manual: bool = False):
        self.detect_viewer = _ViewerStub(path)  # type: ignore[assignment]
        self._manual = manual

    def _detect_manual(self) -> bool:
        return self._manual


def run(ctx) -> None:  # noqa: ARG001 - 本模块自带夹具，不用共享 ctx
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from tests.selftests._context import ok

    # ---------------------------------------------------------------- 文案
    with_boxes = manual_hint_text(has_boxes=True)
    without = manual_hint_text(has_boxes=False)
    manual_boxes = manual_hint_text(has_boxes=True, manual=True)
    manual_empty = manual_hint_text(has_boxes=False, manual=True)

    ok("有框：提示可以改框类型（点名右栏那个控件）",
       WANT_BOX_KINDS in with_boxes and "右栏" in with_boxes, with_boxes)
    ok("有框：提示怎么改位置/尺寸（拖动 / 拉角 / 空白处画新框）",
       "拖动" in with_boxes and "拉角" in with_boxes and "新框" in with_boxes,
       with_boxes)
    ok("文案短到一行放得下（不折成第二行只剩几个字）",
       max(len(with_boxes), len(without), len(manual_boxes),
           len(manual_empty)) <= 40,
       str(max(len(with_boxes), len(without), len(manual_boxes),
               len(manual_empty))))
    ok("无框：先告诉用户**能直接手画**（模型检不出时最快的出路）",
       WANT_DRAW in without, without)
    ok("无框：也给出底部「检测文本框」这条批量路径",
       "检测文本框" in without, without)
    ok("有框时两种方式共用同一句（框的操作没差别）",
       manual_boxes == with_boxes, manual_boxes)
    ok("人工标注 + 无框：点名当前方式，且**不提**「检测文本框」"
       "（该方式下那个按钮压根不显示）",
       WANT_MANUAL in manual_empty and "检测文本框" not in manual_empty,
       manual_empty)
    ok("人工标注 + 无框：仍然告诉用户怎么画", WANT_DRAW in manual_empty, manual_empty)

    # ------------------------------------------------- 宿主：文案随状态切换
    host = _HostStub("/t/0001.png")
    host._sync_box_hint([[10, 10, 100, 100]])
    ok("宿主：有框时给「改类型」那句",
       host.detect_viewer.hint == with_boxes, str(host.detect_viewer.hint))
    host._sync_box_hint([])
    ok("宿主：没框时给「手画一个」那句",
       host.detect_viewer.hint == without, str(host.detect_viewer.hint))
    host_manual = _HostStub("/t/0001.png", manual=True)
    host_manual._sync_box_hint([])
    ok("宿主：人工标注 + 没框时给「人工标注」那句",
       host_manual.detect_viewer.hint == manual_empty,
       str(host_manual.detect_viewer.hint))
    host_none = _HostStub(None)
    host_none._sync_box_hint([[10, 10, 100, 100]])
    ok("宿主：没有当前页时收起提示（空态上不该浮一句「在图上拖」）",
       host_none.detect_viewer.hint == "", repr(host_none.detect_viewer.hint))

    # -------------------------------------------------------- 控件：位置/关闭
    viewer = ImageViewerWidget(editable=False, show_boxes=True)
    viewer.resize(700, 480)
    viewer.show()
    QApplication.processEvents()

    ok("查看器自带提示条（默认隐藏，不占位）",
       isinstance(viewer.hint_banner, HintBanner) and viewer.hint_banner.isHidden())

    viewer.set_hint_banner("提示一下")
    QApplication.processEvents()
    banner = viewer.hint_banner
    ok("给了文案就显示出来", not banner.isHidden() and banner.isVisible())
    ok("提示条在图片**上方**（不压图、也不在图下面）",
       banner.geometry().bottom() <= viewer.view.geometry().top(),
       f"banner={banner.geometry()} view={viewer.view.geometry()}")

    # 用户点 × → 收起，并且**后续刷新不许把它顶回来**
    QTest.mouseClick(banner.close_button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()
    ok("点 × 之后收起", banner.isHidden())
    viewer.set_hint_banner("换一句话")
    QApplication.processEvents()
    ok("点过 × 之后换文案也不再弹（不打扰已经知道的人）",
       banner.isHidden() and banner.text() == "换一句话", banner.text())

    # 换一本/清空清单：没有图就没有"在图上拖一下"
    fresh = ImageViewerWidget(editable=False, show_boxes=True)
    fresh.set_hint_banner("有图时的提示")
    ok("准备：有图之前提示可以显示", fresh.hint_banner.isHidden() is False)
    fresh.set_images([])
    ok("清单空了 → 提示条跟着收起", fresh.hint_banner.isHidden())

    # 空串也能收起（宿主"没有当前页"那条路）
    fresh.set_hint_banner("")
    ok("传空串 = 收起", fresh.hint_banner.isHidden())
