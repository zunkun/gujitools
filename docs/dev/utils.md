# 工具模块说明 (`utils/`)

`utils/` 包含通用工具函数，按职责拆分为 11 个模块。所有公共函数通过
`utils/__init__.py` 统一导出，功能模块通过 `import utils` 后直接调用。

> 本文件讲**算法与设计**；逐个函数的签名、参数与 docstring 见自动生成的
> [API 参考 · utils](../api/utils.md)（由 `tools/gen_api_docs.py` 从源码提取）。

## 模块总览

| 模块             | 职责                            | 主要函数 / 常量                                                                                                                |
| ---------------- | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `box_geometry.py`| 文本框几何规则（GUI/CLI 共用）  | `parse_border_mm`, `compute_final_boxes`                                                                                       |
| `box_draw.py`    | 检测框标注绘制（GUI/CLI 共用）  | `draw_boxes`, `box_color`, `box_name`, `find_cjk_font`                                                                         |
| `image_utils.py` | 图像处理核心算法                | `calculate_auto_threshold`, `extract_red_seal`, `apply_otsu_to_region`, `apply_otsu_whole`, `parse_border`, `parse_border_mm`   |
| `image_io.py`    | OpenCV 读写（中文路径安全）     | `imread`, `imwrite`                                                                                                            |
| `file_utils.py`  | 文件收集与校验                  | `collect_image_files`, `is_valid_image_size`, `IMAGE_EXTS`                                                                      |
| `yolo_utils.py`  | YOLO 模型加载与检测             | `load_yolo_model`, `detect_left_right_boxes`                                                                                    |
| `pdf_utils.py`   | PDF 渲染与提取                  | `parse_pages`, `validate_page_range`, `calculate_zoom`, `process_page_batch`, `extract_pdf_optimized`, `run_on_input_directory` |
| `path_utils.py`  | 输出目录解析                    | `resolve_final_output_dir`, `get_extract_output_root`                                                                          |
| `sort_utils.py`  | 自然排序                        | `natural_sort_key`, `pdf_custom_sort_key`                                                                                       |
| `string_utils.py`| 字符串辅助                      | `num_to_chinese`                                                                                                               |
| `help.py`        | 帮助文本与分页显示              | `process_help_command`                                                                                                         |

---

## box_geometry.py — 文本框几何规则（GUI/CLI 共用）

本模块**不导入 cv2/numpy**，因此可以被 GUI 主进程、desktop worker 与 CLI
`functions/` 同时复用——这保证了 detect 阶段预览里画出的"最终大框"与 `crop`
实际切割的区域完全一致（单一实现，不各写一份）。

坐标系一律是原始图片像素 `[x1, y1, x2, y2]`。

### `parse_border_mm(border_value, dpi=300) -> [top, right, bottom, left] | None`

border 参数的**唯一权威实现**：CSS 风格 1~4 值写法，按 DPI 换算为像素
（`px = mm × dpi / 25.4`，默认 300dpi）。

`utils.image_utils.parse_border_mm` 是本函数的向后兼容转发入口，实现已迁移到这里。

### `compute_final_boxes(boxes, area, border_mm) -> list`

由检测框 + `area` + `border` 推导最终裁剪框：

- `area=1`：逐框各出一个框（框本身 + border）；
- `area=2`：左右框的**并集**画布 + border（框间内容丢弃）；
- `area=3`：并集区域**整块**作为 ROI（框间内容保留）+ border。

返回值供 GUI 画参考轮廓、供 `crop`/`cropremove` 实际裁剪，两边共用同一份几何。

---

## box_draw.py — 检测框标注绘制（GUI/CLI 共用）

**为什么放在 utils**：CLI 的 `guji detect --save` 要把左右框画到图片上落地，
GUI 的预览控件也要画同样的框。配色与命名必须一致，否则「命令行看到的」和
「界面看到的」是两套东西。视觉约定集中在这里：

- 左框 `#21c178`（绿）、右框 `#3b82f6`（蓝）、合并框 `#f59e0b`（橙）；
- 标注文字为「左框 (x1,y1,x2,y2)」。

**中文字体**：OpenCV 的 `putText` 不支持中文（会画成 `????`），因此文字用 PIL
绘制。字体按 `utils.pdf_utils.register_fonts` 相同的候选顺序探测 Windows 系统中
文字体（fsgb2312 → simfang → simsun → msyh）；全部缺失时退化为 ASCII 标签
（`L` / `R` / `U`），保证任何环境下都不会崩。

与 `box_geometry.py` 一样，本模块**不参与实际裁剪**，只负责「把框画出来」。

### `draw_boxes(img_bgr, boxes, thickness=4, show_label=True, color=None)`

- **跳过 `None` 项**：只画真正检出的框，避免「只检出左框」时在猜测位置画出错误右框；
- 线宽按图像短边自适应（`min(2..10)`），大图小图都看得清；
- **返回新数组，不修改入参**（便于调用方复用原图）。

颜色常量 `BOX_COLORS_BGR` / `BOX_NAMES` 与
`desktop/components/viewers/image_view.py` 保持一致。

---

## image_utils.py — 图像处理核心算法

### `calculate_auto_threshold(pixels) -> int`

**大津法（Otsu）阈值计算**：遍历 0~255 所有可能阈值，将像素分为前景(≤t)和背景(>t)两类，使类间方差 `σ² = w_b · w_f · (m_b - m_f)²` 最大的 t 即为最佳阈值。

| 参数   | 类型       | 说明                                      |
| ------ | ---------- | ----------------------------------------- |
| pixels | np.ndarray | 一维 uint8 像素数组（通常为非白像素子集） |
| 返回   | int        | 0~255 范围内的整数阈值                    |

**实现要点**：使用直方图代替逐像素遍历，复杂度 O(256)；预算 `sum_total` 避免重复求和；默认阈值 128。

### `extract_red_seal(rgb_img, min_seal_area, min_saturation) -> (red_mask, has_valid_seal)`

**红色印章提取**：基于 HSV 色域双区间匹配 + 形态学清理 + 连通域过滤。

| 参数           | 类型       | 说明                                          |
| -------------- | ---------- | --------------------------------------------- |
| rgb_img        | np.ndarray | RGB 图像 (H, W, 3)                            |
| min_seal_area  | int        | 印章最小连通域像素面积（默认 80）             |
| min_saturation | int        | HSV 中 S 通道下限，过滤浅红色噪声（默认 50）  |
| 返回           | tuple      | `(red_mask: bool[H,W], has_valid_seal: bool)` |

**算法流程**：

1. RGB → HSV 转换；
2. 双区间 `inRange` 匹配红色（HSV 红色分布在色环两端）：H∈[0,10]∪[162,180]，S≥min_saturation，V≥55；
3. 形态学开运算（2×2 核）去孤立噪点 + 膨胀（1×1 核）修补断裂；
4. `findContours` 提取连通域，三重判定过滤：
   - 面积 ≥ min_seal_area
   - 纵横比 ≤ 2.8（排除细长条状噪声）
   - 填充率 ≥ 0.35（area / 外接矩形面积）
5. 输出 `red_mask`（所有红色像素，用于去底时排除）和 `has_valid_seal`（仅合格印章，用于决定是否输出彩色图）。

### `apply_otsu_to_region(img_rgb, gray, roi_box, threshold, enable_seal, seal_color, red_mask, img_type=1) -> np.ndarray`

**区域去底色**：对图像中指定矩形 ROI 执行 Otsu 去底，返回 ROI 大小的结果数组。

| 参数        | 类型            | 说明                                       |
| ----------- | --------------- | ------------------------------------------ |
| roi_box     | tuple           | (x1, y1, x2, y2) 区域坐标                  |
| threshold   | int             | 二值化阈值                                 |
| enable_seal | bool            | 是否启用印章检测                           |
| seal_color  | bool            | 是否要求彩色印章输出                       |
| red_mask    | np.ndarray/None | 全图红色印章掩码                           |
| img_type    | int             | 1=二值 / 2=1bit / 3=灰度                   |
| 返回        | np.ndarray      | ROI 大小数组（彩色为 3 通道，单通道为 2D） |

**输出规则**：

- `seal_color=True` 且有印章 → RGB：白底 + 红色印章原色 + 黑色文字；
- `img_type=3` → 单通道灰度，文字保留原灰度值；
- `img_type=1/2` → 单通道二值，文字=0（黑），背景=255（白）。

### `apply_otsu_whole(img_rgb, gray, threshold, red_mask, seal_color, img_type=1) -> np.ndarray`

**整图去底色**：与 `apply_otsu_to_region` 逻辑一致，但作用于整图。用于未检测到文本框时的 fallback 路径。

### `parse_border(border_value) -> [top, right, bottom, left] or None`

**CSS 风格 border 参数解析（像素单位）**：

| 写法               | 展开结果                           |
| ------------------ | ---------------------------------- |
| 单值 `30`          | [30, 30, 30, 30]                   |
| 两值 `20,30`       | [20, 30, 20, 30]（上下，左右）     |
| 三值 `20,30,25`    | [20, 30, 25, 30]（上，左右，下）   |
| 四值 `10,20,30,40` | [10, 20, 30, 40]（上，右，下，左） |

### `parse_border_mm(border_value, dpi=300) -> [top, right, bottom, left] or None`

与 `parse_border` 写法规则相同，但最终值按 DPI 转换为像素：`px = mm × dpi / 25.4`。

默认 dpi=300（古籍扫描常用值）。`cropremove --border` 使用此函数。

> 实现已迁移到 `utils.box_geometry.parse_border_mm`（无重依赖，GUI 共用），
> 本模块的同名函数只是转发，保留是为了不破坏既有调用点。

---

## image_io.py — OpenCV 读写（中文路径安全）

### `imread(path, flags=cv2.IMREAD_COLOR) -> np.ndarray | None`

### `imwrite(path, image) -> bool`

`cv2.imread` / `cv2.imwrite` 在 Windows 上遇到**中文路径会静默失败**（返回
`None` / 不写文件，且不抛异常），而古籍文件名几乎必然含中文。这两个封装改用
`np.fromfile` + `cv2.imdecode` 读、`cv2.imencode` + `tofile` 写，行为与原生
一致但支持任意路径。

**约定：项目内不要再直接调用 `cv2.imread` / `cv2.imwrite`。**

---

## file_utils.py — 文件收集与校验

### `collect_image_files(input_path, is_file) -> List[Path]`

收集输入路径下的所有图片文件，按自然排序返回。

| 参数       | 类型       | 说明                     |
| ---------- | ---------- | ------------------------ |
| input_path | Path       | 输入路径（文件或目录）   |
| is_file    | bool       | True=单文件，False=目录  |
| 返回       | List[Path] | 按自然排序的图片路径列表 |

**支持的扩展名**（`IMAGE_EXTS`）：`.jpg .jpeg .png .tif .tiff .bmp .gif .webp`

### `is_valid_image_size(path, min_size=100) -> bool`

校验文件大小是否大于最小阈值（默认 100 字节），过滤异常小文件。

---

## yolo_utils.py — YOLO 模型加载与检测

### `load_yolo_model() -> YOLO`

**延迟加载 YOLO 模型单例**：双重检查锁定（double-checked locking）确保多线程下只加载一次。

- 权重文件路径：`gujitools/weights/detect.pt`
- 强制 CPU 模式（兼容无 GPU 环境）
- 找不到权重文件时抛出 `FileNotFoundError`

### `detect_left_right_boxes(image_bgr, model) -> (left_boxes, right_boxes)`

**左右文本框检测与分割**：

| 参数      | 类型       | 说明                                                       |
| --------- | ---------- | ---------------------------------------------------------- |
| image_bgr | np.ndarray | BGR 格式图像                                               |
| model     | YOLO       | 模型实例                                                   |
| 返回      | tuple      | `(left_boxes, right_boxes)`，每个 box = (x1,y1,x2,y2,area) |

**左右分割算法**：

1. 计算图像中线 `mid_x = w / 2`；
2. 遍历所有检测框，计算水平中心 `cx = (x1 + x2) / 2`；
3. `cx < mid_x` → left，否则 → right；
4. 每组按面积降序排序，调用方取 `[0]` 即可获得最大候选框。

> ⚠️ **唯一调用方是 `functions/detect.py`**：`functions.detect.detect_page_boxes()`
> 是本原语的封装（它负责「取最大框的前 4 个坐标」这一步），也是全仓库**唯一**
> 调用 `detect_left_right_boxes` 的地方。`crop` / `cropremove`（经
> `TextRegionProcessor`）与 GUI 的 detect 阶段都必须走 `detect_page_boxes`，
> **不得直接调用本文件的原语**。
> `tests/selftests/detect_shared.py` 会扫描全仓库守卫这条约束，违反即测试红。

---

## pdf_utils.py — PDF 渲染与提取

### `parse_pages(pages_str, total_pages) -> List[int]`

解析页码字符串为 0-based 页码列表。支持 `"1,3-5,7"` 格式，1-based 输入，0-based 输出。

### `validate_page_range(start, end, total_pages) -> List[int]`

根据 start/end 整数对生成 0-based 页码列表。

### `calculate_zoom(page_width, requested_zoom=1) -> float`

计算实际缩放因子，限制最大输出宽度 6000px：

- 页面宽度 > 3000pt → zoom=1（已足够宽）；
- 页面宽度 × zoom > 6000 → zoom = 6000 / 页面宽度；
- 否则 → 使用用户指定值。

### `process_page_batch(pdf_path, page_indices, out_dir, zoom, ext, quick, progress) -> List[bool]`

处理一批 PDF 页面，返回每页成功状态。支持 quick 模式（优先提取内嵌图片）和标准模式（渲染整页）。

### `extract_pdf_optimized(...) -> bool`

提取 PDF 页面为图片的主入口，支持多线程批次处理。参数包括 zoom、ext、workers、quick、pages、start、end、batch_size、clean。

### `run_on_input_directory(input_path, out_root, ...)`

处理输入路径（文件或目录），对每个 PDF 调用 `extract_pdf_optimized`。目录输入时按 PDF 文件名创建子目录。

缺失路径或空目录会抛 `ValueError`；单页失败会汇总为 `RuntimeError`，不再静默返回成功。

---

## path_utils.py — 输出目录解析

### `resolve_final_output_dir(input_path, raw_out, is_file, temp_name) -> Path`

解析 `--output` 的最终落点，是各功能模块共用的输出目录规则：

- 未指定 `--output`：文件输入用父目录下的 `temp_name`，目录输入用输入目录下的
  `temp_name`；
- 只给一个名称（不含路径分隔符）：相对输入目录创建；
- 含路径分隔符：按绝对/相对路径解析。

### `get_extract_output_root(input_path, raw_out, is_file) -> Path`

`extract` 专用的输出根目录：多 PDF 时按文件名分子目录，单文件直接落一层。

---

## sort_utils.py — 自然排序

### `natural_sort_key(filename) -> tuple`

生成自然排序键，封面和菜单排在最前。

**排序规则**：

1. 优先级：`cover*.png` 和 `menu.png` 排在所有文件之前（priority=0）；
2. 数字感知：将文件名拆分为 [文字, 数字, 文字, ...] 序列，数字部分按整数值比较。

**示例**：`["page10.png", "page2.png", "cover.png"]` → `["cover.png", "page2.png", "page10.png"]`

### `pdf_custom_sort_key(file_path) -> tuple`

**PDF 页面专用排序键**（`natural_sort_key` 不区分左右页，不足以表达双页扫描件的
阅读顺序）。逐级比较：

1. `cover*` 优先，编号小的在前；
2. `menu` 次之；
3. `<页号>` / `<页号>-l` / `<页号>-r`：先按页号数值，再按侧边 **r → l → 无后缀**；
4. 其余按文件名排在最后。

GUI 的待打印列表与 CLI `print` 都使用它，保证页序一致。

---

## string_utils.py — 字符串辅助

### `num_to_chinese(num) -> str`

整数 → 中文数字（支持到万以内）。用于 PDF 页码的「第X頁」标注，例如
`2` → `二`、`12` → `十二`。负数会加「負」前缀。

---

## help.py — 帮助文本与分页显示

### `process_help_command(command)`

根据命令名加载对应的 man 风格帮助文本并分页显示。定义在 `utils/help.py` 中，被 CLI 层调用。

---

## 设计约定

- **算法无关逻辑**放在 `utils/`，业务实现放在 `functions/`，保持职责分离；
- 所有公共函数通过 `utils/__init__.py` 的 `__all__` 统一导出；
- 图像处理函数同时接受 RGB 和灰度数组，避免重复转换；
- `red_mask` 在全图计算一次后裁剪到 ROI 复用，避免重复计算。
