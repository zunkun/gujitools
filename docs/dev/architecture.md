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
  `cli`，`cli` 不 import `desktop`。白名单与例外见 `tests/selftests/layering.py`。
- **进程模型**：桌面端主进程只做界面；所有重活（YOLO 推理、批量处理）在独立
  worker 子进程里跑。打包环境下 worker 以 `guji-desktop.exe --worker --config …`
  启动自身（`desktop.py` 负责路由），不需要额外可执行文件。

## 2. 桌面端的两种页面形态

桌面端一个窗口里并存两种形态（左侧导航切换，壳层 `desktop/shell.py`）：

### 任务流程 taskdetail（`desktop/pages/taskdetail/`）

- 用户先在任务列表页导入 PDF（建任务，得任务号 `0001…`），进入详情页后沿
  **固定四步**推进：提取图片 → 检测文本框 → 图片去底色 →（可选拼版）→ 生成 PDF；
- 它的核心职责是**编排**：步骤顺序、上一步产物作为下一步输入、跨步骤联动
  （改了去底色参数 → 第四步产物过期）、历史参数回填、每步产物存进任务目录；
- 一切数据落在 `~/Documents/guji/tasks/<任务号>/`（纯 JSON，无数据库），
  删除任务即删目录。

### 独立任务 singletask（`desktop/modules/<key>/`）

- 把流程中的一步**拆出来**的独立功能页：PDF图片提取 / 检测文本框 / 图片去底色 /
  生成PDF / 图片拼板，共 5 个（数量由 spec 派生，别写死）；
- **没有任务上下文**：不建任务、不进任务目录，选个文件/目录就能跑；
  产物默认落在源文件旁（`<源名>_提取/`、`<源名>_去底/`…）；
- 它的存在有两个原因：① 临时处理一两张图/一本小册子不值得建任务；
  ② 它验证了「一步 = 输入 + 输出 + 参数」这个最小单元——这正是未来 BPM
  流程引擎里单步执行器的雏形。

### 两者的关系（契约）

| 维度 | 关系 |
| --- | --- |
| 共用 | 渲染组件（`components/viewers/`，含编辑生效原语 `viewers/edit_sync.py`）、参数面板（`components/panels/`）、检测框人工干预交互（`components/box_kinds.py`）、执行内核（`steps/kernel.py`）、worker（`workers/`）、日志/进度组件 |
| 不共用 | **数据**：任务目录 `tasks/<id>/` 与独立页缓存 `singletask/<key>/` 各归各，**互不相通、禁止借道** |
| 代码方向 | taskdetail 不 import `desktop.modules`；模块页不 import `desktop.pages`（导航壳层除外） |

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

## 5. 测试地图

- 运行器：`tests/gui_selftest.py`（offscreen），`--only` 选模块自动补依赖、
  `--list` 列出全部。**按改动范围分档跑**，不要每次全量。
- 守护契约的自测：
  - `selftests/layering.py` — 分层白名单（含「desktop 不 import cli」）；
  - `selftests/modules_shell.py` — 导航注册表 = `NAV_STEPS` 派生、模块惰性构造；
  - `selftests/step_ports.py` — BPM 端口：spec 声明的 inputs/outputs 与落点一致；
  - `selftests/imposition.py` — 拼版全链，含**缓存边界断言**（拼板缩略图必须写
    进 `tasks/<id>/thumbnails/imposition/`，不许借道 singletask）；
  - `selftests/params_spec.py` — 面板默认值单一来源。
- CLI 侧契约：`tests/reporter_cli_parity.py` 等（改 progress 事件协议前先看它）。

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
`tests/selftests/flow_bpm.py`）。条件连线（拼版生效 → print 换上游）用
`guji:condition` 属性表达。后续：详情页按 BPMN 节点渲染 → 创建任务弹窗 →
拖拽编辑画布（见 `docs/tasks/bpm.md`）。

新代码请顺着这个方向写：把知识放进 spec/ports/组件参数，而不是写死在某侧页面里。
