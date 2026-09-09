# extract 功能说明

从 PDF 文件中批量提取页面为图片，支持缩放、页码选择与多线程处理。

## 命令

```bash
guji extract -i <输入> -o <输出> [选项]
# 别名
guji -e -i <输入> -o <输出> [选项]
```

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

### 3. 渲染模式

**标准模式（quick=False，默认）**：
- 使用 PyMuPDF 渲染整页为高质量图片
- JPEG: quality=95, subsampling=0
- PNG: 无损

**快速模式（quick=True）**：
- 优先提取 PDF 内嵌图片（速度快，分辨率取决于内嵌图片）
- `--zoom` 对内嵌图片按**图片原始像素尺寸**缩放（而非 PDF 页面 pt 尺寸），并限制最大输出 6000px
  - 例：图片原始 2400px、zoom=2 → 输出 4800px（非页面 1800pt × 2 = 3600）
  - 图片已 > 3000px 时不放大，保持原始尺寸
- zoom=1 时直接写入原始图片字节，不做任何缩放
- 无内嵌图片时退化为渲染整页
- 多图时加序号后缀：`page3_1.jpg`, `page3_2.jpg`

### 4. 多线程批量处理

- 将页码列表切分为批次（batch_size，默认 4）
- 使用 ThreadPoolExecutor 并行处理各批次
- 线程安全的进度计数器（lock 保护）

## 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| -i/--input | . | PDF 文件路径或包含 PDF 的目录 |
| -o/--output | None | 输出目录名称 |
| --zoom | 1 | 缩放因子（整数，如 2 表示 2 倍分辨率） |
| --quick | True | 快速模式（优先提取内嵌图片） |
| --ext | jpg | 输出格式（jpg/png/tiff） |
| --pages | None | 页码字符串（如 "1,3-5,7"） |
| --start | None | 起始页码（1-based） |
| --end | None | 结束页码（1-based） |
| --workers | CPU 核数 | 线程数 |
| --batch-size | 4 | 每批次处理的页数 |
| --clean | False | 清空输出目录 |

## 输出命名规则

```
输入: book.pdf（10 页）
输出目录: book/
  ├── 1.jpg
  ├── 2.jpg
  ├── ...
  └── 10.jpg
```

- 文件名 = 页码（1-based）+ 扩展名
- 快速模式多图时加序号：`3_1.jpg`, `3_2.jpg`

## 处理流程

```
输入路径（文件或目录）
  │
  ├─ 遍历找到所有 PDF
  │
  ├─ 对每个 PDF:
  │   ├─ 打开文档，获取总页数
  │   ├─ 解析页码（--pages 或 --start/--end）
  │   ├─ 计算实际缩放因子（限制 6000px）
  │   ├─ 切分批次
  │   │
  │   └─ 多线程处理各批次:
  │       ├─ 打开 PDF
  │       ├─ 对每页:
  │       │   ├─ quick=True → 提取内嵌图片 / 渲染整页
  │       │   ├─ quick=False → 渲染整页
  │       │   ├─ 保存为 jpg/png/tiff
  │       │   └─ 更新进度计数器
  │       └─ 关闭 PDF
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
- **JPEG 质量**：标准模式 quality=95, subsampling=0（无色度抽样）；快速模式 quality=85, subsampling=1（4:2:0 色度抽样，体积更小）。
- **不使用 FunctionBase 并发引擎**：PDF 渲染的并发逻辑在 `pdf_utils` 内部实现，ExtractFunction 直接重写 `execute()`。
- **clean 默认值**：extract 的 clean 默认为 False（不自动清空），其他功能默认 True。
