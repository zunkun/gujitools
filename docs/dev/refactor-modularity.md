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
detect_page_boxes` 是**有意的算法复用**（GUI 检测阶段要跑与 CLI 完全相同的检测），
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
