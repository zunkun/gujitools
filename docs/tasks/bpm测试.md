# BPM 流程合法性校验与测试

> 状态：已实现（2026-10-06）。校验器：`desktop/steps/validate.py`；
> 自测：`tests/selftests/flow_validate.py`（模块名 `flow_validate`）。

BPM 允许任意组合节点，但**并非所有组合都合法**。我们希望用户用默认流程，
但真实需求千奇百怪——所以策略是：**合法的尽量放行（运行时按图判就绪），
不合法的在创建/编辑保存时当场拒绝**。

## 节点与运行阶段映射

流程图上的节点分两类：**功能节点**（`task`，参与运行）与**图形节点**
（事件/网关，不参与运行）。

| 图上节点 | 运行阶段 | 说明 |
| --- | --- | --- |
| 上传 PDF（源PDF） | —（`startEvent`） | 图形节点；与「提取图片」成对增删（`ports.paired_node_for_stage`） |
| PDF 提取（提取图片） | `extract` | 吃任务源 PDF，产出 `pages` |
| 文本框识别（检测文本框） | `detect` | 吃 `pages`，产出 `boxes.json` |
| 去底色（图片去底色） | `rembg`（+ 同格的 `rembg_submit`「提交去底色结果」） | 预览/提交是同一步的两个动作，`rembg_submit` 不单独占格 |
| 拼版（图片拼板） | `imposition` | 可选步骤；是否拼版在参数面板里开关。⚠️ 图上的「是否拼版」网关**依附这一步**（不是可自由增删的组件，界面上没有"添加判断"入口），删掉拼版时它跟着删（`ports.orphaned_gateway_ids`） |
| PDF排版（`print` 任务节点，按钮「生成PDF」） | `print` | 收尾动作 |
| 生成PDF（结束事件） | —（`endEvent`） | 图形节点；不进拓扑序，只图示"流程在此收尾" |

⚠️ **同名不同物**：「PDF排版」是**这一步的名字**（流程图节点 / 步骤条 / 面板 /
导航都是它），「生成PDF」是**这一下按下去做的事**（详情页与独立页的执行按钮），
外加默认流程里挂在它后面的**结束事件**也用这个名字。三处撞名不是笔误——
认节点时看 `kind`（只有 `task` 才映射阶段），认界面步骤时看 `stage_label`。

## 删除联动（编辑时级联，非合法性规则）

| 删哪个 | 跟着删什么 | 判据（事实声明处） |
| --- | --- | --- |
| 「上传 PDF」/「提取图片」任一个 | 另一个（成对，双向） | `ports.paired_node_for_stage` |
| 「PDF排版」（print 任务节点） | 附在它后面的「生成PDF」结束事件 | `ports.orphaned_end_event_ids` |
| 「图片拼版」（最后一个 imposition 节点） | 依附它的「是否拼版」网关 | `ports.orphaned_gateway_ids` |

结束事件的判据是**图上的性质**（入线是否全部来自将被删的节点），不按名字
认「生成PDF」；删「图片拼板」这类上游时不牵连（结束事件的入线还剩别的）。
本来就越着空的事件不动（删除面不越界）。

网关的依附关系是**单向**的（用户 2026-10-08："是否拼版依附拼版"）：拼版没了
网关就无所依附，跟着删；反过来删网关**不动**拼版（"图片拼版可以不需要判断
是否拼版"）。图里还剩别的拼版节点时也不删（那只是删重复）。

三条删除路径（工具栏「删除」、Delete 键、确认框）都联动，确认框写明"会一起删除"。

## 合法性规则

判定输入是 :meth:`FlowDiagram.stage_order()`（拓扑序）——与状态机同一份
答案，**不另写顺序推导**。归纳文档列的 10 条组合，硬规则只有两条：

| # | 规则 | 级别 |
| --- | --- | --- |
| R1 | 流程里必须有可执行步骤（只有起止事件/网关的空流程拒绝） | 错误，拒绝保存 |
| R2 | 「PDF排版」（`print`）如果在流程里，必须排在**最后**——它后面的产出没人消费。覆盖全部反例：`print→rembg`、`print→imposition`、`rembg→print→detect` 等 | 错误，拒绝保存 |
| W1 | `extract` 不在第一位（它吃任务源 PDF，习惯上打头） | 警告，放行 |
| W2 | 有 `extract` 但图上没有「源PDF」入口节点 | 警告，放行 |
| W3 | 同一**运行阶段**画了多个节点（运行时按拓扑序去重只跑一遍）。⚠️ 「去底色」+「提交去底色结果」不算重复——那是同格的两个阶段 | 警告，放行 |
| W4 | 有未接入运行的节点（认不出阶段的 task，如随手画的「OCR 识别」） | 警告，放行 |

**放行的合法组合**（文档 10 条，映射到运行阶段后全部通过）：

1. `extract → detect → rembg →(imposition) → print`
2. `detect → rembg →(imposition) → print`
3. `rembg →(imposition) → print`
4. `imposition → print`
5. `print`（单步）
6. `extract`（单步）
7. `detect`（单步）
8. `rembg`（单步）
9. `imposition`（单步）
10. `detect / rembg / imposition` 任意顺序任意个数（`print` 有则必须在最后）

这些"缺上游"的流程之所以放行，是因为运行时本来就支持：
入口步骤的 `pages` 回落到入口图片目录（`tasks/<id>/stages/input/`，
`ports.resolve_input_with_entry`）、没有检测框时去底色按整页处理
（`ports.stage_blocking_inputs` 按图判就绪）。

## 校验实现与接入点

- **校验器**：`desktop/steps/validate.py::validate_flow(diagram) →
  FlowValidation`（纯逻辑，不 import Qt）。`errors` 拒绝保存；
  `warnings` 只提示。错误信息点名问题步骤（如"「PDF排版」必须放在流程
  最后——它后面还有：去底色"）。
- **接入点（保存时拦截）**：
  - `desktop/components/flow_dialog.py::FlowPanel.accept` ——
    详情页弹窗路径 + 创建任务页内嵌编辑器的「保存流程」；
  - `desktop/pages/taskflow/page.py::TaskFlowPage._on_done` ——
    流程编辑二级页顶部「保存流程」（它绕过 `FlowPanel.accept`，
    校验要在同一处再做一遍）。
  - 拒绝时：不落盘、不关窗/不切页，弹 InfoBar + 摘要行写明原因。
- ⚠️ 校验是**保存口**的闸，不是运行时的闸：手编 `flow.bpmn` 塞进不合法
  文件仍会回落默认流程（`store.task_diagram` 的既有行为），不被这里管。

## 数据链：第一个节点有输入，每一步都有数据

除了页面能渲染，**数据层也要成立**：第一个节点引入输入（入口图片目录
`stages/input/` 或任务源 PDF）后，产物沿连线逐跳传递，**任意合法流程里
每个节点的输入端口都要解析得出具体路径**（2026-10-07 补验）。

解析规则（`desktop/store/tasks.py::stage_input`，图优先 + 静态表兜底 +
入口回落）：

- 节点有上游产出该端口 → 吃**上游产物目录**（如 rembg 提交的成品
  `stages/rembg` 传给 imposition，拼版产物 `stages/imposition` 传给
  print）；
- 沿图回溯不出（入口步骤、或上游不产该端口，如 detect 不产 pages）→
  `pages` 回落**入口图片目录**（`boxes`/`pdf` 不回落）；
- 拼版生效（开开关 + 流程里有该节点 + area 前提，见下一节）时 print 的
  取图来源换成 `stages/imposition`，否则回落提交成品。

自测钉死：`flow_validate._check_data_chain` 对 10 条合法组合 × 拼版
开/关，逐阶段逐端口断言 `stage_input` 非 None；并对 `rembg →
imposition → print` 逐跳核对（rembg 吃入口目录 → 提交成品传 imposition →
拼版产物传 print，不开拼版时 print 回退提交成品不断链）。

## 无检测数据的流程：area 锁整页、拼版放行（2026-10-07）

用户口径：

> 图片去底色作为第一个节点，则 area 默认 = 4，并且不可修改——area 其他
> 选项没有提前执行 detect 步骤，页面都是空白。
> 后续拼板也使用了 detect 数据；同理拼板作为第一个节点，也是不需要使用
> detect 数据。

判据唯一处：`desktop/steps/ports.py::detect_feeds_rembg`（流程里
「图片去底色」沿图回溯 `boxes` 有产出方，即「检测文本框」在它上游）。
两处消费，别另写一份：

1. **去底色面板**（`RembgPanel(whole_page_only=…)`）：没有检测数据时
   area 固定 4（整页/不检测）、下拉禁用；暂存/历史里残留的旧 area 一律
   不回填、不导出。第二步「整页模式」开关同步锁定——整页模式关不掉
   （取消勾选会被回填并提示）。
2. **拼版前提**（`imposition.py::_imposition_area_ok`）：流程里**有**
   检测数据时仍要求 `area=1`（左右分开才产出成对半页图）；**没有**检测
   数据时拼版吃整图照样拼（整幅单独一页、手动任意两张一页），area 前提
   不再适用——「拼板作为第一个节点，也不需要 detect 数据」。

自测：`step_ports`（`detect_feeds_rembg` 三态）与 `params_spec`（锁定
面板的 get_args/禁用/回填防回归）。

## 节点可重复执行

每个节点都支持反复重跑（改参数只重做一步是常态操作）：重跑某节点后
**重新提交/重跑下游**，下游按新数据重出产物。真实数据验证过整条链
重跑一遍：重跑 rembg → 重新提交 → 重跑 print，`print.pdf` 按
新数据重生成（mtime 前进）；print 本身连跑两遍也无状态残留。

## 测试

### 自测（离屏，进 `gui_selftest` 套件）

`tests/selftests/flow_validate.py`（依赖 `flow_bpm`）钉四件事：

1. 上面 10 条合法组合全部放行；「去底色+提交」同格两动作不误判重复；
2. 反例全部拒绝（含空流程、`None` 图），错误信息点名「PDF排版」；
3. 警告（W1–W4）只提示不拦，`ok` 仍为真；完整默认流程零警告；
4. 默认模板（`task_default.bpmn`）必须**零错误零
   警告**——模板是用户起点，一打开就警告等于说"程序自己的东西不合法"；
5. 保存口真的拦：`FlowPanel.accept` 不合法不置 `edited`；`TaskFlowPage`
   不合法不覆盖 `flow.bpmn`、不发 `flow_saved`（不切页）；换成合法图后
   同一颗按钮正常保存。

```bash
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only flow_validate
```

### 真实数据（~/Downloads 的古籍扫描件）

方法：取 `劉宗周年譜-1.pdf`（192 页真实古籍扫描）前 8 页做样本 PDF，
offscreen 驱动真实 GUI（`ModuleShell` + `TaskDetailPage`），走**真实
worker 子进程**（非 mock）跑两条合法流程：

- **任务A 默认流程**：extract → detect → rembg → 提交 → print。
  结果：8/8 页提取（830×1430 内嵌图）、YOLO 检测出框（`boxes.json`）、
  预览+提交产物落 `stages/rembg`、最终 `stages/print/print.pdf` 生成。
  默认模板校验零错误零警告。
- **任务B 合法组合 `detect → print`（无提取）**：把任务A提取出的真实
  扫描页当入口图片喂进 `stages/input`，检测打头 → 生成 PDF。
  结果：检测、生成 PDF 全部成功——"没有提取的入口流程"在真实数据上
  跑得通（这正是 R2 之外全部放行的依据）。
- **任务C 数据链 `rembg → imposition → print`（2026-10-07 补）**：真实
  扫描页喂入口目录 → rembg 吃入口图并提交（8 张成品落 `stages/rembg`）→
  开拼版（候选池 = rembg 提交成品 8 张，自动拼版成 8 页版面）→
  合成 8 张落 `stages/imposition` → `print.pdf` 生成（711KB）。
  随后**整链重跑**：重跑 rembg → 重新提交 → 重跑 print，产物按新数据
  重生成（mtime 前进）；print 连跑两遍无残留。
  ⚠️ 实测要点：**开拼版开关 ≠ 有合成产物**——拼版文档里要先有版面页
  （GUI 走「选择拼版」，`services.imposition.auto_impose_pages` 是唯一
  规则实现），`stages/imposition` 才会有东西，print 的输入守卫也据此
  放行。

⚠️ 环境注意：detect/rembg 依赖 `ultralytics`/`torch`，必须用 conda
`py310` 环境跑（base 环境报 `No module named 'ultralytics'`）。

## 历史记录

- 2026-10-06 之前：任何组合都能保存（保存口无校验），不合法流程要到
  运行时才暴露（如「生成 PDF」排在中间时，它后面的步骤产出没人消费）。
- 2026-10-06：新增 `validate_flow` + 两个保存口拦截 + `flow_validate`
  自测模块 + 真实数据验证（本文档）。
- 2026-10-07：去底色作为第一个节点（拿不到检测框）时 area 锁 4 不可改；
  没有检测数据的流程里拼版不再被 area=1 前提拦住（吃整图照样拼）。
