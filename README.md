# gujitools（古籍重製）

> 文档按读者分家：**想学操作** → [`docs/guide/user-guide.md`](docs/guide/user-guide.md)（用户操作手册）；
> **想了解代码/打包/架构** → 本 README 与 [`docs/dev/`](docs/README.md)；
> AI 助手与新人从仓库根 [`AGENTS.md`](AGENTS.md) 入手。

古籍处理工具——从 PDF 提取图片、检测裁剪文本区域、去底色二值化、印章保留并生成 PDF。
程序安装后的显示名称与开始菜单项为**古籍重製**。

## 下载（Windows）

**不用装 Python。** 打开最新版 Release 页面，自行下载其中的 Windows 安装包：

👉 **[Windows 安装包](https://github.com/zunkun/gujitools/releases/latest)**

- 要下的文件是 Release 页里的 `guji_setup_*.exe`（约 192 MB，桌面端与命令行一体，依赖已内置，装上就能用）
- 系统要求 **Windows 10 (1809) 及以上 / Windows 11**，64 位
- 装好后：开始菜单「古籍重製」进桌面端；命令行 `guji` 会自动加入 PATH

其他平台（Linux / Ubuntu）没有现成安装包，需从源码自行打包，见下文「Linux / Ubuntu 打包」。

## 两种使用方式

同一个安装包提供**桌面端**与**命令行**两套入口，共用同一套图像处理算法，处理结果完全一致。按场景二选一：

|          | 桌面端（GUI）                                | 命令行（CLI）                                 |
| -------- | -------------------------------------------- | --------------------------------------------- |
| 启动     | 开始菜单「古籍重製」，或 `python desktop.py` | 终端 `guji <命令>`，或 `python cli.py <命令>` |
| 适合     | 手工逐本处理，需要看预览、手绘修正           | 批量处理、脚本集成、无界面环境                |
| 参数方式 | 表单填写，上次执行的参数自动回填             | 命令行参数，或 `guji.yaml` 配置文件           |
| 中间结果 | 每一步都有预览图可回看                       | 直接落盘到输出目录                            |

- **处理一两本书、想边看效果边调参数** → 看下面的「使用方式一：桌面端（GUI）」。
- **批量跑几十本、或要集成进脚本 / 定时任务** → 看「使用方式二：命令行（CLI）」。

桌面端**操作步骤**（配截图）见[用户操作手册](docs/guide/user-guide.md)；
开发者向的桌面端深入文档见 [`docs/dev/gui/`](docs/dev/gui/readme.md)；
命令行完整参数见 [`docs/guide/cli.md`](docs/guide/cli.md)。

## 功能一览

| 命令         | 别名  | 功能                                                        |
| ------------ | ----- | ----------------------------------------------------------- |
| `extract`    | `-e`  | 从 PDF 批量提取页面为图片                                   |
| `detect`     | —     | 检测左右文本框并输出标注图（**非必要**，命令行须 `--save`） |
| `crop`       | —     | 基于 YOLO 检测裁剪左右文本框                                |
| `rembg`      | `-r`  | 整图去底色 / 二值化 / 印章保留                              |
| `cropremove` | `-cr` | 复合流程：裁剪 + 区域去底色（一步完成）                     |
| `print`      | —     | 将图片目录生成为 PDF                                        |

```
extract   ── PDF → 图片（前置步骤）
   │
   ▼
detect    ── 检测左右文本框坐标（唯一实现；命令行须 --save 落地标注图）
   │            ↑ 由 crop / cropremove 内部自动调用，不必单独执行
   ├──────────► crop        ── 仅裁剪文本框（保留原图质量）
   │
   └──────────► cropremove  ── 裁剪 + 去底色（一步完成）
                                （支持 area/border 精细控制）

rembg     ── 整图去底色（无检测文本框）
   │
   ▼
print     ── 图片目录 → PDF（支持 A3/A4/A5/B5、标题和页码）
```

`detect` 是**非必要**步骤：`crop` / `cropremove` 内部已自动调用同一套检测算法，
日常流程不必单独执行它。它用于**单独查看检测结果**——把左右框画到原图上落地
（视觉与桌面端第 2 步一致），因此命令行下**必须给 `--save`**；不带会被直接
拒绝并提示替代方案（命令行里检测不落盘没有任何产出去处）。作为**代码调用**
（`functions.detect.detect_page_boxes`）时不受此限制，可以只取坐标不落盘。

## 安装（从源码）

> 只是想在 Windows 上使用程序 —— 直接下载上面的安装包即可，**不需要装 Python**。
> 本节以下是**开发与打包**相关的步骤。

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

| 依赖                   | 用途          | 命令                                  |
| ---------------------- | ------------- | ------------------------------------- |
| PyMuPDF                | PDF 渲染      | extract                               |
| PyYAML                 | YAML 配置读取 | run                                   |
| Pillow                 | 图像读写      | 所有图像命令（含 detect --save 标注） |
| opencv-python-headless | 图像处理      | detect / rembg / crop / cropremove    |
| numpy                  | 数组运算      | detect / rembg / crop / cropremove    |
| ultralytics            | YOLO 模型推理 | detect / crop / cropremove            |
| fpdf2                  | PDF 生成      | run                                   |

YOLO 模型权重文件需放置于 `static/weights/bookcontent.pt`。

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
安装包。**构建只产出 `dist/` 下的两样东西——一份可执行目录 + 一个安装包**：
它不会（也不该）把程序复制到 `C:\Software` 之类的地方去"部署"，装到哪、PATH
指向哪，由安装包决定（见下文「安装后」）。构建前应确认 `ISCC.exe` 已安装且
位于 Inno Setup 默认安装目录或 `PATH` 中（没装也不会让构建失败，只会跳过
安装包，`dist/guji/` 照样可用）。不要只删除 `dist` 后重复打包；如果当前
Python 环境使用 CUDA 版 PyTorch，PyInstaller 仍会把 CUDA 运行库收集进包中。

> **一次完整构建约 11~15 分钟**，属正常现象：PyInstaller 约 9~10 分钟（两次
> Analysis + COLLECT 落地 650MB），体积瘦身 1~8 分钟（视磁盘而定），Inno Setup
> 压缩约 110 秒。（还带着「复制到 `C:\Software\guji`」那个旧步骤时实测
> 18m32s，其中约 3.5 分钟花在那一步。）每个阶段结束会打印 `⏱️ … 耗时 …`，
> **长时间无输出不等于卡死**。若把输出接给 `tail`/`grep` 之类的过滤器，中间
> 过程会被缓冲到进程结束才显示，看起来像假死。

### Linux / Ubuntu 打包

> ⚠️ **PyInstaller 不能交叉编译**：Windows 上只能产出 `.exe`，Linux 上只能产出
> ELF。想要 Ubuntu 的包，就**必须在 Linux 本机**（物理机 / WSL2 / CI runner）
> 执行同样的命令，Windows 侧无论怎么配置都变不出来。

```bash
# 1) 系统依赖（Ubuntu 22.04 / 24.04）
sudo apt-get update
sudo apt-get install -y python3.10 python3-pip python3-venv \
    libgl1 libglib2.0-0 libfontconfig1 fontconfig \
    libxcb-cursor0 libxkbcommon-x11-0 libegl1 libdbus-1-3 xdg-utils

# 2) Python 依赖（与普通安装完全同一份 requirements.txt）
python3 -m pip install -r requirements.txt

# 3) 构建
python3 build.py
```

产物在 `dist/guji/`（**无 `.exe` 后缀**）：

```
dist/guji/guji        命令行
dist/guji/guji-desktop    桌面 GUI
dist/guji_<版本>_<时间戳>_linux-x86_64.tar.gz
```

Linux 没有安装包（Inno Setup 是 Windows 专属），改为 `tar.gz` 分发；需要
AppImage 或 `.desktop` 再另行打包。

版本下限与 PyQt/PySide 版本绑定：

| 目标系统          | 要求                                                                                                                   |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **Ubuntu 22.04+** | 直接可跑（现役 PySide6 6.11 的 wheel 是 manylinux_2_34）                                                               |
| Ubuntu 20.04      | glibc 2.31 不够，需把 PySide6 降到 `6.8.x`（manylinux_2_28）                                                           |
| Windows 10 / 11   | Qt 官方支持 **Win10 1809（17763）+**；`requirements.txt` 已把 PySide6 锁在 `<6.13`（6.12 是最后一个支持 Win10 的版本） |

**中文字体**：Ubuntu 最小安装通常一个中文字体都没有，缺字体时 PDF 的标题会
静默变成方块。GUI 启动时会体检——没有就直接问要不要从软件源装（首选仿宋
`fonts-cwtex-fs`，装不了才提示手动装）。要提前装好也可以：

```bash
sudo apt-get install -y fonts-cwtex-fs fonts-noto-cjk   # 或 fonts-arphic-uming
fc-cache -f
```

详见 [`docs/dev/utils.md`](docs/dev/utils.md) 的「中文字体层」一节。

> `build.py` 在构建开头会**直接删除**旧的 `dist/`、`build/`（含瘦身清出的文件），
> 不再往仓库外归档——归档实测攒到 **8 GB** 也没腾出空间，而构建产物本身是可
> 再生的。删除失败只在日志里警告，不会让整轮构建失败。

### CLI 与 GUI 一体打包

程序名为**古籍重製**。`python build.py` 一次构建产出**两个可执行文件**，
放进同一个目录并共享同一份 `_internal`：

| 入口         | 产物                         | 类型     | 说明                                      |
| ------------ | ---------------------------- | -------- | ----------------------------------------- |
| `cli.py`     | `dist/guji/guji.exe`         | console  | 命令行工具，安装后 PATH 中可直接用 `guji` |
| `desktop.py` | `dist/guji/guji-desktop.exe` | windowed | 桌面 GUI，无控制台窗口，安装包建快捷方式  |

两者由 `guji.spec` 的两次 `Analysis` + 一次 `COLLECT` 合并产出。这样 torch/cv2/Qt
等数百 MB 的二进制只在 `_internal` 里落地一份；若分两次独立打包再塞进同一个
安装包，torch 会出现两份（约 +600MB）。

**不重复打包组件**：每个入口只收集自己真正用到的东西。

- 两边共用：`functions` / `utils` / `weights` / `static` / `docs/functions`（GUI 的
  worker 子进程要跑同样的 CLI 功能；`guji help` 读的是 `docs/functions/`）；
- **只进 GUI**：`desktop` 子模块与 `desktop/static`——CLI 完全不碰 desktop，
  若一起收集会把 66 个 desktop 模块 + 103 个 Qt 模块白白塞进 CLI 的字节码包；
- PYZ（纯 Python 字节码）是每个 EXE 各自内嵌的，torch 等的 `.py` 无法跨 EXE
  共享，这属于双 EXE 结构的固有开销。

### 用户手册：构建期预生成一个自包含 HTML

手册有两条路，判据是**打包与否**（不是"文件在不在"）：

| 模式                        | 手册从哪来                                          | 截图              |
| --------------------------- | --------------------------------------------------- | ----------------- |
| 开发（`python desktop.py`） | 点按钮时现渲染 `docs/guide/*.md` 到 `%TEMP%`        | 绝对 `file://`    |
| 打包（安装版）              | 构建期已生成 `desktop/static/manual.html`，点开即用 | **内联 data URI** |

构建时 `build.py` 会额外跑一步「预生成手册」：把 `user-guide.md` / `cli.md` 连同
12 张截图**压进一个约 8MB 的自包含 HTML**。所以——

- `docs/guide/` 整目录**不进安装包**（md 与 6MB 截图对最终用户没用）；
- `markdown` 库也被 `guji.spec` 的 `excludes` 排掉：只有构建环境需要它；
- 改了手册必须**重新打包**才会生效（开发模式则改完即见）。

自包含是硬要求：装到用户机器上既没有 md 也没有 `screenshots/`，任何外部引用
都会变成碎图。`tools/smoke_frozen.py` 会核对「12 张内联图 + 无外部引用 +
包内没有 `docs/guide` 与 `markdown`」。

调手册的文案/版式时**不必跑完整打包**（十几分钟），用这条只重生成手册并
重压安装包（约 2.5 分钟）：

```bash
python build.py --manual-only     # 改了 .py 仍然必须完整打包
```

依赖只有 `requirements.txt` **一份**（CLI + GUI 全量）：CLI 与 GUI 打进同一个
目录、共享同一份 `_internal`，构建环境本来就必须同时具备两边的依赖，拆两份
文件只会造成「两处事实来源」。

`yolobuild` 里装的是这份全量表（PySide6 / PySide6-Fluent-Widgets / markdown
都在里面）。**只跑一次 `pip install -r requirements.txt`**——不要再加一份
「GUI 增量」手写清单：那份清单曾漏掉 `markdown`，导致源码模式下手册是结构化
HTML、安装版里退化成 `<pre>` 包裹的原始 markdown，而 `collect_submodules()`
对缺失的包静默返回空，PyInstaller 全程不报错，只有点了「用户手册」才暴露。

> ⚠️ `build.py` 的 `install_build_dependencies()` 开头有个**环境自检探针**
> （import 一串包），通过就直接 return、后面的 pip install 一次都不跑。
> 所以**往 requirements.txt 加包时必须同步加进探针**，否则已有的
> `yolobuild` 环境永远装不上它。

安装后：

- **安装目录**：`{localappdata}\Programs\guji`，即
  `C:\Users\<你>\AppData\Local\Programs\guji`。纯用户级安装（`PrivilegesRequired=lowest`，
  不弹 UAC），也不往系统盘根的公共 `C:\Software` 里塞东西；向导里可以改目录。
- **CLI**：**实际安装目录**（`{app}`）会加入当前用户 PATH，重开终端即可
  `guji --help`。目录改了 PATH 条目跟着改，安装脚本里不写死任何绝对路径；
  安装/卸载时会顺带把历史遗留的旧目录条目（`{sd}\Software\guji`、
  `{localappdata}\Software\guji`）从 PATH 里清掉，不留死路径。
- **GUI**：开始菜单「古籍重製」（安装时可选桌面快捷方式）；
- GUI 的重处理子进程在打包环境下以 `guji-desktop.exe --worker --config …` 启动
  自身（`desktop.py` 负责路由），因此不需要额外的可执行文件。

打包后 `desktop` 包位于 PYZ 字节存档内，磁盘上没有 `desktop/static/icon.png`；
窗口图标改由 `desktop/utils/files.py` 的 `package_dir()` 指向
`_internal/desktop/static`（spec 的 `datas` 已收集该目录）。

### 体积瘦身

`python build.py` 在 PyInstaller 结束后会执行 `prune_bloat()`，并跑
`python tools/check_bloat.py` 复核。清理的是确定用不到的部分：

| 内容                                  | 约省   | 说明                                                                                                                 |
| ------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------------------- |
| `torch` 源码副本                      | 48 MB  | `hook-torch.py` 把整个 torch 源码树当 data 收进 `_internal`，而运行时由 FrozenImporter 从 PYZ 加载——磁盘这份是纯重复 |
| `cv2/opencv_videoio_ffmpeg500_64.dll` | 29 MB  | 视频编解码，项目只用 `imread`/`imwrite` 等图像 API                                                                   |
| `PySide6/opengl32sw.dll`              | 20 MB  | Qt 软件 OpenGL 回退，界面不依赖 OpenGL                                                                               |
| `torch/bin/protoc.exe`                | 3 MB   | 构建期工具，运行期不执行                                                                                             |
| `sqlite3.dll` / `_sqlite3.pyd`        | 1.6 MB | 旧数据迁移已移除                                                                                                     |

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

安装版直接点开始菜单「古籍重製」。从源码启动时：

```bash
# 安装依赖（安装版不需要；依赖就一份 requirements.txt，含 GUI 部分）
python -m pip install -r requirements.txt

# 启动
python desktop.py

# 开发热重载（可选）
hupper -m desktop
```

主窗口标题为**古籍重製**。所有任务数据、阶段日志、预览图和缩略图统一保存在
`~/Documents/guji`（纯 JSON 文件，无数据库），卸载后不会被安装包清理。

### 两种页面形态

主窗口左侧导航里并存两种形态（共用同一批界面组件与参数面板）：

| | 任务流程（taskdetail） | 独立任务页（singletask） |
| --- | --- | --- |
| 怎么用 | 导入 PDF 建任务（`0001`、`0002`…），沿固定四步推进 | 不建任务，选个文件/目录就能跑 |
| 步骤 | 提取图片 → 检测文本框 → 图片去底色 →（可选拼版）→ PDF排版 | 五个独立页：PDF图片提取 / 检测文本框 / 图片去底色 / PDF排版 / 图片拼板 |
| 数据 | `~/Documents/guji/tasks/<任务号>/`，删任务即删目录 | 产物落在源文件旁；缓存独立在 `~/Documents/guji/singletask/` |

**两者数据互不相通**：独立任务页是任务流程里的一步拆出来的独立功能，
只有界面组件、参数面板是共用的（这也是未来 BPM 自定义流程的组件基础）。

每个阶段都有实时日志、历史参数回填、预览；所有重处理都在独立 Worker 子进程
里跑，主界面始终可响应。

### 操作手册

**完整的逐步操作说明（含截图）在[用户操作手册](docs/guide/user-guide.md)**，
包括：导入与任务管理、四步流程每步的参数与门禁、图片拼版、独立任务页用法、
图片预览与编辑（双击/右键）、日志与常见问题排查。本 README 不再重复。

界面截图见 [`docs/guide/screenshots/`](docs/guide/screenshots/)。

### 桌面端开发相关

测试**按改动范围分档跑，不必每次全量**——只跑与本次改动相关的功能模块即可，
只有动了共享底层（`core/`、`utils` 几何单位、配置默认值、`store/`、打包入口）
或发布打包前才跑全量。⚠️ 测试比较耗时，按改动攒批最后统一跑，不要每改一小处
就跑一轮。

```bash
# ① 日常：只跑相关模块（自动带上其依赖）
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only detect_shared

# 列出全部模块与依赖 / 跳过无关的大批模块
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --list
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --skip extract,resume

# ② 动了共享底层 / 发布前：全量
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py

# 离屏渲染界面截图（视觉自查）
QT_QPA_PLATFORM=offscreen python tests/gui_shot.py D:/tmp/shots
```

改动源码后同步 API 参考（`docs/api/` 为自动生成，不要手工编辑）：

```bash
python tools/gen_api_docs.py          # 重新生成
python tools/gen_api_docs.py --check  # 校验是否与源码一致（退出码非 0 表示过期）
```

---

## 使用方式二：命令行（CLI）

命令行的**完整说明**（全部参数表、`guji.yaml` 配置文件、`--config` 优先级规则、
退出码、调用链架构）见 [CLI 使用说明](docs/guide/cli.md)；每个命令的算法与参数
**权威手册**在 [`docs/functions/`](docs/functions/overview.md)——
`guji help <命令>` 在终端里读的就是它们，两者内容保持一致。

快速上手：

```bash
guji init                          # 首次推荐：生成 guji.yaml 配置文件

# 按配置文件执行各流程
guji run extract                   # 1. 从 PDF 提取图片
guji run crop                      # 2. 裁剪文本框
guji run rembg                     # 3. 去底色
guji run cropremove                # 裁剪+去底色一步完成
guji run print                     # 4. 生成 PDF（只能这样执行）

# 不用配置文件，直接给参数（python cli.py 与 guji 等价）
python cli.py extract -i book.pdf -o ./images --zoom 2
python cli.py cropremove -i ./images -o ./output --area 3 --border 30
python cli.py rembg -i ./images -o ./output --type 2
```

要点：

- `detect` 是**非必要**步骤：`crop` / `cropremove` 内部已自动调用同一套检测算法；
  单独执行用于查看检测结果，命令行下**必须给 `--save`**（否则没有任何产出，会被
  直接拒绝）。
- 通用参数 `-i/--input`、`-o/--output`、`--clean`、`--workers` 对所有命令生效；
  输出目录未传时按规则自动生成（规则见
  [输入/输出路径规则](docs/dev/io_path_rules.md)）。
- `--area`（1=逐框分图 / 2=逐框写回 / 3=合并整体）与 `--border`（mm，CSS 风格
  1~4 值写法）的完整说明见 [cropremove 手册](docs/functions/cropremove.md)。
- 帮助：`guji help`（概览）、`guji help <命令>`（单命令手册）、`guji -v`（版本）。

---

## 文档

文档按**读者**分家（这也是本 README 的定位）：

- **用户操作文档**：[`docs/guide/`](docs/guide/) —— 照着点/照着敲；
- **开发人员文档**：本 README、[`docs/dev/`](docs/README.md)、[`docs/api/`](docs/api/README.md)；
- **AI 助手**：从仓库根 [`AGENTS.md`](AGENTS.md) 入手（分层规则、事实来源、
  契约、测试命令一页读完）。

### 使用指南（给使用者）

- [用户操作手册](docs/guide/user-guide.md) — 桌面端从导入 PDF 到出 PDF 的完整
  步骤 + 独立任务页用法（配操作截图）
- [CLI 使用说明](docs/guide/cli.md) — 命令、参数、示例、退出码、架构

### 架构与开发（给开发者）

- [全仓架构](docs/dev/architecture.md) — 入口/分层/两种页面形态/公共组件契约/
  数据与缓存布局/BPM 演进方向（**新人先读这篇**）
- [桌面端文档索引](docs/dev/gui/readme.md) — 术语、速览、快速开始
- [桌面端架构](docs/dev/gui/gui-architecture.md) — 模块结构、进程模型、文件存储与任务目录布局
- [模块化重构](docs/dev/refactor-modularity.md) — 模块化设计、已落地项与后续解耦路线图
- [界面系统](docs/dev/gui/gui-ui-system.md) — 设计令牌、基础控件、自绘约束
- [技术规范](docs/dev/gui/gui-technical-spec.md) — Worker 消息协议、JSON 格式、area/border 几何
- [交互设计](docs/dev/gui/gui-design.md) — 导入流程、步骤条、历史配置、检测框编辑
- [布局](docs/dev/gui/gui-layout.md) — 窗口布局与组件尺寸约定
- [需求](docs/dev/gui/gui-requirements.md) — 功能需求与非功能需求
- [工具函数说明](docs/dev/utils.md) — Otsu、印章、border 解析、YOLO、PDF 渲染
- [输入 / 输出路径规则](docs/dev/io_path_rules.md) — 输出目录解析规则

### 命令手册（`guji help` 读取）

- [功能模块概览](docs/functions/overview.md) — 模块清单与命令关系
- [extract 手册](docs/functions/extract.md) — 页码解析、缩放计算、渲染模式
- [detect 手册](docs/functions/detect.md) — 左右检测文本框、坐标上报、`--save` 标注图
- [crop 手册](docs/functions/crop.md) — YOLO 检测、左右分割算法
- [rembg 手册](docs/functions/rembg.md) — Otsu 阈值、HSV 印章提取
- [cropremove 手册](docs/functions/cropremove.md) — area 区域模式、border 边框控制
- [print 手册](docs/functions/print.md) — 纸张、排序、标题和页码

### API 参考（自动生成，不要手编）

由 `tools/gen_api_docs.py` 从源码自动生成（`--check` 校验是否过期）：

- [API 参考索引](docs/api/README.md) — 收录范围与同步方式
- [desktop API](docs/api/desktop.md) — 桌面端全部公开类与函数
- [cli API](docs/api/cli.md) / [functions API](docs/api/functions.md) / [utils API](docs/api/utils.md)
- [入口脚本 API](docs/api/entrypoints.md) — cli.py / desktop.py / config.py
