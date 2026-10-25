# extract 功能说明

从 PDF 或 DjVu 文件中批量提取页面为图片，支持缩放、页码选择与多进程处理。

## 命令

```bash
guji extract -i <输入> -o <输出> [选项]
# 别名
guji -e -i <输入> -o <输出> [选项]
# 使用 YAML 配置
guji extract --config ./book.yaml
```

指定 `--config` 时读取配置文件中的 `extract:` 配置块；命令行显式提供的参数
会覆盖配置值。

## 核心算法

### 1. 页码解析

支持两种页码选择方式：

**--pages 字符串**（优先级更高）：

```
--pages "1,3-5,7"  → 提取第 1,3,4,5,7 页
```

**--start / --end 整数对**：

```
--start 3 --end 10  → 提取第 3~10 页
```

未指定时提取全部页面。页码为 1-based，内部转为 0-based。

### 2. 缩放计算

限制最大输出宽度为 6000px，防止内存溢出：

```
if 页面宽度 > 3000pt:
    zoom = 1  # 已足够宽，不放大
elif 页面宽度 × zoom > 6000:
    zoom = 6000 / 页面宽度  # 限制最大宽度
else:
    zoom = 用户指定值
```

**整页渲染另有 DPI 下限**（`--dpi`，默认 300）：

```
渲染 zoom = max(上面算出的 zoom, dpi / 72)   # 仍受 6000px 封顶
```

原因是 PDF 的页面单位是 pt（1pt = 1/72 inch），PyMuPDF 在 zoom=1 时把 1pt
渲染成 1px —— 也就是 72 DPI。古籍扫描件不受影响（走内嵌图，分辨率由扫描件
决定），但**普通矢量 PDF**没有内嵌图，只能整页渲染，zoom=1 就只有 72 DPI，
去底色后再打回 PDF 必然发虚。补到 300 DPI 后 A4 约 2480×3509，足够打印。

⚠️ 这个下限**只作用于整页渲染**：取内嵌图时按原图字节落盘，既不放大
（原图就是原图），也不会因为下限变严而被判成「低清」降级——否则 240 DPI
的扫描件会被重新渲染成插值放大图，反而更糊。
想回到旧行为（`zoom` 完全说了算），把 `--dpi` 设成 72 即可。

### 3. DjVu 支持（.djvu / .djv）

DjVu 走 **djvu-rs**（纯 Rust 解码，`pip install djvu-rs`，无需安装 DjVuLibre）：
每页按**原生分辨率 × zoom** 解码成图片，受 6000px 宽度封顶。

- DjVu 页面自带原生扫描分辨率，因此**不套 PDF 的 300 DPI 下限**——补 DPI
  只是放大插值，细节不会变多，文件反而更大。要更高分辨率请用 `--zoom`；
- `--quick` / `--dpi` 对 DjVu 无效（没有"内嵌原图直拷"这条捷径）；
- 其余参数（`--pages` / `--start` / `--end` / `--ext` / `--workers` 等）与 PDF 相同。

### 4. 渲染模式

**自动直取（quick=True，默认）**：`zoom=1` 时自动判断能否直接取内嵌图。

只在**同时满足**下面条件时才直取，否则**整页渲染**（图片 + 文字 + 水印等
一起合成，不会丢内容）；判定见 `utils.pdf_extract._embedded_page_image()`：

1. `zoom=1` —— `zoom≠1` 一律整页渲染（直取需要重采样，尺寸口径容易乱）；
2. 本页**只有一张**内嵌图；
3. 页面上**没有其他可见内容**：无可见文字（不可见 OCR 文字层不算）、无矢量
   绘制、无注释（`/Link` 链接除外）、无旋转、无裁切框、图片铺满整页；
4. 内嵌格式是 **jpg/png**（或可降档解码的 jpx/jp2，按目标分辨率只解所需小波层）；
5. 内嵌图像素 **不低于整页渲染尺寸的 90%**（`QUICK_MIN_COVERAGE`）——
   否则是低清缩略图/装饰图，取它只会更糊。

满足时的两种落盘方式：

- **直拷**：内嵌格式与目标 `ext` 同类（jpg→jpg、png→png）且 zoom=1 时，
  直接把 PDF 里的压缩字节写成文件，**零解码零重编码**（最快，实测约 2 倍）；
- **转码**：格式不同或 zoom≠1 时解码再编码，参数与标准模式一致。

降级情况会在结束时打印一行汇总，例如：

```
ℹ️  quick：12/12 页降级整页渲染（内嵌格式 .jpx（非 jpg/png，解码重编码不划算） ×12）
```

**标准模式（quick=False）**：始终用 PyMuPDF 渲染整页。

- JPEG: quality=95, subsampling=0
- PNG: 无损
- 输出尺寸 = 页面 pt 尺寸 × zoom（受 6000px 上限保护）

### 5. 多进程批量处理

- 将页码列表切分为批次（batch_size，默认 4）
- 使用 `ProcessPoolExecutor`（多进程）并行处理各批次
- 线程安全的进度计数器（lock 保护）
- CLI 与 GUI **共用同一份**并发实现 `render_pages_parallel()`
  （GUI 曾经直接调 `process_page_batch()` 串行跑全部页，是提取慢的主因）

实测加速（12 页、JPEG 扫描件）：单线程 0.54s → 8 线程 0.28s（约 1.9x）。
注意 **JP2/JBIG2 压缩的 PDF 基本吃不到并行收益** —— 瓶颈在解码器本身且是串行的，
此时提升主要来自 quick 直拷或降级判断，而不是加线程。

## 参数说明

| 参数         | 默认值   | 说明                                   |
| ------------ | -------- | -------------------------------------- |
| -i/--input   | .        | PDF/DjVu 文件路径或包含它们的目录      |
| -o/--output  | None     | 输出目录名称                           |
| --zoom       | 1        | 缩放因子（整数，如 2 表示 2 倍分辨率） |
| --dpi        | 300      | 整页渲染的 DPI 下限（内嵌图路径不生效；DjVu 不适用） |
| --quick      | True     | 快速模式（优先提取内嵌图片；DjVu 忽略） |
| --ext        | jpg      | 输出格式（jpg/png/tiff）               |
| --pages      | None     | 页码字符串（如 "1,3-5,7"）             |
| --start      | None     | 起始页码（1-based）                    |
| --end        | None     | 结束页码（1-based）                    |
| --workers    | 按机器动态（≤8） | 线程数（CPU+内存双约束）      |
| --batch-size | 4        | 每批次处理的页数                       |
| --clean      | False    | 清空输出目录                           |

## 输出命名规则

```
输入: book.pdf（10 页）
输出目录: book/
  ├── 1.jpg
  ├── 2.jpg
  ├── ...
  └── 10.jpg

输入: book.djvu（同样 10 页）
输出目录: book/
  └── …（命名规则与 PDF 完全相同）
```

- 文件名 = 页码（1-based）+ 扩展名
- 一页永远只产出一个文件（多图页整页渲染，不会产出 `3_1.jpg`）

## 处理流程

```
输入路径（文件或目录）
  │
  ├─ 遍历找到所有 PDF / DjVu
  │
  ├─ 对每个源文件:
  │   ├─ 打开文档，获取总页数（PDF→PyMuPDF，DjVu→djvu-rs）
  │   ├─ 解析页码（--pages 或 --start/--end）
  │   ├─ 计算实际缩放因子（限制 6000px；PDF 整页渲染还兜 300 DPI 下限）
  │   ├─ 切分批次
  │   │
  │   └─ 多进程处理各批次:
  │       ├─ 打开源文件
  │       ├─ 对每页:
  │       │   ├─ DjVu → djvu-rs 按原生分辨率 × zoom 解码
  │       │   ├─ PDF quick=True → 提取内嵌图片 / 渲染整页
  │       │   ├─ PDF quick=False → 渲染整页
  │       │   ├─ 保存为 jpg/png/tiff
  │       │   └─ 更新进度计数器
  │       └─ 关闭源文件
  │
  └─ 打印统计信息
```

## 示例

```bash
# 基本提取
guji extract -i book.pdf -o ./images

# 高分辨率提取
guji extract -i book.pdf -o ./images --zoom 2

# 指定页码范围
guji extract -i book.pdf -o ./images --pages "1,3-5,7"

# 使用 start/end
guji extract -i book.pdf -o ./images --start 3 --end 10

# PNG 无损输出
guji extract -i book.pdf -o ./images --ext png

# 标准模式（渲染整页，不用内嵌图片）
guji extract -i book.pdf -o ./images --zoom 2

# 多线程
guji extract -i book.pdf -o ./images --workers 8 --batch-size 8

# 目录批量处理
guji extract -i ./pdfs/ -o ./images/
```

## 实现要点

- **quick 模式**：PDF 可能内嵌了原始扫描图片，直接提取比渲染更快。但若内嵌图片分辨率不足，应使用标准模式。
- **缩放限制**：古籍扫描 PDF 通常页面宽度很大，zoom=2 可能导致输出图片超过 6000px，此时自动降低 zoom。
- **JPEG 质量**：渲染/转码路径 quality=95, subsampling=0（无色度抽样）；quick 直拷路径**原样写 PDF 内嵌 JPEG 字节**，不重编码（质量与体积由源文件决定）。
- **不使用 FunctionBase 并发引擎**：页面渲染的并发逻辑在 `utils.pdf_extract` 内部实现，ExtractFunction 直接重写 `execute()`。
- **clean 默认值**：extract 的 clean 默认为 False（不自动清空），其他功能默认 True。
