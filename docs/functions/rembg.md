# rembg 功能说明

对整张图片执行阈值去底色处理（7 种算法可选，默认 Otsu），输出白底黑字的
二值图/灰度图，可选保留红色印章原色。

## 命令

```bash
guji rembg -i <输入> -o <输出> [选项]
# 别名
guji -r -i <输入> -o <输出> [选项]
# 使用 YAML 配置
guji rembg --config ./book.yaml
```

指定 `--config` 时读取配置文件中的 `rembg:` 配置块；命令行显式提供的参数会
覆盖配置值。

> **输出格式固定为 PNG，不可配置**（因此没有 `--ext` 参数，配置模板里也没有
> `rembg.ext` 键）：`--type 2` 产出的是 1bit 单色位图，只有 PNG 能无损承载它；
> JPEG 是有损的 8bit 格式，会把二值图重新糊成灰阶，二值化的意义就没了。
> 需要 `jpg` 时请先输出 PNG 再另行转换。

## 核心算法

### 1. 图片加载与标准化

- 读取图片并统一为 RGB 模式
- RGBA 透明图与白底合并（alpha 通道作为 mask paste 到白色背景），避免透明通道影响阈值
- 其他模式（L/P/CMYK 等）直接 convert("RGB")

### 2. 印章检测（可选，--seal 开关）

**HSV 双区间红色匹配**：

HSV 色环中红色分布在两端，需要两个区间：

- 低区间：H ∈ [0, 10]，S ∈ [min_saturation, 255]，V ∈ [55, 255]
- 高区间：H ∈ [162, 180]，S ∈ [min_saturation, 255]，V ∈ [55, 255]

**形态学清理**：

1. 开运算（2×2 核）去除孤立噪点
2. 膨胀修补断裂

**连通域过滤**（三重判定）：

| 指标       | 阈值                    | 说明                                |
| ---------- | ----------------------- | ----------------------------------- |
| 最小面积   | min_seal_area (默认 80) | 连通域像素面积下限                  |
| 最大纵横比 | 2.8                     | max(w,h)/min(w,h)，排除细长条状噪声 |
| 最小填充率 | 0.35                    | area / 外接矩形面积，排除稀疏噪声   |

输出两个掩码：

- `red_mask`：所有红色像素（用于去底时排除，防止印章被误判为文字）
- `valid_seal_mask`：仅合格印章（用于决定是否输出彩色图）

### 3. 阈值计算（算法族，`--algorithm`）

统一接口：**入口 = 整页灰度图，出口 = 文本掩码**（`True` = 文字）。
实现见 `utils/rembg_algorithms.py`：每种算法是一个 `RembgAlgorithm` 子类，
加算法只需加一个子类并在注册表登记一行。

| 算法 key | 类型 | 核心思想 | 说明 |
| -------- | ---- | -------- | ---- |
| `otsu`（默认） | 全局 | 最大化类间方差 | 对整体直方图自适应，快速；要求直方图近似双峰 |
| `fixed` | 全局 | 预设固定值 128 | 极快，但完全不适应图像变化 |
| `mean` | 全局 | 整页平均灰度 | 简单快速，对前景/背景比例敏感 |
| `niblack` | 局部 | 局部均值 − k×标准差 | 适应光照变化，平坦区域易产生噪声 |
| `sauvola` | 局部 | 局部均值 × (1 + k×(std/R − 1)) | 文档图像效果好，R=128；参数需调试 |
| `bernsen` | 局部 | 局部对比度（max − min） | 对背景灰度渐变鲁棒，低对比度区易出块状伪影 |
| `wolf` | 局部 | 局部统计 + 全局最小值归一化 | 低对比度/光照不均优于 Sauvola |

`offset` **只对全局算法生效**（阈值最后统一 `clamp(threshold + offset, 30, 240)`）；
局部算法逐像素定阈值，叠加全局常量偏移没有意义，因此忽略 `offset`（桌面端选
局部算法时该控件自动置灰并归零）。

**Otsu 的向后兼容口径**（默认算法，历史任务都按它出图）：

```
1. 取非白像素子集: non_white = gray[gray < 250]
2. 若非白像素 > 500:
     threshold = Otsu(non_white) + offset
   否则:
     threshold = 128  # 退化为固定值（近似空白页）
3. 限制范围: threshold = clamp(threshold, 30, 240)
```

Otsu 遍历 0~255 所有可能阈值，将像素分为前景(≤t)和背景(>t)两类，计算类间方差
`σ² = w_b · w_f · (m_b - m_f)²`，使 σ² 最大的 t 即为最佳阈值。使用直方图实现，
复杂度 O(256)。

**局部算法的参数**：

- `--window`：窗口边长（像素，默认 25，>=3）。窗口越大越平滑、计算越慢；
- `--k`：灵敏度（0~1，默认 0.2）。Niblack 内部取负号（`mean − k×std`），
  Bernsen 映射为局部对比度下限（`k×75`，默认 15）；全局算法忽略这两个参数。

局部算法按**行分块**计算（每块 512 行，上下留 `window/2` 的 halo），
峰值内存只与块宽有关，结果与整页计算逐像素一致。

#### 桌面任务流程：同页左右裁图共享阈值

GUI 任务里去底色的输入是「检测文本框 → 提交本次任务」裁出的 `35-l` / `35-r`。
**只对全局算法**按下面的规则合并：

- 执行链上**最近的上游 detect 节点**写出的 `boxes.json` 提交计划里，同一源页的
  左右两张**都真实存在** ⇒ 合并非白像素算一个阈值，并分别应用到这两张；
- **占位图**（`plan.outputs[].placeholder=true`）不参与合并，自己单独计算阈值；
- 半幅/整幅单张、无文本框的整页图：各自按整图计算；
- 无上游 detect（自定义流程 / 独立模块页 / CLI）：逐图计算。

局部算法逐像素定阈值，不参与共享。实时预览与全量执行使用同一套规则。

### 4. 去底处理

算法输出文本掩码后，统一排除印章：`text_mask = algorithm_mask & ~red_mask`。
全局算法等价于 `gray < threshold`，局部算法等价于 `gray < threshold_map`。

形态学去噪：

1. 开运算（1×1 核）去除孤立噪点
2. 闭运算填充文字内部孔洞

输出模式：

| 模式 | 条件                     | 输出                                |
| ---- | ------------------------ | ----------------------------------- |
| 彩色 | seal_color=True 且有印章 | RGB：白底 + 红色印章原色 + 黑色文字 |
| 二值 | type=1（默认）           | 单通道：白底 + 黑色文字             |
| 1bit | type=2                   | 8bit 二值 → 1bit 单色位图           |
| 灰度 | type=3                   | 单通道：白底 + 原灰度文字           |

### 5. 保存

PNG 格式，300 DPI，optimize=True，compress_level=9。

## 参数说明

| 参数          | 默认值   | 说明                                 |
| ------------- | -------- | ------------------------------------ |
| -i/--input    | .        | 输入图片文件或目录                   |
| -o/--output   | None     | 输出目录名称                         |
| --clean       | False    | 清空输出目录（显式加 --clean 才清）   |
| --algorithm   | otsu     | 阈值算法：otsu/fixed/mean/niblack/sauvola/bernsen/wolf |
| --window      | 25       | 局部算法窗口边长（>=3；全局算法忽略） |
| --k           | 0.2      | 局部算法灵敏度（0~1；全局算法忽略）   |
| --offset      | 0        | 阈值偏移量（仅全局算法生效；正数文字加粗，负数变细） |
| --type        | 1        | 输出类型（1=二值，2=1bit，3=灰度）   |
| --seal        | False    | 印章检测总开关                       |
| --sealcolor   | False    | 印章彩色输出开关                     |
| --sealarea    | 80       | 印章最小连通域像素面积               |
| --sealmin-sat | 50       | 红色识别最低饱和度（0~255）          |
| --workers     | 按机器动态（≤8） | 并行线程数（CPU+内存双约束）  |

## 输出命名规则

```
输入: page3.jpg
输出: page3.png（PNG 格式，300 DPI）
```

## 处理流程

```
图片输入
  │
  ├─ 文件过小？ → 跳过
  │
  ├─ 加载 → RGB 标准化（RGBA 合并白底）
  │
  ├─ 灰度转换
  │
  ├─ 印章检测（可选）
  │   ├─ HSV 双区间匹配
  │   ├─ 形态学清理
  │   └─ 连通域过滤（面积/纵横比/填充率）
  │
  ├─ 阈值计算（--algorithm，默认 otsu）
  │   ├─ 全局（fixed/mean/otsu）→ 单个阈值 + offset，限制 [30, 240]
  │   └─ 局部（niblack/sauvola/bernsen/wolf）→ 逐像素阈值图（忽略 offset）
  │
  ├─ 去底处理
  │   ├─ 文本掩码 = algorithm_mask & ~red_mask
  │   ├─ 形态学开闭去噪
  │   └─ 生成输出数组
  │
  └─ 保存 PNG (300 DPI)
```

## 示例

```bash
# 基本二值化
guji rembg -i ./images -o ./output

# 保留红色印章
guji rembg -i ./images -o ./output --seal --sealcolor

# 灰度输出
guji rembg -i ./images -o ./output --type 3

# 调整阈值（文字加粗）
guji rembg -i ./images -o ./output --offset 10

# 1bit 单色位图（最小体积）
guji rembg -i ./images -o ./output --type 2

# 自定义印章参数
guji rembg -i ./images -o ./output --seal --sealcolor --sealarea 120 --sealmin-sat 60

# 低对比度/光照不均的页：Sauvola
guji rembg -i ./images -o ./output --algorithm sauvola --window 31 --k 0.2

# 背景渐变明显的页：Bernsen
guji rembg -i ./images -o ./output --algorithm bernsen --window 25 --k 0.2
```

## 实现要点

- **非白像素子集**：只对 gray < 250 的像素计算 Otsu，排除大量白色背景的干扰。
- **印章排除**：红色像素从文本掩码中排除，防止印章被误判为文字而变黑。
- **offset 微调**：仅全局算法生效；offset > 0 阈值升高，更多像素被判定为文字（加粗）；offset < 0 阈值降低，文字变细。局部算法忽略该参数。
- **type=2 输出**：先生成 8bit 灰度二值图，再通过 PIL convert("1") 转为 1bit 单色位图，体积最小。
- **并发处理**：基于 FunctionBase 的 ThreadPoolExecutor 并发引擎。
- **算法接口统一**：`utils/rembg_algorithms.py::RembgAlgorithm` 定义
  「灰度图进、文本掩码出」，7 种算法各自实现 `thresholds()`（全局返回整数，
  局部返回逐像素阈值图）；印章排除/形态学/输出类型留在公共收尾。
- **局部算法分块**：按 512 行分块并带 `window/2` halo，峰值内存不随页高线性
  增长，结果与整页计算逐像素一致。
- **执行记录**：桌面端任务会把「每页实际使用的算法」写进任务根目录的
  `rembg_methods[~节点].json`，运行记录 `runs.json` 同时保存默认算法与逐张
  覆盖表。
