# 命令 / 配置 / 实测细节（functions/ + cli/）

> 从 MEMORY.md 拆出，避免主文件过长被截断注入。按需读本文件。

## 功能模块与命令全景

**每个步骤都是 `functions` 层的一个能力，CLI 与 desktop 组合同样的步骤，只差参数与编排。**

| 步骤 | 模块 | 命令 | 产出 |
|---|---|---|---|
| 提取 | `extract.py` | `extract` (`-e`) | 页图片 |
| 检测 | `detect.py` | `detect` | **默认无文件**；`--save` 出标注图 |
| 裁剪 | `crop.py` | `crop` | = detect + 裁剪 |
| 去底色 | `rembg.py` | `rembg` (`-r`) | 去底图（整图，无检测） |
| 复合 | `crop_remove.py` | `cropremove` (`-cr`) | = detect + 裁剪 + 去底色 |
| 排版 | `print.py` | `print`（仅 `guji run print`） | PDF |

**⚠️ 检测只有一份实现**：`functions/detect.py` 的 `detect_page_boxes()`。
`TextRegionProcessor`（crop/cropremove 的公共基类）与 `desktop/stages/detect_stage.py`
（GUI 第二步）都必须调它，**不得再直接调 `utils.detect_left_right_boxes`**；
`tests/selftests/detect_shared.py` 扫全仓库守卫（断言真实调用方只有 `functions/detect.py`）。

### detect 细节

- 默认无副作用（`outpath=None`），不建目录不写文件；只在 `save=True` 时 mkdir/clean。
- **命令行强制 `--save`**，不带则拒绝：拦截在 CLI 入口 `cli.cli._reject_dry_run`
  （`main()` 里 `validate()` 之后，exit 1）。不带 `--save` 时给 `-o` 也**不生效**——
  detect 纯属 crop / cropremove 的前置中间步骤。
- `--save` 的输出目录规则与 crop **完全同源**（调 `resolve_final_output_dir`），
  落在 `<输入父目录>/detect`，**不是**嵌进输入目录里（曾因自拼路径嵌套，被用户实测报出）。
- 返回 `(left_box, right_box)` 各可为 `None`，而 `store.save_detect_boxes()` 要**列表**：
  `[b for b in (l, r) if b is not None]`。
- `ext` 默认 png（线框标注用无损格式）；无框是**正常**（`no_detect`），由下游决定。
- `detect` 上报的 `page_boxes` 事件名与 crop 阶段一致，GUI 视为同种事件。

### CLI 与 GUI 预览必须画同一套框

- 颜色与 `desktop/components/viewers/image_view.py` 对齐：左框 `#21c178` 绿、
  右框 `#3b82f6` 蓝、合并框 `#f59e0b` 橙；名称 `左框/右框/合并框`。
  ⚠️ `utils/box_draw.py` 里存的是 **BGR**。
- `draw_boxes(img_bgr, boxes, ...)`：**跳过 `None` 项**（只画真正检出的框）；
  线宽按短边自适应（短边/500，钳 2..10）；返回新数组，不污染入参。
- **⚠️ 中文标注必须走 PIL**（`cv2.putText` 画成 `????`）。字体候选同
  `utils.pdf_utils.register_fonts`（fsgb2312 → simfang → simsun → msyh）；
  全缺失时降级 ASCII `L`/`R`/`U`，任何环境都不崩。
- **⚠️ 标注带白色衬底且贴框顶边**，框顶边被标签遮住属预期设计。
  写像素级测试时取**侧边或底边**采样，取顶边会假失败（已踩）。

## ⚠️ 配置模板 ↔ 命令规格必须一致（static/guji.yaml）

`core/command_spec.COMMAND_SPECS` 是「命令与参数」的事实来源，但用户实际编辑的是
`static/guji.yaml`。漂移后果**静默**：模板缺一个命令块，`guji run <cmd>` 只在运行时
抛「config section missing」，用户照模板抄却抄不出来。

`tests/selftests/config_template.py`（**55 断言**）守住：

1. 6 个命令（extract/rembg/crop/cropremove/print + **非必要的 detect**）在模板里都有小节；
2. **小节键名 ⊆ `spec.defaults | {input, output, clean, workers}`**；
3. detect 小节上方注释块必须含「非必要」并提到 crop/cropremove；
4. 模板取值能构造 `CommandArgs` 并 `validate()` 通过
   （⚠️ `input` 会被 `.resolve()`，比较要用 `work.resolve()`，不能比原始字符串）；
5. CLI `run` 的位置参数 choices 覆盖全部 `COMMAND_SPECS`；
6. **索引型文档不得漏记命令**：`README.md` / `docs/README.md` / `docs/guide/cli.md` /
   `docs/functions/overview.md` 四份都必须出现每个命令名，且都含「非必要」说明；
7. **`docs/guide/cli.md` 参数表的行首参数名必须真实存在于对应 parser**
   （⚠️ 只扫**表格行** `^\|\s*`--xxx``，**不扫正文**——正文里「rembg 没有 `--ext` 参数」
   这类正常提及会造成假失败）。

**新增命令/参数的接线清单**（缺一即漂移）：
`core/command_spec.py` → `functions/<cmd>.py` → `functions/__init__._COMMAND_MAP`
→ `cli/cli_args.py`（子命令 + `run` 的 choices）→ `functions/base.DEFAULT_TEMP_NAME_MAP`
→ **`static/guji.yaml` 加小节** → `functions/init.py` 的 `for cmd in [...]` 填入 input
→ `utils/help._DOC_MAP` + `docs/functions/<cmd>.md` → `docs/functions/overview.md`
（模块表 + 命令关系图）→ 跑 `tools/gen_api_docs.py` + `tools/check_docs.py`。
**外加四份索引型文档**与 `docs/dev/io_path_rules.md` 的 default_temp_name 列表。

- **detect 是「非必要」步骤**：`crop`/`cropremove` 内部已自动检测，小节可整段删除。
  ⚠️ 模板里 detect 必须是 **`save: true`**（`guji run detect` 走 CLI 空跑拦截，
  写 false 则照模板抄跑不起来）；`clean` 特意写 **`false`**（不是其他小节的 `true`）。
- **死配置反例 `rembg.ext` 已从模板删除**：spec 无此键、`rembg.py` 也从不读
  （输出路径硬编码 `f"{stem}.png"`），给了个没人读的旋钮。`rembg` 的 `type=2` 是
  1bit 单色位图**只有 PNG 能无损承载**（JPEG 会糊成灰阶）→ 输出格式本就**不该可配置**。
  对照：`crop`/`cropremove` 确实读 `ext`，所以它们有默认值。
  **判据**：模板有、spec 没有的键，要么补 spec（真读它），要么删模板（死配置）。

## 实测备忘（真实古籍跑全流程）

- **`guji init` 不可脚本化**：`functions/init.py:104` 调 `safe_input()` 读 stdin，
  非交互环境下 `EOFError` 退出（exit 2）。**自动化/批量场景必须手写 guji.yaml**
  （照 `static/guji.yaml` 抄）。待办：给 `init` 加 `--yes` / 非交互开关。
- **`extract` 的默认输出目录**：输入是**文件**时 → `<输入父目录>/images/`
  （经 `get_extract_output_root`），不是 cwd。后续步骤 `-i` 要指这个目录。
- **竖开本扫描件必须改 `orientation`**：print 默认 `landscape`，
  竖开本（如 1041x1800pt，比例 0.578）要显式写 `orientation: "portrait"`。
- **保留印章**：`rembg --seal --sealcolor`（默认都是 false）。红印章古籍建议开，
  实测红色印文能干净保留、正文仍为纯黑白。
