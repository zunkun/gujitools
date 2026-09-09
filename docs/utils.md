# 工具模块说明 (`utils/`)

`utils/` 包含通用工具函数，按职责拆分为 6 个模块。所有公共函数通过 `utils/__init__.py` 统一导出，功能模块通过 `import utils` 后直接调用。

## 模块总览

| 模块             | 职责                | 主要函数                                                                                                                        |
| ---------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `image_utils.py` | 图像处理核心算法    | `calculate_auto_threshold`, `extract_red_seal`, `apply_otsu_to_region`, `apply_otsu_whole`, `parse_border`, `parse_border_mm`   |
| `file_utils.py`  | 文件收集与校验      | `collect_image_files`, `is_valid_image_size`, `IMAGE_EXTS`                                                                      |
| `yolo_utils.py`  | YOLO 模型加载与检测 | `load_yolo_model`, `detect_left_right_boxes`                                                                                    |
| `pdf_utils.py`   | PDF 渲染与提取      | `parse_pages`, `validate_page_range`, `calculate_zoom`, `process_page_batch`, `extract_pdf_optimized`, `run_on_input_directory` |
| `sort_utils.py`  | 自然排序            | `natural_sort_key`                                                                                                              |
| `help.py`        | 帮助文本与分页显示  | `process_help_command`                                                                                                          |

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

---

## sort_utils.py — 自然排序

### `natural_sort_key(filename) -> tuple`

生成自然排序键，封面和菜单排在最前。

**排序规则**：

1. 优先级：`cover*.png` 和 `menu.png` 排在所有文件之前（priority=0）；
2. 数字感知：将文件名拆分为 [文字, 数字, 文字, ...] 序列，数字部分按整数值比较。

**示例**：`["page10.png", "page2.png", "cover.png"]` → `["cover.png", "page2.png", "page10.png"]`

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
