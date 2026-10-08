# gujitools 记忆

古籍重製 PDF→提图→检测框→去底色→生成PDF。双入口共用算法：`cli.py`(打包`guji`)/`desktop.py`(PySide6+qfluentwidgets)。分层`utils←core←{cli,functions,desktop}`**严格单向**。⚠`docs/**`基准 main，本分支**以代码为准**。⚠本文件有上限，**新增先删旧的**；过程细节见 `2026-10-*.md`。

## 提交纪律
⚠️长期大量未提交在制品。**AI 禁止自动 `git commit`**（用户明令）。完成只汇报 `git status`/diff，等用户说"提交"；说"撤回"用 `git reset --soft HEAD~N`（**绝不 `--hard`/`checkout --`/`restore`**）。提交前：①`git diff > /tmp/b.patch` **加**逐个 `cp` 未跟踪文件；②跑相关自测；③`git add -A` 后 `git diff --cached --name-only | grep -E "_out/|\.png$|\.log$"` 兜产物。⚠自测退出码 **127 是伪错误**（末段 `QThread: Destroyed`）且会**吃掉收尾一批模块**⇒比对 `--list` 计划数 vs 日志 `==标题==` 数，再用 `--only` 补跑。

## 临时文件落点（2026-10-07 定）
**测试用例只进 `tests/selftests/<名>.py`**（须带 `NAME`/`TITLE`/`DEPENDS`）；探针/截图放 `tests/`；**禁止仓库根新建测试脚本**。**测试临时数据一律落 `tests/tmp/`**（唯一落点 `tests/tmpdir.py`：`from tests.tmpdir import temp_dir`→`temp_dir("前缀_")`；存量入口顶部调一次 `install()`——它把 `tempfile.tempdir` **和** `TMPDIR/TEMP/TMP` 一起指过去（worker 子进程也覆盖），必须早于任何 `tempfile` 调用；收工 `clean()`）。**临时脚本/日志/JSON dump 一律放 `_scratch/`，收工前删净**——被 `.gitignore` 的 `_*/` **整目录**忽略。⚠`_*/` 只忽略**目录**、不忽略**文件**⇒根目录散落的 `_pwrun.py`/`_selftests.log` 会被 `git add -A` 收走。⚠**别往 `.gitignore` 补 `_*.py`**（会匹配 `__init__.py`）。收工自查 `git status --short` 无 `??` 临时文件。

## 事实来源（别另写一份，漂移必出 bug）
- CLI参数`core/command_spec.py`｜桌面默认值`components/panels/params_spec.py`｜色距字号`ui/theme.py`｜JSON`store/json_io.py`(临时文件+`os.replace`)。
- 框几何`utils/box_geometry.py`：半幅恒2槽[左,右]/整幅恒1槽，下游靠槽数辨形态；绘制`box_draw.draw_slots`；排版`page_layout.py`；页序`sort_utils.pdf_custom_sort_key`。
- 步骤`steps/spec.py::SPECS`唯一(`STEP_KEYS`/`FLOW_STAGES`/`OPTIONAL_STEPS`/`NAV_STEPS`/`PANEL_CLASSES` 全派生；`role`⊥`nav`)。页面内查`ports.spec_for_stage(stage)`，⚠别用`spec_by_key`(`rembg_submit`→None)。阶段中文名一律走`ports.stage_label()`。

## BPM 流程（唯一真源＝文件）
- `tasks/<id>/flow.bpmn`＋模板文件是唯一真源——页面照文件渲染、顺序走**状态机**。`steps/bpmn_diagram.py::FlowDiagram` 读/写整图；`stage_order()`=**Kahn 拓扑序**（⚠别用 BFS：分叉"短路"会让 `print` 排在 `imposition` 前）。
- `bpmn_view.py::BpmnView`(照文件画)；`bpmn_editor.py::BpmnEditor`(拖拽/连线/选中**节点与连线**/双击改名)；`bpmn_editor_panel.py`+`bpmn_palette.py`(拖进画布即加一步)；`steps/scheduler.py::Scheduler`(顺序取拓扑序、跳过看`CONDITIONS`)。
- 弹窗`flow_dialog.py::FlowPanel`(打开即编辑态)+详情页入口`flow_mixin.py`；`store.task_diagram/save_task_diagram`(⚠save 必须清 `_flow_cache`)。
- **默认流程=`desktop/static/task_default.bpmn`**，自定义初值=`task_detail.bpmn`，**都是手工真源**。⚠**不许代码派生默认流程**（旧 `gen_default_bpmn.py` 从 `ports.SUPPLIERS` 派生＝图成一团乱线），该工具现在**只校验**。
- ⚠**只有 `task` 节点才映射运行阶段**（`endEvent` 常叫「生成PDF」，按名查表会误认成 `print`）；阶段按**节点名**接回（`STAGE_ALIASES`）。⚠⚠**端口依赖 ≠ 流程连线**（`(consumer,port)→supplier` 是"取谁的文件"，`sequenceFlow` 是"先做哪一步"）。
- **状态机已接线**：`store.task_scheduler(tid,imposition_active)`(唯一查询面)／`store.stage_supplier()`／`stale_chain.upstream_from_diagram()`／`runner` 守卫(不在流程里的阶段直接拒)。
- ⚠**每层界面都必须问图**：步骤条格子与**任务列表子任务胶囊**＝`task_slots`（**别写死 `for stage in STAGES`**）；拼版节点可见性＝图里有没有那一格。

## 页面栈
`desktop/pages/createtask/page.py::CreateTaskPage`(路由`create`)+`desktop/pages/taskflow/page.py::TaskFlowPage`(路由`flow`)。⚠两页都**没有导航条目**，`_SUBROUTES` 高亮统一留在「任务管理」。⚠**组件内嵌后不许自己关窗**：`CreateTaskPanel.reject()` 只发 `cancelled`；`FlowPanel` 要 `close_window=False`+`embedded=True`。⚠Signal 只能声明在 **QWidget 子类**（Mixin 里发不出去），故 `flow_edit_requested` 在 `page.py::TaskDetailPage`。⚠**二级页是惰性单例⇒每次进入必须复位**（`open_create` 调 `CreateTaskPage.reset()`，复位放在"已在这一页"判断**之前**）；`CreateTaskPanel.reset` 里**先清 checkbox 再换自定义图**。
- ⚠⚠**组件内嵌进页面后 `self.window()` 是主窗口**——`CreateTaskPanel.submit()` 曾 `self.window().close()` 把关掉整个程序。面板一律**只发信号**。
- 独立页左栏=缩略图条+大图→`modules/thumb_source.py::ThumbSourceMixin`（⚠别自起`PreviewWorker`/`ImageThumbCacheWorker`；拼图页**不继承**只复用`singletask_dir`）；普通步骤页`modules/base.py::StepModulePage`。缓存`files.image_thumb_cache_path`键含文件大小。
- ⚠判"控件是不是在某个状态"用 **`isHidden()`** 不用 `isVisible()`（后者祖先不可见时恒 False）；且**方向别反**（`isHidden()` True＝已隐藏＝不在编辑态 ⇒ 才 return）。

## 关键契约
- ⚠⚠**「源 PDF」↔「提取图片」成对**。源 PDF 在图上是 **`startEvent`、没有 `stage`**（`SUPPLY_TASK_SOURCE`）⇒**不能按 stage 认**；`ports.source_pdf_node_ids()` 走「事件类型**或**节点名」。配对唯一真源＝`ports.paired_node_for_stage(diagram, node_id)`（**双向**）——⚠别写死 `"extract"↔"startEvent"`。⚠**删除有两条路径都要成对**：`ask_delete_selected()`（工具栏）与 `remove_selected()`（**键盘 Delete**）——凡"某动作要联动"**先 grep 有几条入口**。返回 `None` 时调用方**必须自己再判**。
- ⚠⚠**页头 PDF 图标：只在"流程压根不吃 PDF"时整颗藏起来**（`ports.flow_needs_source_pdf()`，抽成 `manifest._flow_needs_source_pdf()` 复用、**别两处各判**）。⚠**空壳任务**（还没选 PDF 但流程要 PDF）必须**恒显示**。构造期无 `task_id` 给 `True`。自测＝`step_ports` 第8节＋`flow_ui` 第18节（⚠后者**必须替掉 `QMessageBox.question`** 否则真弹模态＝看门狗 `os._exit(3)`）。
- ⚠⚠**「输入入口红框」与「缺输入才亮」是两套，会互相覆盖**：
  - 常驻红框＝**标识入口**（页头插图/插目录、预览区＋/📁）⇒ `ui/widgets.py::mark_input_entry(button)`（**两处用**故收敛成一份）。🗑删除、流程、改名**不标红**。
  - 动态高亮＝缺什么才亮、补上就灭＝`manifest._set_tool_highlight`。⚠它灭时 `setStyleSheet("")` **会把常驻红框一起抹掉**⇒ `_refresh_source_actions` 先走动态、再**无条件重贴** `mark_input_entry(insert)`。别"优化"成只用一个；**同一按钮只能选一套**。
  - ⚠⚠**自测判红框不能看有没有 `border`**：qfluentwidgets ToolButton **自带** border（对所有按钮为真）。正确＝`str(theme.DANGER) in styleSheet()`。也**别断言 `styleSheet()==""`**，用**红字消失**（`source_warning.isHidden()`）判动态高亮。
- ⚠⚠**入口节点：没有上游也要有输入**（"第一个节点一定要有输入可用"）。图片输入原只有上游 `pages` 一条来路，把「检测文本框」放第一位时连坏三处。**唯一实现**＝`ports.resolve_input_with_entry(task_dir, stage, port, supplier)`：供应方 `None` **且该阶段确实吃 `pages`** ⇒ 回落 `ports.task_input_dir()`＝`stages/input/`（落点 `ports.TASK_INPUT_LOCATION` 唯一声明）；`store.stage_input()` 调它，`store.task_input_dir()` 是页面侧入口。
  - ⚠**`boxes`/`pdf` 不许回落**。⚠判据落在**端口自己**身上（`port=="pages" and "pages" in stage_inputs(stage)`），**别写 `port in stage_inputs(stage)`**——`rembg` 声明 `("pages","boxes")`，那种写法会让它的 boxes 也回落（自测 `step_ports` 第7节钉住）。
  - ⚠**插图目标目录与执行读目录必须同源**（都走 `store.stage_input`）＝`manifest._current_stage_input_dir()`。⚠`_sync_manifest_to_input()` **只在清单为空时**重建。⚠这条只解决"没有上游"，**不解决"上游还没跑"**（那是 `Scheduler`/`missing_stages`）。自测＝`step_ports` 第7节＋`flow_ui` 第15/16节。
- ⚠⚠**`getOpenFileNames` 选不了目录**（原生 Windows 框只收文件）——"整目录导入"必须**独立入口**：`ImageViewerWidget.insert_folder_requested`＋📁 按钮（`ToolButton(FIF.FOLDER)`，仅 `editable=True` 建）→ `manifest.insert_pages_from_folder()`＝`getExistingDirectory`。⚠**别只改 filter 写成"图片与文件夹"**。两入口共用 `_insert_paths`；目录展开**复用 `StepSpec.collect_files`**，spec 取**当前阶段**的（`ports.spec_for_stage(current_stage())`）。
- ⚠⚠**按钮写"选目录"就必须真开目录框**：给提示层内容加 **`pick_kind`**（`"folder"`/`"files"`），`MissingSourcePrompt.picked`＝**`Signal(str)`** 发宿主，宿主 `_on_prompt_pick_input(kind)` 分流。⚠**PySide6 不容忍槽签名不匹配**⇒自测收集器必须 `lambda kind="": ...`。⚠组件**自己不知道开哪种框**，只传意图。自测要**真点一次按钮**记录开的哪个框。
- ⚠⚠**插图/复制前必判"源已在目标目录里"**＝`source.resolve().parent == target_dir.resolve()`（**必须 `resolve()`**）：否则重名避让会把同一张图复制成 `xxx-1.jpg`。命中**跳过复制**直接进清单，清单侧**按 `str(file)` 去重**（`_append_pages_to_manifest` 返回**实际新增条数**）。⚠**别把"外部同内容再导入"当 bug**（任务要自包含）；要防的是选了**输入目录本身**。自测替身 `QFileDialog.getExistingDirectory` **必须 try/finally 恢复**。
- ⚠⚠**`Path("")` 是 `"."`，`exists()` 为真**——判"有没有源文件"绝不能只写 `exists()`。**源三态**：`source_path is None`=**还没选**（空壳，页头写「尚未选择 PDF」+补选按钮，**不弹错误框**）／路径在但文件不在=**文件丢了**（红错框）／正常。索引里空源存**空串**不存 `"."`。补选走 `store.set_task_source`（**先复制进任务目录再改索引**）。
- ⚠**创建任务：PDF 非必需、名字两级回落**：`can_submit()` 恒 True；空 path ⇒ `start_create` **跳过整条指纹/查重链**且**不排** `SourceThumbnailsWorker`。名字＝**用户填的 → pdf 文件名 → `任务#<实际 task_id>`**。⚠默认名序号必须用 `create_task` 里**实际分配到的** `task_id` 现算（`default_task_name()` 只是 placeholder）。
- ⚠**"这一步缺什么输入"只有一个判据**＝`TaskDetailPage._missing_input_kind()`→ `"pdf"`/`"images"`/`""`（**PDF 优先**）。⚠**高亮/红字/提示层/执行守卫/toast 全读它**。`"pdf"`＝`ports.flow_needs_source_pdf`（`StepSpec.needs_source_pdf()`＝端口 `inputs` 含 `"pdf"`）AND `source_path is None`（**创建页与详情页共用**）；`"images"`＝`ports.flow_needs_entry_images` AND `stages/input/` 无图。⚠**"入口"是图上的性质**＝`is_entry_stage`（问"有没有上游"），不是"第一个是不是 extract"。⚠执行守卫问"这一步输入齐不齐"（`runner._stage_inputs_ready`），**不是**"有没有 PDF"。⚠每次进入都弹提示层，**复用前必须 `configure()`**。
- ⚠**换/补选源 PDF 必须先算指纹再决定**（`manifest.py::_on_source_hash_ready`）：①==本任务 hash ⇒ 不动；②`find_tasks` 命中别的任务 ⇒ **弹窗问"是否仍然使用"**（⚠**不是一律拒绝**）；③新 PDF ⇒ 确认后才 `_apply_source`。⚠指纹**走后台** `HashWorker`+期间**锁按钮**；⚠`set_task_source` **必须写指纹**。⚠清产物**连待写标记一起清**（`_draft_dirty`/`_pending_sizes`/`_pending_boxes`）。⚠**`MessageBox` 是纯文本不解析 markdown**。
- ⚠**启动不再自动跳回上次任务**（2026-10-06 用户改口径）：`main()` 无恢复入口，一律停列表页。任务级「上次停留的步骤」照旧（`_initial_stage_index()`）；根 `ui.json` 的 `last_task` 照写。自测 `last_stage.py` 第9节钉死"别把 `_restore_last_task`/`RESTORE_DELAY_MS` 留回来"。
- ⚠**singletask≠taskdetail**：共用组件/worker 但**缓存根各归各**（`singletask/<子任务>/` vs `tasks/<id>/thumbnails/{source,print,imposition}`），**禁止借道**。
- 第四步取图=第三步「提交本次任务」成品图：改去底色结果/area/border⇒**必须重新提交**。detect 页交付 `<输出目录>/boxes.json` 与 `tasks/<id>/boxes.json` 逐字段一致。`LogPanel.log()`=append。
- `ImageViewerWidget` 两形态：图片(`set_images`/`set_thumb_source`)、PDF 页(`set_pdf_source`+`begin_pdf_pages`+`set_pdf_thumb`)。⚠`set_images` 须先 `_clear_page_source()`；`gen` 代际号防串页。
- ⚠⚠**`viewers/` 六个大文件已拆同名子包**（`image_editor/`、`image_zoom_dialog/`、`print_preview/`、`image_viewer/`、`image_view/`、`rembg_viewer/`；全量 re-export）：改前先读 `tests/selftests/{image_editor,image_zoom_dialog,viewer}_split.py`——**Mixin 间不许同名成员**（MRO 静默遮蔽），成员换落点必须同步 `_EXPECTED_HOME`、跨 Mixin 调用要登记白名单；**打桩看「定义处」的模块**（打包级属性是假绿）。每包一个**类型检查期宿主面 `_host.py`**（`else: XHost = object`，运行期 MRO 零改动），改成员必须同步 `_context.check_type_only_host()` 的**四条不变量**（宿主面**恰好** = 主类＋各 Mixin 成员；⚠`__init__` 绝不进宿主面）。设计见 `docs/dev/refactor-modularity.md` §9/§10。
- ⚠⚠**图片编辑器版面＝顶部功能选择＋右侧参数面板**（2026-10-08 用户定，`dialog_toolbar.py`）：`_build_toolbar_row`(动作行＋功能行) / `_build_side_panel`(功能名＋`_option_host`＋`history_list`)，`_page_*` 一律收 `QVBoxLayout`、参数**竖排**（旧版挤在一行会横向溢出）。⚠`_build_side_panel` 必须先于 `_build_toolbar_row`（后者末尾 `_set_tool` 就往参数区插页）。**编辑实时生效**：「应用裁剪/应用变换/插入文字」三个按钮已删——裁剪/变换**松手即应用**（画布发 `crop_committed`/`transform_committed` → 弹窗 `_apply_crop`/`_commit_transform`；⚠拖轴心 `xf_pivot` **不发**），文字块＝画布上的预览、切功能/「完成」时自动写入。⚠选区没变时 `_apply_crop` 必须**短路**（点一下不该留空撤销步）。**唯一保留的确认＝覆盖原图**。
- ⚠⚠**撤销＝带名字的步骤时间轴**（`dialog_undo.py`，右侧「编辑历史」可点选跳转）：`_undo`(变更前快照)＋`_redo`＋`_labels`，不变量 **`len(_labels) == len(_undo)+len(_redo)`**，`_labels[i]`＝"改掉 `_undo[i]` 这一步"的名字；节点 0 的名字＝`_origin_label`（栈被截断后换成被丢掉那一步的名字）。⚠**只动 `_undo`/`_redo` 不动 `_labels` 就会让历史点错格**。跳转＝连按 undo/redo，**必须有"推不动就停"的兜底**（文字编辑中 `_undo_now` 会主动让位）；`_history_syncing` 是 `currentRowChanged` 的闸门（否则自己的 `clear()`＋`setCurrentRow` 会被当成用户点击、一路撤到底）。
- ⚠️⚠**扭曲笔刷＝位移场累积 + 区域重采样**（`image_editor/distortion.py`）。三条硬口径：①`StrokeSampler._carry` 是"距上一落点已走的距离"，**记账必须写 `carry = length-(needed-step)`，不许 `+= max(0, length-walked)`**——累加式会让 carry 单调增长，一旦 > step 就每段抛上百个飞点（"拖越久越卡、脏区 2000 px、每帧 56 ms"的机制性原因）；②预览按**精确脏矩形**渲染（⚠别凑整 128 瓦片，多算 10 倍），且单帧渲染量受 `DISTORT_PREVIEW_RENDER_PIXELS` 约束、超出的脏区**挂回** `_distort_preview_dirty_rect` 给下一帧；③提交只渲染 `field.active_rect`，**与拖动时长解耦**，> 4 Mpx 走后台+进度。自测＝`image_editor` 第 2c 节＋预览预算节。
- print 页：未生成=源图缩略图，生成后=产物 PDF 页缩略图。`RembgPreviewWidget.set_images(paths, rembg_dir)`**第二参是结果目录**。
- **编辑生效链**：`ZoomPopupMixin`→`ImageEditorDialog(save_back=True)`→`overwrite_image_file`→`image_saved`；独立页由 `ThumbSourceMixin._wire_source_edit()` 接（`_reload_edited_thumb` 要**先 pop `_thumb_cache_ready[path]` 再 `refresh_page`**）；拼图页产物 `singletask/拼图/edited/<页>.png`。
- **「完成」覆盖确认**：`_confirm_overwrite()` 在**任何烘焙前**问一句；⚠`_finishing` 须先于确认框置位。四个短路 `return True`：`not save_back`/`not target_exists`/`_image==_original`/`MessageBox` 抛异常。⚠`editor.target_name` 只能做属性——**给会替身化的函数加参数前先 grep 替身签名**。
- **落地口径**：独立任务页「应用」**一律落地实体文件**；任务流程**看目标**——有 `ZoomTarget.edit_path` 才落地。判据是 `edit_path`。

## 硬规则
- ⚠⚠⚠**图必须压过静态连线表**（2026-10-06 掉头）。`ports.SUPPLIERS`＝**写死的默认流程连线**，只能兜底。`store.stage_supplier`：①**不声明的端口⇒没有这个输入**（`ports.stage_inputs` 唯一真源，**必须在查图之前**）②**图给出唯一答案⇒图说了算**（`FlowDiagram.producers_of`）③**图说不清⇒退回静态声明+条件开关**。⚠③是**确定性要求**：默认流程带「是否拼版」网关，两条**实线**都进「PDF排版」，必须靠 `print_pages_supplier(imposition_active)` 运行态选。⚠`producers_of` **遇到产出方就停**。自测＝`step_ports` 第9d节。
- ⚠⚠**改名不断绑**：阶段身份是节点属性（落盘 `guji:stage`，`load` 优先读它），名字只是显示标签。认得出的名字换绑、认不出的只改显示保留原阶段、本来没阶段的不许凭空接上；解绑请删节点。`stage_unbound` 已删。自测＝`flow_ui`。
- ⚠⚠**条件开关从 spec 派生**：`scheduler.CONDITIONS`＝`{步骤:步骤 for role=="optional"}`，开关走 `store.step_enabled`（`drafts/<步骤>.json` 的 `enabled`）＋`store.scheduler_flags`。唯一特例＝`imposition` 用传入值覆盖（`imposition_effective()`）。自测＝`step_ports` 第9e节。
- ⚠⚠**读不到流程给空，不伪造**：`runs.flow_stages` 异常曾回 `set(STAGES)`、`task_rows_worker._stage_chips` 曾编四个默认胶囊 ⇒ 坏流程图的任务列表冒默认阶段。两处都给空。自测＝`flow_bpm` chips⑤。
- ⚠⚠⚠**步骤条下标只有一种语义＝格序 `bar_index`**（2026-10-06 血案）。`StepItem.index`/`set_step_status`/`mark_completed`/`set_current`/`current_changed`/`imposition_index` 全是格序；宿主传 `bar_indices=`＋`optional_bar_index=`（`view._bar_step_indices()`/`_optional_bar_index()`）。⚠徽标数字**仍按真实步骤序**。⚠自测必须逐个 `item.clicked.emit(item.index)` **真点**。自测＝`detail_bpm_render` 第5节。
- ⚠⚠**取"别的步骤的面板"只有 `panel_host_of_step(step)` 一个入口**：`control_stack.widget(2)` 恒是「图片去底色」靠**静态步骤表顺序**。返回 `None` 时调用方自己降级，**别兜一个"随便哪一步"**。
- ⚠⚠**左侧列表缩略图"逐张到齐"回填不许整列重灌**（用户报"拼板阶段程序卡死"）：旧实现 380页×380≈7.2万次 `set_thumb`、主线程占住 27.5s。现在只贴刚到那条（`ImpositionViewWidget.set_thumb_at`），定位走 `_imposition_rep_index` 缓存＝**0.06s**。`ImpositionPageList.set_thumb` 另加"同一张早退"（`QPixmap.cacheKey()`）。自测钉**调用形状**。
- ⚠⚠**流程读不出来必须让用户看见**：`store.task_diagram` 三种形态都**静默**回落默认模板（文件缺失／XML坏／解析得动但一个步骤名都认不出）。回落经 `store.flow_degraded_reason()` 记原因＋`page._warn_if_flow_degraded` 弹**一次**。⚠"没有流程"只有一个表示＝`load_default_diagram()`（空图）＋告警；`task_flow`/`save_task_flow` 已删。⚠降级表**必须每实例一份**。
- ⚠⚠**连线表也可能被硬编码掩盖**：`SUPPLIERS["imposition"]["pages"]` 曾错写 `"extract"`，而页面写死读 `stages/rembg` ⇒ 一直看着是对的。判据＝业务事实（`-l/-r` 半页对只由 area=1 去底色产出；`task_default.bpmn` 里拼板排在去底色**之后**）。
- ⚠⚠**三套下标最易错**：①步骤条格序 `bar_index`（**含可选节点占位**）；②栈页号 `stack_index`（`control_stack`/`preview_stack` 物理页号）；③`control_stack.currentIndex()`。`_select_stage()` 收**格序**。
  - ⚠⚠**`stack_index` 必须"查静态表"不能"数当前几格"**：两栈按 `FLOW_STAGES + OPTIONAL_STEPS` **一次建好固定页数**。正确＝`FlowDiagram.stage_slots()` 里 `stack_index = 静态顺序里的位置`。
  - ⚠**自测与生产一律不许写死下标**：查 `bar_index_of_step()`/`stack_index_of_step()`/`panel_host_of_step()`。
  - ⚠⚠**`_refresh_preview(index)` 入参是「栈页号」**（内部走 `stage_at_stack_index`）⇒ `_select_stage` 必须传 `self.stack_index_of(index)`；`runner.py` 那两处 `_refresh_preview(1)/(3)` 改 `stack_index_of_step("detect"/"print")`。**同族坑**：`manifest._active_page_viewer` 曾把栈页号当格序比；`_refresh_downstream_preview(step)` 统一处理"改完上游顺手刷下游"。
- ⚠**重建步骤条/槽位界面时"旧下标"必须用"旧快照"解析**（报障"编辑流程后顶部流程图没立即更新"）。正解＝步骤条**自己记下建时那份槽位快照**（`_build_step_bar` 里 `self._step_bar_slots`），重建时用 `getattr(..., None)` 取。
  - ⚠配套：壳层 `open_detail` 在 `set_task` 返 False（**正在跑子任务**）时原来**什么都不做**⇒从流程页保存回来被**留在流程页**。已修：不 busy 也 `setCurrentWidget`＋`page._toast`（⚠**壳层没有 `_toast`**，借详情页的）。
  - ⚠⚠⚠`task_diagram`/`flow_slots()` **都无缓存**（每次读盘），`save_task_diagram` 清 `_flow_cache`——"改了没反应"**别往缓存上查**。自测＝`flow_ui` 第14节。
- ⚠⚠**自测"这行代码改前会红吗"必须双向验证**。踩过**三种假绿/假红**：①只验"详情页在前台"——它本来就在⇒恒真；②`_toast(kind,title,content)` 标题是**第二个**参数，写 `item[0]` 恒 False；③在完整 `set_task` 链路上验"高亮别跳格"改前也绿（末尾 `_select_stage` 掩盖了错位，须**直接调 `_rebuild_step_bar()`**）。⚠替身要在 `shell.close()` **之前**用完。⚠**别用 `git stash`** 做这件事。
- ⚠⚠**「是否拼版」是三个判据**：①在不在流程里＝`bar_index_of_step("imposition")`②有没有意义＝`area==1`③要不要真跑＝面板底部开关（`imposition_active`＝**用户意图**）。三者全过＝`imposition_effective()`；取图来源/状态机跳过/步骤条生效态**一律认 effective**。
  - ⚠⚠**`area` 是适用前提不是"显示开关"**：`area=1` 产出**成对** `-l`/`-r`。⚠处置是**置灰+说明**不是隐藏；⚠**置灰时保留勾选**且回填勾选态。
  - ⚠⚠**界面与执行必须同一判据**：只改 UI 而 `runner`/`print_list` 仍认"勾没勾" ⇒ 界面说 A、执行做 B。
- ⚠⚠**图上"画了但还没功能"的节点不许静默丢掉**：占一格＋`StageSlot.mapped=False`＋`stack_index=NO_PAGE(-1)`，步骤条画灰节点、**副标题**写「未接入」，`_select_stage` 在 `set_current` **之前**拦下提示。
- ⚠**`stage_states` 键只能加不能删**（调用方硬索引 `["rembg"]`）⇒ 保留四静态键＋`in_flow` 标记；要"只列流程里的"走 `flow_stages()`。⚠**沿图回退取产物要 `fold_forward` 折叠到同格最靠后的动作**（直接取 `rembg` 会拿实时预览目录）。
- ⚠⚠**qfluentwidgets 的 `Dialog` 放不下成套面板**（第二参是**字符串**、**没有** `viewLayout()`）⇒ 走 `components/dialog_shell.py::shell_dialog`。⚠**"点按钮就炸、自测却全绿"先怀疑外壳**（自测都直接实例化 `*Panel`）。⚠**面板的 `self.close()` 关不掉弹窗**⇒用 `self.window().close()`。⚠`qfluentwidgets.PushButton.clicked` 发**无参**信号，按 `(checked: bool)` 接会 TypeError。
- ⚠**编辑器必须有工具栏**：`BpmnEditor` 只是画布，无按钮调用的动作＝**死代码**（用户报"无法编辑"的根因）。画布要有**尺寸下限**。⚠`NodePalette` 置灰项光靠 `ItemIsEnabled` **看不出区别**，须显式 `setForeground(INK_DISABLED)`。
- ⚠**自定义初值缺失会静默回落默认**⇒勾「自定义」与「默认」长得一样；`custom_init_missing()` 有告警。
- ⚠**页内浮层的重铺时机**：`open_detail` 先 `set_task()` 后 `setCurrentWidget()` ⇒ `set_task` 里弹层时页面**还没布局**⇒浮层**零高度**＝"没弹"，第二次进却正常。修法三处：靠 **`showEvent`** 重铺／`resizeEvent` **不判 `isVisible()`**／`_reanchor` 上沿>页高 60% 放弃。⚠`showEvent` **先判 `task_id`**。⚠**这类时序 bug 自测天生抓不到**，必须走**壳层真实入口**＋断言"第一次"。
- ⚠⚠⚠⚠**离屏自测四件套**：①**绝不真弹模态**（`exec()`＝挂住整轮，看门狗 `os._exit(3)`）；拖拽 QGraphicsView 走 `QTest.mousePress`，自绘系走合成 `QMouseEvent` **直调**。②给 `set_task` 加新弹窗时**务必在 `tests/selftests/_context.py` 加公共旁路助手**（如 `silence_source_prompt(page)`）；包装助手**必须先把原方法抓在手里**再包一层，且**自己也要过判据再记录**。③判"提示层没出现"要看**实体是否被建出来**。④Qt 信号 `connect` 时绑死 callable——要拦副作用必须**直连信号**，**不能**靠 `page._on_pick_source = 替身`。
- ⚠⚠**"控件有没有被挡住/能不能点"**：❌`parentWidget().childAt()`（只在直接子控件找，遮罩是页面级）；⚠`QApplication.widgetAt` 离屏下**对按钮返回 None**；✅权威＝**`QTest.mouseClick` 真点一下**看槽有没有被调。⚠`show()` 是**异步**，不跑 `processEvents` 会点空（假红）。⚠`QRect.bottom()` 是**包含式**。
- ⚠⚠⚠**布局在 `set_task` 末尾是"未生效"状态**：`_rebuild_step_bar()` 换控件后 Qt 布局**延迟**生效 ⇒ 步骤条 geometry 还是 **640×480**、`isHidden()` True、`mapTo` 得 **0**，**`layout.activate()` 也不管用**。要取"某控件在哪"必须用**稳定的兄弟控件**（如页头 Card）算：`layout.itemAt(0).geometry().bottom() + layout.spacing()`。
- ⚠`Card`（`ui/widgets.py`）**自带 layout，暴露为 `card.box`**——再建第二个 `QVBoxLayout(card)` 会被忽略、控件**留不下**（卡片空成 32×32）。⚠别在卡片外再套"中层容器+addStretch"。⚠卡片高度**用 `heightForWidth`**。
- 界面：控件`paintEvent`自绘不引样式表；下拉`widgets.combo_box()`；窗口尺寸`ui/window_size.apply_window_size`。PySide6 **不导出** `QWIDGETSIZE_MAX`，用 `(1<<24)-1`。⚠高分屏绝不手 `painter.scale(dpr,dpr)`。
- 跨线程用 `desktop.workers.connect_queued`。⚠**`QThread.run()` 必须 try/except**（异常逃出不杀进程，`result=None`⇒上层当"用户取消"）。`run_with_progress` 收尾在读 cancelled/result 之后并 try/finally。
- ⚠GUI 主进程不许进重依赖(`functions.detect`→cv2)：主进程用的纯规则放 utils 且不 import functions（`box_geometry` 有 AST 守卫）。中文路径勿直用 `cv2.imread/imwrite`，走 `utils.image_io`。⚠按页号命名的缓存不能跨书共用。
- ⚠「点空白处」**直接**开选文件对话框。⚠**"资源管理器"=原生 `QFileDialog`**（**不设** `DontUseNativeDialog`），不是 `explorer.exe`。
- ⚠回滚/二分未提交在制品**禁用 `git checkout HEAD -- <路径>`**：用 Python 按标记字符串切片替换，先备份。
- ⚠`SourceZone` 内有真按钮子控件：几何靠 `_relayout_buttons()`；`accepts_dir=False` 不摆目录按钮；**入口是主路径必须画成按钮**；`_open_dialog` 须 try/except 转 `rejected`。
- ⚠"重跑同一个源"不是"冲突"：收录尾"已存在就跳过"须先 `filecmp.cmp(shallow=False)` 比内容。⚠自测勿手写 JPEG/PNG 十六进制。⚠**传路径的公开 API 须在边界 `Path()` 收口**。
- ⚠**同一输出目录只准一个写入者**（`stages/imposition` 靠 `_COMPOSE_LOCK`+`_save_page_atomic`）。⚠自我续期的 `QTimer.singleShot(0)`＝CPU 风暴：分批解码带间隔(`picker.THUMB_GAP_MS=150`)。
- ⚠`set_task` 走 `_rebuild_step_bar` **重建整个步骤条**⇒自测跨 `set_task` 缓存的 `step_bar.imposition_node` 是**已析构控件**。断言前重新取。

## 测试
`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE <py> -u tests/gui_selftest.py`。⚠必带 `-u`；勿用 `--only` 循环跑全量，一次全量+`--skip`(只接逗号串)；用例=`tests/selftests/*.py`（`NAME`/`DEPENDS`/`TITLE` 自动发现）。**运行器遇模块异常 re-raise 终止整轮**。
- ⚠⚠**别拿 PASS/FAIL 计数判断"我新加的断言跑了没"**：模块中途抛异常时**整轮终止**，计数停在半路。**判据＝日志里能 grep 到断言文本**。
- ⚠⚠**逐模块跑才能定位环境性红**：全量在第一个 FAIL 处终止。`--only <mod>` 循环记录 PASS/FAIL/ABORT 再归类。
- ⚠长跑末 `QThread: Destroyed` 硬中止**吃掉其后模块**⇒看 `[PASS]/[FAIL]`+核对模块清单，`--only` 补跑。跨模块残留异步回调会打后一模块 monkeypatch（单跑即绿⇒非回归）。
- 本机**环境性红**：缺 `static/guji.yaml`、缺**fpdf2**（整个 print 链）、缺 `guji.spec`、缺 ultralytics。⚠**本机 QProcess 一律 `FailedToStart`**⇒**所有真起 worker 子进程的模块都红**（第一道 `extract`，依赖链 `history`/`pages`/`detect`/`rembg`/`print`/… 全被连带）。跑全量前先 `grep -ln "guji.spec\|guji.yaml\|fpdf\|ultralytics" tests/selftests/*.py` 扫环境性红清单。解释器 `C:\Users\zunkun\anaconda3\python.exe`（managed 3.13 无 PySide6）。
- 改 `functions/`|`utils/` 必跑 `tests/reporter_cli_parity.py`|`reporter_worker_e2e.py`|`cli_print_smoke.py`。文档 `tools/gen_api_docs.py --check`+`tools/check_docs.py`；视觉自查 `tests/gui_shot.py`、BPM 截图 `tests/bpm_shot.py`（出图后自行清理）。

## 进程/存储
- 主进程不载 cv2/torch/PyMuPDF；每阶段一 worker 子进程，stdout=**JSON Lines**(started/progress/log/page_boxes/page_size/finished/error/cancelled)，由 `core.reporter.Reporter` 上报，**不解析中文提示**。数据根 `~/Documents/guji` 纯 JSON 无库（`tasks.json`/`ui.json`/`tasks/<0001>/{pages,runs,boxes,sizes,print,drafts,flow.bpmn,thumbnails,stages/*}`/`singletask/<子任务>/{thumbnails,thumbs,edited}`）。拼版合成 `desktop/services/imposition.py`。
- 导航壳层 `desktop/shell.py`；⚠`TaskDetailPage.set_task` 必须返回 True 否则导航切不过去。列表页只发 `open_detail(str)` 信号。

## 文档地图
`docs/guide/*`用法｜`dev/architecture.md`架构/进程模型｜`docs/dev/gui/gui-architecture.md`桌面端细节｜`gui-technical-spec.md`Worker协议/JSON/area｜`gui-ui-system.md`**改界面必读**｜`docs/dev/io_path_rules.md`路径｜`docs/functions/*.md`命令手册｜`api/*.md`签名(自动生成禁手改)｜`tasks/bpm.md`**BPM 口径与坑**。历史坑位清单见 `2026-10-05.md` 附录。
