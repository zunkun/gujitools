# gujitools

古籍处理命令行工具——从 PDF 提取图片、检测裁剪文本区域、去底色二值化、印章保留并生成 PDF。

## 功能一览

| 命令         | 别名  | 功能                                    |
| ------------ | ----- | --------------------------------------- |
| `extract`    | `-e`  | 从 PDF 批量提取页面为图片               |
| `crop`       | —     | 基于 YOLO 检测裁剪左右文本框            |
| `rembg`      | `-r`  | 整图去底色 / 二值化 / 印章保留          |
| `cropremove` | `-cr` | 复合流程：裁剪 + 区域去底色（一步完成） |
| `print`      | —     | 将图片目录生成为 PDF                    |

```
extract   ── PDF → 图片（前置步骤）
   │
   ▼
crop      ── 仅裁剪文本框（保留原图质量）
   │
   ▼
rembg     ── 整图去底色（无文本框检测）

cropremove = crop + rembg（支持 area/border 精细控制）
   │
   ▼
print     ── 图片目录 → PDF（支持 A3/A4/A5/B5、标题和页码）
```

## 安装

Python 3.10

```bash
pip install -r requirements.txt
```

主要依赖（详见 [requirements.txt](requirements.txt)）：

| 依赖          | 用途          | 命令                      |
| ------------- | ------------- | ------------------------- |
| PyMuPDF       | PDF 渲染      | extract                   |
| Pillow        | 图像读写      | 所有图像命令              |
| opencv-python | 图像处理      | rembg / crop / cropremove |
| numpy         | 数组运算      | rembg / crop / cropremove |
| ultralytics   | YOLO 模型推理 | crop / cropremove         |

YOLO 模型权重文件需放置于 `weights/detect.pt`。

## 快速开始

```bash
# 1. 从 PDF 提取图片
python main.py extract -i book.pdf -o ./images --zoom 2

# 2. 裁剪文本框
python main.py crop -i ./images -o ./cropped

# 3. 去底色（二值化）
python main.py rembg -i ./images -o ./output

# 一步完成裁剪 + 去底色
python main.py cropremove -i ./images -o ./output --area 1

# 根据 guji.yaml 生成 PDF
python main.py run print
```

## 帮助

```bash
python main.py help                # 功能模块概览
python main.py help extract        # extract 命令手册
python main.py help cropremove    # cropremove 命令手册
python main.py help print         # print 命令手册
python main.py -v                  # 版本信息
```

帮助内容直接读取 `docs/functions/*.md`，终端内分页显示。

## 通用参数

| 参数          | 默认值   | 说明                             |
| ------------- | -------- | -------------------------------- |
| `-i/--input`  | `.`      | 输入路径（文件或目录）           |
| `-o/--output` | None     | 输出目录（未传时按规则自动生成） |
| `--clean`     | 命令相关 | 清空输出目录                     |
| `--workers`   | CPU 核数 | 并行线程数                       |

## 各命令参数

### extract

| 参数           | 默认值 | 说明                         |
| -------------- | ------ | ---------------------------- |
| `--zoom`       | 1      | 缩放因子（2 = 2 倍分辨率）   |
| `--quick`      | True   | 快速模式（优先提取内嵌图片） |
| `--ext`        | jpg    | 输出格式（jpg/png/tiff）     |
| `--pages`      | None   | 页码字符串，如 `"1,3-5,7"`   |
| `--start`      | None   | 起始页码（1-based）          |
| `--end`        | None   | 结束页码（1-based）          |
| `--batch-size` | 4      | 每批次处理的页数             |

### rembg

| 参数            | 默认值 | 说明                                     |
| --------------- | ------ | ---------------------------------------- |
| `--offset`      | 0      | 阈值偏移量（正数文字加粗，负数变细）     |
| `--type`        | 1      | 1=8位二值图，2=1bit单色位图，3=8位灰度图 |
| `--seal`        | False  | 印章检测总开关                           |
| `--sealcolor`   | False  | 检测到印章时输出 RGB 彩色图              |
| `--sealarea`    | 80     | 印章最小连通域像素面积                   |
| `--sealmin-sat` | 50     | 红色识别最低饱和度（0~255）              |

### cropremove

包含 rembg 全部参数，另加：

| 参数       | 默认值 | 说明                                |
| ---------- | ------ | ----------------------------------- |
| `--area`   | 1      | 区域模式（见下表）                  |
| `--border` | None   | 边框控制（mm），CSS 风格 1~4 值写法 |

### print

`print` 通过 `guji.yaml` 配置，使用 `python main.py run print` 执行。支持 A3、A4、A5、B5 纸张，图片按文件名排序生成 PDF，并可配置标题节点、页码和双页左右标注。

```yaml
print:
  input: ./rembg
  pdf_name: book.pdf
  paper_size: B5
  orientation: portrait
  title_printing: true
  page_number_printing: true
  page_number_start_page: 2
  page_number_base: 200
```

完整参数说明见 [print 手册](docs/functions/print.md)。

**--area 区域模式**：

| area | Otsu 作用区域        | 输出方式                  | border=None 时 |
| ---- | -------------------- | ------------------------- | -------------- |
| 1    | 逐框独立（共享阈值） | 分框输出 `-l`/`-r` 两张图 | 裁剪到各框边界 |
| 2    | 逐框独立（共享阈值） | 单图，ROI 写回原位置      | 输出原尺寸     |
| 3    | 合并左右框为整体     | 单图，ROI 写回原位置      | 输出原尺寸     |

**--border 写法**：

```bash
--border 30              # 四边统一 30mm
--border 20,30           # 上下20，左右30
--border 20,30,25        # 上20，左右30，下25
--border 10,20,30,40     # 上右下左
```

## 常用示例

```bash
# 高分辨率提取指定页码
python main.py extract -i book.pdf -o ./images --zoom 2 --pages "1,3-5,7"

# 裁剪 + 去底色，合并模式 + 外扩 30mm 边距
python main.py cropremove -i ./images -o ./output --area 3 --border 30

# 分框模式 + 保留红色印章
python main.py cropremove -i ./images -o ./output --area 1 --seal --sealcolor

# 灰度输出 + 文字变细
python main.py rembg -i ./images -o ./output --type 3 --offset -5

# 1bit 单色位图（最小体积）
python main.py rembg -i ./images -o ./output --type 2

# 使用指定配置文件生成 PDF
python main.py run print --config ./book.yaml
```

## 文档

详细文档位于 [`docs/`](docs/)：

- [CLI 使用说明](docs/cli.md) — 命令、参数、示例、退出码、架构
- [功能模块概览](docs/functions/overview.md) — 模块清单与命令关系
- [extract 手册](docs/functions/extract.md) — 页码解析、缩放计算、渲染模式
- [crop 手册](docs/functions/crop.md) — YOLO 检测、左右分割算法
- [rembg 手册](docs/functions/rembg.md) — Otsu 阈值、HSV 印章提取
- [cropremove 手册](docs/functions/cropremove.md) — area 区域模式、border 边框控制
- [print 手册](docs/functions/print.md) — 纸张、排序、标题和页码
- [工具函数 API](docs/utils.md) — Otsu、印章、border 解析、YOLO、PDF 渲染
