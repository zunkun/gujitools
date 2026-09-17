# gujitools 项目长期约定

> 细节已拆出，按需读：
> - `memory/gui-notes.md` — 截图闭环、缩略图、列表几何、GUI 交互必知点
> - `memory/commands-notes.md` — 命令全景、detect、配置模板、接线清单、实测备忘

## 架构分层

依赖严格单向，禁止反向引用：`utils ← core ← {cli, functions, desktop}`

- `utils/` 纯工具（图像/PDF/YOLO/路径），无内部依赖。
- `core/` 中立共享层，只依赖标准库与 utils，放「两个入口都需要且语义必须一致」的东西。
- `cli/` / `functions/` / `desktop/` 三个上层，彼此不得交叉引用。
- `functions/` 只依赖 `ArgsProvider` 协议，不依赖具体参数容器类。
- `cli/command_args.py`、`cli/init_args.py` 是 deprecated shim，新代码用 `core.args`。

**core/ 职责**：`core/command_spec.py` 是命令参数**默认值/枚举/校验的唯一事实来源**
（`COMMAND_SPECS`、`PRINT_DEFAULTS`、`PRINT_FORM_DEFAULTS`；`normalize_margin`/`parse_color`
委托 utils；`validate_color_fields` 非法色**不静默降级为黑**）。**新增命令或参数只登记
一次**，cli 与 desktop 自动共享。另有 `core/args.py`（`ArgsProvider`/`CommandArgs`/`InitArgs`）、
`core/result.py`（`StageStatus` + 退出码互转）、`core/reporter.py`（事件通道）。

## 结构化事件通道（替代「文案即契约」）

**背景**：`functions` 曾 28 处 print 混着「给人看的日志」与「给程序读的信号」，
desktop 跑正则从中文提示里捞后者——改一句文案就静默断掉 GUI 进度条。

`core.reporter.Reporter`（runtime_checkable）：`progress(done,total)` / `event(name,**payload)` / `log(msg)`。
`NULL_REPORTER` 空实现，`normalize_reporter(None)` 返回它，调用点**永不判空**；
CLI 不注入 → 输出与历史逐字一致。`CallbackReporter(sink)` 供测试。
事件名常量 `EVENT_PROGRESS`/`EVENT_PAGE_BOXES`/`EVENT_PAGE_SIZE`，**新增先在此登记**。
`progress_total` 是「引擎先给总数」的内部名，被归一化为 `done=0` 的 progress。

**接线**：`FunctionBase.__init__(command_args, reporter=None)` → `normalize_reporter`；
子类同样加 `reporter=None` 并透传；`functions/__init__.get_function(..., reporter=None)`
自动转发；utils 层需上报时也加 `reporter=None`。

- desktop 侧 `desktop/stages/events.py` 的 `JsonLinesReporter` 直接写 JSON Lines；
  `ProgressStream` 已削成**纯日志转发器（无正则）**，`interceptor.done/total` 恒 0（仅兼容）。
- **⚠️ 每个阶段执行器都必须重定向 stdout**：第三方库（ultralytics）裸 print 会混进
  JSON Lines 破坏协议。写法见 `generic_stage.run_stage`：`sys.stdout = ProgressStream(...)`
  → 主体 → `finally` 还原 + `if interceptor.buffer.strip(): interceptor._consume(...)`。
- **⚠️ `finished` 事件不带 `done/total`**：`runner.py` 用 `self._last_progress`
  在 `store.finish_stage()` 时补齐。
- 兼容残留 `[boxes]`/`[imgsize]` 两行文本在 functions 侧保留供核验，worker 已不解析。

## 只有一份实现的共享逻辑

- **几何（`utils/box_geometry` 布局层）**：CLI 与 GUI 曾各实现一遍、两处硬编码
  `SYMMETRIC_GAP_MM = 10`，漂移后产出真实 bug。现 `build_output_layout()`/
  `build_symmetric_layout()` 返回冻结 dataclass，上层**只做渲染**（CLI numpy / GUI QImage），
  禁止再推导几何；**`symmetric` 必须显式传**，布局层不猜。
- **输出目录（`utils.path_utils.resolve_final_output_dir`）**：同类 bug 已两次——
  只要某处自己拼路径，规则必然漂移。**一律调它**：无 `-o` → `input.parent/subdir`；
  纯名字 → `input.parent/name/subdir`；含分隔符 → 绝对化后接 `subdir`。
  **唯一例外 `get_extract_output_root`**（extract 用，输出落在输入目录**内部**）。
  **路径断言必须带负向条件**（同时 `== work.parent/"detect"` 且 `!= work/"detect"`）。
- **纯函数下沉**：`utils/color_utils.py`（`parse_color`/`format_color`，非法输入**抛
  ValueError**）、`utils/margin_utils.py`（`normalize_margin`/`format_margin`）。
  两个及以上上层要用 → 下沉 utils，上层委托，不要各自重复实现。
- **⚠️ `utils/__init__.py` 六个公开别名不可删**：`collect_image_files`、
  `is_valid_image_size`、`IMAGE_EXTS`、`natural_sort_key`、`get_extract_output_root`、
  `resolve_final_output_dir`。pyflakes 报「imported but unused」是**预期噪音**。
  曾误删 → GUI detect 静默失败（`module 'utils' has no attribute ...`）。

## 关键约定

1. **⚠️ None 默认值陷阱（最易踩）**：默认值可能是 `None` 时，`args.get(key, fallback)`
   的兜底**永不生效**（`CommandArgs` 总会注入该键）。必须 `args.get(key) or fallback`。
   None-默认键：extract(pages/start/end)、crop/rembg/cropremove(border)、
   print(pdf_name/left_page_margins/right_page_margins/title_switch_nodes/
   page_number_end_page/skip_pages/files)。
2. **`clean` 默认值恒 `False`**（命令行/GUI/FunctionBase 三处一致），缺省绝不 rmtree 输出目录。
3. **`write_json` 返回 bool**，父目录缺失时静默放弃而非抛异常。
4. **GUI 阶段执行也会 `validate()`**（`generic_stage.run_stage` 内），避免「界面放过、命令行拒绝」。
5. **GUI 专属 `_` 前缀参数**（`_outpath`/`_effects`/`_preview_run_id`）是跨层传参，
   `print_params.EXCLUDED_KEYS` 与 `history.py` 会过滤，勿随意更名。
6. **打包**：`guji.spec` 需 `collect_submodules` 覆盖新增顶层包（已含 core）。

### ⚠️ 限制放入口层，不放共享校验层

**教训**：「命令行 detect 不带 `--save` 就拒绝」写进 `CommandArgs.validate()` 是**错的**——
那是 CLI/GUI 共用层，会把 GUI detect 阶段（本就不落盘，坐标走事件通道）一起拦死。

判据：**是「某入口的取舍」还是「业务的客观约束」？** 前者放该入口自己的层
（如 `cli.cli._reject_dry_run` 谓词，顺手验证拒绝路径无磁盘副作用，提示给**可执行的
替代方案**）；后者放 `core/command_spec` validators（`area ∈ {1,2,3}`、ext 枚举、颜色可解析）。
`functions/` 是**可复用库层，保持宽松**——被 crop/cropremove 当中间步骤调用时必须可用。

**元断言注意**：写「校验器不得依赖 X」的测试要**剥掉 docstring 只查函数体**
（文档往往正在解释「为什么不在这里做」），用 `ast.parse` 过滤 `ast.Expr/ast.Constant`。

## 文档目录按「读者」划分（2026-09-17 重整）

**规则：`docs/` 按读者分，不按模块分。** 口诀：**「照着做」进 guide/，「为什么这么实现」进 dev/。**

```
docs/
├── guide/      使用者：gui-guide.md、cli.md、readme.md、screenshots/
├── dev/        开发者：gui/（6 份技术文档）、io_path_rules.md、utils.md、readme.md
├── functions/  ⚠️ 位置固定：guji help 的运行时文档来源
└── api/        自动生成产物
```

桌面端 6 份技术文档（architecture/technical-spec/design/layout/requirements/ui-system）
全属 dev，只有 `gui-guide.md` 属 guide。

**⚠️ 硬约束：`docs/functions/` 不能移动** —— `utils/help.py:182` 运行时读它，
`guji.spec` 已打包；移动后代码不报错，只有**打包后**跑 `guji help` 才暴露
（静默退化成 `No help available for this topic`）。
护栏 `tests/selftests/docs_layout.py`（19 断言）：三类目录各司其职、旧 `docs/gui/`
已清理、**`docs/guide/` 不得混入技术文档**、7 个 help 主题手册存在、`help.py` 常量仍指
`docs/functions`、`_DOC_MAP` 全覆盖、`guji.spec` 打包了它，且**行为断言真调
`get_help_text()` 确认没退化**。已反向验证（改路径 / 移走 detect.md 都能变红）。

**迁移经验**：`git mv` 对未跟踪文件失败（先 `cp`）；目录被占用 `mv` 报 Permission
denied（改 `cp -r` + `rm -rf`）；迁完扫全库相对链接（当时 54 处断链）。
**改路径字面量后必须 grep 整个文件**——同一文件可能有两处相同字面量（曾漏改一处）。

## 验证方式

- 全量 GUI 自测：`QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py`（**409 断言**）
  - `--only reporter,box_geometry` / `--list` / `--skip`
- CLI 输出一致性 `tests/reporter_cli_parity.py`；worker 端到端 `tests/reporter_worker_e2e.py`
- **解释器用 `C:\Users\liuzu\anaconda3\python`**（系统 python 缺 cv2/numpy/PySide6）
- 静态检查 `python -m pyflakes core/ cli/ functions/ utils/`
- 分层检查：`utils/` 无反向依赖、`core/` 无上层引用、`functions/` 无 cli/desktop 引用
- 文档：`python tools/gen_api_docs.py`（改公开 API 后必跑，`--check` 校验）+ `tools/check_docs.py`

**⚠️ 写行为测试的坑（踩过多次假失败）**：
1. 比对 stdout 时**路径必须相同**（否则「输出目录：…」天然不同）；
2. **行序不可比**（`处理完成: x` 由 `ThreadPoolExecutor.as_completed` 竞速决定），比集合；
3. **耗时数字要归一化**；
4. `tests/selftests/` 由运行器动态发现，**新增用例 = 新增 .py**，声明 `NAME`/`TITLE`/`DEPENDS`；
5. **负向测试前必须备份未跟踪文件**（先 `cp` 到 Temp 再 `sed` 注入）——
   对 **untracked** 文件 `git checkout --` 是 **no-op**，会污染后续全量自测。

**环境坑**：Git Bash `/tmp` ≠ Python `/tmp`（win32）——临时目录用
`C:\Users\liuzu\AppData\Local\Temp\...`；`/d/workspace/...` Windows Python 不认，用 `D:/workspace/...`。

## 已知未处理

- `desktop/` 仍有一批 pyflakes 噪音（未用导入、`ui/widgets.py` 未用局部变量、
  若干测试模块未用局部变量）。不影响运行。
- `functions` 层人类日志仍走 print（经 ProgressStream 转发为 log 事件）；
  将来可把高频日志搬到 `reporter.log()`。
- `guji init` 缺 `--yes` 非交互开关（见 commands-notes.md）。
