# 构建与打包（开发者）

> 本文档由原 README 的开发/打包章节迁移而来。只想使用程序请看
> [用户操作手册](../guide/user-guide.md)；Windows 用户直接下载
> [Release 安装包](https://github.com/zunkun/gujitools/releases/latest)即可，不需要装 Python。

## 开发环境

```bash
python -m pip install -r requirements.txt   # 依赖就一份，含 CLI + GUI 全量

# 启动桌面端
python desktop.py
# 开发热重载（可选）
hupper -m desktop

# 命令行（与安装后的 guji 等价）
python cli.py --help
```

- 国内网络环境可以为普通 PyPI 依赖选择镜像源。清华源示例：

  ```bash
  python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
  ```

- 阿里云源示例：

  ```bash
  python -m pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt
  ```

- Python 版本要求 3.10。
- YOLO 模型权重文件需放置于 `static/weights/bookcontent.pt`。

主要依赖（详见仓库根 [requirements.txt](../../requirements.txt)）：

| 依赖                   | 用途          | 命令                                  |
| ---------------------- | ------------- | ------------------------------------- |
| PyMuPDF                | PDF 渲染      | extract                               |
| PyYAML                 | YAML 配置读取 | run                                   |
| Pillow                 | 图像读写      | 所有图像命令（含 detect --save 标注） |
| opencv-python-headless | 图像处理      | detect / rembg / crop / cropremove    |
| numpy                  | 数组运算      | detect / rembg / crop / cropremove    |
| ultralytics            | YOLO 模型推理 | detect / crop / cropremove            |
| fpdf2                  | PDF 生成      | run                                   |

项目不使用 OpenCV 的窗口、摄像头或 GUI 接口，因此依赖已使用
`opencv-python-headless` 替代 `opencv-python`。它仍然提供 `import cv2` 和图像
处理功能，但不会携带 GUI 相关库；如果以后增加 `imshow` 等窗口功能，再改回
`opencv-python`。注意：`ultralytics` 的依赖声明可能再次安装完整的
`opencv-python`，自动构建会在依赖安装后卸载它并重新固定为 headless 版本。

改完代码的自测命令、文档同步见仓库根 [AGENTS.md](../../AGENTS.md)。

## 创建 CPU 打包环境

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

## Linux / Ubuntu 打包

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

详见 [utils.md](utils.md) 的「中文字体层」一节。

> `build.py` 在构建开头会**直接删除**旧的 `dist/`、`build/`（含瘦身清出的文件），
> 不再往仓库外归档——归档实测攒到 **8 GB** 也没腾出空间，而构建产物本身是可
> 再生的。删除失败只在日志里警告，不会让整轮构建失败。

## CLI 与 GUI 一体打包

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
12 张截图**压进一个约 8MB 的自包含 HTML**（用户手册改版后为 13 张）。所以——

- `docs/guide/` 整目录**不进安装包**（md 与 6MB 截图对最终用户没用）；
- `markdown` 库也被 `guji.spec` 的 `excludes` 排掉：只有构建环境需要它；
- 改了手册必须**重新打包**才会生效（开发模式则改完即见）。

自包含是硬要求：装到用户机器上既没有 md 也没有 `screenshots/`，任何外部引用
都会变成碎图。`tools/smoke_frozen.py` 会核对「内联截图张数（13）+ 无外部引用 +
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

### 安装后（Windows 安装包的行为）

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

## 体积瘦身

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
