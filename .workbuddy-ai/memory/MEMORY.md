# gujitools 项目长期约定

## 架构分层（2026-09-16 确立）

依赖方向严格单向，禁止反向引用：

```
utils  ←  core  ←  cli
                 ←  functions
                 ←  desktop
```

- `utils/`：纯工具（图像/PDF/YOLO/路径），无内部依赖。
- `core/`：**中立共享层**，只依赖标准库与 utils。存放「两个入口都需要且语义必须一致」的东西。
- `cli/`、`functions/`、`desktop/`：三个上层，彼此不得交叉反向引用。

## core/ 层职责（新增代码优先放这里）

- `core/command_spec.py`：命令参数**默认值、枚举、校验规则的唯一事实来源**。
  - `COMMAND_SPECS`：命令 → `CommandSpec(defaults, validators)`。
  - `PRINT_DEFAULTS` / `PRINT_FORM_DEFAULTS`：命令行与 GUI 表单共用的 print 默认值。
  - `normalize_margin()` / `parse_color()`：委托 `utils.margin_utils` /
    `utils.color_utils`，两侧共用同一份规则。
  - `validate_color_fields()`：print 颜色校验（非法值不得静默降级为黑）。
  - **新增命令或参数只登记一次**，cli 与 desktop 自动共享。
- `core/args.py`：`ArgsProvider`（只读协议）、`CommandArgs`、`InitArgs`。
- `core/result.py`：`StageStatus` 枚举 + 退出码/状态字符串双向转换。
- `core/reporter.py`：**功能模块向宿主汇报结构化事件的通道**（见下节）。

## 结构化事件通道（2026-09-16 起，替代「文案即契约」）

**为什么**：`functions` 层原先 28 处 print 混着「给人看的日志」与「给程序读的
信号」，desktop 只能跑正则从中文提示里捞后者。改一句文案就静默断掉 GUI 进度条，
且并发下 print 非原子、正则偶尔漏读。

**协议**：`core.reporter.Reporter`（`progress(done,total)` / `event(name, **payload)` /
`log(msg)`，runtime_checkable 协议）。

- `CoreReporter` 空实现 + `NULL_REPORTER` 单例；`normalize_reporter(None)` 返回它。
  调用点永不判空，**CLI 不注入 → 输出与历史逐字一致**（已脚本验证）。
- `CallbackReporter(sink)` 适配器，测试用（sink 收 `(name, payload)`）。
- 事件名常量：`EVENT_PROGRESS` / `EVENT_PAGE_BOXES` / `EVENT_PAGE_SIZE`。
  **新增事件名先在此登记**，别两端各写各的字符串。
- `progress_total` 是「引擎先给总数」的内部名，`JsonLinesReporter` 会归一化成
  `done=0` 的 progress，不新增 GUI 不认识的事件类型。

**接线点（加新功能类时照做）**：
1. `FunctionBase.__init__(command_args, reporter=None)` → `self.reporter = normalize_reporter(reporter)`。
2. 子类 `__init__` 加 `reporter=None` 并 `super().__init__(command_args, reporter)`。
3. `functions/__init__.get_function(command, command_args, reporter=None)` 会自动透传。
4. utils 层函数（如 `pdf_utils.*`）需要上报时，也加 `reporter=None` 可选参数。

**desktop 侧**：`desktop/stages/events.py` 的 `JsonLinesReporter` 实现协议，
把事件直接写成 JSON Lines。`ProgressStream` 已削成**纯日志转发器（无正则）**；
`interceptor.done/total` 恒为 0（保留属性仅为兼容）。

**⚠️ 每个阶段执行器都必须重定向 stdout**：第三方库（ultralytics 打
`加载 YOLO 模型: …`）会裸 print，不拦截就混进 JSON Lines 破坏协议。
标准写法（见 `generic_stage.run_stage` / `detect_stage.run_detect_stage`）：
`interceptor = ProgressStream(_real_stdout(), context)` → `sys.stdout = interceptor`
→ 主体 → `finally: sys.stdout = original; if interceptor.buffer.strip(): interceptor._consume(...)`。

**⚠️ `finished` 事件不再带 `done/total`**：进度由 progress 事件实时汇报，
`runner.py` 用 `self._last_progress` 在 `store.finish_stage(..., progress=…)` 时补齐。

**兼容残留**：`[boxes]` / `[imgsize]` 两行文本在 functions 侧保留一个版本，
便于对照核验；worker 已不解析它们。确认无用后可删。

## area/border 几何：只有一份实现（utils/box_geometry 布局层）

**教训**：CLI 与 GUI 曾各自实现一遍几何，两处硬编码同一个 `SYMMETRIC_GAP_MM = 10`，
漂移后产生真实 bug —— `area=3 + 双框 + border=None` 时 GUI 把并集搬到画布
左上角 `(0,0)`，而规格要求「写回原位置」（`docs/functions/cropremove.md:57`）。

- 布局层：`build_output_layout(...)` / `build_symmetric_layout(...)`，
  返回冻结 dataclass `OutputLayout(canvases, full_page)` / `Canvas(size, sources, suffix)`。
- 上层只做**渲染**：CLI 用 numpy（`text_region._render_layout`），
  GUI 用 QImage（`preview_worker.render()`）。禁止再次自行推导几何。
- **⚠️ `symmetric` 必须显式传**：布局层不猜。`area=3 合并后的单框` 走普通布局
  （曾因 `len(present)==1` 分支无条件对称，产出 `220x938` 而非 `220x420`）。
- `SYMMETRIC_GAP_MM` / `parse_border_mm` 都在 utils 层。

## utils/ 中的共享纯函数（最低层，core 与 functions 共用）

- `utils/color_utils.py`：`parse_color` / `format_color`。非法输入**抛 ValueError**，
  绝不静默降级（静默返回黑色会让用户打错颜色却毫无提示）。
- `utils/margin_utils.py`：`normalize_margin` / `format_margin` / `DEFAULT_PAGE_MARGINS`。

**规则**：任何「两个及以上上层都要用」的纯函数，下沉到 utils，由上层委托调用，
不要在各自层里重复实现。

### ⚠️ 输出目录只有一个权威：`utils.path_utils.resolve_final_output_dir`

**教训（同类 bug 已出现两次）**：只要某处自己拼输出路径，规则必然漂移。
`detect` 曾自写 `self.input / default_temp_name`，把标注图嵌进输入目录，
而 crop/rembg/cropremove 走 `resolve_final_output_dir` → `input.parent / subdir`。
用户实测 `-i .../a/images --save` 得到 `.../a/images/detect`（错），
期望 `.../a/detect`（与 images **并列**）。

- **一律调用 `resolve_final_output_dir(input, output_arg, is_file, default_subdir)`**，
  禁止在功能类里自拼路径。规则：无 `-o` → `input.parent/subdir`；
  纯名字 → `input.parent/name/subdir`；含分隔符 → 绝对路径解析后再接 `subdir`。
- **唯一的例外是 `get_extract_output_root`**（extract 用）：目录输入时输出落在
  输入目录**内部**，与其余命令的「并列」语义不同，别顺手统一。
- **写路径断言必须带负向条件**：`detect_shared` 原先那条
  `outpath == work / "detect"` 把 bug 固化进了测试。现在同时断言
  `== work.parent / "detect"` **且** `!= work / "detect"`。

**⚠️ `utils/__init__.py` 的公开别名不可删**：`collect_image_files`、
`is_valid_image_size`、`IMAGE_EXTS`、`natural_sort_key`、`get_extract_output_root`、
`resolve_final_output_dir` 六个名字由 `utils/__init__.py` 直接重导出，
供 `utils.xxx` 形式取用（`functions/base.py:118`、`functions/rembg.py:79`、
`functions/text_region.py:49`、`desktop/stages/detect_stage.py:52` 都在用）。
pyflakes 必然报这六行「imported but unused」——这是**预期噪音**，不是死代码。
曾误删一次，导致 GUI detect 阶段静默失败（`module 'utils' has no attribute
'collect_image_files'`），全量自测在 detect 模块中断。

## 关键约定

1. **⚠️ None 默认值陷阱（最易踩）**：参数默认值只要可能是 `None`，
   `args.get(key, fallback)` 的兜底就**永不生效**——`CommandArgs` 总会注入该键。
   必须写 `args.get(key) or fallback`，或显式判空。
   已知 None-默认键：extract(pages/start/end)、crop/rembg/cropremove(border)、
   print(pdf_name/left_page_margins/right_page_margins/title_switch_nodes/
   page_number_end_page/skip_pages/files)。
2. **`functions` 层只依赖 `ArgsProvider` 协议**，不依赖具体参数容器类。
3. **`cli/command_args.py` 与 `cli/init_args.py` 是 deprecated 转发 shim**，
   新代码直接 `from core.args import ...`。
4. **`clean` 默认值恒为 `False`**（命令行、GUI、FunctionBase 三处必须一致）。
   任何情况下都不得在缺省时 `rmtree` 用户输出目录。
5. **`write_json` 返回 bool**，父目录缺失时静默放弃而非抛异常；调用方无需
   再额外判断目录是否存在。
6. **GUI 阶段执行也会 `validate()`**（在 `generic_stage.run_stage` 内），
   与 CLI 共用同一套校验规则，避免「界面放过、命令行拒绝」。
7. **GUI 专属的 `_` 前缀参数**（`_outpath`、`_effects`、`_preview_run_id`）为跨层传参保留，
   `print_params.EXCLUDED_KEYS` 与 `history.py` 会过滤它们，勿随意更名。
8. **验证方式**：
   - 全量 GUI 自测：`QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py`（**361 断言**）
   - 只跑某功能：`--only reporter,box_geometry`；列出：`--list`；跳过：`--skip`
   - CLI 输出一致性：`python tests/reporter_cli_parity.py`
   - worker 协议端到端：`python tests/reporter_worker_e2e.py`
   - 项目依赖齐全的解释器：`C:\Users\liuzu\anaconda3\python`（系统 python 缺 cv2/numpy/PySide6）
   - 静态检查：`python -m pyflakes core/ cli/ functions/ utils/`
   - 分层检查：确认 `utils/` 无反向依赖、`core/` 无上层引用、`functions/` 无 cli/desktop 引用。
   - 文档：`python tools/gen_api_docs.py`（改公开 API 后必跑）+ `python tools/check_docs.py`
9. **打包**：`guji.spec` 需 `collect_submodules` 覆盖新增的顶层包（已含 core）。
10. **⚠️ 写行为测试的四个坑**（本轮踩了三次假失败）：
    - 比对 stdout 时**路径必须相同**，否则「输出目录：…」天然不同；
    - **行序不可比** —— `处理完成: x` 的先后由 `ThreadPoolExecutor.as_completed`
      竞速决定，多线程下本就不确定。比行集合，不比顺序；
    - **耗时数字要归一化**（`用时: 0.04s` 每次都不同）；
    - `tests/selftests/` 下的模块由运行器动态发现，**新增用例 = 新增一个 .py 文件**，
      声明 `NAME` / `TITLE` / `DEPENDS`。

## 功能模块与命令全景（functions/ 下的每一步都是命令）

设计原则：**每个步骤都是 `functions` 层的一个能力，CLI 与 desktop 组合同样的
步骤，只差参数与编排**。

| 步骤 | 模块 | 命令 | 产出 |
|---|---|---|---|
| 提取 | `extract.py` | `extract` (`-e`) | 页图片 |
| 检测 | `detect.py` | `detect` | **默认无文件**；`--save` 出标注图 |
| 裁剪 | `crop.py` | `crop` | 裁剪图（= detect + 裁剪） |
| 去底色 | `rembg.py` | `rembg` (`-r`) | 去底图（整图，无检测） |
| 复合 | `crop_remove.py` | `cropremove` (`-cr`) | = detect + 裁剪 + 去底色 |
| 排版 | `print.py` | `print`（仅 `guji run print`） | PDF |

**⚠️ 检测只有一份实现**：`functions/detect.py` 的 `detect_page_boxes()`。
`TextRegionProcessor`（crop/cropremove 的公共基类）与
`desktop/stages/detect_stage.py`（GUI 第二步）都必须调用它，
**不得再直接调 `utils.detect_left_right_boxes`**。
`tests/selftests/detect_shared.py` 会扫描全仓库守卫这条约束
（断言真实调用方只有 `functions/detect.py`），违反即测试红。

- `detect` **默认无副作用**：不建目录、不写文件、无输出目录（`outpath=None`）。
  `DetectFunction.execute()` 被重写（基类语义是「建目录→处理→落盘→统计」），
  但**只在 `save=True` 时才 mkdir/clean**，其余保留相同的并发与 2 轮重试。
- **⚠️ 命令行强制 `--save`，不带则拒绝**：命令行里 detect 不落盘 = 坐标只打到
  stdout、无任何产出去处 = 白算一趟。拦截在 **CLI 入口**
  `cli.cli._reject_dry_run`（`main()` 里 `validate()` 之后调用，返回退出码 1）。
- `--save` 时输出目录规则与 crop **完全同源**：`DetectFunction._resolve_outpath()`
  直接调用 `utils.path_utils.resolve_final_output_dir`（crop / rembg / cropremove 也是），
  因此输出落在**输入目录的旁边** `<输入父目录>/detect`，**不是**嵌进输入目录里。
  ⚠️ 曾因自实现 `self.input / default_temp_name` 而嵌套，被用户实测报出。
- **不带 `--save` 时 `outpath=None`**：不计算路径、不建目录、不写文件，
  此时给 `-o/--output` 也**不生效**——detect 纯粹是 crop / cropremove 的前置中间步骤。
- `ext` 默认 png（线框标注用无损格式）。
- `detect` 上报的 `page_boxes` 事件名与 crop 阶段一致，GUI 视为同种事件。
- 无框是**正常**情况（`no_detect`，不算失败）；「无框怎么办」由下游决定。

## ⚠️ 配置模板 ↔ 命令规格必须一致（static/guji.yaml）

`core/command_spec.COMMAND_SPECS` 是「命令与参数」的事实来源，但用户实际编辑的是
`static/guji.yaml`。两者漂移的后果是**静默的**：模板缺一个命令块，
`guji run <cmd>` 只在运行时抛「config section missing」，用户照模板抄却抄不出来。

`tests/selftests/config_template.py`（**55 断言**）守住：

1. 6 个命令（extract/rembg/crop/cropremove/print + **非必要的 detect**）
   在模板里都有小节；
2. **小节键名 ⊆ `spec.defaults | {input, output, clean, workers}`**；
3. detect 小节上方的注释块必须含「非必要」并提到 crop/cropremove；
4. 模板取值能构造 `CommandArgs` 并 `validate()` 通过
   （⚠️ `input` 会被 `.resolve()`，比较要用 `work.resolve()`，不能比原始字符串）；
5. CLI `run` 的位置参数 choices 覆盖全部 `COMMAND_SPECS`；
6. **索引型文档不得漏记命令**：`README.md` / `docs/README.md` / `docs/cli.md` /
   `docs/functions/overview.md` 四份都必须出现每个 `COMMAND_SPECS` 命令名，
   且都要含「非必要」说明；
7. **`docs/cli.md` 参数表的行首参数名必须真实存在于对应 parser**
   （⚠️ 只扫**表格行** `^\|\s*`--xxx``，**不扫正文**——正文里
   「rembg 没有 `--ext` 参数」这类正常提及会造成假失败）。

**新增命令/参数的接线清单**（缺一即漂移）：
`core/command_spec.py` → `functions/<cmd>.py` → `functions/__init__._COMMAND_MAP`
→ `cli/cli_args.py`（子命令 + `run` 的 choices）→ `functions/base.DEFAULT_TEMP_NAME_MAP`
→ **`static/guji.yaml` 加小节** → `functions/init.py` 的 `for cmd in [...]` 填入 input
→ `utils/help._DOC_MAP` + `docs/functions/<cmd>.md`。
**外加四份索引型文档**（README 功能一览 + docs/README 命令一览 + docs/cli 参数表
+ overview 模块清单）与 `docs/io_path_rules.md` 的 default_temp_name 列表。

### detect 是「非必要」步骤（模板已标注）

`crop = detect + 裁剪`、`cropremove = detect + 裁剪 + 去底色`，两者内部已自动检测。
detect 小节可**整段删除**而不影响其他命令；它只用于单独查看检测结果。

**⚠️ 模板里 detect 必须是 `save: true`**：`guji run detect` 走的就是 CLI 入口的
空跑拦截，若模板写 `save: false`，用户照着模板抄却跑不起来（模板自己不自洽）。
`guji init` 生成的配置继承 `save: true`。
模板里 detect 的 `clean` 特意写 **`false`**（不是其他小节的 `true`）。

### ⚠️ 死配置反例：`rembg.ext` 已从模板删除

模板原有 `rembg.ext: "png"`，但 `COMMAND_SPECS["rembg"]` 无此键、
`functions/rembg.py` 也从不读它（输出路径硬编码 `f"{stem}.png"`）——模板给了个
没人读的旋钮。判定为死配置并**从模板删除**，而非给 spec 补一个空转的 ext：

- `rembg` 的 `type=2` 是 1bit 单色位图，**只有 PNG 能无损承载**，JPEG 会把它
  重新糊成灰阶 → 输出格式本就**不该可配置**；
- `rembg.py` 写出处与 `COMMAND_SPECS["rembg"]` 各留注释说明「固定 PNG，故无 ext」。
- 对照：`crop` / `cropremove` 确实读 `ext`（`TextRegionProcessor` 里赋值输出后缀），
  所以它们有 `ext` 默认值。

**判据**：模板里有、spec 里没有的键，要么补 spec（真读它），要么删模板（死配置）。
不要放着不管——`config_template` 自测会红。


CLI `detect --save` 与 GUI 预览必须画出**同一套**框，否则两个入口看到两套东西。

- 颜色/命名常量与 `desktop/components/viewers/image_view.py` 对齐：
  左框 `#21c178` 绿、右框 `#3b82f6` 蓝、合并框 `#f59e0b` 橙；
  名称 `左框/右框/合并框`。`utils/box_draw.py` 里存的是 **BGR**。
- `draw_boxes(img_bgr, boxes, ...)`：**跳过 `None` 项**（只画真正检出的框，
  避免「只检出左框」时在猜测位置画出错误右框）；线宽按图像短边自适应
  （短边/500，钳在 2..10）；返回新数组，**不污染入参**。
- **⚠️ 中文标注必须走 PIL**：`cv2.putText` 不支持中文（画成 `????`）。
  字体候选与 `utils.pdf_utils.register_fonts` 同序
  （fsgb2312 → simfang → simsun → msyh）；**全缺失时降级 ASCII 标签 `L`/`R`/`U`**，
  任何环境都不崩。
- **⚠️ 标注带白色衬底且贴框顶边**：因此**框的顶边会被标签遮住**，属预期设计。
  写像素级测试时取**侧边或底边**采样，取顶边会假失败（已踩）。

## ⚠️ 限制放在入口层，不放共享校验层

**教训（detect 空跑拦截）**：需求是「命令行 detect 不带 `--save` 直接拒绝」。
直觉会写进 `CommandArgs.validate()` —— **错的**：那是 CLI 与 GUI **共用**的，
一旦在校验层强制 `save`，GUI 的 detect 阶段（本来就不落盘，坐标经事件通道
交给界面画框）会被一起拦死。

**判据：这条限制是「某个入口的取舍」还是「业务的客观约束」？**

| 类型 | 放哪 | 例子 |
|---|---|---|
| 客观约束（谁调都得满足） | `core/command_spec` 的 validators | `area ∈ {1,2,3}`、`ext` 枚举、颜色必须可解析 |
| 某个入口的取舍 | 该入口自己的层 | CLI 拒绝 detect 空跑 |

- `functions/` 是**可复用的库层，保持宽松**：`DetectFunction` /
  `detect_page_boxes` 作为 `crop` / `cropremove` 的中间步骤被代码调用时
  必须可用，不能因为「命令行不想让它空跑」就设限。
- 实现写法：入口层一个小谓词函数（如 `_reject_dry_run(command, args) -> bool`），
  返回 True 表示已拒绝；**顺手验证拒绝路径无磁盘副作用**。
- 提示文案要给**可执行的替代方案**（正确用法 + 相邻命令 + 代码调用说明），
  不只是报错。

**元断言注意**：写「校验器不得依赖 X」这类测试时，必须**剥掉 docstring 只查
函数体**——校验器的文档往往正是在解释「为什么不在这里做这件事」，
直接搜整段源码会假失败。用 `ast.parse` + 过滤 `ast.Expr/ast.Constant` 节点。


## 新增功能类的接线清单（照做不漏）

1. `functions/<name>.py`：实现类，`__init__(command_args, reporter=None)`。
2. `core/command_spec.COMMAND_SPECS`：登记 `CommandSpec(defaults, validators)`。
   **只登记一次**，cli 与 desktop 自动共享默认值/校验。
3. `functions/__init__._COMMAND_MAP`：命令名 → (模块, 类名)（延迟导入）。
4. `cli/cli_args.py`：加子命令（参数**不设 default**，默认值归 core）；
   若要支持 `guji run <name>`，同时加进 `run_parser` 的 choices。
5. `utils/help.py`：`_DOC_MAP` 加条目 + 总览文本补一行；
   `docs/functions/<name>.md` 写手册。
6. `docs/functions/overview.md`：模块表 + 命令关系图。
7. 跑 `tools/gen_api_docs.py` + `tools/check_docs.py`。

## GUI 列表条目几何：图标框 ≠ 网格（print 列表踩过）

`desktop/components/viewers/print_preview.py` 曾用
`ICON_SIZE=180x240` + `GRID_SIZE=200x290` + `AlignBottom`，导致每个条目被强制
成 200x290 固定框、图标只占顶部 240px、文字被钉在网格最底部 ——
**图片与文字间恒定空出 50px 死区**，与图片宽高比无关。

- 观感差异来自图片比例：`area=2 + border=None` 输出**整页画布**（2481x3508，
  ratio 1.414）几乎占满 180x240 图标框，50px 死区一眼可见；`area=1` 输出
  900x2600（ratio 2.889）只占约 83px 宽，同样死区不刺眼。
- **规则**：IconMode 列表里若设了 `setGridSize`，文字对齐**不得用 `AlignBottom`**
  （会被推离图标）；网格高应 = 图标高 + 文字区（现 `LABEL_H=44`，即 200x284）。
- 回归测试：`tests/selftests/print_list_layout.py`（10 断言）钉住该不变量。
- 诊断手法：`QListWidget.visualItemRect(item)` 返回的是**网格尺寸**，
  与图片比例无关——可用来快速判定「条目高」是网格写死还是图片真的高。

## 已知未处理（后续可做）

- `desktop/` 里仍有一批未清理的 pyflakes 噪音（未用导入、
  `desktop/ui/widgets.py` 未用局部变量、若干测试模块的未用局部变量）。不影响运行。
  （`log_panel.py` 的 `QTextEdit` 未定义名已修：改 TYPE_CHECKING 导入。）
- `functions` 层的人类日志仍走 print（经 ProgressStream 转发为 log 事件）。
  若将来也想走事件通道，可继续把高频日志搬到 `reporter.log()`。
