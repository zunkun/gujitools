# -*- coding: utf-8 -*-
"""「位置 / 文字方向」的固定取值：桌面端不给选，但历史参数要原样回显。

从 ``print_form.PrintFormMixin`` 拆出。这一段**不碰任何控件**，只回答
"这段文字的位置 / 方向该导出成什么"，是全类里依赖最少的一块：

* 依赖：`self._fixed_layout_echo`（由 ``PrintPanel.__init__`` 初始化）
* 被依赖：``PrintFormMixin``（从而 ``PrintPanel``）；``print_panel.get_args``
  经 ``_fixed_layout`` 取值，但不 import 本模块

拆出来的理由：它是**纯取值规则**（界面删了控件、参数键还在），和控件构建
没有任何共同点；留在表单 Mixin 里只会让人以为"改界面会改到它"。
"""

from __future__ import annotations


class PrintTextLayoutMixin:
    """print 面板「位置」「文字方向」的固定取值（由 PrintFormMixin 继承）。"""

    # ---------------------------------------------------------- 固定排版方向
    # 「位置」「文字方向」已在桌面端**删除**（用户要求）：古籍的书名在版框
    # 之上、页码在版心之下，都是竖排的定式，摆成下拉只会让人以为可以乱选
    # （用户的原话是「要不然就取消"位置"和"文字方向"两个参数，默认标题在上面，
    # 页码在下面」）。表单不再创建这两个控件，取值一律走本表：
    # 标题恒 top、页码恒 bottom，两者恒 vertical。
    #
    # ⚠️ 这只是**界面**的固定：命令行/YAML 的 `title_position` /
    # `page_number_orientation` 等键与默认值一字未动（见 core.command_spec），
    # 独立用法照旧可指定；回填时也**不拿本表去覆盖**历史参数——否则用户一个
    # 老任务里存的 horizontal，会在「参数暂存」写入时被悄悄改成 vertical。
    FIXED_TEXT_LAYOUT = {
        "title": {"position": "top", "orientation": "vertical"},
        "page_number": {"position": "bottom", "orientation": "vertical"},
    }

    @classmethod
    def _fixed_layout_default(cls, which: str, key: str) -> str:
        """桌面端固定的排版方向（**出厂默认**）：which=title/page_number。"""
        return cls.FIXED_TEXT_LAYOUT[which][key]

    def _fixed_layout(self, which: str, key: str) -> str:
        """本面板「位置」「文字方向」的导出值。

        界面没有这两个控件，但**回填过的历史值要被原样保留**：
        `_apply_args` 把历史参数里读到的值记进 `self._fixed_layout_echo`，
        这里优先回显它，只有老任务没这个键时才落回固定默认
        （标题 top、页码 bottom、两者 vertical）。
        """
        echo = getattr(self, "_fixed_layout_echo", None) or {}
        value = echo.get(f"{which}_{key}")
        if value:
            return str(value)
        return self._fixed_layout_default(which, key)
