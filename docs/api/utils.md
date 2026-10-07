<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# utils API 参考

通用工具函数：几何、排序、图像 IO、PDF、YOLO

覆盖 25 个模块、11 个公开类、165 个公开函数/方法（生成于 2026-10-08）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`utils.box_draw`](#utilsbox_draw) | 0 | 8 |
| [`utils.box_geometry`](#utilsbox_geometry) | 2 | 15 |
| [`utils.cage_warp`](#utilscage_warp) | 0 | 11 |
| [`utils.color_utils`](#utilscolor_utils) | 0 | 2 |
| [`utils.file_utils`](#utilsfile_utils) | 0 | 4 |
| [`utils.font_scan`](#utilsfont_scan) | 0 | 4 |
| [`utils.font_setup`](#utilsfont_setup) | 3 | 11 |
| [`utils.fonts`](#utilsfonts) | 1 | 13 |
| [`utils.help`](#utilshelp) | 0 | 7 |
| [`utils.image_io`](#utilsimage_io) | 0 | 2 |
| [`utils.image_utils`](#utilsimage_utils) | 0 | 7 |
| [`utils.margin_utils`](#utilsmargin_utils) | 0 | 2 |
| [`utils.page_layout`](#utilspage_layout) | 2 | 13 |
| [`utils.path_utils`](#utilspath_utils) | 0 | 3 |
| [`utils.pdf_draw`](#utilspdf_draw) | 1 | 9 |
| [`utils.pdf_extract`](#utilspdf_extract) | 0 | 9 |
| [`utils.pdf_stream`](#utilspdf_stream) | 1 | 2 |
| [`utils.perspective`](#utilsperspective) | 0 | 12 |
| [`utils.proc_utils`](#utilsproc_utils) | 0 | 1 |
| [`utils.puppet_warp`](#utilspuppet_warp) | 0 | 15 |
| [`utils.sort_utils`](#utilssort_utils) | 0 | 2 |
| [`utils.string_utils`](#utilsstring_utils) | 0 | 3 |
| [`utils.transparent_png`](#utilstransparent_png) | 0 | 2 |
| [`utils.units`](#utilsunits) | 0 | 2 |
| [`utils.yolo_utils`](#utilsyolo_utils) | 1 | 6 |

---

## `utils.box_draw`

源码：[`utils/box_draw.py`](../../utils/box_draw.py)

File: utils/box_draw.py
在图片上绘制检测框标注（供 CLI `detect --save` 与 GUI 预览共用）。

**为什么放在 utils**：CLI 的 `guji detect --save` 要把内容框画到图片上落地，
GUI 的预览控件也要画同样的框。配色与命名必须一致，否则「命令行看到的」
和「界面看到的」是两套东西。因此视觉约定集中在这里：

- 左框 `#21c178`（绿）、右框 `#3b82f6`（蓝）、合并框 `#f59e0b`（琥珀）；
- 整幅内容框（fullcontent，单框整页）`#4F46E5`（靛蓝）——深蓝紫，压在米黄
  纸页上醒目；与前三色区分干净（2026-09-29 用户选定，此前朱砂红被否）。
- 标注文字为「左框 (x1,y1,x2,y2)」。

**中文字体**：OpenCV 的 `putText` 不支持中文（会画成 `????`），因此文字用
PIL 绘制。字体候选路径来自 `utils.fonts`（Windows/Linux/macOS 三份候选 +
`GUJI_CJK_FONT` 逃生口，见那里的说明——**别在本文件再写一遍**）；全部缺失
时退化为 ASCII 标签（`L` / `R` / `U`），保证任何环境下都不会崩。

### 模块常量

| 名称 | 值 |
| --- | --- |
| BOX_NAME_FULL | `"整幅"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `box_kind_name(kind: str) -> str` | 类型键 → 中文名称（``"left"`` → 「左框」）；未知键原样返回。 |
| `reset_font_cache() -> None` | 清空字体探测缓存（`GUJI_CJK_FONT` 改指向后需要重探测）。 |
| `find_cjk_font() -> Optional[str]` | 返回可用的中文字体路径；都没有则返回 None。结果会缓存。 |
| `box_color(index: int) -> Tuple[int, int, int]` | 按框序号取 BGR 颜色。 |
| `box_name(index: int) -> str` | 按框序号取中文名（左框/右框/合并框）。 |
| `draw_boxes(img_bgr, boxes: Sequence[Optional[Sequence[int]]], thickness: int=4, show_label: bool=True, color=None, names: Optional[Sequence[str]]=None, colors: Optional[Sequence[Tuple[int, int, int]]]=None)` | 在图像上绘制一组框（原地绘制并返回新图，不修改入参）。 |
| `slot_names_colors(slots)` | **槽位**表示 → 与 ``slots`` 等长的 ``(names, colors)``（BGR）。 |
| `draw_slots(img_bgr, slots, thickness: int=4, show_label: bool=True)` | 在图像上绘制**槽位**表示的框（标注外观由 :func:`slot_names_colors` 定）。 |

#### `draw_boxes(img_bgr, boxes: Sequence[Optional[Sequence[int]]], thickness: int=4, show_label: bool=True, color=None, names: Optional[Sequence[str]]=None, colors: Optional[Sequence[Tuple[int, int, int]]]=None)`

在图像上绘制一组框（原地绘制并返回新图，不修改入参）。

参数:
    img_bgr: BGR 图像数组。
    boxes: 框列表，每项为 ``(x1, y1, x2, y2)``；``None`` 项被跳过
        （用于「只检出一侧」的常见情形，保持左右序号不串位）。
    thickness: 线宽（像素）。会随图像尺寸自适应放大，避免大扫描图上
        细线看不清。
    show_label: 是否绘制「左框 (x1,y1,x2,y2)」这类标注。
    color: 指定线条颜色 (B,G,R)；None 时按框序号取默认色。
    names: 与 boxes 按序号对齐的名称覆盖；``None`` 项回退到默认名。
        用于把整幅内容框标成「整幅」而不是「左框」。
    colors: 与 boxes 按序号对齐的颜色覆盖；``None`` 项回退到默认色。
        优先于 ``color``（`color` 是"全部同色"的简写）。

返回:
    绘制后的 BGR 图像（新数组）。

#### `slot_names_colors(slots)`

**槽位**表示 → 与 ``slots`` 等长的 ``(names, colors)``（BGR）。

这是"槽位 → 标注外观"的**唯一实现**，两处调用方共用：

- ``functions.detect`` 的 ``--save`` 标注图；
- 独立「检测文本框」模块页的「导出标注图」。

⚠️ 规则按**槽位**给，不按"过滤掉空项后的第几个框"：槽数就是形态
（半幅恒 2 槽 ``[左, 右]``、整幅 1 槽 ``[整幅]``，见
:mod:`utils.box_geometry`）。按序号给会让"只检出一侧"的那一页把左框
标成"第 1 号框"，也会把整幅标成左框。

``None`` 项原样占位（``draw_boxes`` 会跳过它，GUI 侧则按位置对齐），
这样"哪一侧缺失"的信息不丢。

#### `draw_slots(img_bgr, slots, thickness: int=4, show_label: bool=True)`

在图像上绘制**槽位**表示的框（标注外观由 :func:`slot_names_colors` 定）。

与 :func:`draw_boxes` 的区别只有一处，但很关键：调用方手上是**槽位**
（可能含 ``None``、长度 1 或 2，形态信息就在里面），不该自己拆成
``[left, right, full]`` 再逐个传名/配色——那份拆法在
``functions/detect`` 与 desktop 之间各写过一次，已经漂移过一次。

返回绘制后的 BGR 图像（新数组，不修改入参）。

---

## `utils.box_geometry`

源码：[`utils/box_geometry.py`](../../utils/box_geometry.py)

文本框几何规则：border 解析、最终裁剪框计算与输出画布布局。

本模块无重依赖（不导入 cv2/numpy/Qt），供 CLI functions、desktop worker 与
GUI 主进程共用，保证 detect 预览画出的"最终大框"与 crop 实际切割区域
完全一致。

坐标系均为原始图片像素坐标 [x1, y1, x2, y2]。

**布局层（build_output_layout / build_symmetric_layout）** 是 area/border
规则的唯一实现：它只做纯整数算术（画布多大、每块内容贴在哪），把结果表达为
`OutputLayout`。渲染后端由调用方决定——CLI 侧用 numpy 画，GUI 侧用 QImage 画。
这样同一套规则不会因数像素后端不同而被复制成两份。

⚠️ 曾有一处真实分歧：GUI 侧在 area=3 + 双框 + border=None 时把并集区域
搬到了画布左上角，而规格要求"ROI 写回原位置"（见
docs/functions/cropremove.md:57）。布局层统一后该分歧由本模块消除。

### 模块常量

| 名称 | 值 |
| --- | --- |
| SYMMETRIC_GAP_MM | `10` |
| PAGE_CLASS_FULLCONTENT | `"fullcontent"` |
| PAGE_CLASS_HARFCONTENT | `"harfcontent"` |
| PAGE_CLASS_SINGLE | `"single"` |
| PAGE_CLASS_EMPTY | `"empty"` |

### `class Canvas`

一张输出画布及其内容落点。

属性:
    size: (宽, 高)，画布像素尺寸。
    sources: [(源框, 目标x, 目标y), …]。源框用原始图片坐标
        (x1, y1, x2, y2)；目标坐标是它在画布中的左上角落点。
        源框与目标框尺寸相同（1:1 粘贴，不缩放）。
    suffix: 文件名后缀（area=1 逐框输出时为 "-l"/"-r"，否则空串）。

### `class OutputLayout`

一次处理的完整输出布局。

属性:
    canvases: 按输出顺序排列的画布列表。
    full_page: 是否使用整页尺寸画布（无 border 时）。调用方据此决定
        画布底色以外的处理方式。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `is_full_content(boxes) -> bool` | ``boxes`` 是否为「整幅内容」(fullcontent) 的**槽位表示**。 |
| `page_box_slots(left, right, full) -> List[Optional[list]]` | 三类框 → **槽位表示**（槽位约定的**唯一实现**）。 |
| `page_box_slots_from_event(payload) -> List[Optional[list]]` | ``page_boxes`` 事件负载 → **槽位表示**（坐标一律转 int）。 |
| `classify_page_slots(slots) -> str` | 页的**槽位**表示 → 页形态分类键（四类见 `PAGE_CLASS_*` 常量）。 |
| `half_sides(boxes, image_size) -> List[str]` | 半幅(harfcontent)页的框 → 每个框的侧别 ``"left"`` / ``"right"``。 |
| `half_slots(boxes, image_size) -> List[Optional[list]]` | 半幅页的框 → **2 槽** ``[左, 右]``（缺失侧 ``None``）。 |
| `whole_page_box(image_size) -> List[int]` | 整页框 ``[0, 0, W, H]``——「整页只有一个内容区」时的唯一内容区表示。 |
| `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]` | 解析 border 参数（毫米单位），按 DPI 转换为像素。 |
| `compute_final_boxes(boxes, area: int, border_mm, dpi: int=300) -> List[List[int]]` | 按 crop 命令的 area/border 规则计算最终切割框（原始图片坐标）。 |
| `build_output_layout(boxes: Sequence[Sequence[int]], area: int, border_padding, image_size: Tuple[int, int], dpi: int=300, sides: Optional[Sequence[Optional[str]]]=None, symmetric: bool=False) -> OutputLayout` | 按 area/border 规则计算输出画布布局（area=1 / 2 / 3）。 |
| `build_symmetric_layout(box: Sequence[int], border_padding, image_size: Tuple[int, int], is_left: bool=True, dpi: int=300) -> OutputLayout` | 单框对称输出布局：实际框 + 空白镜像 + 中间间隔。 |
| `present_boxes(slots) -> List[list]` | 槽位 → **非空**框列表（保留顺序）。 |
| `set_box_full(slots, index: int) -> List[Optional[list]]` | 把第 ``index`` 个框设为「整幅」→ **单槽** ``[整幅]``，其余框丢弃。 |
| `set_box_half(slots, index: int, image_size) -> List[Optional[list]]` | 把第 ``index`` 个框设为「半幅」→ **2 槽** ``[左, 右]``（按中心定左右）。 |
| `drop_box(slots, index: int, image_size) -> List[Optional[list]]` | 删掉第 ``index`` 个框后的**新槽位**。 |

#### `is_full_content(boxes) -> bool`

``boxes`` 是否为「整幅内容」(fullcontent) 的**槽位表示**。

槽位约定见 `functions/detect.PageBoxes`：
- 半幅（harfcontent）固定 2 槽 ``[左, 右]``，缺失一侧为 None；
- 整幅（fullcontent）只占 **1 槽** ``[整幅]``。

据此判断 area=2/3 的单框要不要做对称镜像——整幅框已近页宽，
镜像会凭空多出一半空白，**不做**镜像（这是整幅在合成层唯一的特殊行为，
区域本身随框走）；半幅漏检一侧才需要镜像补白。

⚠️ 槽数**不是**"有几个框"，而是**形态**：半幅恒 2 槽（`half_slots` 保证），
整幅恒 1 槽。半幅删剩一侧后仍然写回 2 槽（另一侧 None），否则会被误判成整幅。

#### `page_box_slots(left, right, full) -> List[Optional[list]]`

三类框 → **槽位表示**（槽位约定的**唯一实现**）。

半幅优先于整幅：只要有左或右就按半幅出 **2 槽** ``[左, 右]``（缺失侧
``None``）；否则整幅只占 **1 槽** ``[整幅]``；都没有则空表。

半幅优先是既有明文规则（原 ``PageBoxes.slots``）：万一两类同时存在
（互斥消解失灵 / 手工构造的防御场景），按半幅处理——保证 harfcontent 逻辑
与原来完全一致，整幅不会把已检出的半幅挤掉。正常数据下两者不可兼得
（见 ``functions.detect.PageBoxes.conflict``）。

调用方两处，共用本函数以免"同一件事两处定义"而漂移：
``functions.detect.PageBoxes.slots``（对象侧）与
:func:`page_box_slots_from_event`（事件侧）。

#### `page_box_slots_from_event(payload) -> List[Optional[list]]`

``page_boxes`` 事件负载 → **槽位表示**（坐标一律转 int）。

``page_boxes`` 是检测结果跨进程 / 跨线程回传的**唯一通道**，负载形如::

    {"image": stem, "left": [...] | None,
     "right": [...] | None, "full": [...] | None}

（见 ``functions.detect.DetectFunction._report_boxes``）。任务流程第二步与
独立「检测文本框」模块页都从这里还原形态，不再各写一遍槽位拼装。

⚠️ 本模块（utils）**不 import functions**——分层是单向的
``utils ← core ← {cli, functions, desktop}``，反过来引用会被
``tests/selftests/layering.py`` 判违规。所以这里只按负载里的三个键出槽位，
不去构造 ``functions.detect.PageBoxes``：两侧共用的是**规则**
（:func:`page_box_slots`），不是类型。

#### `classify_page_slots(slots) -> str`

页的**槽位**表示 → 页形态分类键（四类见 `PAGE_CLASS_*` 常量）。

分类依据是槽位形态（与 `is_full_content` 同一条约定）：
- 无任何框 → 无文本框；
- 单槽且非空 → 整幅(fullcontent)；
- 双槽全有 → 半幅(harfcontent)；双槽缺一侧 → 单独页（半幅单栏）。

⚠️ 参数必须是**槽位**表示（半幅恒 2 槽、整幅 1 槽，见 `half_slots`），
不是"过滤掉 None 后还剩几个框"——过滤后单独页会误判成整幅。

#### `half_sides(boxes, image_size) -> List[str]`

半幅(harfcontent)页的框 → 每个框的侧别 ``"left"`` / ``"right"``。

规则（用户 2026-09-29 定）**只在本函数实现一处**，GUI 预览的命名/配色与
入库的槽位组装都调它：

- 只有 1 个框：中心 ``cx < 图宽/2`` → 左，否则 → 右（按**位置**判，不看大小）；
- 多个框：按中心 ``cx`` 升序，**最靠左的那个归左**，其余归右——这样把框
  拖过中线时两侧身份自然互换，也不会出现"两个框都想要左槽"。

⚠️ **半幅的左右是位置决定的**（移动/缩放后会重新判定）；与位置无关的显式
类型只有整幅(fullcontent)，由用户在第二步「选中框类型」里选择——那条路
**不经过本函数**（见 :func:`whole_page_box` 与 ``is_full_content``）。

参数:
    boxes: 框列表（原始图片坐标）；空项自动跳过。
    image_size: 原图 (宽, 高)，用于取中线。

返回:
    与 ``boxes``（去掉空项后）等长的侧别字符串列表。

#### `half_slots(boxes, image_size) -> List[Optional[list]]`

半幅页的框 → **2 槽** ``[左, 右]``（缺失侧 ``None``）。

⚠️ 恒为 2 槽是**关键**：``is_full_content`` 靠槽数区分两种形态（整幅 = 1 槽）。
半幅只要漏检/删剩一侧就退化成 1 槽，那个框就会被当成「整幅」——这正是
"删掉整幅框后，右边的框自动变成了整幅" 的根因（用户 2026-09-29 报）。

#### `whole_page_box(image_size) -> List[int]`

整页框 ``[0, 0, W, H]``——「整页只有一个内容区」时的唯一内容区表示。

两处用它，语义相同——都表示"保留整页内容"：

- ``area=4``（整页模式：不检测，整页即唯一文本框）；
- **整幅内容(fullcontent)页 + area=4**：保留框外内容 → 框归一成整页。

整幅页在 area=1/2/3 下**不再**用整页框（用户 2026-09-29 改定）：整幅框
本质是"大一点的单独内容框"，框原样下传，area 1/2/3 统一按 area=3 的
合并语义走单框布局（见 ``preview_worker.region_canvas_specs``）。

CLI（`functions/text_region`）与 GUI（`preview_worker.region_canvas_specs`）
共用本函数，避免各自造 [0,0,W,H]。

#### `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]`

解析 border 参数（毫米单位），按 DPI 转换为像素。

与 `parse_border` 的写法规则相同，但最终值经过 mm→px 换算。
换算公式: px = mm × dpi / 25.4（25.4mm = 1inch）。

返回 [top, right, bottom, left] 像素列表，或 None。

#### `compute_final_boxes(boxes, area: int, border_mm, dpi: int=300) -> List[List[int]]`

按 crop 命令的 area/border 规则计算最终切割框（原始图片坐标）。

与 functions/text_region.py 的切割逻辑一致：
- area=1：每个框各自外扩 border，输出多张图（-l/-r）；
- area=2/3：两框取并集后外扩 border，输出一张大图；
  单框时为对称输出，实际内容区域即该框外扩 border。

参数 boxes 为检测框列表（[左框, 右框]，缺失的已剔除）。

#### `build_output_layout(boxes: Sequence[Sequence[int]], area: int, border_padding, image_size: Tuple[int, int], dpi: int=300, sides: Optional[Sequence[Optional[str]]]=None, symmetric: bool=False) -> OutputLayout`

按 area/border 规则计算输出画布布局（area=1 / 2 / 3）。

与 functions/text_region.py 的 `_build_output` 及
desktop/workers/preview_worker.compose_region_output 的几何完全等价，
差异已在本模块内统一（area=3 + border=None 一律"写回原位置"）。

参数:
    boxes: 检测框列表（原始图片坐标）。area=3 且两框齐全时内部自动取并集。
    area: 区域模式 1/2/3。
    border_padding: [top, right, bottom, left] 像素，或 None。
    image_size: 原图 (宽, 高)，无 border 时画布取其尺寸。
    dpi: 边框换算 DPI（仅用于对称输出的 gap）。
    sides: area=1 时每个框的来源侧（"left"/"right"/None），用于生成
        "-l"/"-r" 后缀与保持输出顺序。
    symmetric: 单框 + border 时是否走**对称输出**（实际框 + 空白镜像）。
        True 对应 `_build_symmetric_output`（area=2/3 且检测到单框）；
        False 表示普通单框布局（含 area=3 合并后的单框）——此时画布
        就是「框 + border」，不做镜像。

返回:
    OutputLayout。调用方按 canvases 顺序渲染并保存。

#### `build_symmetric_layout(box: Sequence[int], border_padding, image_size: Tuple[int, int], is_left: bool=True, dpi: int=300) -> OutputLayout`

单框对称输出布局：实际框 + 空白镜像 + 中间间隔。

与 `build_output_layout` 的单框分支同规则，区别是显式给出实际框在左
还是在右（`is_left=False` 时内容置于右半）。

参数:
    box: 实际检测框（原始图片坐标）。
    border_padding: [top, right, bottom, left] 像素（不可为 None）。
    image_size: 原图 (宽, 高)，仅用于无 padding 时的兜底。
    is_left: 实际框位于左半（True）还是右半（False）。
    dpi: gap 换算 DPI。

返回:
    OutputLayout（单一画布）。

#### `present_boxes(slots) -> List[list]`

槽位 → **非空**框列表（保留顺序）。

下游所有"第 index 个框"都按这个列表的下标算：界面上的框列表、命中检测、
选中下标全都是过滤后的口径，混用槽位下标会选错框（半幅缺左侧时，
槽位 0 是 ``None``、槽位 1 才是右框）。

#### `set_box_full(slots, index: int) -> List[Optional[list]]`

把第 ``index`` 个框设为「整幅」→ **单槽** ``[整幅]``，其余框丢弃。

⚠️ 整幅与半幅互斥、一页只能一个框，所以这个转换**必然丢掉其它框**。
调用方**必须先与用户确认**（任务流程第二步弹 Dialog，模块页弹确认框），
不要静默调用。

``index`` 越界时原样返回（空表则返回空表）——非法输入不该让界面崩。

#### `set_box_half(slots, index: int, image_size) -> List[Optional[list]]`

把第 ``index`` 个框设为「半幅」→ **2 槽** ``[左, 右]``（按中心定左右）。

整幅页的框也能是半幅（漏检一侧的情形），所以这个方向**无损**：一个框
照样按它自己的中心位置落进左槽或右槽，另一侧留 ``None``。

#### `drop_box(slots, index: int, image_size) -> List[Optional[list]]`

删掉第 ``index`` 个框后的**新槽位**。

- 半幅页：仍写回 **2 槽**（缺失侧 ``None``）——删到只剩一个框时形态不会
  从半幅变成整幅，这正是用户报过的"删掉整幅框后右边的框自动变成整幅"；
- 整幅页 / 删光了：空表（整幅只有 1 槽，删掉没有"别的框"可剩）。

---

## `utils.cage_warp`

源码：[`utils/cage_warp.py`](../../utils/cage_warp.py)

变换笼（cage transform）：拖笼上的把手 → **局部**光滑形变。

口径（2026-10-01 用户定）
------------------------
- 笼是一圈**把手**（节点）。拖哪个把手，只有它**附近**的像素跟着走，
  远处的像素**逐字节一动不动**。
- 影响随距离平滑衰减到 0（"像扯弹簧"：作用点变化大，远端几乎不动），
  而且是 **C² 光滑**的——不会沿笼边拉出生硬的折痕。
- 向内拖＝压缩，向外拖＝拉伸，两个方向都行。
- ⚠️ 与 GIMP 原版的差别：GIMP 的笼是"**笼内整体一起走**"（全局 Green
  Coordinates / MVC），拖一个角会把整笼带动、从其余顶点拉出折痕。本项目
  按用户要求改成**局部**影响（2026-10-01 用户反馈："选择一点向内拖会从
  其他节点生出折线……应该尽可能影响局部，尽量少影响距离远的节点"）。

算法：紧支撑 RBF 位移场
----------------------
把每个**被拖过的**把手当作一个约束点：目标位置 ``mᵢ`` 处的像素要取源位置
``hᵢ`` 的像素，即位移 ``qᵢ = hᵢ − mᵢ``。取 **Wendland** 核

    φ(r) = (1 − r)⁴ (4r + 1)   (r < 1)，  核外恒为 0

插值：``s(p) = p + Σⱼ wⱼ φ(|p − mⱼ| / R)``，``w`` 由 ``Φw = q`` 解出
（``Φᵢⱼ = φ(|mᵢ − mⱼ|/R)``，把手数 ≤ 十几个，小线性方程组微秒级）。

四条性质是"手感"与"可断言"的关键，都有自测钉死：

1. **精确插值**：``s(mᵢ) = hᵢ``——把手处的像素严格跟着把手走。
2. **紧支撑 ⇒ 局部**：``|p − mⱼ| ≥ R`` 时 ``φ ≡ 0``，于是 ``s(p) = p``，
   影响半径外**逐字节等于原图**。这就是"拖一个点只动附近"的来源。
3. **只有被拖过的把手进方程组**：没动过的把手（含"在笼线上新加的点"）
   不构成约束，所以**加点仍然逐字节中性**。
4. **恒等即原图**：所有把手都没动 ⇒ 直接 return 原数组的副本。

``R``（影响半径）由 :func:`influence_radius` 决定：取用户给的半径，再抬到
**保证位移场不折叠**的下限——位移场梯度量级是 ``|φ'|max·Σ|wⱼ| / R``，超过 1
就会自交（实测表现为"漩涡"）。半径过小 + 拖得过远必然自交，这条下限把
它挡在门外；越界的请求会被**自动放宽半径**，宁可影响大一点也不能出乱纹。

性能
----
与全局 MVC 不同，**工作区域只有影响半径那么大**：整页 4000×3000 的图拖一个
把手，也只算 ``(2R)²`` 那一小块。瓶颈始终是**逐像素重采样**，不是求场
（稀格求场恒在毫秒级）——实测拆解（本机 2026-10-01，整页 4000×3000）：

=================  ==========
源坐标场（稀格）      <5ms
场采样到全分辨率     1.2s
双线性取样           1.9s
**合计**            **3.1s**
=================  ==========

所以桌面侧仍然**降分辨率出预览**（``image_editor.cage_preview_scale``）、
只在落地时走全分辨率；而局部影响让"要算的面积"从整幅缩到半径平方，
预览几乎必然跟手。

落地（全分辨率）这一步在**大图上仍是秒级到分钟级**，直接同步跑会把 GUI
主线程钉死（用户 2026-10-01 报"卡死/崩溃"）。为此：

- :func:`deform` / :func:`deform_qimage` 支持 ``bounds``（只算影响框、返回
  裁好的图，框外逐字节不动 ⇒ 画布直接透底图）与 ``progress``（每个分块回调
  ``progress(done, total)``，返回 ``False`` 即中止、函数返回 ``None``）；
- 画布侧（``image_editor.run_with_progress``）把落地丢进**后台线程**并显示
  进度对话框，主线程保持响应、可取消。

几何约定
--------
- 全部用**图片像素坐标**，y 向下（与 QImage 一致）；像素中心取整数坐标。
- ``cage_src`` = 把手原位，``cage_dst`` = 把手当前位置；两序列**一一对应**，
  闭合顺序，顺/逆时针都可以。

⚠️ numpy 一律**延迟导入**：桌面主进程要 import 本模块（只为拿函数引用），
启动路径不能因此背上 numpy 的加载成本。

### 模块常量

| 名称 | 值 |
| --- | --- |
| FIELD_MAX | `40000` |
| COINCIDENT | `1e-06` |
| _COINCIDENT_REL | `0.001` |
| _RADIUS_FLOOR | `2.5` |
| _RADIUS_DIVERGE | `10000.0` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `perimeter_cage(rect, per_side: int=2)` | 矩形 ``rect`` = ``(x0, y0, x1, y1)`` → **沿周长均匀取样**的闭合把手序列。 |
| `wendland(r)` | Wendland **C²** 紧支撑核：``r < 1`` 时 ``(1−r)⁴(4r+1)``，否则 ``0``。 |
| `influence_radius(cage_src, cage_dst, influence=None) -> float` | 当前这组拖动需要的**影响半径**（用户下限 + 防自交下限），没动过则 0。 |
| `moved_handles(cage_src, cage_dst, influence=None)` | 把"被拖过的把手"整理成 ``(把手当前位置, RBF 权重, 影响半径)``。 |
| `warp_region(cage_src, cage_dst, influence=None, *, width: int, height: int)` | 这次拖动**实际会改动的矩形区域**（图片坐标，开区间右端）。 |
| `content_region(cage_src, cage_dst, influence=None, *, width: int, height: int)` | 形变后**内容占用的矩形范围**（图片坐标，开区间右端）——**不夹进画布**。 |
| `cage_moved(cage_src, cage_dst, epsilon: float=1e-06) -> bool` | 两个笼是否有实质差别（区分"真变形"与"动过手但没挪"）。 |
| `deform(src, cage_src, cage_dst, *, influence=None, fill=FILL, step: int \| None=None, block: int=BLOCK_PIXELS, bounds=None, grow: bool=False, progress=None)` | 按「把手 ``cage_src`` → 把手 ``cage_dst``」形变 ``src``。 |
| `qimage_to_rgba(image)` | QImage → ``(H, W, 4)`` uint8 **RGBA**（ARGB32 在小端机器上是 B,G,R,A）。 |
| `array_to_qimage(rgb)` | ``(H, W, 3\|4)`` uint8 → QImage（ARGB32）；3 通道按不透明处理。 |
| `deform_qimage(image, cage_src, cage_dst, *, influence=None, fill=None, bounds=None, grow=False, progress=None)` | QImage 版 :func:`deform`（**保留 alpha 通道**）。 |

#### `perimeter_cage(rect, per_side: int=2)`

矩形 ``rect`` = ``(x0, y0, x1, y1)`` → **沿周长均匀取样**的闭合把手序列。

``per_side`` = 每条边分成几段。1 → 只有四个角；2 → 四角 + 四边中点（8 点）。

沿周长取样是为了得到一圈"绳子"上均匀的**结**：把手只在周长上，拖动
某个结时它的邻居距离一致，手感均匀。内部再多铺点也不会算错（算法只用
把手位置，不看多边形形状），只是没必要。

#### `wendland(r)`

Wendland **C²** 紧支撑核：``r < 1`` 时 ``(1−r)⁴(4r+1)``，否则 ``0``。

选它而不是高斯：高斯处处非零（影响永远不为 0，"局部"就成了近似），
紧支撑才让"半径外逐字节不动"成为**可断言**的性质；而多项式形式没有
指数运算，在几十万格点上比高斯还便宜。

#### `influence_radius(cage_src, cage_dst, influence=None) -> float`

当前这组拖动需要的**影响半径**（用户下限 + 防自交下限），没动过则 0。

单独暴露出来是为了让画布知道"该重算多大一块"——省得为了拿一个数字
把整张图跑一遍。

#### `moved_handles(cage_src, cage_dst, influence=None)`

把"被拖过的把手"整理成 ``(把手当前位置, RBF 权重, 影响半径)``。

没动过（或两个笼形状不一致）→ ``None``。**只有真的动过的把手**进方程
组，所以"在笼线上加一个点"不会改变形变（自测有这个断言）。

⚠️ **退化一律退化为恒等**（返回 ``None``），绝不把异常抛给调用方：
方程组在把手重合等退化配置下无解（见 :func:`_drop_coincident`），
异常一旦冒到 Qt 槽函数就是崩溃——而"这一帧不变形"完全可接受
（用户下次把把手分开一点就行）。口径与 ``solve_puppet`` 的
"解算失败退化为恒等"一致。

#### `warp_region(cage_src, cage_dst, influence=None, *, width: int, height: int)`

这次拖动**实际会改动的矩形区域**（图片坐标，开区间右端）。

画布侧的预览浮层就贴在这个框上（框外逐字节等于原图，直接透出底图即可，
既不浪费也不会有接缝）。纯 Python + numpy 基础运算，不加载重型依赖。

#### `content_region(cage_src, cage_dst, influence=None, *, width: int, height: int)`

形变后**内容占用的矩形范围**（图片坐标，开区间右端）——**不夹进画布**。

用户 2026-10-02 报：「图片倾斜后一部分区域超出原本边界，现在会被截掉，
不对；超出原本区域的**不要截**，最终结果要按最后图片的范围。」

口径（用户同日的补充）：「一切以新图为准，新图什么样就什么样，老图不要
了」——最终画布 = **形变后内容的完整外框**，不是"原图 ∪ 形变后"的松散
并集。对变换笼来说，"内容"分两块：

① **没碰到的内容**：RBF 是紧支撑的，影响半径外的像素逐字节不变，仍老实
   待在 ``[0, W] × [0, H]`` 里——这块必须原样留全（它**就是**结果的一
   部分，不是"老图残留"）；
② **被拖走的把手附近的源内容**：它跟着把手走。位移场是后向的，所以不能
   正推落点，但 ``s(mᵢ) = hᵢ``（把手处内容严格跟着把手），于是把手落点
   ``mᵢ`` 就是这块内容的"锚点"。

因此画布 = ``[0, W] × [0, H]`` ∪ ``bbox(被拖把手的落点)``。

⚠️ **不要**再叠加影响半径 ``R``：``R`` 是 RBF 解算出来的**位移场**尺度
（可能远大于实际位移），不是"内容向外铺开的距离"。把 ``mᵢ ± R`` 并进
来会让**向内**拖把手也凭空外扩几十像素（实测拖 25px 却外扩 64px），
画布白白变大、四边多出一圈空白——正是用户要消掉的"老图残留"。

返回 ``(x0, y0, x1, y1)``；没动过 → 原图边界 ``(0, 0, W, H)``。

#### `deform(src, cage_src, cage_dst, *, influence=None, fill=FILL, step: int | None=None, block: int=BLOCK_PIXELS, bounds=None, grow: bool=False, progress=None)`

按「把手 ``cage_src`` → 把手 ``cage_dst``」形变 ``src``。

**默认**（``grow=False``）返回**同尺寸**新数组；``grow=True`` 返回
**放大后**的新数组 + 其原点偏移，让"被拖出原边界的内容"**不被截掉**
（见 :func:`deform_qimage` 的返回值说明与用户 2026-10-02 报障）。

逐像素语义：

1. 落在**影响半径内** → 按位移场反查源坐标、双线性采样（内容跟着把手走）；
2. 半径外 → **原样不动**（位移场在那里恒等于 0，见模块文档「算法」）；
3. 采样点超出**源图** → 填 ``fill``（小端 RGBA 时给 4 元组）。
   ⚠️ 与 ``grow`` 无关：填的是"源图之外"，不是"原边界之外"——内容被
   拖到原边界外时，它的**源坐标仍在源图内**，所以照常取到真实像素。

``src`` 支持 (H, W) 与 (H, W, C)。``influence`` 是影响半径（图片像素，
缺省由位移量自动定，见 :func:`moved_handles`）；``step`` 是位移场的格距
（缺省按 :data:`FIELD_MAX` 自适应）；``bounds`` 可显式指定处理范围。

``progress`` 给定时在**每个分块**后回调 ``progress(done, total)``
（``total`` = 要处理的像素总数）；返回 ``False`` 则**提前中止**并返回
``None``（让长任务能被打断，见画布侧的大图烘焙）。

返回：``grow=False`` → ``out``（同尺寸 ndarray）；``grow=True`` →
``(out, (ox, oy))``（``out`` 是新画布，``(ox, oy)`` = 新画布左上角在
旧坐标系里的位置，可为负）。

#### `qimage_to_rgba(image)`

QImage → ``(H, W, 4)`` uint8 **RGBA**（ARGB32 在小端机器上是 B,G,R,A）。

⚠️ 必须把 alpha 带上。桌面侧编辑的常常是第三步产物"**白底透明 PNG**"：
透明像素的 RGB 分量存的是 0，一旦只取 RGB 丢掉 alpha，整片背景就读成
**黑色**（用户 2026-10-01 报的"变形后图片变成黑色"就是这个）。

#### `deform_qimage(image, cage_src, cage_dst, *, influence=None, fill=None, bounds=None, grow=False, progress=None)`

QImage 版 :func:`deform`（**保留 alpha 通道**）。

⚠️ 返回类型是**多形态**的（``None`` / ``QImage`` / ``(QImage, (ox, oy))``），
刻意不加注解：不加时类型检查器只会看到 Unknown，调用点解包不会报错；
一旦标成联合类型，``preview, origin = deform_qimage(...)`` 这种解包就会因
"QImage 不可迭代"而报错。见 image_editor.bake_transform 的同款说明。

不透明图走 3 通道（比 4 通道少 1/4 的采样量）；带 alpha 的图走 4 通道，
越界填充取 :data:`FILL_CLEAR`（白 + 透明），免得透明底变实心。

``bounds`` = ``(x0, y0, x1, y1)``（图片坐标，开区间右端）时**只算这块**
并返回**裁剪后的图**（左上角 = 框左上角）——画布侧预览就靠它把工作量
从整幅缩到影响框（框外逐字节等于原图，直接透底图即可）。``None``（默认）
返回整幅同尺寸结果。``bounds`` 与 ``grow=True`` 同时给：``bounds`` 仍
作为"要重算哪块"的提示，最终返回的是**放大的整幅**（不裁剪）。

``grow=True``：用户 2026-10-02 报障的修复——内容被拖出原边界时**不截**，
按 :func:`content_region` 放大画布，返回 ``(QImage, (ox, oy))``，
``(ox, oy)`` = 新图左上角在原图坐标系里的位置（可为负）。``grow=False``
（默认）返回单个 ``QImage``，与原行为逐字节一致。

``progress`` 透传给 :func:`deform`（每个分块回调一次，返回 ``False``
则中止并返回 ``None``）。

---

## `utils.color_utils`

源码：[`utils/color_utils.py`](../../utils/color_utils.py)

File: utils/color_utils.py
颜色解析：'r,g,b' 字符串 / 元组 → 整数三元组。

放在 utils 层（最低层）以便 core 与 functions 双方复用而不产生循环依赖：
    utils  ←  core  ←  functions / cli / desktop

设计取舍：非法输入**一律抛 ValueError**，不静默降级为黑色。
静默降级会让用户把 "0,0" 写错时只看到一张黑字 PDF 却毫无提示；
而超范围分量（如 300）写进 PDF 会产生损坏输出。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `parse_color(value: Any) -> Tuple[int, int, int]` | 解析颜色为 (r, g, b) 整数元组，分量取值域 [0, 255]。 |
| `format_color(rgb: Tuple[int, int, int]) -> str` | 整数三元组 → "r,g,b" 文本（与 parse_color 互逆）。 |

#### `parse_color(value: Any) -> Tuple[int, int, int]`

解析颜色为 (r, g, b) 整数元组，分量取值域 [0, 255]。

接受:
    - 字符串 "r,g,b"：半角或全角逗号、全角空格均可；
    - 列表 / 元组 (r, g, b)。

异常:
    ValueError: 分量数不为 3、含非数字、或超出 0~255 范围。

---

## `utils.file_utils`

源码：[`utils/file_utils.py`](../../utils/file_utils.py)

文件系统辅助函数：图片文件收集与尺寸校验。

提供以下功能：
- `collect_image_files`: 从文件或目录收集图片，按自然排序返回；
- `is_valid_image_size`: 校验文件大小，过滤异常小文件；
- `IMAGE_EXTS`: 支持的图片扩展名集合。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `collect_image_files(input_path: Path, is_file: bool) -> List[Path]` | 收集输入路径下的所有图片文件，按自然排序返回。 |
| `is_valid_image_size(path: Path, min_size: int=100) -> bool` | 校验文件大小是否大于最小阈值。 |
| `replace_with_retry(source, target, attempts: int=6, delay: float=0.05) -> None` | `os.replace`，但在 Windows 上**短暂重试**。 |
| `write_bytes_atomic(path, data: bytes) -> None` | 原子写字节：先写同目录临时文件，再替换到目标名。 |

#### `collect_image_files(input_path: Path, is_file: bool) -> List[Path]`

收集输入路径下的所有图片文件，按自然排序返回。

参数:
    input_path: 输入路径（文件或目录）。
    is_file: True 表示输入为单文件，False 表示输入为目录。

返回:
    图片 Path 列表，按自然排序（cover → page1 → page2 → page10）。

异常:
    ValueError: 输入为文件但扩展名不在 IMAGE_EXTS 中。

#### `is_valid_image_size(path: Path, min_size: int=100) -> bool`

校验文件大小是否大于最小阈值。

用于快速过滤异常小文件（下载不完整、占位符等），避免进入图像处理流水线。

参数:
    path: 文件路径。
    min_size: 最小文件大小（字节），默认 100。

返回:
    True = 文件大小合格，False = 文件过小。

#### `replace_with_retry(source, target, attempts: int=6, delay: float=0.05) -> None`

`os.replace`，但在 Windows 上**短暂重试**。

为什么必须重试（2026-09-26 审计实测）
    Windows 的 `os.replace` 走 `MoveFileEx(REPLACE_EXISTING)`，**目标文件只要
    还被别的句柄打开就会失败**（哪怕对方只是在读）：
    `PermissionError: [WinError 5] 拒绝访问`。
    实测场景：一边并发写 `tasks.json`、一边读它 —— 8 个写线程里就有 2 个当场
    撞上。这不是代码写错，是 Windows 的共享语义（POSIX 上 rename 不受读者影响），
    所以只能重试。争用窗口只有毫秒级，几次重试足够；真占用（PDF 被阅读器打开）
    重试完仍会抛，由调用方给用户看得懂的话。

参数:
    source: 已写好的临时文件（同目录，保证同一卷）。
    target: 目标路径。
    attempts: 最多尝试次数（含第一次）。
    delay: 每次重试之间的等待秒数。

抛出:
    最后一次的 OSError（重试仍失败时）。

#### `write_bytes_atomic(path, data: bytes) -> None`

原子写字节：先写同目录临时文件，再替换到目标名。

⚠️ 缩略图缓存**必须**这么写（2026-09-26 审计）：缓存是否可用的判据是
``缓存文件.mtime >= 源 PDF.mtime``（`source_thumbnails_worker._render_page`）。
直接 `write_bytes` 的话，写到一半被 kill/断电留下的**截断 JPEG**，
它的 mtime 必然比源文件新 → 会被**永久**当成有效缓存，预览区长期显示半截/
损坏图，而且**没有任何自愈路径**（因为判断"要不要重渲"时看的就是 mtime）。
原子写则保证目标名下要么不存在、要么是完整内容；被 kill 时只留一个
`.part`（不匹配 `*.jpg`，也不会被当成缓存命中）。

---

## `utils.font_scan`

源码：[`utils/font_scan.py`](../../utils/font_scan.py)

扫描系统字体目录，找出所有含中文的字体文件。

与 `utils.fonts` 的分工
-----------------------
`utils.fonts` 是**纯查表**：一张跨平台候选清单，查它永远很快（只 stat 几个
已知路径），覆盖日常要用的字体。`utils.fonts` 因此是生成 PDF 的唯一入口——
**出 PDF 的路上绝不做全盘扫描**，那会白白多花好几秒。

本模块是**真扫描**：遍历系统字体目录、逐个文件读 cmap 判断有没有汉字。用户
自己装的补字字体（花园明朝、BabelStone Han…）只有扫描才能发现，而它们恰恰是
古籍异体字最需要的字体。代价是慢（本机 200+ 字体约 7 秒），因此：

- 结果**缓存到磁盘**，第二次起毫秒级返回；
- 只在 GUI 空闲时由后台线程跑（`desktop.services.font_catalog`），
  绝不出现在主线程与生成 PDF 的路径上。

扫描失败（没装 fontTools、目录不可读、文件损坏）一律返回空元组——调用方
把它当"没有额外字体"，仍然有 `utils.fonts` 的候选表可用。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _CACHE_NAME | `"guji-cjk-font-cache.json"` |
| _MAX_DEPTH | `4` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `font_directories() -> tuple[str, ...]` | 按平台给出要扫描的字体目录（可能不存在，调用方自己判空）。 |
| `scan_system_fonts(force: bool=False) -> tuple[FontEntry, ...]` | 扫描系统里的中文字体，返回按显示名排序的条目。 |
| `scan_seconds_hint() -> float` | 上一次扫描的耗时（秒）；没有记录返回 0.0（调试用）。 |
| `timed_scan(force: bool=False) -> tuple[tuple[FontEntry, ...], float]` | 带计时的扫描（调试与自测用）：返回 (条目, 耗时秒)。 |

#### `scan_system_fonts(force: bool=False) -> tuple[FontEntry, ...]`

扫描系统里的中文字体，返回按显示名排序的条目。

⚠️ 首次调用要遍历整个字体目录、逐个读 cmap，**本机约 7 秒**——
只能在后台线程里调（见 `desktop.services.font_catalog`）。结果会写
磁盘缓存，之后每次调用毫秒级返回。

---

## `utils.font_setup`

源码：[`utils/font_setup.py`](../../utils/font_setup.py)

中文字体体检与 Linux 自动补装。

为什么需要这一层
----------------
Windows 自带仿宋 / 宋体，`utils.fonts` 的候选表几乎必然命中；而
Ubuntu / Debian 的最小安装**一个中文字体都没有**。问题是：缺字体时代码
不会报错，只会静默降级——

- PDF 标题与页码（`utils.pdf_draw.register_fonts`）退回 ``Helvetica`` →
  中文变方块或整段消失；
- 检测框标注（`utils.box_draw.find_cjk_font`）退回 ASCII 的 ``L`` / ``R`` / ``U``。

**产物是错的，界面却毫无提示**。所以 GUI 启动时先体检一次：

1. 找到中文字体 → 静默通过（Windows / macOS 基本都是这条路）；
2. 没找到 → 弹窗。Linux 上给「自动安装」：从发行版仓库拉一个中文字体包，
   **首选真正的仿宋** ``fonts-cwtex-fs``，其次 AR PL UMing、Noto CJK、文泉驿；
3. 自动装不上（无网络 / 无管理员权限 / 没有已知包管理器）→ 退回提示，
   给出可直接复制的手装命令。

依赖方向：只用标准库 + `utils.fonts`，属 `utils` 最底层，任何层都能引用。
**刻意不依赖 Qt**：安装要跑漫长的子进程并sudo/pkexec 提权，把它做成纯函数，
命令行、自测、GUI 三条路才能共用同一份判断（ GUI 侧只负责套壳与流式日志）。

### `class FontPackage`

一个可安装的中文字体包。

- ``name``：包管理器里的包名；
- ``label``：给用户看的一行说明（为什么要装它）；
- ``families``：装完后得到的字体族名（`fc-list` 里显示的名字）。

### `class FontCheck`

体检结果。

- ``found``：本机是否有可用的中文字体；
- ``path``：命中的字体文件（``found`` 为假时是 ``None``）；
- ``source``：命中来源，``env``（``GUJI_CJK_FONT``）/ ``table``（内置候选表）
  / ``scan``（扫描字体目录）/ ``none``；
- ``platform``：``windows`` / ``macos`` / ``linux`` / 其它（``sys.platform``）。

### `class InstallResult`

安装尝试的结果。

``status`` 取值
- ``ok``：装上了，且重新体检确实能找到中文字体；
- ``network``：软件源不可达 / 下载失败 → 应提示用户手动安装；
- ``permission``：提权失败或用户取消 → 同上；
- ``unsupported``：非 Linux 或没有已知包管理器 → 同上；
- ``failed``：其它失败（``output`` 里留了日志尾部，供排查）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `ok() -> bool` | 是否成功装上并被系统识别。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `platform_name() -> str` | 把 ``sys.platform`` 归一成 ``windows`` / ``macos`` / ``linux`` 三类。 |
| `scan_font_dirs(limit: int=8) -> tuple[str, ...]` | 扫描常见字体目录里**看起来是中文**的字体文件（Linux 为主）。 |
| `check_cjk_font() -> FontCheck` | 体检本机有没有可用的中文字体（不弹任何 UI，纯判断）。 |
| `detect_package_manager() -> str \| None` | 返回可用的包管理器键名（``apt`` / ``dnf`` / ``yum`` / ``pacman`` / ``zypper``）。 |
| `install_plan(manager: str \| None=None) -> tuple[FontPackage, ...]` | 返回该平台的字体安装候选（顺序即优先级）；未知包管理器返回空元组。 |
| `available_packages(plan: tuple[FontPackage, ...], manager: str, timeout: float=10.0) -> tuple[FontPackage, ...]` | 筛掉仓库里**确实没有**的包，避免浪费一次提权。 |
| `repo_reachable(timeout: float=4.0) -> bool \| None` | 探测软件源是否可达。 |
| `classify_failure(returncode: int, output: str) -> str` | 把一次安装命令的失败归类成 ``network`` / ``permission`` / ``refresh`` / ``failed``。 |
| `install_cjk_fonts(packages: tuple[str, ...] \| None=None, manager: str \| None=None, probe_network: bool=True, timeout: float=900.0, on_line=None) -> InstallResult` | 从发行版仓库安装中文字体（Linux 专用，其它平台直接返回 ``unsupported``）。 |
| `manual_install_text(plan: tuple[FontPackage, ...] \| None=None) -> str` | 返回可直接照抄的手动安装说明（自动安装失败时给用户看）。 |

#### `scan_font_dirs(limit: int=8) -> tuple[str, ...]`

扫描常见字体目录里**看起来是中文**的字体文件（Linux 为主）。

为什么要扫：静态候选表只能覆盖"发行版把 Noto/文泉驿装在标准位置"这一种
情况。用户从 Windows 拷来的 ``simfang.ttf``、装到 ``~/.local/share/fonts``
的自定义字体都不在表里——不扫就会明明有字体却提示缺字体。

判定只按**文件名关键词**（见 ``_CJK_NAME_HINTS``）：读字体内部元数据要额外
依赖。这里是"决定要不要弹窗"的启发式，宁可宽松也不漏报。

#### `check_cjk_font() -> FontCheck`

体检本机有没有可用的中文字体（不弹任何 UI，纯判断）。

三级判定：``GUJI_CJK_FONT`` 环境变量 → 内置候选表 → 扫描字体目录。
任何一级命中即认为可用。

#### `available_packages(plan: tuple[FontPackage, ...], manager: str, timeout: float=10.0) -> tuple[FontPackage, ...]`

筛掉仓库里**确实没有**的包，避免浪费一次提权。

只有 apt 能廉价地先问一次（`apt-cache policy` 不需要 root）；dnf/pacman/
zypper 会自己刷新元数据，直接尝试即可。若一个都查不出来（索引为空的容器镜像
很常见），原样返回——交给 `install_cjk_fonts` 先刷新再重试，别在这里把路堵死。

#### `repo_reachable(timeout: float=4.0) -> bool | None`

探测软件源是否可达。

返回 ``True`` / ``False``；**判断不了**（非 Linux、认不出发行版）返回
``None``——此时不该拦人，直接尝试安装即可。

为什么先探一次：apt 的 DNS 失败要等 30 秒以上才超时，用户会以为卡死了；
主动探一下能在 4 秒内给出「连不上软件源」的明确结论。

#### `classify_failure(returncode: int, output: str) -> str`

把一次安装命令的失败归类成 ``network`` / ``permission`` / ``refresh`` / ``failed``。

``refresh`` 是一个特例：它不是真失败，而是「仓库索引过期，刷新一次就好了」，
调用方据此重试而不是直接劝退用户。

先判权限再判网络：polkit 撤销 / sudo 密码错误的输出最具体，
且 apt 在得不到写权限时会先报一堆无关的话，顺序反了会误归因。

#### `install_cjk_fonts(packages: tuple[str, ...] | None=None, manager: str | None=None, probe_network: bool=True, timeout: float=900.0, on_line=None) -> InstallResult`

从发行版仓库安装中文字体（Linux 专用，其它平台直接返回 ``unsupported``）。

流程：候选包 →（apt）筛掉仓库里没有的 → 探网络 → 提权 → 逐个安装；
中途遇到「索引过期」会先刷一次元数据再重试同一个包。任何一个包装上、
且重新体检能在系统里找到中文字体，即返回 ``ok``。

``packages`` 可用来收敛到指定包（自测 / 命令行）；省略则用 `install_plan`。

⚠️ 本函数**会阻塞并可能弹文件外的系统授权框**（pkexec/sudo），GUI 里必须
放进子线程，回调回控件要排队回主线程。

#### `manual_install_text(plan: tuple[FontPackage, ...] | None=None) -> str`

返回可直接照抄的手动安装说明（自动安装失败时给用户看）。

内容包含三条路：包管理器装、手动放字体文件到用户目录、用环境变量指定。
前两条按主次给出命令，最后一条是因为容器 / 精简镜像往往连 root 都没有，
``~/.local/share/fonts`` 是唯一不求人的路。

---

## `utils.fonts`

源码：[`utils/fonts.py`](../../utils/fonts.py)

中文字体探测与降级：候选表、优先级链、字形覆盖查询的唯一定义处。

为什么要抽这一层
----------------
PDF 的标题与页码（`utils.pdf_draw.register_fonts`）和检测框标注
（`utils.box_draw.find_cjk_font`）都要画中文，此前两处各自硬编码了四条
``C:\Windows\Fonts\*``。Windows 上一切正常；换到 Linux / macOS 时探测
全部落空 → PDF 里的中文退回 ``Helvetica``（方块或丢字）、框标注退回
ASCII 的 ``L`` / ``R`` / ``U``——**输出内容是错的却不报任何错**。

为什么不能"指定死一个字体"（本层存在的根本原因）
------------------------------------------------
古籍标题里常有**异体字 / 生僻字**：仿宋只覆盖 GB2312 与扩展 A，遇到
扩展 B（`U+20000` 起）的字就没有字形，fpdf 会静默画出空白（控制台只留一行
"missing the following glyphs"）。系统里并非没有这些字——Windows 自带
``simsunb.ttf``（宋体-ExtB）、``mingliub.ttc``——只是它们**不是仿宋**。

因此这里提供三件事：

1. **候选表**：跨平台的中文字体清单，带中文显示名与优先级分组
   （仿宋 → 宋体 → 微软雅黑 → 黑体 → 其它），供用户挑选；
2. **降级链**：把候选按优先级串成一条链，逐个字挑第一个"有这个字"的字体，
   生僻字因此自动落到 ExtB 补字字体上，仿宋该用的地方仍是仿宋；
3. **补字字体**（``fallback_only``）：只有扩展区生僻字的字体（宋体-ExtB 等）
   只补字、不做主字体——它连常用字都没有，选它当主字体整页都会空。

依赖方向：只 import 标准库，是 ``utils`` 的最底层（与 ``utils/units.py``
同级），任何层都可引用。字形查询按需 import ``fontTools``（缺失时退化为
"假定全部支持"，只是不再逐字降级，不会崩）。

设计取舍
--------
- **不做 fontconfig / ``fc-match`` 动态查询**：静态路径已覆盖主流发行版
  的默认字体，而 spawn 子进程会让打包产物和自测行为都变复杂。
- **留了环境变量逃生口 ``GUJI_CJK_FONT``**：精简镜像 / CI / AppImage 里常常
  没有系统 CJK 字体，指向随包自带的 .ttf / .ttc 即可，它**永远排在最前**。

### 模块常量

| 名称 | 值 |
| --- | --- |
| GUJI_FONT_ENV | `"GUJI_CJK_FONT"` |
| GROUP_FANGSONG | `0` |
| GROUP_SONG | `1` |
| GROUP_YAHEI | `2` |
| GROUP_HEI | `3` |
| GROUP_OTHER | `4` |
| GROUP_SUPPLEMENT | `9` |

### `class FontEntry`

一个可用的中文字体：显示名 + 文件路径 + 优先级组。

``fallback_only`` 为真的条目只用于补字（缺字时才用），不作为主字体、
也不出现在用户的选择列表里。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `exists() -> bool` | 字体文件是否真实存在（构造时不校验，用到才探测）。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `known_entries() -> tuple[FontEntry, ...]` | 全部已知候选（按优先级），含不存在的。 |
| `available_entries(with_supplement: bool=True) -> tuple[FontEntry, ...]` | 系统里真实存在的候选，按优先级排序（仿宋 → 宋体 → …）。 |
| `selectable_entries() -> tuple[FontEntry, ...]` | 给用户挑的字体列表：不含"仅补字"字体，按优先级排序。 |
| `find_entry(value) -> FontEntry \| None` | 按显示名 / 文件路径 / 文件名反查条目（用户配置回填用）。 |
| `resolve_chain(preferred=None) -> list[FontEntry]` | 按优先级串出降级链：首选字体在前，补字字体垫底。 |
| `glyphs(entry: FontEntry) -> frozenset \| None` | 该字体覆盖的码位集合；解析失败或没有 fontTools 时返回 None。 |
| `supports(entry: FontEntry, char: str) -> bool` | 该字体是否有这个字符的字形（读不出 cmap 时按"有"处理）。 |
| `pick_font(chain, char: str) -> FontEntry \| None` | 从降级链里挑第一个有这个字的字体；都没有则返回链首。 |
| `cjk_font_paths() -> tuple` | 中文字体文件候选路径（按优先级）。返回的可能全都不存在。 |
| `first_existing_cjk_font() -> str \| None` | 返回第一个真实存在的中文字体文件路径；全部缺失返回 None。 |
| `cjk_font_families() -> tuple` | 按当前平台返回中文字体族名（按优先级），供 Qt 侧挑**界面**文字。 |
| `content_font_families() -> tuple` | 第四步 PDF 内容（标题 / 页码）的字体族名候选：仿宋（衬线）优先。 |

#### `known_entries() -> tuple[FontEntry, ...]`

全部已知候选（按优先级），含不存在的。

``GUJI_CJK_FONT`` 指定的文件排在最前且只出现一次——它是用户/CI 的
显式指定，优先级高于"仿宋优先"。

#### `available_entries(with_supplement: bool=True) -> tuple[FontEntry, ...]`

系统里真实存在的候选，按优先级排序（仿宋 → 宋体 → …）。

``with_supplement=False`` 时不含"仅补字"字体——那种字体不能当主字体。

⚠️ 排序**只按组**、组内保持候选表里的书写顺序（Python 的 sort 是稳定的）：
早先按 display 排序，结果"华文中宋"跑到"宋体"前面、"华文彩云"跑到
"楷体"前面——缺字降级会先落到装饰字体上，视觉上很突兀。

#### `find_entry(value) -> FontEntry | None`

按显示名 / 文件路径 / 文件名反查条目（用户配置回填用）。

找不到返回 None——用户的机器上可能没有配置里记的那个字体（换机器、
卸载字体），此时应当回落到自动选择而不是报错。

#### `resolve_chain(preferred=None) -> list[FontEntry]`

按优先级串出降级链：首选字体在前，补字字体垫底。

``preferred`` 可以是显示名 / 路径 / 文件名（用户选择或配置里的值）；
找不到就忽略，链条从"仿宋优先"的自动顺序开始——**不会因为配置里记了
一个本机没有的字体就整条链失效**。

#### `glyphs(entry: FontEntry) -> frozenset | None`

该字体覆盖的码位集合；解析失败或没有 fontTools 时返回 None。

None 表示"不知道"，调用方应按"支持"处理（乐观）——宁可画出空白，
也不要因为读不出 cmap 就把整段文字降级成另一种字体。

#### `pick_font(chain, char: str) -> FontEntry | None`

从降级链里挑第一个有这个字的字体；都没有则返回链首。

返回链首（而非 None）是刻意的：此时无论选谁都画不出这个字，但至少
字体是确定的（不会因为返回 None 让调用方崩）。

---

## `utils.help`

源码：[`utils/help.py`](../../utils/help.py)

帮助与手册加载模块。

实现 man 风格帮助：从 `docs/functions/<command>.md` 加载 Markdown 文档，
轻量转换为终端可读纯文本后，通过 less/more 分页显示。

文档来源单一：`docs/functions/` 下的 .md 文件即为帮册内容，无需维护额外 .txt 副本。

支持的帮助主题:
    guji help                # 显示命令总览
    guji help extract        # 查看 extract 命令手册
    guji help crop           # 查看 crop 命令手册
    guji help rembg          # 查看 rembg 命令手册
    guji help cropremove     # 查看 cropremove 命令手册
    guji help overview       # 查看功能模块概览

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `markdown_to_text(md: str) -> str` | 将 Markdown 轻量转为终端可读纯文本。 |
| `print_quick_help()` | 打印内置的快速帮助信息（命令总览）。 |
| `print_version()` | 打印版本信息 |
| `get_help_text(command=None) -> str` | 获取帮助文本。 |
| `show_help_page(command=None)` | 分页显示帮助页面（尝试使用 less/more，无分页器则直接打印）。 |
| `show_command_help(command=None)` | 别名：显示指定命令的帮助页面。 |
| `process_help_command(command: str, topic: str \| None=None)` | 处理 CLI 层传来的 help/version 命令并在需要时退出进程。 |

#### `markdown_to_text(md: str) -> str`

将 Markdown 轻量转为终端可读纯文本。

转换规则:
- 代码围栏 (``` ```python) → 移除围栏行，保留代码内容并缩进；
- 标题 (# / ## / ###) → 移除 # 标记，一级标题加 === 下划线，二级加 --- 下划线；
- 粗体 **text** → text；
- 行内代码 `text` → text；
- 链接 [text]\(url) → text（不含 URL）；
- 表格、列表、流程图等保留原样（等宽字体下可读）。

#### `get_help_text(command=None) -> str`

获取帮助文本。

优先级:
1. `docs/functions/<command>.md` — Markdown 文档（转为纯文本）；
2. `docs/man/guji-<command>.txt` — man 风格文本（兼容旧文件）；
3. 内置快速帮助。

参数:
    command: 命令名（extract/crop/rembg/cropremove/overview），None 表示总览。

返回:
    帮助文本字符串。

#### `process_help_command(command: str, topic: str | None=None)`

处理 CLI 层传来的 help/version 命令并在需要时退出进程。

参数:
    command: argparse 解析出的子命令名。特殊值:
        None    — 未指定子命令，显示总览
        'help'  — help 子命令，显示 topic 指定的手册
        'version' — 显示版本
        '-h'/'--help' — 显示总览
    topic: 当 command='help' 时，要查看的命令名（如 'extract'）。

---

## `utils.image_io`

源码：[`utils/image_io.py`](../../utils/image_io.py)

OpenCV 图片读写的路径安全封装。

``cv2.imread`` / ``cv2.imwrite`` 在 Windows 上走的是 ANSI 文件接口，
路径含中文（古籍文件名基本都是中文）时会**静默返回 None / False**，
表现为"无法读取图片"或输出为空。这里统一改为
``np.fromfile`` + ``cv2.imdecode`` 的字节流方式，绕开编码问题。

cv2 / numpy 体积大且加载慢，故在函数内延迟导入——GUI 主进程只是
偶尔需要读一张图，不应该为此付出启动时间的代价。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `imread(path, flags=None)` | 读取图片（支持中文等非 ASCII 路径）。 |
| `imwrite(path, image) -> bool` | 写出图片（支持中文等非 ASCII 路径），成功返回 True。 |

#### `imread(path, flags=None)`

读取图片（支持中文等非 ASCII 路径）。

参数:
    path: 图片路径（str / Path）。
    flags: cv2.IMREAD_* 标志，默认 IMREAD_COLOR。

返回:
    numpy 数组；文件不存在或无法解码时返回 None。

#### `imwrite(path, image) -> bool`

写出图片（支持中文等非 ASCII 路径），成功返回 True。

编码格式由扩展名决定，无法识别时回退 PNG。

---

## `utils.image_utils`

源码：[`utils/image_utils.py`](../../utils/image_utils.py)

图像处理核心工具：Otsu 阈值计算、红色印章提取、区域/整图去底、border 参数解析。

此模块是去底色（rembg / cropremove）功能的核心算法层，提供以下能力：

1. **阈值计算** (`calculate_auto_threshold`)
   手写实现的大津法（Otsu），遍历 0~255 所有可能阈值，找到使前景/背景类间方差最大的阈值。

2. **红色印章提取** (`extract_red_seal`)
   基于 HSV 色域双区间匹配红色像素（H∈[0,10]∪[162,180]），经形态学清理和连通域过滤后，
   返回红色掩码和是否存在"合格印章"的标志。印章合格性由面积、纵横比、填充率三个指标判定。

3. **区域/整图去底** (`apply_otsu_to_region` / `apply_otsu_whole`)
   对给定阈值将灰度图分为文本（< threshold）和背景（≥ threshold）两类，生成白底黑字输出。
   支持 3 种输出类型：二值图(type=1)、1bit 单色位图(type=2)、灰度图(type=3)。
   当启用 seal_color 且存在印章时，输出 RGB 彩色图，保留印章原色。

4. **border 参数解析** (`parse_border` / `parse_border_mm`)
   将 CSS 风格的 1~4 值边距写法展开为 [top, right, bottom, left] 四元组。
   `parse_border_mm` 额外按 DPI 将毫米转换为像素。

### 模块常量

| 名称 | 值 |
| --- | --- |
| REMBG_DEFAULT_OFFSET | `0` |
| REMBG_DEFAULT_TYPE | `1` |
| REMBG_DEFAULT_ENABLE_SEAL | `False` |
| REMBG_DEFAULT_SEAL_COLOR | `False` |
| REMBG_DEFAULT_SEAL_AREA | `80` |
| REMBG_DEFAULT_SEAL_MIN_SAT | `50` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `calculate_auto_threshold(pixels: np.ndarray) -> int` | 大津法（Otsu）计算最佳阈值。 |
| `extract_red_seal(rgb_img: np.ndarray, min_seal_area: int, min_saturation: int) -> Tuple[np.ndarray, bool]` | 从 RGB 图像中提取红色印章掩码。 |
| `apply_otsu_to_region(img_rgb: np.ndarray, gray: np.ndarray, roi_box: tuple, threshold: int, enable_seal: bool, seal_color: bool, red_mask: Optional[np.ndarray], img_type: int=1) -> np.ndarray` | 对图像中指定矩形区域执行去底色处理，返回 ROI 大小的结果数组。 |
| `apply_otsu_whole(img_rgb: np.ndarray, gray: np.ndarray, threshold: int, red_mask: Optional[np.ndarray], seal_color: bool, img_type: int=1) -> np.ndarray` | 对整张图执行去底色处理，返回与输入同尺寸的结果数组。 |
| `rembg_page(img_rgb: np.ndarray, gray: np.ndarray, *, offset: int=REMBG_DEFAULT_OFFSET, img_type: int=REMBG_DEFAULT_TYPE, enable_seal: bool=REMBG_DEFAULT_ENABLE_SEAL, seal_color: bool=REMBG_DEFAULT_SEAL_COLOR, seal_area: int=REMBG_DEFAULT_SEAL_AREA, seal_min_sat: int=REMBG_DEFAULT_SEAL_MIN_SAT) -> np.ndarray` | 整页去底色的**唯一实现**：算阈值 → 叠加 offset → 整图去底。 |
| `parse_border(border_value) -> Optional[List[int]]` | 解析 border 参数（像素单位），支持 CSS 风格 1~4 值写法。 |
| `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]` | 解析 border 参数（毫米单位），按 DPI 转换为像素。 |

#### `calculate_auto_threshold(pixels: np.ndarray) -> int`

大津法（Otsu）计算最佳阈值。

算法原理：遍历所有可能阈值 t (0~255)，将像素分为前景(≤t)和背景(>t)两类，
计算类间方差 σ² = w_b·w_f·(m_b - m_f)²，使 σ² 最大的 t 即为最佳阈值。

参数:
    pixels: 一维 uint8 像素数组（通常为非白像素子集）。

返回:
    0~255 范围内的整数阈值。

实现细节:
- 使用直方图代替逐像素遍历，复杂度 O(256) 而非 O(N)；
- sum_total 预算所有像素值之和，避免重复求和；
- 当前景或背景像素数为 0 时跳过该阈值。

#### `extract_red_seal(rgb_img: np.ndarray, min_seal_area: int, min_saturation: int) -> Tuple[np.ndarray, bool]`

从 RGB 图像中提取红色印章掩码。

算法流程:
1. RGB → HSV 色域转换；
2. 双区间 inRange 匹配红色像素（HSV 中红色分布在色环两端）；
3. 形态学开运算去孤立噪点，膨胀修补断裂；
4. findContours 提取连通域，逐个做面积/纵横比/填充率过滤；
5. 分离出 red_mask（所有红色像素）和 valid_seal_mask（仅合格印章）。

参数:
    rgb_img: RGB 格式图像数组 (H, W, 3)。
    min_seal_area: 印章最小连通域像素面积，低于此值的红色区域不视为印章。
    min_saturation: HSV 中 S 通道下限，过滤浅红色噪声（默认 50）。

返回:
    (red_mask, has_valid_seal):
    - red_mask: bool 数组 (H, W)，True = 红色像素（用于去底时排除）；
    - has_valid_seal: bool，是否存在合格印章（用于决定是否输出彩色图）。

#### `apply_otsu_to_region(img_rgb: np.ndarray, gray: np.ndarray, roi_box: tuple, threshold: int, enable_seal: bool, seal_color: bool, red_mask: Optional[np.ndarray], img_type: int=1) -> np.ndarray`

对图像中指定矩形区域执行去底色处理，返回 ROI 大小的结果数组。

参数:
    img_rgb: 全图 RGB 数组 (H, W, 3)。
    gray: 全图灰度数组 (H, W)。
    roi_box: (x1, y1, x2, y2) 区域坐标。
    threshold: 二值化阈值（由 calculate_auto_threshold 计算）。
    enable_seal: 是否启用了印章检测（影响 red_mask 的使用）。
    seal_color: 是否要求彩色印章输出。
    red_mask: 全图红色印章掩码（None 表示未检测印章）。
    img_type: 输出类型 1=二值 / 2=1bit / 3=灰度。

返回:
    ROI 大小的数组：
    - seal_color 模式且存在印章 → (h, w, 3) RGB，白底 + 红色印章原色 + 黑色文字；
    - 其他 → (h, w) 单通道，type=3 保留原灰度值，type=1/2 文字为 0（黑）背景为 255（白）。

#### `apply_otsu_whole(img_rgb: np.ndarray, gray: np.ndarray, threshold: int, red_mask: Optional[np.ndarray], seal_color: bool, img_type: int=1) -> np.ndarray`

对整张图执行去底色处理，返回与输入同尺寸的结果数组。

与 `apply_otsu_to_region` 逻辑一致，但作用于整图而非局部 ROI，
用于未检测到文本框时的 fallback 路径（整图 Otsu）。

参数:
    img_rgb: RGB 图像数组 (H, W, 3)。
    gray: 灰度数组 (H, W)。
    threshold: 二值化阈值。
    red_mask: 红色印章掩码（None = 无印章）。
    seal_color: 是否输出彩色印章。
    img_type: 1=二值 / 2=1bit / 3=灰度。

返回:
    (H, W, 3) 彩色 或 (H, W) 单通道数组。

#### `rembg_page(img_rgb: np.ndarray, gray: np.ndarray, *, offset: int=REMBG_DEFAULT_OFFSET, img_type: int=REMBG_DEFAULT_TYPE, enable_seal: bool=REMBG_DEFAULT_ENABLE_SEAL, seal_color: bool=REMBG_DEFAULT_SEAL_COLOR, seal_area: int=REMBG_DEFAULT_SEAL_AREA, seal_min_sat: int=REMBG_DEFAULT_SEAL_MIN_SAT) -> np.ndarray`

整页去底色的**唯一实现**：算阈值 → 叠加 offset → 整图去底。

CLI（``functions.rembg``）与桌面端第三步的「实时预览」都调这里，保证界面
所见与最终产物逐像素一致——两处各写一份组装逻辑迟早会漂移。

参数:
    img_rgb / gray: RGB 数组与灰度数组（同尺寸，H×W）。
    offset: 阈值偏移（-100~100）。正数阈值更高 → 文字更粗更深。
    img_type: 1=二值 / 2=1bit / 3=灰度（1bit 的转换由保存方负责）。
    enable_seal / seal_color / seal_area / seal_min_sat: 印章相关参数。

返回:
    与输入同尺寸的去底结果数组：(H, W, 3) 彩色（保留印章原色）
    或 (H, W) 单通道。

#### `parse_border(border_value) -> Optional[List[int]]`

解析 border 参数（像素单位），支持 CSS 风格 1~4 值写法。

写法规则（与 CSS margin 一致）:
- 单值 30       → [30, 30, 30, 30]  (上右下左)
- 两值 20,30    → [20, 30, 20, 30]  (上下, 左右)
- 三值 20,30,25 → [20, 30, 25, 30]  (上, 左右, 下)
- 四值 10,20,30,40 → [10, 20, 30, 40]  (上, 右, 下, 左)

参数:
    border_value: None / int / 逗号分隔字符串。

返回:
    [top, right, bottom, left] 像素列表，或 None。

#### `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]`

解析 border 参数（毫米单位），按 DPI 转换为像素。

实现已迁移到 `utils.box_geometry.parse_border_mm`（无重依赖，GUI 共用），
此处保留 re-export 以兼容 `utils.parse_border_mm` 的延迟加载入口。

---

## `utils.margin_utils`

源码：[`utils/margin_utils.py`](../../utils/margin_utils.py)

File: utils/margin_utils.py
边距（margin）标准化：CSS 简写 → [上, 右, 下, 左]。

放在 utils 层（最低层）以便 core 与 functions 双方复用而不产生循环依赖：
    utils  ←  core  ←  functions / cli / desktop

支持（与 CSS margin 简写一致）:
    - 单值 "20"        → [20, 20, 20, 20]   （四边相等）
    - 两值 "20,30"     → [20, 30, 20, 30]   （上下, 左右）
    - 三值 "20,30,25"  → [20, 30, 25, 30]   （上, 左右, 下）
    - 四值 "20,30,25,35" → 原样              （上, 右, 下, 左）

本模块统一了原先散落在三处的实现（core.command_spec.normalize_margin、
utils.pdf_utils.parse_margins（已废弃）、desktop 面板 parse_margin4），消除了
「三值在 A 处补成四值、在 B 处静默丢弃、在 C 处报错」的行为分叉。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `normalize_margin(value: Any, default: Optional[List[float]]=None) -> Optional[List[float]]` | 把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左] 四元素列表。 |
| `format_margin(value: Any) -> str` | [上,右,下,左] → 最简 CSS 简写文本（与 normalize_margin 互逆）。 |

#### `normalize_margin(value: Any, default: Optional[List[float]]=None) -> Optional[List[float]]`

把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左] 四元素列表。

参数:
    value: 待解析值，支持字符串 / 列表 / 元组 / 数字 / None。
    default: 值为空或非法时返回的兜底值（默认 None）。

返回:
    四元素浮点列表，或 default。

#### `format_margin(value: Any) -> str`

[上,右,下,左] → 最简 CSS 简写文本（与 normalize_margin 互逆）。

四边相等 → 单值；上下/左右分别相等 → 两值；否则四值。
空值返回空字符串。

---

## `utils.page_layout`

源码：[`utils/page_layout.py`](../../utils/page_layout.py)

print 页面排版的几何规则（纯计算，不依赖 cv2 / Qt / fpdf）。

**这里是被 `functions/print.py`（生成 PDF）与 desktop 第四步「打印效果
预览」共用的唯一事实来源**——两处若各写一份公式，预览就会和成品悄悄
漂移（用户按预览调好边距，生成的 PDF 却不一样，最难排查）。

只算几何，不画图：
- CLI/desktop 拿到 `PrintPagePlan` 后各自用 fpdf / QPainter 渲染；
- 坐标单位统一为 **毫米**，与 fpdf 的 `unit="mm"` 一致；
- 输入图片尺寸为**像素**，换算只发生在"图片放进可用区"这一步
  （scale = mm/px，与 print.py 里的算法逐字等价）。

历史坑：`text_margin`（图片左右额外留白，给竖排标题/页码让位）原先是
print.py 里的裸字面量 `8.0`，现在提为 `TEXT_MARGIN_MM`。

竖排里的拉丁字符（`vertical_runs` / `vertical_extent_mm`）：
- 汉字等宽字符**一字一格**；ASCII 可打印字符连成一段**整体旋转 90°**，
  按竖排惯例（如「呵呵Happiness」）而不是把 9 个字母各占一格；
- 分段规则只在本模块定义，`functions/print.py`（fpdf）与 desktop 预览
  （QPainter）都调它，不会出现"预览排一版、成品排另一版"。

标题/页码的「距页边」（`title_margins` / `page_number_margins`）：
- 语义是**距纸张边界**的绝对距离（mm），不再由 page_margins 推导；
- 用与 `page_margins` 同一套 CSS 简写（1/2/3/4 值 → 上,右,下,左），
  所以「左页取左值、右页取右值」天然可以不一样；
- ⚠️ 横向的口径是**文字轮廓边缘**到纸边，不是落点/字格到纸边：
  文字从落点 x 往右画，所以**右页**要把落点再往左退一个文字宽度
  （`text_block_width_mm`：竖排 = 一个字宽，横排 = 整串宽），
  这样右页的**轮廓右缘**才正好离右纸边 `右` 值。不退的话右页空白会比
  左页多一个字宽（写 10mm 实得 10mm+字宽），左右看着不对称。
  左页不需要退——轮廓左缘就是落点。
- ⚠️ 四值里有**两个永远读不到**：上方文字（标题）只取「上」、下方文字
  （页码）只取「下」（见 `_text_anchor` 的 `is_top` 分支）。桌面端因此
  只摆用得上的两个分量、分两行（第一行「左右边距：」一个值管两边、第二行
  「上边距：」/「下边距：」，见
  `desktop.components.panels.print_form.PrintFormMixin.INSET_VISIBLE`），
  并按键把四值补全后导出（`_inset_values`）——但**参数契约仍是四元素**，
  命令行/YAML 照旧写四值；
- 不填（None）时**完全回落到旧行为**（左页 ml/2、右页 mr-6、上下 2mm），
  老任务的输出一个像素都不会变；
- ⚠️ **填了之后图片不再收窄**：用户填的是"文字离纸边多远"，就按这个距离画，
  **允许文字压在图片上**（用户明确要求取消"自动避让图片"这个限制）。
  图片左右始终只留固定的 `TEXT_MARGIN_MM`——那是「距页边」留空时竖排
  标题/页码的默认落点所在，也是老任务输出的既定几何。
  历史：这里曾经按「距页边 + 字宽」把图片收窄（`text_reserve_mm`），
  结果用户设一个 10mm 的左距就把图缩掉一大圈，且判定口径很难解释。

### 模块常量

| 名称 | 值 |
| --- | --- |
| TEXT_MARGIN_MM | `0.0` |
| TEXT_INSET_MM | `0.0` |
| TEXT_SIDE_OFFSET_MM | `0.0` |
| DEFAULT_PAGE_NUMBER_FORMAT | `"chinese"` |
| DEFAULT_PAGE_NUMBER_PREFIX | `"第"` |
| DEFAULT_PAGE_NUMBER_SUFFIX | `"頁"` |
| LATIN_ADVANCE_RATIO | `0.55` |

### `class PrintTextSpec`

一段要画到页面上的文字（标题或页码）。

属性:
    text: 文本内容。
    x_mm: 落点横坐标（竖排为整列的 x）。
    y_start_mm: 起始纵坐标（竖排为**首字**的基线附近）。
    char_h_mm: 单字高度（竖排据此逐字下移）。
    vertical: 是否竖排。
    font_size_pt: 字号（pt，仅用于渲染端换算）。
    color: (r, g, b)。
    direction: 逐字排布方向，"up" 表示 y **递增**（自页顶向下
        排列），与 ``utils.pdf_draw.draw_vertical_text`` 同名参数一致。
    ⚠️ `vertical=True` 时文本按 `vertical_runs` 分段：宽字符（汉字等）
        各自占一格，ASCII（拉丁字母/数字/半角符号）连成一段**整体旋转
        90°**（`Happiness` 不会拆成九个字母格）。
    baseline_mm: 横排时的基线 y（竖排逐字用 y_start_mm，忽略本值）。
    font: 字体指定值（显示名 / 文件路径 / 文件名）；None = 自动
        （仿宋优先）。只用于**选字体**，不参与几何计算——渲染端据此
        挑字体，PDF 端还要按字形降级（见 `utils.pdf_draw.FontChain`）。

### `class PrintPagePlan`

单页排版的完整几何。

属性:
    page_w_mm / page_h_mm: 纸张尺寸（已按方向交换）。
    image: (x, y, w, h) 毫米，图片在页面上的落点与显示尺寸。
    title / page_number: 文字规格，未开启时为 None。
    side: 本页标题/页码所在侧（"left" / "right"）。
    skipped: 本页命中 skip_pages（生成 PDF 时整页不输出，预览留空）。
    text_reserve_mm: 图片左右两侧的固定留白（mm）——**恒为
        `TEXT_MARGIN_MM`**：「距页边」现在只决定文字画在哪儿，
        不再反过来收窄图片（见模块 docstring 的说明）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `is_rotated_char(ch: str) -> bool` | 该字符是否属于"整段旋转 90°"的拉丁/半角段。 |
| `vertical_runs(text: str) -> List[Tuple[str, bool]]` | 竖排文本 → [(片段, 是否旋转 90°)]，相邻同类字符合并成一段。 |
| `vertical_advance_mm(chunk: str, char_h_mm: float, rotated: bool) -> float` | 一段竖排片段在竖直方向上占的高度（mm）——**估算值**。 |
| `vertical_chunk_advance_mm(chunk: str, char_h_mm: float, rotated: bool, latin_width_mm=None) -> float` | 绘制端一段竖排片段的实际步进（mm）——`draw_vertical_text`（fpdf） |
| `vertical_extent_mm(text: str, char_h_mm: float) -> float` | 整串竖排文本的高度（mm）。 |
| `text_block_width_mm(text: str, char_h_mm: float, vertical: bool) -> float` | 一段文字的**横向宽度**（mm）——即它从落点 x 向右占多宽。 |
| `paper_size_mm(paper_size: str) -> Tuple[float, float]` | 纸张名 → (短边, 长边) 毫米；非法纸张抛 ValueError。 |
| `print_page_size_mm(paper_size: str, orientation: str) -> Tuple[float, float]` | 纸张 + 方向 → (页宽, 页高) 毫米。 |
| `image_name_parts(path) -> Tuple[Optional[int], Optional[str]]` | 解析数字页名，返回 (页名数字, side)；side 可能为空。 |
| `resolve_title_nodes(image_files: Sequence, title_switch_nodes: Sequence) -> List[Tuple[int, Tuple[str, str]]]` | 把配置里的 [页名, 标题, side] 解析为「图片下标 → (标题, 侧别)」。 |
| `sides_for_pages(total: int, sorted_nodes: Sequence, page_number_start_page: int) -> List[str]` | 逐页给出标题/页码所在侧（left / right）。 |
| `text_insets(value: Any) -> Optional[List[float]]` | 标题/页码的「距页边」设置 → [上, 右, 下, 左]（mm）。 |
| `plan_print_page(image_size_px: Tuple[int, int], args: dict, page_index: int, total: int, sides: Optional[Sequence[str]]=None, sorted_nodes: Optional[Sequence]=None, image_name: Optional[str]=None, image_rect: Optional[Sequence[float]]=None) -> PrintPagePlan` | 单页排版几何。 |

#### `vertical_runs(text: str) -> List[Tuple[str, bool]]`

竖排文本 → [(片段, 是否旋转 90°)]，相邻同类字符合并成一段。

``"呵呵Happiness"`` → ``[("呵呵", False), ("Happiness", True)]``：
汉字各自占一格，英文整段旋转。绘制端（fpdf / QPainter）按这个分段渲染，
所以两边的断段规则**只在这里定义一次**。

#### `vertical_advance_mm(chunk: str, char_h_mm: float, rotated: bool) -> float`

一段竖排片段在竖直方向上占的高度（mm）——**估算值**。

⚠️ 只用于排版占位（`vertical_extent_mm` → 标题/页码落点）。绘制时的
逐段步进请用 ``vertical_chunk_advance_mm`` 并传渲染端的实测宽度。

#### `vertical_chunk_advance_mm(chunk: str, char_h_mm: float, rotated: bool, latin_width_mm=None) -> float`

绘制端一段竖排片段的实际步进（mm）——`draw_vertical_text`（fpdf）
与 desktop 预览（QPainter）共用的同一份规则。

- 宽字符段：仍是一字一格（``len × char_h_mm``）；
- 旋转拉丁段：优先用渲染端**实测**的字符串宽度（fpdf 的
  ``get_string_width`` / Qt 的 ``QFontMetrics.horizontalAdvance``），
  拿不到实测值（``latin_width_mm=None``）才回落到 `LATIN_ADVANCE_RATIO`
  估算——回落只为兼容，正常路径两条渲染端都会传实测值。

#### `text_block_width_mm(text: str, char_h_mm: float, vertical: bool) -> float`

一段文字的**横向宽度**（mm）——即它从落点 x 向右占多宽。

用于「距右纸边」的口径：用户填的是**文字轮廓右边缘**到纸边的距离，
所以落点得从右边往回退「右距 + 本宽度」，否则文字会比设定值多缩一个字宽
（用户明确要求，见 `_text_anchor`）。

* 竖排：整串是**一列**，宽度就是一个字宽（汉字方块格，等于字号）；
  拉丁段旋转 90° 后也只是一列的宽度，不额外加宽。
* 横排：宽度 ≈ 字符数 × 字宽（比例字体的粗估，`LATIN_ADVANCE_RATIO`
  同一套近似口径；误差只体现在右页横向标题的 1~2mm 留白上）。

#### `print_page_size_mm(paper_size: str, orientation: str) -> Tuple[float, float]`

纸张 + 方向 → (页宽, 页高) 毫米。

方向同时接受 fpdf 的 "P"/"L" 与 CLI/GUI 的 "portrait"/"landscape"：
`functions/print.py` 在 execute() 里把后者映射成了前者再传给排版，
两条路径都要能对上。

#### `resolve_title_nodes(image_files: Sequence, title_switch_nodes: Sequence) -> List[Tuple[int, Tuple[str, str]]]`

把配置里的 [页名, 标题, side] 解析为「图片下标 → (标题, 侧别)」。

``页名`` 是**原始页码**（如 ``5`` / ``5-r``），不是列表下标——用户填
「15」想的是原书第 15 页，即使该页被拖到别处，标题切换仍要跟着它。

#### `sides_for_pages(total: int, sorted_nodes: Sequence, page_number_start_page: int) -> List[str]`

逐页给出标题/页码所在侧（left / right）。

从起始标注页（或最近的章节节点）开始按图片序号交替左右。

#### `text_insets(value: Any) -> Optional[List[float]]`

标题/页码的「距页边」设置 → [上, 右, 下, 左]（mm）。

与 `page_margins` 同款 CSS 简写（1/2/3/4 值）。**空值返回 None**，
表示"沿用由 page_margins 推导的旧行为"——老任务（没有这两个键）
的输出必须一个像素都不变，所以这里绝不能回落到某个默认数字。

非法输入也返回 None（宽松）：校验归入口层
（`core.command_spec` / GUI 表单），库层不替调用方做决定。

#### `plan_print_page(image_size_px: Tuple[int, int], args: dict, page_index: int, total: int, sides: Optional[Sequence[str]]=None, sorted_nodes: Optional[Sequence]=None, image_name: Optional[str]=None, image_rect: Optional[Sequence[float]]=None) -> PrintPagePlan`

单页排版几何。

参数:
    image_size_px: 图片原始像素 (w, h)。
    args: print 参数（CLI 的 command_args 或 GUI 面板 get_args()）。
    page_index: **0-based** 图片下标。
    total: 图片总数（页码结束页缺省时用）。
    sides: 逐页左右侧（由 `sides_for_pages` 预计算）；不传则临时算。
    sorted_nodes: 章节节点（`resolve_title_nodes` 结果）；不传则临时算。
    image_name: 当前图片文件名（stem 即可），用于 ``skip_pages``
        按页名回查；不传则只能按序号匹配。

---

## `utils.path_utils`

源码：[`utils/path_utils.py`](../../utils/path_utils.py)

路径工具函数，用于解析各种命令的输出目录。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `assert_output_not_input(input_path, out_path) -> None` | 确认输出目录不会撞上输入目录：撞上就抛 `ValueError`。 |
| `resolve_final_output_dir(input_path: Path, output_arg: Optional[str], is_file: bool, default_subdir: str) -> Path` | 计算命令的最终输出目录（适用于 crop/rembg/cropremove 等）。 |
| `get_extract_output_root(input_path: Path, output_arg: Optional[str], is_file: bool) -> Path` | 计算 extract 命令的输出根目录（out_root）。 |

#### `assert_output_not_input(input_path, out_path) -> None`

确认输出目录不会撞上输入目录：撞上就抛 `ValueError`。

为什么必须有这道闸（2026-09-26 实测，硬证据）
    `resolve_final_output_dir` 在「目录输入 + 不给 `--output`」时返回
    ``input.parent / <该命令的子目录名>``。当**输入目录的 basename 恰好等于
    该命令的子目录名**时（`.../rembg` 跑 rembg、`.../crop` 跑 crop、
    `.../detect` 跑 `detect --save`、`.../images` 跑 extract），输出目录
    就是**输入目录本身**。实测把两张可辨认的 PNG 放进一个叫 `rembg` 的目录：

    | `clean` | 结果 |
    |---|---|
    | False | `1.png`/`2.png` **被原地覆盖**（rembg 输出名与输入同名） |
    | True  | `rmtree(outpath)` 把**输入目录连同图片全部删除**，目录被重建为空，**退出码仍是 0** |

    后者是静默丢数据：用户的原图没了，命令还报成功。
    "重跑自己上一步的输出目录"是极常见的操作（`.../rembg`、`.../crop`），
    所以不能靠用户小心。

判据（两条都要挡）
    1. 输出 == 输入（原地覆盖 / 删掉输入）；
    2. 输出是输入的**祖先**（`rmtree(输出)` 同样会连输入一起删）。

输入是**文件**时按它的父目录看待——对 extract 这类「输出根目录 = PDF 所在目录、
产物落在其子目录」的命令，`out_path == input.parent` 是合法的，那种情况由
「输出是否是输入的祖先」这条判据排除（父目录不是祖先关系里的 out 侧）。

参数:
    input_path: 输入路径（文件或目录）。
    out_path: 计算出的输出目录。

抛出:
    ValueError: 输出会撞上输入时，附上可照做的修法（改用 `-o` 指到别处）。

#### `resolve_final_output_dir(input_path: Path, output_arg: Optional[str], is_file: bool, default_subdir: str) -> Path`

计算命令的最终输出目录（适用于 crop/rembg/cropremove 等）。

规则：
- 如果指定了 --output：
    - 若输出值不含路径分隔符，则视为简单名称：
        - 根目录 = 输入路径的父目录 / 名称
        - 无论输入是文件还是目录，都使用 `input_path.parent` 作为基准。
    - 若含分隔符，则解析为绝对/相对路径（基于当前工作目录）。
- 如果未指定 --output：
    - 根目录 = 输入路径的父目录（即与输入文件/目录并列）。
- 最终输出目录 = 根目录 / default_subdir

这样设计确保：
    - 对于目录输入，输出默认与输入目录并列（而非在输入目录内部）。
    - 用户指定的 -o 作为根目录，其下自动追加 default_subdir。
    - 对于文件输入，输出默认在文件所在父目录下创建 default_subdir。

参数:
    input_path: 原始输入路径（Path 对象，已解析为绝对路径）。
    output_arg: 用户传入的 --output 参数（原始字符串或 None）。
    is_file: 输入是否为单个文件（否则为目录）。本函数中主要用来区分是否使用 input_path.parent 作为基准。
    default_subdir: 默认子目录名（如 "crop"）。

返回:
    最终的输出目录（Path 对象）。

#### `get_extract_output_root(input_path: Path, output_arg: Optional[str], is_file: bool) -> Path`

计算 extract 命令的输出根目录（out_root）。

该目录下会为每个 PDF 创建以 PDF 文件名命名的子目录，并在其下存放图片。
图片子目录名（如 "images"）由调用方在后续拼接时决定（通过 subdir_name 参数传递给 run_on_input_directory）。

规则：
- 如果指定了 --output：
    - 若输出值不含路径分隔符，则视为简单名称：
        - 输入为文件时，根目录 = 文件所在父目录 / 名称
        - 输入为目录时，根目录 = 输入目录 / 名称
    - 若含分隔符，则解析为绝对/相对路径（基于当前工作目录）。
- 如果未指定 --output：
    - 输入为文件时，根目录 = 文件所在父目录
    - 输入为目录时，根目录 = 输入目录本身

参数:
    input_path: 原始输入路径（Path 对象，已解析为绝对路径）。
    output_arg: 用户传入的 --output 参数（原始字符串或 None）。
    is_file: 输入是否为单个文件（否则为目录）。

返回:
    输出根目录（Path 对象）。

---

## `utils.pdf_draw`

源码：[`utils/pdf_draw.py`](../../utils/pdf_draw.py)

生成 PDF 的绘制辅助：字体注册、竖排文字、左右页判定。

从 `utils/pdf_utils.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）；
PDF → 图片的部分在 `utils/pdf_extract.py`。

⚠️ 竖排的**分段规则**不在本模块，来自 `utils.page_layout.vertical_runs` ——
`functions/print.py`（fpdf 出 PDF）与 desktop 第四步「打印效果预览」
（QPainter）共用同一份，改分段只改那里。

### `class FontChain`

一组已注册到某个 FPDF 实例的字体，可按字符挑名字。

为什么需要它
------------
古籍标题常有异体字 / 生僻字，而**没有任何单一字体**能覆盖它们：仿宋
缺扩展 B 的字，Windows 自带的宋体-ExtB 有那些字却没有常用字。所以
``name_for(ch)`` 按优先级链挑第一个"有这个字"的字体——常用字仍是仿宋，
只有仿宋真没有的那个字才落到补字字体上。

⚠️ 只注册**实际会用到**的字体（构造时传入全部待排文字来算）：
把整条链二十来个字体全注册进去，每页 PDF 都要多嵌几个字体子集，
体积与生成时间都白涨。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(entries, names: dict, primary: str)` | — |
| `entries() -> list` | 参与本链条的字体条目（按优先级）。 |
| `name_for(char: str) -> str` | 这个字符该用哪个已注册字体名（找不到时回落主字体）。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `build_font_chain(pdf, texts=(), preferred=None) -> FontChain` | 按优先级注册字体，返回可按字符取名的 `FontChain`。 |
| `register_fonts(pdf, preferred=None, texts=())` | 注册系统中文字体，返回第一个成功注册的字体名。 |
| `draw_vertical_text(pdf, text, x, y_start, font_name, font_size, color, direction='down', chain=None)` | 在PDF上绘制竖排文字：宽字符一字一格，拉丁段整体旋转 90°。 |
| `draw_horizontal_text(pdf, text, x, y, font_name, font_size, color, chain=None)` | 在 PDF 上绘制横排文字；``chain`` 给出时逐字降级选字体。 |
| `get_page_side_from_name(name_without_ext)` | 根据文件名末尾 '-l' 或 '-r' 判断左右页。 |
| `get_page_side_by_start(image_files, current_index, start_page, default_side='left')` | 根据起始页的左右属性推断当前页是左还是右。 |

#### `build_font_chain(pdf, texts=(), preferred=None) -> FontChain`

按优先级注册字体，返回可按字符取名的 `FontChain`。

- ``preferred``：用户指定的字体（显示名 / 路径 / 文件名）；本机没有时
  忽略，链条仍从"仿宋优先"开始。
- ``texts``：本次要排印的全部文字（标题、各章节标题…）。据此只注册
  真正需要的字体。

一个都注册不上时链条为空、主字体为 `"Helvetica"`（fpdf 内置字体，不含
中文字形），由调用方决定是否告警，这里不抛异常。

#### `register_fonts(pdf, preferred=None, texts=())`

注册系统中文字体，返回第一个成功注册的字体名。

候选来自 `utils.fonts`（跨平台候选表 + `GUJI_CJK_FONT` 环境变量）——
**中文字体路径不许在本文件硬编码**：曾经这么做过，换到非 Windows 平台
后探测全部落空，标题/页码静默退回 Helvetica（方块、丢字）。

需要**逐字降级**（生僻字）时请改用 `build_font_chain`：本函数只返回主
字体名，画不出来就是画不出来。

#### `draw_vertical_text(pdf, text, x, y_start, font_name, font_size, color, direction='down', chain=None)`

在PDF上绘制竖排文字：宽字符一字一格，拉丁段整体旋转 90°。

⚠️ 分段规则来自 `utils.page_layout.vertical_runs`（与第四步预览**同一份**）：
汉字等宽字符逐字下移，ASCII 可打印字符连成一段用 `pdf.rotation(90, …)`
整体旋转——按竖排惯例，「呵呵Happiness」里的英文是一个转 90° 的竖条，
而不是九个字母各占一格（那样既挤又认不出来）。

``chain``（`FontChain`）给出时**逐字挑选字体**：主字体缺这个字的字形
就顺位落到下一个（生僻字因此落到宋体-ExtB 之类的补字字体上），
而不是画出空白。不给则整段用 ``font_name``（历史行为）。

#### `draw_horizontal_text(pdf, text, x, y, font_name, font_size, color, chain=None)`

在 PDF 上绘制横排文字；``chain`` 给出时逐字降级选字体。

逐字降级必然要**逐字落笔**（每个字可能来自不同字体），宽度也必须用
**该字所在字体**实测——用主字体量全串的宽度会在换字体处错位。

---

## `utils.pdf_extract`

源码：[`utils/pdf_extract.py`](../../utils/pdf_extract.py)

PDF 页面提取：把 PDF 每页渲染成图片并保存。

从 `utils/pdf_utils.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）——
原文件把「PDF → 图片」与「生成 PDF 的绘制辅助」两种职责混在 759 行里。
本模块只管前者：

1. **页码解析** (`parse_pages` / `validate_page_range`)
   支持两种页码选择方式：逗号分隔 + 范围字符串（如 "1,3-5,7"）或 start/end 整数对。

2. **缩放计算** (`calculate_zoom` / `render_zoom`)
   根据页面宽度限制最大输出尺寸（6000px），避免内存溢出；整页渲染另有
   DPI 下限（默认 300），避免没有内嵌图的矢量 PDF 在 zoom=1 时只渲染出 72 DPI。

3. **批量渲染** (`process_page_batch` / `render_pages_parallel` / `extract_pdf_optimized`)
   使用 PyMuPDF (fitz) 渲染页面，支持两种模式：
   - quick=True：优先取 PDF 内嵌图片（**自适应**，不满足条件自动降级整页渲染）；
   - quick=False：直接渲染页面为高质量图片。

   quick 的判定见 `_embedded_page_image()`：只有「单张内嵌图 + jpg/png 格式 +
   像素不低于整页渲染尺寸」才走快路径，否则降级。这样 jp2/jbig2/CCITT 压缩、
   一页多图、内嵌缩略图这三类情况不会"为了快而变慢或变糊"。

   ⚠️ 并发后端是**多进程**（`ProcessPoolExecutor`），不是线程：PyMuPDF 的
   `get_pixmap` 期间持有 GIL，线程池对渲染**零加速**（实测 6 线程仅 1.15×，
   还把 GUI 拖卡）。详见 `render_pages_parallel` 的说明。

4. **目录遍历** (`run_on_input_directory`)
   支持输入为单个 PDF 文件或包含多个 PDF 的目录。

依赖: PyMuPDF (pymupdf), Pillow (PIL)。
绘制辅助（字体注册 / 竖排文字 / 左右页判定）在 `utils/pdf_draw.py`。

### 模块常量

| 名称 | 值 |
| --- | --- |
| QUICK_MIN_COVERAGE | `0.9` |
| MAX_OUTPUT_WIDTH_PX | `6000` |
| WIDE_PAGE_PT | `3000` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `parse_pages(pages_str: str, total_pages: int) -> List[int]` | 解析页码字符串为 0-based 页码列表。 |
| `validate_page_range(start: Optional[int], end: Optional[int], total_pages: int) -> List[int]` | 根据 start/end 整数对生成 0-based 页码列表。 |
| `calculate_zoom(page_width: float, requested_zoom: float=1) -> float` | 计算实际缩放因子，限制最大输出宽度为 6000px。 |
| `render_zoom(page_width: float, requested_zoom: float=1, dpi: float=DEFAULT_RENDER_DPI) -> float` | 整页渲染实际使用的缩放因子 = max(用户 zoom, DPI 下限)，再受宽度封顶。 |
| `report_image_size(img_path, width: int, height: int, reporter=None) -> None` | 汇报一页输出图片的尺寸。 |
| `process_page_batch(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=True, progress: Optional[dict]=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]` | 处理一批 PDF 页面，返回每页的成功状态。 |
| `render_pages_parallel(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=True, workers: int=4, batch_size: int=4, progress: Optional[dict]=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]` | 多**进程**提取指定页，返回每页成功状态。 |
| `extract_pdf_optimized(pdf_path: str, out_dir: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=True, pages: Optional[str]=None, start: Optional[int]=None, end: Optional[int]=None, batch_size: int=4, clean: bool=False, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> bool` | 提取 PDF 页面为图片，支持多线程批次处理。 |
| `run_on_input_directory(input_path: str, out_root: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=True, pages: Optional[str]=None, start: Optional[int]=None, end: Optional[int]=None, batch_size: int=4, clean: bool=False, subdir_name: str='images', reporter=None, dpi: float=DEFAULT_RENDER_DPI)` | 处理输入路径（文件或目录），对每个 PDF 在 out_root 下创建以其文件名命名的子目录， |

#### `parse_pages(pages_str: str, total_pages: int) -> List[int]`

解析页码字符串为 0-based 页码列表。

支持格式: "1,3-5,7" → [0, 2, 3, 4, 6]
页码为 1-based，返回值转换为 0-based。

参数:
    pages_str: 页码字符串（逗号分隔，支持范围）。
    total_pages: PDF 总页数（用于越界检查）。

返回:
    排序后的 0-based 页码列表。

异常:
    ValueError: 页码格式错误或超出范围。

#### `validate_page_range(start: Optional[int], end: Optional[int], total_pages: int) -> List[int]`

根据 start/end 整数对生成 0-based 页码列表。

参数:
    start: 起始页（1-based），None 表示从第 1 页开始。
    end: 结束页（1-based），None 表示到最后一页。
    total_pages: PDF 总页数。

返回:
    0-based 页码列表。

#### `calculate_zoom(page_width: float, requested_zoom: float=1) -> float`

计算实际缩放因子，限制最大输出宽度为 6000px。

参数:
    page_width: PDF 页面宽度（pt 单位，1pt ≈ 1/72 inch）。
    requested_zoom: 用户请求的缩放因子。

返回:
    实际使用的缩放因子。

#### `render_zoom(page_width: float, requested_zoom: float=1, dpi: float=DEFAULT_RENDER_DPI) -> float`

整页渲染实际使用的缩放因子 = max(用户 zoom, DPI 下限)，再受宽度封顶。

与 `calculate_zoom` 的区别：**只有这一条路径会补 DPI**。内嵌图（quick）
路径仍旧用 `calculate_zoom` —— 原图字节直拷，既不该被下限放大，也不该
因为下限变严而被判成"低清"降级（那会把 240 DPI 的扫描件重新渲染成
放大插值图，反而更糊）。

参数:
    page_width: PDF 页面宽度（pt）。
    requested_zoom: 用户请求的缩放因子（>=1）。
    dpi: 目标 DPI 下限；传 72 即等价于旧行为（zoom 说了算）。

返回:
    实际渲染缩放因子。

#### `report_image_size(img_path, width: int, height: int, reporter=None) -> None`

汇报一页输出图片的尺寸。

结构化通道 `page_size` 供 GUI 子进程入库（sizes.json 是框坐标的坐标系基准）；
`[imgsize]` 文本行仅为**兼容保留**。

reporter 缺省为 None —— CLI 不注入，行为与原先「只 print 一行」完全一致。

#### `process_page_batch(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=True, progress: Optional[dict]=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]`

处理一批 PDF 页面，返回每页的成功状态。

参数:
    pdf_path: PDF 文件路径。
    page_indices: 0-based 页码列表。
    out_dir: 输出目录。
    zoom: 缩放因子。
    ext: 输出格式（jpg/png）。
    quick: True=优先取内嵌图（不满足条件会自动降级整页渲染，见
          `_embedded_page_image`），False=始终整页渲染。
    progress: 共享进度字典（含 lock, done, total），用于线程安全打印进度；
          额外用 reasons/fallback 记录 quick 降级原因（不逐页刷屏）。
    reporter: 结构化汇报通道（进度 + 页尺寸）。None → 只 print，CLI 不受影响。
    dpi: 整页渲染的 DPI 下限（见 `render_zoom`）。**只影响渲染路径**，
          取内嵌图时按原图字节落盘，不做任何重采样。

返回:
    每页成功/失败的 bool 列表。

#### `render_pages_parallel(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=True, workers: int=4, batch_size: int=4, progress: Optional[dict]=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]`

多**进程**提取指定页，返回每页成功状态。

CLI（`extract_pdf_optimized`）与 GUI（`run_extract_stage`）共用这一份并发
实现——GUI 曾经直接调 `process_page_batch` 串行跑全部页，是提取慢的主因。

⚠️ 2026-09-28：并发后端从 `ThreadPoolExecutor` 换成 `ProcessPoolExecutor`。
起因是「第一步 extract 变慢 + 界面卡」，实测（本机 6 物理核，102 页 jpx
扫描件，见 .workbuddy/memory/2026-09-28.md）：

- **线程对 PyMuPDF 渲染完全无效**：`get_pixmap` 期间持有 GIL，纯渲染
  1→4→6 线程只有 1.15×（1085/942/972 ms/页）；端到端 4 线程与单线程持平，
  6 线程占满物理核还把 GUI 拖卡（**这是"页面卡"的直接原因**）；
- 同一份活交给 4 个**进程**：**1.79 页/秒 vs 0.96（1.86×）**——GIL 不再共享。

代价与约束：
- 每个子进程要各自 `fitz.open`（Document 不可 pickle），结果再 pickle 回父进程，
  因此**只有批次多于 1 批**才开池：单批（≤ batch_size 页）开池会被 ~0.8s 的
  进程启动开销吃回去；
- 所有 `print` / `reporter` / `progress` 都由**父进程**做（见 `_report_batch`），
  子进程只返回数据；
- ⚠️ 本函数会 spawn 子进程，因此**调用方入口必须有 `if __name__ == "__main__"`
  保护**，打包环境还须先调 `multiprocessing.freeze_support()`（PyInstaller 的
  硬要求，否则子进程会重新拉起整个 exe）。

reporter 为结构化汇报通道（进度 + 页尺寸）；None → 保持纯 print 行为。

#### `extract_pdf_optimized(pdf_path: str, out_dir: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=True, pages: Optional[str]=None, start: Optional[int]=None, end: Optional[int]=None, batch_size: int=4, clean: bool=False, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> bool`

提取 PDF 页面为图片，支持多线程批次处理。

参数:
    pdf_path: PDF 文件路径。
    out_dir: 输出目录（此目录将存放该 PDF 的所有页面图片）。
    zoom: 缩放因子（整数，如 2 表示 2 倍分辨率）。
    dpi: 整页渲染的 DPI 下限（见 `render_zoom`），不影响内嵌图路径。
    ext: 输出格式 jpg/png/tiff。
    workers: 线程数。
    quick: True=快速模式（优先提取内嵌图片）。
    pages: 页码字符串（如 "1,3-5,7"），优先级高于 start/end。
    start: 起始页（1-based）。
    end: 结束页（1-based）。
    batch_size: 每批次处理的页数。
    clean: True=清空输出目录后重新提取。
    reporter: 结构化汇报通道；None → 只 print（CLI 默认）。

返回:
    True=处理完成（部分页面可能失败，查看日志），False=整体失败。

#### `run_on_input_directory(input_path: str, out_root: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=True, pages: Optional[str]=None, start: Optional[int]=None, end: Optional[int]=None, batch_size: int=4, clean: bool=False, subdir_name: str='images', reporter=None, dpi: float=DEFAULT_RENDER_DPI)`

处理输入路径（文件或目录），对每个 PDF 在 out_root 下创建以其文件名命名的子目录，
并在该子目录下创建 subdir_name 目录存放图片。

参数:
    input_path: 输入路径（单个 PDF 文件或包含 PDF 的目录）。
    out_root: 输出根目录（所有 PDF 的子目录将创建在此目录下）。
    zoom, ext, workers, quick, pages, start, end, batch_size, clean, dpi:
        透传给 extract_pdf_optimized 的参数。
    subdir_name: 每个 PDF 子目录下存放图片的子目录名。
    reporter: 结构化汇报通道；None → 只 print（CLI 默认）。

---

## `utils.pdf_stream`

源码：[`utils/pdf_stream.py`](../../utils/pdf_stream.py)

让 fpdf 的输出**边写边落盘**，不再把整本 PDF 建在内存里。

背景（2026-09-26 实测，320 页 4900×4400 的扫描页）
    fpdf2 的 `output()` 走 `OutputProducer.bufferize()`：把**整本 PDF** 写进一个
    bytearray，最后一次 `write_bytes` 落盘（`fpdf.py:6535`）。于是 print 阶段的内存是
        图片缓存里的嵌入数据（≈ PDF 体积）+ 输出缓冲（≈ PDF 体积）= **≈ 2×PDF**
    实测：加载完 2644MB（其中 cache 2548MB），`output()` 期间峰值 **5146MB**。

解法
    `output(output_producer_class=...)` 是 fpdf 的**公开注入口**（`fpdf.py:6463`），
    而 `OutputProducer` 对 `self.buffer` 只有两种用法（全仓 grep 确认过）：
        - `self.buffer += data`（`output.py:1116`，唯一的写入路径）
        - `len(self.buffer)`（算对象偏移、startxref、分段统计）
    **从不切片读它**。所以把 buffer 换成一个"写文件 + 记长度"的假 buffer，
    输出就变成一路落盘：

        峰值 5146MB → **2819MB（−45%）**；`output()` 16.5s → **8.1s**（快一倍）
        **产物 SHA-256 完全相同**（逐字节一致，含 trailer 的 /ID）

⚠️ 两个必须处理的细节
    1. `fpdf._default_file_id()` 会拿**整个 buffer** 做 md5 算 trailer 的 /ID
       （`output.py:650`）——这是唯一真的把 buffer 当 bytes 用的地方。解法不是去改
       fpdf，而是**覆盖 `file_id()`**：fpdf 文档明说这个方法留给子类定义自定义 /ID
       （`fpdf.py:5869`）。假 buffer 维护一份**增量 md5**，增量算与全量算结果必然
       相同 → /ID 一字不差，产物仍然逐字节一致。
    2. 落盘走**临时文件 + `os.replace`**：中途失败/被杀不会留下半本 PDF 被用户
       点开（fpdf 原本的 `write_bytes` 是先截断再写，留得下坏文件）。

只给 `print` 用：它是唯一会把**整本大图**攒进 fpdf 的命令（extract/rembg 等
不经 fpdf 输出）。

### `class PdfDocument(FPDF)`

`print` 用的 FPDF：把 `/ID` 接到流式缓冲上（见模块文档细节 1）。

没走流式输出时 `file_id()` 返回 -1，交回 fpdf 默认算法 —— 行为与直接用
`FPDF` 完全一致，所以两条出口的产物可逐字节比对。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `file_id() -> 'str \| int'` | — |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `write_streaming(pdf: PdfDocument, path: str \| os.PathLike[str]) -> None` | 把 pdf 边写边落盘到 path（先写 `.part` 再原子替换）。 |

#### `write_streaming(pdf: PdfDocument, path: str | os.PathLike[str]) -> None`

把 pdf 边写边落盘到 path（先写 `.part` 再原子替换）。

⚠️ 同一个 pdf 只能输出一次：fpdf 的 `output()` 会把自己标成"已定稿"，再调
会抛 `FPDFException`（这是 fpdf 原本就有的约束，不是本模块引入的）。

---

## `utils.perspective`

源码：[`utils/perspective.py`](../../utils/perspective.py)

四点透视校正（古籍拍摄角度 / 页面倾斜的快速摆正）。

## 口径（2026-10-01 用户定：独立入口）

「变形」（:mod:`utils.puppet_warp`）是**局部**微调（褶皱、小面积抽动），
本模块是**整页**的快速摆正：古籍翻拍常见的"梯形/倾斜"——书页四条边不是
矩形（拍摄角度导致），或整页微微斜着（装订线倾斜）。做法是拉四个角点，
把**源四边形**映到**目标矩形**（单应变换 / 透视变换），一次摆正整页。

- 与「变形」的分工：褶皱用变形（局部、图钉、逐点），页形/角度用本模块
  （整页、四个角、一次到位）。两者都落在同一套编辑器与撤销栈里。
- 与「变换」的分工：变换是**仿射**（平行线还是平行线），本模块是**透视**
  （平行线可以交于一点），这才是"角度"该有的数学。

## 算法：四点 DLT 解单应矩阵 + 逆向采样

1. **单应**：``H`` 3×3 使 ``dst ~ H·src``（齐次坐标，共 8 个自由度）。
   四点对应给出 8 个线性方程，解 8×8 线性组（:func:`homography`）。
2. **采样**：对**目标**矩形里每个像素 ``(x', y')``，用 ``H⁻¹`` 反算它来自
   源图的哪个点，双线性采样（**逆向映射**——正向映射会在目标上留空洞）。
   越界处填 ``fill``（白纸口径填白）。

numpy 延迟导入（桌面主进程 import 本模块时不加载）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| MIN_AREA | `0.001` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `homography(src, dst)` | 解四点对应的单应矩阵 ``H``（3×3，``dst ~ H·src``）。 |
| `invert(H)` | 单应矩阵求逆（正变换 ``src→dst``，采样要用逆 ``dst→src``）。 |
| `apply_homography(H, points)` | 把 ``H`` 作用到 ``points``（``(N, 2)`` 或 ``(2,)``），返回同形状。 |
| `target_rect(src, *, mode: str='bbox')` | 给源四边形算一个"摆正后"的目标矩形（图片坐标，**像素闭区间**）。 |
| `quad_area(quad) -> float` | 四边形（按序）的面积（shoelace，恒为非负）。 |
| `quad_degenerate(quad) -> bool` | 四边形是否退化（面积过小）——退化时不校正，直接放弃。 |
| `rectify(src, quad, *, out_size=None, mode: str='bbox', fill=FILL, block: int=BLOCK_PIXELS)` | 把 ``src`` 里 ``quad`` 围的区域透视摆正到目标矩形，返回新数组。 |
| `qimage_to_rgba(image)` | QImage → ``(H, W, 4)`` uint8 **RGBA**（保留 alpha，见 puppet_warp）。 |
| `array_to_qimage(rgb)` | ``(H, W, 3\|4)`` uint8 → QImage（ARGB32）；3 通道按不透明处理。 |
| `rectify_qimage(image, quad, *, out_size=None, mode: str='bbox', fill=None)` | QImage 版 :func:`rectify`（保留 alpha；带 alpha 的图越界填透明白）。 |
| `rectify_region(quad, width: int, height: int, *, mode: str='bbox')` | 这次校正的目标矩形 ``(x0, y0, w, h)``（画布预览贴框用）。 |
| `quad_moved(src_quad, dst_quad, epsilon: float=1e-06) -> bool` | 四角是否真的动过（区分"全选没动"与"要校正"）。 |

#### `homography(src, dst)`

解四点对应的单应矩阵 ``H``（3×3，``dst ~ H·src``）。

``src``/``dst`` 各是 4 个 ``(x, y)``。用 DLT：每个对应点给两行方程，
8 个方程解 8 个未知量（令 ``h33 = 1``）。四点共线（退化）时抛
:class:`ValueError`——调用方应先在 UI 上拦住，而不是解出垃圾。

#### `target_rect(src, *, mode: str='bbox')`

给源四边形算一个"摆正后"的目标矩形（图片坐标，**像素闭区间**）。

- ``mode="bbox"``：目标 = 源四边形的**轴对齐外接框**（尺寸与图幅同）；
- ``mode="area"``：目标 = 与源四边形**等面积**的矩形，宽高比取源四边形
  对边平均长之比（摆正后不变形，内容不拉胖/压扁）。

⚠️ 四角是**像素坐标**（含端点），所以尺寸按 ``max - min + 1`` 取：
四角正好压在图片四角（``(0,0)~(w-1,h-1)``）时目标尺寸 = ``(w, h)``，
校正**逐字节还原原图**（自测钉死）。写成 ``max - min`` 会差 1 像素、
反而把没动的整页缩掉一行一列。

返回 ``(x0, y0, x1, y1)``（闭区间；尺寸 = ``x1-x0+1``）。

#### `rectify(src, quad, *, out_size=None, mode: str='bbox', fill=FILL, block: int=BLOCK_PIXELS)`

把 ``src`` 里 ``quad`` 围的区域透视摆正到目标矩形，返回新数组。

- ``src``：``(H, W)`` 或 ``(H, W, C)``。
- ``quad``：源四边形四个角，顺序 ``[左上, 右上, 右下, 左下]``。
- ``out_size``：目标尺寸 ``(宽度, 高度)``；缺省按 :func:`target_rect`
  的 ``mode`` 推。
- 输出**尺寸 = 目标矩形尺寸**（就地摆正，不是原尺寸上的贴块）。

---

## `utils.proc_utils`

源码：[`utils/proc_utils.py`](../../utils/proc_utils.py)

进程相关的通用小工具。

只放"跨模块都要用、但不值得各自写一遍"的东西。目前是 `pid_alive`——本项目有两处
都要判断"某个 pid 的属主进程是不是已经死了"（清理效果图暂存目录、清理常驻服务
的发现文件），逻辑一样，抽出来只留一份。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `pid_alive(pid: int) -> bool` | pid 对应的进程是否还活着。 |

#### `pid_alive(pid: int) -> bool`

pid 对应的进程是否还活着。

⚠️ **保守优先**：任何"说不清"的情况（权限不足、psutil 不可用、平台差异）
都返回 True（当作活着）。调用方是拿它做**删除判据**的（删暂存目录、删发现
文件），把"不确定"当成"已死"就会误删正在用的东西；反过来只是少清一点垃圾。

---

## `utils.puppet_warp`

源码：[`utils/puppet_warp.py`](../../utils/puppet_warp.py)

操控变形（puppet warp）：图钉 + 三角网格 + **尽可能保刚** 的形变。

口径（2026-10-01 用户定：GIMP 变换笼做不好就改用 PS 的方案）
------------------------------------------------------------
对齐 Photoshop 的 **操控变形 Puppet Warp**：在图上钉几个图钉（pin），拖某个
图钉时**图钉附近的内容跟着走、离得越远动得越少、没被钉又被钉住的区域基本不动**
（"像扯弹簧"/"像揉面团"）。**不是** PS 的「变形 Warp」（那是有规则网格控制点的
拉伸），也**不是** GIMP 的变换笼。

⚠️ 为什么换掉变换笼（Green 坐标）
--------------------------------
前一版按 GIMP 变换笼实现（Green 坐标闭式系数），**数学逐字对得上 GIMP 源码**
（`green_coefs` 与 `gimpoperationcagecoefcalc.c` 一致，`Σφ≡1`、恒等复现、
相似复现三条性质实测误差均为 0），但有两个绕不过去的问题：

1. 它的形变是**全局**的：拖一个把手，**笼内每个点都在动**，位移缓慢衰减却
   从不归零（实测 100 → 59 → 35 → 16 px）。用户看到的就是"整页歪掉、
   两个弯把图片干得稀碎"。GIMP 里能用是因为**笼只圈一小块**，而本项目的
   默认笼是**贴图边的矩形**（覆盖整幅）⇒ 全局形变作用在整页上。
2. 落地实现里还要做"从形变后位置反解源位置"的**反演**，而正向场只在
   源笼内有定义，反演极易陷入"源笼外位移为零"的假不动点（实测拖 100px
   只有 0.4% 像素变化，即"拖了没反应"）。

**这两条在 Green 坐标路线里是结构性的，不是调参能修的。**
ARAP（As-Rigid-As-Possible）恰好相反：能量函数直接惩罚"每个三角形偏离
刚体旋转"的量，未约束处的解由**拉普拉斯型线性系统**给出，天然是"近处大、
远处衰减"的**局部**形变，且不需要反演（直接用正向解的网格做三角形内插）。

算法：ARAP 表面建模（Sorkine & Alexa, SGP 2007）
----------------------------------------------
1. **建网格**：把图片按 `mesh_cell` 像素切成一格一格的**规则三角网格**
   （每格两个三角形，对角线方向交替以避开规则偏置）。
   顶点 = 网格交点，初始位置 = 图片像素坐标。
2. **图钉**：每个图钉把某个原始网格顶点**钉到**一个新位置（用户拖到的地方）。
   钉住处是**硬约束**（狄利克雷边界），解方程时不参与求解。
3. **能量**：
   ``E = Σ_i Σ_{j∈N(i)} w_ij · ‖(p'_i − p'_j) − R_i (p_i − p_j)‖²``
   其中 ``R_i`` 取"让顶点 i 的 1-邻域最贴合某个旋转"的最优旋转矩阵，
   ``w_ij = (cot α + cot β)/2``（网格是正的三角剖分，余切权重恒正）。
4. **local-global 迭代**（论文口径，交替最小化）：
   - **local**：固定当前顶点位置，对每个顶点 i 由
     ``S_i = Σ_j w_ij (p_i − p_j)(p'_i − p'_j)ᵀ`` 做 **SVD**，
     ``R_i = V Uᵀ``（含翻转修正，见 :func:`_best_rotation`）。
   - **global**：固定所有 ``R_i``，对能量求导得**稀疏对称正定线性系统**
     ``L P' = b``（L = 余切拉普拉斯），解出新的顶点位置。
     钉住处按行替换成单位方程（硬约束），所以"钉在哪就精确在哪"。
   迭代十几次即收敛（残差单调下降），实测整页 4000px 网格只需毫秒级。
5. **取样**：网格只解出**顶点**位移；输出像素落在哪个三角形里，就用该
   三角形的**重心坐标**插值出源坐标，再双线性采样原图。

三条性质是"手感"与"可断言"的关键（自测钉死）：

1. **不乱动**：所有图钉都没挪 ⇒ 网格恒等 ⇒ 输出**逐字节**等于原图。
2. **钉住就准**：图钉落在网格顶点上，硬约束保证该顶点**精确**到位。
3. **衰减 + 局部**：远离被拖图钉方向的位移单调变小；把**被拖图钉周围的
   邻域钉死**（PS 的用法：关节两侧都钉）后，那些钉住处**一动都不动**——
   这正是"近处动得多、远处几乎不动"的可量化版本。

性能
----
**瓶颈在逐像素重采样，不在解方程。**（2026-10-02 全面实测，结论与数量级都
已钉死，改前先读这段，免得重复走弯路。）

1. **重采样 ≈ 0.7 µs/像素**（内存带宽受限，已到 numpy 下界）。1200×900
   (1.08M 像素) 拆开实测：纯双线性采样 336ms、纯重心坐标 101ms、固定开销
   仅 7ms。任何"再优化一点"的尝试（float32 顶点、融合光栅化+采样、扫描线、
   格张量）都只拿到 -15%~+5%，还引入正确性回归 —— **本条路已走到底**。
   ⇒ 唯一的杠杆是**降分辨率预览**（成本随像素数近线性：8 万像素 43ms、
   12 万 72ms、20 万 140ms）。形变场是低频的，预览图再由 Qt 平滑放大，
   肉眼看不出差别。

2. **ARAP 不是局部的**（像素级确认）：拖**一个**图钉 100px，改动区域
   :func:`mesh_region` 仍是整图的 **96~98%**（位移场缓慢衰减但永不归零）。
   ⇒ **"只重算图钉附近"做不到，裁剪 :func:`mesh_region` 也没收益（只省 ~4%）。**

3. **求解耗时随顶点数超线性**：7676 顶点 2.1s、1989 顶点 0.26s、520 顶点
   0.07s。拖动时用 :func:`drag_cell` 给出的**粗网格**（两道约束：相对倍数
   :data:`MESH_DRAG_COARSEN` + 顶点数绝对上限 :data:`MESH_DRAG_MAX_VERTICES`），
   松手 / 应用时才回精网格。⚠️ 只卡"倍数"不够：最密档 20px 在 4000×3000
   下有 3 万顶点，×4 后仍剩 1989 顶点 ≈ 单次求解 103ms，照样卡。

桌面侧的完整降本链见 `image_editor._refresh_deform_preview`（粗网格解 +
按整幅图面积限预算的降分辨率 + 节流）。

几何约定
--------
- 全部用**图片像素坐标**，y 向下（与 QImage 一致）。
- numpy 一律**延迟导入**：桌面主进程要 import 本模块（只为拿函数引用），
  启动路径不能因此背上 numpy 的成本。

### 模块常量

| 名称 | 值 |
| --- | --- |
| MESH_CELL_DEFAULT | `40.0` |
| MESH_MAX_VERTICES | `200000` |
| ARAP_ITERATIONS | `12` |
| ARAP_DRAG_ITERATIONS | `4` |
| ARAP_TOLERANCE | `0.001` |
| ARAP_DRAG_TOLERANCE | `0.005` |
| MESH_DRAG_COARSEN | `4.0` |
| MESH_DRAG_MAX_VERTICES | `600` |
| COINCIDENT | `1e-06` |
| WARP_BBOX_LIMIT | `200000` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `grid_cell(width: int, height: int, cell: float \| None=None) -> float` | 按图片尺寸与目标格距算出**实际格距**（夹在护栏内）。 |
| `drag_cell(width: int, height: int, cell: float \| None=None) -> float` | **拖动中**用的格距：在 :func:`grid_cell` 基础上再粗化到顶点数上限内。 |
| `build_mesh(width: int, height: int, cell: float \| None=None)` | 建规则三角网格：返回 ``(vertices, triangles, cols, rows, cell)``。 |
| `nearest_vertex(vertices, point) -> int` | 离 ``point`` 最近的网格顶点下标（图钉吸附到网格顶点用）。 |
| `cotangent_weights(vertices, triangles)` | 三角网格上的**余切权重**：``(edge_i, edge_j, weights)`` 三个等长数组。 |
| `build_laplacian(edge_i, edge_j, weights, n_vertices)` | 余切拉普拉斯矩阵 ``L``（稀疏 CSR）：``L[i,i] = Σ_j w_ij``， |
| `solve_arap(vertices, triangles, pins, *, iterations: int=ARAP_ITERATIONS, tolerance: float=ARAP_TOLERANCE)` | 解 ARAP：``pins`` = ``[(顶点下标, (x, y)), ...]`` 硬约束 → 返回新顶点。 |
| `border_vertices(vertices, width: int, height: int)` | 贴图片四边的网格顶点下标（**隐式锚点**，见 :func:`solve_puppet`）。 |
| `solve_puppet(vertices, triangles, pins, *, width: int \| None=None, height: int \| None=None, anchor_border: bool=True, iterations: int=ARAP_ITERATIONS, tolerance: float=ARAP_TOLERANCE)` | **面向交互**的入口：把图钉 + 隐式边框锚点合起来解 ARAP。 |
| `puppet_warp(src, vertices_rest, vertices_moved, triangles, *, fill=FILL, block: int=BLOCK_PIXELS, grow: bool=False, progress=None)` | 把 ``vertices_rest → vertices_moved`` 的网格形变应用到 ``src``。 |
| `qimage_to_rgba(image)` | QImage → ``(H, W, 4)`` uint8 **RGBA**（ARGB32 在小端机器上是 B,G,R,A）。 |
| `array_to_qimage(rgb)` | ``(H, W, 3\|4)`` uint8 → QImage（ARGB32）；3 通道按不透明处理。 |
| `puppet_warp_qimage(image, vertices_rest, vertices_moved, triangles, *, fill=None, grow=False, progress=None)` | QImage 版 :func:`puppet_warp`（**保留 alpha 通道**）。 |
| `mesh_region(vertices_rest, vertices_moved, width: int, height: int)` | 这次形变**实际会改动的矩形区域**（图片坐标，开区间右端）。 |
| `mesh_moved(vertices_rest, vertices_moved, epsilon: float=1e-06) -> bool` | 网格是否有实质变化（区分"钉过但没挪"与"真变形"）。 |

#### `grid_cell(width: int, height: int, cell: float | None=None) -> float`

按图片尺寸与目标格距算出**实际格距**（夹在护栏内）。

``cell`` 缺省用 :data:`MESH_CELL_DEFAULT`；顶点数超过
:data:`MESH_MAX_VERTICES` 时自动放大格距（超大图兜底，不让内存爆掉）。

#### `drag_cell(width: int, height: int, cell: float | None=None) -> float`

**拖动中**用的格距：在 :func:`grid_cell` 基础上再粗化到顶点数上限内。

两道约束叠加（取更粗的那个）：

1. **相对粗化**：``cell × MESH_DRAG_COARSEN``——保住"粗网格解出的形变
   趋势与精网格一致"这一点；
2. **绝对上限**：顶点数不超过 :data:`MESH_DRAG_MAX_VERTICES`——挡住
   "原格距本就很密"的情形（最密档 20px 在 4000×3000 下有 3 万顶点，
   乘 4 仍剩 1989，单次求解 103ms）。

⚠️ 这是"拖动卡死"的第二道关键手段（第一道是降分辨率预览）。ARAP 求解
耗时随顶点数**超线性**增长，只控倍数不控绝对量，最密档照样卡。

#### `build_mesh(width: int, height: int, cell: float | None=None)`

建规则三角网格：返回 ``(vertices, triangles, cols, rows, cell)``。

- ``vertices``：``(N, 2)`` 网格交点（图片像素坐标）。
- ``triangles``：``(M, 3)`` 三角形顶点下标，每格两个三角，
  **对角线交替**（棋盘式翻转）——全用同一方向的对角线会让网格在
  某个方向偏硬，交替后各向同性得多（这是标准做法）。
- ``cols``/``rows``：**格数**（顶点数各 +1）。
- ``cell``：实际格距。

网格严格覆盖 ``[0, width-1] × [0, height-1]``（末行/末列贴到图边），
所以"图片四角"永远是网格顶点——用户在图角钉钉时能钉到。

#### `cotangent_weights(vertices, triangles)`

三角网格上的**余切权重**：``(edge_i, edge_j, weights)`` 三个等长数组。

每条**无向边只出现一次**（``i < j``），权重 ``w_ij = (cot α + cot β)/2``
（α/β 是该边两侧三角形在**对角顶点处**的内角）。

⚠️ **本函数返回的权重恒为正**，这是 ARAP 能量的前提（能量
``Σ w_ij‖·‖²`` 要求 ``w_ij > 0``，否则最小化会退化）。做法是取
``cot = dot / |cross|``：``|cross|`` 抹掉了三角形**
绕向**（CW/CCW）带来的符号，只留下几何意义上的余切。规则网格的对角
不超过 45°，两对角之和 < 90°，故 ``cot α + cot β > 0`` 恒成立。

⚠️ 前一版用 ``cross``（带符号）作分母，遇到 :func:`build_mesh` 里
``(r+c)%2==0`` 那一支产出的 **CW 三角形**时，全部 ``cot`` 变负、
``degree`` 变负，归一化时除以 ``sqrt(负×负)`` 后放大到 **1e12**，
右端项直接爆成 4e13 —— 解出来就是"整页平移 167px"（探针实测）。
**符号必须在这里就地掐掉。**

同一条边被两个三角形共享时权重**累加**（先收集再按边 key 归并）。

#### `build_laplacian(edge_i, edge_j, weights, n_vertices)`

余切拉普拉斯矩阵 ``L``（稀疏 CSR）：``L[i,i] = Σ_j w_ij``，
``L[i,j] = −w_ij``（对称）。

求解时钉住处按行替换成单位方程（见 :func:`solve_arap`），所以这里
返回**未加约束**的矩阵，由调用方按需改行。

#### `solve_arap(vertices, triangles, pins, *, iterations: int=ARAP_ITERATIONS, tolerance: float=ARAP_TOLERANCE)`

解 ARAP：``pins`` = ``[(顶点下标, (x, y)), ...]`` 硬约束 → 返回新顶点。

没给任何图钉（或图钉位置与初始一致）时直接返回 ``vertices`` 的副本——
恒等形变**不做任何计算**（自测钉死"逐字节还原"）。

local-global 交替：
- **local**：``R_i`` 取 :func:`_best_rotation` ``S_i`` 的 SVD 最优旋转，
  ``S_i = Σ_j w_ij (p_i−p_j)(p'_i−p'_j)ᵀ``；
- **global**：解 ``L P' = b``，``b_i = Σ_j (w_ij/2)(R_i+R_j)(p_i−p_j)``。

⚠️ **硬约束的正确消元**（前一版错在这里，症状是"钉了不动也整页乱飞"）：
钉住顶点的未知量要**同时**做两件事——① 在自由顶点的方程里把 ``L[i,k]·t_k``
挪到右端；② **把该列从矩阵里清成 0**（再用单位行覆盖钉住行）。
前一版只做了 ① 没做 ②，于是 ``A[i,k]`` 仍留着 ``−w_ik``，与右端里已经
挪走的 ``t_k`` **重复计入**，等价于把约束位置算了两次 —— 实测"两个图钉
都不挪"竟解出 202px 的整页位移（正确解应是 0）。

#### `border_vertices(vertices, width: int, height: int)`

贴图片四边的网格顶点下标（**隐式锚点**，见 :func:`solve_puppet`）。

⚠️ 这条是 Puppet Warp 能"稳住"的关键，必须理解：
ARAP 能量只惩罚"三角形偏离刚体旋转"，**对整体平移/旋转不变**。所以只钉
一个图钉时，整张网格可以靠"一起平移"来满足它 —— 实测（400×300，格距
40）只钉一个图钉拖 37px，**每个顶点都平移 14.269px**，完全是"整页漂移"。
Photoshop 的做法是默认把**画布边界**视为固定：拖内部图钉时边框被拉住，
形变才收敛成"近处大、远处为零"。

返回贴住 ``x∈{0, width-1}`` 或 ``y∈{0, height-1}`` 的顶点下标数组。

#### `solve_puppet(vertices, triangles, pins, *, width: int | None=None, height: int | None=None, anchor_border: bool=True, iterations: int=ARAP_ITERATIONS, tolerance: float=ARAP_TOLERANCE)`

**面向交互**的入口：把图钉 + 隐式边框锚点合起来解 ARAP。

- ``anchor_border=True``（默认，PS 口径）时自动把
  :func:`border_vertices` 里的顶点按**原位**钉住，作为边界约束；
  否则一个图钉会让整页一起平移（见 :func:`border_vertices` 的说明）。
- ``width``/``height`` 缺省时由 ``vertices`` 的包围盒推出（网格严格覆盖
  ``[0, w-1]×[0, h-1]``）。
- 用户图钉与边框锚点若有重合，以**用户图钉**为准（后者被覆盖，避免
  同一顶点两个目标位置）。

返回新的顶点数组。``pins`` 为空且 ``anchor_border=False`` 时原样返回。

#### `puppet_warp(src, vertices_rest, vertices_moved, triangles, *, fill=FILL, block: int=BLOCK_PIXELS, grow: bool=False, progress=None)`

把 ``vertices_rest → vertices_moved`` 的网格形变应用到 ``src``。

逐像素重映射（**正向解网格 + 三角形重心插值**，不做反演）：
对每个输出像素，找到它落在**形变后网格**的哪个三角形里 ⇒ 用该三角形的
重心坐标在**形变前网格**上插值出源坐标 ⇒ 双线性采样。

``src`` 支持 (H, W) 与 (H, W, C)。网格没动过时**逐字节**返回原图。
``block`` 保留仅为兼容旧调用（现实现不再分块）。

``grow=True``：网格顶点被拖出原边界时**不裁**，画布放大到
「原图 ∪ 形变后网格外接框」（用户 2026-10-02：「超出原本区域的不要截，
最终结果按最后图片的范围」）。返回 ``(out, (ox, oy))``，``(ox, oy)`` =
新画布左上角在原坐标系里的位置（可为负）。

``progress`` 给定时在**三个粗阶段**回调 ``progress(stage, 3)``
（扫描线栅格化 → 双线性采样 → 完成）；返回 ``False`` 则中止并返回
``None``。这里只在粗粒度上报（实现是整表向量化，没有可切分的分块循环，
见 ``utils.puppet_warp`` 的「性能」）——只为让画布侧的长任务有进度可示、
可被取消。

#### `qimage_to_rgba(image)`

QImage → ``(H, W, 4)`` uint8 **RGBA**（ARGB32 在小端机器上是 B,G,R,A）。

⚠️ 必须把 alpha 带上。桌面侧编辑的常常是第三步产物"**白底透明 PNG**"：
透明像素的 RGB 分量存的是 0，一旦只取 RGB 丢掉 alpha，整片背景就读成
**黑色**（用户 2026-10-01 报的"变形后图片变成黑色"就是这个）。

#### `puppet_warp_qimage(image, vertices_rest, vertices_moved, triangles, *, fill=None, grow=False, progress=None)`

QImage 版 :func:`puppet_warp`（**保留 alpha 通道**）。

不透明图走 3 通道（比 4 通道少 1/4 的采样量）；带 alpha 的图走 4 通道，
越界填充取 :data:`FILL_CLEAR`（白 + 透明），免得透明底变实心。

``grow=True``：网格被拖出原边界时不裁，画布放大，返回
``(QImage, (ox, oy))``（见 :func:`puppet_warp`）。``grow=False``（默认）
返回单个 ``QImage``，与原行为逐字节一致。

``progress`` 透传给 :func:`puppet_warp`（粗阶段回调，返回 ``False``
则中止并返回 ``None``）。

#### `mesh_region(vertices_rest, vertices_moved, width: int, height: int)`

这次形变**实际会改动的矩形区域**（图片坐标，开区间右端）。

取"移动过的网格顶点"的包围盒——网格没动的部分逐字节等于原图，
画布侧的预览浮层贴在框外也不会留接缝。返回 ``(x0, y0, x1, y1)``；
没动过返回 ``(0, 0, 0, 0)``。

---

## `utils.sort_utils`

源码：[`utils/sort_utils.py`](../../utils/sort_utils.py)

自然排序工具：支持封面/菜单优先与数字感知排序。

用于文件列表排序，使 "page2, page10" 按数值 2 < 10 排序而非字典序 "10" < "2"。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `natural_sort_key(filename: str) -> tuple` | 生成自然排序键，封面和菜单排在最前。 |
| `pdf_custom_sort_key(file_path: str) -> tuple` | 生成 PDF 页面排序键（古籍双页扫描件的阅读顺序）。 |

#### `natural_sort_key(filename: str) -> tuple`

生成自然排序键，封面和菜单排在最前。

排序规则:
1. 优先级：cover*.png 和 menu.png 排在所有文件之前（priority=0）；
2. 数字感知：将文件名拆分为 [文字, 数字, 文字, ...] 序列，
   数字部分按整数值比较而非字符串比较。

参数:
    filename: 文件名（含扩展名）。

返回:
    (priority, natural_key) 元组，可直接用于 sort/sorted 的 key 参数。

示例:
    >>> files = sorted(["page10.png", "page2.png", "cover.png", "page3.png"],
    ...                key=natural_sort_key)
    >>> [f.name for f in files]
    ['cover.png', 'page2.png', 'page3.png', 'page10.png']

#### `pdf_custom_sort_key(file_path: str) -> tuple`

生成 PDF 页面排序键（古籍双页扫描件的阅读顺序）。

分级规则，逐级比较：

1. ``cover*`` 优先，编号小的在前；
2. ``menu`` 次之；
3. 形如 ``<页号>`` / ``<页号>-l`` / ``<页号>-r``（``_`` 亦可）的图片：
   先按页号数值，再按侧边 ``r → l → 无后缀``——双页扫描件右侧页先读；
4. 其余文件按文件名排在最后。

参数:
    file_path: 文件路径或文件名，内部只取 basename。

返回:
    ``(优先级, 页号, 侧边)`` 或 ``(999, 0, 文件名)`` 元组。

---

## `utils.string_utils`

源码：[`utils/string_utils.py`](../../utils/string_utils.py)

数字转中文等字符串辅助工具。

当前提供：

- ``num_to_chinese``：整数转中文数字（支持万以内）；
- ``num_to_ganzhi``：整数转**干支**（六十甲子，古籍册次/卷次常用）；
- ``format_page_number``：按「样式 + 前缀 + 后缀」拼出页码文本——第四步
  页码样式的**唯一组装处**（PDF 与预览共用同一份）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `num_to_chinese(num: int) -> str` | 将整数转换为中文数字（支持万以内）。 |
| `num_to_ganzhi(num: int) -> str` | 将整数转换为干支纪序（六十甲子）：1 → 甲子，2 → 乙丑，61 → 甲子。 |
| `format_page_number(num: int, style: str='chinese', prefix: str='', suffix: str='') -> str` | 按「样式 + 前缀 + 后缀」拼出页码文本（第四步页码的唯一组装处）。 |

#### `num_to_ganzhi(num: int) -> str`

将整数转换为干支纪序（六十甲子）：1 → 甲子，2 → 乙丑，61 → 甲子。

古籍的册次/卷次常用干支编号。天干 10 与地支 12 的最小公倍数是 60，
所以序号按 60 循环（超过 60 从头再来，不会越界）。非正整数退化为
阿拉伯数字，保证任何输入都有可打印的结果。

#### `format_page_number(num: int, style: str='chinese', prefix: str='', suffix: str='') -> str`

按「样式 + 前缀 + 后缀」拼出页码文本（第四步页码的唯一组装处）。

- ``chinese``：中文数字（五），``num_to_chinese``；
- ``arabic``：阿拉伯数字（5）；
- ``ganzhi``：干支（甲子，60 循环）；
- 认不出的样式按中文数字处理——老配置里可能存着别的值，回落成中文
  比抛异常或印出空串都好。

前缀/后缀是**原样拼接**的（不做空格补全）：想排「第 5 页」就把前缀写成
``"第 "``。空前缀/后缀表示只要数字本身。

---

## `utils.transparent_png`

源码：[`utils/transparent_png.py`](../../utils/transparent_png.py)

「白底 → 透明底」的 PNG 编码：**唯一实现**。

只作用于第三步「提交本次任务」写出的最终图片（``stages/rembg/*.png``），
不碰去底产物本身、也不碰 PDF。

为什么值得单独一个模块
----------------------
这个规则同时决定两件容易漂移的事：**哪些像素算白底**、**用哪种编码最省空间**。
散在调用方（``desktop/stages/rembg_stage.py``）里，下一处再要透明 PNG 就会
各抄一份、判据各写一套。

编码形态与实测（5000×4400 仿古籍页，见
``.workbuddy/perf/bench_transparent_submit_2026-09-30.py``）：

===========================  ==============  =========  ==================
页内容                        编码形态         体积        对比旧写法
                          （PNG 头）                   （Qt 直存 RGB24）
===========================  ==============  =========  ==================
纯黑白（type=1/2，主流）      位深 1 调色板    0.011MB     6.7× 小、3.2× 快
灰度（type=3）               位深 2~8 调色板  0.015MB     5× 小、3.3× 快
彩色（sealcolor 印章原色）    RGBA8          0.095MB     体积略增（必须无损）
===========================  ==============  =========  ==================

三条硬约定（改动前先读）
------------------------
1. **判据只看像素，不看 ``type`` 参数**。提交阶段的图是「去底预览图经
   ``compose_region_output`` 合成」出来的 Qt ``Format_RGB32``，而面板的
   ``type`` 与预览可能不同步（改了参数没重新生成预览也能提交）——按像素
   判定才不会写错。
2. **透明像素的 RGB 保持 255，不清零**。第四步缩略图是 JPEG，Qt 丢 α 时直接
   取 RGB；清零就会把缩略图显示成黑底（``tools/make_icon.py`` 里那套
   「清零防预乘淡边」的做法在这里**不适用**）。
3. ⚠️ PIL 的 ``save(mode="P", transparency=N)`` 里 N 是**首个透明项的调色板
   下标**（实现为写 ``b"\xff"*N + b"\x00"`` 再按调色板项数截断），不是灰度
   值：传 255 而调色板只有 2 项 → tRNS 变成 ``[255, 255]``，**一个透明项都
   没写进去**，而且不报错。位深不用手写：不传 ``bits`` 时 PIL 按调色板项数
   自动取 1/2/4/8。

### 模块常量

| 名称 | 值 |
| --- | --- |
| WHITE_LEVEL | `255` |
| PNG_COMPRESS_LEVEL | `6` |
| _GRAY_LEVELS | `256` |
| _COMPACT_PALETTE_MAX | `16` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `save_white_as_transparent(rgb: np.ndarray, path: str \| Path, *, compress_level: int=PNG_COMPRESS_LEVEL) -> dict` | 把「白底图」写成白底透明的 PNG，自动选最省的编码形态。 |
| `describe_encoding(rgb: np.ndarray) -> Optional[dict]` | 只算编码形态、不落盘（日志/护栏用，判据与 ``save_white_as_transparent`` 同源）。 |

#### `save_white_as_transparent(rgb: np.ndarray, path: str | Path, *, compress_level: int=PNG_COMPRESS_LEVEL) -> dict`

把「白底图」写成白底透明的 PNG，自动选最省的编码形态。

参数:
    rgb: (H, W, 3) 的 RGB 数组（``uint8``）；多于 3 通道时只用前 3 个。
    path: 输出 PNG 路径（调用方负责目录已存在）。
    compress_level: PNG 压缩级别（0~9）。

返回:
    ``{"encoding": "P"|"RGBA", "colors": int|None, "bits": int, "bytes": int}``，
    供调用方打日志/统计；失败会直接抛异常（不静默降级成白底）。

---

## `utils.units`

源码：[`utils/units.py`](../../utils/units.py)

长度单位换算常量（mm / inch / pt 互转的唯一定义处）。

这些值此前在 ``utils/page_layout.py``、``utils/pdf_utils.py``、
``functions/print.py`` 各写一份（``MM_PER_INCH = 25.4`` 三处、
``POINTS_PER_MM`` 两处），``utils/box_geometry.py`` 里还散着裸的 ``25.4``。
换算常量是**客观值**，本来就不该有第二份——改一处漏两处时又查不出来
（值都一样，不会报错，只会悄悄各走各的）。

依赖方向：本模块不 import 任何东西，是 ``utils`` 的最底层，任何层都可引用。

### 模块常量

| 名称 | 值 |
| --- | --- |
| MM_PER_INCH | `25.4` |
| DEFAULT_RENDER_DPI | `300` |
| POINTS_PER_INCH | `72.0` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `mm_to_px(mm: float, dpi: float) -> float` | 毫米 → 像素（按给定 DPI）。 |
| `px_to_mm(px: float, dpi: float) -> float` | 像素 → 毫米（按给定 DPI）。 |

---

## `utils.yolo_utils`

源码：[`utils/yolo_utils.py`](../../utils/yolo_utils.py)

YOLO 检测封装：模型加载与页面内容框检测。

此模块封装了 YOLO 目标检测模型的使用，提供两个核心功能：

1. **模型加载** (`load_yolo_model`)
   延迟加载 + 模块级单例 + 双重检查锁，确保多线程下模型只加载一次。
   权重文件查找路径: `gujitools/static/weights/bookcontent.pt`。

2. **页面内容框检测** (`detect_content_boxes`)
   权重 `static/weights/bookcontent.pt` 是**两类**模型，两类对一页而言互斥：

   - ``harfcontent``（半幅，即原 `bookcontent` 改名）——双栏排版中的**一栏**。
     双页扫描时一页出左右两栏，故按检测框水平中心与图像中线的关系分为
     left / right 两组，供 crop / cropremove 使用；
   - ``fullcontent``（整幅）——整页只有一个内容区（单页排版）。它**只有
     一个框**，不参与左右分割，否则会被中线误判成某一半。

   ⚠️ **类别名决定路由，不靠几何猜**：`harfcontent` 的框宽实测约 43%、
   `fullcontent` 约 95%，但单栏书的 ``harfcontent`` 框也可能横跨整幅
   （实测最宽 98.5%）。用宽度阈值区分二者并不可靠，所以一律按模型的
   **类别号**路由（类别号由 `model.names` 按**类名**解析，见
   :func:`_content_class_ids`）。

   模型偶尔会在同一页同时给出两类（实测把推理尺寸调到 1280 时会出现
   「整幅-半幅-整幅-半幅」四个框），因此检测后按**互斥规则**强制消解
   （见 :func:`resolve_content_boxes`）：窄整幅剔除 → 双半幅压制整幅 →
   单半幅与整幅比置信度。返回结果保证两类互斥，`notes` 说明触发了哪条规则。

左右分割算法（仅对半幅）:
    以图像宽度一半为分界线，检测框中心 cx < w/2 归入 left，否则归入 right。
    每组按面积降序排序，调用方取 [0] 即可获得最大候选框。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _YOLO_MODEL | `None` |
| _LOAD_SECONDS | `0.0` |
| _YOLO_DEVICE | `"cpu"` |
| CONTENT_CLASS_HARF | `"harfcontent"` |
| CONTENT_CLASS_FULL | `"fullcontent"` |
| FULL_MIN_WIDTH_RATIO | `0.7` |

### `class ContentBoxes(NamedTuple)`

一页的内容框检测结果（**已按互斥规则消解**），按类别分流。

属性:
    left_boxes: 半幅框中中心在中线左侧的（面积降序）。
    right_boxes: 半幅框中中心在中线右侧的（面积降序）。
    full_boxes: 整幅框（面积降序，至多一个）。
    notes: 互斥消解**实际触发**的规则说明（人读，供调用方打日志）；
        没有触发任何规则时为空元组。消解之后两类必然互斥，
        因此 left/right 与 full 不会同时非空。

每个 box = ``(x1, y1, x2, y2, area, conf)``，坐标为整数像素值。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `model_path() -> Path` | YOLO 权重文件路径（候选表只保留这一份）。 |
| `is_model_loaded() -> bool` | 本进程是否已加载过 YOLO（常驻服务用它对外汇报，便于确认复用）。 |
| `load_seconds_used() -> float` | 本进程**实际执行**加载模型时花掉的秒数；没加载过则为 0.0。 |
| `load_yolo_model() -> object` | 延迟加载 YOLO 模型并返回单例实例。 |
| `resolve_content_boxes(raw_boxes, img_w: float, harf_id: int, full_id: int) -> Tuple[List[tuple], List[tuple], List[tuple], Tuple[str, ...]]` | 按**互斥规则**消解 harfcontent / fullcontent，返回 (left, right, full, notes)。 |
| `detect_content_boxes(image_bgr: np.ndarray, model: object) -> ContentBoxes` | 使用 YOLO 检测页面内容框，按类别分流并按**互斥规则消解**。 |

#### `model_path() -> Path`

YOLO 权重文件路径（候选表只保留这一份）。

权重路径同时被三处用到——真正加载模型、给用户打印、以及常驻 YOLO 服务的
身份指纹（见 `functions/yolo_service.py`）。三处各写一遍候选列表迟早会
漂移，所以统一收在这里。

返回:
    `gujitools/static/weights/bookcontent.pt` 的绝对路径。

异常:
    FileNotFoundError: 权重文件不存在（打包遗漏或安装损坏）。

#### `load_seconds_used() -> float`

本进程**实际执行**加载模型时花掉的秒数；没加载过则为 0.0。

调用方（常驻服务）据此把这笔开销**单独报一次**，而不是算进某一张图的
检测耗时——"第一张图要 5 秒"看起来像图的问题，其实是模型在加载。

#### `load_yolo_model() -> object`

延迟加载 YOLO 模型并返回单例实例。

使用双重检查锁定（double-checked locking）确保线程安全：
先无锁检查 → 再加锁检查 → 最后加载，避免每次调用都竞争锁。

⚠️ 单例只保证**进程内**复用。跨进程复用模型要靠常驻服务
（`functions/yolo_service.py`）——每次点「检测」都是新的 worker 子进程，
进程一退模型就没了，这里再单例也救不了第二次调用。

返回:
    ultralytics.YOLO 实例（CPU 模式）。

异常:
    FileNotFoundError: 未找到 static/weights/bookcontent.pt。

#### `resolve_content_boxes(raw_boxes, img_w: float, harf_id: int, full_id: int) -> Tuple[List[tuple], List[tuple], List[tuple], Tuple[str, ...]]`

按**互斥规则**消解 harfcontent / fullcontent，返回 (left, right, full, notes)。

与参考实现 `gujitrain/test/predict_bookcontent.py::resolve_boxes` **同规则**
（规则顺序即优先级）：

1. **窄整幅剔除**：整幅框宽必须 > ``img_w × FULL_MIN_WIDTH_RATIO``（0.70），
   否则判为失败检测直接剔除；
2. **双半幅压制整幅**：harfcontent ≥ 2 个 → 整幅框一律不存在（全删）——
   两栏都检出来了，整幅一定是错的；
3. **单半幅与整幅比置信度**：harfcontent 恰好 1 个 → 取置信度最高的整幅框
   与它比，整幅**严格更高**才留整幅（平局留半幅）；没有 harfcontent 时
   整幅原样保留。

参数:
    raw_boxes: 模型原始输出 ``[(cls_id, conf, x1, y1, x2, y2), …]``，未过滤。
    img_w: 图像宽度（规则1 的基准）。
    harf_id / full_id: 两类各自的类别号；``-1`` 表示该类不存在。

返回:
    ``(left_boxes, right_boxes, full_boxes, notes)``。前三个均为面积降序的
    ``(x1,y1,x2,y2,area,conf)``；``notes`` 是消解说明（人读，只含**真的触发**
    的规则）。

⚠️ 「两类互斥」是就**已登记的两个类别**而言的：未知类别（将来若再添类别）
一律按半幅处理、且**不参与**上述三条规则的计数与置信度比较——既不丢框，
也不会让它误压制整幅框。真出现第三类时，应把它当作新的语义在
`PageBoxes` / 槽位约定里显式建模，而不是靠这里兜底。

#### `detect_content_boxes(image_bgr: np.ndarray, model: object) -> ContentBoxes`

使用 YOLO 检测页面内容框，按类别分流并按**互斥规则消解**。

算法:
1. 模型推理，取全部框的 ``(类别, 置信度, 坐标)``；
2. 按类别号分流（``fullcontent`` 与其余分开）；
3. 调用 :func:`resolve_content_boxes` 消解两类冲突（窄整幅剔除、双半幅压制
   整幅、单半幅与整幅比置信度），保证返回结果**两类互斥**；
4. 半幅框按中线分左右，各组按面积降序（最大框排在 [0]）。

参数:
    image_bgr: BGR 格式图像（cv2 读取的默认格式）。
    model: YOLO 模型实例。

返回:
    :class:`ContentBoxes`（已消解；`notes` 说明触发了哪条规则）。

---
