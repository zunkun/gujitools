# gujitools 记忆

古籍重製：PDF→提图→检测框→去底色→生成PDF。双入口共用算法：`cli.py`(打包`guji`)/`desktop.py`(PySide6+qfluentwidgets)。分层`utils←core←{cli,functions,desktop}`**严格单向**。

> ⚠**只放"高频必守"判据（有硬上限）**；全部判据在 **`MEMORY-details.md`**，理由与量化在 `2026-10-*.md` 日志。**改某子系统前先检索这两处**。⚠新增先删旧的。

## 纪律
- **AI 禁止自动 `git commit`**：只汇报 `git status`/diff，等用户说"提交"。"撤回"＝`git reset --soft HEAD~N`（**绝不 `--hard`/`checkout --`/`restore`**）。提交前：diff 落盘＋`cp` 未跟踪文件→自测→`git diff --cached --name-only` 兜产物。
- 用例只进 `tests/selftests/<名>.py`（`NAME`/`TITLE`/`DEPENDS`）；探针放 `tests/`；**禁仓库根新建脚本**。临时数据只落 `tests/tmp/`（唯一落点 `tests/tmpdir.py::temp_dir("前缀_")`，入口先 `install()` 须早于任何 `tempfile` 调用，收工 `clean()`）；临时脚本/日志放 `_scratch/`，收工删净、`git status --short` 无 `??`；⚠**别往 `.gitignore` 补 `_*.py`**（匹配 `__init__.py`）。

## 自测（细则见 `MEMORY-details.md`）
- `QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE python -u tests/gui_selftest.py`，⚠**必带 `-u`**；`--only <mod>` 定位。解释器＝`C:/Users/liuzu/anaconda3/python.exe`。⚠别拿 PASS 计数判"新断言跑了没"＝**grep 日志断言文本**。⚠`QThread: Destroyed` 硬中止**吃掉其后模块**（127＝伪错误）⇒核对 `--list`、`--only` 补跑。
- ⚠**本会话环境**全量会在第 1 模块后整体中止（`safe-delete` 钩子拦批量删临时目录）⇒验证一律**分组 `--only`**。本机环境性红：缺若干依赖＋⚠**QProcess 一律 FailedToStart**（真起 worker 的模块都红）。
- ⚠⚠⚠**离屏**：绝不真弹模态（看门狗 `os._exit(3)`）；拖拽走 `QTest.mousePress`；判"控件能不能点"❌`childAt()`、`widgetAt` 离屏返 None，✅`QTest.mouseClick` 真点看槽；`show()` 异步须 `processEvents`。⚠**"改前会红吗"必须双向验证**：注入在**独立子进程**、`cp` 备份不用 git、先 `assert count==1`、确认红的是**目标断言**；⚠**别 `git stash`**。
- ⚠本仓 CRLF/LF 混杂：脚本"读-替换-写回"须 `read_text()` 后按 `\n` 匹配、写回 `newline="\r\n"`，否则 `str.count` 恒 0。改 `functions/`|`utils/` 必跑 `reporter_cli_parity.py`|`reporter_worker_e2e.py`|`cli_print_smoke.py`；文档 `gen_api_docs.py --check`+`check_docs.py`（私有方法不进 API 文档）。

## 事实来源（别另写一份）
CLI参数`core/command_spec.py`｜桌面默认值`components/panels/params_spec.py`｜色距字号`ui/theme.py`｜JSON`store/json_io.py`。框几何`utils/box_geometry.py`：半幅恒2槽[左,右]/整幅恒1槽（**下游靠槽数辨形态**）；绘制`box_draw.draw_slots`；排版`page_layout.py`；页序`sort_utils.pdf_custom_sort_key`。步骤`steps/spec.py::SPECS`唯一（`STEP_KEYS` 等 5 张表全由它派生；`role`⊥`nav`）；页面内查`ports.spec_for_stage(stage)`（⚠别用`spec_by_key`：`rembg_submit`→None），中文名走`ports.stage_label()`。

## 图片编辑器（当前重点）
- ⚠⚠**子包拆分**：`viewers/` 六个大文件已拆同名子包（`image_editor/`…`rembg_viewer`；全量 re-export）。改前读 `tests/selftests/*_split.py`：**Mixin 间不许同名成员**（MRO 静默遮蔽）；成员换落点同步 `_EXPECTED_HOME`；跨 Mixin 调用登记白名单；**打桩看「定义处」的模块**。每包有**类型检查期宿主面 `_host.py`**（`else: XHost = object`），改成员须同步 `_context.check_type_only_host()` 四条不变量（宿主面**恰好**＝主类＋各 Mixin 成员；⚠`__init__` 绝不进宿主面）。
- ⚠⚠**版面＝顶部功能选择＋右侧参数面板**（`dialog_toolbar.py`）：`_build_side_panel` **必须先于** `_build_toolbar_row`；**参数区必须装 `ScrollArea`**（不装 ⇒ Qt 把整页压到最小高度）。裁剪/变换**松手即应用**（`crop_committed`/`transform_committed`；⚠拖轴心**不发**）；⚠选区没变 `_apply_crop` **必须短路**；**唯一确认＝覆盖原图**。
- ⚠⚠**统一变换＝`geometry.compose_transform` 一条数学**（预览与烘焙共用）。⚠**绝不用 `QPainter.setTransform(xf)`＋`drawImage(rect,region)`**：实测**不等价于 `map(rect)`**（漂 ~10px）且只支持仿射。像素一律走 `warp_placement`（取不到 numpy 才退 QPainter）。⚠返回值多形态（`grow=False`=QImage、`True`=(图,原点)）⇒ 一律 `r[0] if grow else r`。
- ⚠⚠⚠**病态投影的尺寸闸门＝`geometry.mapped_bounds()` 唯一判据**（透视角拖到对角附近 ⇒ `QImage(2.18e9,…)` OverflowError 崩）：非有限／坐标>`ABSURD_COORD`(1e8)／外框像素>`WARP_MAX_PIXELS`(40MP) ⇒ `None`＝**宁可不画**。四入口共用：`warp_region`、`warp_placement` 的 QPainter 兜底（曾没挡⇒崩）、`compose_transform(grow=True)`、`transform.py` 透视步进（拒绝该步、框不动）。**别在各处另写 min/max**。
- ⚠⚠⚠**变换预览＝两档，图元矩阵口径故意不同**（2026-10-09 修"只旋转不能实时"）：**拖动中**＝快档：像素**不重采样**（画布＝`_xf_preview_region`），变换全交给图元 `_float_fast_xf()`（**0.6–2 ms/帧**；逐像素档 12MP 要 158/442ms，连 k=1 小图也 158ms ⇒ 就是"不能实时"）。**首次/松手后**＝精确档：`_render_float_plane()` 逐像素 `warp_placement`，图元只 `_float_placement()`＝**纯 scale(1/k)+translate**（**m12/m21 恒 0**）。⚠**两档绝不可混用**；⚠`_apply_float_fast()` 末尾**必须清 `_xf_preview_keyframe`**（否则松手不补精确帧⇒跳变）。摆位矩阵唯一＝`_placed_xf()`＝`translate(选区左上角)*_preview_xf(_xf)`。⚠"预览==烘焙"只在精确档成立。
- ⚠⚠⚠**预览尺度矩阵的"左右"（2026-10-09 第三轮报障）**：Qt 的 `A*B`＝**先 A 后 B**（行向量约定），数学记号 `S(k)∘placed∘S(1/k)` 正相反⇒`_preview_placement_xf`/`_float_fast_xf` 两处都写反，**平移量被多除一个 k**（k=0.6 时 160px 偏出 920px＝「框与图分离、格子远离」）；⚠`_render_float_plane` 拿到的 `(x0,y0)` 在预览尺度里，还要 **`÷k`** 才是图片坐标。⚠⚠**选区 ≤0.5MP ⇒ k=1，这条路完全测不到**——判据必须用**大于 `TRANSFORM_PREVIEW_PIXELS`** 的图（旧自测 200×120/600×800 ⇒ 全绿放过）。
- ⚠⚠**场景矩形恒＝`image_rect()`**（`_sync_scene_rect`，用户"画布画面是不变的"）：`AlignCenter` 下 `setSceneRect` 一变、场景矩形中心就变 ⇒ **整幅画面跟着平移**（转+移漂 294px）。⚠它只管滚动条范围、**不影响绘制**：画到矩形外的图元照样画得出来，所以预览不需要扩它。
- ⚠⚠**拖动中裁剪要自己掩膜**：裁剪矩形**逆映射回区域局部**得平行四边形，`QPainterPath` 掩膜。⚠⚠**`setClipPath` 限制在路径之内**，配 `Clear` 必须传**补集**（`outside.subtracted(mapped)`）——传原集会清反（该留的透明、该清的留着）。
- ⚠⚠**画布底＝浅底(#e3e8ed)＋"原图矩形"处条纹格，纸透明**（`core.paintEvent`）：「白底不该扩大…旋转不再有白色区域」；⚠「灰色太突兀」⇒底色两度调浅(#8B949D→#C9D1D8→#e3e8ed)，**底一浅、棋盘格暗格必须跟着压深**(#d9dce1→#cdd4db)否则格子糊进底。`_base_target_rect()` **恒＝`image_rect()`**（不跟变换长大），底图填**透明**（选区原位必须 `CompositionMode_Clear`）；⚠烘焙画布仍走 `_bake_canvas_rect()`（只用来定"越界内容裁到哪"）。细节见 `MEMORY-details.md`。
- ⚠⚠⚠**统一变换一律在"视觉矩阵"里算**（2026-10-09 修「方向=校正，图片和操作框方向相反」）：视觉矩阵＝`_visual_xf()`（正向=`_xf`、**校正(向后)=`_xf` 的逆**，与浮层/烘焙同口径）。覆盖层（`_transform_quad`/手柄/轴心/命中）与拖拽快照、六个 `transform_*` 语义入口全吃它，算完经 **`_apply_visual()`** 按方向落账回 `_xf`（唯一写入口；`_apply_shear` 只**返回**矩阵）。旧版框画 `_xf`、内容走逆 ⇒ 校正下框与内容反向。**正向行为逐位不变**；`transform_pending` 返回的 `_xf` 语义未动，烘焙照旧取逆。
- ⚠⚠⚠**整幅烘焙绝不能同步跑**：12 MP 实测 **11.3 秒** ⇒ `DISTORT_SYNC_RENDER_PIXELS` 内同步、超出走 `bake.run_with_progress`（可取消）。⚠撤销点**先压、两条路只压一次**；取消/失败 `_undo_now()`＋`reset_transform()`。⚠**"松手挂起、离开工具才烘焙"**：`mouseReleaseEvent` 只 `make_transform_pending()`；`_set_tool`/`_flip_transform` 走 `_commit_transform(force=True)`；⚠`has_pending_transform()` 为真时**不烘**。⚠⚠**纯翻转走快路径**：无挂起变换且选区=整幅 ⇒ `QImage.mirrored` 直翻（重采样 12MP 要 ~11 秒＝"翻转卡顿"），压撤销点「翻转」；测试丢弃挂起变换用 `reset_transform`（`_set_tool` 会烘焙）。
- ⚠⚠**变换节点 16 个**：4 角大方框(28px，双轴)＋4 边中方框(16)＋4 切变菱形(16；¾ 处、顺时针 `t→tl/r→tr/b→br/l→bl`)。⚠⚠**透视小菱形(16)与角方框同心**（`PERSP_INSET=0`）⇒"角点归谁"由**半径**分（透视 8／方框 13 方形环带）。**命中优先级**：轴心→透视菱形→角方框→边中方框→**切变菱形**→边带→框内→框外。⚠⚠**节点默认中空（主题色描边）、只有焦点实心**（`overlay._style_node`）；⚠菱形与角**共享身份**：焦点 `tl`⇔`p_tl` 键归一后**一起实心**。⚠切变跟手：k＝沿线位移 ÷ **该边自身跨度**，`mode` 起点存**选区局部坐标**。
- ⚠⚠**回写后"界面没变"＝典型静默失败**：①内存缩略图按路径缓存不过期；②**拿路径串直接 `==` 比**（Win `/`→`\` 落空后整段 return）⇒统一走 `services/imposition.py::same_path/page_has_file`；③缓存失效只 pop 原样串（要扫**同形键**）。⚠`_confirm_overwrite()` 在任何烘焙前问、`_finishing` **先于确认框置位**；`editor.target_name` **只能做属性**。
- `ImageViewerWidget` 两形态：图片(`set_images`/`set_thumb_source`)／PDF 页(`set_pdf_source`+`begin_pdf_pages`+`set_pdf_thumb`)；⚠`set_images` 须先 `_clear_page_source()`。`RembgPreviewWidget.set_images(paths, rembg_dir)` **第二参是结果目录**。
- 📄**另有 4 条编辑器坑（棋盘格 `NoBrush`／"越转越小"两真因＋`fit()` 不许动 `_user_zoomed`／撤销时间轴 len 配对／扭曲 `_carry`）见 `MEMORY-details.md`，各有自测守着。**

## Qt/界面通用坑
- ⚠⚠**Qt `clicked` 顺手喂一个 `checked: bool`**：槽**只要带一个可选位置参数**就中招（`connect(canvas.fit)` ⇒ `fit(ratio=False)`、图缩成 1/4）；**接线一律套 lambda**，被调方对 `bool`**降落回默认**。
- ⚠⚠**qfluentwidgets `Dialog` 放不下成套面板**（第二参是**字符串**、**没有** `viewLayout()`）⇒走 `components/dialog_shell.py::shell_dialog`。⚠**"点按钮就炸、自测却全绿"先怀疑外壳**（自测都直接实例化 `*Panel`）。⚠**面板 `self.close()` 关不掉弹窗**⇒`self.window().close()`。
- ⚠`Card`（`ui/widgets.py`）**自带 layout、暴露为 `card.box`**——再建第二个 `QVBoxLayout(card)` 会被忽略（卡片空成 32×32）；高度**用 `heightForWidth`**。⚠判控件状态用 **`isHidden()`** 不用 `isVisible()`，**方向别反**。
- ⚠界面：控件 `paintEvent` 自绘不引样式表；下拉 `widgets.combo_box()`；窗口尺寸 `ui/window_size.apply_window_size`。⚠高分屏绝不手 `painter.scale(dpr,dpr)`。⚠「点空白处」**直接**开选文件对话框；⚠**"资源管理器"＝原生 `QFileDialog`**（**不设** `DontUseNativeDialog`）。
- ⚠跨线程用 `desktop.workers.connect_queued`。⚠**`QThread.run()` 必须 try/except**（异常逃出不杀进程、`result=None` 被上层当"用户取消"）。⚠GUI 主进程不许进重依赖(`functions.detect`→cv2)：纯规则放 utils 且不 import functions（AST 守卫）；中文路径走 `utils.image_io`。⚠**传路径的公开 API 须在边界 `Path()` 收口**；⚠**同一输出目录只准一个写入者**（`stages/imposition` 靠 `_COMPOSE_LOCK`+`_save_page_atomic`）。

## BPM / 步骤条（最狠的坑；详见 `MEMORY-details.md`）
- ⚠⚠⚠**图必须压过静态连线表**：`ports.SUPPLIERS` 只兜底；`store.stage_supplier`①**不声明的端口⇒没这个输入**（`ports.stage_inputs` 必须在查图**之前**）②**图给出唯一答案⇒图说了算**（`producers_of`，遇产出方就停）③**图说不清⇒退回静态声明+条件开关**（默认流程带「是否拼版」网关＋两条**实线**进「PDF排版」⇒必须靠 `print_pages_supplier(imposition_active)` 运行态选）。
- ⚠⚠**端口依赖 ≠ 流程连线**（`(consumer,port)→supplier`＝取谁的文件；`sequenceFlow`＝先做哪一步）。`stage_order()`＝**Kahn 拓扑序**（⚠别用 BFS：分叉"短路"会把 `print` 排到 `imposition` 前）。⚠只有 `task` 节点映射阶段（`endEvent` 常叫「生成PDF」，按名查表会误认成 `print`）。
- ⚠⚠**三套下标别混**：①**格序 `bar_index`**（含可选节点占位）＝步骤条唯一语义②**栈页号 `stack_index`** ③`currentIndex()`。⚠**`stack_index` 必须"查静态表"**（两栈一次建好固定页数）。**生产与自测都不许写死下标**（`bar_index_of_step()`/`stack_index_of_step()`/`panel_host_of_step()`）；⚠`_refresh_preview(index)` 收**栈页号**。⚠每层界面都必须问图（步骤条格子与任务列表胶囊＝`task_slots`，**别写死 `for stage in STAGES`**）。
- ⚠⚠**「是否拼版」＝三判据**：①在流程里②`area==1`③面板底部开关（`imposition_active`＝**用户意图**）；全过＝`imposition_effective()`，**取图来源/状态机跳过/步骤条生效态一律认它**。⚠`area` 是前提不是开关；**置灰+说明、置灰时保留并回填勾选**。⚠⚠**界面与执行必须同一判据**。
- ⚠⚠**"这一步缺什么输入"唯一判据**＝`TaskDetailPage._missing_input_kind()`→`"pdf"`/`"images"`/`""`（**PDF 优先**）；**高亮/红字/提示层/执行守卫/toast 全读它**。⚠**源三态**：`source_path is None`＝还没选（空壳，**不弹错误框**）／文件丢了（红错框）／正常。⚠⚠**`Path("")` 是 `"."`、`exists()` 为真**——绝不能只写 `exists()`。
- ⚠⚠**「输入入口红框」（常驻）与「缺输入才亮」（动态）是两套**：常驻＝`ui/widgets.py::mark_input_entry(button)`；⚠动态灭时 `setStyleSheet("")` **会连常驻红框一起抹**⇒`_refresh_source_actions` 先走动态、再**无条件重贴**；**同一按钮只能选一套**。⚠判红框**别看 `border`**（自带 border）＝`str(theme.DANGER) in styleSheet()`。
- ⚠⚠**`getOpenFileNames` 选不了目录**⇒"整目录导入"必须**独立入口**（`insert_folder_requested`＋📁 按钮→`getExistingDirectory`）；⚠**别只改 filter**；提示层加 **`pick_kind`**、`MissingSourcePrompt.picked`＝**`Signal(str)`**（⚠PySide6 不容忍槽签名不匹配⇒自测 `lambda kind="": ...`）。⚠⚠**插图前必判"源已在目标目录里"**＝`source.resolve().parent == target_dir.resolve()`（**必须 `resolve()`**），否则重名避让会把同一张图复制成 `xxx-1.jpg`。
- ⚠⚠**改名不断绑**（阶段身份是节点属性 `guji:stage`，名字只是标签）；⚠⚠**条件开关从 spec 派生**；⚠**读不到流程给空、不伪造**。⚠⚠**流程读不出来必须让用户看见**（`flow_degraded_reason()`＋弹**一次**）。⚠⚠**连线表也可能被硬编码掩盖**（`SUPPLIERS["imposition"]["pages"]` 曾错写 `"extract"` 而页面写死读 `stages/rembg`）⇒判据是**业务事实**。

## 进程/存储 · 文档地图
- 主进程不载 cv2/torch/PyMuPDF；每阶段一 worker 子进程，stdout＝**JSON Lines**（started/progress/finished/…），由 `core.reporter.Reporter` 上报，**不解析中文提示**。数据根 `~/Documents/guji` 纯 JSON 无库（`tasks/<0001>/{pages,runs,boxes,sizes,print,drafts,flow.bpmn,thumbnails,stages/*}`/`singletask/<子任务>/…`）。拼版合成 `desktop/services/imposition.py`；导航壳层 `desktop/shell.py`（⚠`TaskDetailPage.set_task` 必须返 True，否则导航切不过去）。
- 文档：`docs/guide/*`用法｜`dev/architecture.md`架构/进程模型｜`docs/dev/gui/gui-architecture.md`桌面端｜`gui-technical-spec.md`Worker协议/JSON/area｜`gui-ui-system.md`**改界面必读**｜`io_path_rules.md`路径｜`docs/functions/*.md`命令手册｜`api/*.md`签名（自动生成禁手改）｜`tasks/bpm.md`**BPM 口径与坑**。
