# gujitools 项目长期记忆（2026-10-02 精简版）

> 古籍重製：**PDF → 提取图片 → 检测文本框 → 去底色 → 生成 PDF**。
> 双入口共用同一套算法：`cli.py`（打包名 `guji`）/ `desktop.py`（PySide6 + qfluentwidgets）。
> 分层 `utils ← core ← {cli, functions, desktop}`（严格单向）。工作分支 **`stitch`**。
> ⚠️ `docs/**` 基准是 `main`；本分支新增能力（图片编辑器、颜色选择器、模块页、变换笼…）**以代码为准**。

## 1. 单一事实来源（别另写一份，漂移必出 bug）

- CLI 参数表 → `core/command_spec.py`；桌面表单默认值 → `desktop/components/panels/params_spec.py`
- 色值/间距/圆角/字号 → `desktop/ui/theme.py`（状态→颜色文案 `theme.status_colors/label`）
- **area/border 几何 + 检测框槽位约定 → `utils/box_geometry.py`**：
  - 半幅恒 2 槽 `[左,右]` / 整幅恒 1 槽 `[整幅]`，**下游靠槽数分辨形态**。
  - 唯一实现 `page_box_slots`：对象侧 `PageBoxes.slots()`、事件侧 `page_box_slots_from_event(payload)`；
    人工画框转槽位走 `half_slots`。**别按"还剩几个框"推类型**。
  - 检测框绘制 → `utils/box_draw.py`；打印排版 → `utils/page_layout.py`；页序 → `utils/sort_utils.pdf_custom_sort_key`
- JSON 读写 → `desktop/store/json_io.py`（临时文件 + `os.replace` 原子落盘）
- **步骤清单 → `desktop/steps/spec.py::SPECS`（唯一来源）**：`STAGES`/`STAGE_LABELS`/`STAGE_SHORT`/
  `MODULES`/`PANEL_CLASSES`/`FLOW_STAGES`/`OPTIONAL_STEPS`/`NAV_STEPS` **全部由它派生**。
  加一步 = 加一条 spec；`role`（主链/可选）与 `nav`（有无独立模块页）**正交**；
  文案按**界面面**逐个建字段（`title`/`subtitle`/`nav_tooltip`/`stage_title`/`short`），**别合并**。

## 2. 硬规则

- **绝对导入**，不用 `from .x`；取项目根用 `desktop.utils.files.project_root()`（禁 `Path(__file__).parents[N]`）。
- **跨层 import 白名单**（`tests/selftests/layering.py`）：`core→utils`、`cli→{utils,core}`、
  `functions→{utils,core}`、`desktop→{utils,core}`。**`desktop→functions` 违规**（函数内延迟导入合规）。
- ⚠️ **GUI 主进程不许被拖进重依赖**：实测 `import functions.detect` 会带进 **cv2**。
  主进程要用的纯规则**必须放 utils**，且**不许 import functions**（`box_geometry` 有 AST 级守卫）。
- 检测只有一份实现：`functions.detect.detect_page_content`（**不得**直调 `utils.yolo_utils`）。
- 中文路径不许直接 `cv2.imread/imwrite`，用 `utils.image_io`。
- 界面：基础控件 `paintEvent` 自绘、不引样式表；下拉框 `widgets.combo_box()`，单独按钮设 `CONTROL_HEIGHT`。
  窗口尺寸用 `desktop/ui/window_size.apply_window_size`（不写死 `resize()`；主窗口**默认最大化**）。
- 跨线程：用 `desktop.workers.connect_queued`；`signal.connect(lambda)` 是直接连接会碰 widget。
- **通用事件通道**：`StepKernel.event` / `StepControl.event` 透传**非 progress/log** 的 reporter 事件
  （detect 报 `page_boxes` 靠它）。内核不认识事件名，只原样转发。
- ⚠️ **禁止 AI 自动 git 提交**：改完只汇报，等用户明确说「提交」。

## 3. 关键契约

- **第四步取图 = 第三步「提交本次任务」的成品图**（用户 2026-10-01 定）。编辑去底色结果 / 改 area/border
  → **必须重新提交**才进 PDF。`_build_print_effects` 只做整图透传；`plan_print_effects`/`_base_label` 已删。
- **五个独立模块页** `desktop/modules/<key>/`（`PAGE` 约定）+ 共用步骤层 `desktop/steps/`
  （`spec`/`kernel`/`control`/`source_zone`/`process`）；主链四步 + 拼版**全部** `nav=True`。
  detect 页交付物 = `<输出目录>/boxes.json`，与 `tasks/<id>/boxes.json` **逐字段一致**。

## 4. 进程模型与存储

- 主进程**不加载** cv2/torch/PyMuPDF；每阶段一个 worker 子进程，stdout 走 **JSON Lines**
  （`started/progress/log/page_boxes/page_size/finished/error/cancelled`）。
- 进度/坐标由 `core.reporter.Reporter` 结构化上报（desktop 注入 `JsonLinesReporter`），**不再正则解析中文提示**。
- 数据根 `~/Documents/guji`，**纯 JSON 无数据库**：`tasks.json`、`ui.json`、
  `tasks/<0001>/{pages,runs,boxes,sizes,print,drafts,thumbnails,stages/*}`。

## 5. 测试与工具

- GUI 自测：`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE <py> -u tests/gui_selftest.py --only <模块>`
- ⚠️ **解释器一律加 `-u`**：不带时部分模块在 **Qt 拆解期以退出码 127** 结束并吞掉块缓冲 stdout
  → 0 字节、被误判"失败"。**127 是伪错误码**；判成败看输出有没有 `全部 N 项断言通过`。
- ⚠️ **别用 `--only` 逐模块循环跑全量**（每个模块连带重跑整条依赖链）。一次全量 + `--skip` 跳过
  环境性失败：`extract`（QProcess `FailedToStart`）、`docs_layout`（`guji.spec` 生成物）、
  `config_template`/`defaults_single_source`（缺 `static/guji.yaml`）、`detect_shared`（缺 `ultralytics`）、
  `print` 链（本机 **fpdf 1.7.2** 而非 fpdf2）。
- **GUI 全绿 ≠ CLI 没坏**：动 `functions/`、`utils/` 时必跑 `tests/reporter_cli_parity.py`、
  `reporter_worker_e2e.py`、`cli_print_smoke.py`。
- 文档同步：`tools/gen_api_docs.py`（`--check` 校验）、`tools/check_docs.py`；视觉自查 `tests/gui_shot.py`。
- **本机解释器**：`C:\Users\zunkun\anaconda3\python.exe`（managed 3.13 **没装 PySide6**）。

## 6. 高频踩坑

- `--clean`：CLI 默认 False 但 `FunctionBase.execute()` 兜底 **True** —— 自建参数字典**必须显式给 `clean`**。
- `rembg` 输出固定 **PNG**；第三步「提交产物」是**白底透明 PNG**，透明必须**在合成之后**加。
- `print` 只能 `guji run print`；页序以 `files` 清单为准，为空才回退文件名排序。
- 整幅页（`fullcontent`）：框原样下传，area=1/2/3 结果一致，**只有 area=4 保留框外内容**。
- 高分屏：**绝不**手动 `painter.scale(dpr, dpr)`；dpr 改动用 `QT_SCALE_FACTOR=1.5` **真进程**验。
- 手册页：`os.startfile` 只传**原生路径**（别传 `file:///`）；手册 HTML **不加 `<base>`**。
- **校验 import 别用文本匹配**：用 AST（`tests/selftests/_context.py::imported_modules`）。
- `.gitignore:44` **裸模式 `guji.yaml`** 会匹配任意层级 → 误伤模板 `static/guji.yaml`（**从未进 git**），
  而 `functions/init.py` 读它当模板 ⇒ `guji init` 在本机也是坏的。修法应为 `/guji.yaml`（**未改**）。
- 旧记忆留下 3 处死引用（纯文本，`check_docs.py` 抓不到）：`utils/pdf_extract.py` docstring、
  `docs/api/utils.md`、`docs/dev/gui/readme.md`。

## 7. 构建

- `python build.py`（**11~15 分钟**，开头**直接删** `dist/`、`build/`）。往 `requirements.txt` 加包
  **必须同步加进 `install_build_dependencies()` 的开头探针**，否则 yolobuild 永远装不上。
  别往 `excludes` 加 `torch.*`（会让 `guji crop` ModuleNotFoundError）。
- 手册：`python build.py --manual-only`（~2.5 分钟）；打包后自检 `tools/check_bloat.py`、`tools/smoke_frozen.py`。

## 8. 文档地图

用法/参数 → `README.md`、`docs/guide/*`；GUI 架构/进程模型 → `docs/dev/gui/gui-architecture.md`；
Worker 协议/JSON/area → `gui-technical-spec.md`；**改界面必读** → `gui-ui-system.md`；
路径规则 → `docs/dev/io_path_rules.md`；算法 → `docs/dev/utils.md`；
命令手册 → `docs/functions/*.md`（**位置固定不可移动**）；函数签名 → `docs/api/*.md`（**自动生成禁手改**）。
