# gujitools 记忆

古籍重製 PDF→提图→检测框→去底色→生成PDF。双入口共用算法：`cli.py`(打包`guji`)/`desktop.py`(PySide6+qfluentwidgets)。分层`utils←core←{cli,functions,desktop}`**严格单向**。⚠`docs/**`基准 main，本分支**以代码为准**；过程见`2026-10-0*.md`。⚠本文件有上限，**新增先删旧的**。

## 提交纪律
⚠️长期大量未提交在制品。**AI 禁止自动 `git commit`**。提交前：①`git diff > /tmp/b.patch` **加**逐个`cp`未跟踪文件；②跑相关自测；③`git add -A` 后 `git diff --cached --name-only | grep -E "_out/|\.png$|\.log$"` 兜产物。⚠自测退出码 **127 是伪错误**（末段`QThread: Destroyed`）且**会吃掉收尾一批模块**⇒必须比对 `--list` 计划数 vs 日志`==标题==`数再用 `--only` 补跑。⚠`git stash`验证"改前就红"是可用的，但 stash 会带走未跟踪文件的编译产物，注意 pop 回来。

## 事实来源（别另写一份，漂移必出 bug）
- CLI参数`core/command_spec.py`｜桌面默认值`components/panels/params_spec.py`｜色距字号`ui/theme.py`｜JSON`store/json_io.py`(临时文件+`os.replace`)。
- 框几何`utils/box_geometry.py`：半幅恒2槽[左,右]/整幅恒1槽，**下游靠槽数辨形态**；绘制统一`box_draw.draw_slots`；排版`page_layout.py`；页序`sort_utils.pdf_custom_sort_key`。
- 步骤`steps/spec.py::SPECS`唯一(`STEP_KEYS`/`FLOW_STAGES`/`OPTIONAL_STEPS`/`NAV_STEPS`/`PANEL_CLASSES` 全派生；`role`⊥`nav`)。页面内查`ports.spec_for_stage(stage)`，⚠别用`spec_by_key`(`rembg_submit`→None)。**阶段中文名一律走`ports.stage_label()`**。
- **BPM（2026-10-05 起，口径已掉头）**：⚠️**`tasks/<id>/flow.bpmn` 与两个模板文件是唯一真源**——页面**照文件渲染**、可直接编辑、运行顺序走**状态机**（用户："bpm 流程引擎太复杂"）。
  - `steps/bpmn_diagram.py::FlowDiagram` 读/写整张图（任意节点类型+DI坐标+折点+边标签+注释）；`stage_order()`=**Kahn 拓扑序**（⚠别用 BFS：分叉"短路"会让 `print` 排在 `imposition` 前）。
  - `bpmn_view.py::BpmnView`(照文件画：网关菱形/结束事件双圈/走文件折点)；`bpmn_editor.py::BpmnEditor`(拖拽/连线/选中**节点与连线**/双击改名)；`bpmn_editor_panel.py::BpmnEditorPanel`(工具栏+滚动画布+状态行)+`bpmn_palette.py::NodePalette`(固定节点面板，拖进画布即加一步)；`steps/scheduler.py::Scheduler`(状态机：顺序取拓扑序、跳过看 `CONDITIONS`)。
  - 弹窗`flow_dialog.py::FlowPanel`(打开即编辑态)+详情页入口`flow_mixin.py`；`store.task_diagram/save_task_diagram`(⚠save 必须清 `_flow_cache`)。
  - **默认流程=`desktop/static/task_default.bpmn`**，自定义初值=`task_detail.bpmn`，**两者都是手工真源**。⚠**不许代码派生默认流程**（旧 `gen_default_bpmn.py` 从 `ports.SUPPLIERS` 派生＝把端口依赖写成流程连线→图成一团乱线），该工具现在**只校验**。
  - ⚠️**只有 `task` 节点才映射运行阶段**（`endEvent` 常叫「生成PDF」，按名查表会误认成 `print`）；阶段按**节点名**接回（`STAGE_ALIASES`），改名要重算。⚠️⚠️**端口依赖 ≠ 流程连线**（`(consumer,port)→supplier` 是"取谁的文件"，`sequenceFlow` 是"先做哪一步"，不能互转——互转会把默认图画成一团乱线）。
  - **状态机已接线**：`store.task_scheduler(tid,imposition_active)`(唯一查询面)／`store.stage_supplier()`(按图求供给方)／`stale_chain.upstream_from_diagram()`(过期链按图)／`runner` 守卫(不在流程里的阶段直接拒)。
  - ⚠️**每层界面都必须问图**（否则"改了图没反应"）：步骤条格子与**任务列表子任务胶囊**＝`task_slots`（**别写死 `for stage in STAGES`**）；拼版节点可见性＝图里有没有那一格。
- **页面栈**（2026-10-06 新增两个二级页）：`desktop/pages/createtask/page.py::CreateTaskPage`（路由 `create`，创建任务不再是弹窗）+ `desktop/pages/taskflow/page.py::TaskFlowPage`（路由 `flow`，详情页页头进入）。⚠️ 这两页与详情页都**没有导航条目**，`_SUBROUTES` 里统一把高亮留在「任务管理」。⚠️**组件被内嵌进页面后不许自己关窗**：`CreateTaskPanel.reject()` 只发 `cancelled`；`FlowPanel` 要 `close_window=False`、`embedded=True`（藏自带标题）。⚠️ Signal 只能声明在 **QWidget 子类**里（Mixin 里写 `Signal(...)` 发不出去），故 `flow_edit_requested` 在 `page.py::TaskDetailPage` 上。⚠️**二级页是惰性单例⇒每次进入必须复位**（`open_create` 调 `CreateTaskPage.reset()`，且复位放在"已在这一页"判断**之前**），否则第二次建任务接着上一次的表单填（用户报障）；`CreateTaskPanel.reset` 里**先清 checkbox 再换自定义图**（反过来会拿旧自定义图刷默认预览）。
- ⚠️判"控件是不是在某个状态"用 **`isHidden()`** 不用 `isVisible()`（后者祖先不可见时恒 False）。⚠️且**方向别反**：`isHidden()` 为 True = 已隐藏 = 不在编辑态 ⇒ 才 return（写成 `not isHidden()` 会让改名永远不生效，我犯过一次）。
- 独立页左栏=缩略图条+大图→`modules/thumb_source.py::ThumbSourceMixin`（⚠别自起`PreviewWorker`/`ImageThumbCacheWorker`；拼图页**不继承**只复用`singletask_dir`）；普通步骤页外设`modules/base.py::StepModulePage`（钩子`source_summary/source_images/on_failed/edit_effect_note`）。缓存`files.image_thumb_cache_path`键含文件大小。

## 关键契约
- ⚠⚠**「源 PDF」↔「提取图片」成对存在**（2026-10-06）。⚠️源 PDF 在图上是 **`startEvent`、没有 `stage`**（语义标记是 `SUPPLY_TASK_SOURCE`）⇒ **不能按 stage 认**；`ports.source_pdf_node_ids()` 走「事件类型**或**节点名」两条任一命中。配对唯一真源＝`ports.paired_node_for_stage(diagram, node_id)`（**双向**；其它步骤返回 `None`）——⚠️**别在编辑器里写死 `"extract"↔"startEvent"`**。⚠️**删除有两条路径，两条都要成对**：`ask_delete_selected()`（工具栏）与 `remove_selected()`（**键盘 Delete**）——凡"某动作要联动"**先 grep 有几条入口**。⚠️返回 `None` 时调用方**必须自己再判**对方是否真在图里（别给幽灵 id）。
- ⚠⚠**页头 PDF 图标：只在"流程压根不吃 PDF"时整颗藏起来**（判据 `ports.flow_needs_source_pdf()`，抽成 `manifest._flow_needs_source_pdf()` 供 `_missing_source` 复用、**别两处各判**）。⚠️**空壳任务**（还没选 PDF 但流程要 PDF）必须**恒显示**——原来"按钮恒可见"是硬规则（文件被移走时它同样要当补救入口），所以要分清「流程不碰 PDF」（藏）与「还没选」（显）。⚠️构造期无 `task_id` 时给 `True`＝保持原样。自测＝`step_ports` 第 8 节（纯逻辑）＋`flow_ui` 第 18 节（端到端）；⚠️后者**必须替掉 `QMessageBox.question`** 否则真弹模态＝看门狗 `os._exit(3)`。
- ⚠⚠**「输入入口红框」与「缺输入才亮」是**两套**，会互相覆盖**（2026-10-06）。
  - 常驻红框＝**标识入口**（页头插图/插目录、预览区＋/📁，用户"都是红色框住"）⇒ `ui/widgets.py::mark_input_entry(button)`（**两处用**故必须收敛成一份，别各写样式串）。🗑 删除、流程、改名**不标红**（不是入口）。
  - 动态高亮＝**缺什么才亮、补上就灭**＝`manifest._set_tool_highlight`。
  - ⚠️ 动态那套灭时 `setStyleSheet("")` **会把常驻红框一起抹掉**⇒ `_refresh_source_actions` 里先走动态、再**无条件重贴** `mark_input_entry(insert)`。⚠️别"优化"成只用一个（只留动态＝入口看不出该点哪儿；只留常驻＝缺输入不再提醒）。**同一按钮上只能选一套**。
  - ⚠️⚠️**自测判"有没有红框"不能看有没有 `border`**：qfluentwidgets ToolButton **自带** border 样式表，`'border' in styleSheet()` 对**所有按钮**为真（我第一版探针全绿且毫无意义）。正确＝`str(theme.DANGER) in styleSheet()`。同理**别断言 `styleSheet()==""`** 来判"高亮撤掉"（常驻红框让它永不为空）——用**红字是否消失**（`source_warning.isHidden()`）判动态高亮。
- ⚠⚠**入口节点：没有上游也要有输入**（2026-10-06 用户口径"如果某个节点作为第一个节点，一定要可以有输入可用"）。此前图片输入只有一条来路＝上游 `pages` 端口，于是自定义流程把「检测文本框」放第一位时**连坏三处**：①`stage_input` 沿图回溯不到供给方→点执行弹"输入未接好"；②页面清单只有 extract 成功才刷新→预览永远"暂无图片"；③插图只写 `stages/extract/`＋`_refresh_preview` 拿栈页号当格序用→插完左侧列表不刷新。
  - **唯一实现**＝`ports.resolve_input_with_entry(task_dir, stage, port, supplier)`：供应方为 `None` **且该阶段确实吃 `pages`** ⇒ 回落 `ports.task_input_dir()`＝`stages/input/`（落点由 `ports.TASK_INPUT_LOCATION` 唯一声明）。`store.stage_input()` 调它；`store.task_input_dir()` 是页面侧入口。
  - ⚠️**`boxes`/`pdf` 不许回落**（用户不会手写 boxes.json，回落＝把"接口没接好"伪装成"有输入了"）。⚠️判据必须落在**这个端口自己**身上（`port=="pages" and "pages" in stage_inputs(stage)`），**别写 `port in stage_inputs(stage)`**——`rembg` 声明的是 `("pages","boxes")`，那种写法会让它的 boxes 也回落（我犯过一次，自测第 7 节钉住）。
  - ⚠️**插图目标目录与执行读目录必须同源**（都走 `store.stage_input`）＝`manifest._current_stage_input_dir()`；否则"插进去了却读不到"。
  - ⚠️⚠️**按钮写"选目录"就必须真开目录框**（提示层主按钮，用户 2026-10-06"改成选择图片目录"）：`getOpenFileNames` 选不了目录，只改文案＝骗人。做法＝给提示层内容加 **`pick_kind`**（`"folder"`/`"files"`），`MissingSourcePrompt.picked` 改成 **`Signal(str)`** 把它发给宿主，宿主 `_on_prompt_pick_input(kind)` 分流到 `insert_pages_from_folder()`。⚠️**PySide6 不容忍槽签名不匹配**⇒自测收集器写 `lambda: ...` 会 TypeError，必须 `lambda kind="": ...`。⚠️组件**自己不知道开哪种框**（通用浮层），只传意图，别把 QFileDialog 塞进组件。⚠️自测要**真点一次按钮**记录开的是哪个框，别只断言文案。
  - ⚠️**插图/复制前必判"源已在目标目录里"**＝`source.resolve().parent == target_dir.resolve()`（⚠️比较**必须 `resolve()`**，Windows 大小写/短路径不等）：否则 `while target.exists()` 的重名避让会把同一张图复制成 `xxx-1.jpg`。命中的**跳过复制**、直接进清单，且清单侧**按 `str(file)` 去重**（`_append_pages_to_manifest` 返回**实际新增条数**，0＝全已在清单里，调用方据此不刷新）。⚠️**别把"外部同内容再导入一次"当bug 修**（源在任务目录外时本就该复制一份进去，任务要自包含）。
  - ⚠️`_sync_manifest_to_input()` **只在清单为空时**重建（用户插过/删过/重排过就不能拿目录内容覆盖）。`_refresh_preview` 入口调它。
  - ⚠️这条只解决"没有上游"，**不解决"上游还没跑"**——那是 `Scheduler`/`missing_stages`，两件事别混。默认流程（有 extract 上游）行为**一字不变**。自测＝`step_ports` 第 7 节（不含 extract 的 flow.bpmn 复现现场）＋`flow_ui` 第 15/16 节。
- ⚠⚠**`getOpenFileNames` 选不了目录**（原生 Windows 对话框只收文件）——"整目录导入"必须有**独立入口**：`ImageViewerWidget.insert_folder_requested`＋📁 按钮（`ToolButton(FIF.FOLDER)`，仅 `editable=True` 时建）→ `manifest.insert_pages_from_folder()`＝`getExistingDirectory`。⚠**别只改 filter 写成"图片与文件夹"**（看着像支持了，实际选不到）。
  - 两个入口（＋多选文件／📁选目录）**共用 `_insert_paths` 一个实现**；目录展开**复用 `StepSpec.collect_files`**（顶层→下钻一层→去重按名排序，**别另写遍历**），spec 取**当前阶段**的（`ports.spec_for_stage(current_stage())`，延迟导入）。
  - ⚠️**插图/复制前必判"源已在目标目录里"**＝`source.resolve().parent == target_dir.resolve()`（⚠️比较**必须 `resolve()`**，Windows 大小写/短路径不等）：否则 `while target.exists()` 的重名避让会把同一张图复制成 `xxx-1.jpg`。命中的**跳过复制**、直接进清单，且清单侧**按 `str(file)` 去重**（`_append_pages_to_manifest` 返回**实际新增条数**，0＝全已在清单里，调用方据此不刷新）。
  - ⚠️**别把"外部同内容再导入一次"当 bug 修**：源在任务目录外时本来就该复制一份进去（任务要自包含）。要防的只是"用户选了**输入目录本身**"。
  - ⚠️自测里替身 `QFileDialog.getExistingDirectory` **必须 try/finally 恢复**（不恢复会漏给别的模块）。自测＝`flow_ui` 第 15 节。
- ⚠⚠**重建步骤条/槽位相关界面时，"旧下标"必须用"旧快照"解析**（2026-10-06 用户报障"编辑流程后顶部流程图没立即更新"）。`_rebuild_step_bar` 原来在摘控件**之后**才 `step_at_index(old_bar._current)`／`flow_slots()`——那些查的是**磁盘上那张新流程图**，而 `old_bar._current` 是**旧流程**的格序。实测：停在 rembg（旧格序 2），删掉 extract（格序 0）后它在新流程里是格序 1，拿新表查旧下标 2 得到 imposition ⇒ **高亮默默挪走**＝"看着像没更新"。⚠️**光把取值提到摘控件之前不够**（`flow_slots()` 读的仍是磁盘）——正解是步骤条**自己记下建时那份槽位快照**（`_build_step_bar` 里 `self._step_bar_slots`），重建时用 `getattr(..., None)` 取（兜住构造期还没快照）。
  - ⚠️配套：壳层 `open_detail` 在 `set_task` 返回 False（**正在跑子任务**）时原来**什么都不做**⇒用户从流程页保存回来被**留在流程页**上。已修：不 busy 也 `setCurrentWidget`＋`page._toast`（⚠️**壳层没有 `_toast`**，借详情页的）。
  - ⚠️⚠️**自测"这行代码改前会红吗"必须双向验证**（把修复块用脚本还原成改前跑一遍）。踩到过**三种假绿/假红**：①只验"详情页在前台"——它本来就已在前台、从没被切走⇒恒真（须**先切到流程页**再触发失败）；②`_toast(kind,title,content)` 标题是**第二个**参数，写 `item[0]`（那是 kind）⇒`any()` 恒 False，**差点去改已经正确的生产代码**；③在完整 `set_task` 链路上验"高亮别跳格"改前也绿——末尾 `_select_stage` 按 key 找回了高亮、**掩盖**了错位（必须**直接调 `_rebuild_step_bar()`** 验）。⚠️替身要在 `shell.close()` **之前**用完（之后 page 已析构、判据恒假）。⚠️**别用 `git stash` 做这件事**：它带走未跟踪文件的编译产物，自测 import 失败、掩盖真实结果。⚠️别拿"完成态跨重建保住"当断言（完成态按 runs.json 重算，`set_task` 全量复位会清掉手工标的＝**既有正确行为**）。
  - ⚠️`task_diagram`/`flow_slots()` **都无缓存**（每次读盘），`save_task_diagram` 会清 `_flow_cache`——"改了没反应"**别往缓存上查**。自测＝`flow_ui` 第 14 节。
- ⚠⚠**入口节点：没有上游也要有输入**（2026-10-06 用户口径"如果某个节点作为第一个节点，一定要可以有输入可用"）。此前图片输入只有一条来路＝上游 `pages` 端口，于是自定义流程把「检测文本框」放第一位时**连坏三处**：①`stage_input` 沿图回溯不到供给方→点执行弹"输入未接好"；②页面清单只有 extract 成功才刷新→预览永远"暂无图片"；③插图只写 `stages/extract/`＋`_refresh_preview` 拿栈页号当格序用→插完左侧列表不刷新。
  - **唯一实现**＝`ports.resolve_input_with_entry(task_dir, stage, port, supplier)`：供应方为 `None` **且该阶段确实吃 `pages`** ⇒ 回落 `ports.task_input_dir()`＝`stages/input/`（落点由 `ports.TASK_INPUT_LOCATION` 唯一声明）。`store.stage_input()` 调它；`store.task_input_dir()` 是页面侧入口。
  - ⚠️**`boxes`/`pdf` 不许回落**（用户不会手写 boxes.json，回落＝把"接口没接好"伪装成"有输入了"）。⚠️判据必须落在**这个端口自己**身上（`port=="pages" and "pages" in stage_inputs(stage)`），**别写 `port in stage_inputs(stage)`**——`rembg` 声明的是 `("pages","boxes")`，那种写法会让它的 boxes 也回落（我犯过一次，自测第 7 节钉住）。
  - ⚠️**插图目标目录与执行读目录必须同源**（都走 `store.stage_input`）＝`manifest._current_stage_input_dir()`；否则"插进去了却读不到"。
  - ⚠️⚠️**按钮写"选目录"就必须真开目录框**（提示层主按钮，用户 2026-10-06"改成选择图片目录"）：`getOpenFileNames` 选不了目录，只改文案＝骗人。做法＝给提示层内容加 **`pick_kind`**（`"folder"`/`"files"`），`MissingSourcePrompt.picked` 改成 **`Signal(str)`** 把它发给宿主，宿主 `_on_prompt_pick_input(kind)` 分流到 `insert_pages_from_folder()`。⚠️**PySide6 不容忍槽签名不匹配**⇒自测收集器写 `lambda: ...` 会 TypeError，必须 `lambda kind="": ...`。⚠️组件**自己不知道开哪种框**（通用浮层），只传意图，别把 QFileDialog 塞进组件。⚠️自测要**真点一次按钮**记录开的是哪个框，别只断言文案。
  - ⚠️`_sync_manifest_to_input()` **只在清单为空时**重建（用户插过/删过/重排过就不能拿目录内容覆盖）。`_refresh_preview` 入口调它。
  - ⚠️这条只解决"没有上游"，**不解决"上游还没跑"**——那是 `Scheduler`/`missing_stages`，两件事别混。默认流程（有 extract 上游）行为**一字不变**。自测＝`step_ports` 第 7 节（用一条不含 extract 的 flow.bpmn 复现现场）。
- ⚠⚠**`Path("")` 是 `"."`（当前目录），`exists()` 为真**——判"有没有源文件"绝不能只写 `exists()`。**源文件三态**（2026-10-06，PDF 非必需之后）：`source_path is None`=**还没选**（空壳任务，页头写「尚未选择 PDF」+ 补选按钮，**不弹错误框**）／路径在但文件不在=**文件丢了**（红错框）／正常。索引里空源存**空串**不存 `"."`（`create_task` 里显式挡）。补选走 `store.set_task_source`（**先复制进任务目录再改索引**）。
- ⚠**创建任务：PDF 非必需、名字两级回落**（2026-10-06 用户口径）：`can_submit()` 恒 True；空 path ⇒ `start_create` **跳过整条指纹/查重链**且**不排** `SourceThumbnailsWorker`（没文件渲会卡队列）。名字回落＝**用户填的 → pdf 文件名 → `任务#<实际 task_id>`**。⚠默认名的序号必须用 `create_task` 里**实际分配到的** `task_id` 现算，`store.default_task_name()` 给的只是 placeholder（占号原子、可能顺延，用预测值会让「任务#0008」落在 0009 上）。
- ⚠**"这一步缺什么输入"只有一个判据**＝`TaskDetailPage._missing_input_kind()`→ `"pdf"`/`"images"`/`""`（**PDF 优先**）。⚠**高亮/红字/提示层/执行守卫/toast 全读它**（散开各判各的必然漂移成"红字说缺图、弹窗说缺 PDF"）。`"pdf"`＝`ports.flow_needs_source_pdf`（`StepSpec.needs_source_pdf()`＝端口 `inputs` 含 `"pdf"`）AND `source_path is None`——**创建页与详情页共用这一份**；`"images"`＝`ports.flow_needs_entry_images`（**入口阶段不吃 pdf**）AND `stages/input/` 无图。⚠**"入口"是图上的性质**＝`is_entry_stage`（问"有没有上游"），**不是**"第一个是不是 extract"（那两条都不成立、判不出）。⚠执行守卫问"这一步输入齐不齐"（`runner._stage_inputs_ready`）**不是**"有没有 PDF"（写死那个会让"第一步不吃 PDF"的任务**有图也点不动**）。⚠每次进入都弹提示层（别自作主张加"已存在就不再弹"——用户恰恰是**忘了**才要重新进来被提醒）；提示层**复用**但⚠**每次显示前要 `configure()` 刷文案**。⚠别拿 `input_noun()` 判。
- ⚠⚠**组件内嵌进页面后 `self.window()` 是主窗口**——`CreateTaskPanel.submit()` 曾有 `self.window().close()`，点一次「创建任务」把整个程序关掉（用户报"创建成功但 GUI 不可见了"）。面板一律**只发信号**，`reject()`/`submit()` 都不碰窗口，去哪儿由宿主决定。
- ⚠**换/补选源 PDF 必须先算指纹再决定**（`manifest.py::_on_source_hash_ready`）：①==本任务当前 hash ⇒ 不动；②`find_tasks` 命中别的任务 ⇒ **弹窗问"是否仍然使用"，答"仍然使用"就换**（⚠️**不是一律拒绝**，用户 2026-10-06 明确纠偏过；与外层 `_confirm_duplicate` 同一态度，重复的事实要说清、决定权在用户）；③新 PDF ⇒ 确认后才`_apply_source`。⚠指纹**走后台** `HashWorker`（几百 MB 要一两秒）+期间**锁按钮**；⚠`set_task_source` **必须写指纹**（`source_hash` 参数）否则换一次后判重失效。⚠清产物**连待写标记一起清**（`_draft_dirty`/`_pending_sizes`/`_pending_boxes`），否则 `set_task` 开头的 flush 把旧书数据写回来。⚠**`MessageBox` 是纯文本不解析 markdown**——文案写 `**` 用户看到的是星号。
- ⚠**启动不再自动跳回上次任务**（2026-10-06 用户改口径，与 09-30 的"重启回到上次任务"相反）：`main()` 里无恢复入口，一律停列表页。任务级「上次停留的步骤」照旧（`set_task` 末尾 `_initial_stage_index()`＝点详情落到上次那步的全部实现，与启动解耦）；根目录 `ui.json` 的 `last_task` 照写不误，留给将来的**显式**入口。自测 `last_stage.py` 第9节钉死"别把 `_restore_last_task`/`RESTORE_DELAY_MS` 留回来"。
- ⚠**singletask≠taskdetail**：共用组件/worker但**缓存根各归各**——独立页`singletask/<子任务>/`；任务流程`tasks/<id>/thumbnails/{source,print,imposition}`，**禁止借道**；taskdetail缓存随`delete_task`清理。
- 第四步取图=第三步「提交本次任务」成品图：改去底色结果/area/border⇒**必须重新提交**。detect页交付`<输出目录>/boxes.json`与`tasks/<id>/boxes.json`逐字段一致。`LogPanel.log()`=append。
- `ImageViewerWidget`两形态：图片(`set_images`/`set_thumb_source`)、PDF页(`set_pdf_source`+`begin_pdf_pages`+`set_pdf_thumb`)。⚠`set_images`须先`_clear_page_source()`；`gen`代际号防串页。
- print页：未生成=源图缩略图，生成后=产物PDF页缩略图。`RembgPreviewWidget.set_images(paths, rembg_dir)`**第二参是结果目录**。
- **编辑生效链**：`ZoomPopupMixin`→`ImageEditorDialog(save_back=True)`→`overwrite_image_file`→`image_saved`；独立页由`ThumbSourceMixin._wire_source_edit()`接（`_reload_edited_thumb` 要**先 pop `_thumb_cache_ready[path]` 再 `refresh_page`**）；拼图页产物`singletask/拼图/edited/<页>.png`；任务侧`TaskDetailPage._on_page_image_saved`。
- **「完成」覆盖确认**：`_confirm_overwrite()`在**任何烘焙前**问一句；⚠`_finishing`须先于确认框置位(`MessageBox.exec()`自带事件循环)。四个短路`return True`：`not save_back`/`not target_exists`/`_image==_original`/`MessageBox`抛异常。⚠`editor.target_name`只能做属性——自测替身按死签名覆盖，**给会替身化的函数加参数前先grep替身签名**。
- **落地口径**：独立任务页「应用」**一律落地实体文件**；任务流程**看目标**——有`ZoomTarget.edit_path`才落地。判据是`edit_path`，不是"在哪个页面"。

## 硬规则
- ⚠⚠**三套下标，最易错**：①步骤条格序`bar_index`（**含可选节点占位**，只数本流程里有的格）；②栈页号`stack_index`（`control_stack`/`preview_stack` 的物理页号）；③`control_stack.currentIndex()`。`_select_stage()`收**格序**。
  - ⚠⚠**`stack_index` 必须"查静态表"，不能"数当前有几格"**：两个栈按 `FLOW_STAGES + OPTIONAL_STEPS` **一次建好固定页数**，与流程图文件无关。文件里少了某一步（如默认流程不含「图片去底色」）时若按"数出来的位置"编号，后面每步都前移→点「生成 PDF」翻到去底色页。正确做法：`FlowDiagram.stage_slots()` 里 `stack_index = 静态顺序里的位置`（`page_of` 查表）。
  - ⚠**自测与生产代码一律不许写死下标**：查 `bar_index_of_step(step)` / `stack_index_of_step(step)`。旧硬编码 0/1/2 恰好在可选节点之前才没受影响，`3` 一律错。
  - ⚠⚠**`_refresh_preview(index)` 的入参是「栈页号」不是格序**（2026-10-06 踩中）：它内部走 `stage_at_stack_index`，所以 `_select_stage` 必须传 `self.stack_index_of(index)` 转一道，`runner.py` 里那两处 `_refresh_preview(1)`/`(3)` 也已改成 `stack_index_of_step("detect"/"print")`。**同族坑**：`manifest._active_page_viewer` 原写 `preview_stack.currentIndex() == 1`（把栈页号当格序比），已改走 `stage_at_stack_index`。凡"拿 `preview_stack`/`control_stack` 的页号去过 `stage_at_index`/`bar_index_of_step`"的地方都要查一遍。
- ⚠`set_task` 走 `_rebuild_step_bar` **重建整个步骤条**（`deleteLater` 旧的）⇒自测跨 `set_task` 缓存的 `step_bar.imposition_node` 是**已析构控件**（`isHidden()` 拿僵尸状态，曾假红）。断言前重新取。
- ⚠⚠**qfluentwidgets 的 `Dialog` 放不下成套面板**（第二参是**字符串**、**没有** `viewLayout()`）⇒ 走`components/dialog_shell.py::shell_dialog`。⚠**"点按钮就炸、自测却全绿"先怀疑外壳**（自测都直接实例化`*Panel`、从不构造外壳，三个弹窗曾同时踩中）。
- ⚠**面板的 `self.close()` 关不掉弹窗**（面板自己没窗口）⇒用 `self.window().close()`。参数名别与局部 `layout` 重名。⚠`qfluentwidgets.PushButton` 的 `clicked` 发**无参**信号，按 `(checked: bool)` 接会 TypeError。
- ⚠**编辑器必须有工具栏**：`BpmnEditor` 只是画布，动作函数若无按钮调用就是**死代码**（用户报"无法编辑"的根因）。画布要有**尺寸下限**（跟随视口）。⚠`NodePalette` 置灰项光靠 `ItemIsEnabled` 在 qfluentwidgets 列表里**看不出区别**，须显式 `setForeground(INK_DISABLED)`。
- ⚠**自定义初值缺失会静默回落默认**⇒勾「自定义」与「默认」长得一样（用户报过）；`custom_init_missing()` 有告警。
- ⚠⚠**「是否拼版」是三个判据**（用户口径"操作在拼版面板里，它可以用，但是否生效由…"；逐层查证业务流程后定）：①**在不在流程里**＝`bar_index_of_step("imposition")`②**有没有意义**＝`area==1`③**要不要真跑**＝面板底部开关（`imposition_active`＝**用户意图**，只看勾没勾）。三者全过＝`imposition_effective()`＝**能不能真跑**；取图来源/状态机跳过/步骤条生效态**一律认 effective**，`imposition_active` 只留给"文案里说没说勾"。
  - ⚠⚠**`area` 是拼版的适用前提，不是"显示开关"**（我一度当"语义错配"删掉，又查回来）：`area=1` 产出**成对** `-l`/`-r` 半页图，两张并排才拼得出**正刊对开版面**；2/3/4 本来就是一张整图。⚠处置是**置灰+说明**不是隐藏（隐藏＝"节点凭空消失"）。⚠**置灰时保留勾选**（那是意图记录，改回 area=1 自动恢复），且要回填勾选态（盘上才准）。
  - ⚠⚠**界面与执行必须同一判据**：只改 UI 而 `runner`/`print_list` 仍认"勾没勾" ⇒ **界面说 A、执行做 B**（比不改更坏）。
- ⚠⚠**图上"画了但还没功能"的节点不许静默丢掉**（bpmn.io 可随手加「OCR 识别」，旧 `stage_slots` 直接 `continue` ⇒ 界面上凭空消失）：现在占一格＋`StageSlot.mapped=False`＋`stack_index=NO_PAGE(-1)`，步骤条画成灰节点、**副标题**写「未接入」（别放标题后缀，会被省略号截断），`_select_stage` 在 `set_current` **之前**拦下并提示"改名接上/删掉"；它不进运行阶段、不进列表胶囊。
- ⚠**`stage_states` 键只能加不能删**（调用方硬索引 `["rembg"]`，删键＝KeyError）⇒ 保留四个静态键＋`in_flow` 标记；要"只列流程里的"走 `flow_stages()`（按界面格摊开，`rembg_submit` 与 `rembg` 同格共存亡）。⚠**沿图回退取产物要 `fold_forward` 折叠到同格最靠后的动作**：直接取 `rembg` 会拿到**实时预览目录**而非用户提交过的成品 ⇒ 打印出没提交的图。
- ⚠GUI主进程不许进重依赖(`functions.detect`→cv2)：主进程用的纯规则放 utils 且不 import functions(`box_geometry`有AST守卫)。中文路径勿直用`cv2.imread/imwrite`，走`utils.image_io`。
- ⚠**"某个控件有没有被挡住/能不能点"怎么测**（2026-10-06 踩过两次）：
  ❌`parentWidget().childAt()`——它只在**直接子控件**里找，遮罩是**页面**级
  子控件（按钮的"叔伯层"）永远找不到 ⇒ 误判"没挡住"。
  ⚠️`QApplication.widgetAt(global)`——离屏下**对按钮返回 None**（top-level
  映射不完整）⇒ 只能测**页面内**控件（步骤条，有效）。
  ✅ 权威判据＝**`QTest.mouseClick` 真点一下**看槽有没有被调（把会弹模态的动作
  替成记录器）。⚠️"看起来可点"（`isEnabled()`/几何在遮罩外）**不等于**"点了有用"。
- ⚠**页内浮层的重铺时机**（2026-10-06，详细推导见 `2026-10-06.md`）：`open_detail` 先 `set_task()` 后 `setCurrentWidget()` ⇒ `set_task` 里弹层时页面**还没布局**（`640x480`、`_content_top()` 返垃圾值）⇒ 浮层**零高度**＝用户看到"没弹"，第二次进却正常。修法三处配合：靠 **`showEvent`** 重铺（布局就绪的第一个时刻）／`resizeEvent` **不判 `isVisible()`**（页面未 show 时它恒 False，恰好拦掉"首次进入"）／`_reanchor` 上沿>页高 60% 时放弃这次。⚠`showEvent` **先判 `task_id`**（`addWidget` 即触发，早于首次 `set_task` → `store.task_dir(None)` 抛错打断自测）。⚠**这类时序 bug 自测天生抓不到**（现有用例都是 `show()` 之后才 `set_task()`），必须走**壳层真实入口**＋断言"第一次"。
- ⚠⚠**离屏自测绝不真弹模态**（`exec()` 转事件循环＝挂住整轮，看门狗 `os._exit(3)`）；拖拽：QGraphicsView系走`QTest.mousePress`，自绘系走合成`QMouseEvent`**直调**（`event.globalPosition()`不可靠，改`mapToGlobal`）。⚠**给 `set_task` 这类常用入口加新弹窗时，务必在 `tests/selftests/_context.py` 加公共旁路助手**（现有 `silence_source_prompt(page)`），否则任何打开该状态的任务的测试都会挂。⚠包装助手**必须先把原方法抓在手里**再包一层（否则无限递归）；助手**自己也要过判据再记录**——"方法被调用"≠"该弹窗"，直接记调用会让"不弹"那条断言永远假绿。⚠判"提示层/弹层没出现"要看**实体是否被建出来**，别只看记录列表。
- ⚠⚠**Qt 信号在 `connect` 那一刻就把槽绑成当时的 callable**——之后替换对象的
  方法属性，对**已连的信号无效**。自测想拦住副作用必须**直连那个信号**
  （`prompt.picked.connect(收集器)`），**不能**靠 `page._on_pick_source = 替身`
  （真槽会真的弹模态）。⚠`show()` 是**异步**的，`show()` 后不跑一遍
  `processEvents` 就 `QTest.mouseClick` 会点空（假红）。⚠ `QRect.bottom()` 是
  **包含式**（top+height−1），比高度永远差 1，用 `y() + height()`。
- ⚠⚠⚠**布局在 `set_task` 末尾是"未生效"状态**：`set_task` 里 `_rebuild_step_bar()` 是 `removeWidget`+`insertWidget` 换控件，Qt 布局**延迟**生效 ⇒ 那一刻新步骤条 geometry 还是 QWidget 默认的 **640×480**、`isHidden()` 为 True、`mapTo` 得 **0**，**连 `layout.activate()` 都不管用**。要取"某控件在哪"必须用**稳定的兄弟控件**（如页头 Card，构造后再没被换过）算：`layout.itemAt(0).geometry().bottom() + layout.spacing()`。与 qfluentwidgets `MaskDialogBase` 只在构造时读一次 `parent.width()/height()` 同类根因。
- ⚠`Card`（`ui/widgets.py`）**自带 layout，暴露为 `card.box`**——再 `QVBoxLayout(card)` 建第二个会被 Qt 忽略、加进去的控件**一个都留不下**（卡片空成 32×32，文字全裁掉，像"没渲染"）。⚠ 别在卡片外再套一层"装卡片的中层容器 + addStretch"：带 stretch 的 `sizeHint` 高度算不对，会把卡片压成 20px 白条。⚠ 卡片高度**用 `heightForWidth`**：`sizeHint` 给的是**未换行**高度，wordWrap 标签会被裁一截。
- 界面：控件`paintEvent`自绘不引样式表；下拉`widgets.combo_box()`；窗口尺寸`ui/window_size.apply_window_size`。PySide6 **不导出** `QWIDGETSIZE_MAX`，要"不限"用 `(1<<24)-1`。⚠高分屏绝不手`painter.scale(dpr,dpr)`。
- 跨线程用`desktop.workers.connect_queued`。⚠**`QThread.run()`必须 try/except**（异常逃出不杀进程，`result=None`+`cancelled=False`⇒上层当"用户取消"）。存`self.error`再 raise；`run_with_progress`收尾在读 cancelled/result 之后并 try/finally。
- ⚠「点空白处」**直接**开选文件对话框。⚠**"资源管理器"=原生`QFileDialog`**（**不设**`DontUseNativeDialog`），不是`explorer.exe`（别再试UIA：Win10+文件列表是`DirectUIHWND`）。
- ⚠回滚/二分未提交在制品**禁用`git checkout HEAD -- <路径>`**：用Python按标记字符串切片替换，先备份。
- ⚠`SourceZone`内有真按钮子控件：几何靠`_relayout_buttons()`，改paintEvent须避开按钮区(`EMPTY_HEIGHT`=168)；`accepts_dir=False`不摆目录按钮；**入口是主路径必须画成按钮**；`_open_dialog`须try/except转`rejected`。
- ⚠按页号命名的缓存不能跨书共用。⚠自测判子控件可见用`isHidden()`（**不是**`isVisible()`，后者对未挂到已显示窗口的子树恒假红）；断言滚动条须真`show()`页面。
- ⚠"重跑同一个源"不是"冲突"：收尾"已存在就跳过"须先`filecmp.cmp(shallow=False)`比内容。⚠自测勿手写 JPEG/PNG 十六进制。⚠**传路径的公开API须在边界`Path()`收口**。
- ⚠**同一输出目录只准一个写入者**（`stages/imposition` 靠 `_COMPOSE_LOCK`+`_save_page_atomic`）；新增写入路径自己带锁。
- ⚠自我续期的`QTimer.singleShot(0)`＝CPU 风暴：分批解码带间隔(`picker.THUMB_GAP_MS=150`)。

## 测试
`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE <py> -u tests/gui_selftest.py`。⚠必带`-u`；勿用`--only`循环跑全量，一次全量+`--skip`(只接逗号串)；用例=`tests/selftests/*.py`(`NAME`/`DEPENDS`/`TITLE`自动发现)。**运行器遇模块异常 re-raise 终止整轮**。
- ⚠长跑末`QThread: Destroyed`硬中止**吃掉其后模块**⇒看`[PASS]/[FAIL]`+核对模块清单，`--only`补跑。跨模块残留异步回调会打后一模块monkeypatch（单跑即绿⇒非回归）。
- 本机**环境性红**(改前就红)：缺`static/guji.yaml`、缺**fpdf2**(整个print链)、缺`guji.spec`、缺ultralytics。⚠**本机 QProcess 一律 `FailedToStart`**（已最小复现钉死）⇒**所有真起 worker 子进程的模块都红**，第一道是`extract`，依赖链(`history`/`pages`/`detect`/`rembg`/`print`/`detect_boxes`/`detect_stats`/`page_order`/`progress_scope`…)全被连带。⚠跑全量前先 `grep -ln "guji.spec\|guji.yaml\|fpdf\|ultralytics" tests/selftests/*.py` 扫环境性红清单。解释器`C:\Users\zunkun\anaconda3\python.exe`(managed 3.13无PySide6)。
- 改`functions/`|`utils/`必跑`tests/reporter_cli_parity.py`|`reporter_worker_e2e.py`|`cli_print_smoke.py`。文档`tools/gen_api_docs.py --check`+`tools/check_docs.py`；视觉自查`tests/gui_shot.py`、BPM 截图`tests/bpm_shot.py`（出图后自行清理）。

## 进程/存储
- 主进程不载cv2/torch/PyMuPDF；每阶段一worker子进程，stdout=**JSON Lines**(started/progress/log/page_boxes/page_size/finished/error/cancelled)，由`core.reporter.Reporter`上报，**不解析中文提示**。数据根`~/Documents/guji`纯JSON无库（`tasks.json`/`ui.json`/`tasks/<0001>/{pages,runs,boxes,sizes,print,drafts,flow.bpmn,thumbnails,stages/*}`/`singletask/<子任务>/{thumbnails,thumbs,edited}`）。拼版合成`desktop/services/imposition.py`。
- 导航壳层`desktop/shell.py`；⚠`TaskDetailPage.set_task`必须返回True否则导航切不过去。列表页只发`open_detail(str)`信号。

## 踩坑
长期坑位清单已迁到 `2026-10-05.md` 的「历史踩坑」附录（MEMORY.md 有体积上限）。
本轮新坑见下方「硬规则」里的 ⚠⚠ 条目。

## 文档地图
`docs/guide/*`用法｜`dev/architecture.md`架构/进程模型｜`docs/dev/gui/gui-architecture.md`桌面端细节｜`gui-technical-spec.md`Worker协议/JSON/area｜`gui-ui-system.md`**改界面必读**｜`docs/dev/io_path_rules.md`路径｜`docs/functions/*.md`命令手册(位置固定)｜`api/*.md`签名(自动生成禁手改)｜`tasks/bpm.md`**BPM 口径与坑**。
