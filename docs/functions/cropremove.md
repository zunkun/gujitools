# cropremove 功能说明

复合流程：基于 YOLO 检测定位左右文本框 → 区域 Otsu 去底色。等同于 `crop` + `rembg` 的一步完成。

与 `crop` 共享相同的检测与裁剪规则（共同继承 `TextRegionProcessor` 基类），区别是 cropremove 的 ROI 做 **Otsu 二值化去底色**，并支持印章保留。

## 命令

```bash
guji cropremove -i <输入> -o <输出> [选项]
# 别名
guji -cr -i <输入> -o <输出> [选项]
```

## 核心算法

### 1. YOLO 文本框检测

使用 YOLO 模型对图片推理，检测到的框按**水平中心**（cx = (x1+x2)/2）与图像中线（w/2）的关系分为 left / right 两组。每组取面积最大的候选框。

### 2. 阈值计算

从 left + right 两个文本框区域提取灰度像素，合并后调用 `calculate_auto_threshold`（Otsu 大津法）计算**共享阈值**。

```
threshold = Otsu(left_pixels + right_pixels) + offset
# 限制范围 [30, 240]
```

### 3. Otsu 去底

对灰度图按阈值生成文本掩码（gray < threshold = 文字），经形态学开闭运算去噪后，生成白底黑字输出。可选排除红色印章像素。

### 4. 输出类型

| type | 模式           | 说明                         |
| ---- | -------------- | ---------------------------- |
| 1    | 二值图（默认） | 文字=0（黑），背景=255（白） |
| 2    | 1bit 单色位图  | 二值图转 1bit，体积最小      |
| 3    | 灰度图         | 文字保留原灰度值，层次更丰富 |

## 参数说明

### --area（区域模式）

控制 Otsu 作用区域与输出方式，默认 1。

| area | Otsu 作用区域        | 输出方式                              | border=None 时 |
| ---- | -------------------- | ------------------------------------- | -------------- |
| 1    | 逐框独立（共享阈值） | 分别裁剪左右框，输出 `-l`/`-r` 两张图 | 裁剪到各框边界 |
| 2    | 逐框独立（共享阈值） | 单图，ROI 写回原位置                  | 输出原尺寸     |
| 3    | 合并左右框为整体     | 单图，ROI 写回原位置                  | 输出原尺寸     |

### --border（边框控制，单位 mm）

控制输出图像的裁剪与外扩边距，对 area=1/2/3 均生效，默认 None。

| border 值     | area=1              | area=2/3               |
| ------------- | ------------------- | ---------------------- |
| None          | 裁剪到各框边界      | 输出原尺寸             |
| 0             | 裁剪到各框边界      | 裁剪到文本框联合外边界 |
| 有值（如 30） | 各框边界 + 外扩空白 | 联合外边界 + 外扩空白  |

**对称输出规则**：area=2/3 + border 有值 + **仅检测到一个文本框**时，输出对称布局——实际框 + border 在检测侧，另一侧为等宽空白镜像，中间间隔 10mm。使单张图也呈现完整的双栏版面。

布局示意（检测到右框，is_left=False）：

```
+------------ top ------------+
|                            |
|  left | blank | gap | box | right |
|                            |
+---------- bottom ----------+
```

- 实际框（box）经 `_process_roi` 做 Otsu 去底后粘贴到检测侧
- 另一侧为空白（白色），宽度与实际框相同
- gap = 10mm（按 300 DPI 换算约 118px）
- 输出尺寸：高 = top + box_h + bottom，宽 = left + box_w + gap + box_w + right

`single_box_detected` 在 area=3 合并前判断，因此"一个框"指的是检测到左框或右框中的一个，而非合并后的结果。

**CSS 风格写法**（mm→px 按 300 DPI 换算）：

```
--border 30              # [30,30,30,30] 四边统一
--border 20,30           # [20,30,20,30] 上下20，左右30
--border 20,30,25        # [20,30,25,30] 上20，左右30，下25
--border 10,20,30,40     # [10,20,30,40] 上右下左
```

### 印章相关参数

| 参数          | 默认值   | 说明                                 |
| ------------- | -------- | ------------------------------------ |
| --seal        | False    | 印章检测总开关                       |
| --sealcolor   | False    | 检测到印章时输出 RGB 彩色图保留红色  |
| --sealarea    | 80       | 印章最小连通域像素面积               |
| --sealmin-sat | 50       | 红色识别最低饱和度（0~255）          |
| --offset      | 0        | 阈值偏移量（正数文字加粗，负数变细） |
| --type        | 1        | 输出类型（1=二值，2=1bit，3=灰度）   |
| --workers     | CPU 核数 | 并行线程数                           |

## 输出命名规则

### area=1（默认，分框裁剪输出）

```
输入: page3.jpg（检测到左右两个框）
输出: page3-l.png（左框去底色）
      page3-r.png（右框去底色）

输入: page5.jpg（仅检测到左框）
输出: page5-l.png

输入: page7.jpg（未检测到框）
输出: page7.png（原图拷贝）
```

### area=2/3（单图输出）

```
输入: page3.jpg
输出: page3.png
```

## 完整行为矩阵

| area | border      | 输出尺寸                         | Otsu | 输出文件       |
| ---- | ----------- | -------------------------------- | ---- | -------------- |
| 1    | None        | 裁剪到各框边界                   | 逐框 | -l.png, -r.png |
| 1    | 0           | 裁剪到各框边界                   | 逐框 | -l.png, -r.png |
| 1    | 值          | 各框 + 外扩边距                  | 逐框 | -l.png, -r.png |
| 2    | None        | 原尺寸                           | 逐框 | .png           |
| 2    | 0           | 裁剪到联合外边界                 | 逐框 | .png           |
| 2    | 值          | 联合 + 外扩边距                  | 逐框 | .png           |
| 2    | 值 + 仅单框 | 对称布局（框+空白镜像+10mm间隔） | 逐框 | .png           |
| 3    | None        | 原尺寸                           | 合并 | .png           |
| 3    | 0           | 裁剪到合并边界                   | 合并 | .png           |
| 3    | 值          | 合并 + 外扩边距                  | 合并 | .png           |
| 3    | 值 + 仅单框 | 对称布局（框+空白镜像+10mm间隔） | 逐框 | .png           |

## 处理流程

```
图片输入
  │
  ├─ 文件过小？ → 跳过
  │
  ├─ cv2 读取（BGR）
  │
  ├─ YOLO 检测 → 左右文本框分割
  │
  ├─ 无文本框？
  │   ├─ area=1 → 输出原图（BGR→RGB 转换后保存）
  │   └─ area=2/3 → 整图 Otsu 去底
  │
  ├─ 子类预处理：RGB/灰度/印章掩码/共享阈值 → 返回 ctx
  │
  ├─ 记录原始框数量（single_box_detected，合并前判断）
  │
  ├─ area=3 且左右框均存在 → 合并为整体外边界
  │
  ├─ border 参数解析 (mm→px)
  │
  ├─ 单框 + area=2/3 + border有值 → 对称输出（实际框+空白镜像+10mm间隔）
  │
  ├─ area=1 → 逐框 Otsu，分别输出 -l/-r
  │   area=2 → 逐框 Otsu，单图输出
  │   area=3 → 合并 Otsu，单图输出
  │
  └─ 保存为 PNG (300 DPI)
```

## 示例

```bash
# 默认模式：分框裁剪输出
guji cropremove -i ./images -o output

# 合并模式 + 外扩 30mm 边距
guji cropremove -i ./images -o output --area 3 --border 30

# 分框模式 + 印章保留
guji cropremove -i ./images -o output --area 1 --seal --sealcolor

# 单图模式 + 自定义边距
guji cropremove -i ./images -o output --area 2 --border 20,30,20,25

# 灰度输出 + 阈值偏移
guji cropremove -i ./images -o output --type 3 --offset -5
```

## 实现要点

- **继承 TextRegionProcessor**：与 `crop` 共享 YOLO 检测 + area/border 规则 + 输出构建流程。子类仅实现差异方法：`_on_boxes_detected`（计算阈值并返回 ctx）、`_process_roi`（对 ROI 做 Otsu）、`_handle_no_boxes`（无框时整图 Otsu 或输出原图）、`_save_output`（按 type 保存）。
- **线程安全（ctx 模式）**：每张图的 `img_rgb`/`gray`/`threshold`/`red_mask` 通过 `_on_boxes_detected` 返回的 ctx 字典传递，**绝不写入 self 实例变量**。这是因为 `FunctionBase.execute()` 使用 `ThreadPoolExecutor` 并发处理多张图，若状态存于 self 会被并发覆盖（曾导致输出尺寸错乱）。
- **阈值共享**：无论 area 模式如何，阈值始终从 left+right 合并像素计算，保证一致性。
- **印章排除**：启用 `--seal` 时，红色像素从文本掩码中排除，防止印章被误判为文字。
- **border 换算**：mm→px 按 300 DPI（古籍扫描常用值），`px = mm × 300 / 25.4`。
- **无框 fallback**：area=1 输出原图（BGR→RGB 转换后保存），area=2/3 退化为整图 Otsu。
- **并发处理**：基于 ThreadPoolExecutor，默认使用全部 CPU 核心。
