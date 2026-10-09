# -*- coding: utf-8 -*-
"""图片编辑弹窗：裁剪 / 变换 / 扭曲 / 擦除 / 文字（实时编辑）。

**版面**（2026-10-08 重排）：顶部一条**功能选择**（裁剪 变换 扭曲 擦除 文字）、
中间画布、**右侧当前功能的参数面板**（含「编辑历史」步骤列表）、底部状态行。
切功能 = 换右侧参数面板，参数竖排不横向溢出。

**编辑实时生效**：「应用裁剪」「应用变换」「插入文字」三个单步确认按钮已删除
——裁剪/变换**拖完松手即应用**，文字块本身就是画布上的实时预览、切功能或
「完成」时自动写入。每一步都会进撤销栈，右侧「编辑历史」里点某一格可直接
回退/前进到那一步（同 Ctrl+Z / Ctrl+Y）。

从图片预览弹窗（``image_zoom_dialog``）的「编辑」按钮进入，编辑的是
**画布当前整分辨率图**（已含翻转/旋转）；「完成」后写回弹窗画布。宿主
给 ``save_back=True``（画布显示 1:1 对应真实文件）时，「完成」= 直接
**原子覆盖原图片文件**，并**先弹一次覆盖确认**（用户 2026-10-04 定的：
原图被覆盖后不可逆，必须让用户知道；见 :meth:`ImageEditorDialog.
_confirm_overwrite`）。虚拟预览（区域合成/打印重排/PDF 页）没有文件
可回写，维持"满意用「下载」落盘、翻页/关窗即丢弃"的旧行为，也**不弹**
确认框（不写盘的事不该假报警）。

五个功能的行为口径：

- **裁剪**：**默认选中整幅图**，沿四边/四角**任意位置**向内拖收边（整条
  边都是命中带，不只手柄小方块）、拖框中间移动；**松手即裁到当前选区**
  （再点按钮那一版已删），画布尺寸随之收小、视图重新适应新图。不做截图式
  "拖拽画框"——那是截图的交互，裁剪的语义是"从原图里收出想要的部分"
  （用户 20:05 定）。
- **变换**（GIMP「统一变换」口径，`Shift+T` 那套）：**默认选中整幅图**，
  手柄按形状分语义——**四角大方框=双轴缩放**（内嵌小菱形=**透视**，单独挪
  一个角）、**四边中方框=单轴缩放**（只改宽或只改高，对边锚定）、**边上
  两个菱形=切变**（被抓的边不离开原边线）；框内拖=移动、框外拖=**绕轴心
  旋转**、轴心圆点可拖。面板照 GIMP 分节：方向 / 插值 / 剪裁 / 预览 /
  参考线 / 限制(Shift) / 从轴心(Ctrl) / 轴心 / 调整范围 / 翻转。
  勾选「**调整范围**」后沿边拖动**收小要处理的区域**（收完自动回到变换
  模式）——小范围修褶皱的入口。拖动即实时预览，**松手即烘焙进像素**——
  一步一个撤销点。
  ⚠️ 预览与烘焙走**同一个** `geometry.compose_transform`：拖动期间看到的
  内容落点 = 松手之后图变成的样子（含「校正（向后）」按反向矩阵掰正的
  那一档），不会出现"框在这里、内容却落在别处"。
- **扭曲**（GIMP「扭曲变换」口径）：圆形软笔刷支持移动像素、扩张/收缩、顺/逆时针旋转、平滑与恢复；大小/硬度/强度/间距均可调，支持最近邻/线性/立方插值。实时预览可关闭（松开时回放整笔），高质量预览可在拖动时使用所选插值；一笔一个撤销点。
- **擦除**：按住左键涂抹把污点**擦成白底**（古籍页面去污点就是涂白）；
  直径在参数面板可调；光标处有**实圈指示**，直径恒等于实际擦除直径
  （所见即所擦）。一笔一个撤销点。
- **文字**：点击落点 → 画布上**就地输入**（光标可见，点已有块可继续
  编辑）→ 参数面板可调字体 family / 字号 / **颜色选择器**（对整块即时
  生效，样式是段落属性，与手机作图App同口径）→ 鼠标悬停在文字上出现
  **边界虚线框**，按住拖动整块移动（虚线框跟随，松手即消失）。文字块
  就是实时预览，**切功能或点「完成」时自动写进图片**（「插入文字」按钮
  已删）。一个批次一个撤销点。

  参数面板的字体下拉**以中文字体为主**、只带几个常用西文字体（系统字体库
  动辄两三百个族，全列出来反而找不到"仿宋"，见 `ui.fonts`）；颜色是
  **一个按钮**，常用色块收在它弹出的面板里（见 `ui.color_picker`）。

  ⚠️ 样式改动作用在"**当前样式块**"（``EditorCanvas.style_target_block``）
  上，而不是"场景焦点项"：参数面板的控件（尤其 qfluentwidgets 的 Slider，
  它是 ``StrongFocus``）一被点击就会抢走键盘焦点，场景焦点项随之变 None，
  按焦点项找块的话**改字号/颜色全部落空**（用户 2026-10-01 报障）。

⚠️ 撤销栈存的是**整图快照**（QImage 写时复制在就地绘制时仍会共享底层数据，
必须 ``copy()``），上限 12 步——4000px 预览约 60MB/步，再多内存吃不消。
每一步还带一个**名字**（裁剪/变换/扭曲/擦除/文字/还原），右侧「编辑历史」
就是这张时间轴；名字与快照的对齐关系见 ``dialog_undo.py`` 开头的长注释。
"""
from __future__ import annotations

from .bake import (
    wait_cursor, _BakeWorker, run_with_progress,
)
from .canvas import EditorCanvas
from .consts import (
    UNDO_LIMIT, MIN_ZOOM, MAX_ZOOM, WHEEL_STEP, MIN_RECT_EDGE,
    HANDLE_VIEW_PX, EDGE_BAND_VIEW_PX, HOVER_CURSORS, SEL_FIT_RATIO,
    EDIT_FIT_RATIO, PIVOT_VIEW_PX, ROTATE_SNAP_DEG, ERASER_MIN,
    ERASER_MAX, ERASER_DEFAULT, TEXT_MIN, TEXT_MAX, TEXT_DEFAULT,
    TEXT_SWATCHES, TOOLS,
    CORNER_HANDLES, SIDE_HANDLES, SHEAR_HANDLES, PERSP_HANDLES, SHEAR_AT,
    SIDE_VIEW_PX, SHEAR_VIEW_PX, PERSP_VIEW_PX, PERSP_INSET_VIEW_PX,
    HANDLE_HIT_VIEW_PX, EDGE_HANDLE_MIN_VIEW_PX,
    INTERPOLATIONS, INTERPOLATION_DEFAULT, CLIPPINGS, CLIPPING_DEFAULT,
    DIRECTIONS, DIRECTION_DEFAULT, GUIDES, GUIDE_RATIOS, GUIDE_DEFAULT,
    CONSTRAIN_OPS, PIVOT_OPS, PREVIEW_OPACITY_DEFAULT, STEP_FLIP,
)
from .dialog import EDITOR_MIN_SIZE, EDITOR_SIZE, ImageEditorDialog
from .geometry import (
    clamp_rect, rotate_about, scale_about, shear_about, bake_transform,
    compose_transform, warp_placement,
    _image_has_alpha, transform_region, warp_region, quad_point,
    quad_to_quad_transform, flip_transform, center_crop_aspect,
    draw_text, _project_on_segment, _segment_hit,
    _dist_to_segment,
)
from .text_item import TextBlockItem

__all__ = [
    "UNDO_LIMIT", "MIN_ZOOM", "MAX_ZOOM",
    "WHEEL_STEP", "MIN_RECT_EDGE", "HANDLE_VIEW_PX",
    "EDGE_BAND_VIEW_PX", "HOVER_CURSORS", "SEL_FIT_RATIO",
    "EDIT_FIT_RATIO", "PIVOT_VIEW_PX", "ROTATE_SNAP_DEG",
    "ERASER_MIN", "ERASER_MAX", "ERASER_DEFAULT",
    "TEXT_MIN", "TEXT_MAX", "TEXT_DEFAULT",
    "TEXT_SWATCHES", "TOOLS", "EDITOR_SIZE",
    "CORNER_HANDLES", "SIDE_HANDLES", "SHEAR_HANDLES", "PERSP_HANDLES",
    "SHEAR_AT", "SIDE_VIEW_PX", "SHEAR_VIEW_PX", "PERSP_VIEW_PX",
    "PERSP_INSET_VIEW_PX", "HANDLE_HIT_VIEW_PX",
    "EDGE_HANDLE_MIN_VIEW_PX", "INTERPOLATIONS", "INTERPOLATION_DEFAULT",
    "CLIPPINGS", "CLIPPING_DEFAULT", "DIRECTIONS", "DIRECTION_DEFAULT",
    "GUIDES", "GUIDE_RATIOS", "GUIDE_DEFAULT", "CONSTRAIN_OPS", "PIVOT_OPS",
    "PREVIEW_OPACITY_DEFAULT", "STEP_FLIP",
    "EDITOR_MIN_SIZE", "clamp_rect", "rotate_about",
    "scale_about", "shear_about", "bake_transform",
    "compose_transform", "warp_placement",
    "_image_has_alpha", "transform_region", "warp_region", "quad_point",
    "quad_to_quad_transform", "flip_transform", "center_crop_aspect",
    "draw_text", "_project_on_segment",
    "_segment_hit", "_dist_to_segment", "wait_cursor",
    "_BakeWorker", "run_with_progress",
    "TextBlockItem", "EditorCanvas",
    "ImageEditorDialog",
]
