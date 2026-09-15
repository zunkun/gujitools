# print 生成 PDF

将图片合成为 PDF，支持标题、章节节点、页码、双页左右标注和多种纸张尺寸。

页序有两个来源：**显式清单 `files`**（优先，桌面端第四步的列表顺序）或
**按文件名推导**（`files` 为空时的命令行独立用法）。

## 命令

`print` 仅通过配置文件执行：

```bash
guji run print
guji run print --config ./guji.yaml
```

配置文件默认是当前目录下的 `guji.yaml`。

## 基本配置

```yaml
print:
  input: ./rembg
  pdf_name: book.pdf

  paper_size: B5
  orientation: portrait
  page_margins: [20, 20, 20, 20]
  title_printing: true
  title_text: 古籍名称
  page_number_printing: true
  page_number_start_page: 2
  page_number_base: 200
```

## 配置参数

以下字段均位于 `print:` 下：

| 参数                      | 默认值          | 说明                                                       |
| ------------------------- | --------------- | ---------------------------------------------------------- |
| `input`                   | `.`             | 输入图片文件或目录；相对路径相对于配置文件所在项目目录解析 |
| `files`                   | None            | 显式页序清单（图片路径数组）；非空时**直接采用其顺序**，不再解析文件名 |
| `output`                  | None            | 输出目录；未指定时自动创建，`pdf_name` 是其中的 PDF 文件名 |
| `pdf_name`                | `output.pdf`    | 输出 PDF 文件名                                            |
| `clean`                   | False           | 统一配置字段；PDF 生成不会清空输入或输出目录               |
| `paper_size`              | `A4`            | 纸张尺寸，仅支持 `A3`、`A4`、`A5`、`B5`                    |
| `orientation`             | `landscape`     | 页面方向：`landscape` 横向、`portrait` 纵向                |
| `page_margins`            | `[20,20,20,20]` | 通用页边距，顺序为上、右、下、左，单位 mm                  |
| `left_page_margins`       | None            | 左页专用页边距；与右页配置同时存在时启用左右页覆盖         |
| `right_page_margins`      | None            | 右页专用页边距；格式同 `page_margins`                      |
| `title_printing`          | False           | 是否打印标题                                               |
| `title_text`              | `""`            | 默认标题；为空时不打印标题                                 |
| `title_font_size`         | 18              | 标题字号，单位 pt                                          |
| `title_color`             | `0,0,0`         | 标题颜色，格式为 `r,g,b`，范围 0 到 255                    |
| `title_position`          | `top`           | 标题位置：`top` 或 `bottom`                                |
| `title_orientation`       | `vertical`      | 标题方向：`vertical` 或 `horizontal`                       |
| `title_switch_nodes`      | None            | 标题切换节点，格式为 `[原始页码, 标题, side]`              |
| `page_number_printing`    | False           | 是否打印页码                                               |
| `page_number_start_page`  | 1               | 从排序后第几张图片开始标注，1-based                        |
| `page_number_end_page`    | None            | 标注结束的图片序号；为空表示到最后                         |
| `page_number_base`        | 0               | 页码基数；显示页码为基数加图片序号                         |
| `page_number_font_size`   | 12              | 页码字号，单位 pt                                          |
| `page_number_color`       | `0,0,0`         | 页码颜色，格式为 `r,g,b`                                   |
| `page_number_position`    | `bottom`        | 页码位置：`top` 或 `bottom`                                |
| `page_number_orientation` | `vertical`      | 页码方向：`vertical` 或 `horizontal`                       |
| `skip_pages`              | None            | 跳过的页：纯数字按**清单序号**（1 起），其余按文件名匹配   |
| `workers`                 | 4               | 图片加载线程数                                             |

输出 PDF 默认创建在输入目录的自动输出目录中，也可以通过 `output` 指定输出目录。

## 纸张与方向

`paper_size` 支持以下四种尺寸，单位为 mm：

| 尺寸 | 纵向      | 横向      |
| ---- | --------- | --------- |
| A3   | 297 × 420 | 420 × 297 |
| A4   | 210 × 297 | 297 × 210 |
| A5   | 148 × 210 | 210 × 148 |
| B5   | 176 × 250 | 250 × 176 |

```yaml
paper_size: B5
orientation: portrait
```

图片会在页边距以内按比例缩放，并为标题和页码预留左右空白。页面尺寸不会写死为 A4，标题、页码和图片布局会根据实际纸张尺寸计算。

## 图片排序

页序有两个来源，优先使用显式清单：

### 1. 显式清单 `files`（推荐，桌面端使用）

`files` 是**按最终页序排列的图片路径数组**。只要它非空，就完全采用其顺序，
**不再解析、也不再对文件名排序**——文件名只是标识，页序由数据层决定。桌面端
第四步列表里的拖拽重排、插入、删除只改动这份清单，不产生任何副本文件。

```yaml
print:
  input: ./rembg
  files:
    - E:/books/rembg/5.png
    - E:/books/rembg/1.png
    - E:/books/rembg/3.png   # 实际页序即为 5 → 1 → 3
```

清单中指向不存在文件的条目会被静默跳过，不会让整次打印失败。

### 2. 按文件名推导（`files` 为空时的命令行独立用法）

图片按以下规则排序：

1. `cover` 图片优先，`menu` 图片其次；
2. 数字文件名按数字大小排序，而不是按字符串排序；
3. 同一数字前缀按 `-r`、`-l`、无后缀排序；
4. 例如：

```text
1-r.png
1-l.png
2-r.png
2-l.png
3.png
```

排序结果与上面相同。文件名中的 `-l` 和 `-r` 用于标题节点定位；页码和标题实际放在左侧还是右侧，按排序后的图片序号交替决定。

## 页码

```yaml
page_number_printing: true
page_number_start_page: 2
page_number_end_page:
page_number_base: 200
page_number_font_size: 18
page_number_color: 0,0,0
page_number_position: bottom
page_number_orientation: vertical
```

- `page_number_start_page` 是排序后图片的物理序号，从 1 开始，不是文件名中的数字；
- 实际显示页码为 `page_number_base + 图片序号`；
- 起始图片固定使用左侧，后续图片在同一区间内按左、右、左、右交替；
- 例如排序结果为 `1-r.png, 1-l.png, 2-r.png, 2-l.png`，且起始序号为 2：
  - `1-l.png` 显示第一页页码并放在左侧；
  - `2-r.png` 显示下一页页码并放在右侧；
  - 即使 `2-r.png` 缺失，`2-l.png` 仍按下一张图片放在右侧；
- `page_number_end_page` 为空时标注到最后一张图片。

页码位置支持 `top`、`bottom`，文字方向支持 `vertical`、`horizontal`。

## 标题与章节节点

```yaml
title_printing: true
title_text: 古籍名称
title_font_size: 18
title_color: 0,0,0
title_position: top
title_orientation: vertical
title_switch_nodes:
	- [1, 雙溪倡和詩 序, left]
	- [7, 雙溪倡和詩 目錄, left]
	- [12, 雙溪倡和詩 卷一, left]
```

节点格式为 `[文件名前缀数字, 标题, side]`：

- 数字表示章节对应的图片组，例如 `1` 对应 `1-r.png`、`1-l.png`、`1.png`；
- `side` 支持 `left`、`right`、`both`，省略时默认为 `left`；
- 节点会定位到指定数字组中匹配 side 的图片；指定图片不存在时回退到该组无后缀图片或该组第一张图片；
- 节点是章节区间的起点，后续节点到达前都使用该标题；
- 节点的 side 同时作为该章节区间左右交替的起始侧；
- 标题只从 `page_number_start_page` 开始打印，但章节标题状态会按已到达节点计算。

> 节点的数字是**原始页码**，不是清单下标：填「15」指原书第 15 页。即使该页被
> 拖到清单别处，标题切换仍会按同名回查跟着这一页走。

## 页边距与图片布局

页边距顺序为 `[上, 右, 下, 左]`，支持单值、两值或四值：

```yaml
page_margins: [20, 20, 20, 20]
left_page_margins:
right_page_margins:
```

也可以使用字符串形式，例如 `"20,30"` 表示上下 20 mm、左右 30 mm。设置 `left_page_margins` 和 `right_page_margins` 后，可分别覆盖左右页的通用边距。

图片保持原始宽高比，自动缩放到可用区域内，不会因切换 A3、A4、A5 或 B5 而使用固定页面尺寸。

## 图片过滤与其他参数

`input` / `output` / `pdf_name` / `clean` 见上方

[配置参数](#配置参数)表；图片过滤与并发相关的补充项：

| 参数         | 默认值 | 说明                                                                    |
| ------------ | ------ | ----------------------------------------------------------------------- |
| `skip_pages` | None   | 纯数字按**清单序号**（1 起，与桌面端表单一致）；`5-r` 之类按文件名匹配  |
| `workers`    | 4      | 图片加载线程数                                                          |

示例：

```yaml
skip_pages: [cover, menu]   # 按文件名跳过
skip_pages: [1, 3]          # 按清单序号跳过第 1、3 页
workers: 4
```

## 完整示例

```yaml
print:
	input: E:\books\rembg
	pdf_name: book.pdf
	paper_size: B5
	orientation: portrait
	page_margins: [20, 20, 20, 20]
	title_printing: true
	title_text: 古籍名称
	title_font_size: 18
	title_color: 0,0,0
	title_position: top
	title_orientation: vertical
	title_switch_nodes:
		- [1, 雙溪倡和詩 序, left]
		- [7, 雙溪倡和詩 目錄, left]
		- [12, 雙溪倡和詩 卷一, left]
	page_number_printing: true
	page_number_start_page: 2
	page_number_end_page:
	page_number_base: 200
	page_number_font_size: 18
	page_number_color: 0,0,0
	page_number_position: bottom
	page_number_orientation: vertical
	skip_pages:
	workers: 4
```
