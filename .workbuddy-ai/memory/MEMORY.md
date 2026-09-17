# gujitools 项目长期约定

> 细节已拆出，按需读：
> - `memory/gui-notes.md` — 截图闭环、缩略图、列表几何、手册 HTML、GUI 交互必知点
> - `memory/commands-notes.md` — 命令全景、detect、配置模板、接线清单、实测备忘

## 架构分层

依赖严格单向：`utils ← core ← {cli, functions, desktop}`；三个上层**不得交叉引用**。
- `functions/` 只依赖 `ArgsProvider` 协议。
- `cli/command_args.py`、`cli/init_args.py` 是 deprecated shim，新代码用 `core.args`。
- `core/command_spec.py` 是参数**默认值/枚举/校验的唯一事实来源**（`COMMAND_SPECS`、
  `PRINT_DEFAULTS`、`PRINT_FORM_DEFAULTS`）。新增命令/参数**只登记一次**，cli 与 desktop 自动共享。
- 打包：`guji.spec` 需 `collect_submodules` 覆盖新增顶层包（已含 core）。

## 结构化事件通道（替代「文案即契约」）

`core.reporter.Reporter`（runtime_checkable）：`progress(done,total)` / `event(name,**payload)` / `log(msg)`。
`NULL_REPORTER` 空实现，`normalize_reporter(None)` 返回它，**调用点永不判空**；CLI 不注入 → 输出与历史一致。
事件名常量 `EVENT_PROGRESS`/`EVENT_PAGE_BOXES`/`EVENT_PAGE_SIZE`，新增先登记。

- 接线：`FunctionBase.__init__(command_args, reporter=None)`，子类同步透传；
  `get_function(..., reporter=None)` 自动转发。
- desktop：`JsonLinesReporter` 写 JSON Lines；**每个阶段执行器都必须重定向 stdout**
  （ultralytics 裸 print 会破坏协议），写法见 `generic_stage.run_stage`。
- ⚠️ `finished` 事件不带 `done/total`，`runner.py` 用 `self._last_progress` 补齐。

## 只有一份实现的共享逻辑

- **几何**：`utils/box_geometry` 的 `build_output_layout()`/`build_symmetric_layout()`
  返回冻结 dataclass，上层**只渲染不推导**（`symmetric` 必须显式传）。
- **输出目录**：一律调 `utils.path_utils.resolve_final_output_dir`
  （唯一例外 `get_extract_output_root`，extract 输出落在输入目录**内部**）。
  路径断言要带负向条件。
- **纯函数下沉**：`utils/color_utils.py`、`utils/margin_utils.py`（非法输入抛 ValueError）。
- ⚠️ `utils/__init__.py` 六个公开别名不可删（`collect_image_files` / `is_valid_image_size` /
  `IMAGE_EXTS` / `natural_sort_key` / `get_extract_output_root` / `resolve_final_output_dir`）；
  pyflakes 报「imported but unused」是**预期噪音**。

## 关键约定

1. **⚠️ None 默认值陷阱**：默认值可能是 `None` 时，`args.get(key, fallback)` 兜底**永不生效**，
   必须 `args.get(key) or fallback`。None-默认键见 commands-notes.md。
2. `clean` 默认值恒 `False`（命令行/GUI/FunctionBase 三处一致）。
3. `write_json` 返回 bool，父目录缺失时静默放弃。
4. GUI 阶段执行也会 `validate()`（避免「界面放过、命令行拒绝」）。
5. GUI 专属 `_` 前缀参数（`_outpath`/`_effects`/`_preview_run_id`）是跨层传参，勿随意更名。

### ⚠️ 限制放入口层，不放共享校验层

判据：**某入口的取舍**（→ 该入口自己的层，如 `cli.cli._reject_dry_run`，提示给可执行的替代方案）
vs **业务客观约束**（→ `core/command_spec` validators）。
`functions/` 是可复用库层，保持宽松（被 crop/cropremove 当中间步骤调用时必须可用）。
元断言注意：写「校验器不得依赖 X」的测试要**剥掉 docstring 只查函数体**。

## 文档目录按「读者」划分

口诀：**「照着做」进 guide/，「为什么这么实现」进 dev/。**
`docs/guide/`（使用者）、`docs/dev/`（开发者，含 desktop 6 份技术文档）、
`docs/functions/`（**位置固定**：`guji help` 运行时读它）、`docs/api/`（自动生成）。

⚠️ `docs/functions/` **不能移动** —— `utils/help.py` 运行时读它，移动后只有**打包后**跑
`guji help` 才暴露。护栏 `tests/selftests/docs_layout.py`（19 断言）。
迁移经验：`git mv` 对未跟踪文件失败；**改路径字面量后必须 grep 整个文件**（同一文件可能两处）。

## 验证方式

- 全量 GUI 自测：`QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py`
  （`--only a,b` / `--list` / `--skip`）
- CLI 输出一致性 `tests/reporter_cli_parity.py`；worker 端到端 `tests/reporter_worker_e2e.py`
- **解释器用 `C:\Users\liuzu\anaconda3\python`**（系统 python 缺 cv2/numpy/PySide6）
- 静态 `python -m pyflakes core/ cli/ functions/ utils/`；分层检查（无反向依赖）
- 文档：`python tools/gen_api_docs.py`（改公开 API 后必跑，`--check`）+ `tools/check_docs.py`

**⚠️ 写行为测试的坑**：
1. 比 stdout 时**路径必须相同**；2. **行序不可比**（线程池竞速），比集合；
3. 耗时数字归一化；4. `tests/selftests/` 动态发现，新增用例 = 新增 .py（声明 `NAME`/`TITLE`/`DEPENDS`）；
5. **负向测试前必须备份未跟踪文件**（对 untracked 文件 `git checkout --` 是 no-op）。

**环境坑**：Git Bash `/tmp` ≠ Python `/tmp`（win32），用
`C:\Users\liuzu\AppData\Local\Temp\...`；Windows Python 要 `D:/workspace/...` 而非 `/d/...`。

## 已知未处理

- `desktop/` 仍有一批 pyflakes 噪音（未用导入等），不影响运行。
- `functions` 层人类日志仍走 print（将来可搬到 `reporter.log()`）。
- `guji init` 缺 `--yes` 非交互开关。
