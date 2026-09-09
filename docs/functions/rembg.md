# rembg 功能说明

对整张图片执行 Otsu 去底色处理，输出白底黑字的二值图/灰度图，可选保留红色印章原色。

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

| 指标 | 阈值 | 说明 |
|------|------|------|
| 最小面积 | min_seal_area (默认 80) | 连通域像素面积下限 |
| 最大纵横比 | 2.8 | max(w,h)/min(w,h)，排除细长条状噪声 |
| 最小填充率 | 0.35 | area / 外接矩形面积，排除稀疏噪声 |

输出两个掩码：
- `red_mask`：所有红色像素（用于去底时排除，防止印章被误判为文字）
- `valid_seal_mask`：仅合格印章（用于决定是否输出彩色图）

### 3. 阈值计算（Otsu 大津法）

```
1. 取非白像素子集: non_white = gray[gray < 250]
2. 若非白像素 > 500:
     threshold = Otsu(non_white) + offset
   否则:
     threshold = 128  # 退化为固定值（近似空白页）
3. 限制范围: threshold = clamp(threshold, 30, 240)
```

**Otsu 算法**：遍历 0~255 所有可能阈值，将像素分为前景(≤t)和背景(>t)两类，计算类间方差 `σ² = w_b · w_f · (m_b - m_f)²`，使 σ² 最大的 t 即为最佳阈值。使用直方图实现，复杂度 O(256)。

### 4. 去底处理

生成文本掩码：`text_mask = (gray < threshold) & ~red_mask`

形态学去噪：
1. 开运算（1×1 核）去除孤立噪点
2. 闭运算填充文字内部孔洞

输出模式：

| 模式 | 条件 | 输出 |
|------|------|------|
| 彩色 | seal_color=True 且有印章 | RGB：白底 + 红色印章原色 + 黑色文字 |
| 二值 | type=1（默认） | 单通道：白底 + 黑色文字 |
| 1bit | type=2 | 8bit 二值 → 1bit 单色位图 |
| 灰度 | type=3 | 单通道：白底 + 原灰度文字 |

### 5. 保存

PNG 格式，300 DPI，optimize=True，compress_level=9。

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| -i/--input | . | 输入图片文件或目录 |
| -o/--output | None | 输出目录名称 |
| --clean | True | 清空输出目录 |
| --offset | 0 | 阈值偏移量（正数文字加粗，负数变细） |
| --type | 1 | 输出类型（1=二值，2=1bit，3=灰度） |
| --seal | False | 印章检测总开关 |
| --sealcolor | False | 印章彩色输出开关 |
| --sealarea | 80 | 印章最小连通域像素面积 |
| --sealmin-sat | 50 | 红色识别最低饱和度（0~255） |
| --workers | CPU 核数 | 并行线程数 |

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
  ├─ 阈值计算
  │   ├─ 非白像素 > 500 → Otsu + offset
  │   └─ 否则 → 128
  │   └─ 限制 [30, 240]
  │
  ├─ 去底处理
  │   ├─ 文本掩码 = (gray < threshold) & ~red_mask
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
```

## 实现要点

- **非白像素子集**：只对 gray < 250 的像素计算 Otsu，排除大量白色背景的干扰。
- **印章排除**：红色像素从文本掩码中排除，防止印章被误判为文字而变黑。
- **offset 微调**：offset > 0 阈值升高，更多像素被判定为文字（加粗）；offset < 0 阈值降低，文字变细。
- **type=2 输出**：先生成 8bit 灰度二值图，再通过 PIL convert("1") 转为 1bit 单色位图，体积最小。
- **并发处理**：基于 FunctionBase 的 ThreadPoolExecutor 并发引擎。
