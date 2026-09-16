<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# functions API 参考

图像处理功能模块：GUI 与 CLI 共用同一套算法

覆盖 10 个模块、9 个公开类、22 个公开函数/方法（生成于 2026-09-16）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`functions`](#functions) | 0 | 1 |
| [`functions.base`](#functionsbase) | 1 | 4 |
| [`functions.crop`](#functionscrop) | 1 | 1 |
| [`functions.crop_remove`](#functionscrop_remove) | 1 | 1 |
| [`functions.detect`](#functionsdetect) | 1 | 4 |
| [`functions.extract`](#functionsextract) | 1 | 2 |
| [`functions.init`](#functionsinit) | 1 | 3 |
| [`functions.print`](#functionsprint) | 1 | 2 |
| [`functions.rembg`](#functionsrembg) | 1 | 2 |
| [`functions.text_region`](#functionstext_region) | 1 | 2 |

---

## `functions`

源码：[`functions/__init__.py`](../../functions/__init__.py)

File: functions/__init__.py
功能模块包：每个命令对应一个功能实现类。

模块职责:
- `base.py`: FunctionBase 基类，提供输入路径解析、输出路径计算、并发执行引擎。
- `text_region.py`: TextRegionProcessor 基类，封装 YOLO 检测 + area/border 规则 + 输出构建。
- `extract.py`: 从 PDF 提取页面图片（ExtractFunction）。
- `detect.py`: 检测整页图片的左右文本框，只上报坐标不写盘（DetectFunction）。
- `crop.py`: 裁剪原图像素（CropFunction），继承 TextRegionProcessor。
- `rembg.py`: 整图去底色/二值化/印章保留（RembgFunction）。
- `crop_remove.py`: 裁剪 + 去底色（CropRemoveFunction），继承 TextRegionProcessor。

通过 `get_function(command, command_args)` 工厂方法获取对应实例。

加载策略:
- 各功能类延迟加载，`get_function('extract')` 只导入 extract.py（仅需 pymupdf/PIL），
  不会触发 crop.py 的 cv2 依赖。这使得 `guji extract` 在未安装 cv2 的环境也能运行。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `get_function(command: str, command_args: ArgsProvider, reporter: Reporter=None)` | 工厂函数：根据命令字符串返回对应的功能实例。 |

#### `get_function(command: str, command_args: ArgsProvider, reporter: Reporter=None)`

工厂函数：根据命令字符串返回对应的功能实例。

延迟导入对应模块，避免未使用的命令触发重依赖（如 crop 触发 cv2）。

参数:
    command: 命令名称（extract/detect/crop/rembg/cropremove/print）。
    command_args: 已解析的命令参数对象。
    reporter: 结构化汇报通道（进度 / 检测框 / 尺寸）。None 时功能模块用空实现，
        输出与历史「只 print」行为一致；desktop 传入 JSON Lines 实现。

返回:
    FunctionBase 子类实例，或 None（命令不存在）。

---

## `functions.base`

源码：[`functions/base.py`](../../functions/base.py)

File: functions/base.py
Function 基类与并行执行引擎。

本模块提供 `FunctionBase`，它封装了：
- 输入路径解析（文件/目录）与输出路径计算辅助方法；
- 并发处理流水线：从 `collect_input_files` 获取待处理文件并使用线程池并行处理；
- 日志记录与失败重试机制（默认最多重试 max_retries 次）。

子类只需实现 `_process_single_image()`，返回包含 `status` 与 `file` 字段的字典。

### `class FunctionBase`

抽象基类，提供通用执行引擎。

关键约定：
- `_process_single_image(path)`：子类实现单张图片处理逻辑，返回 `{'status': ..., 'file': filename, ...}`；
- `_collect_input_files()`：默认从 `utils.collect_image_files` 获取输入文件列表，子类可以覆盖；
- `execute()`：负责并发调度、重试、日志写入与最终统计。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args: ArgsProvider, reporter: Reporter=None)` | 解析输入路径与输出占位，输入不存在时直接抛 FileNotFoundError。 |
| `parse_user_output(raw_out: Optional[str], file_stem: str=None) -> Path` | 统一解析用户传入的 `--output` 参数。 |
| `make_out_dir()` | 创建最终输出目录 self.outpath。 |
| `execute() -> dict` | 执行入口：并行处理所有输入图片，支持多轮重试与日志记录。 |

##### `__init__(command_args: ArgsProvider, reporter: Reporter=None)`

解析输入路径与输出占位，输入不存在时直接抛 FileNotFoundError。

is_file 以「是文件或带扩展名」判断；outpath 留待子类在自身初始化里算。
command_args 只需满足 ArgsProvider 协议（有 get 方法），不限定具体类型。

reporter 是结构化汇报通道（进度 / 检测框 / 尺寸）：CLI 不传 → 空实现，
实际输出与人读日志逐字不变；desktop 传 JSON Lines 实现 → 不必再跑正则
去解析中文提示文案。

##### `parse_user_output(raw_out: Optional[str], file_stem: str=None) -> Path`

统一解析用户传入的 `--output` 参数。

规则：
- 若未指定，文件输入默认使用父目录下以文件名为名的目录；目录输入使用 parent/temp 作为默认输出；
- 若只传入单个名称（无路径分隔符），则相对于输入目录创建；
- 若传入包含路径分隔符，则按绝对/相对路径解析为最终 Path。

##### `make_out_dir()`

创建最终输出目录 self.outpath。

必须在 self.outpath 已由子类初始化阶段计算完成后调用，否则抛出
RuntimeError。目录以 parents=True, exist_ok=True 创建，已存在时不会报错。

注意：--clean 的清空逻辑在 execute() 中（先 rmtree 再 mkdir），本方法
不处理 clean，仅确保目录存在。输出目录的推导规则由子类 __init__ 中的
_calc_outpath / parse_user_output 负责，不在本方法内。

##### `execute() -> dict`

执行入口：并行处理所有输入图片，支持多轮重试与日志记录。

实现细节：
- 使用 ThreadPoolExecutor 并发调用 `_process_single_image()`；
- 对出错的文件会记录到失败日志，并在可重试次数内再次尝试；
- 最终按文件名排序导出统计信息与输出路径。

---

## `functions.crop`

源码：[`functions/crop.py`](../../functions/crop.py)

File: functions/crop.py
裁剪功能：基于 YOLO 检测定位文本框并裁剪原图像素。

与 cropremove 共享 area/border 规则（继承 TextRegionProcessor），
但不做 Otsu 去底色，仅裁剪原始图像像素。

### `class CropFunction(TextRegionProcessor)`

裁剪功能：输出原始彩色像素。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(*args, output_suffix: str='.png', **kwargs)` | 初始化裁剪功能并覆盖输出后缀与输出目录。 |

##### `__init__(*args, output_suffix: str='.png', **kwargs)`

初始化裁剪功能并覆盖输出后缀与输出目录。

output_suffix 为全局输出文件后缀（默认 ".png"，自动转小写）。构造时
重新计算 self.outpath（覆盖基类/父类的计算），确保裁剪结果按配置后缀保存。

---

## `functions.crop_remove`

源码：[`functions/crop_remove.py`](../../functions/crop_remove.py)

File: functions/crop_remove.py
复合流程：裁剪（基于检测）+ 去底色（Otsu / 红色印章保留）。

与 crop 共享 area/border 规则（继承 TextRegionProcessor），
区别是 ROI 做 Otsu 二值化去底色，并支持印章保留。

- `area` 控制裁剪区域与输出方式（详见 TextRegionProcessor）；
- `border` 控制空白边界（详见 TextRegionProcessor）；
- 额外参数：offset / type / seal / sealcolor / sealarea / sealmin_sat。

线程安全说明：每张图的 img_rgb / gray / threshold / red_mask 通过
`_on_boxes_detected` 返回的 ctx 字典传递，绝不写入 self 实例变量，
从而可被 ThreadPoolExecutor 并发调用而不串扰。

### `class CropRemoveFunction(TextRegionProcessor)`

裁剪 + Otsu 去底色。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args, reporter=None)` | 初始化裁剪+去底色功能，固化去底色参数并推导输出目录。 |

##### `__init__(command_args, reporter=None)`

初始化裁剪+去底色功能，固化去底色参数并推导输出目录。

将 default_temp_name 设为 "rembg"，并将 offset/type/seal/sealcolor/
sealarea/sealmin_sat 等命令级常量只读存入实例（线程安全）。最后重新计算
self.outpath，使输出落入 rembg 目录。

---

## `functions.detect`

源码：[`functions/detect.py`](../../functions/detect.py)

File: functions/detect.py
检测功能：在整页图片中检测左右两个文本框。

这是「检测」这一步的唯一实现——`crop = detect + 裁剪`、`cropremove =
detect + 裁剪 + 去底色`，两者都通过本模块拿到左右框，而不是各自调用
`utils.detect_left_right_boxes`。GUI 的 detect 阶段同样复用这里，因此
「CLI 与 desktop 用同一套算法、只是参数不同」在检测这一步也成立。

与其它功能类的区别：
- **`save` 决定是否落盘**。不带 `--save` 时 `self.outpath = None`，不计算路径、
  不创建目录、不写任何文件，只上报坐标——此时它纯粹是 `crop` / `cropremove`
  的前置中间步骤，供代码调用或 GUI 的 detect 阶段使用。
- **命令行下必须给 `--save`**：不落盘时命令行没有任何产出去处（坐标只打到
  stdout，下游 `crop` / `cropremove` 各自会重新检测），属于白算一趟，因此
  CLI 入口会直接拒绝（`cli.cli._reject_dry_run`）。本模块**不**做这个限制——
  它是可复用的库层，`DetectFunction` 作为中间步骤被代码调用时必须保持可用。
- **落地时**输出标注图（框 + 坐标文字），输出目录规则与 `crop`
  **完全一致**（都调 `utils.path_utils.resolve_final_output_dir`）：
  `<输入父目录>/detect`，即与 crop 同级、落在输入目录旁边。
- **`execute()` 被重写**：基类语义是「建目录 → 处理 → 落盘 → 统计」，
  对不落盘的检测无意义。

### `class DetectFunction(FunctionBase)`

检测功能：逐图检测左右文本框并上报坐标。

是否落盘由 `save` 决定：关闭时**不生成任何文件**（供代码调用 /
GUI detect 阶段当中间步骤），开启时把标注图（框 + 坐标文字）落地，
视觉与 GUI 的 detect 预览一致。

注意：命令行下「不带 `--save`」会被 CLI 入口拒绝，但那是入口层的
取舍，与本类无关——本类保持可复用，不在此处设限。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args, reporter=None)` | 初始化并加载 YOLO 模型（单例，进程内复用）。 |
| `execute() -> dict` | 逐图检测，返回汇总结果。 |

##### `__init__(command_args, reporter=None)`

初始化并加载 YOLO 模型（单例，进程内复用）。

`save`（默认关闭）决定是否把标注图落地，落地目录同 crop 的
输出规则（`-o` 或默认 `detect` 目录），仅在开启时才创建。

##### `execute() -> dict`

逐图检测，返回汇总结果。

**默认不写任何文件**；`--save` 开启时把标注图落地到 `outpath`。

为什么重写：`FunctionBase.execute` 的语义是「建输出目录 → 处理 →
落盘 → 统计写出数量」，而检测默认没有产出，也不该凭空创建输出
目录。这里保留**相同的并发与进度汇报行为**（含失败重试），只在
`--save` 时才做落盘相关的准备。

返回:
    {"processed": n, "left": n, "right": n, "output": 目录或 None}

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `extract_first_box(boxes) -> Optional[Box]` | 从 `detect_left_right_boxes` 的返回里取面积最大的框的 4 个坐标。 |
| `detect_page_boxes(img_bgr, model=None) -> Tuple[Optional[Box], Optional[Box]]` | 检测一页图片的左右文本框，返回 (left_box, right_box)。 |

#### `extract_first_box(boxes) -> Optional[Box]`

从 `detect_left_right_boxes` 的返回里取面积最大的框的 4 个坐标。

`detect_left_right_boxes` 返回 ``[(x1, y1, x2, y2, area), ...]``，
已按面积降序排列，故取 ``[0]`` 即最大候选框。统一在此处裁剪到前 4 个
元素——此前 CLI 与 GUI 各自写了一遍
``left_boxes[0][:4] if left_boxes else None``。

参数:
    boxes: 单侧框列表，可为空。

返回:
    (x1, y1, x2, y2)，或 None（该侧无框）。

#### `detect_page_boxes(img_bgr, model=None) -> Tuple[Optional[Box], Optional[Box]]`

检测一页图片的左右文本框，返回 (left_box, right_box)。

这是检测算法的**唯一入口**：crop / cropremove / GUI detect 阶段都调用
它，保证三处的框完全相同。

参数:
    img_bgr: BGR 图像数组（由 `utils.imread` 读取，支持中文路径）。
    model: YOLO 模型实例；None 时使用进程内单例。

返回:
    (left_box, right_box)，各为 (x1, y1, x2, y2) 或 None。

---

## `functions.extract`

源码：[`functions/extract.py`](../../functions/extract.py)

File: functions/extract.py
从 PDF 中提取页面图片的功能实现。

此功能对应 `guji extract` 命令，将 PDF 每页渲染为图片并保存到输出目录。

处理流程：
1. 计算输出根目录（支持文件/目录两种输入，--output 统一作为根目录）；
2. 从命令参数收集 zoom、ext、pages、workers 等选项；
3. 委托给 `utils.pdf_utils.run_on_input_directory` 执行实际渲染。

注意：此功能不使用 FunctionBase 的并发执行引擎（不需要 _process_single_image），
因为 PDF 渲染的并发逻辑在 `pdf_utils` 内部实现。

### `class ExtractFunction(FunctionBase)`

PDF 提取功能实现类。

直接重写 execute()，不使用基类的并发图片处理引擎。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args, reporter=None)` | 调用基类完成输入解析后，立即计算输出根目录。 |
| `execute()` | 执行 PDF 提取：收集参数并委托给 pdf_utils。 |

##### `execute()`

执行 PDF 提取：收集参数并委托给 pdf_utils。

输出规则：
- 每个 PDF 的输出位置为 <out_root>/<pdf_name>/<default_temp_name>/，
  其中 <out_root> 即 self.outpath，<default_temp_name> 为类属性。
- 不再区分单文件/目录，统一行为。

---

## `functions.init`

源码：[`functions/init.py`](../../functions/init.py)

File: functions/init.py
`guji init` 命令的功能实现。

该模块负责交互式生成 `guji.yaml` 配置文件，引导用户输入项目元数据
（名称、描述、版本）和输入路径，并基于模板 `static/guji.yaml`
生成最终的配置文件，同时保留模板中的所有注释和键顺序。

关键行为：
- 如果 `guji.yaml` 已存在且未使用 `--force`，会询问是否覆盖。
- 可以交互式或通过命令行参数 `-i/--input` 提供输入路径。
- **不再询问输出根目录**，`extract.output` 始终保持为空（null）。
- 后续命令（crop/rembg/cropremove）的 `input` 根据输入类型自动计算：
    - 若输入是 PDF 文件 → `<父目录>/<pdf_stem>/<DEFAULT_EXTRACT_NAME>`（实际路径）
    - 若输入是目录 → `<输入目录>/<pdf_file_name>/<DEFAULT_EXTRACT_NAME>`（占位符，用户可自行替换）
- `print` 命令的 `input` 自动指向 `rembg` 的输出目录（`DEFAULT_REMBG_NAME`），
  与其他命令共用相同的 `<pdf_stem>` 或 `<pdf_file_name>` 父目录，
  以便用户直接生成最终的 PDF。
- 依赖 `ruamel.yaml` 保留注释和格式，若未安装则报错提示。

### `class InitFunction`

交互式生成 guji.yaml 配置文件的命令实现。

根据用户输入或命令行 -i/--input 计算各子命令的 input 路径，并写入由
static/guji.yaml 模板派生的配置，保留原模板的注释与键顺序。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args)` | 读取 --force 与 -i/--input，供 execute 生成配置。 |
| `execute()` | 在进程当前目录生成 guji.yaml。 |

##### `execute()`

在进程当前目录生成 guji.yaml。

文件已存在且未加 --force 时交互确认；用户回答 n 则原样返回
``{"status": "cancelled"}`` 不做任何写入。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `safe_input(prompt_text: str, use_path_completer: bool=False) -> str` | 统一输入封装，支持路径补全。 |

---

## `functions.print`

源码：[`functions/print.py`](../../functions/print.py)

图片目录 → PDF：纸张/方向/页边距、标题与页码、双页左右标注。

本模块同时被 CLI（``guji run print``）与 GUI 的 print 阶段复用。页序完全由
数据层决定：GUI 把列表顺序作为 ``files`` 清单传进来，这里照单执行，不再解析
文件名；CLI 独立用法（无清单）才回退按文件名排序。

### 模块常量

| 名称 | 值 |
| --- | --- |
| MM_PER_INCH | `25.4` |
| PRINT_IMAGE_DPI | `300` |

### `class PrintFunction(FunctionBase)`

把图片目录合成 PDF 的命令实现。

直接重写 ``execute()``：参数全部来自命令行 / YAML 配置块，实际排版由
``_generate_pdf`` 完成，不使用基类的并发图片处理引擎。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args, reporter=None)` | 调用基类完成输入解析后，立即计算输出 PDF 路径。 |
| `execute() -> dict` | 收集打印参数并委托 _generate_pdf 生成 PDF。 |

##### `execute() -> dict`

收集打印参数并委托 _generate_pdf 生成 PDF。

从 command_args 读取纸张尺寸（默认 A4）、方向（默认 landscape）、
页边距、标题与页码相关配置，以及 skip_pages（默认空列表）与
workers（默认 4）。将参数透传给 _generate_pdf，返回其
{"processed": N, "output": path} 结果字典。

---

## `functions.rembg`

源码：[`functions/rembg.py`](../../functions/rembg.py)

File: functions/rembg.py
去底色功能：对单张图片执行整图 Otsu 二值化/灰度化/彩色保留印章。

此功能对应 `guji rembg` 命令，处理流程：

1. **图片加载与标准化**
   - 读取图片并统一为 RGB 模式；
   - RGBA 透明图与白底合并（避免 alpha 通道影响阈值计算）。

2. **印章检测**（可选，`--seal` 开关）
   - 基于 HSV 色域双区间提取红色掩码；
   - 连通域过滤噪声（面积/纵横比/填充率三重判定）。

3. **阈值计算**
   - 取非白像素（gray < 250）作为输入，调用 `calculate_auto_threshold` 计算 Otsu 阈值；
   - 叠加 `offset` 偏移量，并限制在 [30, 240] 范围内；
   - 非白像素不足 500 时退化为固定阈值 128。

4. **去底处理**
   - 调用 `apply_otsu_whole` 生成白底黑字输出；
   - 支持 3 种输出类型：二值(type=1)、1bit(type=2)、灰度(type=3)；
   - `--sealcolor` 开关下输出彩色图，保留红色印章原色。

5. **保存为 PNG**（300 DPI，optimize+compress_level=9）

### `class RembgFunction(FunctionBase)`

去底色功能实现类。

继承 FunctionBase 的并发执行引擎，只需实现 `_process_single_image`。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args, reporter=None)` | 初始化并推导去底色输出目录。 |
| `execute()` | 执行整图去底色：直接复用基类的并发图片处理引擎。 |

##### `__init__(command_args, reporter=None)`

初始化并推导去底色输出目录。

先调用基类解析输入/输出路径，再经 _calc_outpath 计算 self.outpath
（规则见 _calc_outpath：未指定 --output 时与输入并列，否则按用户输出解析）。

---

## `functions.text_region`

源码：[`functions/text_region.py`](../../functions/text_region.py)

File: functions/text_region.py
文本区域处理基类：YOLO 检测 → area/border 规则 → 输出构建。

crop 和 cropremove 共享相同的检测与裁剪规则，唯一区别是 ROI 处理：
- crop：裁剪原图像素
- cropremove：Otsu 去底色

本基类将公共流程模板化，子类只需实现差异方法：
- `_on_boxes_detected(img_bgr, boxes)`：检测到框后预处理，返回上下文 ctx
- `_process_roi(img_bgr, box, ctx)`：处理单个文本框区域
- `_handle_no_boxes(img_bgr, image_path, area_mode)`：无检测框时的处理
- `_save_output(arr, out_path)`：保存输出图片

ctx 通过参数传递（而非 self 实例变量），保证 ThreadPoolExecutor 并发安全。

**几何规则来源**：area/border 的画布尺寸与粘贴落点由
`utils.box_geometry.build_output_layout` / `build_symmetric_layout` 统一计算
（与 desktop 侧预览共用同一份规则）。本模块只负责用 numpy 把布局"画"出来，
不再自行推导几何。

### `class TextRegionProcessor(FunctionBase)`

文本区域处理基类：封装 YOLO 检测 + area/border 规则 + 输出构建。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(command_args, reporter=None)` | 计算输出目录并加载 YOLO 模型（单例，进程内复用）。 |
| `execute()` | 执行文本区域处理：委托基类并发引擎逐图处理。 |

##### `execute()`

执行文本区域处理：委托基类并发引擎逐图处理。

复用 FunctionBase.execute() 的线程池、重试与日志；单图完整流程
（读取→YOLO 检测→area/border 规则→输出）在 _process_single_image 中。

---
