# extract 功能说明

从 PDF 文件中批量提取页面为图片，支持缩放、页码选择与多线程处理。

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

### 3. 渲染模式

**快速模式（quick=True，默认）**：优先取 PDF 内嵌图片。

只在**同时满足**下面三条时才走快路径，否则**自动降级为整页渲染**
（判定见 `utils.pdf_utils._embedded_page_image()`）：

1. 本页**只有一张**内嵌图 —— 一页多图时老实现会产出 `1_1.jpg`/`1_2.jpg`
   多个文件，而 detect/rembg/print 都按「一页一图」工作，多出来的文件会变成
   孤儿页；
2. 内嵌格式是 **jpg/png** —— jp2/jbig2/CCITT 之类必须解码再重编码，很可能比
   整页渲染还慢（"quick" 名不副实），而且 PIL 缺对应解码器时整页会直接失败；
3. 内嵌图像素 **不低于整页渲染尺寸的 90%**（`QUICK_MIN_COVERAGE`）——
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

### 4. 多线程批量处理

- 将页码列表切分为批次（batch_size，默认 4）
- 使用 ThreadPoolExecutor 并行处理各批次
- 线程安全的进度计数器（lock 保护）
- CLI 与 GUI **共用同一份**并发实现 `render_pages_parallel()`
  （GUI 曾经直接调 `process_page_batch()` 串行跑全部页，是提取慢的主因）

实测加速（12 页、JPEG 扫描件）：单线程 0.54s → 8 线程 0.28s（约 1.9x）。
注意 **JP2/JBIG2 压缩的 PDF 基本吃不到并行收益** —— 瓶颈在解码器本身且是串行的，
此时提升主要来自 quick 直拷或降级判断，而不是加线程。

## 参数说明

| 参数         | 默认值   | 说明                                   |
| ------------ | -------- | -------------------------------------- |
| -i/--input   | .        | PDF 文件路径或包含 PDF 的目录          |
| -o/--output  | None     | 输出目录名称                           |
| --zoom       | 1        | 缩放因子（整数，如 2 表示 2 倍分辨率） |
| --quick      | True     | 快速模式（优先提取内嵌图片）           |
| --ext        | jpg      | 输出格式（jpg/png/tiff）               |
| --pages      | None     | 页码字符串（如 "1,3-5,7"）             |
| --start      | None     | 起始页码（1-based）                    |
| --end        | None     | 结束页码（1-based）                    |
| --workers    | CPU 核数 | 线程数                                 |
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
