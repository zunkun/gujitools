# 测试与验收规范

> 本文是全仓测试的**规范层**：怎么分层、用例怎么写、什么必须测、什么时候跑什么、
> 什么算"做完"。运行器机制见 `tests/gui_selftest.py` 文件头；本文只定规矩。

## 1. 分层测试策略（金字塔）

| 层 | 测什么 | 速度 | 依赖 | 典型模块 |
|---|---|---|---|---|
| L0 架构守卫 | 分层方向、单一事实来源不漂移、文档/注册点一致 | 秒级、静态 | 无 Qt/子进程 | `layering`、`defaults_drift`、`command_registry`、`params_spec`、`docs_layout` |
| L1 纯函数 | 几何/排序/算法数学 | 快 | 无 Qt | `box_geometry`、`page_order`、`print_number_format` |
| L2 控件接线 | 「按钮摆出来没、点下去接没接线」——用户交互层 | 中 | offscreen Qt，**不起子进程** | `detect_module_page`、`flow_ui`、`image_context_menu` |
| L3 端到端 | 从入口跑到产物落盘（GUI worker 子进程 / CLI `subprocess`） | 慢 | 子进程/模型/重依赖 | `extract`、`detect`、`rembg`、`cli_run`、`print_rect_pdf_e2e` |

**强制规则**：

1. 每个功能域**至少**有 L2 覆盖——"相关代码存在"不算覆盖，"按钮点得动、点了走到对的地方"才算。
2. 有 CLI 入口的功能必须有 L3 CLI 端到端（`cli_run`），有 GUI 流程的必须有 L3 worker 端到端。
3. L0 守卫是"改了就必红"的安全网：新增 CLI 参数、新增步骤、改默认值时，必须确认对应守卫模块
   （`command_registry` / `defaults_drift` / `params_spec`）的断言天然覆盖，否则补断言。
4. 探针脚本（`tests/probe_*.py`）只允许两类：**视觉截图工具**（与 `bpm_shot.py` 同类）和
   **一次性排查记录**（用完可删）。凡是"判据适合自动化"的探针，**必须转正**为 selftest——
   留在 probe 里等于没有回归保护。

## 2. 用例组织规范（`tests/selftests/` 动态发现契约）

- **一个功能域一个文件**。运行器扫描目录发现用例，新增用例 = 新增文件，不改运行器。
- 文件头四件套（缺一不可）：

  ```python
  # -*- coding: utf-8 -*-
  """<守护什么>（<为什么>）。⚠️ 必须写明是否起子进程/需要哪些重依赖——
  沙箱环境 QProcess 起不来，后来人靠这句话决定跑不跑。"""
  from __future__ import annotations
  NAME = "..."          # 与文件名一致
  DEPENDS: list[str] = [...]   # 只声明"共享夹具依赖"（要用 ctx.tid 就依赖创建者）
  TITLE = "..."         # 中文一句话
  def run(ctx) -> None: ...
  ```

- `TEARDOWN = True` 只给**销毁共享夹具**的清场模块（如 `task_delete`）；运行器自动排最后。
- 断言一律走 `tests/selftests/_context.py::ok(name, cond, detail)`；失败信息必须带
  "差在哪"的细节（实际值 vs 期望值），不许只说"不对"。
- **断言必须会红**（双向验证）：新写的行为断言，先想清楚"这个 bug 发生时它为什么红"；
  测"接线生效"就真点（`QTest.mouseClick`），不查 `childAt()` 猜坐标。
- 共享夹具（`ctx.tid` / `ctx.injected_boxes` / …）按依赖链传递；不在自己模块里造第二份。
- 临时数据只落 `tests/tmp/`（`tests/tmpdir.py::install()`，worker 子进程也覆盖）；
  临时脚本落 `_scratch/`，**收工删净**。仓库根不许出现 `_xxx.py` / `_xxx.log`。

## 3. 测试代码规范

- 与生产代码同一分层约束：`tests/` 也遵守 `utils ← core ← functions ← desktop/cli`，
  不许测试代码自己绕层（`layering` 不扫 tests，但规矩不豁免）。
- 不许用固定 `sleep` 等异步结果——用 `wait_until` / `pump` / `wait_worker`。
- 不许真弹模态（离屏环境挂死）；模态路径用替身（`silence_source_prompt` 模式）。
- 端到端 CLI 用 `subprocess.run([sys.executable, "cli.py", ...])`（打包语义等价 `guji`），
  断退出码 + 断产物文件；YOLO 类命令前先探 `import torch`，模型不可用时打印 SKIP 并继续
  （跳过必须**显式可见**，不许静默）。
- 涉及 `functions/` 协议的改动，跑 `tests/reporter_cli_parity.py` / `reporter_worker_e2e.py`。
- 用例内不写 `git` / 不动任务目录以外的用户数据。

## 4. 架构规范（与测试强相关的那部分）

- **单一事实来源**：CLI 参数 `core/command_spec.py`、桌面默认值
  `desktop/components/panels/params_spec.py`、步骤元数据 `desktop/steps/spec.py::SPECS`。
  任何"第二份手写清单"都是 bug 温床——发现即报警，测试里同样不许复制这些清单，
  要断言就从真源派生（参照 `command_registry` 的写法）。
- **GUI 主进程不进重依赖**（cv2/torch）：重活走 worker 子进程；测试如果需要重依赖，
  必须把"import 放在 run() 函数体内"并写明，让不需要它的模块不受连坐。
- **公共组件只认「输入目录 + 输出目录」**：singletask 与 taskdetail 数据不相通、缓存各归各，
  跨域借道的回归由 `modules_shell` / `step_ports` / `layering` 守卫。
- `QThread.run()` / worker 协议变更必须 try/except 与协议双跑（见 §3 最后一条）。

## 5. 功能域覆盖责任表（谁必须有什么测试）

| 功能域 | 必备覆盖 | 现有模块（部分列举） |
|---|---|---|
| CLI extract | L0 参数 + L3 端到端 | `arg_types`、`extract_dpi`、`cli_run` |
| CLI crop / cropremove | L0 + L1 几何 + L3 端到端（area=4 免模型 + 有模型时 area=1/3） | `box_geometry`、`whole_page`、`audit_round2`、`cli_run` |
| CLI rembg | L0 + L3 端到端 + 目录安全 | `output_dir_safety`、`defaults_drift`、`cli_run` |
| CLI print | L0 + L3 端到端（yaml 配置） | `print_rect_pdf_e2e`、`cli_run` |
| 任务流程编辑(BPM) | L1 模型 + L2 渲染/编辑 + 校验 | `flow_bpm`、`flow_ui`、`flow_validate`、`detail_bpm_render` |
| 图片提取 | L3 worker + L2 交互 | `extract`、`extract_preview`、`history`、`resume` |
| 检测文本框 | L3 YOLO + L2 手绘/框类型/统计 | `detect`、`detect_boxes`、`detect_stats`、`detect_edit` |
| 图片去底色 | L3 + L2 实时预览/透明产物 | `rembg`、`rembg_live`、`rembg_transparent` |
| 拼版 | L1 版面 + L2 弹窗/画布 | `imposition`、`print_doc_rect_roundtrip` |
| PDF 排版生成 | L3 PDF + L2 编辑器 | `print_stage`、`print_rect_pdf_e2e`、`print_layout_editor` 等 16 个 |
| image 预览 | L2 右键/缩放 + DPR | `preview_zoom`、`image_context_menu`、`preview_dpr` |
| singletask 各独立页 | 每页一个 `<key>_module_page`（L2 接线+产物落点） | `detect_module_page`、`extract_module_page`、`print_module_page`、`rembg_module_thumbs`、`module_progress` |
| image edit | L1 数学 + L2 画布交互 + 存回 | `image_editor`、`image_editor_saveback`、`module_edit_sync` |

**新增功能时**：先在上表登记功能域 → 决定必备层级 → 落模块 → 才算功能完成（见 §7）。

## 6. 测试计划（改什么 → 跑什么）

| 改动 | 必跑 |
|---|---|
| `utils/**`（纯算法） | L1 相关模块 + `layering` |
| `core/**`（spec/参数） | `command_registry`、`arg_types`、`defaults_drift`、`params_spec`、`audit_round2` |
| `functions/**`（功能实现） | 该命令的 L3 端到端 + `reporter_cli_parity` / `reporter_worker_e2e` + `layering` |
| `cli/**` 或 `cli.py` | `cli_run`（全命令冒烟）+ §6 对应 functions 行 |
| `desktop/steps/**`（BPM/调度） | `flow_bpm`、`flow_validate`、`detail_bpm_render`、`scheduler` 相关 |
| `desktop/pages/**` | 该页面域的 L2 模块 + `pages`、`detail_structure` |
| `desktop/modules/**`（singletask） | `modules_shell`、`steps_components`、对应 `<key>_module_page` |
| `desktop/components/viewers/**`（编辑器/预览） | `image_editor`、`image_editor_saveback`、`module_edit_sync`、`preview_zoom` |
| 攒批收尾 / 提交前 | 全量（本机）或受限集合（见下） |

**运行方式**：

```bash
QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE python -u tests/gui_selftest.py --only <模块1[,2]>   # 解释器：C:/Users/liuzu/anaconda3/python.exe
QT_QPA_PLATFORM=offscreen python -u tests/gui_selftest.py                # 全量
python tests/gui_selftest.py --list                                     # 计划核对
```

- **沙箱受限集合**：本机 shell 的 QProcess 起不来（`ERROR_PIPE_BUSY`，环境问题非代码问题），
  真起 worker 子进程的模块会红。此时跑 `--skip` 掉子进程类模块的集合 + `cli_run`
  （CLI 走 `subprocess.run`，不受影响）。
- 退出码 127 是 `QThread: Destroyed` 伪错误，且会吃掉其后模块：**必须**比对
  `--list` 计划数与日志中 `==` 标题数，缺了用 `--only` 补跑。
- 测试耗时，**不要每改一小处就跑**：按改动攒批，收尾统一跑。

## 7. 验收规范（Definition of Done）

一个功能（或修复）算"验收通过"，必须同时满足：

1. **功能代码**在正确的层（§4 分层），不违反单一事实来源。
2. **行为断言**存在且会红：至少一条 L2（"按钮点得动、接线到对的地方"），
   有 CLI/产物语义的加 L3（"真跑一次、产物落盘正确"）。
3. §5 责任表里该功能域的**存量模块仍全绿**（回归不破）。
4. 文档同步：改了参数/步骤/用法 → `docs/functions/`、`docs/guide/`、API 文档
   （`python tools/gen_api_docs.py --check`）+ `python tools/check_docs.py` 全过。
5. 现场干净：`git status --short` 无 `??` 临时文件；`_scratch/` 删净；`tests/tmp/` 不进仓库。
6. **不自动 `git commit`**——汇报 status/diff，等用户明示。
