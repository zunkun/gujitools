# 桌面端技术规范（与 desktop/ 当前实现对齐）

## 1. Worker 消息协议（JSON Lines）

worker 子进程 stdout 每行一个 JSON 对象，均含 `type` 与 `task_id/stage/run_id`：

| type | 说明 | 关键字段 |
| --- | --- | --- |
| `started` | 子任务启动 | stage |
| `progress` | 进度（GUI 更新 runs.json + 进度条） | done, total |
| ~~`progress_total`~~ | **不作为独立事件类型**：被两个 reporter 归一化成 `done=0` 的 `progress`（判定用 `core.reporter.PROGRESS_TOTAL_EVENT`） | — |
| `log` | 日志行（进日志视图） | message |
| `page_boxes` | detect 阶段逐页文本框坐标（入 boxes.json） | image(stem), left, right |
| `page_size` | extract 阶段逐页图片原始尺寸（入 sizes.json） | image(stem), width, height |
| `finished` | 子任务完成 | output, result |
| `error` | 失败（原因进日志） | message |
| `cancelled` | 被中断 | — |
| `boxes` | 预览单图检测结果（mode=detect） | image, left, right |
| `detect_error` | 单图检测失败 | image, message |

**信号来源（重要）**：`progress` / `page_boxes` / `page_size` 不再由解析中文
提示文案得到，而是功能模块通过 `core.reporter.Reporter` **结构化上报**：

- `functions/` 在关键节点调 `self.reporter.progress(done, total)` /
  `reporter.event("page_boxes", …)`；
- `utils/pdf_utils.py` 接受可选 `reporter`，上报 `page_size` 与 `progress`；
- CLI **不注入** reporter → 落到 `core.reporter.CoreReporter` 空实现，
  输出与人读日志逐字不变；
- desktop 注入 `desktop.stages.events.JsonLinesReporter` → 直接写 JSON Lines。

`ProgressStream` 现在**只**把 print 转发为 `log` 事件（含第三方库输出），
不再做任何正则解析 —— 改一句中文提示不会再静默打断 GUI 进度条。
`[boxes]`/`[imgsize]` 两行文本在 functions 侧兼容保留一个版本，便于对照核验，
但 worker 已不解析它们。

⚠️ **`progress_total` 的归一化必须**两个** reporter 都做**（`core.reporter.CallbackReporter` 走进程内、独立功能页那条；`desktop.stages.events.JsonLinesReporter` 走子进程、任务流程那条）。只做一处的话，独立功能页永远拿不到上限、进度条一直是「总量未知」——两处口径分叉过一次，由 `tests/selftests/module_progress.py` 钉住。

⚠️ 渐进式迁移约定：
⚠️ `finished` 不再携带 `done/total`：进度由 `progress` 事件实时汇报，
GUI 侧用「最近一次 progress」在 `finish_stage` 时补齐最终计数。

阶段路由（`desktop/worker.py`）：`mode=detect` → 单图检测；
`stage=detect` → `run_detect_stage`（只检测不落盘）；
`stage=extract` → `run_extract_stage`（直接渲染到 `stages/extract`）；
`rembg`/`print` → `CommandArgs` + `functions.get_function`（CLI 层）。

## 2. JSON 数据格式

**tasks.json**（数据根目录）：任务数组，字段
`id(任务号"0001")、name、source_path、source_hash、status、created_at、updated_at、duplicate_confirmed`。

**runs.json**（任务目录）：`{stage: [record…]}` 最新在前，每阶段 ≤20 条：

```json
{"extract": [{"run_id": "...", "status": "success", "parameters": {"resume": false,
  "zoom": 2, "ext": "jpg"}, "done": 6, "total": 6, "started_at": ...,
  "finished_at": ..., "output_path": "..."}]}
```

**boxes.json**：`{页stem: {"boxes": [左框, 右框], "origin": "auto"|"manual",
"updated_at": ...}}`。缺失一侧为 `null`（保留左右身份）；坐标为原始图片像素
`[x1, y1, x2, y2]`。manual 优先：自动结果不覆盖手动框。

**sizes.json**：`{页stem: [width, height]}`（extract 渲染时上报）。
所有框坐标与预览映射均以该尺寸为坐标系基准，与显示缩放无关。

**pages.json**：`[{"file": "…/stages/extract/1.jpg", "label": "1"}]`（自然排序）。

**竖排分段**：`utils.page_layout.vertical_runs(text) -> [(片段, 是否旋转)]`。
汉字/全角等宽字符每字一格；ASCII 可打印字符连成一段，预览与成品各用
`painter.rotate(90)` / `pdf.rotation(-90, x, y)` 把该段旋转 90°（字头朝右、
自上而下读）。竖排高度用 `vertical_extent_mm`（拉丁段按 0.55 字宽折算）。

**ui.json**：`{"last_stage": "rembg"}`——任务级界面状态，目前只有一项：用户
**上次在详情页停留的步骤**。打开任务时 `_initial_stage_index()` 把 key 映射回
当前流程里的下标（`_stage_index_of`），匹配不上（key 认不出、或「图片拼版」
这个条件节点当前不在流程里）就回第一步。⚠️ **记 key 不记下标**：步骤会增减，
下标错位会把用户送到另一个步骤去。写入在 `_select_stage()`（切步骤的唯一
入口，进程被杀也不丢），读取只读盘不建面板。

**根目录 ui.json**：`{"last_task": "0012", "source_hash": "…"}`——全局界面状态，
与任务级那份各管一半：这里记「上次待的任务」，步骤仍由任务自己的 `ui.json`
记。写入口在 `TaskDetailPage.set_task()` 末尾（进任务即写）；启动时
`main()` 延迟 `RESTORE_DELAY_MS` 调 `MainWindow._restore_last_task()`：任务
存在**且指纹一致**才 `_open_detail`（步骤由 `set_task` 自己恢复）。`source_hash`
是防撞号的——任务号顺序复用（删 0012 再新建也叫 0012），对不上说明这个号
已经是别的任务，当"任务不存在"安静留在列表页。冒烟模式（`GUJI_GUI_SELFTEST`）
不做恢复。

**drafts/<阶段>.json**：`{参数名: 值}`，内容是 `PrintPanel.get_args()` 那一套键
（已归一化）。用途是「参数暂存」——改了参数没执行就切阶段/切任务/关程序时，
改动落在这里，下次进入该阶段按 **暂存 > 最近一次执行参数 > 内置默认** 回填。
用户改动经 `StagePanel.param_edited` 上报、400ms 防抖写盘；**程序化回填不算**
（面板 `_applying` 期间不转发），参数非法时不覆盖上一份有效暂存。

## 3. area/border 效果区域合成（compose_region_output）

几何规则**只在 `utils/box_geometry` 布局层定义一次**，CLI（numpy 渲染）与
GUI（QImage 渲染）共同消费同一份 `OutputLayout`，不得各自推导
（历史上两处各自实现并硬编码同一个 `SYMMETRIC_GAP_MM = 10`，漂移后产生过
真实 bug：`area=3 + 双框 + border=None` 时 GUI 把并集搬到了画布左上角）：

| 场景 | 输出 |
| --- | --- |
| area=1 | 每个文本框各一张：框 + border（border 缺省为 0），文件名 `-l`/`-r` |
| area=2 双框 | 一张：并集画布 + border，两框内容按原位置粘贴，**框间内容丢弃（留白）** |
| area=3 双框 | 一张：并集区域**整块**作为 ROI（框间内容保留）+ border |
| area=2/3 单框 + border | 对称画布：宽 = 左 + 框宽×2 + 10mm 间隔 + 右，内容在一侧 |
| area=2/3 border 未填 | 整页尺寸画布，仅框内（area=3 为并集内）保留内容，其余留白；**ROI 写回原位置** |
| area=4 整页 | 一张：**不调用 YOLO**，整页 `[0,0,W,H]`（或用户手画的框）作为一个整体 + border；**不做对称镜像** |

- 布局层入口：`utils.box_geometry.build_output_layout` /
  `build_symmetric_layout`（返回冻结 dataclass `OutputLayout` / `Canvas`）。
  单框对称输出必须由调用方用 `symmetric=True` 显式选择 —— 合并后的单框
  （area=3）走普通布局，布局层不猜。
- border 解析：`utils.box_geometry.parse_border_mm`（mm→px @300dpi，
  CSS 风格 1~4 值，返回 [top, right, bottom, left]）。
- 合成在 worker 线程完成（`compose_region_output` + `compose_outputs_horizontal`），
  多输出横向拼接展示；不生成文件。
- **提交产物（`stages/rembg/*.png`）一律是白底透明的 PNG**（2026-09-30 用户要求：
  无论 `type` 是什么，提交结果的白底都转透明）。⚠️ 透明只能在**合成之后**加：
  合成画布是**不透明白**填充（`Format_RGB32` + `fill(Qt.white)`），在去底计算处
  （`utils.rembg_page`）加会被它重新压平。落盘的唯一实现是
  `utils.save_white_as_transparent`（`desktop/stages/rembg_stage._save_transparent_png`
  调用）：判据只看像素不看 `type`（面板参数与预览可能不同步），灰阶页走调色板 +
  tRNS（纯黑白页 1bit、灰度页 2/4/8bit；透明区 RGB 保留 255，第四步 JPEG 缩略图
  才不会变黑底），彩色印章页走 RGBA 保原色。回归防护：
  `tests/selftests/rembg_transparent.py`。
- rembg 预览默认显示去底色结果，可切换原图；两者均按上述规则裁剪显示。
- 回归防护：`tests/selftests/box_geometry.py`（规格一致 + 两侧同源）。

## 4. 检测框规范

- 坐标基准：原始图片像素（extract 记录于 sizes.json）。
- 存储：`[左框, 右框]`，缺失一侧 null；手动编辑后为紧凑列表（保持左先顺序）。
- 预览映射：显示缩放比以原始尺寸为基准（`ImageView._update_mapping`），
  鼠标命中/拖拽/绘制共用同一映射，窗口缩放后立即生效。
- **线宽**：叠加层线宽必须**取整到设备像素**（`ImageView._pen_width()` =
  `round(logical*dpr)/dpr`）。`QPen(width)` 是逻辑单位，Qt 用 `逻辑宽 × dpr` 得设备
  宽；不是整数设备像素时（125% 下 2×1.25=2.5、150% 选中态 3×1.5=4.5）四条边的取整
  不一致 → **同一个框「上3 下3 左3 右2」**，用户报"有的线粗有的线细"（2026-09-24 实测）。
  选中态 3 / 未选中 2 是**设计**（点击选中的框变粗）。
- **高分屏（dpr>1）**：`ImageView._rerender` 按**物理**像素出图
  （`QSize(round(w*0.96*dpr), …)`）并把 dpr 写回 pixmap；`_update_mapping` 必须把
  `scaled.width()/dpr` 换算回逻辑尺寸再算映射与居中偏移。
  ⚠️ **绝不要**再手动 `painter.scale(dpr, dpr)`：Qt 在带 `devicePixelRatio` 的
  pixmap 上作画时，painter 的坐标**已经是逻辑坐标**（dpr 在设备层生效，
  `transform().m11()` 仍报 1.0——实测 dpr=1.5 时 `drawRect(0,0,10,10)` 覆盖物理
  0~15px）。再乘一次 dpr 就是放大两次：**底图对、框错位**，看上去"框和图片比例
  对不上"（2026-09-24 真实踩过，且离屏 dpr=1 时全绿、只在 dpr≥1.25 暴露）。
  ⚠️ 按逻辑像素出图再让 Qt 按 dpr 放大 = 图被"先降后升"重采样两轮，实测 150%
  缩放下锐度差 **7.6 倍**、200% 下差 **16 倍**（100% 缩放下无差别）。跨显示器
  拖动由 `event()` 接 `DevicePixelRatioChange` 重绘。
  ⚠️ **dpr 相关的渲染改动必须用像素断言 + 真 dpr 进程验**
  （`QT_SCALE_FACTOR=1.5 python …`），只查尺寸/映射是抓不到"多乘一次 dpr"的。
- 渲染密度：预览不再写死最长边，由 `ImageView.preview_edge()` 给出
  （控件长边 × dpr，夹在 `MIN/MAX_PREVIEW_EDGE` 之间），四处调用点
  （image_viewer / pdf_viewer / rembg_viewer / print_preview）统一取用。
  ⚠️ 必须在 **GUI 线程**先算好再闭包进 worker 的 lambda（worker 线程碰 QWidget 越界）。
- 编辑交互：点选（四角手柄缩放）、拖动、Delete 删除、空白拖拽手绘；
  仅坐标变化时提交。
- 回归防护：`tests/selftests/preview_dpr.py`（74 项，含**像素级**框线位置与四边等粗断言）。
  ⚠️ 第三步预览的**显示源解析**另有 `tests/selftests/rembg_preview.py`（15 项，
  `DEPENDS=[]`，不碰管道）：`rembg.py` 依赖 `extract` 子进程，跑不了管道的环境里
  整条被跳过——2026-09-24 的 `NameError` 就是这样漏过去的。

## 5. 缩略图规范

- 命名：`thumbnails/source/<页号4位补零>.jpg`（1 起始，0001.jpg…），
  与预览查看器缓存同名，导入即生成、永不清理。
- 分辨率：最长边 `THUMBNAIL_EDGE=256`（`desktop/utils/files.py`）；
  目录 `.meta` 标记记录生成时分辨率，启动迁移仅在不匹配时清理重建。
- 预览条图标框 116×156（`ThumbStrip.ICON_SIZE`）：整页条目按最长边
  `ThumbStrip.decode_edge(dpr)`（= 框长边 × dpr）**等比缩放解码**；area=1 条目
  按框裁剪后覆盖填充。⚠️ 解码边长必须取框的**长边**：竖开本页面受高度约束，
  取框宽会让缩略图只占条目宽度的一半。⚠️ 还要乘 dpr：条目本身是按 dpr 放大
  绘制的，只解码到逻辑尺寸等于让 Qt 再放大一次（与大图预览同源的问题）；
  dpr 必须在**主线程**算好（批次工厂 `make_worker` 跑在 worker 线程里）。
- 排序：条目按 `pdf_custom_sort_key`（数字感知、同页 r→l、cover/menu 优先）。

## 6. print 页面列表与参数表单

- **print.json**（任务目录）：`[{"file": "…/stages/rembg/1.png", "label": "1"}]`，
  首次进入 print 阶段由 rembg 输出目录（自然排序）初始化。**该数组顺序即页序**
  （唯一事实来源）：拖拽重排 / 删除条目只改数组，不落地任何物理文件。
- **有序清单**：执行时把数组顺序作为 `args["files"]` 交给 CLI，效果图按该
  顺序在一次性临时目录中合成（`0001.png`…），CLI 直接按清单加载、不再读
  目录解析文件名。因此不需要 workset 这类「把顺序烧进文件名」的物化目录。
  不传清单时 CLI 仍回退到 `pdf_custom_sort_key` 文件名排序（独立用法兼容）。
- **参数表单**（阶段面板控件，**不是文本编辑框**）：键集与 CLI `print` 命令一致
  （pdf_name、paper_size、orientation、page_margins、title_*、
  title_switch_nodes、page_number_*、skip_pages）；
  `input/output/workers/clean` 由系统管理，不在表单范围内；
  `pdf_name` 缺省兜底为 `print.pdf`。
  控件创建见 `desktop/components/panels/print_form.py`，
  取值/回填见同目录 `print_params.py`。
- **效果预览的渲染密度**（`compose_print_page` / `PreviewWorker.print_spec`）：
  密度必须由宿主给（`print_spec["target_edge"]`），**不能吃默认值**——默认是
  `PRINT_PREVIEW_TARGET_EDGE(1600)` 的固定密度，与屏幕无关。
  ⚠️ 反直觉但实测确定的规律：**密度高于屏幕需求反而更清晰**，因为 Qt 的
  `SmoothTransformation` 在「一次大比例缩小」时质量明显差于「分两档温和缩放」。
  实测（A4 横向、源图 5873×3539、视口长边 788、最终显示 756）：
  「合成 3000」锐度 23200（≈ 理想 23387），「合成 1600」13121，
  「合成 = 显示尺寸（1:1 合成）」只有 9797（最糊）。
  故 `print_preview` 取 `target_edge = max(preview_edge(), MAX_PREVIEW_EDGE)`，
  并同时传 `longest_edge=0`（画布已按该密度合成，**别再缩一次**）。
- **密度的硬上限**：`compose_print_page` 把密度夹在**源图原生密度**之下
  （`image.width()/图区域宽mm`）——再往上就是凭空放大（更糊 + 白占内存）。
  所以「要 4000 与要 8000」得到同一张画布，小图不会被拉大。
- `longest_edge=0` 的语义是「不缩放（要原始分辨率）」，图片分支原样返回画布；
  ⚠️ PDF 分支此前直接相除会得到 `scale=0` → **空图**，现在显式处理为 `1.0`。
- **原比例缩放**（print 参数 `keep_ratio`，默认 True）决定自动排版与编辑器手感：
  - True：`scale = min(可用宽/w, 可用高/h)` 等比 fit（既有行为）；画布四角拖拽
    **等比**（以拖拽起点框为基准、鼠标宽高取更受限维度配对，超页整体等比缩回），
    **不提供**四边手柄；
  - False：图片**铺满**可用区域（宽高各自取满，`x=ml+reserve, y=mt`），画布四角
    拖拽也变为自由拉伸；
  - ⚠️ 画布的**四边手柄（索引 4~7，`_EDGE_BY_HANDLE`）恒可用**——拖边即单方向
    拉伸，**不受 keep_ratio 约束**（用户明确拖边就是要改那一维；曾做成"取消
    原比例才出现"，用户 16:58 报四边也要能拉伸，遂改恒显）。keep_ratio 只约束
    **四角**是否等比；
  - 与「版面编辑器逐图 rect」的关系：rect 存在就原样采用（所见即所得），本键
    只影响**没有 rect 的页**与拖拽手感；`functions/print.py` 的
    `pdf.image(w,h)` 本就直接按目标矩形拉伸，无需改动。
  - 跨层登记：`PRINT_DEFAULTS` → `PRINT_FORM_DEFAULTS`（展开）→
    `params_spec.PRINT_DEFAULTS`（引用）→ `print_params._FORM_KEYS`（表单可见键）
    → `static/guji.yaml`。护栏 `config_template` 逐值校验 CLI ↔ yaml。
- **第四步取图：只排版「提交本次任务」的成品图**（`SubmitMixin._build_print_effects`
  / `submit.py`；2026-10-01 用户口径「去底色那一步，必须提交才能传给下一步」）。
  第四步**不再**拿去底图（`stages/rembgpreview`）+ 当前 area/border 现场合成：
  area/border 在提交那一刻就兑现进 `stages/rembg`（拼版生效时是
  `stages/imposition`），第四步只把列表**整图透传**（`effect=None`）——列表顺序
  即页序、删掉即消失；编辑第四步的「待打印图」则「生成 PDF」即生效。
  ⚠️ 之前的 `plan_print_effects` 要按 label 把列表与"当前 area 派生集合"对齐
  （形态不同时还得按基础页名重映射），一旦对齐出错，用户在第四步**删掉的页会被
  补回来**（实际事故：列表 101 条却生成 198 页 PDF）。这套对齐逻辑已随该契约
  一并删除；护栏见 `print_list_layout` 第 2 节与 `print_area_border_e2e`。
- **进度条只有一个来源**：`functions/print.py` 的 `reporter.progress(已写入页数, total)`，
  `total` = **实际写入 PDF 的页数**（页面清单增删后自然变化）。
  ⚠️ 合成阶段（`print_stage`）**刻意不发 progress**：它也发一份的话，进度条会先跑完
  合成、再由写入**从 0 重跑**，用户看到"顶部 197/198、底部 160/198 两个数字对不上"
  （实际报障）。合成快（每页约 25ms），用日志（每 10 页一条）给反馈即可。
  底部那行摘要来自 `LogPanel` 取日志**最后一行**，与顶部进度条不是一个来源——
  这正是当初"两个数字不一致"的观感来源。

## 7. 图片预览弹窗（image_zoom_dialog）

`ImageView` 只管**框编辑**（点选/拖动/四角缩放/手绘），固定"适应窗口"；放大查看
走独立弹窗，**只读**——同一个画布上再叠"滚轮缩放 + 拖拽平移"会让两种拖拽打架，
而框坐标是 detect/rembg 的实际输出依据。

- **入口**：预览大图**双击** → `ImageView.double_clicked` → 宿主的
  `ZoomPopupMixin._open_zoom_popup`。四个宿主（image_viewer / pdf_viewer /
  rembg_viewer / print_preview）都实现了 `_zoom_target(index)`。
  ⚠️ `ImageView.mouseDoubleClickEvent` 必须把本次按下可能已经开始的"手绘新框"
  清掉（`_mode`/`_new_start`/`_ghost_box`），否则留橡皮筋残影还会真落一个框。
- **数据来源**：宿主在主线程造 `ZoomTarget(render, note, stem, count, original, cap)`；
  `render(edge) -> worker` 只由宿主实现（图片按最长边解码 / PDF 按该边长渲染 /
  打印效果按该边长反推 px/mm 重排）。**弹窗不认识 PreviewWorker**，也不拼路径。
  ⚠️ `render` 在 **worker 线程**被调用，闭包只能读快照值，不得碰 QWidget。
- **渲染密度** `_render_edge()`：视口**物理**长边 × `RENDER_HEADROOM(1.5)`，
  约束顺序为「先 `MIN_RENDER_EDGE(1600)` 兜底 → 再 `MAX_RENDER_EDGE(4000)`
  → 最后 `ZoomTarget.cap`（位图原生边长，**可低于下限**）」。上限拉满一页约
  45MB、PDF 渲染约 235ms，都在后台线程。
  ⚠️ 密度决定的是「**100% 时能看到多大一块**（约 1.5 个窗口）」，**不是**「放到
  多少倍还不糊」——倍率相对图片自身像素定义（1.0 = 一图片像素对一设备像素），
  任何 >100% 的显示都是放大，与源图有多少像素无关。想让深放大也锐，得做
  「按缩放级别重渲可见区域」（未做，见本节末尾）。
- **缩放倍率语义**：1.0 = 100% = **1 图片像素对 1 设备像素**，即视图变换比例
  = 倍率 ÷ dpr。为此场景里的 pixmap 刻意**不设** devicePixelRatio
  （1 场景单位 = 1 图片像素）。
- **锚点缩放**：`set_zoom(zoom, anchor_pos)` 自己算锚点——缩放时滚动量不变、
  场景点被缩成 1/factor，于是把这段偏差用 `translate()` 按场景单位补回变换上，
  实测**零漂移且多步不累积**。⚠️ 不要用 Qt 的 `AnchorUnderMouse`：它依赖私有的
  `lastMouseEventPosition`，弹窗刚打开就滚轮时该值陈旧（会退化成左上角）；
  也不要用 `centerOn` 补偏差：滚动量取整会残留约 0.9px，连续滚轮会累积。
  变换锚点固定为 `NoAnchor`，别让 Qt 插一脚。
- **翻转/旋转**非破坏性：屏幕走 `QGraphicsPixmapItem.setTransform`、导出走
  `QImage.transformed`，**两处必须共用 `display_transform()`**，否则"看到的和
  下载的不一样"。旋转后 `fitInView` 会 `resetTransform`（清掉累积平移）。
- **可拖留白**（`PAN_MARGIN_RATIO=0.25`）：场景矩形 = 图片占位 + 居中补差 +
  **每边 25% 视口**。⚠️ 中间那部分补出来正好让"内容 = 视口"，Qt 的滚动范围
  （内容显示尺寸 − 视口）仍然是 **0**，`ScrollHandDrag` 一点都拖不动——图片在适应
  窗口时必定铺满视口，所以**必须额外加留白**，"不缩放也能拖"才成立。留白依赖当前
  缩放（场景单位 vs 逻辑像素），故 `set_zoom`/`resizeEvent`/`fit` 之后都要重算。
  ⚠️ 判断"有没有滚动范围"只能看 `maximum() - minimum()`：QGraphicsView 给滚动条的
  `[min,max]` 原点会随场景原点漂移，实测两个值都是负数，拿 `maximum() > 0` 判定会
  得出"没有范围"的假结论。
  ⚠️ 几何/朝向判断一律用 `image_rect()`（图片占位），**不要**用 `sceneRect()`
  （含留白）——否则"旋转后宽高互换"这类断言会假失败。
- **图标**：qfluentwidgets 没有可用的翻转图标（`SEARCH_MIRROR` 是带镜子的放大镜、
  `SYNC` 是循环箭头），翻转用**自绘**（两个相对三角 + 虚线镜像轴，水平/垂直只差
  90°）；左旋用 `FIF.ROTATE` 的**水平镜像**（原图箭头在弧底指向左 = 顺时针/右旋）。
  自绘图标按 16/20/24/32/48 多档位塞进 QIcon，高分屏不掉清晰度。
- **下载**：导出**整分辨率**（含翻转/旋转，与屏幕缩放无关）→ 保存对话框选
  PNG（无损）或 JPEG（画质 90）。保存逻辑抽成 `save_image(image, path, quality)`
  以便自测（对话框在离屏环境弹不出来）。
- **关窗**：作废在飞的渲染令牌 + `shutdown_workers()` + `canvas.clear()`
  （一张 4000px 预览约 45MB）。宿主换数据（`set_images`/`set_pdf`/`set_entries`/
  条目重建、第三步切形态）时调 `close_zoom_popup()`——弹窗里那页是打开时的快照。
- 回归防护：`tests/selftests/preview_zoom.py`（93 项）。

**已知不足（未做）**：>100% 的显示是放大（屏幕像素上限）。要让深放大也是 1:1，
需要「按缩放级别重渲可见区域」：缩放后按 `edge × zoom`（受 cap）重渲，再把倍率
显示归一化到 100% 并保持视图中心。⚠️ 归一化会让界面上的百分比"跳回 100%"，
得先把倍率的参考基准从"图片像素"改成"页面标称尺寸"才不误导用户——所以没顺手做。

## 8. 任务号

- `tasks.json` 中 `id` 即任务号，四位零填充（0001…），任务目录同名。
- 新任务号 = 当前最大号（索引 ∪ 磁盘目录）+ 1；删除不复用。
- 启动迁移将 uuid 目录按 created_at 重编号。

## 9. 图片拼版（节点文档、坐标与合成）

### 9.1 文档：`drafts/imposition.json`

```json
{
  "enabled": true,
  "pages": [
    {"items": [
       {"file": "…/stages/rembg/3-r.png", "rect": [x, y, w, h], "rotation": 0.0},
       {"file": "…/stages/rembg/3-l.png", "rect": [x, y, w, h], "rotation": 0.0}
     ]}
  ]
}
```

- 放在 `drafts/` 是**历史原因**（占位节点时代就存 `{"enabled": bool}`），
  换位置会让老任务的选择态丢失；
- `items` **恒 2 项**：`0` = 右槽（源清单序号在前），`1` = 左槽；
- `rect` 单位是**源图像素**（左上原点、x 向右、y 向下）；
- ⚠️ **没有 `sheet`**（用户 2026-09-30：「拼版不需要设置纸张，只需要
  背景是白色的就行，后续提交时根据图片的四个区域合并出一张图片」）：老文档里
  的 `sheet` 读进来直接忽略；
- `rotation` 是**顺时针角度**（Qt `QPainter.rotate` 口径，PIL 侧取负），
  绕该项 `rect` 的中心；
- 读写与形状校验：`store/imposition.py`（IO）+ `services/imposition.py`
  （`normalize_page` / `normalize_doc`，唯一校验处）。

### 9.2 产出：`stages/imposition/0001.png …`

- 文件名按**列表顺序**编号（列表顺序即 PDF 页序）；重合成时序号更大的旧文件
  会被清掉（`compose_doc` 的 `_sweep_stale`），否则用户删页后旧页还会进 PDF；
- 合成白底 PNG，**尺寸 = 两张图外接框的紧裁**（`page_bounds`）：没有纸张，
  图上多大、挪多远，产出就跟到哪；去底图自带的透明在此压到白底
  （与 `functions.print` 的压平一致）；
- 触发：版面/页数变化 → 500ms 防抖 → **后台线程**重合成
  （`workers/imposition_worker.py`）；点「生成PDF」前再**同步**补一次
  （`_compose_imposition_now`），保证 PDF 用的是最新版面。

### 9.3 画布：`components/imposition/canvas.py`

拼版 UI 组件包 `components/imposition/` 按操作逻辑分两个模块：**模块一
「选择拼版」**（`page_list.py` 左列清单 + `picker.py` 弹窗）与**模块二
「拼版操作」**（`canvas.py` 画布 + `panel.py` 控制面板），`view.py` 是装配层；
控制器在 `pages/taskdetail/` 同样按模块拆：`imposition.py`（共享基元）、
`imposition_pages.py`（模块一）、`imposition_layout.py`（模块二）。

左列清单（`page_list.py`）每格 `_PageEntry` **左上有勾选框**（用户 2026-09-30；
钉死 22px 小方块——qfluentwidgets CheckBox 空文本的 sizeHint 有 57px 宽，
不钉死就与页标题隔着大空档）。勾选数驱动**悬浮操作条** `_SelectBar`
（「已选 N 页」+「取消选择」「批量删除」，浮在滚动区下沿、勾选数归零自动
收起），点「批量删除」经 ``batch_delete_requested`` → 控制器
`_on_imposition_batch_delete` **弹窗确认**后批量删页。勾选集合**按副标题
（caption）跨 `set_pages` 重建保留**——拖动排序/加页不丢勾，页被删则自然
落选；勾选框吃掉自己的鼠标事件，不会触发条目的切页/拖动排序。
「＋ 选择拼版」格**钉在左列最底部**（滚动区之外，不随页数上下移动）。

画布是 `PrintLayoutCanvas` 的同族实现（页面坐标 → 控件像素等比适配），差异在于
可以放**多张**图、每张带旋转：`rect` 是落点框、`rotation` 只作用于框内图像
（框线恒画在未旋转的矩形上），手柄命中沿用「四角圆点邻域 + 四边整条命中带」
并多一个**旋转钮**（框上方 26px）。

**框线两态**（用户 2026-09-30 口径）：**点击某张图 → 选中**，选中的图带一圈
**常显的细虚线**（`_draw_selected_border`，选中状态一直看得见）；**按住鼠标
操作期间**才升级为 `Qt.DashLine` 虚线框 + 手柄 + 旋转钮（`_pressed` 为真时画，
`mouseRelease`/`leaveEvent`/`flush_pending` 都把它清掉，松手回到细框）。
**载页/切页/点空白处都清空选中**（`set_page` 恒 `_selected=-1`，不自动选中；
`view.set_current` 对"画布已是这份版面"的回灌会跳过 `set_page`，拖动落盘后的
刷新不掉选中态）。因此**命中判定必须是几何的**，不能依赖"看得见手柄"——
未按下时靠光标提示（图内 `OpenHand`、四角/四边缩放光标、圆钮处 `Cross`）。

**红色对齐线恒显 + 旋转组件**（用户 2026-09-30 口径）：`paintEvent` 在图之上
画一条 `SPINE_COLOR`（`#E02020`）红色垂直虚线，x 取 `_spread_center_units()`——
**两图未旋转 rect 中心的中点**（单图时即其中心）。用 rect 中心而不是外接框
中心是刻意的：单图自转不挪 rect 中心、整版旋转又绕这个中点公转，所以无论
怎么转对齐线都钉在同一处。旋转有两条入口，都**只重绘不上报**（脏标记交给
控制器的停顿计时器 `EDIT_COMMIT_DEBOUNCE_MS=250` 统一 `flush_pending` 落盘，
避免滑块每 1° 就走一遍 set_page + 落盘 + 合成）：

- **整版旋转** `canvas.rotate_whole(delta)`：每图"rect 中心绕公共中心公转
  （y 向下坐标系的视觉顺时针矩阵）+ 自身 `rotation` 叠加"——两图相对位置、
  相对角度不变，对齐线不动；`spread_rotation()` 取两图平均角收敛到
  [-180, 180) 当整版角度（单图转过后角度差原样保留）；
- **单图绝对角度** `canvas.set_item_rotation(angle)`：只改选中图的
  `rotation`（绕自身 rect 中心），提交后 `refit()` 重新适配可视区。

面板（`panel.py`）按用户 2026-09-30 口径**分区分布**：页级块**「操作当前
图片页」**（整体旋转 / 复位本页版面 / 删除本页拼版（这两个**同行**）/
清空全部拼版）与图片级块**「操作当前图片」**（旋转，`_ItemSection` 自绘框）
分开；说明收在标题旁的 `desktop.ui.widgets.HelpButton` 问号按钮里（与
`StagePanel` 同款），**「在流程中启用图片拼版」开关放面板最底部**；
面板上**没有**「选择拼版」按钮（入口只在左列虚线格，`add_requested`
信号随之移除）。图片级块
**只在画布里选中了某张图时激活并高亮**（描边 `ACCENT` + 浅底 `ACCENT_SOFT`，
未选中灰底 + "未选中图片"提示），切页/点空白取消选中后整块灰掉。两组旋转组件
都是「`Slider`（1°/格）+ `DoubleSpinBox`（1° 步进）」：**整体旋转**发
`whole_rotate_delta`（**增量**，跨 ±180° 边界按 wrap 取最近方向），**选中图
旋转**发 `item_rotation_edited`（**绝对角度**，未选中时禁用）；程序化回填走
`set_whole_angle` / `set_item_rotation`（blockSignals 语义不回抛，后者同时驱动
图片块的高亮态），挂在 `_update_imposition_status` 这个"当前页/选中变了"的
汇聚点上同步。旋转组件是**微调口径**（用户 2026-09-30）：输入框挂说明行右侧
（2 位小数、步进 0.1°），滑块**通栏独占一行**、内部值 = 度数 ×100 即
**0.01°/格**（键盘 1 格 0.01°、PageUp/Down 1°），大角度直接在输入框键入。
画布还**恒显**一条灰色虚线框（`CROP_COLOR`，`_draw_crop_frame`）＝两图旋转后
外接框的并集——与 `services.imposition.page_bounds` 同一套几何
（`_item_box_units` 是它的画布版），即成品紧裁范围的可视化。

### 9.4 选择弹窗：真控件卡片网格

`ImpositionPickerDialog` **不用** `QListWidget` 的图标模式——那条路把缩略图尺寸
与文字排版交给委托按 `sizeHint` 自行决定，在真机上（高分屏 + 真实的
「1bit 调色板 + tRNS 白底透明」PNG）会把卡片内容画成一小条、文字也看不见
（用户 2026-09-30 截图报过）。改成一排**真控件卡片**：

- `_SourceCard`：固定 `CARD_W×CARD_H = 188×264`，内含**固定尺寸**
  `THUMB_W×THUMB_H = 156×196` 的缩略图 QLabel + 名字 QLabel，勾选框与选中底
  由卡片 `paintEvent` 自绘。⚠️ 顶部留 `CARD_HEAD=30` 的「页眉」放勾选框——
  子控件（缩略图）会盖在卡片之上，不留位置勾选标记就被压住。
- `_CardGrid`：`QGridLayout` + `resizeEvent` 重排，列数 = `(宽度+gap)//(CARD_W+gap)`，
  等价于 flex 换行（窗口变宽一行放更多），卡片尺寸不变、不拉伸变形。
- 缩略图：整幅解码后**自己缩**进固定框（`_source_thumb_pixmap`），**不用**
  `QImageReader.setScaledSize`——对 1bit 调色板 PNG 的缩放读取会给出尺寸异常的图
  （正是"卡片里只有一段残图/空白"的来源）。分批 6 张/轮解码，弹窗不卡。
- 交互：点**整张卡片**即勾选（`toggle_card`），超过两张回退并提示；勾选结果
  按**源清单顺序**返回（序号在前的排拼版页右侧）。

护栏：`tests/selftests/imposition.py`（88 条，含"真实白底透明 PNG 也能出缩略图"、
"无纸张：产出按外接框紧裁"、"拖动/缩放不设范围限制"）。
