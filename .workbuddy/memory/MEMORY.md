# 项目长期记忆（gujitools）

## 环境与命令
- 完整依赖（PySide6 + cv2 + torch）在 conda `py310`；anaconda base 也可；`yolobuild` 无 PySide6。
- **打包用 conda `yolobuild`**（CPU torch，产物小）：`PYTHONPATH= GUJI_BUILD_ENV_READY=1 C:/Users/liuzu/anaconda3/envs/yolobuild/python.exe -u build.py`（约 22 分钟）。产出 `dist/guji/guji.exe` + `guji-gui.exe` + `dist/guji_setup_<版本>_<时间戳>.exe`。**`PYTHONPATH=` 必须加**，否则 WorkBuddy 的 sitecustomize shim 会让 pip 静默装一半（见下方打包坑）。
- GUI 自测（已拆成功能模块）：`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE C:/Users/liuzu/anaconda3/envs/py310/python.exe -u tests/gui_selftest.py`（**135 项断言，全量约 37s**）。`--list` / `--only a,b`（自动补依赖）/ `--skip a,b` / `--module-timeout N`。判据以「全部 N 项断言通过 ✅」为准；增删用例 = 增删 `tests/selftests/*.py`（`_` 开头跳过），约定 `NAME/DEPENDS/TITLE/run(ctx)` + 可选 `TEARDOWN`（清场模块恒排最后）。
- **文档工具**：`python tools/gen_api_docs.py`（`--check` 比对）、`python tools/check_docs.py`（链接/锚点/表格）。改完源码/docstring 重跑。
- **改界面的标准回归流程**：①离屏探针渲染 PNG 对比（先 `tests/gui_shot.load_fonts(app)` 注册中文字体，否则全是方框）；②实现 + 自测断言（守卫要**双向验证**：注入回归形态确认断言真会失败）；③`tests/gui_shot.py` 出图覆盖 `docs/gui/screenshots/`（**文件名是中文，用 Python 脚本复制，别在 bash 写中文路径**；Python 脚本参数用 Windows 原生路径，`/d/...` 会被当字面量）；④重跑三条文档工具。探针放 `D:\tmp`，用完删。

## 测试断言的坑（血泪教训）
- **`wait_worker()` 后别立刻读状态**：最后的 `finished` 事件（带最终 `done`）可能还在队列里，先 `processEvents()` 轮询到目标值。
- **别在 QStackedWidget 未选中页面上量几何**：qfluent `ScrollArea` 懒构建，未显示时 `layout()` 为 None、viewport/inner 全是 480×640 脏值。测布局先走 `_context.show_detail()`。
- **自测模块间无残留**：拆分后 `set_task()`/历史回填会重置控件（如 rembg `border` 清空），每个模块自己显式设好前置条件。
- **没 `setFixedHeight` 的控件未 `show()` 时 `height()` 返回 480**；断言用 `LineEdit().height()`（33）当基准。
- **像素断言踩空白页陷阱**：自测 PDF 渲染不出中文 → 两半裁切后像素相同、假失败。改用确定性契约断言（monkeypatch 抓参数/坐标）。
- **双向验证注入前，先确认真实旧实现的路径/行为**：曾把「删除 workset」的回归注入写到 `output.parent/workset`（= `stages/workset`），而真实旧位置是 `output.parents[1]/workset`（= `tasks/<id>/workset`）→ 守卫不报错，差点误判「守卫失灵」。**注入无效 ≠ 守卫有效**，先让注入确实产生副作用再断言。
- **阶段子进程用 `TaskStore()` 默认根（`~/Documents/guji`）**：GUI 测试只重定向了主进程的 store（`w.store = repo`），子进程读 `config["args"]` 里的绝对路径。凡是「子进程内计算出的路径」都不会落在临时目录——注入回归时可能污染**真实用户数据**。
- **守卫断言要拆开、别串成一条**：`a == b == 0` 里 `==0` 会掩盖「拖拽是否产生文件」的真实语义，拆成「前后相等」+「恒为 0」两条。

## 工具链坑（非测试）
- **pip 装包前先 `PYTHONPATH=`**：WorkBuddy 的 `sitecustomize.py` shim 经 PYTHONPATH 注入，pip 替换文件时会触发 bulk-delete guard → `ERROR: Exception ... SystemExit(1)`，**装一半且看起来像网络问题**。`dangerouslyDisableSandbox` 无效（是 shim 不是沙箱）。

## 打包体积（实测数据，2026-09）
- 基线 750.8MB / 3448 文件 → 移除 sqlite + 瘦身 → **647.2MB / 1107 文件**（安装包 187MB）。下限被 `torch/lib/torch_cpu.dll`（291.7MB）锁死，不换推理引擎下不去。
- **删 `_internal/torch/*.py` 会崩 `OSError: could not get source code`**：`torch/utils/_config_module.py`
  的 `install_config_module` 会 `inspect.getsource` 各 config 模块。实测保留 **13 个源文件**即可全绿
  （规则见 `build.py::_keep_torch_source()`：任意 `config.py`/`config_comms.py` + 显式清单）。
  别全删，也别逐个试——按这条规则白名单保留。
- **`torch.*` 子模块一个都排不掉**（实测 `guji crop` 崩在 ModuleNotFoundError）。它们全在 `import torch` / `import torchvision` 时被顶层引用、无 try/except：
  `torch.distributions`←`torch/__init__.py:2059`；`torch._prims`←`_meta_registrations`←`__init__:2486`；
  `torch._inductor`←`_subclasses/functional_tensor`←`_higher_order_ops`←`torch/export`；
  `torch.distributed`←`utils/data/dataloader.py:20`；`torch.onnx`←`torchvision/ops/_register_onnx_ops.py`（我们用 nms，必留）。
  → **加 excludes 前先跑 `python tools/probe_excludes.py <模块名>`**（用 meta_path 阻塞器在**独立子进程**里跑真实链路；
  同进程里第二次 `import torch` 会命中 sys.modules 缓存，导致后续测试形同虚设）。
- 可安全排除：`sqlite3`、`win32com`/`win32api`/`pythoncom`/`pywintypes`（torch/_appdirs.py 里是函数内导入）。
- **PyInstaller 6 默认 `pyz+py`**：包会同时进 PYZ 和 `_internal` 磁盘两份。hook-torch.py 还额外把整个 torch 源码树当 data 收集
  （Windows 分支 `datas=[(get_package_paths("torch")[1],"torch")]`），所以 `_internal/torch/*.py` 是纯重复（48MB），
  但它是 hook 的 datas，**excludes 管不到**，只能在构建后删（build.py `prune_bloat()`）。
- 配套工具：`tools/check_bloat.py`（构建后复核，挂进了 build.py）、`tools/smoke_frozen.py`（frozen 端到端冒烟）。
- **CLI 输出布局**：`extract -o X` 实际落到 `X/<pdf名>/images/`（按源分层）；`rembg`/`crop` **不递归子目录**，输入要指向真正有图的那一层，否则「未找到图片文件」但退出码仍为 0。

## 危险操作红线
- **别在 bash 命令里写含中文/非 ASCII 的路径**（曾致整个 `docs/` 被误回收）。操作这类文件用 Python 脚本（`pathlib` + UTF-8）。
- 误删恢复：回收站 `D:\$RECYCLE.BIN\<SID>\` 下 `$R<id>` 是内容、`$I<id>` 是元数据（含 UTF-16LE 原始路径），`ls -lat` 找到后 `cp -r`。

## 构建耗时（别误判成卡死）
- 一次完整 `python build.py` 约 **15~20 分钟**（实测 18m32s）：PyInstaller ~9-10min（两次 Analysis +
  COLLECT 落地 650MB）→ 复制到 `C:\Software\guji` ~3.5min（含旧版备份，跨盘）→ ISCC 压缩 ~110s。
- **把输出接给 `tail`/`grep` 会缓冲到进程结束才显示**，中间 18 分钟零输出 = 假死错觉，不是卡死。
  build.py 现已分段打 `⏱️ <阶段> 耗时 …`，照这个判断进度。
- 只改了安装包配置时别重跑 PyInstaller：
  `python -c "import build; build.build_installer(Path(根), Path(ico))"` 约 2 分钟。
- 查进程别用 `wmic`（被安全策略拉黑）；bash 里 `find` 是 Windows find.exe（`find . -type f` 报错且
  返回 0 行），数文件用 `ls`/`du` 或 `/usr/bin/find`。

## 打包约定（详见 README「CLI 与 GUI 一体打包」）
- 程序名 **古籍重製助手**（iss 的 AppName / 快捷方式名 / GUI 窗口标题 / README 标题统一）。
- **入口**：CLI=`main.py`→`guji.exe`(console)；GUI=`desktop.py`→`guji-gui.exe`(windowed)。
- **单 spec 双 EXE**：`guji.spec` 两次 `Analysis` + 一次 `COLLECT`，共享 `_internal`。分两次独立打包会让 torch 出现两份（+600MB）。
- **不重复打包组件**：`functions`/`utils`/`weights`/`static`/`docs` 两边共用；**`desktop` 子模块与 `desktop/static` 只进 GUI**（否则 CLI 的 PYZ 会多带 66 个 desktop + 103 个 Qt 模块）。PYZ 字节码每 EXE 一份是固有开销，省不掉。
- **判重别用 basename**（`__init__.py` 同名不同包会误报上千条），也别用 `-(\w{8,})\.(dll|pyd)$` 找冲突改名（`cd.cp310-win_amd64.pyd` 会误命中）。直接数关键大文件出现次数。
- `build.py` 是唯一构建入口（已删除 `build_gui.py` / `guji_gui.spec`）。清理列表**不能**再删 `guji.spec`——它现在是构建输入。
- **只改 iss 时不用重跑 PyInstaller**：`PYTHONPATH= python -c "import build; build.build_installer(Path(根), Path(ico))"` 约 2 分钟（全流程 23 分钟）。
- 改名/改快捷方式名后记得加 `[InstallDelete]` 删旧 .lnk，否则升级用户会留新旧两套快捷方式。
- **frozen 下 `desktop` 包在 PYZ 字节存档内，磁盘无实体**：资源一律走 `desktop/utils/files.py::package_dir()`（`sys._MEIPASS/desktop`），别用 `Path(__file__)`。`functions/` `utils/` 的 `Path(__file__).parent.parent` 本来就能解析到 `_MEIPASS`，无需改。
- 装 GUI 依赖只补 `PySide6` + `PySide6-Fluent-Widgets` 两个增量，**别整表装** `requirements.gui.txt`（会把 CPU torch 顶成 CUDA 版，产物暴增数 GB）。
- GUI 的 worker 子进程在 frozen 下是 `sys.executable --worker --config <json>`（= `guji-gui.exe`），`desktop.py` 负责路由，不需要额外 EXE。
- 安装包：`guji_setup.iss`，`{app}` 加入用户 PATH（CLI 可用）+ 开始菜单 GUI 快捷方式（桌面快捷方式默认不勾选）。

## 架构约定（desktop 包分层）
- 职责：pages 页面骨架 + Mixin / services 纯业务规则（无 Qt）/ store 数据 / workers 后台线程 / stages 子进程阶段执行器。纯业务规则放 `services/` 便于脱离 Qt 测试。
- 页面层按页面分子包（tasklist/page.py、taskdetail/{page,view,manifest,history,submit,print_list,runner,detect}.py）；新增职责优先加 Mixin。
- `desktop/worker.py` 只做初始化与路由（实现在 `stages/`）；保持 `python -m desktop.worker` 可用。子进程：`sys.executable -m desktop.worker --config <json>` + `setWorkingDirectory(project_root())`。
- **desktop 包内一律绝对导入**（`from desktop.ui import theme as T`），相对导入挪目录会静默指错；**项目根用 `desktop.utils.files.project_root()`**，别用 `Path(__file__).parents[N]`。
- **print 页序 = 数据层**：`print.json` 的 `pages` 数组顺序是唯一事实来源，执行时作为 `args["files"]` 传给 CLI（**不读目录、不解析文件名**）；**已废弃 workset**（不再把顺序烧进文件名）。新增/删除/重排只改数组，零物理文件。不传 `files` 时 CLI 回退 `pdf_custom_sort_key` 文件名排序（独立用法兼容）。`title_switch_nodes` 填**原始页码**、`skip_pages` 纯数字按**清单序号**（1 起）。

## 界面样式约定（详见 docs/gui/gui-ui-system.md）
- 视觉常量只在 `desktop/ui/theme.py`（`SCROLLBAR_*`、`DANGER_*`、`SURFACE_SUNKEN`、`BORDER_STRONG` 等），不写魔法值；状态颜色走 `theme.status_colors/label`。
- **基础视觉控件自绘 `paintEvent`，不用样式表**；全局 QSS 只选 `QMainWindow`、`QWidget#pageRoot`（+滚动条+`#taskTable`）。实例级 setStyleSheet 会顶掉库样式，按钮四态写全。
- **qfluent 控件自带控件级样式表**，优先级高于应用级 QSS；定制必须设控件自身（见 `log_panel.apply_log_view_style`）。
- **表单控件高统一 `widgets.CONTROL_HEIGHT = 33`**：下拉框用 `widgets.combo_box()` 建；qfluent `ComboBox` 继承 `QPushButton` 默认 27px，类名判断单独列出。
- 形态切换用 `widgets.SegmentedToggle`（高 30）：轨道 `SURFACE_SUNKEN` + 选中文字 `ACCENT` 加粗 + 滑块投影；`set_current()` 不发信号；别用两个 PushButton 或 qfluent `SegmentedWidget` 拼。
- 各阶段参数表单由 `StagePanel.build_form()` 统一装进透明 `ScrollArea`（可滚动不压扁）；print 面板自带滚动区、覆盖此法。
- 别硬编码表格行高：qfluent TableWidget `defaultSectionSize()` 实测 38px，按实测 API 算。
- **表格单元格容器必须 `setFixedHeight(ROW_HEIGHT)` 锁整行高**：qfluent `TableItemDelegate.updateEditorGeometry` 用「改高度前」的容器高算居中偏移、随后又把高度改成整格高，高度≠行高时位置随几何更新时序漂移（运行中胶囊/按钮偏到行底、行与行还不一致），且离屏探针因时序不同**未必能复现**——别相信"探针里是居中的"就断定没问题。tasklist.py 有直调 delegate 的守卫断言。

## 缩略图/预览数据供给链
- `_page_thumb_for(...)` spec 唯一有效键 **`effect`**（boxes/area/border/dpi）；`ImageListWorker` 互斥入参 `crops=`/`effects=`。凡「区域/边框/DPI 参与渲染」一律传 `effect`（曾误读 `crop` 致 area=1 显示整页）。
- `gui_shot.py` 演示数据：缩略图 4 位名、调 `save_pages()/save_image_size()/save_detect_boxes()`、文字铺满整页。

## 文档约定
- docstring：中文，首行一句话以「。」结尾（≤40 字）；Qt 事件覆写不必手写（生成器自动标注）。
- `docs/api/*.md` 生成物勿手改；表格单元格 `|` 转义 `\|`；路径规则单一来源 `docs/io_path_rules.md`。
- **改行为必须顺手改手册，别只改代码**：行为变更的落点有四处——模块 docstring、`docs/functions/*.md`、
  `docs/cli.md`、README。曾改了 print 页序语义（`files` 清单优先、skip_pages 按序号、title_switch_nodes
  按原始页码）却漏改手册，隔一轮才补齐，docstring 里还留着已废弃的 workset 描述。
- **写用户文档前先 grep 源码核对**：按钮文案、产物路径、默认值容易记错（如 print 产物不是固定
  `print.pdf`，而是 `书名[重制].pdf`；下载按钮叫「下载 PDF」）。写完再跑三个文档工具。
