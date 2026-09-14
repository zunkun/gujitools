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
| `finished` | 子任务完成 | done, total, output |
| `error` | 失败（原因进日志） | message |
| `cancelled` | 被中断 | — |
| `boxes` | 预览单图检测结果（mode=detect） | image, left, right |
| `detect_error` | 单图检测失败 | image, message |

标记行解析：功能模块 print 的 `进度: d/t`、`图片总数: n` 等由 `ProgressStream`
解析为 progress 事件；`[boxes] <stem> left=… right=…`（text_region）与
`[imgsize] <stem> w,h`（pdf_utils）解析为结构化事件，不进日志视图。

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

与 `functions/text_region.py` 输出几何完全一致（CLI crop/cropremove 同规范）：

| 场景 | 输出 |
| --- | --- |
| area=1 | 每个文本框各一张：框 + border（border 缺省为 0），文件名 `-l`/`-r` |
| area=2 双框 | 一张：并集画布 + border，两框内容按原位置粘贴，**框间内容丢弃（留白）** |
| area=3 双框 | 一张：并集区域**整块**作为 ROI（框间内容保留）+ border |
| area=2/3 单框 + border | 对称画布：宽 = 左 + 框宽×2 + 10mm 间隔 + 右，内容在一侧 |
| area=2/3 border 未填 | 整页尺寸画布，仅框内（area=3 为并集内）保留内容，其余留白 |

- border 解析：`utils.box_geometry.parse_border_mm`（mm→px @300dpi，
  CSS 风格 1~4 值，返回 [top, right, bottom, left]）。
- 合成在 worker 线程完成（`compose_region_output` + `compose_outputs_horizontal`），
  多输出横向拼接展示；不生成文件。
- rembg 预览默认显示去底色结果，可切换原图；两者均按上述规则裁剪显示。

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

## 6. print 页面列表与 YAML 参数

- **print.json**（任务目录）：`[{"file": "…/stages/rembg/1.png", "label": "1"}]`，
  首次进入 print 阶段由 rembg 输出目录（自然排序）初始化。
- **顺序物化**：执行时按列表顺序在 workset 生成顺序命名硬链接
  （`0001.png`…），CLI 的 `pdf_custom_sort_key` 输出顺序与列表严格一致。
- **YAML 参数**（阶段面板文本编辑）：键集与 CLI `print` 命令一致
  （pdf_name、paper_size、orientation、page_margins、title_*、
  title_switch_nodes、page_number_*、skip_pages）；
  `input/output/workers/clean` 由系统管理，编辑器中出现也会被剥离；
  `pdf_name` 缺省兜底为 `print.pdf`。

## 7. 任务号

- `tasks.json` 中 `id` 即任务号，四位零填充（0001…），任务目录同名。
- 新任务号 = 当前最大号（索引 ∪ 磁盘目录）+ 1；删除不复用。
- 启动迁移将 uuid 目录按 created_at 重编号。
