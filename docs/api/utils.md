<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# utils API 参考

通用工具函数：几何、排序、图像 IO、PDF、YOLO

覆盖 19 个模块、9 个公开类、104 个公开函数/方法（生成于 2026-09-22）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块                                       | 类  | 函数 |
| ------------------------------------------ | --- | ---- |
| [`utils.box_draw`](#utilsbox_draw)         | 0   | 5    |
| [`utils.box_geometry`](#utilsbox_geometry) | 2   | 4    |
| [`utils.color_utils`](#utilscolor_utils)   | 0   | 2    |
| [`utils.file_utils`](#utilsfile_utils)     | 0   | 2    |
| [`utils.font_scan`](#utilsfont_scan)       | 0   | 4    |
| [`utils.font_setup`](#utilsfont_setup)     | 3   | 11   |
| [`utils.fonts`](#utilsfonts)               | 1   | 13   |
| [`utils.help`](#utilshelp)                 | 0   | 7    |
| [`utils.image_io`](#utilsimage_io)         | 0   | 2    |
| [`utils.image_utils`](#utilsimage_utils)   | 0   | 7    |
| [`utils.margin_utils`](#utilsmargin_utils) | 0   | 2    |
| [`utils.page_layout`](#utilspage_layout)   | 2   | 13   |
| [`utils.path_utils`](#utilspath_utils)     | 0   | 2    |
| [`utils.pdf_draw`](#utilspdf_draw)         | 1   | 9    |
| [`utils.pdf_extract`](#utilspdf_extract)   | 0   | 9    |
| [`utils.sort_utils`](#utilssort_utils)     | 0   | 2    |
| [`utils.string_utils`](#utilsstring_utils) | 0   | 3    |
| [`utils.units`](#utilsunits)               | 0   | 2    |
| [`utils.yolo_utils`](#utilsyolo_utils)     | 0   | 5    |

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
PIL 绘制。字体候选路径来自 `utils.fonts`（Windows/Linux/macOS 三份候选 +
`GUJI_CJK_FONT` 逃生口，见那里的说明——**别在本文件再写一遍**）；全部缺失
时退化为 ASCII 标签（`L` / `R` / `U`），保证任何环境下都不会崩。

### 模块函数

| 函数                                                                                                                 | 说明                                                     |
| -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| `reset_font_cache() -> None`                                                                                         | 清空字体探测缓存（`GUJI_CJK_FONT` 改指向后需要重探测）。 |
| `find_cjk_font() -> Optional[str]`                                                                                   | 返回可用的中文字体路径；都没有则返回 None。结果会缓存。  |
| `box_color(index: int) -> Tuple[int, int, int]`                                                                      | 按框序号取 BGR 颜色。                                    |
| `box_name(index: int) -> str`                                                                                        | 按框序号取中文名（左框/右框/合并框）。                   |
| `draw_boxes(img_bgr, boxes: Sequence[Optional[Sequence[int]]], thickness: int=4, show_label: bool=True, color=None)` | 在图像上绘制一组框（原地绘制并返回新图，不修改入参）。   |

#### `draw_boxes(img_bgr, boxes: Sequence[Optional[Sequence[int]]], thickness: int=4, show_label: bool=True, color=None)`

在图像上绘制一组框（原地绘制并返回新图，不修改入参）。

参数:
img_bgr: BGR 图像数组。
boxes: 框列表，每项为 `(x1, y1, x2, y2)`；`None` 项被跳过
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

| 名称             | 值   |
| ---------------- | ---- |
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

| 函数                                                                                                                                                                                                              | 说明                                                            |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]`                                                                                                                                              | 解析 border 参数（毫米单位），按 DPI 转换为像素。               |
| `compute_final_boxes(boxes, area: int, border_mm, dpi: int=300) -> List[List[int]]`                                                                                                                               | 按 crop 命令的 area/border 规则计算最终切割框（原始图片坐标）。 |
| `build_output_layout(boxes: Sequence[Sequence[int]], area: int, border_padding, image_size: Tuple[int, int], dpi: int=300, sides: Optional[Sequence[Optional[str]]]=None, symmetric: bool=False) -> OutputLayout` | 按 area/border 规则计算输出画布布局（area=1 / 2 / 3）。         |
| `build_symmetric_layout(box: Sequence[int], border_padding, image_size: Tuple[int, int], is_left: bool=True, dpi: int=300) -> OutputLayout`                                                                       | 单框对称输出布局：实际框 + 空白镜像 + 中间间隔。                |

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
utils ← core ← functions / cli / desktop

设计取舍：非法输入**一律抛 ValueError**，不静默降级为黑色。
静默降级会让用户把 "0,0" 写错时只看到一张黑字 PDF 却毫无提示；
而超范围分量（如 300）写进 PDF 会产生损坏输出。

### 模块函数

| 函数                                              | 说明                                                 |
| ------------------------------------------------- | ---------------------------------------------------- |
| `parse_color(value: Any) -> Tuple[int, int, int]` | 解析颜色为 (r, g, b) 整数元组，分量取值域 [0, 255]。 |
| `format_color(rgb: Tuple[int, int, int]) -> str`  | 整数三元组 → "r,g,b" 文本（与 parse_color 互逆）。   |

#### `parse_color(value: Any) -> Tuple[int, int, int]`

解析颜色为 (r, g, b) 整数元组，分量取值域 [0, 255]。

接受: - 字符串 "r,g,b"：半角或全角逗号、全角空格均可；- 列表 / 元组 (r, g, b)。

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

| 函数                                                                 | 说明                                           |
| -------------------------------------------------------------------- | ---------------------------------------------- |
| `collect_image_files(input_path: Path, is_file: bool) -> List[Path]` | 收集输入路径下的所有图片文件，按自然排序返回。 |
| `is_valid_image_size(path: Path, min_size: int=100) -> bool`         | 校验文件大小是否大于最小阈值。                 |

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

## `utils.font_scan`

源码：[`utils/font_scan.py`](../../utils/font_scan.py)

扫描系统字体目录，找出所有含中文的字体文件。

## 与 `utils.fonts` 的分工

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

| 名称         | 值                           |
| ------------ | ---------------------------- |
| \_CACHE_NAME | `"guji-cjk-font-cache.json"` |
| \_MAX_DEPTH  | `4`                          |

### 模块函数

| 函数                                                                   | 说明                                                       |
| ---------------------------------------------------------------------- | ---------------------------------------------------------- |
| `font_directories() -> tuple[str, ...]`                                | 按平台给出要扫描的字体目录（可能不存在，调用方自己判空）。 |
| `scan_system_fonts(force: bool=False) -> tuple[FontEntry, ...]`        | 扫描系统里的中文字体，返回按显示名排序的条目。             |
| `scan_seconds_hint() -> float`                                         | 上一次扫描的耗时（秒）；没有记录返回 0.0（调试用）。       |
| `timed_scan(force: bool=False) -> tuple[tuple[FontEntry, ...], float]` | 带计时的扫描（调试与自测用）：返回 (条目, 耗时秒)。        |

#### `scan_system_fonts(force: bool=False) -> tuple[FontEntry, ...]`

扫描系统里的中文字体，返回按显示名排序的条目。

⚠️ 首次调用要遍历整个字体目录、逐个读 cmap，**本机约 7 秒**——
只能在后台线程里调（见 `desktop.services.font_catalog`）。结果会写
磁盘缓存，之后每次调用毫秒级返回。

---

## `utils.font_setup`

源码：[`utils/font_setup.py`](../../utils/font_setup.py)

中文字体体检与 Linux 自动补装。

## 为什么需要这一层

Windows 自带仿宋 / 宋体，`utils.fonts` 的候选表几乎必然命中；而
Ubuntu / Debian 的最小安装**一个中文字体都没有**。问题是：缺字体时代码
不会报错，只会静默降级——

- PDF 标题与页码（`utils.pdf_draw.register_fonts`）退回 `Helvetica` →
  中文变方块或整段消失；
- 检测框标注（`utils.box_draw.find_cjk_font`）退回 ASCII 的 `L` / `R` / `U`。

**产物是错的，界面却毫无提示**。所以 GUI 启动时先体检一次：

1. 找到中文字体 → 静默通过（Windows / macOS 基本都是这条路）；
2. 没找到 → 弹窗。Linux 上给「自动安装」：从发行版仓库拉一个中文字体包，
   **首选真正的仿宋** `fonts-cwtex-fs`，其次 AR PL UMing、Noto CJK、文泉驿；
3. 自动装不上（无网络 / 无管理员权限 / 没有已知包管理器）→ 退回提示，
   给出可直接复制的手装命令。

依赖方向：只用标准库 + `utils.fonts`，属 `utils` 最底层，任何层都能引用。
**刻意不依赖 Qt**：安装要跑漫长的子进程并sudo/pkexec 提权，把它做成纯函数，
命令行、自测、GUI 三条路才能共用同一份判断（ GUI 侧只负责套壳与流式日志）。

### `class FontPackage`

一个可安装的中文字体包。

- `name`：包管理器里的包名；
- `label`：给用户看的一行说明（为什么要装它）；
- `families`：装完后得到的字体族名（`fc-list` 里显示的名字）。

### `class FontCheck`

体检结果。

- `found`：本机是否有可用的中文字体；
- `path`：命中的字体文件（`found` 为假时是 `None`）；
- `source`：命中来源，`env`（`GUJI_CJK_FONT`）/ `table`（内置候选表）
  / `scan`（扫描字体目录）/ `none`；
- `platform`：`windows` / `macos` / `linux` / 其它（`sys.platform`）。

### `class InstallResult`

安装尝试的结果。

`status` 取值

- `ok`：装上了，且重新体检确实能找到中文字体；
- `network`：软件源不可达 / 下载失败 → 应提示用户手动安装；
- `permission`：提权失败或用户取消 → 同上；
- `unsupported`：非 Linux 或没有已知包管理器 → 同上；
- `failed`：其它失败（`output` 里留了日志尾部，供排查）。

#### 方法

| 方法           | 说明                       |
| -------------- | -------------------------- |
| `ok() -> bool` | 是否成功装上并被系统识别。 |

### 模块函数

| 函数                                                                                                                                                                  | 说明                                                                         |
| --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `platform_name() -> str`                                                                                                                                              | 把 `sys.platform` 归一成 `windows` / `macos` / `linux` 三类。                |
| `scan_font_dirs(limit: int=8) -> tuple[str, ...]`                                                                                                                     | 扫描常见字体目录里**看起来是中文**的字体文件（Linux 为主）。                 |
| `check_cjk_font() -> FontCheck`                                                                                                                                       | 体检本机有没有可用的中文字体（不弹任何 UI，纯判断）。                        |
| `detect_package_manager() -> str \| None`                                                                                                                             | 返回可用的包管理器键名（`apt` / `dnf` / `yum` / `pacman` / `zypper`）。      |
| `install_plan(manager: str \| None=None) -> tuple[FontPackage, ...]`                                                                                                  | 返回该平台的字体安装候选（顺序即优先级）；未知包管理器返回空元组。           |
| `available_packages(plan: tuple[FontPackage, ...], manager: str, timeout: float=10.0) -> tuple[FontPackage, ...]`                                                     | 筛掉仓库里**确实没有**的包，避免浪费一次提权。                               |
| `repo_reachable(timeout: float=4.0) -> bool \| None`                                                                                                                  | 探测软件源是否可达。                                                         |
| `classify_failure(returncode: int, output: str) -> str`                                                                                                               | 把一次安装命令的失败归类成 `network` / `permission` / `refresh` / `failed`。 |
| `install_cjk_fonts(packages: tuple[str, ...] \| None=None, manager: str \| None=None, probe_network: bool=True, timeout: float=900.0, on_line=None) -> InstallResult` | 从发行版仓库安装中文字体（Linux 专用，其它平台直接返回 `unsupported`）。     |
| `manual_install_text(plan: tuple[FontPackage, ...] \| None=None) -> str`                                                                                              | 返回可直接照抄的手动安装说明（自动安装失败时给用户看）。                     |

#### `scan_font_dirs(limit: int=8) -> tuple[str, ...]`

扫描常见字体目录里**看起来是中文**的字体文件（Linux 为主）。

为什么要扫：静态候选表只能覆盖"发行版把 Noto/文泉驿装在标准位置"这一种
情况。用户从 Windows 拷来的 `simfang.ttf`、装到 `~/.local/share/fonts`
的自定义字体都不在表里——不扫就会明明有字体却提示缺字体。

判定只按**文件名关键词**（见 `_CJK_NAME_HINTS`）：读字体内部元数据要额外
依赖。这里是"决定要不要弹窗"的启发式，宁可宽松也不漏报。

#### `check_cjk_font() -> FontCheck`

体检本机有没有可用的中文字体（不弹任何 UI，纯判断）。

三级判定：`GUJI_CJK_FONT` 环境变量 → 内置候选表 → 扫描字体目录。
任何一级命中即认为可用。

#### `available_packages(plan: tuple[FontPackage, ...], manager: str, timeout: float=10.0) -> tuple[FontPackage, ...]`

筛掉仓库里**确实没有**的包，避免浪费一次提权。

只有 apt 能廉价地先问一次（`apt-cache policy` 不需要 root）；dnf/pacman/
zypper 会自己刷新元数据，直接尝试即可。若一个都查不出来（索引为空的容器镜像
很常见），原样返回——交给 `install_cjk_fonts` 先刷新再重试，别在这里把路堵死。

#### `repo_reachable(timeout: float=4.0) -> bool | None`

探测软件源是否可达。

返回 `True` / `False`；**判断不了**（非 Linux、认不出发行版）返回
`None`——此时不该拦人，直接尝试安装即可。

为什么先探一次：apt 的 DNS 失败要等 30 秒以上才超时，用户会以为卡死了；
主动探一下能在 4 秒内给出「连不上软件源」的明确结论。

#### `classify_failure(returncode: int, output: str) -> str`

把一次安装命令的失败归类成 `network` / `permission` / `refresh` / `failed`。

`refresh` 是一个特例：它不是真失败，而是「仓库索引过期，刷新一次就好了」，
调用方据此重试而不是直接劝退用户。

先判权限再判网络：polkit 撤销 / sudo 密码错误的输出最具体，
且 apt 在得不到写权限时会先报一堆无关的话，顺序反了会误归因。

#### `install_cjk_fonts(packages: tuple[str, ...] | None=None, manager: str | None=None, probe_network: bool=True, timeout: float=900.0, on_line=None) -> InstallResult`

从发行版仓库安装中文字体（Linux 专用，其它平台直接返回 `unsupported`）。

流程：候选包 →（apt）筛掉仓库里没有的 → 探网络 → 提权 → 逐个安装；
中途遇到「索引过期」会先刷一次元数据再重试同一个包。任何一个包装上、
且重新体检能在系统里找到中文字体，即返回 `ok`。

`packages` 可用来收敛到指定包（自测 / 命令行）；省略则用 `install_plan`。

⚠️ 本函数**会阻塞并可能弹文件外的系统授权框**（pkexec/sudo），GUI 里必须
放进子线程，回调回控件要排队回主线程。

#### `manual_install_text(plan: tuple[FontPackage, ...] | None=None) -> str`

返回可直接照抄的手动安装说明（自动安装失败时给用户看）。

内容包含三条路：包管理器装、手动放字体文件到用户目录、用环境变量指定。
前两条按主次给出命令，最后一条是因为容器 / 精简镜像往往连 root 都没有，
`~/.local/share/fonts` 是唯一不求人的路。

---

## `utils.fonts`

源码：[`utils/fonts.py`](../../utils/fonts.py)

中文字体探测与降级：候选表、优先级链、字形覆盖查询的唯一定义处。

## 为什么要抽这一层

PDF 的标题与页码（`utils.pdf_draw.register_fonts`）和检测框标注
（`utils.box_draw.find_cjk_font`）都要画中文，此前两处各自硬编码了四条
`C:\Windows\Fonts\*`。Windows 上一切正常；换到 Linux / macOS 时探测
全部落空 → PDF 里的中文退回 `Helvetica`（方块或丢字）、框标注退回
ASCII 的 `L` / `R` / `U`——**输出内容是错的却不报任何错**。

## 为什么不能"指定死一个字体"（本层存在的根本原因）

古籍标题里常有**异体字 / 生僻字**：仿宋只覆盖 GB2312 与扩展 A，遇到
扩展 B（`U+20000` 起）的字就没有字形，fpdf 会静默画出空白（控制台只留一行
"missing the following glyphs"）。系统里并非没有这些字——Windows 自带
`simsunb.ttf`（宋体-ExtB）、`mingliub.ttc`——只是它们**不是仿宋**。

因此这里提供三件事：

1. **候选表**：跨平台的中文字体清单，带中文显示名与优先级分组
   （仿宋 → 宋体 → 微软雅黑 → 黑体 → 其它），供用户挑选；
2. **降级链**：把候选按优先级串成一条链，逐个字挑第一个"有这个字"的字体，
   生僻字因此自动落到 ExtB 补字字体上，仿宋该用的地方仍是仿宋；
3. **补字字体**（`fallback_only`）：只有扩展区生僻字的字体（宋体-ExtB 等）
   只补字、不做主字体——它连常用字都没有，选它当主字体整页都会空。

依赖方向：只 import 标准库，是 `utils` 的最底层（与 `utils/units.py`
同级），任何层都可引用。字形查询按需 import `fontTools`（缺失时退化为
"假定全部支持"，只是不再逐字降级，不会崩）。

## 设计取舍

- **不做 fontconfig / `fc-match` 动态查询**：静态路径已覆盖主流发行版
  的默认字体，而 spawn 子进程会让打包产物和自测行为都变复杂。
- **留了环境变量逃生口 `GUJI_CJK_FONT`**：精简镜像 / CI / AppImage 里常常
  没有系统 CJK 字体，指向随包自带的 .ttf / .ttc 即可，它**永远排在最前**。

### 模块常量

| 名称             | 值                |
| ---------------- | ----------------- |
| GUJI_FONT_ENV    | `"GUJI_CJK_FONT"` |
| GROUP_FANGSONG   | `0`               |
| GROUP_SONG       | `1`               |
| GROUP_YAHEI      | `2`               |
| GROUP_HEI        | `3`               |
| GROUP_OTHER      | `4`               |
| GROUP_SUPPLEMENT | `9`               |

### `class FontEntry`

一个可用的中文字体：显示名 + 文件路径 + 优先级组。

`fallback_only` 为真的条目只用于补字（缺字时才用），不作为主字体、
也不出现在用户的选择列表里。

#### 方法

| 方法               | 说明                                               |
| ------------------ | -------------------------------------------------- |
| `exists() -> bool` | 字体文件是否真实存在（构造时不校验，用到才探测）。 |

### 模块函数

| 函数                                                                     | 说明                                                             |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| `known_entries() -> tuple[FontEntry, ...]`                               | 全部已知候选（按优先级），含不存在的。                           |
| `available_entries(with_supplement: bool=True) -> tuple[FontEntry, ...]` | 系统里真实存在的候选，按优先级排序（仿宋 → 宋体 → …）。          |
| `selectable_entries() -> tuple[FontEntry, ...]`                          | 给用户挑的字体列表：不含"仅补字"字体，按优先级排序。             |
| `find_entry(value) -> FontEntry \| None`                                 | 按显示名 / 文件路径 / 文件名反查条目（用户配置回填用）。         |
| `resolve_chain(preferred=None) -> list[FontEntry]`                       | 按优先级串出降级链：首选字体在前，补字字体垫底。                 |
| `glyphs(entry: FontEntry) -> frozenset \| None`                          | 该字体覆盖的码位集合；解析失败或没有 fontTools 时返回 None。     |
| `supports(entry: FontEntry, char: str) -> bool`                          | 该字体是否有这个字符的字形（读不出 cmap 时按"有"处理）。         |
| `pick_font(chain, char: str) -> FontEntry \| None`                       | 从降级链里挑第一个有这个字的字体；都没有则返回链首。             |
| `cjk_font_paths() -> tuple`                                              | 中文字体文件候选路径（按优先级）。返回的可能全都不存在。         |
| `first_existing_cjk_font() -> str \| None`                               | 返回第一个真实存在的中文字体文件路径；全部缺失返回 None。        |
| `cjk_font_families() -> tuple`                                           | 按当前平台返回中文字体族名（按优先级），供 Qt 侧挑**界面**文字。 |
| `content_font_families() -> tuple`                                       | 第四步 PDF 内容（标题 / 页码）的字体族名候选：仿宋（衬线）优先。 |

#### `known_entries() -> tuple[FontEntry, ...]`

全部已知候选（按优先级），含不存在的。

`GUJI_CJK_FONT` 指定的文件排在最前且只出现一次——它是用户/CI 的
显式指定，优先级高于"仿宋优先"。

#### `available_entries(with_supplement: bool=True) -> tuple[FontEntry, ...]`

系统里真实存在的候选，按优先级排序（仿宋 → 宋体 → …）。

`with_supplement=False` 时不含"仅补字"字体——那种字体不能当主字体。

⚠️ 排序**只按组**、组内保持候选表里的书写顺序（Python 的 sort 是稳定的）：
早先按 display 排序，结果"华文中宋"跑到"宋体"前面、"华文彩云"跑到
"楷体"前面——缺字降级会先落到装饰字体上，视觉上很突兀。

#### `find_entry(value) -> FontEntry | None`

按显示名 / 文件路径 / 文件名反查条目（用户配置回填用）。

找不到返回 None——用户的机器上可能没有配置里记的那个字体（换机器、
卸载字体），此时应当回落到自动选择而不是报错。

#### `resolve_chain(preferred=None) -> list[FontEntry]`

按优先级串出降级链：首选字体在前，补字字体垫底。

`preferred` 可以是显示名 / 路径 / 文件名（用户选择或配置里的值）；
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
guji help # 显示命令总览
guji help extract # 查看 extract 命令手册
guji help crop # 查看 crop 命令手册
guji help rembg # 查看 rembg 命令手册
guji help cropremove # 查看 cropremove 命令手册
guji help overview # 查看功能模块概览

### 模块函数

| 函数                                                          | 说明                                                         |
| ------------------------------------------------------------- | ------------------------------------------------------------ |
| `markdown_to_text(md: str) -> str`                            | 将 Markdown 轻量转为终端可读纯文本。                         |
| `print_quick_help()`                                          | 打印内置的快速帮助信息（命令总览）。                         |
| `print_version()`                                             | 打印版本信息                                                 |
| `get_help_text(command=None) -> str`                          | 获取帮助文本。                                               |
| `show_help_page(command=None)`                                | 分页显示帮助页面（尝试使用 less/more，无分页器则直接打印）。 |
| `show_command_help(command=None)`                             | 别名：显示指定命令的帮助页面。                               |
| `process_help_command(command: str, topic: str \| None=None)` | 处理 CLI 层传来的 help/version 命令并在需要时退出进程。      |

#### `markdown_to_text(md: str) -> str`

将 Markdown 轻量转为终端可读纯文本。

转换规则:

- 代码围栏 (` `python) → 移除围栏行，保留代码内容并缩进；
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
None — 未指定子命令，显示总览
'help' — help 子命令，显示 topic 指定的手册
'version' — 显示版本
'-h'/'--help' — 显示总览
topic: 当 command='help' 时，要查看的命令名（如 'extract'）。

---

## `utils.image_io`

源码：[`utils/image_io.py`](../../utils/image_io.py)

OpenCV 图片读写的路径安全封装。

`cv2.imread` / `cv2.imwrite` 在 Windows 上走的是 ANSI 文件接口，
路径含中文（古籍文件名基本都是中文）时会**静默返回 None / False**，
表现为"无法读取图片"或输出为空。这里统一改为
`np.fromfile` + `cv2.imdecode` 的字节流方式，绕开编码问题。

cv2 / numpy 体积大且加载慢，故在函数内延迟导入——GUI 主进程只是
偶尔需要读一张图，不应该为此付出启动时间的代价。

### 模块函数

| 函数                           | 说明                                                 |
| ------------------------------ | ---------------------------------------------------- |
| `imread(path, flags=None)`     | 读取图片（支持中文等非 ASCII 路径）。                |
| `imwrite(path, image) -> bool` | 写出图片（支持中文等非 ASCII 路径），成功返回 True。 |

#### `imread(path, flags=None)`

读取图片（支持中文等非 ASCII 路径）。

参数:
path: 图片路径（str / Path）。
flags: cv2.IMREAD\_\* 标志，默认 IMREAD_COLOR。

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

| 函数                                                                                                                                                                                              | 说明                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `calculate_auto_threshold(pixels: np.ndarray) -> int`                                                                                                                                             | 大津法（Otsu）计算最佳阈值。                                  |
| `extract_red_seal(rgb_img: np.ndarray, min_seal_area: int, min_saturation: int) -> Tuple[np.ndarray, bool]`                                                                                       | 从 RGB 图像中提取红色印章掩码。                               |
| `apply_otsu_to_region(img_rgb: np.ndarray, gray: np.ndarray, roi_box: tuple, threshold: int, enable_seal: bool, seal_color: bool, red_mask: Optional[np.ndarray], img_type: int=1) -> np.ndarray` | 对图像中指定矩形区域执行去底色处理，返回 ROI 大小的结果数组。 |
| `apply_otsu_whole(img_rgb: np.ndarray, gray: np.ndarray, threshold: int, red_mask: Optional[np.ndarray], seal_color: bool, img_type: int=1) -> np.ndarray`                                        | 对整张图执行去底色处理，返回与输入同尺寸的结果数组。          |
| `rembg_page(img_rgb: np.ndarray, gray: np.ndarray, *, offset: int=0, img_type: int=1, enable_seal: bool=False, seal_color: bool=False, seal_area: int=80, seal_min_sat: int=50) -> np.ndarray`    | 整页去底色的**唯一实现**：算阈值 → 叠加 offset → 整图去底。   |
| `parse_border(border_value) -> Optional[List[int]]`                                                                                                                                               | 解析 border 参数（像素单位），支持 CSS 风格 1~4 值写法。      |
| `parse_border_mm(border_value, dpi: int=300) -> Optional[List[int]]`                                                                                                                              | 解析 border 参数（毫米单位），按 DPI 转换为像素。             |

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
(red_mask, has_valid_seal): - red_mask: bool 数组 (H, W)，True = 红色像素（用于去底时排除）；- has_valid_seal: bool，是否存在合格印章（用于决定是否输出彩色图）。

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
ROI 大小的数组：- seal_color 模式且存在印章 → (h, w, 3) RGB，白底 + 红色印章原色 + 黑色文字；- 其他 → (h, w) 单通道，type=3 保留原灰度值，type=1/2 文字为 0（黑）背景为 255（白）。

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

#### `rembg_page(img_rgb: np.ndarray, gray: np.ndarray, *, offset: int=0, img_type: int=1, enable_seal: bool=False, seal_color: bool=False, seal_area: int=80, seal_min_sat: int=50) -> np.ndarray`

整页去底色的**唯一实现**：算阈值 → 叠加 offset → 整图去底。

CLI（`functions.rembg`）与桌面端第三步的「实时预览」都调这里，保证界面
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

- 单值 30 → [30, 30, 30, 30] (上右下左)
- 两值 20,30 → [20, 30, 20, 30] (上下, 左右)
- 三值 20,30,25 → [20, 30, 25, 30] (上, 左右, 下)
- 四值 10,20,30,40 → [10, 20, 30, 40] (上, 右, 下, 左)

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
utils ← core ← functions / cli / desktop

支持（与 CSS margin 简写一致）: - 单值 "20" → [20, 20, 20, 20] （四边相等）- 两值 "20,30" → [20, 30, 20, 30] （上下, 左右）- 三值 "20,30,25" → [20, 30, 25, 30] （上, 左右, 下）- 四值 "20,30,25,35" → 原样 （上, 右, 下, 左）

本模块统一了原先散落在三处的实现（core.command_spec.normalize_margin、
utils.pdf_utils.parse_margins（已废弃）、desktop 面板 parse_margin4），消除了
「三值在 A 处补成四值、在 B 处静默丢弃、在 C 处报错」的行为分叉。

### 模块函数

| 函数                                                                                         | 说明                                                            |
| -------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `normalize_margin(value: Any, default: Optional[List[float]]=None) -> Optional[List[float]]` | 把 CSS 风格的 margin 简写标准化为 [上, 右, 下, 左] 四元素列表。 |
| `format_margin(value: Any) -> str`                                                           | [上,右,下,左] → 最简 CSS 简写文本（与 normalize_margin 互逆）。 |

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

| 名称                       | 值          |
| -------------------------- | ----------- |
| TEXT_MARGIN_MM             | `0.0`       |
| TEXT_INSET_MM              | `0.0`       |
| TEXT_SIDE_OFFSET_MM        | `0.0`       |
| DEFAULT_PAGE_NUMBER_FORMAT | `"chinese"` |
| DEFAULT_PAGE_NUMBER_PREFIX | `"第"`      |
| DEFAULT_PAGE_NUMBER_SUFFIX | `"頁"`      |
| LATIN_ADVANCE_RATIO        | `0.55`      |

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
排列），与 `utils.pdf_draw.draw_vertical_text` 同名参数一致。
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

| 函数                                                                                                                                                                                                                                                                | 说明                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `is_rotated_char(ch: str) -> bool`                                                                                                                                                                                                                                  | 该字符是否属于"整段旋转 90°"的拉丁/半角段。                       |
| `vertical_runs(text: str) -> List[Tuple[str, bool]]`                                                                                                                                                                                                                | 竖排文本 → [(片段, 是否旋转 90°)]，相邻同类字符合并成一段。       |
| `vertical_advance_mm(chunk: str, char_h_mm: float, rotated: bool) -> float`                                                                                                                                                                                         | 一段竖排片段在竖直方向上占的高度（mm）——**估算值**。              |
| `vertical_chunk_advance_mm(chunk: str, char_h_mm: float, rotated: bool, latin_width_mm=None) -> float`                                                                                                                                                              | 绘制端一段竖排片段的实际步进（mm）——`draw_vertical_text`（fpdf）  |
| `vertical_extent_mm(text: str, char_h_mm: float) -> float`                                                                                                                                                                                                          | 整串竖排文本的高度（mm）。                                        |
| `text_block_width_mm(text: str, char_h_mm: float, vertical: bool) -> float`                                                                                                                                                                                         | 一段文字的**横向宽度**（mm）——即它从落点 x 向右占多宽。           |
| `paper_size_mm(paper_size: str) -> Tuple[float, float]`                                                                                                                                                                                                             | 纸张名 → (短边, 长边) 毫米；非法纸张抛 ValueError。               |
| `print_page_size_mm(paper_size: str, orientation: str) -> Tuple[float, float]`                                                                                                                                                                                      | 纸张 + 方向 → (页宽, 页高) 毫米。                                 |
| `image_name_parts(path) -> Tuple[Optional[int], Optional[str]]`                                                                                                                                                                                                     | 解析数字页名，返回 (页名数字, side)；side 可能为空。              |
| `resolve_title_nodes(image_files: Sequence, title_switch_nodes: Sequence) -> List[Tuple[int, Tuple[str, str]]]`                                                                                                                                                     | 把配置里的 [页名, 标题, side] 解析为「图片下标 → (标题, 侧别)」。 |
| `sides_for_pages(total: int, sorted_nodes: Sequence, page_number_start_page: int) -> List[str]`                                                                                                                                                                     | 逐页给出标题/页码所在侧（left / right）。                         |
| `text_insets(value: Any) -> Optional[List[float]]`                                                                                                                                                                                                                  | 标题/页码的「距页边」设置 → [上, 右, 下, 左]（mm）。              |
| `plan_print_page(image_size_px: Tuple[int, int], args: dict, page_index: int, total: int, sides: Optional[Sequence[str]]=None, sorted_nodes: Optional[Sequence]=None, image_name: Optional[str]=None, image_rect: Optional[Sequence[float]]=None) -> PrintPagePlan` | 单页排版几何。                                                    |

#### `vertical_runs(text: str) -> List[Tuple[str, bool]]`

竖排文本 → [(片段, 是否旋转 90°)]，相邻同类字符合并成一段。

`"呵呵Happiness"` → `[("呵呵", False), ("Happiness", True)]`：
汉字各自占一格，英文整段旋转。绘制端（fpdf / QPainter）按这个分段渲染，
所以两边的断段规则**只在这里定义一次**。

#### `vertical_advance_mm(chunk: str, char_h_mm: float, rotated: bool) -> float`

一段竖排片段在竖直方向上占的高度（mm）——**估算值**。

⚠️ 只用于排版占位（`vertical_extent_mm` → 标题/页码落点）。绘制时的
逐段步进请用 `vertical_chunk_advance_mm` 并传渲染端的实测宽度。

#### `vertical_chunk_advance_mm(chunk: str, char_h_mm: float, rotated: bool, latin_width_mm=None) -> float`

绘制端一段竖排片段的实际步进（mm）——`draw_vertical_text`（fpdf）
与 desktop 预览（QPainter）共用的同一份规则。

- 宽字符段：仍是一字一格（`len × char_h_mm`）；
- 旋转拉丁段：优先用渲染端**实测**的字符串宽度（fpdf 的
  `get_string_width` / Qt 的 `QFontMetrics.horizontalAdvance`），
  拿不到实测值（`latin_width_mm=None`）才回落到 `LATIN_ADVANCE_RATIO`
  估算——回落只为兼容，正常路径两条渲染端都会传实测值。

#### `text_block_width_mm(text: str, char_h_mm: float, vertical: bool) -> float`

一段文字的**横向宽度**（mm）——即它从落点 x 向右占多宽。

用于「距右纸边」的口径：用户填的是**文字轮廓右边缘**到纸边的距离，
所以落点得从右边往回退「右距 + 本宽度」，否则文字会比设定值多缩一个字宽
（用户明确要求，见 `_text_anchor`）。

- 竖排：整串是**一列**，宽度就是一个字宽（汉字方块格，等于字号）；
  拉丁段旋转 90° 后也只是一列的宽度，不额外加宽。
- 横排：宽度 ≈ 字符数 × 字宽（比例字体的粗估，`LATIN_ADVANCE_RATIO`
  同一套近似口径；误差只体现在右页横向标题的 1~2mm 留白上）。

#### `print_page_size_mm(paper_size: str, orientation: str) -> Tuple[float, float]`

纸张 + 方向 → (页宽, 页高) 毫米。

方向同时接受 fpdf 的 "P"/"L" 与 CLI/GUI 的 "portrait"/"landscape"：
`functions/print.py` 在 execute() 里把后者映射成了前者再传给排版，
两条路径都要能对上。

#### `resolve_title_nodes(image_files: Sequence, title_switch_nodes: Sequence) -> List[Tuple[int, Tuple[str, str]]]`

把配置里的 [页名, 标题, side] 解析为「图片下标 → (标题, 侧别)」。

`页名` 是**原始页码**（如 `5` / `5-r`），不是列表下标——用户填
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
image_name: 当前图片文件名（stem 即可），用于 `skip_pages`
按页名回查；不传则只能按序号匹配。

---

## `utils.path_utils`

源码：[`utils/path_utils.py`](../../utils/path_utils.py)

路径工具函数，用于解析各种命令的输出目录。

### 模块函数

| 函数                                                                                                                | 说明                                                        |
| ------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `resolve_final_output_dir(input_path: Path, output_arg: Optional[str], is_file: bool, default_subdir: str) -> Path` | 计算命令的最终输出目录（适用于 crop/rembg/cropremove 等）。 |
| `get_extract_output_root(input_path: Path, output_arg: Optional[str], is_file: bool) -> Path`                       | 计算 extract 命令的输出根目录（out_root）。                 |

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

这样设计确保：- 对于目录输入，输出默认与输入目录并列（而非在输入目录内部）。- 用户指定的 -o 作为根目录，其下自动追加 default_subdir。- 对于文件输入，输出默认在文件所在父目录下创建 default_subdir。

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

## 为什么需要它

古籍标题常有异体字 / 生僻字，而**没有任何单一字体**能覆盖它们：仿宋
缺扩展 B 的字，Windows 自带的宋体-ExtB 有那些字却没有常用字。所以
`name_for(ch)` 按优先级链挑第一个"有这个字"的字体——常用字仍是仿宋，
只有仿宋真没有的那个字才落到补字字体上。

⚠️ 只注册**实际会用到**的字体（构造时传入全部待排文字来算）：
把整条链二十来个字体全注册进去，每页 PDF 都要多嵌几个字体子集，
体积与生成时间都白涨。

#### 方法

| 方法                                           | 说明                                                 |
| ---------------------------------------------- | ---------------------------------------------------- |
| `__init__(entries, names: dict, primary: str)` | —                                                    |
| `entries() -> list`                            | 参与本链条的字体条目（按优先级）。                   |
| `name_for(char: str) -> str`                   | 这个字符该用哪个已注册字体名（找不到时回落主字体）。 |

### 模块函数

| 函数                                                                                                   | 说明                                                      |
| ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------- |
| `build_font_chain(pdf, texts=(), preferred=None) -> FontChain`                                         | 按优先级注册字体，返回可按字符取名的 `FontChain`。        |
| `register_fonts(pdf, preferred=None, texts=())`                                                        | 注册系统中文字体，返回第一个成功注册的字体名。            |
| `draw_vertical_text(pdf, text, x, y_start, font_name, font_size, color, direction='down', chain=None)` | 在PDF上绘制竖排文字：宽字符一字一格，拉丁段整体旋转 90°。 |
| `draw_horizontal_text(pdf, text, x, y, font_name, font_size, color, chain=None)`                       | 在 PDF 上绘制横排文字；`chain` 给出时逐字降级选字体。     |
| `get_page_side_from_name(name_without_ext)`                                                            | 根据文件名末尾 '-l' 或 '-r' 判断左右页。                  |
| `get_page_side_by_start(image_files, current_index, start_page, default_side='left')`                  | 根据起始页的左右属性推断当前页是左还是右。                |

#### `build_font_chain(pdf, texts=(), preferred=None) -> FontChain`

按优先级注册字体，返回可按字符取名的 `FontChain`。

- `preferred`：用户指定的字体（显示名 / 路径 / 文件名）；本机没有时
  忽略，链条仍从"仿宋优先"开始。
- `texts`：本次要排印的全部文字（标题、各章节标题…）。据此只注册
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

`chain`（`FontChain`）给出时**逐字挑选字体**：主字体缺这个字的字形
就顺位落到下一个（生僻字因此落到宋体-ExtB 之类的补字字体上），
而不是画出空白。不给则整段用 `font_name`（历史行为）。

#### `draw_horizontal_text(pdf, text, x, y, font_name, font_size, color, chain=None)`

在 PDF 上绘制横排文字；`chain` 给出时逐字降级选字体。

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

4. **目录遍历** (`run_on_input_directory`)
   支持输入为单个 PDF 文件或包含多个 PDF 的目录。

依赖: PyMuPDF (pymupdf), Pillow (PIL)。
绘制辅助（字体注册 / 竖排文字 / 左右页判定）在 `utils/pdf_draw.py`。

### 模块常量

| 名称                | 值     |
| ------------------- | ------ |
| QUICK_MIN_COVERAGE  | `0.9`  |
| MAX_OUTPUT_WIDTH_PX | `6000` |
| WIDE_PAGE_PT        | `3000` |
| DEFAULT_RENDER_DPI  | `300`  |

### 模块函数

| 函数                                                                                                                                                                                                                                                                                       | 说明                                                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| `parse_pages(pages_str: str, total_pages: int) -> List[int]`                                                                                                                                                                                                                               | 解析页码字符串为 0-based 页码列表。                                               |
| `validate_page_range(start: Optional[int], end: Optional[int], total_pages: int) -> List[int]`                                                                                                                                                                                             | 根据 start/end 整数对生成 0-based 页码列表。                                      |
| `calculate_zoom(page_width: float, requested_zoom: float=1) -> float`                                                                                                                                                                                                                      | 计算实际缩放因子，限制最大输出宽度为 6000px。                                     |
| `render_zoom(page_width: float, requested_zoom: float=1, dpi: float=DEFAULT_RENDER_DPI) -> float`                                                                                                                                                                                          | 整页渲染实际使用的缩放因子 = max(用户 zoom, DPI 下限)，再受宽度封顶。             |
| `report_image_size(img_path, width: int, height: int, reporter=None) -> None`                                                                                                                                                                                                              | 汇报一页输出图片的尺寸。                                                          |
| `process_page_batch(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, progress: dict=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]`                                                                                      | 处理一批 PDF 页面，返回每页的成功状态。                                           |
| `render_pages_parallel(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, workers: int=4, batch_size: int=4, progress: dict=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]`                                                | 多线程提取指定页，返回每页成功状态。                                              |
| `extract_pdf_optimized(pdf_path: str, out_dir: str, zoom: float=2, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> bool`                        | 提取 PDF 页面为图片，支持多线程批次处理。                                         |
| `run_on_input_directory(input_path: str, out_root: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, subdir_name: str='images', reporter=None, dpi: float=DEFAULT_RENDER_DPI)` | 处理输入路径（文件或目录），对每个 PDF 在 out_root 下创建以其文件名命名的子目录， |

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

#### `process_page_batch(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, progress: dict=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]`

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

#### `render_pages_parallel(pdf_path: str, page_indices: List[int], out_dir: str, zoom: float, ext: str, quick: bool=False, workers: int=4, batch_size: int=4, progress: dict=None, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> List[bool]`

多线程提取指定页，返回每页成功状态。

CLI（`extract_pdf_optimized`）与 GUI（`run_extract_stage`）共用这一份并发
实现——GUI 曾经直接调 `process_page_batch` 串行跑全部页，是提取慢的主因。

每批一个 `fitz.open`（PyMuPDF 的 Document 非线程安全，必须各自打开）。

reporter 为结构化汇报通道（进度 + 页尺寸）；None → 保持纯 print 行为。

#### `extract_pdf_optimized(pdf_path: str, out_dir: str, zoom: float=2, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, reporter=None, dpi: float=DEFAULT_RENDER_DPI) -> bool`

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

#### `run_on_input_directory(input_path: str, out_root: str, zoom: float=1, ext: str='jpg', workers: int=4, quick: bool=False, pages: str=None, start: int=None, end: int=None, batch_size: int=4, clean: bool=False, subdir_name: str='images', reporter=None, dpi: float=DEFAULT_RENDER_DPI)`

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

## `utils.sort_utils`

源码：[`utils/sort_utils.py`](../../utils/sort_utils.py)

自然排序工具：支持封面/菜单优先与数字感知排序。

用于文件列表排序，使 "page2, page10" 按数值 2 < 10 排序而非字典序 "10" < "2"。

### 模块函数

| 函数                                           | 说明                                              |
| ---------------------------------------------- | ------------------------------------------------- |
| `natural_sort_key(filename: str) -> tuple`     | 生成自然排序键，封面和菜单排在最前。              |
| `pdf_custom_sort_key(file_path: str) -> tuple` | 生成 PDF 页面排序键（古籍双页扫描件的阅读顺序）。 |

#### `natural_sort_key(filename: str) -> tuple`

生成自然排序键，封面和菜单排在最前。

排序规则:

1. 优先级：cover\*.png 和 menu.png 排在所有文件之前（priority=0）；
2. 数字感知：将文件名拆分为 [文字, 数字, 文字, ...] 序列，
   数字部分按整数值比较而非字符串比较。

参数:
filename: 文件名（含扩展名）。

返回:
(priority, natural_key) 元组，可直接用于 sort/sorted 的 key 参数。

示例: >>> files = sorted(["page10.png", "page2.png", "cover.png", "page3.png"],
... key=natural_sort_key) >>> [f.name for f in files]
['cover.png', 'page2.png', 'page3.png', 'page10.png']

#### `pdf_custom_sort_key(file_path: str) -> tuple`

生成 PDF 页面排序键（古籍双页扫描件的阅读顺序）。

分级规则，逐级比较：

1. `cover*` 优先，编号小的在前；
2. `menu` 次之；
3. 形如 `<页号>` / `<页号>-l` / `<页号>-r`（`_` 亦可）的图片：
   先按页号数值，再按侧边 `r → l → 无后缀`——双页扫描件右侧页先读；
4. 其余文件按文件名排在最后。

参数:
file_path: 文件路径或文件名，内部只取 basename。

返回:
`(优先级, 页号, 侧边)` 或 `(999, 0, 文件名)` 元组。

---

## `utils.string_utils`

源码：[`utils/string_utils.py`](../../utils/string_utils.py)

数字转中文等字符串辅助工具。

当前提供：

- `num_to_chinese`：整数转中文数字（支持万以内）；
- `num_to_ganzhi`：整数转**干支**（六十甲子，古籍册次/卷次常用）；
- `format_page_number`：按「样式 + 前缀 + 后缀」拼出页码文本——第四步
  页码样式的**唯一组装处**（PDF 与预览共用同一份）。

### 模块函数

| 函数                                                                                        | 说明                                                              |
| ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `num_to_chinese(num: int) -> str`                                                           | 将整数转换为中文数字（支持万以内）。                              |
| `num_to_ganzhi(num: int) -> str`                                                            | 将整数转换为干支纪序（六十甲子）：1 → 甲子，2 → 乙丑，61 → 甲子。 |
| `format_page_number(num: int, style: str='chinese', prefix: str='', suffix: str='') -> str` | 按「样式 + 前缀 + 后缀」拼出页码文本（第四步页码的唯一组装处）。  |

#### `num_to_ganzhi(num: int) -> str`

将整数转换为干支纪序（六十甲子）：1 → 甲子，2 → 乙丑，61 → 甲子。

古籍的册次/卷次常用干支编号。天干 10 与地支 12 的最小公倍数是 60，
所以序号按 60 循环（超过 60 从头再来，不会越界）。非正整数退化为
阿拉伯数字，保证任何输入都有可打印的结果。

#### `format_page_number(num: int, style: str='chinese', prefix: str='', suffix: str='') -> str`

按「样式 + 前缀 + 后缀」拼出页码文本（第四步页码的唯一组装处）。

- `chinese`：中文数字（五），`num_to_chinese`；
- `arabic`：阿拉伯数字（5）；
- `ganzhi`：干支（甲子，60 循环）；
- 认不出的样式按中文数字处理——老配置里可能存着别的值，回落成中文
  比抛异常或印出空串都好。

前缀/后缀是**原样拼接**的（不做空格补全）：想排「第 5 页」就把前缀写成
`"第 "`。空前缀/后缀表示只要数字本身。

---

## `utils.units`

源码：[`utils/units.py`](../../utils/units.py)

长度单位换算常量（mm / inch / pt 互转的唯一定义处）。

这些值此前在 `utils/page_layout.py`、`utils/pdf_utils.py`、
`functions/print.py` 各写一份（`MM_PER_INCH = 25.4` 三处、
`POINTS_PER_MM` 两处），`utils/box_geometry.py` 里还散着裸的 `25.4`。
换算常量是**客观值**，本来就不该有第二份——改一处漏两处时又查不出来
（值都一样，不会报错，只会悄悄各走各的）。

依赖方向：本模块不 import 任何东西，是 `utils` 的最底层，任何层都可引用。

### 模块常量

| 名称        | 值     |
| ----------- | ------ |
| MM_PER_INCH | `25.4` |

### 模块函数

| 函数                                       | 说明                        |
| ------------------------------------------ | --------------------------- |
| `mm_to_px(mm: float, dpi: float) -> float` | 毫米 → 像素（按给定 DPI）。 |
| `px_to_mm(px: float, dpi: float) -> float` | 像素 → 毫米（按给定 DPI）。 |

---

## `utils.yolo_utils`

源码：[`utils/yolo_utils.py`](../../utils/yolo_utils.py)

YOLO 检测封装：模型加载与左右文本框分割。

此模块封装了 YOLO 目标检测模型的使用，提供两个核心功能：

1. **模型加载** (`load_yolo_model`)
   延迟加载 + 模块级单例 + 双重检查锁，确保多线程下模型只加载一次。
   权重文件查找路径: `gujitools/weights/bookcontent.pt`。

2. **左右文本框检测** (`detect_left_right_boxes`)
   对古籍扫描图（通常左页 + 右页双栏排版）执行检测后，按检测框水平中心点
   与图像中线的关系分为 left / right 两组，供 crop / cropremove 使用。

左右分割算法:
以图像宽度一半为分界线，检测框中心 cx < w/2 归入 left，否则归入 right。
每组按面积降序排序，调用方取 [0] 即可获得最大候选框。

### 模块常量

| 名称           | 值     |
| -------------- | ------ |
| \_YOLO_MODEL   | `None` |
| \_LOAD_SECONDS | `0.0`  |

### 模块函数

| 函数                                                                                               | 说明                                                            |
| -------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `model_path() -> Path`                                                                             | YOLO 权重文件路径（候选表只保留这一份）。                       |
| `is_model_loaded() -> bool`                                                                        | 本进程是否已加载过 YOLO（常驻服务用它对外汇报，便于确认复用）。 |
| `load_seconds_used() -> float`                                                                     | 本进程**实际执行**加载模型时花掉的秒数；没加载过则为 0.0。      |
| `load_yolo_model() -> object`                                                                      | 延迟加载 YOLO 模型并返回单例实例。                              |
| `detect_left_right_boxes(image_bgr: np.ndarray, model: object) -> Tuple[List[tuple], List[tuple]]` | 使用 YOLO 检测文本框并按水平中心分为左右两组。                  |

#### `model_path() -> Path`

YOLO 权重文件路径（候选表只保留这一份）。

权重路径同时被三处用到——真正加载模型、给用户打印、以及常驻 YOLO 服务的
身份指纹（见 `functions/yolo_service.py`）。三处各写一遍候选列表迟早会
漂移，所以统一收在这里。

返回:
`gujitools/weights/bookcontent.pt` 的绝对路径。

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
FileNotFoundError: 未在候选路径找到 weights/bookcontent.pt。

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
(left_boxes, right_boxes)：- 每个 box = (x1, y1, x2, y2, area)，坐标为整数像素值；- 面积降序排列，取 [0] 即可得最大候选框；- 若某侧无检测框，对应列表为空。

---
