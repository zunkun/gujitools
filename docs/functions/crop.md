# crop 功能说明

基于 YOLO 目标检测定位图片中的左右文本框，按 `--area`/`--border` 规则裁剪并导出原图像素。

与 `cropremove` 共享相同的检测与裁剪规则（共同继承 `TextRegionProcessor` 基类），区别是 crop **不做 Otsu 去底色**，仅裁剪原始彩色像素。

## 命令

```bash
guji crop -i <输入> -o <输出> [选项]
guji crop --config ./book.yaml
```

指定 `--config` 时读取配置文件中的 `crop:` 配置块；命令行显式提供的参数会
覆盖配置值，例如 `guji crop --config ./book.yaml --area 2`。

## 核心算法

### YOLO 检测 + 左右分割

1. 使用 YOLO 模型对图片推理，获取所有文本框；
2. 计算每个框的水平中心 `cx = (x1 + x2) / 2`；
3. 以图像宽度一半 `w/2` 为分界线：
   - `cx < w/2` → 归入 left 组
   - `cx >= w/2` → 归入 right 组
4. 每组按面积降序排序，取 `[0]` 作为最大候选框。

### 模型加载

- 权重文件路径：`gujitools/weights/detect.pt`
- 延迟加载 + 模块级单例 + 双重检查锁，确保多线程下只加载一次
- 强制 CPU 模式运行

## 参数说明

| 参数        | 默认值   | 说明                                |
| ----------- | -------- | ----------------------------------- |
| -i/--input  | .        | 输入图片文件或目录                  |
| -o/--output | None     | 输出目录名称                        |
| --area      | 1        | 区域模式（详见下表）                |
| --border    | None     | 边框控制（mm），CSS 风格 1~4 值写法 |
| --clean     | False    | 清空输出目录                        |
| --workers   | CPU 核数 | 并行线程数                          |

### --area（区域模式）

控制裁剪区域与输出方式，默认 1。

| area | 裁剪方式               | 输出方式                              | border=None 时 |
| ---- | ---------------------- | ------------------------------------- | -------------- |
| 1    | 逐框独立裁剪           | 分别裁剪左右框，输出 `-l`/`-r` 两张图 | 裁剪到各框边界 |
| 2    | 逐框独立裁剪           | 单图，ROI 写回原位置                  | 输出原尺寸     |
| 3    | 合并左右框为整体外边界 | 单图，ROI 写回原位置                  | 输出原尺寸     |

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

- 实际框（box）经 `_process_roi` 裁剪后粘贴到检测侧
- 另一侧为空白（白色），宽度与实际框相同
- gap = 10mm（按 300 DPI 换算约 118px）
- 输出尺寸：高 = top + box_h + bottom，宽 = left + box_w + gap + box_w + right

**CSS 风格写法**（mm→px 按 300 DPI 换算）：

```
--border 30              # [30,30,30,30] 四边统一
--border 20,30           # [20,30,20,30] 上下20，左右30
--border 20,30,25        # [20,30,25,30] 上20，左右30，下25
--border 10,20,30,40     # [10,20,30,40] 上右下左
```

## 输出命名规则

### area=1（默认，分框裁剪输出）

```
输入: page3.jpg（检测到左右两个框）
输出: page3-l.png（左框裁剪）
      page3-r.png（右框裁剪）

输入: page5.jpg（仅检测到右框）
输出: page5-r.png

输入: page7.jpg（未检测到任何框）
输出: page7.png（原图拷贝，状态为 no_detect）
```

### area=2/3（单图输出）

```
输入: page3.jpg
输出: page3.png
```

- 输出格式统一为 **PNG**（300 DPI）
- area=1 左框加 `-l` 后缀，右框加 `-r` 后缀
- 无检测时输出原图（无视 area_mode），返回 `no_detect` 状态

## 完整行为矩阵

| area | border      | 输出尺寸                         | 输出文件       |
| ---- | ----------- | -------------------------------- | -------------- |
| 1    | None        | 裁剪到各框边界                   | -l.png, -r.png |
| 1    | 0           | 裁剪到各框边界                   | -l.png, -r.png |
| 1    | 值          | 各框 + 外扩边距                  | -l.png, -r.png |
| 2    | None        | 原尺寸                           | .png           |
| 2    | 0           | 裁剪到联合外边界                 | .png           |
| 2    | 值          | 联合 + 外扩边距                  | .png           |
| 2    | 值 + 仅单框 | 对称布局（框+空白镜像+10mm间隔） | .png           |
| 3    | None        | 原尺寸                           | .png           |
| 3    | 0           | 裁剪到合并边界                   | .png           |
| 3    | 值          | 合并 + 外扩边距                  | .png           |
| 3    | 值 + 仅单框 | 对称布局（框+空白镜像+10mm间隔） | .png           |

## 处理流程

```
图片输入
  │
  ├─ 文件过小？ → 跳过
  │
  ├─ cv2 读取（BGR）
  │
  ├─ YOLO 检测 → 左右分组（按面积降序取最大框）
  │
  ├─ 无文本框？→ 输出原图，返回 no_detect
  │
  ├─ 记录原始框数量（single_box_detected）
  │
  ├─ area=3 且左右框均存在 → 合并为整体外边界
  │
  ├─ border 参数解析 (mm→px @300dpi)
  │
  ├─ 单框 + area=2/3 + border有值 → 对称输出（实际框+空白镜像+10mm间隔）
  │
  ├─ area=1 → 逐框裁剪原图像素，分别输出 -l/-r
  │   area=2 → 逐框裁剪，单图输出
  │   area=3 → 合并裁剪，单图输出
  │
  └─ 保存为 PNG (300 DPI)
```

## 示例

```bash
# 默认模式：分框裁剪输出 -l/-r
guji crop -i ./images -o ./cropped

# 单文件
guji crop -i page3.jpg -o ./output

# 合并模式 + 外扩 30mm 边距
guji crop -i ./images -o ./output --area 3 --border 30

# 单图模式 + 自定义边距（上20 右30 下20 左25）
guji crop -i ./images -o ./output --area 2 --border 20,30,20,25

# 清空输出目录重新处理
guji crop -i ./images -o ./output --clean
```

## 实现要点

- **继承 TextRegionProcessor**：与 `cropremove` 共享 YOLO 检测 + area/border 规则 + 输出构建流程，仅 `_process_roi` 不同（crop 裁剪原图像素，cropremove 做 Otsu）。
- **不做去底色处理**：仅裁剪，保留原始图像质量，后续可配合 `rembg` 命令处理。
- **并发处理**：基于 FunctionBase 的 ThreadPoolExecutor 并发引擎。
- **无检测 fallback**：直接输出原图到输出目录，返回 `no_detect` 状态，便于后续人工排查。
- **与 cropremove 的关系**：`cropremove --area 1` 等同于 `crop --area 1` + 对每个裁剪结果执行 Otsu 去底色。两者的 area/border 规则完全一致。
