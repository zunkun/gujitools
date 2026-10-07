# -*- coding: utf-8 -*-
"""图片编辑弹窗：裁剪 / 擦除 / 插入文字（Win10 照片风格）。

从图片预览弹窗（``image_zoom_dialog``）的「编辑」按钮进入，编辑的是
**画布当前整分辨率图**（已含翻转/旋转）；「完成」后写回弹窗画布。宿主
给 ``save_back=True``（画布显示 1:1 对应真实文件）时，「完成」= 直接
**原子覆盖原图片文件**，并**先弹一次覆盖确认**（用户 2026-10-04 定的：
原图被覆盖后不可逆，必须让用户知道；见 :meth:`ImageEditorDialog.
_confirm_overwrite`）。虚拟预览（区域合成/打印重排/PDF 页）没有文件
可回写，维持"满意用「下载」落盘、翻页/关窗即丢弃"的旧行为，也**不弹**
确认框（不写盘的事不该假报警）。

五个工具的行为口径：

- **裁剪**：**默认选中整幅图**，沿四边/四角**任意位置**向内拖收边（整条
  边都是命中带，不只手柄小方块）、拖框中间移动；松手后**视图自动适配新
  选区**（选区变小就放大查看）。不做截图式"拖拽画框"——那是截图的交互，
  裁剪的语义是"从原图里收出想要的部分"（用户 20:05 定）。
- **变换**（GIMP「统一变换」口径，处理古籍褶皱/歪斜）：**默认选中整幅
  图**，拖角=缩放（Shift 等比）、拖边=切变、框内拖=移动、框外拖=**绕
  轴心旋转**（Shift 每 15° 吸附）；轴心圆点可拖动，「从轴心」勾选后
  缩放/切变也以轴心为锚。勾选「**调整范围**」后沿边拖动**收小要处理的
  区域**（收完自动回到变换模式）——小范围修褶皱就是"收小区域 → 旋转/
  切变把它正回来"。拖动即实时预览（原区域填白，变换后的内容以
  浮层显示）；「应用变换」（或切走工具/「完成」）才烘焙进像素——原
  区域填白、只把选区内容按仿射矩阵画回去，画布尺寸不变，**区域外的
  像素一动不动**。一批一个撤销点。
- **变形**（**PS 操控变形 Puppet Warp 口径**，处理古籍褶皱/卷曲/线段倾斜）：
  在图上**打图钉**（点一下放一个）→ 拖某个图钉，**它附近的内容跟着走、
  离得越远动得越少、没被钉住的远处几乎不动**（"像扯弹簧"/"像揉面团"）。
  - **加图钉**：工具激活时直接点图上的位置；点已有图钉附近＝选中它而不是
    新建（吸附半径 :data:`PIN_HIT_VIEW_PX`）。
  - **删图钉**：`Alt`+点，或右键点。
  - **图钉拖到图外**：允许（往外拉＝把那块内容往外拉伸），越界部分填底。
  - **网格疏密**：算法把图片切成三角网格，格距在选项行选（见
    :data:`MESH_DENSITY_CHOICES`）；越密越细腻、解方程越慢。
  - ⚠️ **边框自动锚定**：ARAP 能量对整体平移/旋转不变，只钉一个图钉时整张
    网格会"一起漂移"（实测每个顶点都平移 14px）。所以默认把**图片四边**
    视为固定（PS 的做法），拖内部图钉时边框被拉住，形变才收敛成"近处大、
    远处为零"（见 ``utils.puppet_warp.solve_puppet``）。
  - 拖动即实时预览（只算动过的网格凸包包围盒 + 按屏幕清晰度降采样，见
    :func:`cage_preview_scale`），松手补一帧更清楚的；「应用变形」（或切走
    工具/「完成」）才烘焙进像素（有等待光标）。
  - ⚠️ 「应用变形」后**图钉留在原地**（``adopt_pins``）：古籍褶皱往往要来回
    试几次，每次应用后都清空图钉的话用户得重新钉一遍。
  算法与口径见 ``utils/puppet_warp.py``。
  ⚠️ 进这个工具时图片**不铺满视口**（:data:`DEFORM_FIT_RATIO`），四周留白
  方便把图钉往图外拖。
- **擦除**：按住左键涂抹把污点**擦成白底**（古籍页面去污点就是涂白）；
  直径在选项行可调；光标处有**实圈指示**，直径恒等于实际擦除直径
  （所见即所擦）。一笔一个撤销点。
  （原「拉伸」与笔刷配色已按用户 2026-10-01 要求移除；同日按 GIMP
  变换笼方案重新实现为上面的「变形」。）
- **文字**：点击落点 → 画布上**就地输入**（光标可见，点已有块可继续
  编辑）→ 选项行可调字体 family / 字号 / **颜色选择器**（对整块即时
  生效，样式是段落属性，与手机作图App同口径）→ 鼠标悬停在文字上出现
  **边界虚线框**，按住拖动整块移动（虚线框跟随，松手即消失）→
  「插入文字」把块写进图片（切走工具或点「完成」时未插入的块也自动
  写入）。一个批次一个撤销点。

  选项行的字体下拉**以中文字体为主**、只带几个常用西文字体（系统字体库
  动辄两三百个族，全列出来反而找不到"仿宋"，见 `ui.fonts`）；颜色是
  **一个按钮**，常用色块收在它弹出的面板里（见 `ui.color_picker`）。

  ⚠️ 样式改动作用在"**当前样式块**"（``EditorCanvas.style_target_block``）
  上，而不是"场景焦点项"：选项行的控件（尤其 qfluentwidgets 的 Slider，
  它是 ``StrongFocus``）一被点击就会抢走键盘焦点，场景焦点项随之变 None，
  按焦点项找块的话**改字号/颜色全部落空**（用户 2026-10-01 报障）。

⚠️ 撤销栈存的是**整图快照**（QImage 写时复制在就地绘制时仍会共享底层数据，
必须 ``copy()``），上限 12 步——4000px 预览约 60MB/步，再多内存吃不消。
"""
from __future__ import annotations

from .bake import (
    wait_cursor, _BakeWorker, run_with_progress, _bake_cage_work,
    _bake_puppet_work
)
from .canvas import EditorCanvas
from .consts import (
    UNDO_LIMIT, MIN_ZOOM, MAX_ZOOM, WHEEL_STEP, MIN_RECT_EDGE,
    HANDLE_VIEW_PX, EDGE_BAND_VIEW_PX, HOVER_CURSORS, SEL_FIT_RATIO,
    EDIT_FIT_RATIO, PIVOT_VIEW_PX, ROTATE_SNAP_DEG, ERASER_MIN,
    ERASER_MAX, ERASER_DEFAULT, TEXT_MIN, TEXT_MAX, TEXT_DEFAULT,
    TEXT_SWATCHES, MESH_DENSITY_CHOICES, MESH_DENSITY_DEFAULT,
    DEFORM_FIT_RATIO, PIN_NODE_VIEW_PX, PIN_HIT_VIEW_PX,
    QUAD_HANDLE_VIEW_PX, QUAD_HIT_VIEW_PX, RECTIFY_RATIO_CHOICES,
    RECTIFY_RATIO_DEFAULT, DEFORM_PREVIEW_PIXELS,
    DEFORM_PREVIEW_SETTLE_PIXELS, DEFORM_PREVIEW_INTERVAL,
    CAGE_HANDLE_VIEW_PX, CAGE_HIT_VIEW_PX, CAGE_EDGE_BAND_VIEW_PX,
    CAGE_PREVIEW_PIXELS, CAGE_PREVIEW_SETTLE_PIXELS,
    CAGE_PREVIEW_INTERVAL, CAGE_FIT_RATIO, CAGE_DENSITY_CHOICES,
    CAGE_DENSITY_DEFAULT, TOOLS
)
from .dialog import EDITOR_MIN_SIZE, EDITOR_SIZE, ImageEditorDialog
from .geometry import (
    clamp_rect, rotate_about, scale_about, shear_about, bake_transform,
    _image_has_alpha, transform_region, bake_puppet,
    cage_preview_scale, draw_text, _project_on_segment, _segment_hit,
    _dist_to_segment
)
from .text_item import TextBlockItem

__all__ = [
    "UNDO_LIMIT", "MIN_ZOOM", "MAX_ZOOM",
    "WHEEL_STEP", "MIN_RECT_EDGE", "HANDLE_VIEW_PX",
    "EDGE_BAND_VIEW_PX", "HOVER_CURSORS", "SEL_FIT_RATIO",
    "EDIT_FIT_RATIO", "PIVOT_VIEW_PX", "ROTATE_SNAP_DEG",
    "ERASER_MIN", "ERASER_MAX", "ERASER_DEFAULT",
    "TEXT_MIN", "TEXT_MAX", "TEXT_DEFAULT",
    "TEXT_SWATCHES", "MESH_DENSITY_CHOICES", "MESH_DENSITY_DEFAULT",
    "DEFORM_FIT_RATIO", "PIN_NODE_VIEW_PX", "PIN_HIT_VIEW_PX",
    "QUAD_HANDLE_VIEW_PX", "QUAD_HIT_VIEW_PX", "RECTIFY_RATIO_CHOICES",
    "RECTIFY_RATIO_DEFAULT", "DEFORM_PREVIEW_PIXELS", "DEFORM_PREVIEW_SETTLE_PIXELS",
    "DEFORM_PREVIEW_INTERVAL", "CAGE_HANDLE_VIEW_PX", "CAGE_HIT_VIEW_PX",
    "CAGE_EDGE_BAND_VIEW_PX", "CAGE_PREVIEW_PIXELS", "CAGE_PREVIEW_SETTLE_PIXELS",
    "CAGE_PREVIEW_INTERVAL", "CAGE_FIT_RATIO", "CAGE_DENSITY_CHOICES",
    "CAGE_DENSITY_DEFAULT", "TOOLS", "EDITOR_SIZE",
    "EDITOR_MIN_SIZE", "clamp_rect", "rotate_about",
    "scale_about", "shear_about", "bake_transform",
    "_image_has_alpha", "transform_region", "bake_puppet",
    "cage_preview_scale", "draw_text", "_project_on_segment",
    "_segment_hit", "_dist_to_segment", "wait_cursor",
    "_BakeWorker", "run_with_progress", "_bake_cage_work",
    "_bake_puppet_work", "TextBlockItem", "EditorCanvas",
    "ImageEditorDialog",
]
