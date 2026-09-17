# 桌面端技术规范（与 desktop/ 当前实现对齐）

## 1. Worker 消息协议（JSON Lines）

worker 子进程 stdout 每行一个 JSON 对象，均含 `type` 与 `task_id/stage/run_id`：

| type | 说明 | 关键字段 |
| --- | --- | --- |
| `started` | 子任务启动 | stage |
| `progress` | 进度（GUI 更新 runs.json + 进度条） | done, total |
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

- 布局层入口：`utils.box_geometry.build_output_layout` /
  `build_symmetric_layout`（返回冻结 dataclass `OutputLayout` / `Canvas`）。
  单框对称输出必须由调用方用 `symmetric=True` 显式选择 —— 合并后的单框
  （area=3）走普通布局，布局层不猜。
- border 解析：`utils.box_geometry.parse_border_mm`（mm→px @300dpi，
  CSS 风格 1~4 值，返回 [top, right, bottom, left]）。
- 合成在 worker 线程完成（`compose_region_output` + `compose_outputs_horizontal`），
  多输出横向拼接展示；不生成文件。
- rembg 预览默认显示去底色结果，可切换原图；两者均按上述规则裁剪显示。
- 回归防护：`tests/selftests/box_geometry.py`（规格一致 + 两侧同源）。

## 4. 检测框规范

- 坐标基准：原始图片像素（extract 记录于 sizes.json）。
- 存储：`[左框, 右框]`，缺失一侧 null；手动编辑后为紧凑列表（保持左先顺序）。
- 预览映射：显示缩放比以原始尺寸为基准（`ImageView._update_mapping`），
  鼠标命中/拖拽/绘制共用同一映射，窗口缩放后立即生效。
- 编辑交互：点选（四角手柄缩放）、拖动、Delete 删除、空白拖拽手绘；
  仅坐标变化时提交。

## 5. 缩略图规范

- 命名：`thumbnails/source/<页号4位补零>.jpg`（1 起始，0001.jpg…），
  与预览查看器缓存同名，导入即生成、永不清理。
- 分辨率：最长边 `THUMBNAIL_EDGE=256`（`desktop/utils/files.py`）；
  目录 `.meta` 标记记录生成时分辨率，启动迁移仅在不匹配时清理重建。
- 预览条图标 96×128：整页条目缩放解码；area=1 条目按框裁剪后覆盖填充。
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

## 7. 任务号

- `tasks.json` 中 `id` 即任务号，四位零填充（0001…），任务目录同名。
- 新任务号 = 当前最大号（索引 ∪ 磁盘目录）+ 1；删除不复用。
- 启动迁移将 uuid 目录按 created_at 重编号。
