# CLI 使用说明

程序入口：`python cli.py <command> [options]`，或打包后的可执行文件 `guji <command> [options]`。

## 推荐工作流

首次使用时，先生成配置文件：

```bash
guji init
```

`guji init` 会交互式询问项目名称、描述、版本号和原始 PDF 或图片目录，不会单独
询问输出目录。例如：

```text
guji.yaml 已存在，是否覆盖？(y/N) y
请输入项目信息（直接回车使用默认值）：
项目名称 (default: 我的古籍项目): 古籍处理
项目描述 (default: 示例古籍数字化处理):
版本号 (default: 1.0.0):
原始 PDF 或图片目录 (default: ./sample.pdf): c:/a/b/c.pdf
✅ 已生成配置文件: D:\workspace\gujitools\guji.yaml
```

然后按 `guji.yaml` 中对应的配置块执行命令：

```bash
guji run extract
guji run crop
guji run rembg
guji run cropremove
guji run print
```

配置模板里还有一段 `detect`（非必要）——它默认关闭（`save: false`），
只在你**想单独查看检测结果**时才需要执行 `guji run detect`。
`crop` / `cropremove` 内部已含检测，日常流程删掉整段 `detect:` 也不影响。

也可以指定配置文件：

```bash
guji run crop --config ./book.yaml
guji run print --config ./book.yaml
```

不需要配置文件时，可以直接执行 CLI 子命令，例如：

```bash
guji extract -i book.pdf -o ./images
guji crop -i ./images -o ./cropped
guji rembg -i ./images -o ./output
guji cropremove -i ./images -o ./output --area 1
```

`print` 的业务参数来自 YAML 配置，必须使用 `guji run print`，不能直接使用
`guji print`。

普通子命令也支持 `--config`：

```bash
guji crop --config ./book.yaml
guji crop --config ./book.yaml --area 2
guji rembg --config ./book.yaml --type 3
guji cropremove --config ./book.yaml --area 3 --border 30
guji extract --config ./book.yaml --pages "1,3-5"
```

该选项读取 YAML 中与命令同名的配置块，配置值作为基础值；命令行显式提供的
参数优先覆盖配置值。`print` 仍只能使用 `guji run print`。

未定义的参数会输出警告并忽略；已定义参数仍会校验类型和取值。例如，`-b c`
不会阻止命令执行，但 `--area x` 或 `--area` 缺少值仍会报错。

## 帮助

```bash
guji -h                  # 显示快速帮助（命令一览）
guji --help              # 同上
guji help                # 显示功能模块概览（docs/functions/overview.md）
guji help <command>      # 查看指定命令的详细手册（docs/functions/<command>.md）
guji -v                  # 显示版本
```

可用帮助主题：

| 命令                   | 内容              |
| ---------------------- | ----------------- |
| `guji help overview`   | 功能模块概览      |
| `guji help extract`    | PDF 提取手册      |
| `guji help detect`     | 文本框检测手册    |
| `guji help crop`       | 文本框裁剪手册    |
| `guji help rembg`      | 去底色手册        |
| `guji help cropremove` | 复合流程手册      |
| `guji help print`      | 图片生成 PDF 手册 |

帮助内容直接读取 `docs/functions/*.md`，经 Markdown→纯文本转换后用 `less`/`more` 分页显示。无需维护额外 `.txt` 帮助文件。

## 命令一览

| 命令         | 别名  | 功能                       | 详细文档                                 |
| ------------ | ----- | -------------------------- | ---------------------------------------- |
| `extract`    | `-e`  | 从 PDF 提取页面为图片      | [extract.md](../functions/extract.md)       |
| `detect`     | —     | 检测左右文本框坐标         | [detect.md](../functions/detect.md)         |
| `crop`       | —     | 基于 YOLO 裁剪左右文本框   | [crop.md](../functions/crop.md)             |
| `rembg`      | `-r`  | 整图去底色/二值化/印章保留 | [rembg.md](../functions/rembg.md)           |
| `cropremove` | `-cr` | 复合流程：裁剪 + 去底色    | [cropremove.md](../functions/cropremove.md) |
| `print`      | —     | 将图片目录生成为 PDF       | [print.md](../functions/print.md)           |

> 注：`detect` 是**非必要**步骤。`crop = detect + 裁剪`、`cropremove = detect + 裁剪 + 去底色`，
> 两者内部已自动调用同一套检测算法，因此日常流程不必单独执行 `detect`。
> 该命令用于**单独查看检测结果**：默认只输出坐标、不生成任何文件；
> 加 `--save` 才会把标注图画到原图上落地（视觉与桌面端 detect 阶段一致）。

## 通用参数

以下参数所有命令通用：

| 参数          | 默认值   | 说明                                                      |
| ------------- | -------- | --------------------------------------------------------- |
| `-i/--input`  | `.`      | 输入路径（文件或目录），内部自动 `expanduser().resolve()` |
| `-o/--output` | None     | 输出目录名称（纯名称或完整路径）                          |
| `--clean`     | False    | 处理前清空输出目录；CLI 下所有命令默认 False（保留既有输出） |
| `--workers`   | CPU 核数 | 并行线程数                                                |

> `--clean` 是 `store_true` 开关，不传即 False。注意 `FunctionBase.execute()` 内部
> 取该键时兜底为 `True`，因此**自建参数字典（不经 `CommandArgs`）时必须显式给
> `clean`**，否则会意外清空输出目录。

## 路径规则

所有命令遵循统一的输入/输出路径规则，详见 [io_path_rules.md](../dev/io_path_rules.md)：

- **未传 `-o`**：文件输入 → 父目录/默认目录名；目录输入 → 输入目录/默认目录名
- **纯名称**（无 `/` `\`）：相对于 `parent_path` 创建
- **完整路径**：直接作为绝对输出目录

默认输出目录名：extract=PDF文件名、detect=`detect`（仅 `--save` 时）、
crop=`crop`、rembg=`rembg`、cropremove=`rembg`

## 各命令参数

### extract — PDF 提取图片

| 参数           | 默认值 | 说明                                               |
| -------------- | ------ | -------------------------------------------------- |
| `--zoom`       | 1      | 缩放因子（整数，如 2 表示 2 倍分辨率）             |
| `--dpi`        | 300    | 整页渲染的 DPI 下限（内嵌图路径不生效，72=旧行为） |
| `--quick`      | True   | 快速模式（默认开启）：优先取 PDF 内嵌的 jpg/png 图 |
| `--no-quick`   | —      | 关闭快速模式，始终整页渲染                         |
| `--ext`        | jpg    | 输出格式（jpg/png/tiff）                           |
| `--pages`      | None   | 页码字符串（如 `"1,3-5,7"`），优先级高于 start/end |
| `--start`      | None   | 起始页码（1-based）                                |
| `--end`        | None   | 结束页码（1-based）                                |
| `--batch-size` | 4      | 每批次处理的页数                                   |
| `--clean`      | False  | 清空输出目录                                       |

### detect — 文本框检测（非必要）

检测整页图片中的左右文本框，并把标注图（左框绿色、右框蓝色 + 坐标文字）
落地。**命令行下 `--save` 必须给**，否则命令被直接拒绝：

```bash
$ guji detect -i ./images
ERROR: 'detect' 不接受空跑（既未指定 --save，就不会产生任何文件）。
```

原因：命令行执行 detect 的唯一目的就是落地标注图；不落盘时坐标只会打到
stdout，没有任何产出去处（`crop` / `cropremove` 内部各自都会重新检测）。
作为**代码调用**（`functions.detect.detect_page_boxes`）不受此限制，
可以只取坐标不落盘。

`crop` / `cropremove` 内部已经包含这一步，因此日常流程不必单独执行 `detect`；
本命令用于单独查看检测结果、排查「框检不到 / 框位置不对」的问题。

| 参数        | 默认值 | 说明                                          |
| ----------- | ------ | --------------------------------------------- |
| `--save`    | False  | 把检测结果画到图片上并保存（**命令行必填**）   |
| `--ext`     | png    | 标注图格式（jpg/png/tiff）                    |
| `--clean`   | False  | 清空输出目录                                  |

`-o/--output` 指定输出根目录，其下自动追加 `detect` 子目录。

```bash
# 落地标注图：左框绿色、右框蓝色，各带坐标文字
# 默认输出到 <输入父目录>/detect（与 crop 同级、和输入目录并列）
guji detect -i ./images --save
guji detect -i ./images --save -o ./detect-out --ext png
```

详见 [functions/detect.md](../functions/detect.md)。

### crop — 文本框裁剪

基于 YOLO 检测左右文本框并裁剪输出原图像素，支持 area/border 控制（与 cropremove 共享规则，但不做 Otsu 去底色）。

| 参数       | 默认值 | 说明                                |
| ---------- | ------ | ----------------------------------- |
| `--area`   | 1      | 区域模式（详见下表）                |
| `--border` | None   | 边框控制（mm），CSS 风格 1~4 值写法 |

**--area 区域模式**：

| area | 裁剪方式               | 输出方式                              | border=None 时 |
| ---- | ---------------------- | ------------------------------------- | -------------- |
| 1    | 逐框独立裁剪           | 分别裁剪左右框，输出 `-l`/`-r` 两张图 | 裁剪到各框边界 |
| 2    | 逐框独立裁剪           | 单图，ROI 写回原位置                  | 输出原尺寸     |
| 3    | 合并左右框为整体外边界 | 单图，ROI 写回原位置                  | 输出原尺寸     |

**--border 边框控制**（mm→px 按 300 DPI 换算）：

| border 值     | area=1          | area=2/3         |
| ------------- | --------------- | ---------------- |
| None          | 裁剪到各框边界  | 输出原尺寸       |
| 0             | 裁剪到各框边界  | 裁剪到联合外边界 |
| 有值（如 30） | 各框 + 外扩空白 | 联合 + 外扩空白  |

> 特殊：area=2/3 + border有值 + 仅单框 → 对称输出（实际框+空白镜像+10mm间隔，构成完整双栏版面）。

### rembg — 去底色

| 参数            | 默认值 | 说明                                               |
| --------------- | ------ | -------------------------------------------------- |
| `--offset`      | 0      | 阈值偏移量（正数文字加粗变深，负数变细）           |
| `--type`        | 1      | 输出类型：1=8位二值图，2=1bit单色位图，3=8位灰度图 |
| `--seal`        | False  | 印章检测总开关                                     |
| `--sealcolor`   | False  | 检测到印章时输出 RGB 彩色图保留红色                |
| `--sealarea`    | 80     | 印章最小连通域像素面积                             |
| `--sealmin-sat` | 50     | 红色识别最低饱和度（0~255）                        |

> 输出格式固定为 **PNG**（不可配置）：`type=2` 的 1bit 单色位图只有 PNG 能无损
> 承载，JPEG 会把它重新糊成灰阶。因此 `rembg` 没有 `--ext` 参数。

### print — 图片生成 PDF

`print` 的业务参数通过 `guji.yaml` 配置，使用 `guji run print` 执行。

| 参数                     | 默认值          | 说明                               |
| ------------------------ | --------------- | ---------------------------------- |
| `files`                  | None            | 显式页序清单（图片路径数组），非空时直接采用其顺序 |
| `paper_size`             | A4              | A3、A4、A5 或 B5                   |
| `orientation`            | landscape       | `portrait` 纵向或 `landscape` 横向 |
| `page_margins`           | `[20,20,20,20]` | 上、右、下、左，单位 mm            |
| `title_printing`         | False           | 是否打印标题                       |
| `title_switch_nodes`     | None            | 章节节点 `[原始页码, 标题, side]`  |
| `page_number_printing`   | False           | 是否打印页码                       |
| `page_number_start_page` | 1               | 从排序后第几张图片开始标注         |
| `page_number_base`       | 0               | 显示页码基数                       |
| `skip_pages`             | None            | 纯数字按清单序号（1 起），其余按文件名 |
| `workers`                | 4               | 图片加载线程数                     |

> 以上只是常用键；完整参数表（`left_page_margins`、`title_text`、字号/颜色/方向、
> `page_number_end_page` 等）见 [print.md](../functions/print.md)。

**页序**：`files` 非空时完全按清单顺序生成，不再解析文件名；为空时才按文件名排序。
桌面端第四步的列表顺序就是通过 `files` 传给本命令的。详细的排序、双页左右标注和
YAML 示例见 [print.md](../functions/print.md)。

### cropremove — 裁剪 + 去底色

包含 rembg 的全部参数，另加：

| 参数       | 默认值 | 说明                                |
| ---------- | ------ | ----------------------------------- |
| `--area`   | 1      | 区域模式（详见下表）                |
| `--border` | None   | 边框控制（mm），CSS 风格 1~4 值写法 |

**--area 区域模式**：

| area | Otsu 作用区域        | 输出方式                              | border=None 时 |
| ---- | -------------------- | ------------------------------------- | -------------- |
| 1    | 逐框独立（共享阈值） | 分别裁剪左右框，输出 `-l`/`-r` 两张图 | 裁剪到各框边界 |
| 2    | 逐框独立（共享阈值） | 单图，ROI 写回原位置                  | 输出原尺寸     |
| 3    | 合并左右框为整体     | 单图，ROI 写回原位置                  | 输出原尺寸     |

**--border 边框控制**（mm→px 按 300 DPI 换算）：

| border 值     | area=1          | area=2/3         |
| ------------- | --------------- | ---------------- |
| None          | 裁剪到各框边界  | 输出原尺寸       |
| 0             | 裁剪到各框边界  | 裁剪到联合外边界 |
| 有值（如 30） | 各框 + 外扩空白 | 联合 + 外扩空白  |

CSS 风格写法：

```
--border 30              # [30,30,30,30] 四边统一
--border 20,30           # [20,30,20,30] 上下20，左右30
--border 20,30,25        # [20,30,25,30] 上20，左右30，下25
--border 10,20,30,40     # [10,20,30,40] 上右下左
```

## 示例

### extract

```bash
# 从 PDF 提取图片
guji extract -i book.pdf -o ./images

# 高分辨率提取（2 倍缩放）
guji extract -i book.pdf -o ./images --zoom 2

# 指定页码范围
guji extract -i book.pdf -o ./images --pages "1,3-5,7"

# 使用 start/end
guji extract -i book.pdf -o ./images --start 3 --end 10

# PNG 无损输出
guji extract -i book.pdf -o ./images --ext png

# 标准模式（渲染整页，不用内嵌图片）
guji extract -i book.pdf -o ./images --zoom 2

# 目录批量处理
guji extract -i ./pdfs/ -o ./images/

# 多线程 + 大批次
guji extract -i book.pdf -o ./images --workers 8 --batch-size 8
```

### crop

```bash
# 基本裁剪（默认 area=1，分框输出 -l/-r）
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

### rembg

```bash
# 基本二值化
guji rembg -i ./images -o ./output

# 保留红色印章（彩色输出）
guji rembg -i ./images -o ./output --seal --sealcolor

# 灰度输出（保留原灰度层次）
guji rembg -i ./images -o ./output --type 3

# 调整阈值（文字加粗）
guji rembg -i ./images -o ./output --offset 10

# 1bit 单色位图（最小体积）
guji rembg -i ./images -o ./output --type 2

# 自定义印章参数
guji rembg -i ./images -o ./output --seal --sealcolor --sealarea 120 --sealmin-sat 60
```

### cropremove

```bash
# 默认模式（area=1，分框裁剪输出 -l/-r）
guji cropremove -i ./images -o ./output

# 合并模式 + 外扩 30mm 边距
guji cropremove -i ./images -o ./output --area 3 --border 30

# 分框模式 + 印章保留
guji cropremove -i ./images -o ./output --area 1 --seal --sealcolor

# 单图模式 + 自定义边距（上20 右30 下20 左25）
guji cropremove -i ./images -o ./output --area 2 --border 20,30,20,25

# 灰度输出 + 阈值偏移（文字变细）
guji cropremove -i ./images -o ./output --type 3 --offset -5

# 1bit 输出（最小体积）
guji cropremove -i ./images -o ./output --type 2
```

### print

```bash
# 使用当前目录的 guji.yaml
guji run print

# 指定配置文件
guji run print --config ./book.yaml
```

## 退出码

| 退出码 | 含义                           |
| ------ | ------------------------------ |
| 0      | 正常完成                       |
| 1      | 错误（未知命令、功能执行失败） |
| 130    | 用户中断（Ctrl+C）             |

## 架构

```
cli.py                  入口：注册 SIGINT，委托 cli_main()
  └─ cli/__main__.py    参数解析 → CommandArgs → get_function() → execute()
      ├─ cli/cli_args.py    argparse 配置（子命令、参数、别名）
      ├─ cli/command_args.py 标准化参数容器（input→Path，不做 I/O）
      └─ functions/         功能实现
          ├─ base.py           FunctionBase 基类（并发引擎、路径解析）
          ├─ text_region.py    TextRegionProcessor 中间基类（YOLO 检测 + area/border 规则）
          ├─ extract.py        PDF 提取
          ├─ crop.py           文本框裁剪（继承 TextRegionProcessor）
          ├─ rembg.py          去底色
          ├─ crop_remove.py    复合流程（继承 TextRegionProcessor）
          └─ print.py          图片生成 PDF
```

更多参数细节请参阅 [cli/cli_args.py](../../cli/cli_args.py) 源码。
