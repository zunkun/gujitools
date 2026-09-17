# GUI 细节（桌面端 desktop/）

> 从 MEMORY.md 拆出，避免主文件过长被截断注入。按需读本文件。

## 截图与操作指南维护闭环

- 截图 `tests/gui_shot.py`：默认 6 张总览 → `<out>/`；`--guide` 12 张分步 →
  `<out>/guide/`，入库 `docs/guide/screenshots/guide/*.png`。
- 指南 `docs/guide/gui-guide.md`；护栏 `tests/selftests/gui_guide.py`（29 断言）：
  无裂图无孤儿、指南点名的按钮文案必须在 `desktop/**.py` 存在、`gui_shot.py` 文件名
  集合 == 磁盘、四步骤顺序 == `desktop.store.STAGES`、三份索引收录、演示数据契约
  （真实古籍优先 + `DEMO_PAGE` 一致）、**演示缩略图无全白**。

## ⚠️ 「缩略图看起来没加载完」成因相反，别瞎等

用户曾反馈后我们加了等待逻辑，但**图标其实早就就绪**——真因是**内容是白的**。

| 成因 | 判据 | 处理 |
|---|---|---|
| 图标还没回填 | `icon.pixmap() == strip._placeholder` | 等（`wait_for_thumbnails`） |
| 已就绪但内容是白图 | cacheKey 都不同，深色占比 ≈ 0 | **等多久都没用**，查坐标系 |

真因：`_page_thumb_for()` 用 `sx = 缩略图宽 / image_size 宽` 把检测框（阶段图坐标系）
换算到缩略图。若 `image_size` 记成**缩略图**尺寸，`sx` 恒为 1，2400px 的框被拿去裁
700px 缩略图 → 越界裁出纯白。

**规则**：`save_image_size(task_id, key, w, h)` 必须记**阶段图尺寸**（extract 产物），
不是缩放后的缩略图尺寸。`_assert_demo_thumbs_not_blank()` 实际合成并采样深色占比，
**< 2% 判「疑越界裁白」**（报 `001(深色仅 0%，疑越界裁白)`）。
`wait_for_thumbnails()` **只管「图标换了没有」**，管不了内容对不对，别往里加内容判断。

**排查方法论**：像素/渲染不对时，先**把数据对象单独拎出来量**（逐个
`item.icon().pixmap().toImage()` 数深色像素）再怀疑绘制层；取样窗口要覆盖整个控件，
取窄了会量到滚动条/边框而误判。

## ⚠️ GUI print 面板是「参数表单」，不是 YAML 编辑器

**曾有四份文档说错**（FR-06 / gui-design / technical-spec §6 / layout），描述成
「右侧 YAML 文本编辑面板」。实际 `print_form.py` 有 19 处 `_add_row`、零个 `QTextEdit`。
**写这类文档先读源码，别信旧文档。**

## ⚠️ 列表条目几何：图标框 ≠ 网格

`print_preview.py` 曾 `ICON 180x240` + `GRID 200x290` + `AlignBottom` → 每个条目被强制
成 200x290、文字钉在网格最底，**图片与文字间恒定 50px 死区**（与图片宽高比无关）。

- 观感差异来自图片比例：`area=2 + border=None` 输出整页画布（2481x3508，ratio 1.414）
  几乎占满图标框，死区一眼可见；`area=1` 输出 900x2600（ratio 2.889）只占约 83px 宽，不刺眼。
- **规则**：IconMode 列表设了 `setGridSize` 就**不得用 `AlignBottom`**（会被推离图标）；
  网格高 = 图标高 + 文字区（现 `LABEL_H=44` → 200x284）。
- 诊断：`QListWidget.visualItemRect(item)` 返回**网格尺寸**，与图片比例无关——
  可快速判定「条目高」是网格写死还是图片真的高。
- 回归 `tests/selftests/print_list_layout.py`（10 断言）。

## ⚠️ 操作 GUI 内部状态截图的必知点

1. **detect 的框在内层 `ImageView`**（`detect_viewer.view`），不是外层
   `ImageViewerWidget`。错对象上取 `_boxes` 会**静默返回 `None`**，交互态全丢、截图重复。
2. **改交互态后必须 `_rerender()`，不能用 `update()`** —— 框烘焙进位图，`update()` 只重绘旧图。
3. **交互态要在 `before` 回调里施加**：`set_boxes()` 会把 `_selected` 重置为 `None`。
4. 回任务列表 `window.pages.setCurrentWidget(window.list_page)`；
   `TaskStore.list_tasks()` 的字典键是 `id` 而非 `task_id`。
5. **`QImage.scaled()` 没有 `keep_aspect_ratio` 关键字**，位置参数是
   `(w, h, AspectRatioMode, TransformationMode)`，写错抛 `TypeError`；若外层有
   `except Exception` 会被吞 → 「数据灌入失败」静默回退。**兜底 except 一定要打 `{exc!r}`**。
6. **print 面板的下拉是「中文显示 / 英文值」双列 combo**，值在 `itemData`：
   `setCurrentText("portrait")` **静默选不中**（显示文案是「竖版」），必须
   `findData()` + `setCurrentIndex()`。（rembg 面板的 area/type 是纯文本列表，可直接 setCurrentText。）
7. 离屏截图：**`QFontDatabase.addApplicationFont` 必须在 `QApplication()` 之后调**，
   否则段错误。字体 msyh.ttc / msyhbd.ttc / simhei.ttf / simsun.ttc。

## 演示数据来源（gui_shot.py）

**优先真实古籍**：`GUJI_SHOT_PDF` 环境变量 → `REAL_PDF_DIRS` 里含「龍譚精舍叢刻」的 PDF
→ 该目录任意 PDF；配套产物取同级 `guji_work/book/{images,detect,rembg}`。
找不到则回退合成占位图。演示页由 `DEMO_PAGE` 常量控制（**当前 4**，用户明确要求不用第 3 页）
——改动它必须重跑 `gui_selftest.py --only gui_guide`。

`store.detect_boxes_entry(task_id, key)` 返回 `(boxes, origin)`；
`detect_page_boxes()` 返回 `(left, right)` 各可为 `None`，存库要转成列表。
