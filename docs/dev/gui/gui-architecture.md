# 桌面端架构文档（与 desktop/ 当前实现对齐）

## 1. 进程模型

```
desktop.py（入口）
  ├─ GUI 主进程        python desktop.py        PySide6 + qfluentwidgets
  └─ worker 子进程     python -m desktop.worker --config <json>   每阶段一个
```

- **GUI 主进程不加载重依赖**（cv2/YOLO/PyMuPDF）：预览用已生成缩略图或
  worker 渲染结果；算法全部隔离在子进程。
- worker 子进程执行完即退出，操作系统回收模型/内存，无需手动释放。
- worker 与 GUI 通过 stdout 的 **JSON Lines** 通信（见 technical-spec）。

## 2. 模块划分

```text
desktop.py              # GUI 与 worker 统一入口
desktop/
  app.py                # 主窗口与启动逻辑（只按注册表建导航，不认具体模块页）
  __main__.py           # 支持 python -m desktop / hupper -m desktop
  worker.py             # 子进程入口：仅做初始化与阶段路由（薄壳）
  stages/               # 子进程阶段执行器：events 事件输出、detect/generic/print/rembg
  steps/                # 共用步骤组件层（与流程无关的"一个处理步骤"，见 2.3）
    spec.py             #   StepSpec：命令/面板/输入种类/后缀/默认输出/一批路径归一成源
    kernel.py           #   StepKernel：只认「输入 + 输出 + 参数」的进程内执行内核
    source_zone.py      #   SourceZone：大输入区（拖文件/拖文件夹/点选/清空）
    control.py          #   StepControl：把上面几件装成"选源 → 调参 → 执行/中断"
    process.py          #   StageProcess：子进程传输层（起进程/字节流/看门狗），任务管理用
  modules/              # 左侧导航的独立模块（每个条目 = 一个自包含页面，见 2.3）
    __init__.py         #   注册表 MODULES（key/标题/图标/副标题/工厂）——唯一事实来源
    shell.py            #   壳层：NavigationInterface + 页面栈（导航默认折叠）
    base.py             #   ModulePage 基类：页头 + 整幅输入区 + 左右分栏 + 状态行
    extract/page.py     #   图片提取
    rembg/page.py       #   去底色
    imposition/page.py  #   拼图（= 图片拼版）
  pages/                # 页面层：一个页面一个子包
    tasklist/page.py    #   任务列表页（首页：表格、导入、详情/删除）
    taskdetail/         #   任务详情页：一个骨架 + 按职责拆分的控制器 Mixin
      page.py           #     骨架（任务切换/阶段切换/状态刷新），组合下列 Mixin
      view.py           #     UI 组装（头部/步骤条/预览区/控制列/日志）
      manifest.py       #     页面清单、缩略图、页面增删
      history.py        #     历史执行配置回填（暂存优先）
      params_draft.py   #     参数暂存：改过没执行也不丢
      submit.py         #     rembg 提交控制器与按钮状态
      print_list.py     #     第四步待打印列表
      runner.py         #     阶段执行（worker 子进程编排）
      detect.py         #     detect 检测控制
      rembg_live.py     #     第三步改参数/翻页时只重算当前页
      imposition.py     #     流程条「图片拼版」共享基元（文档读写/取图来源/详情进出）
      imposition_pages.py #   模块一「选择拼版」控制器：启用开关、弹窗加页、删页/页序/清空
      imposition_layout.py #  模块二「拼版操作」控制器：旋转/复位、版面落盘、防抖合成、状态行
  services/             # 纯业务规则（无 Qt）：print_plan 条目派生、submit_state 版本状态机、
                        #   imposition 拼版版面与合成
  ui/                   # 界面系统：设计令牌 + 基础自绘控件 + 全局样式（详见 gui-ui-system.md）
    theme.py            #   颜色/间距/圆角/字号/状态色映射（唯一色值来源）
    style.py            #   全局字体、主题色、极简全局 QSS
    widgets.py          #   Card/StatusChip/ProgressLine/EmptyState/PageHeader…（paintEvent 自绘）
  components/           # 步骤条、任务表格、查看器（PDF/图片/rembg）、阶段参数面板、日志
    step_bar.py             # 顶部步骤条：编号/对勾徽标 + 连接箭头 + 状态色（自绘，不用样式表）
    imposition/                    # 图片拼版组件包（components/imposition/），按操作逻辑分两个模块
      page_list.py                 #   模块一「选择拼版」：左列拼版页清单
      picker.py                    #   模块一「选择拼版」：「选择拼版」弹窗
      canvas.py                    #   模块二「拼版操作」：拖动/缩放拉伸/旋转画布（同 PrintLayoutCanvas 一族）
      panel.py                     #   模块二「拼版操作」：右侧控制面板（开关/页序/旋转/复位/删除）
      view.py                      #   装配层：左列清单 + 画布（ImpositionViewWidget）
    task_table.py           # 任务表格：子任务状态用状态胶囊组显示
    log_panel.py            # 执行日志：底部状态条 + 点击唤出的浮层（出错自动标红）
    panels/params_spec.py   # 各阶段默认参数与下拉候选表（唯一默认值来源，见下）
    panels/print_params.py  # print 参数解析/序列化纯函数（默认值转发自 params_spec）
    panels/print_form.py    # print 表单控件构建（分区与控件组装）
    panels/print_nodes.py   # 标题切换节点列表（逐行堆叠，高度随行数自适应）
    panels/print_panel.py   # print 面板状态（取值/回填/重置）
    panels/base.py          # 阶段参数面板基类（表单构建 / 重置默认值）
  workers/              # 后台 Qt worker：指纹、预览渲染、缩略图、清单缩略图
  store/                # 文件持久化：tasks/runs/pages/annotations + 旧数据迁移
    json_io.py              # 原子读写 JSON（临时文件 + os.replace，损坏自动备份）
  utils/                # file_hash、natural_key、清单工具
```

配套（desktop 之外）：

- `utils/box_geometry.py` — area/border 几何规则唯一实现，GUI 预览与 CLI 共用；
- `utils/box_draw.py` — 检测框标注绘制唯一实现，GUI 预览与 CLI `detect --save` 共用；
- `functions/`、`cli/` — CLI 层，`rembg`/`print` 阶段经 `CommandArgs` 转发执行，
  `extract`/`detect` 由 desktop worker 直接实现（不走 CLI 输出目录规则）。
  不过 **`detect` 的检测算法仍复用 `functions.detect.detect_page_content`**——
  只有「输出目录规则」被绕开，算法没有第二份实现。

### 2.1 阶段参数默认值：`panels/params_spec.py` 是唯一来源

四个阶段面板的**默认参数**与**下拉候选表**集中在 `components/panels/params_spec.py`：
面板的「控件初值」「`_apply_args` 缺键兜底」「`reset_to_default`」三处都从
`DEFAULTS[stage]` 取，不再各写一份字面量。

散着写的代价是漂移——`page_number_font_size` 曾真的存在两套值：默认表 18、
`_apply_args` 兜底 12（源头还是 `docs/functions/print.md` 的参数表写着 12，
面板照抄了文档）。用户点「恢复默认」得到 18，历史配置缺这个键时回填成 12。

`params_spec` 与 `core.command_spec` 的分工：

- `core/command_spec.py` 是**命令行**参数的唯一事实来源；
- `params_spec.DEFAULTS` 是**桌面表单**的那一份。extract/rembg 直接以
  `COMMAND_SPECS[stage].defaults` 为底、只覆盖表单侧特有的键（如 `pages` 的
  `None` → 空串），CLI 改默认值时桌面自动跟随；
- print 段刻意取 `PRINT_FORM_DEFAULTS`（比 CLI 更"已开启"：有书名、有页码）。

配套便利函数 `base.default_for(parameters, defaults, key)`：缺键**或值为 `None`**
时回落默认。不能写成 `parameters.get(key, defaults[key])`（存着 `{"dpi": null}`
时兜底永不生效），也不能写成 `parameters.get(key) or 默认`（合法的 `False`/`0`
会被误判成"没值"）。

守卫见 `tests/selftests/params_spec.py`：源码层（不许再写 `p.get("键", 字面量)`）、
覆盖层（`get_args()` 的键必须登记）、行为层（恢复默认 == 默认表）、
文档层（`docs/functions/print.md` 的数值默认值与 `command_spec` 一致）。

### 2.2 导入约定：一律使用绝对导入

全项目（`desktop/`、`cli/`、`functions/`、`utils/`）**不使用相对导入**
（`from .x` / `from ..x`），统一写自顶向下的完整路径：

```python
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.pages.taskdetail.page import TaskDetailPage
from desktop.components.viewers import ImageViewerWidget
```

理由：相对导入的层数绑定文件位置，**文件一挪目录就静默指向错误模块**（本次把
`pages/` 拆成子包时就踩到：`from ..services...` 在深一层后解析成了
`desktop.pages.services`）。绝对导入与文件位置解耦，移动/重命名文件只需改引用点。

包内动态导入同样走绝对路径：

```python
# functions/__init__.py
_COMMAND_MAP = {"crop": ("functions.crop", "CropFunction"), ...}
mod = importlib.import_module("functions.crop")   # 不用 import_module(".crop", __name__)

# utils/__init__.py 的延迟加载表 _LAZY 同理，值为 "utils.image_utils" 这类全路径
```

> 与之配套的一条：**不要用 `Path(__file__).parents[N]` 推算项目根**。文件挪一层
> 就会算错（worker 子进程的工作目录就是这么坏的）。取项目根用
> `desktop.utils.files.project_root()`，它基于 `desktop` 包自身位置计算。

### 2.3 独立模块与共用步骤组件层（`desktop/modules` + `desktop/steps`）

用户 2026-10-02 的口径：

> 左侧开发「图片提取 / 去底色 / 拼图」等模块功能，这些功能**独立**、
> 但是**复用先有功能**；任务管理每个步骤组件有先后关系，因此我们的组件
> **不需要相互关联**，公共组件**定义好 API 就行**——入口文件目录、输出文件目录。

这条口径落成两层，**依赖方向严格单向：`modules` → `steps` → `components/ui`**。

**`desktop/steps` —— 与流程无关的"一个处理步骤"**（谁都能用）

| 文件 | 职责 | 有没有 Qt |
| --- | --- | --- |
| `spec.py` | `StepSpec`：跑哪个命令、用哪个参数面板、输入是什么、默认输出怎么派生；**入口规则**也在这里（认哪些后缀、能不能直接收目录、用户拖进来一堆文件/文件夹到底算哪个源） | ✗ 纯逻辑 |
| `kernel.py` | `StepKernel`：只认「源 + 输出目录 + 参数」的执行内核，跑在 QThread 里，进度/成功/失败走信号；`job_for(spec)` 是**造 job 的唯一入口** | ✓ |
| `source_zone.py` | `SourceZone`：**大输入区**——拖文件、拖文件夹、点选、一键清空 | ✓ |
| `control.py` | `StepControl`：把「选源 → 调参数 → 执行/中断」装成一块控件（模块页右栏就是它） | ✓ |
| `process.py` | `StageProcess`：子进程传输层（起进程 / 转发原始字节 / 看门狗兜底） | ✓ |

**`desktop/modules` —— 左侧每个条目一个自包含页面**

- 模块清单**不再单独维护**：`modules/__init__.py::MODULES` 由
  `desktop.steps.spec` 里 `nav=True` 的 spec **派生**。加一个模块 = 写一个
  ``desktop/modules/<key>/`` 包（必须导出 `PAGE` = 页面类）+ 在 `SPECS` 加一条
  `nav=True` 的 spec，**壳层一行都不用动**（壳层只认元数据与工厂，从不 import
  具体页面）；
- 模块页**惰性构造**：用户第一次点进去才建；模块之间、模块与 `TaskDetailPage`
  之间**没有 import 依赖**（由 `tests/selftests/modules_shell.py` 用 AST 静态检查）；
- 四个模块（extract / rembg / print / imposition）**各持自己的一份** `StepControl`
  （各自的源、输出、执行线程）⇒ 一个模块在跑，另一个模块的按钮不受影响。

**「整幅大输入区」怎么来的**：`ModulePage._build_input()` 返回 `SourceZone` 时，
它会插在页头与左右分栏之间、横跨整幅宽度；页面同时在 `_build_control()` 里
把**同一块控件**交给 `StepControl(zone=...)`（`StepControl` 因此不重复摆一块）。
`ModulePage` 还把**整页拖拽**转发给它——拖到页面空白处也算拖进输入区。

**入口与出口的接缝（两处，都别绕过走自己那套）**：

- **入口归一化**：`StepSpec.resolve_source(paths)` 把"用户拖进来的一堆文件/文件夹"
  收成**一个源**，`collect_files(paths)` 摊平成**一份文件清单**（拼图要的）。
  顶层没有可用文件时**自动下钻 1~2 层**（`AUTO_DESCEND_DEPTH`）——因为
  `extract` 的产物固定落在 `<输出根>/<PDF名>/images/`，用户会理所当然地
  把那个**输出根**拖给「去底色」；恰好一个子目录装着就自动指过去，多个则
  拒绝并让用户挑（混着处理会把不同书的页拼在一起）。
- **出口布局**：`StepSpec.flat_output` 置真的步骤（目前只有 `extract`），
  单源时由 `kernel.job_for(spec)` 装上收尾钩子，把 `<输出>/<PDF名>/**`
  **平铺到输出目录根下**再删空壳；源是**目录**（批量）时**保持**每个 PDF
  一个子目录（否则大家的 `1.jpg` 会互相覆盖）。同名冲突时整个不动。
  ⚠️ 造 job 只走 `job_for(spec)`——哪一步需要收尾只有它知道，在别处再拼一次
  `command_job` 就一定会漏（实测断过「提取 → 去底色」）。

**步骤清单只有一份（2026-10-02 收敛，BPM 的地基）**

用户要做的「自定义流程（类 BPM）——步骤随意搭配」要求步骤清单**只有一个事实
来源**。改造前有四份各写各的：`store/tasks.py` 的 `STAGES`、`steps/spec.py` 的
`SPECS`、`modules/__init__.py` 的 `MODULES`、`components/panels/__init__.py` 的
`_PANEL_ORDER`——加一步要改四处，漏一处没有任何守卫能发现（文案已经漂过一次：
流程条写「提取图片」、导航写「图片提取」）。现在全部由 `SPECS` 派生：

| 派生物 | 在哪 | 取哪些 |
| --- | --- | --- |
| `STAGES` / `STAGE_LABELS` / `STAGE_SHORT` | `desktop/store/tasks.py` | `role == "stage"` 的 key / `stage_name()` / `short_name()` |
| `IMPOSITION_STAGE` / `_LABEL` / `_INDEX` | 同上 | `role == "optional"` 的第一条；下标 = `len(STAGES)` |
| `MODULES` | `desktop/modules/__init__.py` | `nav == True` 的 `title` / `nav_tip()` / `nav_icon` |
| `PANEL_CLASSES` | `desktop/components/panels/__init__.py` | `role == "stage"` 的 `panel` 类名 |

`StepSpec.role` 区分**主链步骤**（`"stage"`，进 `STAGES`）与**流程条可选节点**
（`"optional"`，拼版就是）；`StepSpec.nav` 表示**有没有独立模块页**。两者正交——
"进不进流程"和"有没有独立功能"是两件事。

**四条主链步骤 + 拼版现在全部有独立模块页**（`nav=True`，共 5 个）。补第 4、5 个
（`print` / `detect`）时暴露出两类"产物形态"问题，都留在 spec 上而不是散在各页里：

- **产物是单个文件**（`print`，`artifact_is_file=True`）：见上一节。
- **产物根本不是文件**（`detect`）：检测默认不落盘，框坐标只经 ``page_boxes``
  **结构化事件**回来。内核原先只转 ``progress`` / ``log``，这类事件全被丢掉，
  于是"检测页永远显示不出框"。补了一条**通用事件通道**
  （``StepKernel.event`` / ``StepControl.event``，2026-10-02）：内核不认识事件名，
  只原样透传，认不认识由上层决定——将来自定义流程里任何"步骤自己产生结构化结果"
  的场景都走这条，不必再改内核。

⚠️ **`flat_output` 与 `artifact_is_file` 是两种不同的"出口形态"**：
`flat_output`（extract）指产物是个**目录**，单源时把里面平铺到输出根；
`artifact_is_file`（print）指产物是**单个文件**，输出参数收的是**目录**而文件名
由命令自己定，所以内核**不能**用 `--output` 去覆盖 `outpath`，`finished` 回传的
是**产物路径**而不是目录。两者互斥（`steps_components` 有断言钉住）。

⚠️ **文案字段按"界面上有哪几个地方显示"逐个建，不合并**：`title`（模块页头大
标题 + 导航条目）、`subtitle`（模块页头副标题）、`nav_tooltip`（导航悬停提示）、
`stage_title`（流程步骤条）、`short`（步骤条短名）。同一步在流程条和导航里本来
就叫法不同（流程条说**动作**「提取图片」，导航说**东西**「图片提取」），硬合成
一个名字必然改动其中一处界面。

⚠️ **`inputs` / `outputs` 是 BPM 端口预留**：已经声明（如 extract 的
`("pdf",)` → `("pages",)`），但**还没接线**——任务流程走的仍是"约定目录布局"。

⚠️ **检测框的「槽位约定」只有一份实现**：半幅恒 2 槽 ``[左, 右]``（缺失侧 null）、
整幅恒 1 槽 ``[整幅]``，下游（rembg / 布局）靠**槽数**分辨形态——所以它是跨层
契约，不是某一步的内部细节。规则本体在 `utils/box_geometry.page_box_slots`，
两个入口都调它：`functions.detect.PageBoxes.slots()`（对象侧）与
`page_box_slots_from_event(payload)`（**事件侧**，任务流程第二步与独立检测页共用）。

放在 `utils` 而不是 `functions` 是刻意的：`utils` 不许 import `functions`（分层
单向），而 GUI **主进程**必须能便宜地导入这条规则——实测 `functions.detect` 一被
导入就带进 **cv2**，主进程直接用它会破坏"主进程不加载 cv2/torch"的进程模型。
人工画框那一侧（扁平框 → 槽位）走 `half_slots`，同属这一层。

**与任务流程的边界（现状，别再走回头路）**：

- **已共用**：参数面板（`ExtractPanel`/`RembgPanel`/`ImpositionPanel`）、执行
  入口（`functions.get_function` / 纯函数 `services.imposition`）、步骤元数据与
  入口规则（`StepSpec`）、子进程传输层（`StageProcess`）、大输入区（`SourceZone`）；
- **没共用**：任务详情页的**编排**（四步先后、提交门禁、步骤记忆、拼版可选节点）。
  那本来就是"有先后关系"的那部分，按用户口径**不需要**做成可复用零件；
  它只在 `desktop/pages/taskdetail/` 里演进。

## 3. 数据存储：纯 JSON 文件（无数据库）

数据根目录 `~/Documents/guji`：

```text
guji/
  tasks.json            # 任务索引（id=任务号、名称、源路径、hash、状态、时间…）
  ui.json               # 全局界面状态（last_task + source_hash：上次停留的任务，重启恢复用）
  tasks/<任务号>/
    <源文件名>.pdf      # 导入时复制的源文件副本
    pages.json          # 页面清单 [{file, label}]
    runs.json           # 各阶段执行历史（最新在前，≤20 条）
    boxes.json          # 检测框 {页stem: {boxes:[左,右], origin: auto|manual}}
    sizes.json          # 页面图片原始尺寸 {页stem: [w, h]}
    ui.json             # 界面状态（当前只有 last_stage：上次停留的步骤 key）
    drafts/<阶段>.json  # 参数暂存：用户改过但还没执行的阶段参数（进页面时优先回填）
    runs/               # 子进程执行配置 run-*.json / detect-config.json
    thumbnails/
      source/0001.jpg…  # 源 PDF 页缩略图（256px，导入即生成，永不清理）
      print/            # 输出 PDF 预览缩略图（print 成功后重建）
    stages/
      extract/          # 提取图片（1.jpg…，直接平铺）
      rembg/            # 去底色整页结果（1.png…）
      print/print.pdf
```

所有 JSON 读写统一走 `store/json_io.py`：

- **写**：先写同目录临时文件，`flush` + `fsync` 后再 `os.replace` 原子替换——中途
  崩溃不会留下半截文件，也让并发读者永远看到完整内容；
- **读**：解析失败时把损坏文件备份为 `<名>.corrupt-<时间>` 并返回默认值，而不是
  让整个界面崩掉；
- **删除任务竞态**：任务目录已被删除时，写入直接跳过（回调晚于删除时不报错）。

存储一直是纯 JSON 文件，**没有旧数据需要迁移**：`TaskStore` 构造时只确保
`tasks/` 存在（`store/store.py`）。曾经的 `store/migrate.py`（SQLite `guji.db`
与旧目录布局的一次性迁移）已随 SQLite 一并移除，因此打包产物不再包含
`sqlite3.dll`。

## 4. 关键算法位置

| 算法 | 位置 |
| --- | --- |
| 内容框检测（GUI/CLI 唯一入口） | `functions.detect.detect_page_content` → 底层 `utils.yolo_utils.detect_content_boxes`（单例，CPU；半幅 harfcontent / 整幅 fullcontent） |
| area/border → 效果区域合成 | `desktop/workers/preview_worker.compose_region_output` |
| 几何规则（GUI/CLI 共用） | `utils/box_geometry.py`（parse_border_mm、compute_final_boxes） |
| 检测框标注绘制（GUI/CLI 共用） | `utils/box_draw.py`（draw_boxes，配色与 GUI 预览一致） |
| 自然排序（r 在 l 前） | `utils/sort_utils.pdf_custom_sort_key` |
| 页缩略图生成 | `desktop/workers/source_thumbnails_worker.py` |
| 文件指纹 | `desktop/utils/files.file_hash` |

## 5. 性能设计

- **重负载隔离**：图像解码、区域合成、YOLO 推理全部在 worker 线程/子进程；
  主线程只接收最终小图。
- **⚠️ 跨线程连接必须走 `connect_queued`**：PySide6 里
  `signal.connect(lambda)` 是**直接连接**（lambda 没有接收者 QObject），
  槽会跑在 worker 线程；加 `QueuedConnection` 也没用（functor 连接的接收者
  仍记成 sender，事件照样排回 worker 线程）。闭包里一旦碰 widget，Qt 就在
  子线程启动定时器 → 刷屏 `QBasicTimer::start: Timers cannot be started
  from another thread`。连到宿主 QObject 的**绑定方法**本来就是安全的，
  闭包一律用 `desktop.workers.connect_queued(owner, signal, slot, thread)`。
- **缩略图直读**：列表条目图标读取 256px 预生成缩略图（QImageReader 缩放解码），
  不解码原始扫描图；rembg 预览的区域合成也以缩略图/worker 完成为主。
- **防重复**：阶段切换时页面清单未变化则跳过重建；加载请求带令牌，
  仅最后一次生效。
- **请求取消**：阶段执行中可 kill worker 子进程；续跑按缺失页/缺失输出补齐。
