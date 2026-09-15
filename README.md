# gujitools（古籍重製助手）

古籍处理工具——从 PDF 提取图片、检测裁剪文本区域、去底色二值化、印章保留并生成 PDF。
程序安装后的显示名称与开始菜单项为**古籍重製助手**。

## 两种使用方式

同一个安装包提供**桌面端**与**命令行**两套入口，共用同一套图像处理算法，处理结果完全一致。按场景二选一：

| | 桌面端（GUI） | 命令行（CLI） |
| --- | --- | --- |
| 启动 | 开始菜单「古籍重製助手」，或 `python desktop.py` | 终端 `guji <命令>`，或 `python main.py <命令>` |
| 适合 | 手工逐本处理，需要看预览、手绘修正 | 批量处理、脚本集成、无界面环境 |
| 参数方式 | 表单填写，上次执行的参数自动回填 | 命令行参数，或 `guji.yaml` 配置文件 |
| 中间结果 | 每一步都有预览图可回看 | 直接落盘到输出目录 |

- **处理一两本书、想边看效果边调参数** → 看下面的「使用方式一：桌面端（GUI）」。
- **批量跑几十本、或要集成进脚本 / 定时任务** → 看「使用方式二：命令行（CLI）」。

桌面端的深入文档见 [`docs/gui/`](docs/gui/readme.md)；命令行完整参数见 [`docs/cli.md`](docs/cli.md)。

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

`build.py` 生成 onedir 包，并在成功后调用 Inno Setup 生成带版本号和时间戳的
安装包。构建前应确认 `ISCC.exe` 已安装且位于 Inno Setup 默认安装目录或
`PATH` 中。不要只删除 `dist` 后重复打包；如果当前 Python 环境使用 CUDA 版
PyTorch，PyInstaller 仍会把 CUDA 运行库收集进包中。

> **一次完整构建约 15~20 分钟**，属正常现象（实测 18m32s）：PyInstaller 约
> 9~10 分钟（两次 Analysis + COLLECT 落地 650MB），复制到 `C:\Software\guji`
> 约 3~4 分钟（含旧版备份），Inno Setup 压缩约 110 秒。每个阶段结束会打印
> `⏱️ … 耗时 …`，**长时间无输出不等于卡死**。若把输出接给 `tail`/`grep`
> 之类的过滤器，中间过程会被缓冲到进程结束才显示，看起来像假死。

### CLI 与 GUI 一体打包

程序名为**古籍重製助手**。`python build.py` 一次构建产出**两个可执行文件**，
放进同一个目录并共享同一份 `_internal`：

| 入口           | 产物                     | 类型     | 说明                                      |
| -------------- | ------------------------ | -------- | ----------------------------------------- |
| `main.py`      | `dist/guji/guji.exe`     | console  | 命令行工具，安装后 PATH 中可直接用 `guji`  |
| `desktop.py`   | `dist/guji/guji-gui.exe` | windowed | 桌面 GUI，无控制台窗口，安装包建快捷方式  |

两者由 `guji.spec` 的两次 `Analysis` + 一次 `COLLECT` 合并产出。这样 torch/cv2/Qt
等数百 MB 的二进制只在 `_internal` 里落地一份；若分两次独立打包再塞进同一个
安装包，torch 会出现两份（约 +600MB）。

**不重复打包组件**：每个入口只收集自己真正用到的东西。

- 两边共用：`functions` / `utils` / `weights` / `static` / `docs`（GUI 的 worker
  子进程要跑同样的 CLI 功能）；
- **只进 GUI**：`desktop` 子模块与 `desktop/static` 图标——CLI 完全不碰 desktop，
  若一起收集会把 66 个 desktop 模块 + 103 个 Qt 模块白白塞进 CLI 的字节码包；
- PYZ（纯 Python 字节码）是每个 EXE 各自内嵌的，torch 等的 `.py` 无法跨 EXE
  共享，这属于双 EXE 结构的固有开销。

GUI 依赖（PySide6 / PySide6-Fluent-Widgets）也装在 `yolobuild` 里——构建时
只补装 `requirements.txt` 之外的 GUI 增量，不整表重装 `requirements.gui.txt`，
以免 pip 重新解析依赖链时把 CPU 版 torch 顶掉。

安装后：

- **CLI**：`{app}` 已加入当前用户 PATH，重开终端即可 `guji --help`；
- **GUI**：开始菜单「古籍重製助手」（安装时可选桌面快捷方式）；
- GUI 的重处理子进程在打包环境下以 `guji-gui.exe --worker --config …` 启动
  自身（`desktop.py` 负责路由），因此不需要额外的可执行文件。

打包后 `desktop` 包位于 PYZ 字节存档内，磁盘上没有 `desktop/static/icon.png`；
窗口图标改由 `desktop/utils/files.py` 的 `package_dir()` 指向
`_internal/desktop/static`（spec 的 `datas` 已收集该目录）。

### 体积瘦身

`python build.py` 在 PyInstaller 结束后会执行 `prune_bloat()`，并跑
`python tools/check_bloat.py` 复核。清理的是确定用不到的部分：

| 内容 | 约省 | 说明 |
| --- | --- | --- |
| `torch` 源码副本 | 48 MB | `hook-torch.py` 把整个 torch 源码树当 data 收进 `_internal`，而运行时由 FrozenImporter 从 PYZ 加载——磁盘这份是纯重复 |
| `cv2/opencv_videoio_ffmpeg500_64.dll` | 29 MB | 视频编解码，项目只用 `imread`/`imwrite` 等图像 API |
| `PySide6/opengl32sw.dll` | 20 MB | Qt 软件 OpenGL 回退，界面不依赖 OpenGL |
| `torch/bin/protoc.exe` | 3 MB | 构建期工具，运行期不执行 |
| `sqlite3.dll` / `_sqlite3.pyd` | 1.6 MB | 旧数据迁移已移除 |

删 torch 源码时**必须保留少数几个会被 `inspect.getsource()` 读回的文件**
（任意 `config.py`、`config_comms.py`，以及 `utils/_config_module.py`、
`_sources.py`、`fx/experimental/` 下三个内省模块）——否则 `import torch` 会
`OSError: could not get source code`。规则见 `build.py` 的 `_keep_torch_source()`。

`guji.spec` 的 `excludes` 只额外排除了 `sqlite3` 与 pywin32
（`win32com`/`win32api`/`pythoncom`/`pywintypes`，只在 torch 取用户目录的函数内分支用到）。

> ⚠️ **不要再往 `excludes` 里加 `torch.*` 子模块**——实测一个都排不掉：
> `torch.distributions`、`torch._prims`、`torch._inductor`、`torch.distributed`
> 都在 `import torch` 时被顶层引用，`torch.onnx` 更是 `torchvision/ops` 引入的
> （我们正用 `torchvision.ops.nms`）。加了会让 `guji crop` 直接
> `ModuleNotFoundError`。新增排除项前先跑 `python tools/probe_excludes.py <模块名>`。

体积下限由 `torch/lib/torch_cpu.dll`（约 292MB）锁定，不换推理引擎就无法再降。

打包后自检：

```bash
python tools/check_bloat.py    # 确认无用内容没被打回来
python tools/smoke_frozen.py   # frozen 端到端冒烟（含 YOLO 推理）
```

## 使用方式一：桌面端（GUI）

### 启动

安装版直接点开始菜单「古籍重製助手」。从源码启动时：

```bash
# 安装 GUI 依赖（安装版不需要）
python -m pip install -r requirements.gui.txt

# 启动
python desktop.py

# 开发热重载（可选）
hupper -m desktop
```

主窗口标题为**古籍重製助手**。所有任务数据、阶段日志、预览图和缩略图统一保存在
`~/Documents/guji`（纯 JSON 文件，无数据库），卸载后不会被安装包清理。

### 操作步骤

#### 第 0 步：导入 PDF，建立任务

在**任务管理页**点右上角「导入 PDF」，选择一本书：

- 系统先后台计算内容指纹做查重——同一本书重复导入会提示确认；
- 确认后自动分配任务号（`0001`、`0002`…），复制源 PDF 到任务目录，并生成逐页缩略图；
- 表格里每行一个任务，显示任务名、页数与各子任务状态；右侧可删除任务（会清空该任务目录）。

点某一行进入**任务详情页**，顶部步骤条即为下面四步。

#### 第 1 步：提取图片（extract）

把 PDF 逐页提取成图片，输出到任务目录 `stages/extract/`。

- 面板可选渲染倍率（zoom）、输出格式（jpg/png）、**快速模式 quick** 等参数；
- **quick 默认开启**：直接取 PDF 内嵌的 jpg/png 图（原样落盘，不重新编码），
  通常更快、分辨率也更高。一页有多张图、内嵌格式是 jp2/jbig2 等、或内嵌图
  比整页渲染还小时，会**自动降级为整页渲染**，日志里会打印降级原因；
- 多线程并行处理（线程数 = CPU 核数），与命令行同一份实现；
- 若中断过，可用「继续执行（跳过已完成）」只补缺失的页。

#### 第 2 步：检测文本框（detect）

YOLO 识别每页的**左、右文本框**，结果存入 `boxes.json`（不生成图片文件）。

- 预览区可**拖拽、缩放、删除、手绘**调整检测框，手动结果不会被自动检测覆盖；
- 这一步只记坐标，是第 3 步裁剪的依据。

#### 第 3 步：图片去底色（rembg）

整页去底色 / 二值化，支持保留红色印章。这一步是**两段式**，务必按顺序点：

1. 点「**生成预览**」——先产出去底预览图，填好 `area`（区域模式）与 `border`（外扩边距）等参数后生成；
2. 在预览区确认效果，可逐页查看、勾选要保留的页；
3. 点「**提交本次任务**」——按 `area`/`border` + 检测框合成**最终图片**，这才是第 4 步的输入。

> 参数改动后预览图会标记为过期，需重新「生成预览」再提交。

#### 第 4 步：生成 PDF（print）

设置纸张、边距、标题、页码后合成 PDF，产物落在任务目录 `stages/print/`。

- PDF 文件名默认由书名派生为 `书名[重制].pdf`（与标题文字联动，可手工改写）；
- 左侧**待打印列表**的顺序就是 PDF 的页序，**直接拖拽即可调整**（只改数据，不产生任何副本文件）；
- 列表支持「插入图片」（在指定位置插入外部图片）与「删除选中」；
- 右侧表单设置纸张（A3/A4/A5/B5）、横竖方向、页边距、标题文字、页码、跳过的页等；
- 生成完成后「下载 PDF」按钮可用，默认另存到系统「下载」目录。

### 每个阶段都有的能力

- **实时日志**：右下日志区显示子进程输出；可展开为浮层查看完整记录。
- **历史执行记录**：每次运行的参数会被保存，切换阶段时自动回填上次的参数；可从历史里挑一条恢复。
- **预览**：除第 2 步外每步都有预览图，随执行结果刷新。
- **界面不卡**：所有重处理都在独立 Worker 子进程里跑，主界面始终可响应。

界面截图见 [`docs/gui/screenshots/`](docs/gui/screenshots/)：

| 截图 | 内容 |
| --- | --- |
| `01-任务列表页.png` | 任务管理、导入 PDF |
| `02-详情页-提取.png` | 第 1 步 提取图片 |
| `03-详情页-检测.png` | 第 2 步 检测文本框 |
| `04-详情页-去底色.png` | 第 3 步 图片去底色 |
| `05-详情页-生成PDF.png` | 第 4 步 生成 PDF |
| `06-详情页-日志浮层.png` | 日志浮层（完整执行记录） |

### 桌面端开发相关

```bash
# 功能自测（147 项断言）
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py

# 离屏渲染界面截图（视觉自查）
QT_QPA_PLATFORM=offscreen python tests/gui_shot.py D:/tmp/shots
```

改动源码后同步 API 参考（`docs/api/` 为自动生成，不要手工编辑）：

```bash
python tools/gen_api_docs.py          # 重新生成
python tools/gen_api_docs.py --check  # 校验是否与源码一致（退出码非 0 表示过期）
```

## 使用方式二：命令行（CLI）

下面「帮助」「通用参数」「各命令参数」「常用示例」四节均为命令行参数速查；
完整说明见 [CLI 使用说明](docs/cli.md)。

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

### 帮助

```bash
python main.py help                # 功能模块概览
python main.py help extract        # extract 命令手册
python main.py help cropremove    # cropremove 命令手册
python main.py help print         # print 命令手册
python main.py -v                  # 版本信息
```

帮助内容直接读取 `docs/functions/*.md`，终端内分页显示。

### 通用参数

| 参数          | 默认值   | 说明                             |
| ------------- | -------- | -------------------------------- |
| `-i/--input`  | `.`      | 输入路径（文件或目录）           |
| `-o/--output` | None     | 输出目录（未传时按规则自动生成） |
| `--clean`     | 命令相关 | 清空输出目录                     |
| `--workers`   | CPU 核数 | 并行线程数                       |

### 各命令参数

#### extract

| 参数           | 默认值 | 说明                         |
| -------------- | ------ | ---------------------------- |
| `--zoom`       | 1      | 缩放因子（2 = 2 倍分辨率）   |
| `--quick`      | True   | 快速模式（默认开启）：优先取内嵌的 jpg/png 图 |
| `--no-quick`   | —      | 关闭快速模式，始终整页渲染                   |
| `--ext`        | jpg    | 输出格式（jpg/png/tiff）     |
| `--pages`      | None   | 页码字符串，如 `"1,3-5,7"`   |
| `--start`      | None   | 起始页码（1-based）          |
| `--end`        | None   | 结束页码（1-based）          |
| `--batch-size` | 4      | 每批次处理的页数             |

#### rembg

| 参数            | 默认值 | 说明                                     |
| --------------- | ------ | ---------------------------------------- |
| `--offset`      | 0      | 阈值偏移量（正数文字加粗，负数变细）     |
| `--type`        | 1      | 1=8位二值图，2=1bit单色位图，3=8位灰度图 |
| `--seal`        | False  | 印章检测总开关                           |
| `--sealcolor`   | False  | 检测到印章时输出 RGB 彩色图              |
| `--sealarea`    | 80     | 印章最小连通域像素面积                   |
| `--sealmin-sat` | 50     | 红色识别最低饱和度（0~255）              |

#### cropremove

包含 rembg 全部参数，另加：

| 参数       | 默认值 | 说明                                |
| ---------- | ------ | ----------------------------------- |
| `--area`   | 1      | 区域模式（见下表）                  |
| `--border` | None   | 边框控制（mm），CSS 风格 1~4 值写法 |

#### print

`print` 通过 `guji.yaml` 配置，使用 `python main.py run print` 执行。支持 A3、A4、A5、B5 纸张，可配置标题节点、页码和双页左右标注。页序优先取 `files:` 清单（桌面端列表顺序），清单为空时才按文件名排序。

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

### 常用示例

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

详细文档位于 [`docs/`](docs/)。

桌面端（GUI）：

- [桌面端文档索引](docs/gui/readme.md) — 术语、速览、快速开始
- [界面系统](docs/gui/gui-ui-system.md) — 设计令牌、基础控件、自绘约束
- [架构](docs/gui/gui-architecture.md) — 模块结构、进程模型、文件存储与任务目录布局
- [技术规范](docs/gui/gui-technical-spec.md) — Worker 消息协议、JSON 格式、area/border 几何
- [交互设计](docs/gui/gui-design.md) — 导入流程、步骤条、历史配置、检测框编辑
- [布局](docs/gui/gui-layout.md) — 窗口布局与组件尺寸约定

命令行（CLI）：

- [CLI 使用说明](docs/cli.md) — 命令、参数、示例、退出码、架构
- [功能模块概览](docs/functions/overview.md) — 模块清单与命令关系
- [extract 手册](docs/functions/extract.md) — 页码解析、缩放计算、渲染模式
- [crop 手册](docs/functions/crop.md) — YOLO 检测、左右分割算法
- [rembg 手册](docs/functions/rembg.md) — Otsu 阈值、HSV 印章提取
- [cropremove 手册](docs/functions/cropremove.md) — area 区域模式、border 边框控制
- [print 手册](docs/functions/print.md) — 纸张、排序、标题和页码
- [工具函数 API](docs/utils.md) — Otsu、印章、border 解析、YOLO、PDF 渲染

API 参考（由 `tools/gen_api_docs.py` 从源码自动生成，随代码同步）：

- [API 参考索引](docs/api/README.md) — 收录范围与同步方式
- [desktop API](docs/api/desktop.md) — 桌面端全部公开类与函数
- [cli API](docs/api/cli.md) / [functions API](docs/api/functions.md) / [utils API](docs/api/utils.md)
- [入口脚本 API](docs/api/entrypoints.md) — main.py / desktop.py / config.py
