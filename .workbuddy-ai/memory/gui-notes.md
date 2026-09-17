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

## 任务名称列 = 链接样式（下划线 + 主色 + hover + 点击跳详情）

`desktop/components/task_table.py`：`NameLabel(QLabel)` + `_name_widget()` 放进
cellWidget。护栏在 `tests/selftests/tasklist.py`。

- ⚠️ **`QTableWidgetItem` 文本必须留空**：cellWidget 是透明的，item 里再写一遍
  名字就是「一条名字显示两次」的重影。item 只留 `UserRole=task_id`（`select_task()`
  靠它定位行）。因此**读任务名要去 QLabel 取**（`tasklist_pagination` 已改）。
- ⚠️ 主题里**没有 `T.PRIMARY`**，主色是 `ACCENT` / `ACCENT_HOVER`（写错 = 一进列表页崩）。
- 下划线是 `paintEvent` 自绘（字体下划线间距不可调），颜色走 `setLinkColor()`，
  不要再用 stylesheet 的 `color:` 判断。
- elide 放在 `resizeEvent`：建表时 `columnWidth()` 只有几十像素，会把名字截成空串。
- **像素级断言的两个坑**：① 离屏下窗口没 `show()`，单元格控件被布局压成 10px 宽，
  名字被省略成「…」→ 断言前先 `show()` + `processEvents()`，验完 `hide()`
  （一直可见会打乱后续模块读子进程日志的时序）；② 1px 线落在半像素上会被抗锯齿
  摊成两行半透明，**不能比「等于主色」**，按「非白像素」统计最长行。

## 桌面端用户手册（运行时 MD → HTML → 系统浏览器）

`desktop/ui/help_dialog.py` 导出 `generate_manual_html()` / `open_manual()` /
`manual_dir()` / `MANUAL_ENTRIES`（**`ManualDialog` 类已删**）；新加手册只改
`MANUAL_ENTRIES`。任务列表页 `PageHeader.actions` 的「用户手册」按钮调 `open_manual()`。

- **不是构建步骤**：HTML 每次打开时运行时生成，无产物漂移。一个 HTML 装全部手册，
  顶部吸顶分段开关（JS 切 tab），落在固定临时文件名 `guji_manual.html`。
- CSS 用 `string.Template`（`$TOKEN`）不用 f-string；色值取 `theme.py` 令牌。
- ⚠️ `<base>` 必须指向手册目录**且带结尾斜杠**（护栏断言 `endswith("docs/guide/")`）。
- ⚠️ img 的 src 必须经 `_absolutize_image_srcs()` + `Path.as_uri()` 编成绝对
  `file:///`（截图名含中文，靠 `<base>` 让浏览器编码会「有框无图」）。
- ⚠️ `open_manual()` 的 URL 带 `?v=<时间戳>`：固定文件名 + file:// = 强缓存。
- ⚠️ markdown 扩展**静态 import 类再传实例**（`TableExtension()` 等），不能传字符串名
  ——按名加载走 entry point，frozen 下 `.dist-info` 未必打包 → 一打包就 ImportError。
- 指南间互链 `[cli.md](cli.md)` 改写成 `#tab-cli`，否则浏览器把 .md 当纯文本。
- `guji.spec`：`gui_datas` 含 `('docs/guide','docs/guide')`；`gui_hiddenimports`
  追加 `collect_submodules('markdown')`。护栏 `tests/selftests/manual_dialog.py`（37 断言）。
- 资源定位复用 `package_dir()`：`manual_dir() = package_dir().parent/"docs"/"guide"`。
- **教训：自测全绿 ≠ 用户看到对**——浏览器缓存与 CJK 图片编码两个 bug 都是用户实测才暴露。

## 演示数据来源（gui_shot.py）

**优先真实古籍**：`GUJI_SHOT_PDF` 环境变量 → `REAL_PDF_DIRS` 里含「龍譚精舍叢刻」的 PDF
→ 该目录任意 PDF；配套产物取同级 `guji_work/book/{images,detect,rembg}`。
找不到则回退合成占位图。演示页由 `DEMO_PAGE` 常量控制（**当前 4**，用户明确要求不用第 3 页）
——改动它必须重跑 `gui_selftest.py --only gui_guide`。

`store.detect_boxes_entry(task_id, key)` 返回 `(boxes, origin)`；
`detect_page_boxes()` 返回 `(left, right)` 各可为 `None`，存库要转成列表。

## 自定义矢量图标（`desktop/ui/icons.py`）

内置 FIF 没有「带圆圈的问号」：`QUESTION` 是**被裁到边框上的裸问号**，`HELP` 糊成一团且
超出画布，`INFO`（环 + `i`）才是干净样板。自绘见 `desktop/ui/icons.py` 的 `SvgIcon`。

**⚠️ `FluentIconBase` 自绘 SVG 必须同时重写 `icon()` 和 `render()`**（详见 2026-09-17 日志）：
基类两条链都靠 `path.endswith('.svg')` 区分「文件路径 vs 源码」，源码字符串会被当文件名
→ 空图标；而 `PushButton.paintEvent` 在 `icon().isNull()` 时直接 return（只剩文字）。
- `icon()` → `QIcon(SvgIconEngine(svg))`
- `render()` → `drawSvgIcon(svg.encode(), painter, rect)`

## 看不到图时如何「看」界面（ASCII 探针）

本会话里模型读不了图片。可渲染 → 采样像素 → 打成 ASCII 打印出来判断形状，
比 `isNull()` 之类的布尔断言强得多（能看出「裁到边框」「糊成一团」「偏下」）。
写法：`icon.icon().pixmap(34,34).toImage()`，逐像素取 alpha/亮度映射到 `" .:-=+*#%@"`。
同理可用于 `btn.grab()` 后截取左侧 40px 确认「按钮上图标真的画出来了」。
