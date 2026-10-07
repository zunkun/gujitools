# 模块化与可扩展性重构设计

> 目标：**解耦、模块化、可扩展**。本文只做设计与迁移规划，动手前先过一遍。
> 数据来自对当前代码的一次体检（2026-09-18），不是凭印象列的清单。

## 1. 现状体检

### 1.1 分层是健康的（好消息，别推翻重来）

模块级跨层引用 **0 违规**，依赖严格单向：

```text
utils ← core ← {cli, functions, desktop}
```

- `utils`/`core` 内部**无循环引用**。
- 体检脚本最初报出的 3 处「违规」（`desktop/stages/*` → `cli` / `functions`）
  复查后确认都是**函数内延迟导入**，不是启动期耦合，见 §3.C。

结论：**不需要改分层，只需要收口散落的清单与过大的文件。**

### 1.2 扩展点成本：新增一个命令要改 6 个生产文件

命令名成组出现（疑似各抄一份清单）的生产文件：

| 文件 | 清单形态 | 与 `COMMAND_SPECS` 的关系 |
| --- | --- | --- |
| `core/command_spec.py` | `COMMAND_SPECS`（6 个） | **设计上的唯一事实来源** |
| `cli/cli_args.py` | 6 个子命令 parser | 各写一份 |
| `functions/__init__.py` | `_COMMAND_MAP`（6 个） | 各写一份 |
| `functions/init.py` | 6 段初始化 | 各写一份 |
| `utils/help.py` | 6 段帮助文本 | 各写一份 |
| `desktop/store/tasks.py` | `STAGES`（**4 个**） | 子集，见下 |
| `desktop/pages/taskdetail/{page,runner}.py` | 4 个阶段 | 子集 |
| `desktop/components/panels/params_spec.py` | `DEFAULTS`（4 个） | 子集 |

⚠️ `STAGES` 只有 4 个（extract/detect/rembg/print），比 6 个命令少——
GUI 流程不含 `crop`/`cropremove`。这是**合理的「步骤不同」**，不是漂移，
但目前没有哪份代码表达「它是 `COMMAND_SPECS` 的子集」这层关系。

### 1.3 文件规模

| 行数 | 文件 | 性质 |
| --- | --- | --- |
| 759 | `utils/pdf_utils.py` | **两种职责混装**（见 §3.B） |
| 612 | `desktop/ui/widgets.py` | 控件杂货铺 |
| 584 | `desktop/components/panels/print_form.py` | 单个 Mixin 过大 |
| 560 | `utils/page_layout.py` | 已分节，**建议不动** |
| 468 | `desktop/pages/taskdetail/runner.py` | 阶段执行编排 |
| 423 | `desktop/pages/tasklist/page.py` | 列表页 |

### 1.4 间接层冗余（顺手清掉）

`utils/pdf_utils.py` 里的 `parse_margins()` / `parse_color()` **已经是委托壳**
（分别转发 `utils.margin_utils.normalize_margin` 与 `utils.color_utils.parse_color`），
但 `functions/print.py` 仍绕道 `pdf_utils` 取用。同一份逻辑有三个入口：

```text
utils/color_utils.parse_color      ← 真身
core/command_spec.parse_color      ← 委托（core 层复用，合理）
utils/pdf_utils.parse_color        ← 又一层委托（冗余）
```

---

## 2. 设计原则

1. **不动分层**：`utils ← core ← {cli, functions, desktop}` 继续有效。
2. **不让 core 反向知道上层**：`COMMAND_SPECS` **不**写 `("functions.extract",
   "ExtractFunction")` 这类实现坐标——那会让 core 语义上依赖 functions 的内部结构。
3. **用守卫替代强集中**：清单留在各自的层里，但加断言钉住「与 `COMMAND_SPECS`
   一致」。漏改的地方**会红**，比"记得改 6 处"可靠，也符合本项目已有的守卫风格。
4. **每步可独立验收**：任何一步做完都能跑完 §5 的回归判据，不留半成品。

---

## 3. 重构项

### A. 注册点收敛（用守卫，不是硬集中）

**不改结构，只加一致性断言**——放在 `tests/selftests/command_registry.py`（新模块）。

| 守卫 | 判据 |
| --- | --- |
| 工厂覆盖 | `set(_COMMAND_MAP) == set(COMMAND_SPECS)` |
| CLI 子命令 | `set(run 的 subcommand) == set(COMMAND_SPECS)` |
| 帮助文本 | 每个命令在 `utils/help.py` 里有条目 |
| GUI 阶段是子集 | `set(STAGES) ⊆ set(COMMAND_SPECS)`，且 `params_spec.DEFAULTS` 的键 `⊇ STAGES` |

外加一条**元守卫**：确认 `COMMAND_SPECS` 至少 N 个命令（防止表被清空后所有
「==」断言同义反复地全绿）。

⚠️ 双向验证要做「反向」：往 `_COMMAND_MAP` 里塞一个 `COMMAND_SPECS` 里没有的
命令，确认守卫真的会红（`set` 相等断言容易写成恒真）。

### B. 大文件拆分

**`utils/pdf_utils.py` → 两个模块**（职责本来就是两件事）：

| 新模块 | 收什么 |
| --- | --- |
| `utils/pdf_extract.py` | PDF → 图片：`parse_pages`、`validate_page_range`、`calculate_zoom`、`render_zoom`、`report_image_size`、`process_page_batch`、`render_pages_parallel`、`extract_pdf_optimized`、`run_on_input_directory` 及其私有 helper |
| `utils/pdf_draw.py` | 生成 PDF 的绘制辅助：`register_fonts`、`draw_vertical_text`、`get_page_side_from_name`、`get_page_side_by_start` |

`utils/pdf_utils.py` 保留为**兼容 re-export 壳**（`__all__` 不变），
外部 import 无需改动，等所有调用点迁完再考虑删壳。

**`desktop/ui/widgets.py`**：把 `SegmentedToggle`（349–519，171 行）先独立成
`desktop/ui/segmented_toggle.py`；其余控件按「基础 / 复合」分组留在原文件。
`widgets.py` 继续 re-export，调用点不动。

**`print_form.py` 的 `PrintFormMixin`**（584 行，一个类）：按依赖从少到多拆成
四层（**已落地**，见 §7）：

| 文件 | 类 | 收什么 | 依赖 |
| --- | --- | --- | --- |
| `print_text_layout.py` | `PrintTextLayoutMixin` | 「位置/文字方向」固定取值 | `self._fixed_layout_echo` |
| `print_inset.py` | `PrintInsetMixin` | 「距页边」控件组（造/取值/回填/释义） | `self._add_row`、`_title_inset` / `_page_number_inset` |
| `print_sections.py` | `PrintSectionsMixin` | 五个分区的控件 | 上面的 + `_section` / `_line_edit` / `_color_row` / `_sync_enabled` |
| `print_form.py` | `PrintFormMixin` | 编排（`build_form`）+ 通用控件工厂 + 节点行 | 全部 |

MRO：`PrintPanel → PrintFormMixin → PrintSectionsMixin → PrintInsetMixin →
PrintTextLayoutMixin → StagePanel`。⚠️ 这是唯一**有回归风险**的拆分：Mixin
之间靠 `self._xxx` 共享状态，拆之前必须先把读写点列全（用 AST 扫
`self.X` 的读/写行号，并标出「本类调用但没有定义」的方法）。

**`utils/page_layout.py`**：**建议不动**。它已经是分节清晰的结构，
且是 `functions/print.py` 与 desktop 预览共用的唯一事实来源——
拆成多文件只会让"改纸张/边距算法"的落点变模糊。

### C. stages 依赖倒置（低成本，先做）

`desktop/stages/generic_stage.py` 函数内：

```python
from cli.command_args import CommandArgs      # ← 换成 core.args
```

`cli/command_args.py` 本身是 **deprecated shim**（新代码用 `core.args`）。
改成 `from core.args import CommandArgs` 就**直接消掉对 cli 的依赖**，零风险。

`desktop/stages/detect_stage.py` 函数内 `from functions.detect import
detect_page_content` 是**有意的算法复用**（GUI 检测阶段要跑与 CLI 完全相同的检测），
下沉到 core 不合适（算法属业务层）。处置：保留，但集中到
`desktop/stages/registry.py` 并登记为「已知的跨层复用点」，加注释说明原因，
避免后来人以为是疏漏。

### D. 间接层清理

`functions/print.py` 改用 `utils.margin_utils` / `utils.color_utils` 直接取用；
`utils/pdf_utils.parse_margins` / `parse_color` 标记为待废弃。
⚠️ 注意 `pdf_utils.parse_margins` 的 default 是 `DEFAULT_PAGE_MARGINS`，
直接换底层调用时**别丢了这个 default**。

---

## 4. 迁移顺序

按「风险从低到高」，每步独立提交：

1. **C**（改一行 import + 抽出 registry 注释）—— 零风险
2. **A**（只加守卫，不动生产代码）—— 零风险，且立刻锁住现状
3. **D**（换 import 来源）—— 低风险，自测覆盖
4. **B 之 pdf_utils 拆分**（有 re-export 壳兜底）—— 低风险
5. **B 之 ui/widgets 拆分**（有 re-export 壳兜底）—— 低风险
6. **B 之 print_form Mixin 拆分** —— **中风险，最后做**，且要先列全共享状态

---

## 5. 回归判据（每步都要过）

```bash
# 1. 全量 GUI 自测（当前基线 894/894）
QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE \
  C:/Users/liuzu/anaconda3/envs/py310/python.exe -u tests/gui_selftest.py

# 2. CLI 侧两条链路
python -u tests/reporter_cli_parity.py     # CLI stdout 文案不变
python -u tests/reporter_worker_e2e.py     # worker 子进程 JSON Lines 协议
python -u tests/cli_print_smoke.py         # 真跑一次 guji run print

# 3. 文档工具
python tools/gen_api_docs.py --check
python tools/check_docs.py

# 4. 静态检查：不得新增 pyflakes 条目
python -m pyflakes core/ cli/ functions/ utils/ desktop/
```

⚠️ **GUI 自测全绿 ≠ CLI 没坏**。本轮六步跑完时 GUI 894 全绿，但
`tests/cli_print_smoke.py` 一跑就抓到真问题：`functions/print.py` 在 D 步骤
换了 margin/color 的 import 之后，**仍从 `utils.pdf_utils` 壳里取
`register_fonts` / `draw_vertical_text`**——GUI 侧根本走不到这条路径。
动了 CLI 与 GUI 共用的代码（`functions/`、`utils/`）时，第 2 组必须跑。

⚠️ 拆 `utils/` 下任何模块后，**必须重跑 `gen_api_docs.py`**（`--check` 会点名
`docs/api/utils.md`）。

⚠️ 新增/移动公开函数后，`tests/selftests/docs_layout.py` 与
`tests/selftests/api_docs.py`（若存在）也要过。

## 6. 验收标准

- 新增一个命令时，**只需改 `core/command_spec.py` 一处**，其余清单漏改会红；
- `utils/` 与 `desktop/ui/` 下无 600 行以上的文件；
- `desktop/` 不再出现对 `cli` 的任何引用（含函数内）；
- 全量自测、文档工具、pyflakes 三项相对基线无退化。

---

## 7. 落地结果

全部六步已完成，自测 **871 → 892**（新增 21 条，都是守卫，不是行为改动）。

| 步骤 | 动作 | 新增守卫 |
| --- | --- | --- |
| C | `stages/` 改从 `core.args` 取 `CommandArgs`；`detect_stage` 的跨层复用加注释登记 | — |
| A | 注册点一致性 | `tests/selftests/command_registry.py`（10 项） |
| D | `functions/print.py` 直连 `utils.margin_utils` / `utils.color_utils`；顺手修掉过时硬编码兜底 18/12 | — |
| B1 | `utils/pdf_utils.py` → `pdf_extract.py` + `pdf_draw.py`，原文件留 re-export 壳 | — |
| B2 | `desktop/ui/widgets.py` → `fonts.py` + `segmented_toggle.py`，原文件 `__all__` re-export | — |
| B3 | `print_form.py` 拆四层 Mixin | `tests/selftests/print_form_split.py`（6 项） |
| B1 收尾 | 生产代码全部直连 `pdf_extract` / `pdf_draw`，不再走 `pdf_utils` 壳 | `tests/selftests/deprecated_shim.py`（2 项）+ `tests/cli_print_smoke.py` |

### 7.1 print_form 拆分的三条不变量

`tests/selftests/print_form_split.py` 用 AST 钉住：

1. 每个成员仍在**指定的那个类**里（改落点必须同步改守卫里的 `_EXPECTED_HOME`）；
2. 四个类之间**无同名成员**——同名会被 MRO 静默遮蔽，等于偷偷改了行为；
3. Mixin 调本类没有的 `self.X` 必须**登记在 `_CROSS_DEPS` 白名单**里。

⚠️ 双向验证的坑（踩过两次）：

* 注入必须**行为等价**（复制一个纯静态 helper、或加一个永不被调用的方法）。
  注入成"程序崩溃"只能证明代码坏了，**证明不了守卫会红**——因为崩溃发生在
  `ctx.prepare()`，断言根本跑不到。
* 别往方法体**中间**插行：那里常有元组拆包（`cross_key, cross_label = ...`），
  插进去就是 `SyntaxError`，同样是死在 import 阶段。

## 8. 后续解耦路线图（2026-10-04 起）

§7 之前的模块化已落地；本节记录**下一阶段**的解耦项，按风险从低到高排列。
背景契约（用户 2026-10-04 口径，写代码前先读）：

> 公共组件只有**输入目录 + 输出目录**，这样后期 BPM 流程可以定义各种流程出来，
> singletask 也就能拆出来作为独立的任务处理。singletask 与 taskdetail 除了功能
> 相似、共用渲染组件与参数面板外**没有任何关系**——singletask 是 taskdetail 中
> 一步拆出来的独立功能，数据不相通。

| # | 解耦项 | 现状 | 做法 | 风险 |
| --- | --- | --- | --- | --- |
| 1 | ✅ **toast 工厂合一**（2026-10-04 已做） | `TaskDetailPage._toast` 与 `ModulePage.toast` 逐字重复 | 收进 `desktop/ui/toast.py::show_toast`，两侧转发 | 低 |
| 2 | ✅ **拼版面板「流程启用」开关参数化**（2026-10-04 已做） | 公共面板 `ImpositionPanel` 底部内置 taskdetail 专属的「在流程中启用图片拼版」复选框，独立拼图页构造后"伸手"隐藏 | `ImpositionPanel(enable_switch=False)` 构造时声明；契约钉进 `tests/selftests/imposition.py` | 低 |
| 3 | ✅ **壳层搬出 `desktop/modules/`**（2026-10-04 已做） | `modules/shell.py` import `pages`（tasklist/TaskDetailPage），包边界与"modules 不依赖 pages"的叙述不符 | 已移到 `desktop/shell.py`；`modules_shell` 自测同步改读新位置 | 低 |
| 4 | ✅ **detect 人工干预的共享交互器**（2026-10-04 已做） | 两页各写一份"框类型回填/删除/整幅互斥确认" | 已抽 `desktop/components/box_kinds.py::BoxKindEditor`（无 Qt；确认框走宿主 `box_confirm` 回调，两侧的 `Dialog`/`MessageBox` 自测替身机制原样保留）；两侧旧方法名保留、实现委托 | 中低 |
| 5 | ⚖️ **`STAGE_LOCATIONS` 评估后决定保留在 `steps/ports.py`**（2026-10-04） | 曾考虑迁到 store 层 | 不迁：① 依赖方向本来就对（store→steps 单向），没有分层违规；② `PORT_ARTIFACTS`/`STAGE_LOCATIONS`/`SUPPLIERS` 三张表是同一个 BPM 连线故事（"换连线只改一张表"），拆到两个模块反而稀释叙事、破坏 `step_ports` 自测的契约面；③ 它是"落点表"，本来就是流程级知识。真正的边界守则是：**steps 包不许出现 UI/编排代码**，声明表不算 | — |
| 6 | ✅ **"编辑图片生效"查看器级原语统一**（2026-10-04 已做） | "立即上屏 + 单条缩略图刷新"的 getattr 探测逻辑两页各一份 | 已抽 `desktop/components/viewers/edit_sync.py`（`show_edited_image` / `apply_single_thumb`），两侧共用。⚠️ **缩略图重渲的 worker 与目标目录刻意保留各自实现**：taskdetail 用 `ImageListWorker` 写 `tasks/<id>/thumbnails/source/`、singletask 用 `ImageThumbCacheWorker` 写 `singletask/<key>/`——那是两套有意不同的缓存布局（禁止借道），合并会把分支塞进组件 | 中高 |
| 7 | 拼版模块页并入 StepModulePage 体系 | `modules/imposition/page.py`（869 行）靠 docstring 豁免，自写一套胶水 | `base.py` 扩展"多文件源"钩子后再收编 | 高（最后做） |

原则（与 §2 一致）：**每完成一项就重跑相关 `--only` 自测 + `gen_api_docs --check`
+ `check_docs`**；组件层不许新增任何宿主专属概念，宿主特有 UI 一律构造参数声明。

---

## 9. viewer 包拆分（2026-10-07）

起因（用户原话）："viewer 下的一些文件行数太多，文件大，维护困难，拆分成组件
或者模块，是否可以复用"；口径选择 **先做 viewer 包** + **彻底拆**（单文件
200~500 行，大类拆成 per-tool Mixin）。

### 9.1 六个单文件 → 六个子包

| 原文件 | 行数 | 拆成 |
| --- | --- | --- |
| `image_editor.py` | 4095 | `image_editor/`：`consts` / `geometry` / `bake` / `text_item` / `dialog` + `canvas/`（基座 + 7 个工具 Mixin） |
| `image_zoom_dialog.py` | 1246 | `image_zoom_dialog/`：`consts` / `icons` / `io` / `canvas` / `dialog` / `popup` |
| `print_preview.py` | 904 | `print_preview/`：`thumbs` / `layout` / `export` + `widget` |
| `image_viewer.py` | 781 | `image_viewer/`：`thumbs` / `pdf` / `boxes` + `core` |
| `image_view.py` | 666 | `image_view/`：`styles` / `render` / `edit` + `core` |
| `rembg_viewer.py` | 625 | `rembg_viewer/`：`entries` / `thumbs` + `core` |

收尾（同一轮）：`image_editor/dialog.py` 拆分后仍有 894 行（单类
`ImageEditorDialog`），再按职责拆成 4 个 Mixin —— `dialog_toolbar` /
`dialog_pages` / `dialog_undo` / `dialog_commit` + 基座（最大 270 行）。

**子包 = 同名目录 + `__init__.py`**。Python 的 `FileFinder` **先查目录再查
文件**，所以只要目录里有 `__init__.py` 就一定赢；但**旧单文件必须删掉**，
否则两份实现并存、改一份不生效（守卫里有专门一条断言钉这个）。

### 9.2 机械拆分流程（不手抄方法体）

```text
① AST 取方法/函数的 lineno~end_lineno → 按字节切片
② 每个新模块的 import 由"该模块用到的自由名字"反推（别名感知：
   FluentIcon as FIF / theme as T / widgets as ui 原样保留）
③ AST 等价校验：原文件 166 个方法逐个 ast.dump 对比新包（必须 0 差异）
④ pyflakes 不得新增条目
⑤ 自测 + 守卫双向验证
```

⚠️ 三个踩过的坑：

* **相对导入的 `level` 必须带上**。`from .canvas import X` 的 `n.module` 只是
  `"canvas"`，拼成 `from canvas import X` 就是 `ModuleNotFoundError`。
* **模块级常量别丢**。`ImageEditorDialog` 拆 Mixin 时 `EDITOR_SIZE` /
  `EDITOR_MIN_SIZE` 必须留在 `dialog.py`（`__init__.py` 还在 `from .dialog
  import EDITOR_MIN_SIZE, EDITOR_SIZE, ...`）。
* **测试里打桩要看"定义处"的模块**。`detect.py` 原先打
  `image_viewer.PreviewWorker`；拆包后 `_select_image` 住在
  `image_viewer/core.py`，名字解析看的是**那个模块的 globals** ——
  打包级属性只会多挂一个没人用的名字，计数恒为 0（**假绿**）。
  正确做法是打 `image_viewer.core.PreviewWorker`。

### 9.3 三条不变量（AST 守卫）

| 守卫 | 覆盖 | 钉什么 |
| --- | --- | --- |
| `tests/selftests/image_editor_split.py` | `EditorCanvas`（99 成员）+ `ImageEditorDialog`（32 成员） | 成员归属 / 无同名 / 跨 Mixin 依赖白名单 / 对外 API |
| `tests/selftests/image_zoom_dialog_split.py` | `image_zoom_dialog` 子包 | 子包结构 / 对外 API / 四个宿主仍可导入 |
| `tests/selftests/viewer_split.py` | `image_view` / `image_viewer` / `rembg_viewer` / `print_preview` | 上面四条 + 旧单文件已删 + 模块级函数仍在包命名空间 |

⚠️ **MRO 遮蔽是这次拆分的头号风险**：两个 Mixin 出现同名方法**不报错**，
排在前的静默赢 —— 等于偷偷改了行为。所以"无同名成员"必须**单独**断言一次。

⚠️ 宿主协议方法（`_zoom_index` / `_zoom_target` / `_on_zoom_image_saved`）
**刻意留在主类**，才能盖住 `ZoomPopupMixin` 的默认实现 —— 这条"派生类赢基类"
是**有意的**，不是遮蔽事故。

### 9.4 复用结论：**没有**抽公共基类

`image_viewer` / `rembg_viewer` / `print_preview` 三个宿主长得像，但逐方法
AST 比对后**只有 `navigate` 一个方法三处完全相同**，其余同名方法体都不同
（缩略图重渲的 worker、缓存目录、取图口径各自有别）。这与 §8 第 6 项的
「禁止借道」约定一致 —— **强行合并会把分支塞进组件**。故只做"按职责拆文件
+ Mixin"，不做"跨宿主继承"。

### 9.5 顺带修掉的测试脆弱点

护栏里"读源码文本做断言"的地方原先按老路径读 `xxx.py`，拆包后要么
`FileNotFoundError`、要么断言恒真。统一收进
`tests/selftests/_context.py::module_source_text()` —— 单文件/子包两种形态
都能解析（子包时 `rglob("*.py")` 合起来看）。


## 10. 拆分后的类型检查期宿主面（2026-10-08）

拆成 Mixin 之后，pyright 从 **837 个 error** 起步——全是
`reportAttributeAccessIssue`。根因很单纯：每个 Mixin 都是独立类，pyright
解析 `self` 时只看到它自己那一小块，于是

- 兄弟 Mixin / 主类上的成员（`self._image` / `self._sync_overlay` …）看不到；
- Qt 基类上的成员（`self.mapFromScene` / `self.viewport()` …）也看不到——
  更麻烦的是 `super().mousePressEvent(...)` 会解析到 **`object`**；
- 顺带 `self._fit_ratio` 之类退化成 `Any`，把下游 `float(ratio)` 也带红。

### 10.1 做法：每个子包一个 `_host.py`

```python
# desktop/components/viewers/image_editor/canvas/_host.py
class CanvasHost(QGraphicsView):      # 基类 = 主类去掉本地 Mixin 后剩下的基类
    """``EditorCanvas`` 的成员面：主类 + 7 个 Mixin。"""
    _image: Any
    def image_rect(self) -> QRectF: ...
    def _sync_cursor(self) -> None: ...
```

```python
# 各 Mixin
if TYPE_CHECKING:
    from ._host import CanvasHost
else:
    CanvasHost = object          # 运行期退化成 object ⇒ MRO 与行为零改动

class CageMixin(CanvasHost):
```

宿主类里**只有注解与 `...` 桩**，且 `_host.py` 只在类型检查期被导入
（`if TYPE_CHECKING` 分支），运行期从不加载。六个子包六个宿主：
`CanvasHost` / `DialogHost` / `ImageViewHost` / `ImageViewerHost` /
`RembgViewerHost` / `PrintPreviewHost`。

### 10.2 ⚠️ 四个必须踩过的坑

1. **`__init__` 绝不能进宿主面**。主类里的 `super().__init__(parent)` 会顺着
   MRO 命中宿主里的 `__init__` 桩，于是 `parent` 被当成 `placeholder` /
   `empty_hint` 报参数类型错（`image_view` / `image_viewer` / `print_preview` /
   `rembg_viewer` 四处同时中招）。**dunder 一律不声明**。
2. **只有首字母大写的名字才当类型**。否则 `max(...)` / `tuple(...)` /
   `build_mesh(...)` 会被当成类型，pyright 直接报 "not a valid type"。
3. **相对导入的 `level` 要解析成绝对模块名**。同一个 `ZoomTarget` 在
   `image_zoom_dialog/popup.py` 里写作 `from .canvas import ZoomTarget`，
   直接搬进 `image_editor/canvas/_host.py` 会指向不存在的 `canvas` 包。
4. **属性类型别一律给 `Any`**：`self._fit_ratio = EDIT_FIT_RATIO` 里的
   `EDIT_FIT_RATIO` 是模块级常量（`consts.py` 里 `= 0.98`），要查常量表拿到
   `float`；给 `Any` 会让下游 `float(ratio)` 因为 `float | None` 报错。

### 10.3 `TextBlockItem._canvas` 的类型换成宿主面

`text_item.py` 里 `self._canvas: "EditorCanvas | None"`，而 `add_text_block`
在 `text.py`（`TextMixin`）里写 `item._canvas = self` —— 拆分后 `self` 是
`TextMixin`（不是 `EditorCanvas`），赋值报类型错。改成 `"CanvasHost | None"`
即可：文字块本来只用得上 `_move_text_outline` / `_hide_text_outline` /
`_active_text_block` 这几个回调，**宿主面恰好就是它的真实依赖**。
（纯注解改动，运行期零影响。）

### 10.4 守卫

`tests/selftests/_context.py::check_type_only_host()` 把四条不变量钉死，
`viewer_split.py`（4 个包）与 `image_editor_split.py`（画布 + 弹窗）各调一遍：

1. `_host.py` 存在，宿主类基类 = 主类去掉本地 Mixin 后的基类；
2. 宿主面**恰好**覆盖 主类 + 各 Mixin 的成员（漏一个 = 该成员在类型检查里
   失明；多一个 = 与拆分现状漂移）；
3. 每个 Mixin 都是「TYPE_CHECKING 期继承宿主、运行期退化成 `object`」；
4. 运行期主类 MRO 里**没有**宿主类（证明零副作用）。

双向验证过：宿主面漏成员 → 断言红；去掉运行期兜底 → 红；还原 → 绿。

### 10.5 顺带

- `image_editor/__init__.py` 的 `__all__` 原先写成**裸名字**（`__all__ =
  [UNDO_LIMIT, ...]`，是**值**不是**名字**），pyright 报
  `reportUnsupportedDunderAll`。已改成 64 个字符串字面量。
- `tools/gen_api_docs.py` 现在**跳过单下划线开头的私有模块**（`_host.py`），
  但保留 `__init__` / `__main__` 这类双下划线门面。
- 结果：项目本体 pyright **0 error 0 warning**（拆分时是 837）。
