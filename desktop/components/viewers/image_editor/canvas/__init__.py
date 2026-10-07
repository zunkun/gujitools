# -*- coding: utf-8 -*-
"""编辑画布的**工具域 Mixin 子包**（从 ``image_editor.py`` 拆出，2026-10-07）。

``EditorCanvas`` 由基座（``core``）与七个工具 Mixin 组合而成：

| 模块 | Mixin | 职责 |
| --- | --- | --- |
| ``core`` | ``EditorCanvas`` | 类头/信号/``__init__``/装图/缩放适配/工具切换 |
| ``text`` | ``TextMixin`` | 插入文字块 |
| ``transform`` | ``TransformMixin`` | 统一变换（缩放/切变/旋转/移动） |
| ``deform`` | ``DeformMixin`` | 操控变形（图钉 + ARAP 网格） |
| ``cage`` | ``CageMixin`` | 变换笼（RBF 局部形变） |
| ``rectify`` | ``RectifyMixin`` | 四角校正 |
| ``overlay`` | ``OverlayMixin`` | 覆盖层装配与同步 |
| ``interaction`` | ``InteractionMixin`` | 鼠标/键盘交互与命中测试 |

⚠️ **Mixin 之间无同名成员**（同名会被 MRO 静默遮蔽）——有自测钉住。
"""
from desktop.components.viewers.image_editor.canvas.core import EditorCanvas

__all__ = ["EditorCanvas"]
