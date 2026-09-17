<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# utils API 参考

通用工具函数：几何、排序、图像 IO、PDF、YOLO

覆盖 13 个模块、2 个公开类、50 个公开函数/方法（生成于 2026-09-17）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`utils.box_draw`](#utilsbox_draw) | 0 | 4 |
| [`utils.box_geometry`](#utilsbox_geometry) | 2 | 4 |
| [`utils.color_utils`](#utilscolor_utils) | 0 | 2 |
| [`utils.file_utils`](#utilsfile_utils) | 0 | 2 |
| [`utils.help`](#utilshelp) | 0 | 7 |
| [`utils.image_io`](#utilsimage_io) | 0 | 2 |
| [`utils.image_utils`](#utilsimage_utils) | 0 | 6 |
| [`utils.margin_utils`](#utilsmargin_utils) | 0 | 2 |
| [`utils.path_utils`](#utilspath_utils) | 0 | 2 |
| [`utils.pdf_utils`](#utilspdf_utils) | 0 | 14 |
| [`utils.sort_utils`](#utilssort_utils) | 0 | 2 |
| [`utils.string_utils`](#utilsstring_utils) | 0 | 1 |
| [`utils.yolo_utils`](#utilsyolo_utils) | 0 | 2 |

---

## `utils.box_draw`

源码：[`utils/box_draw.py`](../../utils/box_draw.py)

File: utils/box_draw.py
在图片上绘制检测框标注（供 CLI `detect --save` 与 GUI 预览共用）。

**为什么放在 utils**：CLI 的 `guji detect --save` 要把左右框画到图片上落地，
GUI 的预览控件也要画同样的框。配色与命名必须一致，否则「命令行看到的」
和「界面看到的」是两套东西。因此视觉约定集中在这里：

- 左框 `#21c178`（绿）、右框 `#3b82f6`（蓝）、合并框 `#f59e0b`（橙）；
- 标注文字为「左框 (x1,y1,x2,y2)」。

**中文字体**：OpenCV 的 `putText` 不支持中文（会画成 `????`），因此文字用
PIL 绘制。字体按 `utils.pdf_utils.register_fonts` 相同的候选顺序探测
Windows 系统中文字体；全部缺失时退化为 ASCII 标签（`L` / `R` / `U`），
保证任何环境下都不会崩。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `find_cjk_font() -> Optional[str]` | 返回可用的中文字体路径；都没有则返回 None。结果会缓存。 |
| `box_color(index: int) -> Tuple[int, int, int]` | 按框序号取 BGR 颜色。 |
| `box_name(index: int) -> str` | 按框序号取中文名（左框/右框/合并框）。 |
| `draw_boxes(img_bgr, boxes: Sequence[Optional[Sequence[int]]], thickness: int=4, show_label: bool=True, color=None)` | 在图像上绘制一组框（原地绘制并返回新图，不修改入参）。 |

#### `draw_boxes(img_bgr, boxes: Sequence[Optional[Sequence[int]]], thickness: int=4, show_label: bool=True, color=None)`

在图像上绘制一组框（原地绘制并返回新图，不修改入参）。

参数:
    img_bgr: BGR 图像数组。
    boxes: 框列表，每项为 ``(x1, y1, x2, y2)``；``None`` 项被跳过
        （用于「只检出一侧」的常见情形，保持左右序号不串位）。
    thickness: 线宽（像素）。会随图像尺寸自适应放大，避免大扫描图上
        细线看不清。
    show_label: 是否绘制「左框 (x1,y1,x2,y2)」这类标注。
    color: 指定线条颜色 (B,G,R)；None 时按框序号取默认色。

返回:
    绘制后的 BGR 图像（新数组）。

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
| `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]` | 解析 border 参数（毫米单位），按 DPI 转换为像素。 |
| `compute_final_boxes(boxes, area: int, border_mm, dpi: int=300) -> List[List[int]]` | 按 crop 命令的 area/border 规则计算最终切割框（原始图片坐标）。 |
| `build_output_layout(boxes: Sequence[Sequence[int]], area: int, border_padding, image_size: Tuple[int, int], dpi: int=300, sides: Optional[Sequence[Optional[str]]]=None, symmetric: bool=False) -> OutputLayout` | 按 area/border 规则计算输出画布布局（area=1 / 2 / 3）。 |
| `build_symmetric_layout(box: Sequence[int], border_padding, image_size: Tuple[int, int], is_left: bool=True, dpi: int=300) -> OutputLayout` | 单框对称输出布局：实际框 + 空白镜像 + 中间间隔。 |

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

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `calculate_auto_threshold(pixels: np.ndarray) -> int` | 大津法（Otsu）计算最佳阈值。 |
| `extract_red_seal(rgb_img: np.ndarray, min_seal_area: int, min_saturation: int) -> Tuple[np.ndarray, bool]` | 从 RGB 图像中提取红色印章掩码。 |
| `apply_otsu_to_region(img_rgb: np.ndarray, gray: np.ndarray, roi_box: tuple, threshold: int, enable_seal: bool, seal_color: bool, red_mask: Optional[np.ndarray], img_type: int=1) -> np.ndarray` | 对图像中指定矩形区域执行去底色处理，返回 ROI 大小的结果数组。 |
| `apply_otsu_whole(img_rgb: np.ndarray, gray: np.ndarray, threshold: int, red_mask: Optional[np.ndarray], seal_color: bool, img_type: int=1) -> np.ndarray` | 对整张图执行去底色处理，返回与输入同尺寸的结果数组。 |
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
utils.pdf_utils.parse_margins、desktop 面板 parse_margin4），消除了
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

## `utils.path_utils`

源码：[`utils/path_utils.py`](../../utils/path_utils.py)

路径工具函数，用于解析各种命令的输出目录。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `resolve_final_output_dir(input_path: Path, output_arg: Optional[str], is_file: bool, default_subdir: str) -> Path` | 计算命令的最终输出目录（适用于 crop/rembg/cropremove 等）。 |
| `get_extract_output_root(input_path: Path, output_arg: Optional[str], is_file: bool) -> Path` | 计算 extract 命令的输出根目录（out_root）。 |

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

## `utils.pdf_utils`

源码：[`utils/pdf_utils.py`](../../utils/pdf_utils.py)

PDF 页面提取工具：将 PDF 每页渲染为图片并保存。

此模块是 `extract` 功能的核心实现层，负责：

1. **页码解析** (`parse_pages` / `validate_page_range`)
   支持两种页码选择方式：逗号分隔 + 范围字符串（如 "1,3-5,7"）或 start/end 整数对。

2. **缩放计算** (`calculate_zoom`)
   根据页面宽度限制最大输出尺寸（6000px），避免内存溢出。

3. **批量渲染** (`process_page_batch` / `render_pages_parallel` / `extract_pdf_optimized`)
   使用 PyMuPDF (fitz) 渲染页面，支持两种模式：
   - quick=True：优先取 PDF 内嵌图片（**自适应**，不满足条件自动降级整页渲染）；
   - quick=False：直接渲染页面为高质量图片。

   quick 的判定见 `_embedded_page_image()`：只有「单张内嵌图 + jpg/png 格式 +
   像素不低于整页渲染尺寸」才走快路径，否则降级。这样 jp2/jbig2/CCITT 压缩、
   一页多图、内嵌缩略图这三类情况不会"为了快而变慢或变糊"。

4. **目录遍历** (`run_on_input_directory`)
   支持输入为单个 PDF 文件或包含多个 PDF 的目录。
   统一为每个 PDF 在输出根目录下创建以 PDF 文件名命名的子目录，并在其下创建 images 子目录存放图片。

依赖: PyMuPDF (pymupdf), Pillow (PIL)。

### 模块常量

| 名称 | 值 |
| --- | --- |
| QUICK_MIN_COVERAGE | `0.9` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `parse_pages(pages_str: str, total_pages: int) -> List[int]` | 解析页码字符串为 0-based 页码列表。 |
| `validate_page_range(start: Optional[int], end: Optional[int], total_pages: int) -> List[int]` | 根据 start/end 整数对生成 0-based 页码列表。 |
| `calculate_zoom(page_width: float, requested_zoom: float=1) -> float` | 计算实际缩放因子，限制最大输出宽度为 6000px。 |
| `report_image_size(img_path, width: int, height: int, reporter=None) -> None` | 汇报一页输出图片的尺寸。 |
| `process_page_batch(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, progress: dict=None, reporter=None) -> List[bool]` | 处理一批 PDF 页面，返回每页的成功状态。 |
| `render_pages_parallel(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, workers: int=4, batch_size: int=4, progress: dict=None, reporter=None) -> List[bool]` | 多线程提取指定页，返回每页成功状态。 |
| `extract_pdf_optimized(pdf_path: str, out_dir: str, zoom: float=2, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, reporter=None) -> bool` | 提取 PDF 页面为图片，支持多线程批次处理。 |
| `run_on_input_directory(input_path: str, out_root: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, subdir_name: str='images', reporter=None)` | 处理输入路径（文件或目录），对每个 PDF 在 out_root 下创建以其文件名命名的子目录， |
| `parse_margins(val) -> Optional[List[float]]` | 解析边距为 [上,右,下,左] (mm)。 |
| `parse_color(color_str: Union[str, tuple]) -> Tuple[int, int, int]` | 解析颜色 'r,g,b' 或 (r,g,b) 为整数元组，取值域 [0,255]。 |
| `register_fonts(pdf)` | 尝试注册系统中文字体，返回第一个成功注册的字体名。 |
| `draw_vertical_text(pdf, text, x, y_start, font_name, font_size, color, direction='down')` | 在PDF上绘制垂直文字（逐字上下排列）。 |
| `get_page_side_from_name(name_without_ext)` | 根据文件名末尾 '-l' 或 '-r' 判断左右页。 |
| `get_page_side_by_start(image_files, current_index, start_page, default_side='left')` | 根据起始页的左右属性推断当前页是左还是右。 |

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

#### `report_image_size(img_path, width: int, height: int, reporter=None) -> None`

汇报一页输出图片的尺寸。

结构化通道 `page_size` 供 GUI 子进程入库（sizes.json 是框坐标的坐标系基准）；
`[imgsize]` 文本行仅为**兼容保留**。

reporter 缺省为 None —— CLI 不注入，行为与原先「只 print 一行」完全一致。

#### `process_page_batch(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, progress: dict=None, reporter=None) -> List[bool]`

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

返回:
    每页成功/失败的 bool 列表。

#### `render_pages_parallel(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, workers: int=4, batch_size: int=4, progress: dict=None, reporter=None) -> List[bool]`

多线程提取指定页，返回每页成功状态。

CLI（`extract_pdf_optimized`）与 GUI（`run_extract_stage`）共用这一份并发
实现——GUI 曾经直接调 `process_page_batch` 串行跑全部页，是提取慢的主因。

每批一个 `fitz.open`（PyMuPDF 的 Document 非线程安全，必须各自打开）。

reporter 为结构化汇报通道（进度 + 页尺寸）；None → 保持纯 print 行为。

#### `extract_pdf_optimized(pdf_path: str, out_dir: str, zoom: float=2, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, reporter=None) -> bool`

提取 PDF 页面为图片，支持多线程批次处理。

参数:
    pdf_path: PDF 文件路径。
    out_dir: 输出目录（此目录将存放该 PDF 的所有页面图片）。
    zoom: 缩放因子（整数，如 2 表示 2 倍分辨率）。
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

#### `run_on_input_directory(input_path: str, out_root: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, subdir_name: str='images', reporter=None)`

处理输入路径（文件或目录），对每个 PDF 在 out_root 下创建以其文件名命名的子目录，
并在该子目录下创建 subdir_name 目录存放图片。

参数:
    input_path: 输入路径（单个 PDF 文件或包含 PDF 的目录）。
    out_root: 输出根目录（所有 PDF 的子目录将创建在此目录下）。
    zoom, ext, workers, quick, pages, start, end, batch_size, clean:
        透传给 extract_pdf_optimized 的参数。
    subdir_name: 每个 PDF 子目录下存放图片的子目录名。
    reporter: 结构化汇报通道；None → 只 print（CLI 默认）。

#### `parse_margins(val) -> Optional[List[float]]`

解析边距为 [上,右,下,左] (mm)。

实现委托 utils.margin_utils.normalize_margin，与命令行/GUI 共用同一份
规则：原先此处对 3 值静默回落到默认、对非数字串直接抛 ValueError，
与其他两处实现行为不一致。

#### `parse_color(color_str: Union[str, tuple]) -> Tuple[int, int, int]`

解析颜色 'r,g,b' 或 (r,g,b) 为整数元组，取值域 [0,255]。

非法输入抛 ValueError（不再静默返回黑色）——否则用户把 "0,0" 写错
只会得到一张黑字 PDF 却毫无提示；超范围分量写进 PDF 会产生损坏输出。

实现委托 utils.color_utils.parse_color，使 core 层可复用同一份逻辑。

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

当前提供 num_to_chinese：将整数转换为中文数字（支持到万以内），用于 PDF 页码
「第X頁」等场景。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `num_to_chinese(num: int) -> str` | 将整数转换为中文数字（支持万以内）。 |

---

## `utils.yolo_utils`

源码：[`utils/yolo_utils.py`](../../utils/yolo_utils.py)

YOLO 检测封装：模型加载与左右文本框分割。

此模块封装了 YOLO 目标检测模型的使用，提供两个核心功能：

1. **模型加载** (`load_yolo_model`)
   延迟加载 + 模块级单例 + 双重检查锁，确保多线程下模型只加载一次。
   权重文件查找路径: `gujitools/weights/detect.pt`。

2. **左右文本框检测** (`detect_left_right_boxes`)
   对古籍扫描图（通常左页 + 右页双栏排版）执行检测后，按检测框水平中心点
   与图像中线的关系分为 left / right 两组，供 crop / cropremove 使用。

左右分割算法:
    以图像宽度一半为分界线，检测框中心 cx < w/2 归入 left，否则归入 right。
    每组按面积降序排序，调用方取 [0] 即可获得最大候选框。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _YOLO_MODEL | `None` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `load_yolo_model() -> object` | 延迟加载 YOLO 模型并返回单例实例。 |
| `detect_left_right_boxes(image_bgr: np.ndarray, model: object) -> Tuple[List[tuple], List[tuple]]` | 使用 YOLO 检测文本框并按水平中心分为左右两组。 |

#### `load_yolo_model() -> object`

延迟加载 YOLO 模型并返回单例实例。

使用双重检查锁定（double-checked locking）确保线程安全：
先无锁检查 → 再加锁检查 → 最后加载，避免每次调用都竞争锁。

返回:
    ultralytics.YOLO 实例（CPU 模式）。

异常:
    FileNotFoundError: 未在候选路径找到 weights/detect.pt。

#### `detect_left_right_boxes(image_bgr: np.ndarray, model: object) -> Tuple[List[tuple], List[tuple]]`

使用 YOLO 检测文本框并按水平中心分为左右两组。

算法:
1. 取图像宽度的一半 mid_x = w / 2 作为左右分界线；
2. 遍历所有检测框，计算中心 cx = (x1 + x2) / 2；
3. cx < mid_x → left_boxes，否则 → right_boxes；
4. 每组按面积降序排序（最大框排在 [0]）。

参数:
    image_bgr: BGR 格式图像（cv2 读取的默认格式）。
    model: YOLO 模型实例。

返回:
    (left_boxes, right_boxes)：
    - 每个 box = (x1, y1, x2, y2, area)，坐标为整数像素值；
    - 面积降序排列，取 [0] 即可得最大候选框；
    - 若某侧无检测框，对应列表为空。

---
