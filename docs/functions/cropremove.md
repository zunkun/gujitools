# cropremove 功能说明

复合流程：基于 YOLO 检测定位文本框 → **每个框各自裁剪并做 Otsu 去底色**。
等同于 `crop` + `rembg` 的一步完成。

与 `crop` 共享相同的检测与裁剪规则（共同继承 `TextRegionProcessor` 基类），区别是 cropremove 的 ROI 做 **Otsu 二值化去底色**，并支持印章保留。

> ⚠️ 2026-10-22 起**没有 `--area` 参数**：检测出几个文本框就裁几张图。
> 半幅页（左右两栏）输出 `-l`/`-r`，整幅页用页名输出一张，无框页整图去底色。

## 命令

```bash
guji cropremove -i <输入> -o <输出> [选项]
# 别名
guji -cr -i <输入> -o <输出> [选项]
# 使用 YAML 配置
guji cropremove --config ./book.yaml
```

指定 `--config` 时读取配置文件中的 `cropremove:` 配置块；命令行显式提供的
参数会覆盖配置值，例如 `guji cropremove --config ./book.yaml --border 20`。

## 核心算法

### 1. YOLO 检测文本框

使用 YOLO 模型对图片推理，检测到的框按**水平中心**（cx = (x1+x2)/2）与图像中线（w/2）的关系分为 left / right 两组（仅 `harfcontent` 半幅；`fullcontent` 整幅只有一个框，不拆左右）。每组取面积最大的候选框。

> **检测来自 `functions/detect.py`**：与 `crop` 一样，`cropremove` 调用
> `functions.detect.detect_page_content(img, model)` 取框，不自己实现检测
> （`cropremove` = `detect` + 裁剪 + 去底色）。GUI 第 2 步用的是同一个函数。

### 2. 阈值计算

从 left + right 两个文本框区域提取灰度像素，合并后调用 `calculate_auto_threshold`（Otsu 大津法）计算**共享阈值**。

```
threshold = Otsu(left_pixels + right_pixels) + offset
# 限制范围 [30, 240]
```

### 3. Otsu 去底

对每个文本框区域按阈值生成文本掩码（gray < threshold = 文字），经形态学开闭运算去噪后，生成白底黑字输出。可选排除红色印章像素。

### 4. 输出类型

| type | 模式           | 说明                         |
| ---- | -------------- | ---------------------------- |
| 1    | 二值图（默认） | 文字=0（黑），背景=255（白） |
| 2    | 1bit 单色位图  | 二值图转 1bit，体积最小      |
| 3    | 灰度图         | 文字保留原灰度值，层次更丰富 |

## 参数说明

### --border（边框控制，单位 mm）

控制每张裁剪图在框外再外扩多少留白。**默认 0**（紧裁到文本框边界）：
第四步会在 A4 上重新排版，前面再外扩留白等于双重留白。

| border 值     | 输出                              |
| ------------- | --------------------------------- |
| None / 0      | 裁剪到每个框的边界（紧裁）        |
| 有值（如 30） | 每个框边界 + 外扩空白             |

**CSS 风格写法**（mm→px 按 300 DPI 换算）：

```
--border 30              # [30,30,30,30] 四边统一
--border 20,30           # [20,30,20,30] 上下20，左右30
--border 20,30,25        # [20,30,25,30] 上20，左右30，下25
--border 10,20,30,40     # [10,20,30,40] 上右下左
```

### 印章相关参数

| 参数          | 默认值           | 说明                                 |
| ------------- | ---------------- | ------------------------------------ |
| --seal        | False            | 印章检测总开关                       |
| --sealcolor   | False            | 检测到印章时输出 RGB 彩色图保留红色  |
| --sealarea    | 80               | 印章最小连通域像素面积               |
| --sealmin-sat | 50               | 红色识别最低饱和度（0~255）          |
| --offset      | 0                | 阈值偏移量（正数文字加粗，负数变细） |
| --type        | 1                | 输出类型（1=二值，2=1bit，3=灰度）   |
| --workers     | 按机器动态（≤8） | 并行线程数（CPU+内存双约束）         |

## 输出命名规则

```
输入: page3.jpg（检测到左右两个框）
输出: page3-l.png（左框去底色）
      page3-r.png（右框去底色）

输入: page5.jpg（仅检测到左框）
输出: page5-l.png

输入: page6.jpg（整幅页，一个框）
输出: page6.png

输入: page7.jpg（未检测到框）
输出: page7.png（整图去底色）
```

- 输出格式由 `--ext` 决定（默认 **PNG**，300 DPI）
- 左框加 `-l` 后缀，右框加 `-r` 后缀；整幅页不带后缀
- 无检测框时不做裁剪，**整图 Otsu 去底色**后输出

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
  ├─ 无文本框？ → 整图 Otsu 去底色
  │
  ├─ 子类预处理：RGB/灰度/印章掩码/共享阈值 → 返回 ctx
  │
  ├─ border 参数解析 (mm→px)
  │
  ├─ 逐框循环：每个框 → 一张图（框 + border）
  │
  └─ 保存（PNG / jpg / tiff，300 DPI）
```

## 示例

```bash
# 每个检测框各裁一张并去底色（半幅页输出 -l/-r）
guji cropremove -i ./images -o output

# 外扩 30mm 边距
guji cropremove -i ./images -o output --border 30

# 印章保留
guji cropremove -i ./images -o output --seal --sealcolor

# 自定义边距
guji cropremove -i ./images -o output --border 20,30,20,25

# 灰度输出 + 阈值偏移
guji cropremove -i ./images -o output --type 3 --offset -5
```

## 实现要点

- **继承 TextRegionProcessor**：与 `crop` 共享 YOLO 检测 + 逐框裁剪 + 输出构建流程。子类仅实现差异方法：`_on_boxes_detected`（计算阈值并返回 ctx）、`_process_roi`（对 ROI 做 Otsu）、`_handle_no_boxes`（无框时整图 Otsu）、`_save_output`（按 type 保存）。
- **线程安全（ctx 模式）**：每张图的 `img_rgb`/`gray`/`threshold`/`red_mask` 通过 `_on_boxes_detected` 返回的 ctx 字典传递，**绝不写入 self 实例变量**。这是因为 `FunctionBase.execute()` 使用 `ThreadPoolExecutor` 并发处理多张图，若状态存于 self 会被并发覆盖（曾导致输出尺寸错乱）。
- **阈值共享**：每个框共用同一阈值（从 left+right 合并像素计算），保证同一页输出一致。
- **印章排除**：启用 `--seal` 时，红色像素从文本掩码中排除，防止印章被误判为文字。
- **border 换算**：mm→px 按 300 DPI（古籍扫描常用值），`px = mm × 300 / 25.4`。
- **无框 fallback**：整图 Otsu 去底色后输出。
- **并发处理**：基于 ThreadPoolExecutor，默认使用全部 CPU 核心。
