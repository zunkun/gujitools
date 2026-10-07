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
                         #     + inputs/outputs（**BPM 端口声明**）
    kernel.py           #   StepKernel：只认「输入 + 输出 + 参数」的进程内执行内核
    source_zone.py      #   SourceZone：大输入区（拖文件/拖文件夹/点选/清空）
    control.py          #   StepControl：把上面几件装成"选源 → 调参 → 执行/中断"
    process.py          #   StageProcess：子进程传输层（起进程/字节流/看门狗），任务管理用
    ports.py            #   端口与连线：产物类型 / 每步的输入输出 / 落点 / 谁供给谁
  shell.py              # 壳层：NavigationInterface + 页面栈（导航默认折叠）。
                         #   ⚠️ 住在 desktop 包根而非 modules/：它要挂任务列表页与
                         #   详情页（pages），住进 modules 会破坏包边界
  modules/              # 独立任务页（singletask）：每个条目 = 一个自包含页面，见 2.3
    __init__.py         #   注册表 MODULES（key/标题/图标/副标题/工厂）——由
                         #     steps/spec.py::NAV_STEPS 派生，不是独立清单
    base.py             #   ModulePage 骨架（页头/输入区/左右分栏/状态行/日志）
                         #     + StepModulePage（普通步骤页的共用外设，见 2.3）
    thumb_source.py     #   ThumbSourceMixin：左栏「缩略图条 + 大图」统一接线
    extract/page.py     #   PDF图片提取
    detect/page.py      #   检测文本框（含导出标注图 / 导出坐标 JSON）
    rembg/page.py       #   图片去底色
    print/page.py       #   PDF排版
    imposition/page.py  #   图片拼板（有意不继承 StepModulePage，见 2.3）
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
| `source_zone.py` | `SourceZone`：**大输入区**——拖文件、拖文件夹、**「选择文件 / 选择文件夹」按钮**、已选态「更换」、一键清空；**独占模式**（页面上再没有别的控件时撑满整幅） | ✓ |
| `control.py` | `StepControl`：把「选源 → 调参数 → 执行/中断」装成一块控件（模块页右栏就是它） | ✓ |
| `process.py` | `StageProcess`：子进程传输层（起进程 / 转发原始字节 / 看门狗兜底） | ✓ |
| `ports.py` | 步骤的**输入 / 输出端口** + 落点 + 连线表（BPM 换顺序只改它） | ✓ |

#### 端口与连线：`desktop/steps/ports.py`（2026-10-03 补完）

需求原话是「每一步都有输入，输出就可以了，后续用 bpm 处理不同的任务流程顺序」。
此前 `StepSpec.inputs` / `outputs` 只是**声明了没人读**，任务流程仍靠"约定目录
布局"串联——`store.tasks` 四个 `*_output_dir` 方法 + `taskdetail.runner` 里的
`if stage == "extract" / elif "print"`。加一步或重排顺序要改这些地方，BPM 无从下手。

现在这一层把"步骤怎么连"收成三张表（**纯逻辑、无 Qt**，可被 CLI/自测/将来的
编排引擎安全导入）：

| 表 | 回答什么 | 谁在用 |
| --- | --- | --- |
| `PORT_ARTIFACTS` | 数据"是什么"（`pdf` / `pages` / `boxes`） | BPM 按类型匹配，不认上游是谁 |
| `STAGE_LOCATIONS` | 每个端口落在 `tasks/<id>/` 的哪里 | `store.artifact()` 及四个 `*_output_dir` |
| `SUPPLIERS` | 谁供给哪个端口（**BPM 的边**） | `store.stage_input()` → runner / 拼版取图 |

```python
# 改连线 = 改一张表，别处不动
ports.SUPPLIERS["print"] = {"pages": "imposition"}       # 让 PDF 直接吃拼版图
repo.stage_input(tid, "print", "pages")                  # 自动解析成 stages/imposition
```

三处要点：

- **BPM 化的前提是端口按类型匹配**：`rembg` 声明吃 `("pages", "boxes")`，
  它不关心 `pages` 来自 `extract` 还是将来的别的步骤——这才是"解耦"。
  ⚠️ 声明必须与事实一致：漏写一个就等于给 BPM 一条**假的边**（`rembg` 漏写
  `boxes` 曾让依赖检查放行"先去底色后检测"的非法顺序，由
  `tests/selftests/step_ports.py` 逮到并修掉）；
- **运行阶段 ≠ 步骤 key**：多一个 `rembg_submit`（「提交本次任务」是 `rembg`
  的第二个动作）。`STAGE_STEPS` 负责映射，否则第三步产物没有落点；
- **条件连线单列**：`print` 的上游随"拼版是否生效"变化，用
  `print_input_overrides()` 作为**运行时覆盖**传进 `resolve_input`，而不是
  写进静态表——把运行态开关混进结构表，将来就没法枚举可能的流程了。

`missing_stages(order)` 是给编排器用的**依赖检查**：按顺序列出"上游还没跑"的
阶段。它必须放过 `SUPPLY_TASK_SOURCE`（入口阶段的输入由任务自己供给），
否则 extract 会被永远判成不能跑。

⚠️ **同一输出目录只准有一个写入者**（2026-10-03 修「程序容易跑崩溃」）：
拼版合成有**两条**路径会打到同一个 `stages/imposition` 目录——

- 后台防抖合成 `ImpositionComposeWorker`（拖版面时反复触发）；
- 主线程同步合成 `_compose_imposition_now`（改完版面立刻点「生成PDF」时补一轮，
  见 `runner.py` 的 `elif stage == "print"`）。

原先两条路径**无任何互斥**，写盘又是 `PIL.Image.save()` 的**就地截断重写**
⇒ 8 线程并发实测直接抛 `PermissionError`（后者撞上前者正开着的文件句柄），
`_sweep_stale` 还会在另一线程写到一半时把它 `unlink` 掉。现在
`services/imposition.py` 的 `compose_doc` 整轮持 `_COMPOSE_LOCK` +
`_save_page_atomic`（临时文件 + `os.replace`）。**两道防线各挡一类故障**：
锁挡线程间打架，原子写挡"同一线程自己中途挂掉"留下的半张 PNG。
新增并发路径时必须自己带锁，别直接调 `compose_page()` 落盘。

⚠️ **分批解码的批次之间必须有间隔**（同一天修「cpu 跑满」）：
`imposition/picker.py` 的 `_fill_thumbs` 原先用 `QTimer.singleShot(0, ...)`
自我续期——0 间隔 = 事件循环一空闲就接着下一批，而每批要**整幅解码**几张几千
像素的原图（`_source_thumb_pixmap` 不能用 `QImageReader.setScaledSize`：
去底成品是「1bit 调色板 + tRNS」的透明 PNG，缩放解码会给出异常尺寸）。
N 张候选图 = `ceil(N/6)` 轮零间隔重解码全程占着 GUI 主线程 ⇒ CPU 跑满、
界面像崩了。现在批次之间走 `THUMB_GAP_MS = 150`（对齐 `ThumbsMixin.BATCH_GAP_MS`）。
**凡是「自己续期自己」的 singleShot，一律要想清楚间隔。**

#### 详情页的步骤元数据也在 spec 里（2026-10-03）

连线抽完之后，任务详情页里还剩 4 条 `if stage == "..."`。它们全是
「**这一步在详情页长什么样**」的声明性数据，于是同样搬进 `StepSpec`：

| 原 if 链 | 现在查 spec 的字段 |
| --- | --- |
| 按钮文案 / 提交按钮显隐 / 右栏区块显隐 | `run_button_text` / `has_submit` / `panel_extra` |
| `stage == "print"` 换控制列宽度 | `control_width` |
| 主预览控件名（原 `_STAGE_PREVIEW_ATTRS`） | `preview_attr` |
| 历史回填按阶段跳过不同键 | `history_skip` / `auto_fill_skip` |

统一入口是 :func:`desktop.steps.ports.spec_for_stage`：

```python
spec = ports.spec_for_stage(self.current_stage())   # 处理 rembg_submit → rembg
self.run_button.setText(spec.run_button_text)
```

⚠️ **不要用 `spec_by_key(stage)`**：`rembg_submit` 是同一步骤的第二个动作，
直接按 key 查会拿到 `None`。护栏在 `tests/selftests/step_ports.py` 第 6 节
（既验 spec 的值，也验页面真的读它）。

**加一步现在只改两处**：`SPECS` 加一条 spec（端口 + 界面元数据）+ 一张连线表
（谁供给谁）。页面、store、runner 里不再有任何"认得哪个 step 是谁"的代码。



**`desktop/modules` —— 左侧每个条目一个自包含页面**

- 模块清单**不再单独维护**：`modules/__init__.py::MODULES` 由
  `desktop.steps.spec` 里 `nav=True` 的 spec **派生**。加一个模块 = 写一个
  ``desktop/modules/<key>/`` 包（必须导出 `PAGE` = 页面类）+ 在 `SPECS` 加一条
  `nav=True` 的 spec，**壳层一行都不用动**（壳层只认元数据与工厂，从不 import
  具体页面）；
- 模块页**惰性构造**：用户第一次点进去才建；模块之间、模块与 `TaskDetailPage`
  之间**没有 import 依赖**（由 `tests/selftests/modules_shell.py` 用 AST 静态检查）；
- 五个模块（extract / detect / rembg / print / imposition）**各持自己的一份**
  `StepControl`（各自的源、输出、执行线程）⇒ 一个模块在跑，另一个模块的按钮
  不受影响。

**`StepModulePage`：普通步骤页的共用外设**（2026-10-03）。四个步骤页此前把
`_build_input` / `_build_control` / `_on_source_changed` / `_on_failed` /
`shutdown_workers` **逐字抄了四遍**——加第五个步骤就再抄一遍。现在这些收在
`modules/base.py::StepModulePage`，一个步骤页只剩两件真属于自己的事：

```python
class MyPage(StepModulePage):
    SPEC = spec_by_key("my_step")        # 1. 认领步骤元数据（页头文案也由它派生）

    def _build_preview(self):            # 2. 左栏用哪个预览控件
        self.viewer = SomeViewer()
        return self.viewer

    def on_result(self, output, result): # 3. 产物怎么上屏
        self.viewer.set_images(...)
```

可选钩子：`source_summary()`（副标题那一行，默认 `<源> → <输出>`）、
`source_images()`（源里的图片清单）、`on_failed()`、`idle_text()`。
`tests/selftests/step_ports.py` 第 5 节钉住"页面里不再出现 `SourceZone(` /
`StepControl(`"，防止又抄回来。

⚠️ **拼版页有意不继承** `StepModulePage`：它的"源"是**一批图片**（要
`collect_files` 摊平），执行也是纯函数导出而非 `StepSpec.command`，外壳对不上。
它继续直接继承 `ModulePage`——同一条断言也钉住了这一点，别为了"统一"硬塞。

**日志区与详情页同款**（2026-10-03）：`ModulePage` 的底部改用
`components.log_panel.LogPanel`（常驻 34px 状态条 + 点击唤出浮层），此前是一块
**常驻 76px 的裸 `QPlainTextEdit`**——空闲时白占一块位置，且与详情页两套观感。
⚠️ 随之 `log()` 从 `appendPlainText` 改成 `append`（浮层里是 qfluentwidgets 的
`TextEdit`）；`show_workspace()` 藏的是 **`log_panel` 本身**而不是 `log_view`，
否则会留下一条什么都不显示的状态条。

#### `singletask`：独立任务的数据区（2026-10-03）

用户口径：「这个缩略图也可以放在 `~/Documents/guji/singletask` 下面，
singletask 是独立任务，下面有各种子任务」。

```
~/Documents/guji/
├─ tasks/          任务流程：一个 id = 一本书，四步 + runs/boxes/草稿
├─ tasks.json
└─ singletask/     独立任务：左侧导航那 5 个功能页
   ├─ extract/                       子目录名 = StepSpec.disk_key()（路由键）
   │  ├─ thumbnails/<书键>/0001.jpg …                 PDF 的页缩略图
   │  ├─ thumbnails/<书键>/<边长>/0001.jpg + map.json  extract 的口径（边长进目录）
   │  └─ thumbs/<边长>/<图键>.jpg …                   图片源的缩略图
   └─ imposition/
      └─ edited/0001.png                              手改过的整页组合（成品口径）

⚠️ **singletask ≠ taskdetail，数据不相通（硬规则）**：独立任务页与任务流程只
共用渲染组件、参数面板与步骤元数据；缓存根各归各——独立页缓存在
`singletask/<key>/`，任务流程缓存在 `tasks/<id>/thumbnails/{source,print,
imposition,detect}`。**任何一侧都禁止借道另一侧的缓存区**（历史 bug：拼板左列
缩略图曾误写进 singletask，由 `tests/selftests/imposition.py` 的缓存边界断言
钉住）。taskdetail 缓存随「删除任务」整体清理；singletask 缓存独立生命周期。
```

路径入口都在 `desktop/utils/files.py`：`singletask_dir` / `singletask_thumbnails_dir`
（PDF 按页编号那套）/ `image_thumbs_dir` + `image_thumb_cache_path`（图片源那套）/
`book_key` / `safe_dirname`。

- **只放缓存，不放产物**：模块页的输出目录仍然默认在**源文件旁边**
  （`StepSpec.default_output`），别动用户已经习惯的产物位置（用户确认过）；
- ⚠️ **必须按书分一层目录**（自测当场逮到）：页缩略图文件名是**页号**
  （`0001.jpg`…），而这个目录**所有书共用**。不按书分开，A 书第 1 页会被当成
  B 书第 1 页的命中缓存 ⇒ 翻页翻出别本书的内容。任务流程那边没这问题，因为
  `tasks/<id>/` 一本书一个目录；
- ⚠️ **图片源的缩略图键里带"文件大小 + 路径指纹"**（`book_key`）：图片条目名
  五花八门（`1.jpg` / `右-01.png`…），按序号命名必然张冠李戴；⚠️ 边长必须进
  **目录名**（`ThumbStrip.decode_edge` 随 dpr 变）。

**独立任务页的左栏统一是「缩略图条 + 右侧大图」**（用户 2026-10-03：所有独立
任务左侧都显示缩略图）。此前五个页面各写各的，现在收在两处：

- `desktop/modules/thumb_source.py::ThumbSourceMixin`：`show_source()` 按源类型
  分派（PDF → `show_pdf()`，图片/目录 → `show_images()`）。extract/detect/rembg/print
  继承它；拼图页**不继承**（它的"源"是一批图、左栏是拼版页清单），只复用
  `image_thumbs_dir` 这个路径事实来源；
- `desktop/components/viewers/ImageViewerWidget` 两种形态：**图片模式**
  （`set_images` / `set_thumb_source`）与 **PDF 页模式**（`set_pdf_source` +
  `begin_pdf_pages(count)` + `set_pdf_thumb(gen, idx, img)`，大图按需渲高清页，
  **不是**拿 256px 小图放大）。⚠️ `set_images` **必须先 `_clear_page_source()`**，
  否则清单里的 `1.jpg` 会被当页号去 PDF 里渲。护栏在
  `tests/selftests/modules_shell.py` 第 10 节（含"换一本书渲出的是它自己的页数"）。

⚠️ **PDF 源走 `PreviewWorker` 的缩略图通道，图片源走 `ImageThumbCacheWorker`**：
前者的单飞锁、按耗时让出 GIL、原子写、页边界可取消都是踩出来的，别重写。

#### 「完成」的覆盖确认（2026-10-04）

用户口径：「**图片编辑最后应用的时候需要提醒，会覆盖原本的图片**」。
收在 `ImageEditorDialog._confirm_overwrite()`，由 `_finish()` 在**任何烘焙
之前**问一句；选「返回继续编辑」就 `return`，弹窗不关、编辑全部保留。

⚠️ `_finishing` 必须在**确认框之前**置位：`MessageBox.exec()` 自带事件循环，
双击「完成」会在框弹出后再进一次 `_finish` ⇒ 叠出第二个确认框（甚至两个
后台烘焙）。顺序是"先上锁 → 再问 → 不同意就退出并解锁"。

⚠️ **四个短路都当作用户同意**（`return True`），不写盘/没东西可丢的事一律
不弹，假警报只会让用户觉得这框很蠢：

| 条件 | 为什么 |
| --- | --- |
| `not save_back` | 虚拟预览（区域合成/打印重排/PDF 页）压根不写盘 |
| `not target_exists` | 整页组合**首次**编辑写的是缓存区新建文件，没有旧图可丢 |
| `_image == _original` | 没改动（QImage 逐像素相等），空跑一趟 |
| `MessageBox` 抛异常 | 自测换成记录器替身时没有真 `exec()` |

**「独立任务」与「任务流程」的落地口径不同（这是设计，不是 bug）**：独立任务
页的「应用」**一律落地实体文件**（`ZoomPopupMixin.edit_current_image` 走
`overwrite_image_file` 原子覆盖）；任务流程里则**看目标**——有 `edit_path`
才落地（区域合成、打印效果这些派生显示改的仍是它派生的那个真实文件），
PDF 矢量页没有可回写文件，右键菜单干脆不给「编辑图片」这一项。判据统一是
`ZoomTarget.edit_path`，不是"在哪个页面"。

⚠️ 确认框**要点名文件**（`editor.target_name`，宿主在构造后回填）：不知道
具体文件名的覆盖确认等于没确认。⚠️ 刻意做成**属性而不是 `__init__` 参数**——
六个宿主的签名被自测的替身编辑器（`_StubEditor(parent, image, save_back)`）
硬编码着，`_open_editor` 多一个关键字参数就让整条自测抛 `TypeError`。
护栏：`tests/selftests/image_editor_saveback.py` 第 6 节。

#### 独立任务页的「编辑生效链」（2026-10-03）

用户口径：「**独立步骤，图片也可以编辑生效**」。编辑入口本来就是共用的
（放大弹窗 / 右键「编辑图片」→ `ImageEditorDialog` → 原子覆盖真实文件），
缺的是**覆盖之后界面怎么办**：此前只有任务详情页做了
（`TaskDetailPage._on_page_image_saved`），独立页里改完，磁盘上的图确实变了，
屏幕上的大图与缩略图却还是旧的——看着就是「编辑不生效」。

现在这一半收在 `ThumbSourceMixin`（`desktop/modules/thumb_source.py`），
由 `StepModulePage.__init__` 收尾时调 `_wire_source_edit()` 接上
（⚠️ 用 `getattr` 探测而不是直接调用：`base.py` **不 import** thumb_source，
守住"只依赖共享底座"）。查看器的 `image_saved` 信号到手后做三件事：

1. **立即上屏**：`apply_edited_image(path, image)`（`ImageViewerWidget` 有）；
   没这个通道的控件（`RembgPreviewWidget`）退到 `refresh_page()` 按新文件重载；
2. **重渲缩略图缓存**：交 `ImageThumbCacheWorker` 渲那一张，渲好只刷这一条
   （`set_cached_thumb` / `reload_thumb`）；
3. **写一句「什么时候生效」**：`edit_effect_note(path)`，各步骤按自己的下游覆盖
   （提取页说"检测、去底色读的就是这张图"，去底色页分"源图"与"结果"两种说法，
   PDF排版 页说"重新点生成PDF 即用上"）。

⚠️ **必须"忘掉旧缓存记忆"**：缓存文件名带**文件大小**（`book_key`），编辑一改
字节数就换了键；若查看器还记着旧键那条路径，刷新出来的是**覆盖前**那张缓存
（左栏一直是旧图）。`ImageViewerWidget.reload_thumb()` 会先 pop 掉
`_thumb_cache_ready[path]` 再重取——这是"编辑生效"在左栏的关键一步。
护栏：`tests/selftests/module_edit_sync.py`（同尺寸换色 / 换尺寸 / 同键 mtime
三条路都验，并直接读左栏条目图标的像素）。

**拼图独立页的四条入口**（2026-10-03 补齐）：`ImpositionViewWidget` 一直有
`item_preview_requested` / `spread_preview_requested` / `item_edit_requested` /
`spread_edit_requested` 四条信号，但**独立页没接线**——画布右键菜单弹得出来、
双击也发信号，点了什么都不会发生。现在按任务流程的同一套语义接上：

- 双击图上 / 空白 = 预览这张原图 / 整页左右组合（弹窗**只读**，不给 `edit_path`）；
- 右键「编辑图片」= 不经弹窗直达编辑器：单张 → 覆盖源图 + `canvas.invalidate_image`
  + 重渲左列缩略图；整页组合 → 合成全分辨率 → 编辑 → 存
  `singletask/拼图/edited/<页>.png` 并把 `page["edited_file"]` 记进文档；
  导出时 `_compose_job` 在 `compose_doc` 之上**按页盖回**这张图
  （独立页没有任务流程那种 `stages/imposition` 落点，缓存区就是它的等价物）。
  版面一改（`_on_items_changed` / 复位 / 删图）就作废该页手改记录。
  ⚠️ `_page_overrides()` 的过滤口径必须与 `compose_doc` 一致（同样过
  `normalize_page`），否则一页坏数据会让后面所有页的手改**错位到别人身上**。

**「整幅大输入区」怎么来的**：`ModulePage._build_input()` 返回 `SourceZone` 时，
它会插在页头与左右分栏之间、横跨整幅宽度；页面同时在 `_build_control()` 里
把**同一块控件**交给 `StepControl(zone=...)`（`StepControl` 因此不重复摆一块）。
`ModulePage` 还把**整页拖拽**转发给它——拖到页面空白处也算拖进输入区。

**初始只显示输入框**（用户 2026-10-03）：`ModulePage.__init__` 收尾时调
`show_workspace(False)`，把左右分栏与日志区一起隐藏——页面上只剩页头与
大输入区。用户在「源变了」的回调里调 `sync_workspace_visible(source)`
（有源就展开、清空就收回），`show_workspace` 同时把输入区切进
`SourceZone.set_solo_mode(True)` 独占模式。

⚠️ **独占模式靠 sizePolicy 长高，不靠固定高度**：`SourceZone._sync_height()`
在独占且空态时给 `setMinimumHeight(SOLO_HEIGHT)` + `setMaximumHeight(HEIGHT_UNLIMITED)`
+ 纵向 `Expanding`。⚠️ **只改 minimumHeight 是不够的**——曾经先
`setFixedHeight(320)`（它同时钉死 maximumHeight），后来改成"最小 320 + 可拉伸"
却忘了放开上限，控件就永远长不大：整页只有一条 320px 的框、上下各留一片空白
（靠截图发现，断言全绿时根本看不出来）。Qt 的 `QWIDGETSIZE_MAX` 在 PySide6
里**没有导出**，所以用 `source_zone.HEIGHT_UNLIMITED` 这个哨兵值。

⚠️ **`HEIGHT_UNLIMITED` 必须等于 `(1 << 24) - 1`，不能写 `1 << 24`**（用户
2026-10-03 报「单独拼板界面报错」）：Qt 的硬上限 `QWIDGETSIZE_MAX` 就是
`(1 << 24) - 1 == 16777215`，哨兵超了 1 之后 `setMaximumHeight` 会往 stderr 打
`QWidget::setMaximumSize: The largest allowed size is (16777215,16777215)`
并把值截断回去。功能上无害（截断后正是我们要的"不设上限"），但拼版独立页
初始就是独占模式，每次进页面都刷这条警告，看着像报错。

⚠️ **`_ModuleHeader` 钉成纵向 `Maximum`**（双保险）：页头默认 Preferred 会长大，
一旦输入区走了固定高度，空出来的纵向空间就会被摊给页头——副标题飘到页面
正中、输入框被挤到底边。实测只留输入区的拉伸策略时当前布局已正确，这行是
防"将来输入区不再撑满"时退化。

⚠️ **`SourceZone` 内部有一层子控件**：外框/图标/文案/清空 ✕ 是 `paintEvent`
自绘的，但「选择文件 / 选择文件夹 / 更换」是真正的 `PushButton`（它们要 hover、
按下、焦点态，自绘等于重写一遍交互还写不好）。几何由
`SourceZone._relayout_buttons()` 手工摆（已选态右端一枚），空态则由
`_empty_block_top()` 统一算：**文案 + 按钮作为一整块垂直居中**，按钮顶边 =
`_empty_block_bottom() + BUTTON_GAP`（⚠️ 两者必须共用同一个基准，否则独占模式
下"文案贴顶、按钮钉在框底"，中间一大片空白像两个不相干的区域——用户 2026-10-03
截图反馈）。`_content_rect()` 只负责给整块留上下呼吸空间。加新按钮记得同步
`_build_buttons()`、`_relayout_buttons()`、`_paint_filled()` 的右侧留白与 `__all__`。

⚠️ **「选择文件夹」按钮按 `accepts_dir` 摆**：不接受目录的步骤不摆它（摆一个
注定被拒的入口是骗人），但「选择文件」照常在——那才是它唯一的合法入口。
「图片提取」就是这一档（`accepts_dir=False`，**PDF 只支持文件**，用户 2026-10-03）。

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
  一个子目录（否则大家的 `1.jpg` 会互相覆盖）。
  ⚠️ **同名要分两种情况**（用户 2026-10-03 报）：**内容相同** = 同一个 PDF
  重跑产生的副本 → 当成同一份，搬上去、嵌套壳清掉；**内容不同** = 真冲突 →
  整个嵌套树保留，绝不覆盖用户已有文件。
  ⚠️ 少了第一条会怎样：同一个 PDF 跑两遍，根目录已有上一轮平铺的同名文件 →
  每次都判"冲突"→ 嵌套壳**永久保留** → 输出目录躺着两套（实测 192 + 192），
  而预览页用 `rglob` 收图 ⇒ **每页出现两次**（用户截图里两个 `1.jpg`）。
  双保险：`extract` 模块页改用 `collect_result_images()`（同名只收一份、
  顶层优先），即便目录里已经有历史残留也**显示正常**——去重只影响显示，
  **不删用户的产物**。
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

⚠️ **`inputs` / `outputs` 是 BPM 端口**：声明（如 extract 的 `("pdf",)` →
`("pages",)`）已经**接线**——`steps/ports.py` 的三张表（`PORT_ARTIFACTS` /
`STAGE_LOCATIONS` / `SUPPLIERS`）是任务流程的连线唯一事实来源，
`store.artifact()` / `store.stage_input()` 都走它（见上文「端口与连线」）。
"换流程顺序只改 `SUPPLIERS` 一张表"。

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
  ui.json               # 全局界面状态（last_task + source_hash：上次进入的任务；⚠️ 启动不再自动跳回）
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
      detect/           # 检测预览缩略图
      print/            # 输出 PDF 预览缩略图（print 成功后重建）
      imposition/       # 拼板左列缩略图（⚠️ 只在这里，禁止写 singletask/）
    stages/
      extract/          # 提取图片（1.jpg…，直接平铺）
      rembg/            # 去底色整页结果（1.png…）
      imposition/       # 拼版成品（可选拼版节点启用时）
      print/print.pdf
  singletask/<key>/     # 独立任务缓存区（与 tasks/ 各归各，禁止借道，见 2.3）
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
