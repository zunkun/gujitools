# 全仓架构：入口、分层与两种页面形态

> 本文是**全仓视角**的架构总览（CLI + 桌面端一起讲）。桌面端内部的模块树、
> 数据区、编辑生效链等细节见 [`gui-architecture.md`](gui/gui-architecture.md)；
> 给 AI 的快速上手入口在仓库根 [`AGENTS.md`](../../AGENTS.md)。

## 1. 全景图

```
                 ┌──────────────┐        ┌──────────────┐
   用户操作      │  desktop.py  │        │    cli.py    │   脚本/批处理
                 │  (PySide6)   │        │  (argparse)  │
                 └──────┬───────┘        └──────┬───────┘
                        │  desktop/             │  cli/
                        │  界面 + 编排 + worker  │  参数解析 + 调用
                        └──────────┬────────────┘
                                   ▼
                    ┌──────────────────────────┐
                    │  functions/（功能实现）    │  extract / detect / crop /
                    │  CLI 与 GUI 共用的唯一实现 │  rembg / cropremove / print
                    └──────────┬───────────────┘
                               ▼
              core/（命令定义、reporter）＋ utils/（纯算法）
```

- **一套算法，两个入口**：`functions/` 是图像与 PDF 处理的唯一实现，CLI 直接调它，
  桌面端的 worker 子进程也跑同一份代码——因此两边对同一输入的处理结果完全一致。
- **分层严格单向**：`utils ← core ← {cli, functions, desktop}`；`desktop` 不 import
  `cli`，`cli` 不 import `desktop`。白名单与例外见 `tests/selftests/architecture/layering.py`。
- **进程模型**：桌面端主进程只做界面；所有重活（YOLO 推理、批量处理）在独立
  worker 子进程里跑。打包环境下 worker 以 `guji-desktop.exe --worker --config …`
  启动自身（`desktop.py` 负责路由），不需要额外可执行文件。

## 2. 桌面端的两种页面形态

桌面端一个窗口里并存两种形态（左侧导航切换，壳层 `desktop/shell.py`）：

### 任务流程 taskdetail（`desktop/pages/taskdetail/`）

- 用户先在任务列表页导入 PDF/DjVu（建任务，得任务号 `0001…`），进入详情页后沿
  **固定四步**推进：提取图片 → 检测文本框 → 图片去底色 →（可选拼版）→ PDF排版；
- 它的核心职责是**编排**：步骤顺序、上一步产物作为下一步输入、跨步骤联动
  （改了去底色参数 → 第四步产物过期）、历史参数回填、每步产物存进任务目录；
- 一切数据落在 `~/Documents/guji/tasks/<任务号>/`（纯 JSON，无数据库），
  删除任务即删目录。

### 独立任务 singletask（`desktop/modules/<key>/`）

- 把流程中的一步**拆出来**的独立功能页：PDF/DjVu提取 / 检测文本框 / 图片去底色 /
  PDF排版 / 图片拼版，共 5 个（数量由 spec 派生，别写死）；
- **没有任务上下文**：不建任务、不进任务目录，选个文件/目录就能跑；
  产物默认落在源文件旁（`<源名>_提取/`、`<源名>_去底/`…）；
- 它的存在有两个原因：① 临时处理一两张图/一本小册子不值得建任务；
  ② 它验证了「一步 = 输入 + 输出 + 参数」这个最小单元——这正是未来 BPM
  流程引擎里单步执行器的雏形。

### 两者的关系（契约）

| 维度     | 关系                                                                                                                                                                                                                            |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 共用     | 渲染组件（`components/viewers/`，含编辑生效原语 `viewers/edit_sync.py`）、参数面板（`components/panels/`）、检测框人工干预交互（`components/box_kinds.py`）、执行内核（`steps/kernel.py`）、worker（`workers/`）、日志/进度组件 |
| 不共用   | **数据**：任务目录 `tasks/<id>/` 与独立页缓存 `singletask/<key>/` 各归各，**互不相通、禁止借道**                                                                                                                                |
| 代码方向 | taskdetail 不 import `desktop.modules`；模块页不 import `desktop.pages`（导航壳层除外）                                                                                                                                         |

singletask 与 taskdetail 功能相似是**设计结果**而非耦合：同一批公共组件 +
同一条 `SPECS` 元数据，分别在两种宿主里实例化。改公共组件两边同时受益；
改某一侧的编排/接线不会影响另一侧。

## 3. 公共组件契约：只有「输入 + 输出 + 参数」

这是本仓库最重要的解耦决策，为 BPM 流程化预留：

- **执行内核**唯一认识 `StepRequest(source, dest, args)`
  （`desktop/steps/kernel.py:StepRequest`）：source 是输入（文件或目录），
  dest 是输出目录，args 是参数字典。内核不知道"任务"为何物。
- **参数面板**契约只有 `get_args() / apply_args() / reset_to_default()`
  （`desktop/components/panels/base.py`）：面板不关心自己被谁宿主。
- **步骤元数据**全部在 `desktop/steps/spec.py::SPECS`：一条 spec 声明一个步骤的
  命令名、文案、文件过滤、输出规则、`role`（进不进主流程）、`nav`（进不进左侧
  导航）。`STAGES`（流程步骤表）、`NAV_STEPS → MODULES`（导航注册表）、
  `PANEL_CLASSES`（面板注册表）都从它派生——**新增一步 = 加一条 spec + 写一个
  job**，两种宿主同时长出这一步。
- **连线**：taskdetail 的「哪步的产物喂哪步」是 `desktop/steps/ports.py::SUPPLIERS`
  （BPM 的边表，含落点表 `STAGE_LOCATIONS`——评估后保留在 ports，三张表同属一个
  BPM 连线故事）；singletask 没有连线（一步即全部）。

组件层因此**不得出现任何宿主专属概念**。已知的宿主特有 UI 都通过构造参数声明，
例如拼版面板的「在流程中启用图片拼版」开关（决定第四步取图来源，任务流程专属）：
`ImpositionPanel(enable_switch=False)` 由独立拼图页传入。

## 4. 数据与缓存布局

根目录 `~/Documents/guji/`（`desktop/utils/files.py::guji_data_dir`）：

```
guji/
├── tasks/                     ← 任务流程专区（taskdetail）
│   └── <任务号>/
│       ├── <书名>.pdf           源副本
│       ├── stages/<stage>/      各步骤产物（落点表：steps/ports.py STAGE_LOCATIONS）
│       ├── thumbnails/          缩略图缓存：source / print / imposition / detect
│       ├── drafts/<stage>.json  拼版等交互草稿
│       ├── preview/rembg[~节点]/ 去底色实时调整草稿（不进下游）
│       ├── boxes.json           检测框（detect 页交付格式与独立页一致）
│       ├── runs/                历史执行记录
│       └── ui.json              上次停留的步骤等界面状态
└── singletask/                ← 独立任务专区（singletask）
    └── <key>/                   key = StepSpec.disk_key()（路由键，非界面文案）
        ├── thumbnails/           PDF 页缩略图（按书分目录，防跨书撞页号）
        ├── thumbs/               图片源缩略图（<边长>/<book_key>.jpg）
        └── …                     只放缓存不放产物；产物在源文件旁
```

- 两棵子树**互不引用**。taskdetail 的缓存随「删除任务」整体删除；
  singletask 的缓存独立生命周期。
- 缩略图键含文件大小（编辑换尺寸即换键）、边长进目录名——规则在
  `desktop/utils/files.py`，别在调用处自算。

### 4.1 后台任务的两条硬约束

1. **拼版页缩略图只生成"看得见的那几页"**（`components/imposition/page_thumb.py`
   的 `PageThumbManager.set_window_provider` + `page_list.viewport_changed`）：
   进入拼版页时只交当前可见窗口（±3 页）给 worker，窗口外的页留在队列里，
   用户滚动/翻页时再补。**不要改回"整本一次排满"**——那会和整本成品合成抢
   同一个进程的 GIL，实测把缩略图从 24ms/页 拖到 4~7 秒/页。
2. **GUI 进程装在 Job Object 里**（`utils/proc_job.py`，`desktop/app.py::main`
   开头装配）：本进程一退出（正常关、崩溃、被强杀），系统把子进程一并终止，
   不留孤儿（现场踩过：崩溃后 9 个子进程、约 550MB 残留）。
   ⚠️ 要**活过父进程**的子进程（更新安装器、设置里的「重启程序」）必须用
   `proc_job.detached_creationflags()` 申请脱离作业，否则会被一起收走。

### 4.2 崩溃取证（原生崩溃的现场）

生产版曾反复在 `Qt6Gui.dll+0xe0130`（`QScreen::geometry` 首指令）崩，而 Windows
自带的 WER `LocalDumps` 在这台机器上实测**不落盘**（探针验证过，不是配置错）。
所以现场由程序自己留，三件产物全落在 `~/Documents/guji/logs/`：

```
logs/
├── crash.log                    常驻日志：面包屑 + faulthandler + excepthook + Qt 消息
├── crash_log_<时间>_pid<pid>.log 超过 2MB 时归档旧日志（保留历史、不覆盖）
├── crash_<时间>_pid<pid>.txt    崩溃报告：异常码/出错地址/寄存器/调用链候选/日志尾部
└── crash_<时间>_pid<pid>.dmp    minidump（可用 WinDbg/VS 打开看真栈）
```

- 三个模块分工：`utils/crash_log.py`（日志 + `faulthandler`，管 Python 栈）、
  `utils/crash_dump.py`（`SetUnhandledExceptionFilter` + `MiniDumpWriteDump`，
  管原生现场）、`desktop/ui/qt_log.py`（`qInstallMessageHandler` 把 Qt 警告
  也接进同一份日志）。
- ⚠️ **安装顺序硬约束**：先 `install_crash_log()`（抢 `faulthandler`），再
  `install_crash_dump()`（过滤器末尾回调上一个过滤器）。反过来的话原生过滤器
  会先接管异常，Python 栈就没了。入口在 `desktop/app.py::_install_crash_forensics`，
  位置是 `QApplication` 构造之后、`kill_children_on_exit` 之前。
- ⚠️ 崩溃取证**不许 import Qt**、不许在异常处理里再抛异常：它自己炸了就彻底
  没有现场了。所有步骤都 try/except 兜住，失败只打印。
- 面包屑只在"用户动作/阶段切换"这类粗粒度节点上打（切步骤、切页、选图弹窗、
  开始合成、缩略图批次），一条是一次 IO——别放进渲染循环里。
- 栈扫描是按 `rsp` 往上找"落在模块地址区间内的值"再换算成 `模块+偏移`，
  是**启发式候选**而非真栈回溯；`dmp` 才是准的。栈只按 1KB 分块读（整段读会
  因为越过栈顶而整段失败，看起来像"没有调用链"）。

### 4.3 卡死取证（进程活着、界面不动）

闪退那三件套救不了**卡死**：进程活着、窗口没响应，`faulthandler` / 原生过滤器
都不触发，用户只能强杀，现场全丢（2026-11-21 用户报「拼版卡死」时，`crash.log`
末尾只剩「拼版切页」一条面包屑，无从查起）。

办法是**心跳 + 外部线程**（`utils/crash_log.py::StallWatchdog`）：

- 主线程挂一个 `QTimer` 调 `beat()` 更新时间戳；另一个 daemon 线程盯着它，
  超过 `STALL_THRESHOLD_MS`（默认 3000ms，环境变量 `GUJI_STALL_THRESHOLD_MS`
  可覆盖）没更新就把**所有** Python 线程的栈写进同一份 `crash.log`，前缀
  `[stall]`：

```
22:29:05.462 [stall-watchdog:82a0] [stall] 主线程卡顿：已 3.1s 没有心跳（阈值 3.0s，第 1 次）
--- 主线程 ---
  File ".../desktop/pages/taskdetail/imposition_layout.py", line 812, in _compose_imposition_async
--- 看门狗线程 ---
  ...
22:29:06.978 [stall-watchdog:82a0] [stall] 主线程恢复：这次卡了 4.6s（判定阈值 3.0s）
```

- ⚠️ 心跳必须挂在**主线程**的事件循环上：后台 worker 打心跳等于没盯住。
  心跳间隔必须小于阈值，否则空闲时必误报。
- 主线程卡在**不放 GIL** 的 C 调用里（PIL 编码、cv2、Qt 的部分 C++ 调用）时，
  看门狗线程自己也会被饿死；日志会记下"自身被饿死 X s"，并说明这份栈多半
  已随主线程恢复而前移，只当参考。
- 同一进程最多写 `STALL_MAX_REPORTS`（20）份栈，滚动卡顿不会刷爆日志。
- 入口同上：`_install_crash_forensics(app)` 里 `install_stall_watchdog()` +
  `QTimer(app)` 打心跳；`uninstall()` 会**先停看门狗再关流**。

## 5. 测试地图

- 运行器：`tests/gui_selftest.py`（offscreen），`--only` 选模块自动补依赖、
  `--list` 列出全部。**按改动范围分档跑**，不要每次全量。
- 守护契约的自测：
  - `selftests/architecture/layering.py` — 分层白名单（含「desktop 不 import cli」）；
  - `selftests/ui/modules_shell.py` — 导航注册表 = `NAV_STEPS` 派生、模块惰性构造；
  - `selftests/flow/step_ports/` — BPM 端口：spec 声明的 inputs/outputs 与落点一致；
  - `selftests/printing/imposition/` — 拼版全链，含**缓存边界断言**（拼版缩略图必须写
    进 `tasks/<id>/thumbnails/imposition/`，不许借道 singletask）；
  - `selftests/printing/imposition_thumb_window.py` — 缩略图"只生成可见页"+ 合成让路；
  - `selftests/safety/proc_job.py` — 作业对象：父进程被硬杀后子进程必须跟着退出；
  - `selftests/safety/crash_forensics.py` — 崩溃取证：日志/面包屑/excepthook 链、Qt 消息、
    真 AV 崩溃产生**报告 + minidump + Python 栈**三件套、安装顺序静态契约；
  - `selftests/architecture/params_spec.py` — 面板默认值单一来源。
- CLI 侧契约：`tests/reporter/reporter_cli_parity.py` 等（改 progress 事件协议前先看它）。

## 6. 演进方向：BPM 流程化

「公共组件只有输入 + 输出」这条契约服务的终局是：**用同一批组件与步骤元数据，
由流程定义（而非硬编码的 taskdetail）声明任意处理链**：

- `SPECS` 已经是「步骤库」：每步自带参数面板、执行 job、输入输出声明；
- `ports.SUPPLIERS` 已经是显式的边表（BPM 的边），换流程顺序/换连线只改它；
- singletask 证明了每一步可以脱离任务上下文独立运行——这就是 BPM 单步执行器；
- taskdetail 未来的角色收敛为「一个内置的默认流程定义」。

**M1 已落地（2026-10-05）**：`desktop/steps/flow.py` 把上述形态变成了运行时载体
——`FlowDefinition.default()` 从 ports 静态表**派生**默认流程（不另写一份连线），
序列化成 BPMN 2.0 兼容子集；建任务时落到 `tasks/<任务号>/flow.bpmn`，
`TaskStore.stage_input` 按**本任务的流程定义**解析输入（文件缺失/写坏回落默认）。
自定义流程 = 换一份 `flow.bpmn` 文件，算法、落点、界面代码不动（自测：
`tests/selftests/flow/flow_bpm/`）。条件连线（拼版生效 → print 换上游）用
`guji:condition` 属性表达。后续：详情页按 BPMN 节点渲染 → 创建任务弹窗 →
拖拽编辑画布（见 `docs/tasks/bpm.md`）。

新代码请顺着这个方向写：把知识放进 spec/ports/组件参数，而不是写死在某侧页面里。
