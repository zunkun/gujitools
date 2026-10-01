# gujitools 项目长期记忆（2026-10-01 重建）

> 旧记忆因体积过大已删除。本文由 `README.md` + `docs/**` **并对照当前分支代码**重新提炼，刻意做薄。
> **原则：文档是主要事实来源，但只覆盖到 `main` 的口径；本分支新增能力以代码为准（见 §1）。**

## 0. 项目速览

- **古籍重製（gujitools）**：PDF → 提取图片 → 检测文本框 → 去底色 → 生成 PDF。
- **双入口共用同一套算法**：`cli.py`（打包后命令名 `guji`）/ `desktop.py`（PySide6 + qfluentwidgets）。
- **分层**：`utils ← core ← {cli, functions, desktop}`（严格单向）。CLI 层只解析参数，业务在 `functions/`，算法无关逻辑在 `utils/`。
- 环境：Python 3.10；打包用独立 `yolobuild`（CPU 版 torch，否则包体积几 GB）。
- 工作分支 **`stitch`**（另有 `main`、`gui`）；HEAD `49d1e48`。

## 1. 分支与文档口径（⚠️ 先读这条）

- `stitch` = `main` + **2 个提交**（`b256541` 图片拼版节点 / 任务步骤记忆 / 白底透明 PNG；`49d1e48` 图片编辑器 / 自动拼版 / 拼版面板与流程条样式定稿），外加**37 个未提交改动**（约 +4438 行，拼版、图片编辑器、预览查看器、`print_plan`、`manifest` 等 WIP）。
- **`docs/**` 大体正确，但基准是 `main`**：这两个提交顺带改了 9 份文档（+387 行），所以「图片拼版、白底透明 PNG、bookcontent 双类模型、右键预览/编辑的用户说明」文档里**已有**；而**最新一批 WIP（图片编辑器、颜色选择器、字体目录）dev 文档还没写**——这部分**以代码为准**。

### 1.1 stitch 独有 / 文档未覆盖的能力

| 能力 | 代码位置 | 要点 |
| --- | --- | --- |
| **图片编辑器**（Win10 照片风格：裁剪 / 统一变换 / 擦除 / 插入文字） | `desktop/components/viewers/image_editor.py` | 从预览弹窗的「编辑」进入；`save_back=True`（画布 1:1 对应真实文件）时「完成」= **原子覆盖原文件**，虚拟预览则只能「下载」 |
| **文字颜色选择器** | `desktop/ui/color_picker.py` | 面板内**全部 `NoFocus`**——选项行抢焦点会让"字号/颜色不生效"（真实 root cause）；不用 qfluentwidgets 的 `ColorPickerButton`（色块在外面 + 无中文 .qm） |
| **文字工具字体清单** | `desktop/ui/fonts.py::text_font_families()` + `desktop/services/font_catalog.py` | 静态候选毫秒级；系统字体扫描约 7 秒，只在**后台线程扫一次**并落盘缓存，**绝不挡住出 PDF** |
| **各步骤右键「预览图片 / 编辑图片」** | `ZoomTarget.edit_path`（`image_zoom_dialog`）、`pages/taskdetail/manifest.py`、`pages/taskdetail/view.py` | `save_path` = 画布 1:1 就是该文件；`edit_path` = 编辑要回写的真实文件，两者可不同；**实时暂存图不给编辑**（改了也不生效） |
| **第二步检测结果统计**（总览 / 明细） | `desktop/components/detect_stats.py`；分类规则在 `utils/box_geometry.classify_page_slots` | 只做展示，分类逻辑单一实现 |
| **任务步骤记忆（两层 `ui.json`）** | `desktop/store/ui_state.py` | 任务级记 `last_stage`（**记 key 不记下标**）；全局记 `last_task` + `source_hash` |
| 单实例、分页、图标等 | `desktop/single_instance.py`、`components/pagination.py`、`desktop/ui/icons.py` | 文档未展开 |

### 1.2 已定契约：第四步取图 = 第三步「提交本次任务」的成品图

**用户口径（2026-10-01）：「去底色那一步，必须提交才能传给下一步」。**（旧问题"第四步编辑图片进不了 PDF"由此定案）

- `submit.SubmitMixin._build_print_effects` 只做**整图透传**（`effect=None`，文件=list 条目=
  `stages/rembg`；拼版生效时 `stages/imposition`），**不再**拿去底图 `stages/rembgpreview`
  + 当前 area/border 现算。后果：
  - 编辑去底色结果、改 area/border → **必须重新提交**才进 PDF（提交按钮会亮"待提交"，
    `submit._preview_edited_after_submit()` 用 `rembgpreview` 文件 mtime 判"编辑过"）；
  - 第四步右键编辑「待打印图」→「生成 PDF」即生效；
  - 旧的"改 border 免重提交"**已取消**；`plan_print_effects` / `_base_label` 已删除。
- 护栏：`tests/selftests/print_area_border_e2e.py`、`print_list_layout` §2、`rembg`、`print`、
  `imposition`；探针 `tests/probe_preview_submit_gate.py`、`probe_edit_chain_e2e.py`。
- 自测：`extract` 现在能跑通（此前的"环境失败"未再复现），`--only` 会自动带上依赖链。

## 2. 文档地图（找答案先看这里）

| 想知道什么 | 看哪 |
| --- | --- |
| 用法 / 参数 / 示例 | `README.md`、`docs/guide/user-guide.md`、`docs/guide/cli.md` |
| GUI 架构、进程模型、目录布局 | `docs/dev/gui/gui-architecture.md` |
| Worker 协议、JSON 格式、area 几何 | `docs/dev/gui/gui-technical-spec.md` |
| **改界面前必读**（令牌 / 自绘约束） | `docs/dev/gui/gui-ui-system.md` |
| 交互设计 | `docs/dev/gui/gui-design.md`；布局 `gui-layout.md`；需求 `gui-requirements.md` |
| 输入输出路径规则 | `docs/dev/io_path_rules.md` |
| 算法（Otsu / 印章 / YOLO / PDF 渲染） | `docs/dev/utils.md` |
| 命令手册（`guji help` 运行时读） | `docs/functions/*.md` ⚠️ **位置固定，不可移动** |
| 函数签名 | `docs/api/*.md`（自动生成，**禁手改**） |
| 模块化重构史与守卫 | `docs/dev/refactor-modularity.md` |

## 3. 硬规则（改动前必守）

- **绝对导入**：全项目不用 `from .x`。取项目根用 `desktop.utils.files.project_root()`，**不用** `Path(__file__).parents[N]`。
- **单一事实来源**（别另写一份，漂移必出 bug）：
  - CLI 参数表 → `core/command_spec.py`（新增命令只改这一处，其余清单漏改由守卫测出）
  - 桌面表单默认值 → `desktop/components/panels/params_spec.py`（**不许**再写 `p.get("键", 字面量)`）
  - 色值 / 间距 / 圆角 / 字号 → `desktop/ui/theme.py`；状态→颜色文案 → `theme.status_colors/label`
  - area/border 几何 → `utils/box_geometry.py`（GUI 与 CLI 共用）；检测框绘制 → `utils/box_draw.py`
  - 打印排版 → `utils/page_layout.py`；页序 → `utils/sort_utils.pdf_custom_sort_key`
  - JSON 读写 → `desktop/store/json_io.py`（临时文件 + `os.replace` 原子落盘）
- **检测只有一份实现**：必须走 `functions.detect.detect_page_content`，**不得**直接调 `utils.yolo_utils.detect_content_boxes`（`detect_shared` 守卫会红）。
- **中文路径**：不许直接 `cv2.imread / imwrite`，改用 `utils.image_io`。
- **界面**：基础控件一律 `paintEvent` 自绘、不引样式表；下拉框用 `widgets.combo_box()`，单独按钮设 `CONTROL_HEIGHT`（否则比同列输入框矮 6px）。
- **跨线程**：闭包连信号一律用 `desktop.workers.connect_queued(owner, signal, slot, thread)`；`signal.connect(lambda)` 是直接连接，会在子线程碰 widget。
- ⚠️ **禁止 AI 自动 git 提交**：改完只汇报 `git status`/diff，等用户明确说「提交」才动手。

## 4. GUI 进程模型与存储

- 主进程（PySide6）**不加载** cv2 / torch / PyMuPDF；每阶段一个 worker 子进程，stdout 走 **JSON Lines**（`started/progress/log/page_boxes/page_size/finished/error/cancelled`）。
- 进度/坐标由 `core.reporter.Reporter` **结构化上报**：CLI 不注入 → 空实现、输出逐字不变；desktop 注入 `JsonLinesReporter`。**已不再正则解析中文提示**。
- 数据根 `~/Documents/guji`，**纯 JSON、无数据库、无迁移**：
  `tasks.json`、`ui.json`（last_task + source_hash，重启恢复）、`tasks/<0001>/`（`pages/runs/boxes/sizes/print/drafts/*.json`、`runs/`、`thumbnails/`、`stages/{extract,rembg,imposition,print}`）。

## 5. 构建与打包

- `python build.py`：准备 `yolobuild` → PyInstaller（`guji.spec` **两次 Analysis + 一次 COLLECT**，产出 `guji.exe` + `guji-desktop.exe` 共享 `_internal`）→ `prune_bloat()` → Inno Setup 安装包。
- **一次完整构建 11~15 分钟，长时间无输出 ≠ 卡死**；构建开头会**直接删除**旧 `dist/`、`build/`。
- ⚠️ `install_build_dependencies()` 开头有环境自检探针（import 一串包，通过就 return）：**往 requirements.txt 加包必须同步加进探针**，否则 yolobuild 永远装不上。
- ⚠️ 不要再往 `excludes` 加 `torch.*`（会让 `guji crop` ModuleNotFoundError）；新增排除项先跑 `python tools/probe_excludes.py <模块名>`。
- 删 torch 源码副本时必须保留 `build.py::_keep_torch_source()` 列出的文件，否则 `import torch` 报 `OSError: could not get source code`。
- 用户手册：打包版打开**构建期预生成的** `desktop/static/manual.html`（自包含，12 张截图内联 data URI），`docs/guide/` 整目录**不进安装包**；判据是 `sys.frozen`，不是"静态文件在不在"。只改手册文案不用完整打包：`python build.py --manual-only`（约 2.5 分钟）。
- 打包后自检：`python tools/check_bloat.py`、`python tools/smoke_frozen.py`。

## 6. 测试与文档工具

- **GUI 自测按改动分档跑**，只有动共享底层（`core/`、`utils/`、配置默认值、`store/`、打包入口）或发布前才全量：
  `QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only <模块>`（`--list` 看模块与依赖，`--skip a,b` 跳过）。
- CLI / worker 侧：`tests/reporter_cli_parity.py`、`tests/reporter_worker_e2e.py`、`tests/cli_print_smoke.py`。
  **⚠️ GUI 全绿 ≠ CLI 没坏**——动了 `functions/`、`utils/` 时这三条必跑（历史上就是这么抓到 `print` 断链的）。
- 视觉自查：`python tests/gui_shot.py D:/tmp/shots`（`--guide` 生成用户手册配图）。
- 文档同步：`python tools/gen_api_docs.py` → `--check` 校验；`python tools/check_docs.py` 查链接/锚点/表格列数。
- **本机解释器**：managed python 3.13 **没装 PySide6**；能跑 GUI 自测的是 `C:\Users\liuzu\anaconda3\python.exe`（或 `envs\py310`，PySide6 6.11 + qfluentwidgets 1.11）。
  跑法：`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE <python> tests/gui_selftest.py --only <模块>`

## 7. 高频踩坑（都付过学费）

- `--clean`：CLI 默认 False，但 `FunctionBase.execute()` 内部兜底为 **True**——**自建参数字典必须显式给 `clean`**，否则意外清空输出目录。
- `rembg` 输出固定 **PNG**（没有 `--ext`），`--type 2` 的 1bit 只有 PNG 无损。
- 第三步「提交产物」一律是**白底透明 PNG**，透明必须**在合成之后**加（`utils.save_white_as_transparent`；在去底计算处加会被不透明白底重新压平）。
- `print` 只能 `guji run print`；页序以 `files` 清单（= 桌面第四步列表顺序）为准，为空才回退文件名排序。
- 整幅页（`fullcontent`）：框原样下传，area=1/2/3 结果一致（合并语义、不拆 `-l/-r`），**只有 area=4 保留框外内容**。
- 高分屏：**绝不要**手动 `painter.scale(dpr, dpr)`（会放大两次：底图对、框错位）；叠加层线宽取整到设备像素；dpr 相关改动必须用真 dpr 进程验（`QT_SCALE_FACTOR=1.5`），离屏 dpr=1 全绿也不算过。
- 手册页：只把**原生路径**交给 `os.startfile`，**别传 `file:///` URI**（Windows 上会挂死）；手册 HTML **绝不要加 `<base>`**（片段链接按 base 解析，点锚点会导航走）。
- 删除任务竞态：任务目录已删时，JSON 写入直接跳过，不报错。
- 旧记忆留下 3 处死引用（指向已删的 `.workbuddy/memory/*.md`，纯文本不是链接，`check_docs.py` 抓不到）：`utils/pdf_extract.py:564` docstring、其自动生成副本 `docs/api/utils.md:1623`、`docs/dev/gui/readme.md:50`。
