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

国内网络环境可以为普通 PyPI 依赖选择镜像源。清华源示例：

```bash
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

阿里云源示例：

```bash
python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
```

### 创建 CPU 打包环境

建议使用独立的 `yolobuild` 环境打包，避免继承开发环境中的 CUDA 版 PyTorch：

```bash
conda create -n yolobuild python=3.10 -y
conda activate yolobuild
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
python -c "import torch; print(torch.__version__); print('torch cuda:', torch.version.cuda); print('cuda available:', torch.cuda.is_available())"
python build.py
```

现在直接执行 `python build.py` 会自动检查并准备 `yolobuild`，然后在该环境中
继续执行打包。如果没有安装 Conda，则直接使用当前 Python 环境继续打包；手动
激活环境主要用于提前安装或检查依赖。

PyTorch CPU wheel 建议使用官方 CPU 源；清华源或阿里云源用于安装其他 PyPI
依赖。部分镜像不一定同步完整的 PyTorch CPU wheel，强行从镜像安装可能又装回
CUDA 版本或找不到对应版本。

项目不使用 OpenCV 的窗口、摄像头或 GUI 接口，因此依赖已使用
`opencv-python-headless` 替代 `opencv-python`。它仍然提供 `import cv2` 和图像
处理功能，但不会携带 GUI 相关库；如果以后增加 `imshow` 等窗口功能，再改回
`opencv-python`。注意：`ultralytics` 的依赖声明可能再次安装完整的
`opencv-python`，自动构建会在依赖安装后卸载它并重新固定为 headless 版本。

主要依赖（详见 [requirements.txt](requirements.txt)）：

| 依赖                   | 用途          | 命令                      |
| ---------------------- | ------------- | ------------------------- |
| PyMuPDF                | PDF 渲染      | extract                   |
| PyYAML                 | YAML 配置读取 | run                       |
| Pillow                 | 图像读写      | 所有图像命令              |
| opencv-python-headless | 图像处理      | rembg / crop / cropremove |
| numpy                  | 数组运算      | rembg / crop / cropremove |
| ultralytics            | YOLO 模型推理 | crop / cropremove         |
| fpdf2                  | PDF 生成      | run                       |

YOLO 模型权重文件需放置于 `weights/detect.pt`。

### Windows CPU 环境与打包体积

`ultralytics` 使用的是 PyTorch。`pip install ultralytics` 会根据当前 Python
软件源和环境安装 PyTorch；如果环境中安装的是 CUDA 版 PyTorch，`build.py`
会把 CUDA 运行库一起收集到 `dist/guji`，安装包可能达到数 GB。

可以用下面的命令确认当前环境：

```bash
python -c "import torch; print(torch.__version__); print('torch cuda:', torch.version.cuda); print('cuda available:', torch.cuda.is_available())"
```

如果输出的 `torch cuda` 不是 `None`，说明当前是 CUDA 版 PyTorch。仅使用 CPU
进行 YOLO 推理时，应先安装 PyTorch CPU 版，再安装项目依赖：

```bash
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
```

再次确认时，`torch cuda` 应为 `None`。CPU 版仍会包含 `torch_cpu.dll`，所以安装
包不会变成很小，但不应再包含 `torch_cuda.dll`、`cudnn*.dll`、`cublas*.dll`、
`cudart*.dll` 等 CUDA 文件。

使用 CPU 环境重新构建：

```bash
python build.py
```

`build.py` 默认生成 onedir 包，并在成功后调用 Inno Setup 生成带版本号和时间戳
的安装包。构建前应确认 `ISCC.exe` 已安装且位于 Inno Setup 默认安装目录或
`PATH` 中。不要只删除 `dist` 后重复打包；如果当前 Python 环境使用 CUDA 版
PyTorch，PyInstaller 仍会把 CUDA 运行库收集进包中。

## 快速开始

### 推荐工作流：先初始化配置

首次使用时，建议先执行 `guji init` 生成 `guji.yaml`。初始化命令会引导设置
项目元信息和原始 PDF 或图片目录，后续可以通过配置文件统一执行各个流程：

```bash
guji init
```

交互示例：

```text
guji.yaml 已存在，是否覆盖？(y/N) y
请输入项目信息（直接回车使用默认值）：
项目名称 (default: 我的古籍项目): 古籍处理
项目描述 (default: 示例古籍数字化处理):
版本号 (default: 1.0.0):
原始 PDF 或图片目录 (default: ./sample.pdf): c:/a/b/c.pdf
✅ 已生成配置文件: D:\workspace\gujitools\guji.yaml
```

生成 `guji.yaml` 后，按处理顺序执行对应子命令：

```bash
# 1. 从 PDF 提取图片
guji run extract

# 2. 裁剪文本框
guji run crop

# 3. 去底色
guji run rembg

# 4. 裁剪并去底色
guji run cropremove

# 5. 生成 PDF
guji run print
```

也可以指定配置文件：

```bash
guji run crop --config ./book.yaml
guji run print --config ./book.yaml
```

`guji run <command>` 会读取配置文件中对应的配置块，例如 `run crop` 读取
`guji.yaml` 的 `crop` 部分。执行 `print` 时必须使用 `guji run print`，不能
直接执行 `guji print`。

普通子命令也支持指定配置文件。此时 YAML 配置作为基础值，命令行中显式提供
的参数优先级更高：

```bash
guji crop --config ./book.yaml
guji crop --config ./book.yaml --area 2
guji rembg --config ./book.yaml --type 3
guji cropremove --config ./book.yaml --area 3 --border 30
guji extract --config ./book.yaml --pages "1,3-5"
```

`--config` 会读取与命令同名的配置块，例如 `guji crop --config ./book.yaml`
读取 `book.yaml` 中的 `crop:` 部分。`print` 仍然只能通过 `guji run print`
执行。

### 直接使用 CLI 子命令

不需要配置文件时，也可以直接执行子命令，并通过参数指定输入、输出和处理选项：

```bash
# 从 PDF 提取图片
python main.py extract -i book.pdf -o ./images --zoom 2

# 裁剪文本框
python main.py crop -i ./images -o ./cropped

# 去底色（二值化）
python main.py rembg -i ./images -o ./output

# 一步完成裁剪 + 去底色
python main.py cropremove -i ./images -o ./output --area 1
```

安装包或已加入 PATH 后，可以将 `python main.py` 替换为 `guji`：

```bash
guji extract -i book.pdf -o ./images --zoom 2
guji crop -i ./images -o ./cropped
guji rembg -i ./images -o ./output
guji cropremove -i ./images -o ./output --area 1
```

详细参数和示例见 [CLI 使用说明](docs/cli.md) 及各功能手册。

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
