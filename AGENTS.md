# AGENTS.md — AI 开发者快速上手

> 本文件是给 AI 助手（和新人）的**仓库级入口文档**：读完后你应该知道代码怎么分层、
> 事实来源在哪、哪些契约不能破坏、改完代码要跑什么。细节见各指向文档，**不要在本文件
> 里展开**——它必须保持一屏能读完的密度。

## 项目一句话

古籍扫描件重制工具：PDF 提图 → 检测文本框 → 裁剪/去底色 → 生成 PDF。
**双入口共用同一套算法**：`cli.py`（打包后 `guji`）与 `desktop.py`（PySide6 + qfluentwidgets 桌面端）。

## 分层与方向（有自测守卫）

```
cli.py / desktop.py（入口，只做路由）
    ↓
desktop（界面）/ cli（命令行）        ← 两个入口互不依赖，desktop 禁止 import cli
    ↓
functions（图像/PDF 功能，CLI 与 GUI 共用的唯一实现）
    ↓
core（命令定义、reporter）   →   utils（纯算法：box_geometry、image_io、page_layout…）
```

- 严格单向：`utils ← core ← {cli, functions, desktop}`；跨层白名单见
  `tests/selftests/layering.py`（函数内延迟导入放行）。
- **GUI 主进程不许进重依赖**（cv2/torch）：主进程要用的纯规则放 `utils`；
  重活全部走 worker 子进程（`functions.detect.detect_page_content` 是唯一检测入口）。
- 中文路径禁止直接 `cv2.imread/imwrite`，一律走 `utils.image_io`。

## 桌面端两种页面形态（最容易搞混的事）

| | 任务流程 taskdetail | 独立任务 singletask |
| --- | --- | --- |
| 位置 | `desktop/pages/taskdetail/`（+ `pages/tasklist/`） | `desktop/modules/<key>/` |
| 本质 | 「任务 → 四步 + 可选拼版」的**编排**，数据随任务存 | 把流程中的一步**拆出来**的独立功能页 |
| 数据 | `~/Documents/guji/tasks/<任务号>/` | 产物落在源文件旁（`<源名>_<后缀>/`） |
| 缓存 | `tasks/<id>/thumbnails/{source,print,imposition,detect}` | `~/Documents/guji/singletask/<key>/` |

**契约（破坏即 bug）**：

1. **singletask ≠ taskdetail**：两者只共用渲染组件、参数面板、worker——**数据不相通，
   缓存根各归各，禁止借道**（历史 bug：拼板左列缩略图曾误写进 singletask 缓存区）。
   taskdetail 缓存随 `delete_task` 整体删除，singletask 缓存不随之清理。
2. **公共组件只认「输入目录 + 输出目录」**：执行内核唯一输入形状是
   `StepRequest(source, dest, args)`（`desktop/steps/kernel.py`）；参数面板契约只有
   `get_args/apply_args/reset_to_default`（`desktop/components/panels/base.py`）。
   组件层不许出现 taskdetail 专属概念（如「在流程中启用拼版」开关已参数化为
   `ImpositionPanel(enable_switch=…)`）。这样未来 BPM 才能用同一批组件定义任意流程，
   singletask 也因此能天然充当 BPM 里的单步执行器。
3. taskdetail 代码 **0 处 import** `desktop.modules`；模块页不 import pages
   （导航壳层 `desktop/shell.py` 例外——它住 desktop 包根，是导航宿主）。

## 单一事实来源（改这里，别另写一份）

| 事实 | 唯一来源 |
| --- | --- |
| CLI 参数 | `core/command_spec.py` |
| 桌面参数面板默认值 | `desktop/components/panels/params_spec.py` |
| 步骤元数据（文案/过滤串/输出规则/导航/流程角色） | `desktop/steps/spec.py::SPECS`（`STAGES`/`MODULES`/`PANEL_CLASSES` 全部派生） |
| 任务流程连线（BPM 边表） | `desktop/steps/ports.py::SUPPLIERS`；落点表 `STAGE_LOCATIONS` |
| 「这一步能不能跑」的就绪判据 | `desktop/steps/ports.py::stage_blocking_inputs`（**不是** `stage_inputs` 那份静态声明） |
| 流程图模型（**唯一真源**，含任意节点类型/DI 坐标/折点/边标签） | `desktop/steps/bpmn_diagram.py::FlowDiagram`（读/写 `tasks/<id>/flow.bpmn`） |
| 流程图渲染（只读，照文件画） | `desktop/components/bpmn_view.py::BpmnView`（`paintEvent` 自绘；网关菱形、结束事件双圈） |
| 流程图编辑（拖拽/连线/增删/改名） | `desktop/components/bpmn_editor.py::BpmnEditor`（继承 `BpmnView`） |
| 运行顺序（**状态机**，替代端口级边表推顺序） | `desktop/steps/scheduler.py::Scheduler`（顺序取 `stage_order()` 拓扑序；跳过看 `CONDITIONS`） |
| 流程弹窗（查看/编辑，创建任务与详情页共用） | `desktop/components/flow_dialog.py::FlowPanel` + `pages/taskdetail/flow_mixin.py::FlowMixin` |
| 旧的运行语义模型（阶段序列 + 端口边表，仍供槽位计算） | `desktop/steps/flow.py::FlowDefinition`（页面渲染**不再**用它） |
| 创建任务**页面**（选 PDF + 任务名 + 看/编流程） | `desktop/pages/createtask/page.py::CreateTaskPage`（内含 `components/create_task_dialog.py::CreateTaskPanel`；2026-10-06 起不再是弹窗） |
| 任务流程编辑**页面**（详情页页头进入） | `desktop/pages/taskflow/page.py::TaskFlowPage`（内含 `components/flow_dialog.py::FlowPanel`，`close_window=False`） |
| 详情页查看/编辑流程 | `desktop/components/flow_dialog.py::FlowPanel` + `pages/taskdetail/flow_mixin.py::FlowMixin` |
| 弹窗外壳（标题+内容+按钮） | `desktop/components/dialog_shell.py::shell_dialog`（⚠️ **不要**用 qfluentwidgets 的 `Dialog`，它只支持"字符串+两按钮"、没有 `viewLayout`） |
| 默认流程模板文件 | `desktop/static/task_default.bpmn`（新任务用）与 `task_detail.bpmn`（自定义初值）。**它们是真源**——页面照着渲染、状态机照着排顺序；`tools/gen_default_bpmn.py` 只是可选的重新生成工具 |
| 运行阶段的中文节点名 | `desktop/steps/ports.py::stage_label`（`rembg_submit` 必须走它，否则流程图出现两个「图片去底色」；`store.STAGE_LABELS` 是它的派生） |
| 框几何/绘制 | `utils/box_geometry.py`（半幅恒 2 槽、整幅恒 1 槽）；标注统一 `utils/box_draw.draw_slots` |
| 框类型人工干预交互流（切类型/整幅互斥/删框） | `desktop/components/box_kinds.py::BoxKindEditor`（taskdetail 与独立检测页共用） |
| 编辑生效链的查看器原语（立即上屏/单条缩略图刷新） | `desktop/components/viewers/edit_sync.py` |
| InfoBar 弹出（位置/时长/兜底） | `desktop/ui/toast.py::show_toast` |
| 色距字号 | `desktop/ui/theme.py` |
| JSON 落盘 | `desktop/store/json_io.py`（临时文件 + `os.replace` 原子写） |

## 改完代码必须做的事

```bash
# 桌面自测（offscreen；--only 按改动选模块，自动补依赖；动共享底层才全量）
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only <模块1[,模块2]>
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --list     # 列出全部模块

# API 文档同步（docs/api/ 是自动生成的，不要手编）
python tools/gen_api_docs.py --check     # 不一致退出码非 0；重生成去掉 --check

# 文档链接/表格校验（改任何 md 后）
python tools/check_docs.py
```

⚠️ 自测退出码 127 是伪错误（`QThread: Destroyed`），且会吃掉末段模块——
必须比对 `--list` 计划数与日志中 `==标题==` 数，缺了用 `--only` 补跑。
⚠️ 测试耗时，**不要每改一小处就跑**：按改动攒批，最后统一跑相关模块。

## 其他硬规则（违反过、踩过坑）

- 绝对导入；仓库根用 `desktop.utils.files.project_root()`。
- `QThread.run()` 必须 try/except（异常逃出 = “点了没反应”+ 被当作用户取消）。
- 跨线程信号用 `desktop.workers.connect_queued`，别裸 `connect(lambda)`。
- 界面控件 `paintEvent` 自绘，不引样式表；下拉用 `widgets.combo_box()`。
- 按页号命名的缓存不能跨书共用（键含文件大小/边长，见 `utils/files.py`）。
- 仓库长期有在制品：**不要自动 `git commit`**（等用户明示）；回滚禁用
  `git checkout HEAD -- <路径>`（会抹掉未提交在制品）。

## 文档地图

| 需要什么 | 去哪 |
| --- | --- |
| 全仓架构（入口/分层/进程模型/BPM 演进） | [`docs/dev/architecture.md`](docs/dev/architecture.md) |
| 桌面端细节（模块树、数据区、编辑生效链） | [`docs/dev/gui/gui-architecture.md`](docs/dev/gui/gui-architecture.md) |
| Worker 协议 / JSON 格式 / area 几何 | [`docs/dev/gui/gui-technical-spec.md`](docs/dev/gui/gui-technical-spec.md) |
| 用户操作手册（改了要 `build.py --manual-only` 才进安装包） | [`docs/guide/user-guide.md`](docs/guide/user-guide.md) |
| CLI 手册（`guji help` 运行时读 `docs/functions/`，**位置固定**） | [`docs/functions/`](docs/functions/overview.md) |
| API 参考（自动生成） | [`docs/api/`](docs/api/README.md) |
| 模块化解耦历史与路线图 | [`docs/dev/refactor-modularity.md`](docs/dev/refactor-modularity.md) |
| I/O 路径规则 | [`docs/dev/io_path_rules.md`](docs/dev/io_path_rules.md) |
