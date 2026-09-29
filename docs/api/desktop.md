<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# desktop API 参考

桌面端：GUI 主进程、worker 子进程、存储、界面系统

覆盖 77 个模块、82 个公开类、443 个公开函数/方法（生成于 2026-09-29）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`desktop.app`](#desktopapp) | 1 | 4 |
| [`desktop.components.common.safecomment`](#desktopcomponentscommonsafecomment) | 6 | 12 |
| [`desktop.components.log_panel`](#desktopcomponentslog_panel) | 1 | 9 |
| [`desktop.components.pagination`](#desktopcomponentspagination) | 2 | 11 |
| [`desktop.components.panels.base`](#desktopcomponentspanelsbase) | 1 | 7 |
| [`desktop.components.panels.detect_panel`](#desktopcomponentspanelsdetect_panel) | 1 | 3 |
| [`desktop.components.panels.extract_panel`](#desktopcomponentspanelsextract_panel) | 1 | 1 |
| [`desktop.components.panels.params_spec`](#desktopcomponentspanelsparams_spec) | 0 | 2 |
| [`desktop.components.panels.print_form`](#desktopcomponentspanelsprint_form) | 1 | 1 |
| [`desktop.components.panels.print_inset`](#desktopcomponentspanelsprint_inset) | 1 | 0 |
| [`desktop.components.panels.print_nodes`](#desktopcomponentspanelsprint_nodes) | 2 | 9 |
| [`desktop.components.panels.print_panel`](#desktopcomponentspanelsprint_panel) | 1 | 9 |
| [`desktop.components.panels.print_params`](#desktopcomponentspanelsprint_params) | 0 | 5 |
| [`desktop.components.panels.print_sections`](#desktopcomponentspanelsprint_sections) | 1 | 0 |
| [`desktop.components.panels.print_text_layout`](#desktopcomponentspanelsprint_text_layout) | 1 | 0 |
| [`desktop.components.panels.rembg_panel`](#desktopcomponentspanelsrembg_panel) | 1 | 1 |
| [`desktop.components.step_bar`](#desktopcomponentsstep_bar) | 2 | 15 |
| [`desktop.components.task_table`](#desktopcomponentstask_table) | 3 | 10 |
| [`desktop.components.viewers.image_view`](#desktopcomponentsviewersimage_view) | 1 | 22 |
| [`desktop.components.viewers.image_viewer`](#desktopcomponentsviewersimage_viewer) | 1 | 11 |
| [`desktop.components.viewers.image_zoom_dialog`](#desktopcomponentsviewersimage_zoom_dialog) | 4 | 31 |
| [`desktop.components.viewers.pdf_viewer`](#desktopcomponentsviewerspdf_viewer) | 1 | 2 |
| [`desktop.components.viewers.print_layout_canvas`](#desktopcomponentsviewersprint_layout_canvas) | 1 | 11 |
| [`desktop.components.viewers.print_preview`](#desktopcomponentsviewersprint_preview) | 1 | 11 |
| [`desktop.components.viewers.rembg_viewer`](#desktopcomponentsviewersrembg_viewer) | 1 | 8 |
| [`desktop.components.viewers.thumb_strip`](#desktopcomponentsviewersthumb_strip) | 1 | 10 |
| [`desktop.components.viewers.thumbs_loader`](#desktopcomponentsviewersthumbs_loader) | 1 | 1 |
| [`desktop.pages.taskdetail.detect`](#desktoppagestaskdetaildetect) | 1 | 0 |
| [`desktop.pages.taskdetail.history`](#desktoppagestaskdetailhistory) | 1 | 0 |
| [`desktop.pages.taskdetail.manifest`](#desktoppagestaskdetailmanifest) | 1 | 2 |
| [`desktop.pages.taskdetail.page`](#desktoppagestaskdetailpage) | 1 | 8 |
| [`desktop.pages.taskdetail.params_draft`](#desktoppagestaskdetailparams_draft) | 1 | 1 |
| [`desktop.pages.taskdetail.print_list`](#desktoppagestaskdetailprint_list) | 1 | 0 |
| [`desktop.pages.taskdetail.rembg_live`](#desktoppagestaskdetailrembg_live) | 1 | 0 |
| [`desktop.pages.taskdetail.runner`](#desktoppagestaskdetailrunner) | 1 | 2 |
| [`desktop.pages.taskdetail.submit`](#desktoppagestaskdetailsubmit) | 1 | 1 |
| [`desktop.pages.taskdetail.view`](#desktoppagestaskdetailview) | 2 | 4 |
| [`desktop.pages.tasklist.page`](#desktoppagestasklistpage) | 1 | 6 |
| [`desktop.services.font_catalog`](#desktopservicesfont_catalog) | 1 | 6 |
| [`desktop.services.print_plan`](#desktopservicesprint_plan) | 0 | 5 |
| [`desktop.services.rembg_live`](#desktopservicesrembg_live) | 0 | 3 |
| [`desktop.services.stale_chain`](#desktopservicesstale_chain) | 0 | 2 |
| [`desktop.services.submit_state`](#desktopservicessubmit_state) | 0 | 1 |
| [`desktop.single_instance`](#desktopsingle_instance) | 0 | 3 |
| [`desktop.stages.detect_stage`](#desktopstagesdetect_stage) | 0 | 2 |
| [`desktop.stages.events`](#desktopstagesevents) | 2 | 9 |
| [`desktop.stages.generic_stage`](#desktopstagesgeneric_stage) | 0 | 2 |
| [`desktop.stages.print_stage`](#desktopstagesprint_stage) | 0 | 3 |
| [`desktop.stages.rembg_stage`](#desktopstagesrembg_stage) | 0 | 1 |
| [`desktop.store.annotations`](#desktopstoreannotations) | 1 | 8 |
| [`desktop.store.drafts`](#desktopstoredrafts) | 1 | 5 |
| [`desktop.store.json_io`](#desktopstorejson_io) | 0 | 2 |
| [`desktop.store.pages`](#desktopstorepages) | 1 | 9 |
| [`desktop.store.runs`](#desktopstoreruns) | 1 | 7 |
| [`desktop.store.store`](#desktopstorestore) | 1 | 1 |
| [`desktop.store.tasks`](#desktopstoretasks) | 1 | 20 |
| [`desktop.ui.font_setup`](#desktopuifont_setup) | 2 | 8 |
| [`desktop.ui.fonts`](#desktopuifonts) | 0 | 1 |
| [`desktop.ui.help_dialog`](#desktopuihelp_dialog) | 0 | 6 |
| [`desktop.ui.icons`](#desktopuiicons) | 2 | 4 |
| [`desktop.ui.segmented_toggle`](#desktopuisegmented_toggle) | 1 | 11 |
| [`desktop.ui.style`](#desktopuistyle) | 0 | 3 |
| [`desktop.ui.theme`](#desktopuitheme) | 0 | 2 |
| [`desktop.ui.widgets`](#desktopuiwidgets) | 8 | 35 |
| [`desktop.utils.files`](#desktoputilsfiles) | 0 | 8 |
| [`desktop.utils.icon`](#desktoputilsicon) | 0 | 3 |
| [`desktop.worker`](#desktopworker) | 0 | 1 |
| [`desktop.workers.copy_source_worker`](#desktopworkerscopy_source_worker) | 2 | 4 |
| [`desktop.workers.hash_worker`](#desktopworkershash_worker) | 1 | 2 |
| [`desktop.workers.image_list_worker`](#desktopworkersimage_list_worker) | 1 | 2 |
| [`desktop.workers.preview_worker`](#desktopworkerspreview_worker) | 1 | 11 |
| [`desktop.workers.rembg_live_worker`](#desktopworkersrembg_live_worker) | 1 | 3 |
| [`desktop.workers.render_lock`](#desktopworkersrender_lock) | 0 | 1 |
| [`desktop.workers.serial_jobs`](#desktopworkersserial_jobs) | 1 | 9 |
| [`desktop.workers.source_thumbnails_worker`](#desktopworkerssource_thumbnails_worker) | 1 | 4 |
| [`desktop.workers.task_rows_worker`](#desktopworkerstask_rows_worker) | 1 | 2 |
| [`desktop.workers.worker_host`](#desktopworkersworker_host) | 1 | 4 |

---

## `desktop.app`

源码：[`desktop/app.py`](../../desktop/app.py)

gujitools 桌面端主窗口：任务列表页 + 任务详情页切换。

### 模块常量

| 名称 | 值 |
| --- | --- |
| WINDOW_TITLE | `"古籍重製"` |

### `class MainWindow(QMainWindow)`

主窗口：在任务列表页与任务详情页之间切换。
创建时设定窗口最小尺寸并套用全局底色；通过 QStackedWidget 持有两页，
并连接列表页「打开详情」与详情页「返回」信号完成页面跳转。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `detail_page()` | 详情页实例（惰性构造）。 |
| `keyPressEvent(event) -> None` | ←/→ 转发给详情页翻页。 |
| `closeEvent(event) -> None` | 关闭窗口时先让详情页收尾 worker 子进程。 |

##### `detail_page()`

装饰器：`property`

详情页实例（惰性构造）。

保留这个公开属性名：``tests/selftests/_context.py`` 与
``tests/gui_shot.py`` 都按 ``window.detail_page`` 取页面来操作控件。
读它本身就等于声明「现在就需要详情页」，因此访问即构造——与启动期
惰性并不冲突。

##### `keyPressEvent(event) -> None`

←/→ 转发给详情页翻页。

⚠️ 点击预览大图（QLabel 默认不收焦点）后，焦点落在**主窗口本身**，
按键只会到这里——不转发的话，用户点完图片按左右毫无反应
（用户 18:29 实测）。两条边界：
- 只在**详情页可见**时转发（任务列表页没有翻页语义）；
- 焦点在参数输入区等输入类控件时，方向键被它们自己消费（移光标/
  改值），根本到不了这里——「焦点在输入区不切换」天然成立，
  且详情页的 navigate_by_arrow 里还有同一道守卫兜底。

##### `closeEvent(event) -> None`

关闭窗口时先让详情页收尾 worker 子进程。
详情页持有 worker 子进程与后台线程的引用，直接退出会让进程被强杀；
这里把事件转交给详情页的 closeEvent 完成 kill/等待/清理后再接受关闭。
详情页是惰性的——没建过就说明没有 worker 需要收尾。

列表页也要收尾：导入后的「复制源文件 + 生成缩略图」在后台队列里，
整本可能几千页（实测 2400 页要 69s），退出时让它尽快收手。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `main() -> int` | 创建 QApplication、套用样式并显示主窗口，返回退出码。 |

#### `main() -> int`

创建 QApplication、套用样式并显示主窗口，返回退出码。

设环境变量 ``GUJI_GUI_SELFTEST=1`` 时，主窗口构造并短暂跑过事件循环后
自动退出（退出码 0）。仅供打包后冒烟使用——GUI 是 windowed 程序，没有
控制台，导入期崩溃会弹错误框并一直挂住，靠"进程还活着"根本判断不了
成败；有了这个开关就能用**退出码**判定。

---

## `desktop.components.common.safecomment`

源码：[`desktop/components/common/safecomment.py`](../../desktop/components/common/safecomment.py)

File: safecomponents.py
修复 QFluentWidgets SpinBox / LineEdit 悬浮滚轮直接修改数值、hover自动抢焦点问题
规则：只有控件获得焦点后，滚轮才响应；无焦点时滚轮透传给外层滚动区域

### `class SafeLineEdit(QLineEdit)`

普通文本输入框：悬浮不自动聚焦，无焦点时滚轮透传

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `enterEvent(event)` | Qt 事件覆写：鼠标移入时进入高亮态。 |
| `wheelEvent(event)` | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeSpinBox(SpinBox)`

QFluentWidgets 整数SpinBox，修复悬浮滚轮修改数值

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `wheelEvent(event)` | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeDoubleSpinBox(DoubleSpinBox)`

QFluentWidgets 浮点数SpinBox（用于带 mm 单位边距控件）

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `wheelEvent(event)` | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeCompactSpinBox(CompactSpinBox)`

QFluentWidgets 紧凑版整数SpinBox

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `wheelEvent(event)` | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeCompactDoubleSpinBox(CompactDoubleSpinBox)`

QFluentWidgets 紧凑版浮点数SpinBox

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `wheelEvent(event)` | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class FluentSpinWheelFilter(QObject)`

全局事件过滤器（存量界面不想替换控件类时使用）
一次性拦截所有 fluent spinbox 无焦点滚轮事件
使用：
_filter = FluentSpinWheelFilter()
widget.installEventFilter(_filter)

#### 方法

| 方法 | 说明 |
| --- | --- |
| `eventFilter(obj, event)` | Qt 事件过滤器。 |

---

## `desktop.components.log_panel`

源码：[`desktop/components/log_panel.py`](../../desktop/components/log_panel.py)

执行日志：底部状态条 + 点击唤出的浮层。

原来日志是页面底部一张常驻卡片——空闲时是一块空白卡占着位置，展开时又把
预览区压扁。现在拆成两层：

- **状态条**（常驻，高 34px，不画卡片底，只画一条上分隔线）：状态圆点 +
  标题 + 最近一条输出，右侧是清空与展开按钮。整条可点，点击即唤出浮层。
  出错时圆点与摘要变红，不打开也能看到。
- **浮层**（按需）：从状态条上方升起，盖在预览区下缘而**不挤压**布局，内含
  完整日志（等宽字体，方便看堆栈与路径）。Esc、点击浮层外或再点状态条关闭。

浮层是状态条父控件（详情页）的子控件，因此只在首次打开时才挂到页面上，
并随状态条的位置/尺寸重排。

### 模块常量

| 名称 | 值 |
| --- | --- |
| BAR_HEIGHT | `34` |
| POPUP_HEIGHT | `260` |
| POPUP_GAP | `6` |
| POPUP_MIN_HEIGHT | `140` |

### `class LogPanel(QWidget)`

执行日志状态条：一行摘要，点击唤出日志浮层。

``log_view`` 属性指向浮层里的 QTextEdit，页面各处沿用既有的
``self.log_view.append(...)`` 调用方式，无需改动调用点。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 构建状态条外观与（尚未挂到页面上的）日志浮层。 |
| `toggle() -> None` | 在展开 / 收起之间切换（取反当前状态）。 |
| `set_expanded(expanded: bool) -> None` | 展开或收起日志浮层，并同步箭头方向与状态条摘要。 |
| `eventFilter(obj, event) -> bool` | 浮层打开期间：Esc 或点击浮层/状态条之外的任意位置即收起。 |
| `mouseReleaseEvent(event) -> None` | 点击状态条空白处即可唤出 / 收起浮层。 |
| `resizeEvent(event) -> None` | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。 |
| `moveEvent(event) -> None` | — |
| `paintEvent(event) -> None` | 画一条上分隔线与状态圆点（不画卡片底，比整张卡片轻）。 |

##### `set_expanded(expanded: bool) -> None`

展开或收起日志浮层，并同步箭头方向与状态条摘要。

展开时把浮层挂到页面、定位到状态条正上方并显示，同时滚到底部；
收起时仅隐藏浮层（日志内容保留）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `apply_log_view_style(view: QTextEdit) -> None` | 给日志文本域套上"浅底内嵌字段"样式。 |

#### `apply_log_view_style(view: QTextEdit) -> None`

给日志文本域套上"浅底内嵌字段"样式。

样式必须设在控件自身、而不是写进 `style.py` 的全局 QSS：
qfluentwidgets 的 `TextEdit` 在构造时会给控件设置自己的样式表，而控件级
样式表的优先级高于应用级，写在全局 QSS 里的 `#logView` 规则会被它盖掉
（实测底色始终是白的、描边也不生效）。

---

## `desktop.components.pagination`

源码：[`desktop/components/pagination.py`](../../desktop/components/pagination.py)

分页控件：纯计算 Pager + Qt 控件 Pagination。

拆成两层的理由和项目里其它地方一样：**几何/数值计算不要和渲染混在一起**。
``Pager`` 不 import Qt，能直接在自测里当普通对象断言（切片区间、页码钳制、
末页删空后的回退）；``Pagination`` 只负责把 Pager 的状态画出来、把点击翻译
成 ``set_page`` 调用。

页码一律 **1-based**——直接显示在界面上的东西就跟人看到的保持一致，
0-based 只在内部切片时用一次（``_offset``）。

### `class Pager`

分页状态与派生量（不可变，改页码/每页条数就换一个新实例）。

total      总条数（**过滤后**的条数，不是全量）
page_size  每页条数
page       当前页码，1-based；越界会在读取时被钳制

#### 方法

| 方法 | 说明 |
| --- | --- |
| `total_pages() -> int` | 总页数；0 条时也是 1 页（界面上显示「第 1 / 1 页」比「第 1 / 0 页」自然）。 |
| `clamped_page() -> int` | 钳制到 [1, total_pages] 的页码。 |
| `slice_bounds() -> tuple[int, int]` | 当前页在整表里的 [start, end) 下标区间（左闭右开，直接喂 list 切片）。 |
| `page_slice(items: list) -> list` | 取当前页的切片；越界页码已钳制，不会返回空页。 |
| `with_page(page: int) -> 'Pager'` | — |
| `with_page_size(page_size: int) -> 'Pager'` | 换每页条数：页码按比例换算，尽量停在原来看到的那一条附近。 |
| `with_total(total: int) -> 'Pager'` | — |

##### `clamped_page() -> int`

装饰器：`property`

钳制到 [1, total_pages] 的页码。

⚠️ 必须每次读都用这个值：删掉末页最后一条、或搜索后结果变少，
当前页码就会越界，读原始 page 会切出空列表、界面变成空白页。

##### `with_page_size(page_size: int) -> 'Pager'`

换每页条数：页码按比例换算，尽量停在原来看到的那一条附近。

不这么换算的话，从第 3 页（每页 10 条）切到每页 50 条会直接跳到第 3 页
的第 101~150 条，用户感觉列表「乱跳」。换算后落在第 1 页第 21~50 条。

### `class Pagination(QWidget)`

分页条：总数 + 每页条数 + 上/下一页 + 页码。

只做展示与事件转发，**不持有数据**：宿主页面把算好的 Pager 传进来，
用户操作时由本控件算出新页码并通过 ``changed`` 抛回去，宿主再重算并
``set_pager`` 刷新。这样「过滤 → 分页 → 渲染」只有一条数据流向。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(page_size: int=DEFAULT_PAGE_SIZE, parent=None)` | — |
| `pager() -> Pager` | — |
| `set_pager(pager: Pager) -> None` | 用新的分页状态刷新显示（宿主算完过滤/切片后调它）。 |
| `set_visible_for(total: int) -> None` | 总数为 0 时隐藏（配合空状态卡片，避免「共 0 条 第 1/1 页」的噪音）。 |

---

## `desktop.components.panels.base`

源码：[`desktop/components/panels/base.py`](../../desktop/components/panels/base.py)

阶段控制面板基类：标题 + 问号帮助按钮 + 参数表单骨架。

阶段说明（description）不再平铺在标题下方占高度，改由标题右侧的问号按钮
承载：hover 弹 qfluentwidgets 的 ToolTip 气泡，点击弹 Flyout（内容自动换行）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| HELP_TOOLTIP_WIDTH | `26` |
| HELP_BUBBLE_WIDTH | `360` |

### `class StagePanel(QWidget)`

阶段控制面板：标题（含问号帮助按钮）+ 参数表单。子类实现 _build_form/get_args。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 构建面板骨架：标题行 + 参数表单容器。 |
| `mark_params_edited() -> None` | 补一次"用户改了参数"通知——给**按钮**这类不经过控件信号的入口用。 |
| `build_form() -> QWidget` | 参数表单容器：统一装进透明滚动区，窗口过矮时出滚动条而非压扁表单。 |
| `get_args() -> dict` | 从表单收集该阶段参数（不含 input/output/clean）。 |
| `apply_args(parameters: dict) -> None` | 把一次历史执行/暂存的参数回填到表单（多余键忽略）。 |
| `reset_to_default() -> None` | 恢复控件初始默认值。 |

##### `__init__(parent=None)`

构建面板骨架：标题行 + 参数表单容器。

title 来自子类类属性；description 不再平铺占高度，改挂在标题右侧
问号按钮上（hover 出 ToolTip 气泡、点击出 Flyout）。随后调用
build_form 生成子类表单并占满剩余垂直空间，最后统一把表单里输入
控件的信号接到 ``param_edited``（供参数暂存）。

##### `mark_params_edited() -> None`

补一次"用户改了参数"通知——给**按钮**这类不经过控件信号的入口用。

例：「恢复默认」是把默认值 set 回控件（走 ``_apply_args``），信号会被
``_applying`` 挡掉，但用户确实改动了参数，得让宿主把新值暂存下来。

##### `build_form() -> QWidget`

参数表单容器：统一装进透明滚动区，窗口过矮时出滚动条而非压扁表单。

控制卡片把剩余高度分给 QStackedWidget，窗口一矮表单行就被压得错位
（rembg 的复选框会挤进表单行、说明与行间距被吞掉）。滚动区让表单
始终保持自然高度，高度不足时纵向滚动。print 面板自带分区滚动区，
整体覆盖本方法，不受影响。

##### `reset_to_default() -> None`

恢复控件初始默认值。

各子类的 ``_apply_args`` 对缺失键都取自身默认值，因此传空字典
即可复位——用于切换任务时清掉上一个任务残留的手改参数。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `default_for(parameters: dict, defaults: dict, key: str)` | 取回填值：``parameters`` 里有且**不为 None** 时用它，否则回落 ``defaults[key]``。 |

#### `default_for(parameters: dict, defaults: dict, key: str)`

取回填值：``parameters`` 里有且**不为 None** 时用它，否则回落 ``defaults[key]``。

⚠️ 不能写成 ``parameters.get(key, defaults[key])``——历史配置里存着
``{"dpi": null}`` 时，``get`` 会返回 ``None``，兜底**永不生效**，直接
``setValue(None)`` 就崩（这是本仓库反复踩到的 None 默认值陷阱）。
也不能写成 ``parameters.get(key) or ...``——布尔键的合法值 ``False``
与数值键的合法值 ``0`` 会被误判成"没值"而回落到默认。

---

## `desktop.components.panels.detect_panel`

源码：[`desktop/components/panels/detect_panel.py`](../../desktop/components/panels/detect_panel.py)

检测文本框（detect）阶段面板：本阶段只识别坐标，不生成文件。

### `class DetectPanel(StagePanel)`

检测文本框阶段面板：仅识别坐标，不生成文件。

YOLO 检测每张图的内容框坐标（半幅：左右两栏；整幅：整页单一内容区），
供预览标注与去底色/裁剪使用；
本阶段无表单参数，get_args 返回空字典，手动检测经信号触发。

「整页模式」是第三步 area=4 的入口开关：勾选后整页即唯一文本框，
**不加载也不调用 YOLO**，预览里框画在页面边界，仍可手动拖动/重画。

**人工干预**（用户 2026-09-29 定）：框的类型是**框自己的属性**，不随
"还剩几个框"变化——

- 半幅页的左右由**框的中心位置**决定，拖动跨过中线会自动换边；
- 「整幅」由用户在本面板显式选择，选过之后无论怎么移动/缩放都是整幅；
- 整幅与左右半幅互斥，且整幅一页只能有一个框（宿主负责提示与拦截）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 返回空参数字典（detect 阶段无表单参数）。 |
| `set_whole_page(on: bool) -> None` | 外部（第三步 area）回填勾选状态；blockSignals 避免回抛造成循环。 |
| `set_box_selection(index: int, kind: str) -> None` | 回填「选中框类型」控件：``index < 0``（无选中）时三段都不高亮。 |

##### `get_args() -> dict`

返回空参数字典（detect 阶段无表单参数）。

整页模式不在这里上报：area 归第三步 rembg 面板所有，本开关只负责
把 area 切到 4 / 切回 1（见宿主的 _set_whole_page_mode）。

##### `set_box_selection(index: int, kind: str) -> None`

回填「选中框类型」控件：``index < 0``（无选中）时三段都不高亮。

``set_current`` 是程序化切换、**不发** ``current_changed``，因此不会
反过来再触发一次类型切换（否则会自我递归）。

未选中框时三段仍保持可点：点类型即"选中该类型的框"（用户要求 6）。

---

## `desktop.components.panels.extract_panel`

源码：[`desktop/components/panels/extract_panel.py`](../../desktop/components/panels/extract_panel.py)

提取图片阶段面板。

### `class ExtractPanel(StagePanel)`

提取图片阶段面板：设置缩放、目标 DPI、格式与页码范围。

extract 阶段把源 PDF 每页渲染为图片；参数经 get_args 收集后由 runner
写入子进程配置，input/output 由系统接管。默认值统一取
``params_spec.DEFAULTS["extract"]``（控件初值与回填兜底同一份）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 收集提取参数：zoom/dpi/ext/quick/pages（不含 input/output）。 |

##### `get_args() -> dict`

收集提取参数：zoom/dpi/ext/quick/pages（不含 input/output）。

pages 留空表示全部页；非法页码由 runner 在取参时以 ValueError 拦截。
dpi 默认 300，是**整页渲染**的 DPI 下限（内嵌图路径不生效）。

---

## `desktop.components.panels.params_spec`

源码：[`desktop/components/panels/params_spec.py`](../../desktop/components/panels/params_spec.py)

desktop 各阶段面板的**默认参数**集中定义（唯一事实来源）。

面板散着写默认值会漂移：同一个参数在「构建控件初值」「``_apply_args`` 缺省
兜底」「``reset_to_default``」三处各写一遍，改一处漏两处（`page_number_font_size`
就曾出现「兜底 12 / 默认 18」两套值）。这里按阶段收成一张表，各消费方统一取用：

1. ``DEFAULTS[stage]`` —— 面板 ``_apply_args()`` 的缺键兜底与控件初值；
2. ``StagePanel.reset_to_default()`` —— 复位到本表；
3. 表单下拉的「中文显示 ↔ 参数值」候选表也在此登记。

## 与 core.command_spec 的关系

``core/command_spec.py`` 是**命令行**参数的唯一事实来源，本模块是**桌面表单**的
那一份。两者刻意分开：CLI 的 print 默认是「空表单」（不打印标题、pdf_name=None），
而桌面表单打开就该是一份能直接出 PDF 的配置（有书名、有页码）。print 段的差异
由 ``core.command_spec.PRINT_FORM_DEFAULTS`` 显式表达，这里直接引用，不再抄一份。

其余阶段（extract/detect/rembg）桌面与 CLI 语义一致，因此**以 command_spec 的
defaults 为底**，只覆盖表单侧特有的键（如 ``pages`` 表单里是空串而非 None），
见各表的 ``_base`` 调用。这样 CLI 改默认值时桌面自动跟随，不会再出现两份值。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `stage_defaults(stage: str) -> dict` | 取某阶段的默认参数（副本，可安全改写）。 |
| `default_value(stage: str, key: str, fallback=None)` | 取某阶段某键的默认值；未登记时返回 ``fallback``。 |

#### `default_value(stage: str, key: str, fallback=None)`

取某阶段某键的默认值；未登记时返回 ``fallback``。

⚠️ 默认值可能是 ``None``（如 print 的 ``title_margins``），这里**不做**
``or`` 兜底——调用方要区分「默认就是 None」与「没登记」。

---

## `desktop.components.panels.print_form`

源码：[`desktop/components/panels/print_form.py`](../../desktop/components/panels/print_form.py)

生成 PDF（print）阶段的表单构建 Mixin：编排、通用控件工厂、节点表、焦点策略。

本类是**编排层**，按依赖从少到多继承三个专职 Mixin：

* :mod:`desktop.components.panels.print_text_layout` —— 「位置/文字方向」固定取值
* :mod:`desktop.components.panels.print_inset` —— 「距页边」控件组
* :mod:`desktop.components.panels.print_sections` —— 五个分区的控件

参数定义/解析见 print_params.py，面板状态见 print_panel.py。

⚠️ 拆分只改**代码落在哪个文件**，不改任何行为：四个类的成员名对外一律从
``PrintFormMixin`` 可见（``PrintPanel`` 只继承它一个），
``tests/selftests/print_form_split.py`` 钉住这条不变量。

### `class PrintFormMixin(PrintSectionsMixin, PrintTextLayoutMixin)`

print 面板的表单构建（由 PrintPanel 继承）。

MRO：``PrintFormMixin → PrintSectionsMixin → PrintInsetMixin →
PrintTextLayoutMixin``。前三者都只依赖 ``self`` 上的成员，最终由
``PrintPanel(PrintFormMixin, StagePanel)`` 线性化到 ``StagePanel``
提供的 ``_add_row`` 等基础能力。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `build_form() -> QWidget` | 构建 print 面板表单：滚动区 + 各分区控件 + 节点表。 |

##### `build_form() -> QWidget`

构建 print 面板表单：滚动区 + 各分区控件 + 节点表。

用 ScrollArea 承载全部分区（输出/边距/标题/页码/过滤），顶部放恢复
默认配置/放弃修改按钮，构建后连接 pdf_name 与 title 联动信号；焦点策略延后到
面板 __init__ 末尾统一设置。

---

## `desktop.components.panels.print_inset`

源码：[`desktop/components/panels/print_inset.py`](../../desktop/components/panels/print_inset.py)

「距页边」控件组：标题 / 页码两段文字各自的两行输入框。

从 ``print_form.PrintFormMixin`` 拆出。这一段是**完整内聚**的一块：
造控件 → 加行 → 取值 → 回填 → 刷新释义，都只围着 ``block`` 字典转。

* 依赖：`self._add_row`（``base.StagePanel``）、
  `self._title_inset` / `self._page_number_inset`（由 ``print_sections`` 创建）
* 被依赖：``PrintSectionsMixin``（造行）、``PrintPanel``（取值 / 回填）

⚠️ **拆出后仍然靠 `self._xxx` 共享状态**——这是 Mixin 拆分的固有代价，
不要为了"看起来独立"去加构造参数：面板的 MRO 是线性的，共享 self
反而是这里最简单正确的做法。共享点全部登记在
``tests/selftests/print_form_split.py`` 的白名单里。

### `class PrintInsetMixin`

print 面板「距页边」控件组（由 PrintFormMixin 继承）。

---

## `desktop.components.panels.print_nodes`

源码：[`desktop/components/panels/print_nodes.py`](../../desktop/components/panels/print_nodes.py)

标题切换节点列表：不用表格，高度完全由内容撑开。

原来的做法是 QTableWidget：表格必须有表头 + 固定高度，行数超过上限就只能
靠内部滚动条兜住，于是「高度自适应」永远是人工算出来的常量组合，控件高度
随主题/DPI 一变就被压扁或裁掉。

这里换成 QVBoxLayout 逐行堆叠的普通控件：
- 行数增加 → 容器 sizeHint 自然变大，不需要任何高度计算；
- 行数再多也不会出现内部滚动条（外层面板的 ScrollArea 统一滚动）；
- 每行自带删除按钮，不再依赖「选中行」这种表格语义；
- 行内控件的真实高度就是行高，不存在被行高挤压的可能。

### 模块常量

| 名称 | 值 |
| --- | --- |
| PAGE_MIN | `1` |
| PAGE_MAX | `100000` |
| _SPIN_W | `120` |
| _SIDE_W | `76` |
| _DEL_W | `30` |
| _GAP | `6` |

### `class NodeRow(QWidget)`

一个标题切换节点：触发页码 + 标题 + 侧别 + 删除按钮。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(page: int=1, title: str='', side: str='left', parent=None)` | 构造一个标题切换节点行：页码 + 标题 + 侧别 + 删除按钮。 |
| `value() -> list \| None` | 收集本行配置；标题为空返回 None（该行忽略）。 |

##### `__init__(page: int=1, title: str='', side: str='left', parent=None)`

构造一个标题切换节点行：页码 + 标题 + 侧别 + 删除按钮。

用 QHBoxLayout 横向排布，各行自带删除按钮；removeRequested 在点击
删除时带上本行自身，标题空行在收集时被忽略。

### `class NodeListWidget(QWidget)`

节点行容器：行数决定高度，无表头、无内部滚动条。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 构造节点容器：QVBoxLayout 逐行堆叠，默认显示空态提示。 |
| `count() -> int` | 返回当前节点行数量。 |
| `rows() -> list[NodeRow]` | 返回节点行副本（防止外部直接改内部列表）。 |
| `collect() -> list` | 按行序收集节点配置，空标题行忽略。 |
| `add_row(page: int=1, title: str='', side: str='left') -> NodeRow` | 新增一行节点并刷新空态与高度；插入后发出 changed。 |
| `remove_row(row: NodeRow) -> None` | 移除指定行：解绑布局、删除对象并刷新空态与高度。 |
| `clear() -> None` | 清空所有节点行。 |

##### `add_row(page: int=1, title: str='', side: str='left') -> NodeRow`

新增一行节点并刷新空态与高度；插入后发出 changed。

行写入 QVBoxLayout 使容器高度随行数自适应；新行显式 show 并通知父级
重算几何（已显示时布局会跳过隐藏项），空态提示在首行出现时隐藏。

##### `remove_row(row: NodeRow) -> None`

移除指定行：解绑布局、删除对象并刷新空态与高度。

行不在列表中则忽略；移除后重新显示空态提示（无行时）并通知父级重算
几何，最后发出 changed 让面板同步配置。

---

## `desktop.components.panels.print_panel`

源码：[`desktop/components/panels/print_panel.py`](../../desktop/components/panels/print_panel.py)

生成 PDF（print）阶段面板：表单状态（取值/回填/重置）。

表单控件构建见 print_form.py，参数解析见 print_params.py，
默认值统一取 params_spec.DEFAULTS["print"]。
input/output/workers/clean 由系统管理，不出现在表单中。

### `class PrintPanel(PrintFormMixin, StagePanel)`

生成 PDF 阶段面板：纸张/边距/标题/页码等参数与状态。

input/output/workers/clean 由系统管理；表单构建见 print_form，取值/
回填/重置等状态见本类（含标题切换节点与 pdf_name/title 联动）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 构建 print 面板：设滚动拉伸、联动标志并复位到默认。 |
| `set_source_defaults(source_stem: str) -> None` | 切换任务时调用：以源 PDF 名派生默认值并重置表单。 |
| `set_upstream_border(border) -> None` | 写入上游（第三步 rembg/crop）border，并刷新通用边距默认值显示。 |
| `reset_to_default() -> None` | 恢复为该面板的内置默认参数（不依赖任何历史执行）。 |
| `reset_edits() -> None` | 撤销本次修改：恢复到最近一次执行的参数。 |
| `mark_applied(parameters: dict) -> None` | 记录最近一次执行使用的参数（供「放弃本次修改」恢复）。 |
| `set_inset(which: str, values) -> None` | 程序化设置某段文字的「距页边」（which=title / page_number）。 |
| `inset(which: str) -> list \| None` | 读当前「距页边」：``[上,右,下,左]``；未勾选"自定义"时是 None。 |
| `get_args() -> dict` | 收集 PDF 生成参数（校验颜色/边距，缺省回落内置默认）。 |

##### `__init__(parent=None)`

构建 print 面板：设滚动拉伸、联动标志并复位到默认。

基类 __init__ 构建滚动表单后，这里开启标题/说明换行、初始化
pdf_name 联动标志、记录最近应用参数占位，并调 reset_to_default 复位。

##### `set_source_defaults(source_stem: str) -> None`

切换任务时调用：以源 PDF 名派生默认值并重置表单。

- PDF 文件名：xxx.pdf → xxx[重制].pdf
- 古籍名称（标题文本）：xxx
有历史执行记录时，进入第四步仍会回填最近一次配置，覆盖此默认值。

##### `set_upstream_border(border) -> None`

写入上游（第三步 rembg/crop）border，并刷新通用边距默认值显示。

仅当用户尚未手动改过通用边距时，才把表单里的边距默认值同步为级联
结果（上游非 0 → 0，否则 20），让用户「看见」默认值已变化；
用户一旦手动改过，上游 border 变化不再覆盖其选择。

##### `reset_edits() -> None`

撤销本次修改：恢复到最近一次执行的参数。

与 reset_to_default（恢复内置默认）不同，本方法回到 mark_applied
记录的上一轮执行参数；若从未执行过则退化为恢复默认。

##### `set_inset(which: str, values) -> None`

程序化设置某段文字的「距页边」（which=title / page_number）。

values = [上,右,下,左]（mm）表示启用并填值；None 表示不启用（老行为）。

##### `get_args() -> dict`

收集 PDF 生成参数（校验颜色/边距，缺省回落内置默认）。

input/output/workers/clean 不在此列；颜色或边距非法会抛 ValueError
阻止执行；title_switch_nodes 取节点行、skip_pages 解析为文件名列表。

---

## `desktop.components.panels.print_params`

源码：[`desktop/components/panels/print_params.py`](../../desktop/components/panels/print_params.py)

生成 PDF（print）阶段的参数解析/序列化纯函数。

⚠️ 默认值（``DEFAULT_PARAMS``）与下拉候选表的**唯一事实来源**已上移到
``panels/params_spec.py``（各阶段共用一张表，避免同一参数在「控件初值 /
``_apply_args`` 兜底 / ``reset_to_default``」三处各写一遍而漂移）。本模块只保留
print 专用的解析/序列化纯函数，并把 ``DEFAULT_PARAMS`` 重新导出以兼容既有导入。

表单 UI 见 print_form.py，面板状态见 print_panel.py。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `parse_color(text: str) -> QColor` | 解析 'r,g,b'（0~255）颜色字符串，非法时抛出 ValueError。 |
| `parse_margin4(text: str)` | 解析边距简写：1/2/3/4 值（CSS 简写）→ [上,右,下,左]；空→None。 |
| `margin_to_text(value) -> str` | 边距列表转简写文本：四边相等→单值；上下/左右相等→两值；否则四值。 |
| `skip_pages_to_text(value) -> str` | skip_pages 参数 → 表单文本（逗号分隔的页名）。 |
| `text_to_skip_pages(text: str) -> list[str]` | 表单文本 → skip_pages 参数。 |

#### `parse_margin4(text: str)`

解析边距简写：1/2/3/4 值（CSS 简写）→ [上,右,下,左]；空→None。

⚠️ 必须与 CLI 的 ``normalize_margin``（utils.margin_utils）同口径
（2026-09-26 审计 #13）：三值「上,左右,下」是合法写法（spec 的
title_margins 报错文案也明说 1/2/3/4），原先这里拒绝三值、同样的值
写进 guji.yaml 却能跑——GUI 比命令行更严，没有道理。

---

## `desktop.components.panels.print_sections`

源码：[`desktop/components/panels/print_sections.py`](../../desktop/components/panels/print_sections.py)

print 表单的五个分区（输出与纸张 / 页边距 / 标题 / 页码 / 过滤）。

从 ``print_form.PrintFormMixin`` 拆出。每个 ``_build_xxx_section`` 只负责
"往 root 里加一节的控件并把控件挂到 self 上"，**取值与回填不在这里**
（见 print_panel）。

* 依赖（均来自 ``PrintFormMixin`` / ``PrintPanel``）：
  ``_section`` ``_add_row`` ``_line_edit`` ``_make_combo`` ``_spin_with_unit``
  ``_color_row`` ``_add_node_row`` ``_clear_node_rows`` ``_sync_enabled``
* 被依赖：``PrintFormMixin.build_form`` 依次调用本模块的五个 builder

⚠️ 控件在**本模块**创建、却在 ``PrintPanel`` 里读写（``get_args`` /
``_apply_args`` / ``_connect_preview_signals``）——这条跨模块的隐式契约由
``tests/selftests/print_form_split.py`` 钉住：新增分区必须同时登记它挂到
self 上的控件名，否则漏挂没人会发现。

### `class PrintSectionsMixin(PrintInsetMixin)`

print 面板的分区构建（由 PrintFormMixin 继承）。

继承 ``PrintInsetMixin`` 是因为标题节/页码节都要调 ``_make_inset`` /
``_add_inset_rows``；MRO 上它排在 ``PrintFormMixin`` 之后，通用工具
（``_section`` 等）由最终类 ``PrintPanel`` 的线性化解析到，无需再继承。

---

## `desktop.components.panels.print_text_layout`

源码：[`desktop/components/panels/print_text_layout.py`](../../desktop/components/panels/print_text_layout.py)

「位置 / 文字方向」的固定取值：桌面端不给选，但历史参数要原样回显。

从 ``print_form.PrintFormMixin`` 拆出。这一段**不碰任何控件**，只回答
"这段文字的位置 / 方向该导出成什么"，是全类里依赖最少的一块：

* 依赖：`self._fixed_layout_echo`（由 ``PrintPanel.__init__`` 初始化）
* 被依赖：``PrintFormMixin``（从而 ``PrintPanel``）；``print_panel.get_args``
  经 ``_fixed_layout`` 取值，但不 import 本模块

拆出来的理由：它是**纯取值规则**（界面删了控件、参数键还在），和控件构建
没有任何共同点；留在表单 Mixin 里只会让人以为"改界面会改到它"。

### `class PrintTextLayoutMixin`

print 面板「位置」「文字方向」的固定取值（由 PrintFormMixin 继承）。

---

## `desktop.components.panels.rembg_panel`

源码：[`desktop/components/panels/rembg_panel.py`](../../desktop/components/panels/rembg_panel.py)

图片去底色（rembg）阶段面板：area 决定裁剪方式，border 决定四周留白。

### `class RembgPanel(StagePanel)`

图片去底色阶段面板：area/border/印章等参数。

整图 Otsu 二值化/灰度化去底（可保留印章）；area 决定裁剪方式、
border 决定四周留白，参数经 get_args 收集后传给子进程。默认值统一取
``params_spec.DEFAULTS["rembg"]``。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 收集去底色参数：area/type/offset/seal/border 等。 |

##### `get_args() -> dict`

收集去底色参数：area/type/offset/seal/border 等。

border 留空时按 area 取默认（area=1/2/3 → 0、area=4 → 不设），
由 runner 在续跑时与 detect 框坐标实时合成裁剪区域。

---

## `desktop.components.step_bar`

源码：[`desktop/components/step_bar.py`](../../desktop/components/step_bar.py)

详情页顶部步骤条：编号/对勾徽标 + 连接箭头 + 主副标题。

设计要点：
- 每一步 = 圆形徽标（编号或 ✓）+ 标题 + 状态副标题，用形状表达"第几步"；
- 步骤之间用带箭头的连接线连起来，已完成的线段变色，直观表达先后顺序；
- 状态色：未执行（灰）· 执行中（蓝）· 成功（绿）· 失败（红）· 已中断（橙）；
- 整步可点击切换，带悬停底色，避免按钮样式的标签堆叠感。

对外接口（兼容旧调用）：
- ``buttons``：StepItem 列表（长度 = 步骤数）；
- ``_completed``：已完成步骤下标集合；
- ``set_steps`` / ``set_current`` / ``mark_completed`` / ``current_changed``。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _BADGE | `26` |
| _CONNECTOR_W | `38` |

### `class StepItem(QFrame)`

单个步骤：徽标 + 标题 + 状态副标题，整块可点击。

外层只负责在步骤条里占位（等宽拉伸，保证徽标横向均匀），
真正的底色/悬停胶囊是内层 ``#stepPill``——它贴合内容宽度，
避免当前步骤的高亮底色被拉成一整格的"按钮"。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(index: int, title: str, parent=None)` | 初始化单个步骤项：徽标 + 标题 + 副标题，整块可点击。 |
| `set_title(title: str) -> None` | 只替换标题文案，不改动状态与徽标。 |
| `set_status(status: str, detail: str='', badge_status: str='') -> None` | status 决定副标题/标题色，badge_status 决定徽标（缺省同 status）。 |
| `set_current(current: bool) -> None` | 设置是否为当前步骤，切换高亮底色与标题字重。 |
| `paintEvent(_event) -> None` | 自己画胶囊底色：样式表一旦出现在子树里，Qt 会把 QFrame 底色填白 |
| `enterEvent(event) -> None` | Qt 事件覆写：鼠标移入时进入高亮态。 |
| `leaveEvent(event) -> None` | Qt 事件覆写：鼠标移出时恢复常态。 |
| `mouseReleaseEvent(event) -> None` | Qt 事件覆写：松开（提交本次编辑）。 |

##### `__init__(index: int, title: str, parent=None)`

初始化单个步骤项：徽标 + 标题 + 副标题，整块可点击。

index 为步骤下标（从 0）；pill 为真身胶囊，底色由 paintEvent 自绘
（不用样式表），current 高亮由 _apply_style 控制。

##### `set_status(status: str, detail: str='', badge_status: str='') -> None`

status 决定副标题/标题色，badge_status 决定徽标（缺省同 status）。

两者分开是为了表达"这一步有产出，但最近一次重试失败"：
徽标仍是对勾，副标题用失败色写明最近一次的结果。

##### `paintEvent(_event) -> None`

自己画胶囊底色：样式表一旦出现在子树里，Qt 会把 QFrame 底色填白
（盖住步骤条的卡片底色），所以这里不用样式表。

### `class StepBar(QWidget)`

横向步骤条：4 个步骤按顺序排列，当前步骤高亮、已完成步骤打勾。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(steps, parent=None)` | 按给定步骤标题逐项构建；steps 允许传生成器。 |
| `paintEvent(_event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |
| `set_current(index: int) -> None` | 设置当前步骤下标并同步各步骤高亮与徽标。 |
| `mark_completed(index: int) -> None` | 标记某步骤已完成（徽标改为对勾，连接线着色）。 |
| `set_steps(texts) -> None` | 兼容旧调用：只更新标题文本。 |
| `set_step_status(index: int, status: str, progress: tuple \| None=None, completed: bool \| None=None) -> None` | 设置某步骤状态；progress 为 (已完成, 总数) 时拼出 "成功 · 84/84"。 |
| `reset_statuses() -> None` | 全部步骤恢复为未执行，并清空已完成标记。 |

##### `set_step_status(index: int, status: str, progress: tuple | None=None, completed: bool | None=None) -> None`

设置某步骤状态；progress 为 (已完成, 总数) 时拼出 "成功 · 84/84"。

completed=False 但 status='success' 不可能出现；completed=True 而
status 为失败/中断时，徽标保持对勾、副标题仍显示最近一次的结果。

---

## `desktop.components.task_table`

源码：[`desktop/components/task_table.py`](../../desktop/components/task_table.py)

任务列表表格组件：每行带阶段状态胶囊与 详情/删除 操作按钮。
「子任务状态」原来是一整串 ``提取图片:成功  检测文本框:成功 …`` 纯文本，
列宽一紧就被截断、颜色上也没法区分成败。现在改为 4 个状态胶囊
（提取 / 检测 / 去底 / PDF），颜色来自统一的语义色，鼠标悬停能看到
完整阶段名与进度。

### 模块常量

| 名称 | 值 |
| --- | --- |
| ROW_HEIGHT | `56` |

### `class NameLabel(QLabel)`

任务名标签：按可用宽度自动省略中间部分。

``QTableWidgetItem`` 会自己省略，换成 QLabel 后得自己来——否则长名字
把拉伸列越撑越宽、表格被挤出横向滚动条。
⚠️ 省略时机放在 ``resizeEvent`` 而不是建表时：那时表格还没布局、
``columnWidth()`` 只有几十像素，会把名字截成空串（已踩，表现为「名称列空白」）。
宽度不足 ``_MIN_ELIDE_WIDTH`` 时一律显示全名，等真实宽度来了再收。

下划线改为 ``paintEvent`` 自绘：字体原生下划线紧贴字形底部，间距不可调；
自绘后用 ``_UNDERLINE_GAP`` 控制【基线】到下划线的留白，线宽 1px，颜色跟随
``linkColor``（hover 切换时同步更新）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(text: str, parent=None)` | 记下完整名字，先按全名显示，等布局给出真实宽度再省略。 |
| `setLinkColor(color: QColor) -> None` | 同步文字颜色与下划线颜色。 |
| `linkColor() -> QColor` | — |
| `full_text() -> str` | 完整任务名（省略后的 ``text()`` 可能带 …）。 |
| `resizeEvent(event)` | 宽度变化时重算省略；宽度还没定（未布局）就保持全名。 |
| `paintEvent(event)` | 先让父类画文字，再在文字下方自绘一条同色下划线。 |

##### `setLinkColor(color: QColor) -> None`

同步文字颜色与下划线颜色。

不再依赖 stylesheet 里的 ``color:``（paintEvent 解析不了），
统一走这个方法——hover 进入/离开都调它。

##### `paintEvent(event)`

先让父类画文字，再在文字下方自绘一条同色下划线。
✅ 使用字体基线计算位置，不再依赖boundingRect，gap修改生效。
下划线只覆盖**实际文字宽度**（不铺满整个 label），和网页 <a> 行为一致；

### `class StageChips(QWidget)`

一行 4 个阶段状态胶囊。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(stages: list[dict], parent=None)` | 按 stages 逐项生成状态胶囊；每项需含 short/status/tip。 |

### `class TaskTable(QWidget)`

任务列表表格：每行带阶段状态胶囊与 详情/删除 操作。

列固定为 序号 / 任务名 / 创建时间 / 子任务状态 / 操作；源文件路径
不成列，仅作为任务名 tooltip。open_detail / delete_request 信号
分别携带任务 id。

「序号」列 = **任务编号**（``0001``、``0002``…，即 ``task["id"]`` 与
任务目录名），不是行号——排序/搜索/翻页都不改变它。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 初始化表格：5 列布局、行高与表头对齐。 |
| `set_data(rows: list[dict]) -> None` | rows: [{id, name, source_path, created_at, stages}] |
| `select_task(task_id: str) -> bool` | 选中并滚动到指定任务所在行，返回是否找到。 |

##### `__init__(parent=None)`

初始化表格：5 列布局、行高与表头对齐。

表头对齐跟随各列内容（序号/时间居中、名称/状态左对齐，均垂直居中）；
任务名称列自适应拉伸（占主要宽度），其余列按 _COLUMN_WIDTHS 固定宽度。

##### `set_data(rows: list[dict]) -> None`

rows: [{id, name, source_path, created_at, stages}]

stages 为 ``[{"short": "提取", "status": "success", "tip": "..."}]``；
source_path 不单独成列，仅作任务名的悬浮提示。

⚠️ 「序号」列显示的是**任务自己的编号**（``task["id"]``，如 ``0001``），
不是行号/页内序号：任务号是任务目录名、也是索引里的主键，与排序、
搜索、分页都无关，用户拿它去 ``tasks/0001`` 就能对上号。
（早先用「页内行号 + 全局偏移」，翻页/搜索后同一条任务的号会变，
用户按号找目录会对不上。）

---

## `desktop.components.viewers.image_view`

源码：[`desktop/components/viewers/image_view.py`](../../desktop/components/viewers/image_view.py)

大图查看控件：随控件尺寸缩放，支持叠加切割框。

坐标基准是图片原始像素坐标（_image_size），与预览显示缩放无关。

开启 boxes_editable 后：
- 点击框选中（四角出现缩放手柄），拖动框内移动整框，拖手柄缩放；
- 在空白处按下并拖动可手绘一个新框；
- Delete/Backspace 删除选中框；
- 每次修改结束通过 boxes_edited 发出全部框（仅内存与信号，不落盘）。

reference_boxes 为参考框（如按 area/border 规则推导的最终裁剪大框），
橙色虚线显示，不参与编辑。

### 模块常量

| 名称 | 值 |
| --- | --- |
| HANDLE_RADIUS | `5` |

### `class ImageView(QLabel)`

大图查看：随控件尺寸实时缩放，支持在图片坐标系叠加切割框。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(placeholder: str='无预览', parent=None)` | 初始化画布与框编辑状态；placeholder 为空图时的占位文案。 |
| `has_image() -> bool` | 当前是否已装入图片。 |
| `full_mode() -> bool` | 本页是否为整幅(fullcontent)——整幅页只有「整幅」一种框类型。 |
| `max_boxes() -> int` | 本页允许的框数上限：整幅 1 个；半幅左右各一，共 2 个。 |
| `selected_index() -> int` | 当前选中的框下标；无选中为 -1。 |
| `select_box(index: int) -> None` | 程序化选中第 index 个框（-1 = 取消选中）并重绘。 |
| `box_kinds() -> list` | 当前每个框的类型：``"left"`` / ``"right"`` / ``"full"``。 |
| `preview_edge() -> int` | 当前控件需要多高的预览分辨率（**最长边**像素数）。 |
| `set_boxes_editable(editable: bool) -> None` | 开关框编辑；开启时接受点击焦点以响应键盘删除。 |
| `set_reference_boxes(boxes: list) -> None` | 设置参考框（橙色虚线，不参与编辑）并重绘。 |
| `set_image(image, boxes=None, image_size: QSize \| None=None) -> None` | 装入图片并重置编辑状态。 |
| `set_boxes(boxes: list, image_size: QSize, full: bool=False, selected: int \| None=None) -> None` | 仅更新切割框、形态与图片原始尺寸并重绘（不换图）。 |
| `clear_image(text: str='无预览') -> None` | 清空图片与全部框（含参考框），显示占位文案。 |
| `resizeEvent(event) -> None` | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。 |
| `event(event) -> bool` | 跨显示器拖动（dpr 变化）时按新 dpr 重画。 |
| `mousePressEvent(event) -> None` | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。 |
| `mouseMoveEvent(event) -> None` | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。 |
| `mouseReleaseEvent(event) -> None` | Qt 事件覆写：松开（提交本次编辑）。 |
| `mouseDoubleClickEvent(event) -> None` | 双击 → ``double_clicked``（宿主打开图片预览弹窗）。 |
| `keyPressEvent(event) -> None` | Qt 事件覆写：键盘操作（如 Delete 删除选中项）。 |

##### `box_kinds() -> list`

当前每个框的类型：``"left"`` / ``"right"`` / ``"full"``。

与 :meth:`_draw_boxes` 用的是**同一份规则**（整幅页恒为 full；半幅页按
中心位置判左右），所以面板高亮与实际画出的标签永远一致。

##### `preview_edge() -> int`

当前控件需要多高的预览分辨率（**最长边**像素数）。

按控件的**物理**像素算（逻辑尺寸 × dpr），取宽高较大者：图片按等比
缩放适配控件，长边必定落在控件的长边上，所以按较大边给就够。

交给 ``PreviewWorker(longest_edge=...)`` 用。⚠️ 早先四处调用点都写死
1600：高分屏（150%~200%）或大窗口下屏幕需要的像素比 1600 还多，
源图只能被放大 → 糊。实测（.workbuddy/perf/2026-09-24-preview-sharpness.md）
把密度拉满后 RMSE 再降 30~50%、锐度再涨 1.4~1.7 倍，代价是每页多 25~160ms。

##### `set_image(image, boxes=None, image_size: QSize | None=None) -> None`

装入图片并重置编辑状态。

image 为 QImage；image_size 非空时作为框坐标的坐标系基准（大图可能被
降采样显示，坐标必须按原始尺寸算）。

##### `set_boxes(boxes: list, image_size: QSize, full: bool=False, selected: int | None=None) -> None`

仅更新切割框、形态与图片原始尺寸并重绘（不换图）。

boxes 为图片像素坐标；image_size 为坐标映射基准，与显示缩放无关。
``full=True`` 表示本页是整幅(fullcontent)：框显示为「整幅」且**只允许
一个**；否则是半幅页，框按中心位置显示为左/右，最多两个。
``selected`` 非负时把选中态落到该下标（宿主切换框类型后保持选中）。

⚠️ 名称/颜色不在这里传：它们由 `box_styles` 按**中心位置**每帧现算，
这样拖动框跨过中线时名字与颜色会立刻跟着换（用户 2026-09-29 要求）。

##### `event(event) -> bool`

跨显示器拖动（dpr 变化）时按新 dpr 重画。

Qt 在窗口 dpr 变化时发 ``DevicePixelRatioChange``，**不保证**同时发
``resizeEvent``。不接这个事件的话，把窗口从 100% 屏拖到 200% 屏，
图会一直停在按旧 dpr 出的那版（明显发糊），要等下次换页才恢复。

##### `mouseDoubleClickEvent(event) -> None`

双击 → ``double_clicked``（宿主打开图片预览弹窗）。

⚠️ 必须把本次按下可能已经开始的"手绘新框"清干净：双击的第一下会先落到
``mousePressEvent`` 的"空白处 → 手绘"分支，不清就会在图上留一个跟着
鼠标跑的橡皮筋残影，而且第二下松开还会真的落一个框。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `box_styles(boxes, image_size=None, full: bool=False)` | 框列表 → ``(names, colors)``，与 ``boxes``（去掉空项后）等长。 |
| `box_names(boxes, image_size=None, full: bool=False) -> list` | 框名称列表（大图信息条文案用）——与 :func:`box_styles` 同一份规则。 |

#### `box_styles(boxes, image_size=None, full: bool=False)`

框列表 → ``(names, colors)``，与 ``boxes``（去掉空项后）等长。

- ``full=True``（整幅页 / fullcontent）：每个框都是「整幅」+ 靛蓝——
  整幅是**显式类型**，无论怎么移动、缩放都不变；
- 否则是半幅页：按**中心位置**判左右（`utils.box_geometry.half_sides`，
  规则只有那一处实现），所以把框拖过中线时名字与颜色会跟着换。

⚠️ 这里以前按"框的序号/个数"命名（1 个框→「整幅」、2 个→「左/右」），于是
删掉一个框会让剩下的框"变身"（用户 2026-09-29 报）。现在类型只由
「是否整幅页」与「框的中心位置」决定，**与有几个框无关**。

---

## `desktop.components.viewers.image_viewer`

源码：[`desktop/components/viewers/image_viewer.py`](../../desktop/components/viewers/image_viewer.py)

图片查看器：缩略图条 + 大图，支持切割框叠加与页面增删按钮。

### `class ImageViewerWidget(QWidget, ThumbsMixin, ZoomPopupMixin)`

图片查看器：缩略图条 + 大图，支持切割框叠加、拖动与页面增删按钮。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(editable: bool=False, show_boxes: bool=False, empty_hint: str='暂无图片', image_size_provider=None, thumb_provider=None, parent=None)` | 构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。 |
| `paths() -> list[Path]` | 当前页面清单（按显示顺序）。 |
| `current_path() -> Path \| None` | 当前选中的页面路径；无选中或无清单时为 None。 |
| `navigate(forward: bool) -> None` | 方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。 |
| `set_images(paths: list[Path], boxes_map: dict \| None=None) -> None` | 设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。 |
| `apply_boxes(boxes: list[tuple], image_size: QSize, info_text: str='', full: bool=False, selected: int=-1) -> None` | 在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。 |
| `set_reference_boxes(boxes: list) -> None` | 设置参考框（最终裁剪大框，虚线显示，不参与编辑）。 |
| `select_box(index: int) -> None` | 程序化选中第 index 个框（-1 = 取消选中）。 |
| `selected_index() -> int` | 当前选中的框下标；无选中为 -1。 |
| `box_full_mode() -> bool` | 本页是否为整幅(fullcontent)。 |
| `box_kinds() -> list` | 当前每个框的类型（"left"/"right"/"full"）。 |

##### `__init__(editable: bool=False, show_boxes: bool=False, empty_hint: str='暂无图片', image_size_provider=None, thumb_provider=None, parent=None)`

构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。

image_size_provider 供大图降采样时还原原始像素尺寸；thumb_provider
让缩略图条改用预生成小图，避免反复解码原图。

##### `set_images(paths: list[Path], boxes_map: dict | None=None) -> None`

设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。

paths 为 Path 列表；boxes_map 预留（当前未用）。清单不变时跳过
重建，但仍 emit current_changed 让宿主重新读取该页检测框/参数。

##### `apply_boxes(boxes: list[tuple], image_size: QSize, info_text: str='', full: bool=False, selected: int=-1) -> None`

在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。

``full=True`` 表示本页是整幅(fullcontent)：框显示为「整幅」且只允许一个；
否则按框的**中心位置**显示为左/右框。名称/颜色由控件每帧现算，不用传。
``selected`` 为要选中的框下标（-1 = 不选），用于切换类型后保持选中。

---

## `desktop.components.viewers.image_zoom_dialog`

源码：[`desktop/components/viewers/image_zoom_dialog.py`](../../desktop/components/viewers/image_zoom_dialog.py)

图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。

为什么不把缩放直接做在 ``ImageView`` 上：那是**框编辑**画布——点击选中、
拖拽移动整框、四角缩放、空白拖拽手绘。再叠一层"滚轮缩放 + 拖拽平移"，
两种拖拽立刻打架（拖框 vs 拖画布），而框坐标是 detect/rembg 的实际输出依据，
误操作代价高。所以编辑仍留在原处（固定"适应窗口"），弹窗只做**只读**查看。

渲染密度由弹窗自己算（``_render_edge``：视口物理长边 × ``RENDER_HEADROOM``，
再受宿主给的 ``ZoomTarget.cap`` 与 :data:`MAX_RENDER_EDGE` 约束），宿主只提供
``render(edge) -> worker``。这样「图片按最长边解码」「PDF 按该边长渲染」
「打印效果按该边长反推 px/mm 重新排版」三种口径各归各家，弹窗不必区分。

⚠️ 缩放倍率的语义：**1.0 = 100% = 1 图片像素对 1 设备像素**（QGraphicsView 的
变换比例 = 倍率 ÷ dpr）。所以场景里的 pixmap 刻意**不设** devicePixelRatio
（1 场景单位 = 1 图片像素），否则这套换算会再叠一个 dpr。

### 模块常量

| 名称 | 值 |
| --- | --- |
| WHEEL_STEP | `1.15` |
| RENDER_HEADROOM | `1.5` |
| MIN_RENDER_EDGE | `1600` |
| MAX_RENDER_EDGE | `4000` |
| JPEG_QUALITY | `90` |
| PAN_MARGIN_RATIO | `0.25` |

### `class ZoomTarget`

弹窗某一页的数据来源（宿主在**主线程**里按页现造）。

``render`` 会在 **worker 线程**被调用，所以它只能读构造时快照下来的值
（路径、参数字典……），**不得**碰任何 QWidget——同 ``worker_thread_affinity``
的约束。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(render, note: str='', stem: str='', count: int=1, original=None, cap: int \| None=None)` | render: ``(edge:int) -> worker``；cap: 渲染密度上限（如原图原生边长）。 |

### `class ZoomableCanvas(QGraphicsView)`

缩放画布：滚轮以光标为锚点缩放、左键拖拽平移、双击切换适应/100%。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 初始化场景、拖拽平移与锚点缩放（锚点由 QGraphicsView 原生支持）。 |
| `has_image() -> bool` | 当前是否已装入图片。 |
| `zoom() -> float` | 当前缩放倍率（1.0 = 100% = 1 图片像素对 1 设备像素）。 |
| `set_image(image: QImage \| None) -> None` | 装入图片并复位（适应窗口、清空翻转旋转）。 |
| `clear() -> None` | 卸载图片（关窗时释放大图内存）。 |
| `fit() -> None` | 适应窗口：整图完整可见（保持宽高比）。 |
| `set_zoom(zoom: float, anchor_pos: QPointF \| None=None) -> None` | 设置缩放倍率。 |
| `zoom_in() -> None` | 放大到下一档。 |
| `zoom_out() -> None` | 缩小到上一档。 |
| `image_rect() -> QRectF` | 图片在**场景坐标**里的实际占位（1 场景单位 = 1 图片像素）。 |
| `rotate_clockwise() -> None` | 顺时针旋转 90°。 |
| `rotate_counterclockwise() -> None` | 逆时针旋转 90°。 |
| `flip_horizontal() -> None` | 水平翻转（左右镜像）。 |
| `flip_vertical() -> None` | 垂直翻转（上下镜像）。 |
| `keyPressEvent(event) -> None` | ←/→ 翻页（工具条 tooltip 承诺过的快捷键，此前一直没实现）。 |
| `wheelEvent(event) -> None` | 滚轮缩放：以**光标下的那一点**为锚点（自己算，见 set_zoom）。 |
| `mouseDoubleClickEvent(event) -> None` | 双击在「100%」与「适应窗口」之间切换。 |
| `resizeEvent(event) -> None` | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。 |
| `export_image() -> QImage \| None` | 导出用图：已应用翻转/旋转的**整分辨率**图（缩放的屏幕比例不参与）。 |

##### `set_zoom(zoom: float, anchor_pos: QPointF | None=None) -> None`

设置缩放倍率。

``anchor_pos`` 是**视口坐标**下的不动点（滚轮传光标位置）；不传则以
视口中心为不动点。

⚠️ 刻意**不用** Qt 的 ``AnchorUnderMouse``：它依赖私有的
``lastMouseEventPosition``，弹窗刚打开就滚轮时那个值可能是陈旧的
（实测会退化成左上角），缩放会突然跳到一边。这里自己按"锚点处的场景
点在缩放前后保持不动"来算，结果只取决于传入的位置，既可预期也可测。

##### `image_rect() -> QRectF`

图片在**场景坐标**里的实际占位（1 场景单位 = 1 图片像素）。

⚠️ 与 ``sceneRect()`` 区分：场景矩形为了"没缩放也能拖"会被**居中扩展**
到至少视口那么大（见 :meth:`_sync_scene_rect`），所以几何/朝向判断一律
用本方法，只有滚动范围与 fitInView 的留白才看 ``sceneRect()``。

##### `keyPressEvent(event) -> None`

←/→ 翻页（工具条 tooltip 承诺过的快捷键，此前一直没实现）。

⚠️ 主动 ignore 掉：QGraphicsView 默认用方向键**滚动视图**，焦点落在
画布上时事件到不了对话框，翻页就死了；这里显式放行给父级。

### `class ImageZoomDialog(QDialog, WorkerHost)`

图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None, factory=None, max_edge: int=MAX_RENDER_EDGE)` | ``factory(index) -> ZoomTarget \| None``，在**主线程**里现造该页来源。 |
| `show_for(factory=None, index: int=0) -> None` | 打开/翻到某一页。``factory(index) -> ZoomTarget \| None``（主线程现造）。 |
| `mouseDoubleClickEvent(event) -> None` | 双击**顶部工具栏**空白 → 全屏/还原。 |
| `eventFilter(obj, event) -> bool` | 点「百分比」标签 → 回 100%（标签兼做缩放复位的入口）。 |
| `keyPressEvent(event) -> None` | 快捷键：←/→ 翻页、+/- 缩放、0 适应窗口、1 原始比例、R 旋转。 |
| `closeEvent(event) -> None` | 关窗即作废在飞的渲染并释放大图（一张 4000px 预览约 45MB）。 |

##### `mouseDoubleClickEvent(event) -> None`

双击**顶部工具栏**空白 → 全屏/还原。

⚠️ 系统标题栏的双击（最大化/还原）由 windowFlags 提供的 min/max
按钮接管；这里只管我们自己的工具栏行（用户 17:07 报「双击顶部栏
也可以全屏」「双击顶部栏，不是单击」）。画布的双击是 100%↔适应，
语义不同，互不干扰。

##### `keyPressEvent(event) -> None`

快捷键：←/→ 翻页、+/- 缩放、0 适应窗口、1 原始比例、R 旋转。

Esc 交给 QDialog 自己处理（关窗）。

### `class ZoomPopupMixin`

宿主侧混入：双击大图打开图片预览弹窗。

子类需要实现 :meth:`_zoom_target` 与 :meth:`_zoom_index`，并在
``__init__`` 里调 :meth:`_init_zoom_popup`。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `close_zoom_popup() -> None` | 内容被换掉时关掉弹窗（弹窗里那页是打开时的快照，留着就是旧数据）。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `display_transform(rotation: int=0, flip_h: bool=False, flip_v: bool=False) -> QTransform` | 翻转/旋转的变换矩阵——**屏幕与导出必须共用这一个**。 |
| `mirrored_rotate_icon() -> QIcon` | ``FIF.ROTATE`` 的水平镜像 = **逆时针（左旋）**。 |
| `flip_icon(horizontal: bool=True, color: QColor \| None=None) -> QIcon` | 翻转按钮的图标（水平/垂直 = 同一个图形转 90°）。 |
| `save_image(image: QImage, path: str \| Path, quality: int=JPEG_QUALITY) -> bool` | 把 QImage 写到磁盘：``.jpg``/``.jpeg`` 走有损（quality），其余交给 Qt。 |

#### `display_transform(rotation: int=0, flip_h: bool=False, flip_v: bool=False) -> QTransform`

翻转/旋转的变换矩阵——**屏幕与导出必须共用这一个**。

⚠️ 屏幕侧走 ``QGraphicsPixmapItem.setTransform``、导出侧走
``QImage.transformed``。两处若各写一份，改一处就会出现「看到的和下载的
不一样」（翻转轴或旋转方向不一致）。

#### `mirrored_rotate_icon() -> QIcon`

``FIF.ROTATE`` 的水平镜像 = **逆时针（左旋）**。

qfluentwidgets 只提供一个旋转图标：ROTATE 的箭头在弧线底部**指向左**，
即顺时针（右旋）。左旋用它的镜像，两颗按钮的笔触天然一致、只差方向。

多档位 pixmap 是为了高分屏下不掉清晰度（图标源是 SVG，按需渲染）。

#### `flip_icon(horizontal: bool=True, color: QColor | None=None) -> QIcon`

翻转按钮的图标（水平/垂直 = 同一个图形转 90°）。

qfluentwidgets 没有可用的翻转图标：``SEARCH_MIRROR`` 是"带镜子的放大镜"，
语义不对；``SYNC`` 是循环箭头。自绘还有个好处——一对图标笔触完全一致，
且按需渲染，任意 dpr 下都锐利。

#### `save_image(image: QImage, path: str | Path, quality: int=JPEG_QUALITY) -> bool`

把 QImage 写到磁盘：``.jpg``/``.jpeg`` 走有损（quality），其余交给 Qt。

单独抽出来是为了可测——保存对话框在离屏环境里弹不出来。

---

## `desktop.components.viewers.pdf_viewer`

源码：[`desktop/components/viewers/pdf_viewer.py`](../../desktop/components/viewers/pdf_viewer.py)

PDF 查看器：左侧页面缩略图 + 右侧大图。

### `class PdfViewerWidget(QWidget, WorkerHost, ZoomPopupMixin)`

PDF 查看器：左侧页面缩略图 + 右侧大图。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(placeholder: str='暂无 PDF', parent=None)` | 初始化 PDF 查看器：左侧页缩略图条 + 右侧大图。 |
| `set_pdf(path: Path \| None, placeholder: str \| None=None, cache_dir: Path \| None=None) -> None` | cache_dir：页缩略图缓存目录（如 thumbnails/source、thumbnails/print）， |

##### `__init__(placeholder: str='暂无 PDF', parent=None)`

初始化 PDF 查看器：左侧页缩略图条 + 右侧大图。

placeholder 为无 PDF 时的占位文案；缩略图/大图经 WorkerHost 异步
加载，并用缓存目录避免重复渲染。

##### `set_pdf(path: Path | None, placeholder: str | None=None, cache_dir: Path | None=None) -> None`

cache_dir：页缩略图缓存目录（如 thumbnails/source、thumbnails/print），
命中则直接使用，缺失的页渲染后补写。

⚠️ **缺页渲不渲要看缓存目录有没有别的生产者在填**（判据见
`_cache_is_being_filled`）：导入后台任务正在逐页写同一份缓存，
这里再跑一遍全量渲染 = 工作量翻倍 + 两个 PyMuPDF 循环互相抢 GIL，
界面直接冻住（2026-09-25 实测）。所以那时只做「只读 + 每秒回扫」，
生产者停手了才自己接手。

---

## `desktop.components.viewers.print_layout_canvas`

源码：[`desktop/components/viewers/print_layout_canvas.py`](../../desktop/components/viewers/print_layout_canvas.py)

第四步「版面编辑器」交互画布：在 A4 纸上拖拽 / 缩放图片。

坐标体系与 ``utils.page_layout.plan_print_page`` 算出的 ``plan.image`` 完全一致
——**页面毫米，左上原点，x 向右、y 向下**。控件把页面等比缩放到可视区，
用 ``px_per_mm`` 在「页面 mm」与「控件像素」之间换算；用户拖拽/缩放得到的
``[x_mm, y_mm, w_mm, h_mm]`` 直接写回 ``print.json`` 的 ``pages[].rect``，
生成 PDF 时由 ``plan_print_page(image_rect=...)`` 原样采用——所见即所得。

交互（与 detect/rembg 的裁剪框编辑同款手感）：
- 框内拖动 → 整体移动；**四角**手柄拖动 → 缩放（勾「原比例缩放」时等比）；
  **四条边整条都是命中带**（不限边中点的小圆点）→ 拖上/下边只改高度、
  拖左/右边只改宽度（自由拉伸改变比例）；松手 emit ``rect_changed``；
- 框始终被夹在页面内（夹到纸边即停），不会拖出页面；
- 悬停手柄/边/框时显示对应光标。

**标题与页码照画**：它们是「版面」的一部分，去掉就无从判断图片挪动后会不会
压到字（曾误判为「标题页码被去除」）。绘制复用 ``preview_worker`` 的
``_draw_print_text``——与成品 PDF 同源，只是多了画布自身的居中偏移。
标题/页码的落点只取决于 ``page_margins``，**不随图片框移动**，与 PDF 一致。

图片在框内按目标矩形**拉伸**绘制，与成品 ``pdf.image(img, x, y, w, h)`` 的
拉伸规则一致（PDF 用 w/h 直接定最终尺寸，不保比例）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| HANDLE_RADIUS | `6` |
| MIN_RECT_MM | `2.0` |
| EDGE_HIT_PX | `6` |

### `class PrintLayoutCanvas(QWidget)`

A4 纸上的图片拖拽/缩放画布；rect_changed 发出页面 mm 坐标。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `set_page(page_w_mm: float, page_h_mm: float, image: QImage \| None, rect_mm: Sequence[float], plan=None, keep_ratio: bool=True) -> None` | 设置页面尺寸、待绘制图片与初始图片框（页面 mm）。 |
| `current_rect() -> list[float]` | 当前图片框（页面 mm），供宿主落盘前读取。 |
| `resizeEvent(event) -> None` | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。 |
| `showEvent(event) -> None` | 显示时重算：首次进入第四步可能在布局完成前就 ``set_page`` 过， |
| `mousePressEvent(event) -> None` | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。 |
| `mouseMoveEvent(event) -> None` | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。 |
| `mouseDoubleClickEvent(event) -> None` | 双击 → ``double_clicked``（宿主打开预览弹窗）。 |
| `flush_pending() -> bool` | 把"还没松手"的拖动结果补发出去（关窗口/切步骤/切页时调）。 |
| `mouseReleaseEvent(event) -> None` | Qt 事件覆写：松开（提交本次编辑）。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

##### `set_page(page_w_mm: float, page_h_mm: float, image: QImage | None, rect_mm: Sequence[float], plan=None, keep_ratio: bool=True) -> None`

设置页面尺寸、待绘制图片与初始图片框（页面 mm）。

``plan`` 为 ``utils.page_layout.PrintPagePlan``：本控件据它画标题/
页码与「已跳过」提示——版面编辑不能只看图片，否则无从判断挪动后
会不会压到字。传 None 表示纯图片编辑（无标题/页码）。

``keep_ratio``（print 参数 `keep_ratio`）：True（默认）= 四角拖拽
**保持宽高比**、不提供四边手柄；False = 四角自由拉伸 + 上/下/左/右
四个边手柄可单独拉伸（与「铺满可用区域」的自动排版语义配套）。

##### `showEvent(event) -> None`

显示时重算：首次进入第四步可能在布局完成前就 ``set_page`` 过，
那时 ``width()/height()`` 还是 0，``_px_per_mm`` 会退化为 1.0。
仅靠 resizeEvent 兜不住「已分配尺寸但从未显示」的情况。

##### `flush_pending() -> bool`

把"还没松手"的拖动结果补发出去（关窗口/切步骤/切页时调）。

⚠️ 为什么需要（2026-09-26 审计）：`rect_changed` 只在 `mouseReleaseEvent`
里发（拖动过程中只 `update()` 重绘、不落盘）。于是「拖住图片框不放、
直接关窗口 / 返回列表」这一下改动就**永久丢失**，而且用户以为已经生效了
（画布上就是拖动后的样子）。这里主动补发一次，语义与正常松手完全一致。

返回 True 表示确实补发了一次（即存在未提交的改动）。

---

## `desktop.components.viewers.print_preview`

源码：[`desktop/components/viewers/print_preview.py`](../../desktop/components/viewers/print_preview.py)

生成 PDF（print）预览：左侧缩略图条 + 右侧单页效果预览。

布局与前三步保持一致（``ImageViewerWidget`` / ``RembgPreviewWidget`` 的
「左缩略图 + 右大图」），右侧不再是网格瀑布流：

- **打印效果**：按右侧表单参数（纸张/方向/边距/标题/页码）把图片排进一
  张纸里给用户在屏幕上看到——**只是效果，不执行、不提交、不生成 PDF**；
- **原图**：待打印图片本身（第三步「提交本次任务」的最终图）。

几何全部来自 ``utils.page_layout.plan_print_page``，而真正生成 PDF 的
``functions/print.py`` 用的是同一个函数，所以预览与成品不会漂移。

缩略图默认用条目图片本身（``ImageListWorker`` 走 QImageReader 缩放解码，
等于现算缩略图）；传入 ``thumb_provider`` 时改用它给出的预生成小图。

### `class PrintPreviewWidget(QWidget, ThumbsMixin, ZoomPopupMixin)`

生成 PDF 预览：左侧待打印缩略图条（可拖动排序）+ 右侧单页效果。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(empty_hint: str='暂无图片，请先完成去底色', params_provider=None, thumb_provider=None, parent=None)` | 构建工具栏 + 左缩略图条 + 右效果预览。 |
| `set_entries(entries: list[dict]) -> None` | 重建列表：entries = [{file, label}]，可按条目自带 thumb 指定小图。 |
| `entries() -> list[dict]` | 当前视觉顺序的富条目列表。 |
| `count() -> int` | 列表当前条目数。 |
| `set_pdf_path(path: str \| Path \| None) -> None` | 设置已生成 PDF 的路径；存在则启用下载按钮，否则禁用。 |
| `remove_selected() -> None` | 删除所有选中条目，未选中则通过 hint 信号提示。 |
| `refresh_display() -> None` | 右侧参数变化后按最新参数重画当前页（不生成任何文件）。 |
| `navigate(forward: bool) -> None` | 方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。 |
| `refresh_layout() -> None` | 参数（纸张/方向）变化后刷新画布：保留已存坐标，仅重算页面尺寸。 |
| `export_default_name() -> str \| None` | 导出对话框的默认文件名；没有可导出的页时返回 None。 |
| `export_current_effect(target: str \| Path) -> None` | 把**当前页**排进纸面后的 A4 效果图按 300dpi 写到 ``target``。 |

##### `__init__(empty_hint: str='暂无图片，请先完成去底色', params_provider=None, thumb_provider=None, parent=None)`

构建工具栏 + 左缩略图条 + 右效果预览。

params_provider: () -> print 参数字典；非法时抛异常（由本控件捕获
    并退回「原图」显示）。为 None 时关闭「打印效果」项。
thumb_provider: (path_text) -> Path | dict | None，可选的小图来源。

##### `export_current_effect(target: str | Path) -> None`

把**当前页**排进纸面后的 A4 效果图按 300dpi 写到 ``target``。

单页、不生成 PDF。走 worker 合成（与预览同一条 ``compose_print_page``
链路），所以"下载的图 = 屏幕上看到的效果"，只是精度与 PDF 同级而非
受屏幕像素限制。参数不合法/无条目时发 :attr:`export_failed`。

---

## `desktop.components.viewers.rembg_viewer`

源码：[`desktop/components/viewers/rembg_viewer.py`](../../desktop/components/viewers/rembg_viewer.py)

去底色预览：单视图显示，去底色结果优先，顶部用分段开关切换原图。

左侧缩略图条按"输出条目"组织：
- area=1：每个文本框一条（标签 <页>-l / <页>-r），右侧显示该框 + border 区域；
- area=2/3：每页一条，右侧显示按 crop/cropremove 规则合成的效果区域。

区域合成在 worker 线程完成，不生成文件；通过请求令牌避免快速切换串台。

### `class RembgPreviewWidget(QWidget, ThumbsMixin, ZoomPopupMixin)`

去底色预览：左侧输出条目列表 + 右侧单视图（去底色结果 / 原图切换）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(empty_hint: str='暂无图片', parent=None)` | 构建缩略图条与「去底色结果 / 原图」切换行，默认显示去底色结果。 |
| `set_images(paths: list[Path], rembg_dir: Path \| None, boxes_provider=None, region_params_provider=None, thumb_provider=None) -> None` | 设置图片清单与去底色目录，重建输出条目并加载显示。 |
| `refresh_display() -> None` | detect 框/area/border 变化后，重建输出条目并按新区域重新加载。 |
| `navigate(forward: bool) -> None` | 方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。 |
| `set_live_dir(path: Path \| None) -> None` | 设置（或传 None 清除）「实时预览」暂存目录。 |
| `live_dir() -> Path \| None` | 当前生效的实时预览暂存目录（未启用为 None）。 |
| `current_entry_path() -> str \| None` | 当前选中条目的源图路径（无条目时为 None）。 |
| `show_live_pending() -> None` | 实时预览正在计算：先给个即时反馈，别让界面看起来没反应。 |

##### `set_images(paths: list[Path], rembg_dir: Path | None, boxes_provider=None, region_params_provider=None, thumb_provider=None) -> None`

设置图片清单与去底色目录，重建输出条目并加载显示。

paths 为源图；rembg_dir 为去底色结果目录（存在才显示结果）；
各 provider 给出检测框 / 区域参数 / 缩略图来源。清单变化时重建
缩略图条，否则按最新区域重加载当前显示。

##### `set_live_dir(path: Path | None) -> None`

设置（或传 None 清除）「实时预览」暂存目录。

非 None 时结果图优先从这里取：它是按**此刻**面板参数现算的当前页；
而 ``_rembg_dir``（stages/rembgpreview）是上一次「生成预览」的全量产物，
参数可能已经改过。

---

## `desktop.components.viewers.thumb_strip`

源码：[`desktop/components/viewers/thumb_strip.py`](../../desktop/components/viewers/thumb_strip.py)

垂直缩略图条控件。

### `class ThumbStrip(QListWidget)`

垂直缩略图条：图标在上、标签在下，加载完成前显示占位图。

默认**不可拖动**（前三步的页面顺序由数据层决定）；第四步的待打印
列表调 ``set_reorderable(True)`` 打开内部拖放排序，顺序变化发
``order_changed``。

⚠️ 条目尺寸只有一个事实来源（本类的 ``ICON_SIZE`` / ``GRID_SIZE`` /
``STRIP_WIDTH`` / ``DECODE_EDGE``）：调用方解码缩略图时必须用
``DECODE_EDGE`` 当"最长边"，不要写字面量 96——竖开本页面受**高度**
约束，解码边取小了缩略图就只剩条目宽度的一半（缩略图看起来"没占满"）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `decode_edge(dpr: float=1.0, base: int \| None=None) -> int` | 按 dpr 给出的缩略图**解码最长边**（调用方在**主线程**算好后传进 worker）。 |
| `__init__(parent=None)` | 初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。 |
| `wheelEvent(event) -> None` | 滚轮按**条目**翻页：一格滚轮 = ``WHEEL_STEP_ITEMS`` 个条目。 |
| `set_reorderable(on: bool) -> None` | 打开/关闭条目内部拖放排序（第四步待打印列表用）。 |
| `set_deletable(on: bool) -> None` | 打开/关闭 Delete/Backspace 删除（只发信号，删不删由宿主定）。 |
| `navigate(forward: bool) -> None` | 方向键翻页：移动当前行（夹在两端，不回绕）。 |
| `keyPressEvent(event) -> None` | Delete/Backspace → ``delete_requested``。 |
| `add_placeholder(text: str) -> None` | 追加一个纯文字占位条目（无图标，如"缩略图加载中…"）。 |
| `add_page_item(label: str, path: str='') -> None` | 新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。 |
| `set_item_icon(index: int, image, path: str, label: str) -> None` | 替换某条目的图标/文字/路径（缩略图异步就绪后回调）。 |

##### `decode_edge(dpr: float=1.0, base: int | None=None) -> int`

装饰器：`staticmethod`

按 dpr 给出的缩略图**解码最长边**（调用方在**主线程**算好后传进 worker）。

``base`` 是逻辑像素下的基准边，默认取 ``DECODE_EDGE``（= 图标框长边）。

⚠️ 高分屏下条目本身是按 dpr 放大绘制的，只解码到逻辑尺寸就等于让 Qt
再放大一次 → 缩略图发糊。这与右侧大图 ``ImageView.preview_edge`` 是
同源问题（那边实测 150% 缩放下锐度差 7.6 倍）。

##### `__init__(parent=None)`

初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。

⚠️ 必须监听 ``currentRowChanged`` 而不是只接 ``itemClicked``：
键盘翻页（方向键 / PageUp / PageDown）与程序化 ``setCurrentRow``
只会改 currentRow、**不产生点击**，只接 itemClicked 就会出现
「翻页了但右侧预览不更新，切到别的视图模式再切回来才正常」。

##### `wheelEvent(event) -> None`

滚轮按**条目**翻页：一格滚轮 = ``WHEEL_STEP_ITEMS`` 个条目。

刻意不调 ``super()``：Qt 那条路径按 singleStep / 系统"滚动行数"算步长
（见 WHEEL_STEP_ITEMS 的说明），会把一格变成十几页。这里自己算目标行号
并把该行落到顶端，翻页量恒定。

##### `navigate(forward: bool) -> None`

方向键翻页：移动当前行（夹在两端，不回绕）。

主预览的方向键导航入口——「焦点在哪里，哪里就切换」：焦点在主界面
的非输入控件上时由详情页转到这里（四个步骤的预览组件共用本方法）；
焦点落在本条上时 QListWidget 的方向键本来就移动选择，语义一致。
``setCurrentRow`` 会触发 ``currentRowChanged``，预览刷新由各组件
既有的联动完成。

##### `keyPressEvent(event) -> None`

Delete/Backspace → ``delete_requested``。

⚠️ 第四步工具条的提示写着「Delete 删除选中」，原先没有任何地方接这个
键——提示是空头支票，按下去毫无反应。这里只负责把键翻成信号，
「删哪些、要不要落盘」仍归宿主（``PrintPreviewWidget.remove_selected``）。

##### `add_page_item(label: str, path: str='') -> None`

新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。

占位图按满框（ICON_SIZE）给 sizeHint——此时还不知道这张图的宽高比；
真实缩略图一到就由 set_item_icon 按实际比例改小。

---

## `desktop.components.viewers.thumbs_loader`

源码：[`desktop/components/viewers/thumbs_loader.py`](../../desktop/components/viewers/thumbs_loader.py)

缩略图异步装载混入：为 ThumbStrip **分批**加载图片缩略图。

⚠️ 为什么必须分批
    一次性把全部页面丢给一个 worker，worker 会在紧循环里连续做
    「QImageReader 缩放解码 + SmoothTransformation」，一个核直接打满——
    用户感知是「刚点进详情页，风扇突然转快」。而首屏真正看得见的只有
    最上面几行缩略图，其余几十张晚一两秒补齐完全不影响使用。

    分批后 CPU 从「连续满负载几秒」变成「一小段脉冲 + 间隙 + 若干小脉冲」，
    风扇不会明显起转；界面反而更早可交互（首批只做十几张的分量）。

### `class ThumbsMixin(WorkerHost)`

为持有 ThumbStrip 的查看器提供分批缩略图加载。

子类可以直接用基类的 :meth:`_load_thumbs`，也可以走
:meth:`_load_thumbs_chunked` 自带 worker 工厂与回调（print/rembg 需要
带 edge / effects / 自定义标签，都是走后者）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `shutdown_workers() -> None` | 停掉分批定时器与未完成的批次，再走基类的线程收尾。 |

---

## `desktop.pages.taskdetail.detect`

源码：[`desktop/pages/taskdetail/detect.py`](../../desktop/pages/taskdetail/detect.py)

任务详情页的 detect 检测控制器。

框坐标持久化在任务目录的 `boxes.json`（键为页面 stem）：
- 选中图片时优先读已有结果（命中则不再检测，手动框不被自动结果覆盖）；
- 子进程检测到的框写回（origin=auto）；
- 预览区拖动线框后写回（origin=manual），全程不生成新文件。

### `class DetectMixin`

依赖宿主页面提供的属性：store/task_id、detect_viewer、log_view、
detect_process/detect_cache、current_stage()。

---

## `desktop.pages.taskdetail.history`

源码：[`desktop/pages/taskdetail/history.py`](../../desktop/pages/taskdetail/history.py)

任务详情页的历史执行配置控制器：回填最近参数、历史下拉框。

### `class HistoryMixin`

依赖宿主页面提供的属性：store/task_id、control_stack、step_bar、
history_combo、_toast()。

---

## `desktop.pages.taskdetail.manifest`

源码：[`desktop/pages/taskdetail/manifest.py`](../../desktop/pages/taskdetail/manifest.py)

任务详情页的页面清单控制器：manifest 维护、缩略图/尺寸提供、页面增删。

### `class PageListMixin`

依赖宿主页面提供的属性：store/task_id、pages、pdf_page_count、
preview_stack、detect_viewer、extract_result_viewer、log_view、_toast()。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `delete_selected_page() -> None` | 删除当前选中的页面：按路径反查 manifest 下标后落盘。 |
| `insert_pages() -> None` | 插入图片到清单：按路径反查锚点下标，避免行号错位插错位置。 |

##### `delete_selected_page() -> None`

删除当前选中的页面：按路径反查 manifest 下标后落盘。

预览行号不能直接用于删除——文件缺失会导致查看器行号与清单下标错位；
故先经 _viewer_index_to_manifest_index 按路径反查真实下标再 pop，
删除后刷新预览并同步 detect/extract 两侧。

##### `insert_pages() -> None`

插入图片到清单：按路径反查锚点下标，避免行号错位插错位置。

弹文件框选图后复制到 extract 输出目录，再用当前选中行经路径反查得到
manifest 插入锚点；文件缺失时查看器行号与清单下标会错位，必须用路径。

---

## `desktop.pages.taskdetail.page`

源码：[`desktop/pages/taskdetail/page.py`](../../desktop/pages/taskdetail/page.py)

任务详情页：顶部步骤条 + 左侧多标签预览 + 右侧阶段控制面板。

预览区按阶段组织：
- extract：[PDF 预览 | 提取结果] 双标签页；
- detect：图片预览，叠加显示每张图的检测框位置；
- rembg：原图 / 去底结果对比；
- print：输出 PDF 预览。

本文件只保留页面骨架（任务切换、阶段切换、状态刷新），
其余职责按功能分文件（均位于 desktop/pages/taskdetail/）：
- view.DetailViewMixin       UI 组装（头部/步骤条/预览区/控制列/日志）
- manifest.PageListMixin     页面清单、缩略图、页面增删
- history.HistoryMixin       历史执行配置回填（暂存优先）
- params_draft.ParamDraftMixin 参数暂存（改过没执行也不丢）
- submit.SubmitMixin         rembg 提交控制器与按钮状态
- print_list.PrintListMixin  第四步待打印列表
- runner.StageRunnerMixin    阶段执行（worker 子进程编排）
- detect.DetectMixin         detect 检测控制
- rembg_live.RembgLiveMixin  第三步改参数/翻页时只重算当前页的实时预览

### `class TaskDetailPage(StageRunnerMixin, SubmitMixin, RembgLiveMixin, PrintListMixin, ParamDraftMixin, HistoryMixin, DetectMixin, PageListMixin, DetailViewMixin, QWidget, WorkerHost)`

任务详情页：由多个 Mixin 组合，固定四阶段流程。

编排 extract→detect→rembg→print 四阶段；各职责（预览、清单、历史、
提交、执行、检测）分散到同级 Mixin，本类只持有任务切换与阶段切换骨架。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(store, parent=None)` | 初始化详情页：建 worker 宿主、清运行态并组装 UI。 |
| `set_task(task_id: str) -> bool` | 切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。 |
| `current_stage() -> str` | 返回当前所处阶段的 key（extract/detect/rembg/print）。 |
| `navigate_by_arrow(forward: bool) -> bool` | 方向键切换当前步骤的页面（主窗口 ←/→ 转发入口）。 |
| `keyPressEvent(event) -> None` | ←/→ 切换当前步骤的页面（焦点链不消费时兜底到达这里）。 |
| `closeEvent(event) -> None` | 关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。 |
| `flush_layout_pending() -> None` | 把各处"未提交的界面改动"补发/落盘（关窗口、切步骤、切页前都要调）。 |
| `shutdown_all_workers() -> None` | 连同各预览控件自己的缩略图线程一起收尾。 |

##### `__init__(store, parent=None)`

初始化详情页：建 worker 宿主、清运行态并组装 UI。

创建 store 引用与 _init_worker_host 后台线程宿主；初始化全部运行态
字段（task_id/process/run_id/detect_cache 等）为空，再构建界面骨架。

##### `set_task(task_id: str) -> bool`

切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。

加载任务后先调用各面板 reset_to_default 清掉上一任务手改参数，再清
detect 缓存/运行态引用并刷新清单与预览；防止参数或 run_id 串到新任务。
返回 False = 拒绝切换（任务不存在 / 子任务执行中），调用方应留在原地。

##### `current_stage() -> str`

返回当前所处阶段的 key（extract/detect/rembg/print）。

以步骤条高亮下标映射到 STAGES 序列；下标为负时按 0 兜底处理。

##### `navigate_by_arrow(forward: bool) -> bool`

方向键切换当前步骤的页面（主窗口 ←/→ 转发入口）。

返回是否消费（主窗口据此决定要不要继续处理）。
「焦点在哪里，哪里就切换」：
- 焦点在**输入类控件**上时不抢（`_ARROW_OCCUPIED` 表——参数输入区
  的方向键移光标/改值，用户 18:30 明确那里不需要切换）；
- 焦点在预览弹窗里则由弹窗自己的窗口级 QShortcut 接管；
- 四个步骤的主预览都支持（移动缩略图条当前行，联动预览刷新）。

##### `closeEvent(event) -> None`

关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。

详情页持有 QProcess 与多个 WorkerHost 线程；先 kill 正在跑的执行/
检测子进程并等待（最多 1.5s），再 shutdown_all_workers 收尾其余线程，
最后接受关闭事件，避免解释器退出时被强杀崩溃。

##### `flush_layout_pending() -> None`

把各处"未提交的界面改动"补发/落盘（关窗口、切步骤、切页前都要调）。

目前是第四步的版面画布：拖动中不落盘，只在松手/补发时提交。

⚠️ **只按具体的类 `findChildren`，绝不用 `getattr(widget, ...)` 探测能力**：
四个阶段面板是 `LazyPanelHost`，属性转发（`__getattr__`）会**立刻把面板
构造出来**——那就把用户要求的「不进去就不建」破坏掉了。（2026-09-26 自己
踩到：写成 `getattr(w, "flush_pending", None)` 之后，`detail_prewarm`
护栏直接红成"四个面板全建"。）

##### `shutdown_all_workers() -> None`

连同各预览控件自己的缩略图线程一起收尾。

页面自身、PDF 预览、打印预览、缩略图条分别持有 WorkerHost 的线程，
只停页面的会让其余线程在解释器退出时被强杀（偶发崩溃/卡顿）。

---

## `desktop.pages.taskdetail.params_draft`

源码：[`desktop/pages/taskdetail/params_draft.py`](../../desktop/pages/taskdetail/params_draft.py)

任务详情页的「参数暂存」：用户改过、但还没执行的阶段参数，切走也还在。

问题：进入某阶段时表单按**最近一次执行参数**回填（``history.py``）。用户改完
参数却没执行就切阶段、切任务或关程序，改动全丢——再回来看到的还是上一次执行
的值，等于白调一遍（尤其第四步参数多）。

做法：
- 面板把"用户改了参数"通过 ``StagePanel.param_edited`` 报上来（程序化回填由
  面板自己的 ``_applying`` 挡住，不会误报）；
- 这里按 400ms 防抖写 ``tasks/<任务号>/drafts/<阶段>.json``（``store.DraftMixin``）；
- 进入阶段回填时的优先级是 **暂存 > 最近一次执行参数 > 内置默认**，
  实现在 ``HistoryMixin._restore_stage_params``。

为什么参数非法时不覆盖暂存：颜色/边距是逐字符输入的，"0,0" 这种半截状态
``get_args()`` 会抛 ValueError；此时保留上一份**有效**暂存，比写进去一份
用不了的值更合理（面板本来也会在说明行提示参数不合法）。

### `class ParamDraftMixin`

依赖宿主提供：store、task_id、control_stack。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `save_stage_draft(index: int) -> bool` | 暂存某阶段当前表单值；参数非法/没有任务时返回 False（不覆盖旧暂存）。 |

---

## `desktop.pages.taskdetail.print_list`

源码：[`desktop/pages/taskdetail/print_list.py`](../../desktop/pages/taskdetail/print_list.py)

任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。

### `class PrintListMixin`

依赖宿主页面提供的属性：store/task_id、print_preview、log_view、
_toast()。

---

## `desktop.pages.taskdetail.rembg_live`

源码：[`desktop/pages/taskdetail/rembg_live.py`](../../desktop/pages/taskdetail/rembg_live.py)

第三步「图片去底色」的实时预览控制器。

用户改 offset / type / 印章等参数时，**只重算当前页**并立刻显示，不必等
「生成预览」的全量任务；预览区翻页时，若那一页还没按当前参数算过，也算它。

三条边界（都是刻意的）：

1. **只在参数与「原本去底色参数」不同时才重算**。原本参数 = 最近一次成功
   「生成预览」所用的参数；一致就说明正式产物就是当前参数的结果，直接用它，
   不做无谓计算。
2. **一次只算一页**。全量是「生成预览」按钮的职责。
3. **只影响显示，不落正式产物**。结果写系统临时目录（``services.rembg_live``），
   绝不碰 ``stages/rembgpreview`` —— 那里一旦被单页结果覆盖，「提交本次任务」
   就会把不同参数下算出来的图混在一起。

滑块拖动时 ``valueChanged`` 会连发，所以统一走 ``LIVE_DEBOUNCE_MS`` 防抖；
每次请求带 token，迟到的旧结果直接丢弃（否则慢的旧结果会盖掉新的）。

### `class RembgLiveMixin`

依赖宿主页面提供：store / task_id / process / control_stack /
rembg_viewer / log_view / current_stage() / run_worker /
_latest_success_run() / PREVIEW_PARAM_KEYS。

---

## `desktop.pages.taskdetail.runner`

源码：[`desktop/pages/taskdetail/runner.py`](../../desktop/pages/taskdetail/runner.py)

任务详情页的阶段执行控制器：构建参数、启动 worker 子进程、解析进度日志。

纯业务派生规则见 desktop/services/print_plan.py，
rembg 提交控制器见 desktop/pages/taskdetail/submit.py，
历史配置回填见 desktop/pages/taskdetail/history.py。

### `class StageRunnerMixin`

依赖宿主页面提供的属性：store/task_id/source_path/pages、
control_stack、stage_* 控件、log_view、process/run_id 等。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `run_stage(resume: bool=False) -> None` | 启动当前阶段的 worker 子进程（带执行权守卫，防连点起两个）。 |
| `cancel_stage() -> None` | 中断正在执行的阶段：先落 cancelled 再 kill 子进程。 |

##### `run_stage(resume: bool=False) -> None`

启动当前阶段的 worker 子进程（带执行权守卫，防连点起两个）。

⚠️ 守卫必须包在**最外层**：下面要做参数校验、effects 组装、写运行配置，
这些都是同步重活，做完才 ``QProcess.start()``。若只在 start 之前判断
``self.process``，那段时间它还是 None，连点第二下就能再起一个 worker，
两个 torch 同时加载、同时写同一批输出目录。

守卫由 :meth:`TaskDetailPage._acquire_run` 提供（受理标记 + 防抖窗口）；
真正干活的是 :meth:`_run_stage_unchecked`。

##### `cancel_stage() -> None`

中断正在执行的阶段：先落 cancelled 再 kill 子进程。

先立即把运行记录置为 cancelled——防止进程被强杀来不及回调时状态永远
停留 running（重启后按钮状态错乱）；随后置 cancel_requested 并 kill。

---

## `desktop.pages.taskdetail.submit`

源码：[`desktop/pages/taskdetail/submit.py`](../../desktop/pages/taskdetail/submit.py)

任务详情页的 rembg「提交本次任务」控制器。

- run_rembg_submit          ：提交动作（派生条目 → worker 子进程）；
- _update_submit_button 等  ：提交按钮的版本状态与提示。

纯版本判定规则见 services/submit_state.py，
条目/效果派生规则见 services/print_plan.py。

### `class SubmitMixin`

依赖宿主页面提供的属性：store/task_id/source_path、process、
control_stack、submit_button/submit_hint、log_view、_toast()。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `run_rembg_submit() -> None` | 提交本次任务：把「生成预览」的去底色图片按 area/border 等 |

##### `run_rembg_submit() -> None`

提交本次任务：把「生成预览」的去底色图片按 area/border 等
合成为真正想要的最终图片，输出到 stages/rembg 目录。

⚠️ 与「执行本子任务」共用同一份执行权（``_acquire_run``）：提交与
生成预览抢的是同一个 worker 槽位与同一批输出目录，同时在跑只会互相
覆盖；连点两下同样由防抖窗口吞掉。

---

## `desktop.pages.taskdetail.view`

源码：[`desktop/pages/taskdetail/view.py`](../../desktop/pages/taskdetail/view.py)

任务详情页的视图构建：头部/步骤条/预览区/控制列/日志的 UI 组装。

只做控件创建与信号连接，业务动作全部委托给宿主页面的其他 Mixin。

视觉结构（自上而下）：
1. 页头卡片：返回 + 任务名 + 源文件标签 + 打开目录；
2. 步骤条卡片：四步流程与状态；
3. 主体：左侧预览卡片（自适应）+ 右侧参数卡片（固定宽度区间）；
4. 底部：执行日志状态条（常驻一行，点击唤出不挤压布局的日志浮层）。

### `class LazyPanelHost(QWidget)`

阶段面板的**惰性宿主**：真正被取用时才构造内部面板。

为什么需要：详情页一进来停在第一步，而第四步的 ``PrintPanel`` 构造要
~128 ms（占整个详情页构造的**一半**——它那张参数表单 ``build_form`` 单项
就 106 ms）。用户可能从头到尾都不点第四步，却每次进详情页都在为它买单。

属性访问一律转发给内部面板，所以 ``control_stack.widget(3).get_args()``
这类既有写法照常工作。Qt 自己的 ``sizeHint`` / ``paintEvent`` 等由 C++
层调用，**不走 Python 的 __getattr__**，不会误触发构造。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(factory, hooks=(), parent=None)` | factory() 造真面板；hooks 是"内部面板构造完成"后的回调（接线用）。 |
| `add_created_hook(fn) -> None` | 注册"内部面板构造完成"回调；**若已构造则立刻执行**。 |
| `peek() -> QWidget \| None` | **不触发构造**地看内部面板；尚未构造时返回 None。 |
| `panel() -> QWidget` | 内部真面板，首次访问时构造（并把挂着的回调全部执行一遍）。 |

##### `add_created_hook(fn) -> None`

注册"内部面板构造完成"回调；**若已构造则立刻执行**。

⚠️ 必须支持挂多个回调：视图层要接预览刷新、暂存层要接 param_edited，
它们分属不同 Mixin，各自只知道自己的接线，不能互相覆盖。

### `class DetailViewMixin`

依赖宿主页面提供的方法：_on_back、_select_stage、各预览联动槽、
current_stage()、_update_run_buttons() 等。

---

## `desktop.pages.tasklist.page`

源码：[`desktop/pages/tasklist/page.py`](../../desktop/pages/tasklist/page.py)

任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| HEADER_SUBTITLE | `"导入 PDF 后按四个子任务依次处理"` |

### `class TaskListPage(QWidget, WorkerHost)`

任务管理页：搜索 + 分页的任务列表，支持导入 PDF 与删除。

数据流是单向的：``refresh()`` 从 store 读出**全量**行并缓存，
``_render()`` 负责「按关键词过滤 → 分页切片 → 填表」。搜索框只触发
``_render()``（不再读盘），所以打字时不会每次都去扫一遍任务目录。

含表格/空状态二选一的内容区。导入刻意分两段：**主线程**只做「算指纹 →
查重 → 确认 → 建任务 → 刷新列表」（毫秒级，用户立刻看到新行）；**后台**
串行做「复制源文件 + 生成整本缩略图」，且等列表画完才开工，期间挂一条
「正在导入」提示条。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(store: TaskStore, parent=None)` | 初始化页面：构建 UI、绑定信号并刷新首次列表。 |
| `refresh() -> None` | 刷新任务行：**读盘放后台线程**，读完回主线程渲染。 |
| `focus_task(task_id: str) -> bool` | 翻到任务所在页并选中它；不在当前过滤结果里则返回 False。 |
| `import_pdf() -> None` | 导入 PDF：选文件后后台算指纹并查重确认建任务。 |
| `shutdown_workers() -> None` | 关程序前的收尾：先停导入后台队列（复制/缩略图），再走基类线程。 |
| `delete_task(task_id: str) -> None` | 删除指定任务及其全部中间产物（带确认弹窗）。 |

##### `__init__(store: TaskStore, parent=None)`

初始化页面：构建 UI、绑定信号并刷新首次列表。

parent 一般为 MainWindow；会创建 store 引用与导入按钮状态占位，
随后调用 refresh 重建表格与空状态。

##### `refresh() -> None`

刷新任务行：**读盘放后台线程**，读完回主线程渲染。

⚠️ 读盘不能占着 UI 线程：这里要遍历全部任务、逐个读它的 runs.json
（任务一多就是几十次文件 IO），同步做会把已经画出来的窗口卡住。行的
组装挪进了 ``TaskRowsWorker``，结果走 ``_on_rows_ready`` 回来渲染。

⚠️ 每次刷新带一个**代际令牌**：连续调用（导入任务后紧跟着又刷新）会让
多个 worker 并发跑，先发的可能后回来，把新数据盖成旧的——只认最后
一次发出的那个令牌，其余结果直接丢弃。

##### `focus_task(task_id: str) -> bool`

翻到任务所在页并选中它；不在当前过滤结果里则返回 False。

⚠️ 分页后不能直接用 ``table.select_task``：任务可能不在当前页，
表格里根本没有那一行。要先按**过滤后**的下标算出页码、切过去，
再在表格里选中。

##### `import_pdf() -> None`

导入 PDF：选文件后后台算指纹并查重确认建任务。

弹出文件框后若已有导入在跑则拒绝；否则起后台线程算内容指纹，
完成后回调按查重结果弹「创建新任务/定位已有任务」，命中也可建副本。

##### `delete_task(task_id: str) -> None`

删除指定任务及其全部中间产物（带确认弹窗）。

任务不存在时直接返回；否则弹确认框，确认后删库并刷新列表与提示。

---

## `desktop.services.font_catalog`

源码：[`desktop/services/font_catalog.py`](../../desktop/services/font_catalog.py)

第四步的字体候选目录：已知候选 + 后台扫一次的系统字体。

为什么要这个模块
----------------
`utils.fonts.selectable_entries()` 是一张**静态候选表**，查它只花几毫秒，
足以覆盖日常字体。但用户自己装的补字字体（花园明朝、BabelStone Han…）只有
真扫描才能发现，而它们恰恰是古籍异体字最需要的。

扫描的代价是**慢**（本机 200+ 字体约 7 秒），所以规矩有两条：

1. **只在后台线程扫**（`_ScanThread`），且**全局只启动一次**——扫完的结果
   写磁盘缓存，之后每次都是毫秒级；
2. **绝不挡住出 PDF 的路**：生成 PDF 只用 `utils.fonts` 的静态候选表，
   本模块纯粹服务于"给用户看的字体列表"。

用户在前三步干活的那点空闲，足够后台把列表补全；直接进第四步也能用，
只是列表是静态候选（扫描完成后会自动补进来）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| AUTO_LABEL | `"自动（仿宋优先）"` |
| AUTO_VALUE | `""` |
| _CATALOG | `None` |

### `class FontCatalog(QObject)`

字体候选目录（进程内单例，见 `catalog()`）。

- ``choices()``：立刻给出可用列表（静态候选 + 已扫到的），**不阻塞**；
- ``start_scan()``：后台扫一次系统字体，完成后发 ``scan_finished``，
  界面据此把新字体补进下拉。重复调用直接返回。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `choices() -> list[tuple[str, str]]` | 下拉候选 ``(中文显示, 参数值)``：自动 + 已知 + 扫描到的。 |
| `is_scanning() -> bool` | 后台扫描是否在跑（界面可据此显示"扫描中"）。 |
| `start_scan() -> None` | 启动后台扫描；**只启动一次**。 |

##### `choices() -> list[tuple[str, str]]`

下拉候选 ``(中文显示, 参数值)``：自动 + 已知 + 扫描到的。

⚠️ 按**显示名**去重：扫描结果里常出现与已知候选同名的字体（都叫
"楷体"），留两个同名项对用户没有意义，还容易选错。

##### `start_scan() -> None`

启动后台扫描；**只启动一次**。

调用时机无所谓（进第四步、回到第一步都行）——扫描在后台线程里跑，
主线程不被拖住。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `catalog() -> FontCatalog` | 进程内唯一的字体目录（首次调用时创建，需要已有 QApplication）。 |
| `start_background_scan() -> None` | 在空闲时把系统字体列表补齐（只跑一次，后台线程）。 |

---

## `desktop.services.print_plan`

源码：[`desktop/services/print_plan.py`](../../desktop/services/print_plan.py)

打印/提取条目的派生规则（纯函数，无 Qt 依赖，便于独立测试）。

这里的规则是 GUI 各阶段共享的「单一事实来源」：
- 提取缺页     → 续跑 extract 时的 pages 参数；
- 提交条目     → rembg「提交本次任务」的最终图片派生；
- 打印效果     → print 阶段在 worker 内实时合成的规格；
- 待打印列表   → 第四步左侧列表的默认排序与持久化合并。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `missing_extract_pages_spec(output_dir: Path, total: int) -> str \| None` | 提取输出目录中缺失的页码，压缩为 CLI pages 参数（如 "3,7-9"）。 |
| `plan_rembg_submit_entries(manifest_paths: list[Path], result_path_for, boxes_for, area: int) -> list[dict]` | 预览结果 + 检测框 + area/border → 最终图片条目。 |
| `entry_to_effect_spec(entry: dict, border) -> dict` | 提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。 |
| `plan_print_effects(list_entries: list[dict], composed: list[dict], rembg_dir: Path, submitted_labels: set[str], border) -> list[dict]` | 第四步列表 + 第三步当前 area/border → worker 合成规格。 |
| `plan_print_entries(rembg_files: list[Path], doc: dict \| None) -> tuple[list[dict], dict]` | 第四步待打印图片列表的规划。 |

#### `missing_extract_pages_spec(output_dir: Path, total: int) -> str | None`

提取输出目录中缺失的页码，压缩为 CLI pages 参数（如 "3,7-9"）。

页文件名以数字开头（0001.jpg / 0002.jpg …）。无缺失或 total 为 0
时返回 None（无需续跑）。

#### `plan_rembg_submit_entries(manifest_paths: list[Path], result_path_for, boxes_for, area: int) -> list[dict]`

预览结果 + 检测框 + area/border → 最终图片条目。

参数
----
manifest_paths   : 页面清单路径（stages/extract 内的页图片）
result_path_for  : (stem) -> Path|None，某页对应的「生成预览」去底结果
boxes_for        : (path_str) -> list，某页的检测框 [左框, 右框]
area             : 区域模式（1=左右分页，2/3=并集/对称画布）

派生规则与 rembg 预览条目、print 待打印列表完全一致：
- area=1 双框：拆 <页>-r / <页>-l 两条（古籍阅读顺序 r 在前）；
- area=2/3 双框：合成一条（不再分栏）；
- 单框：area=2/3 走对称画布，其余按普通框；
- 无框：整页预览图透传。
最终按 CLI natural sort 排序（同页 r 在 l 前）。

⚠️ ``parea`` 是**原始 area**（不是"降级"后的合成 area），``boxes`` 是
**原始检测框**（不是并集后的单框）——两者必须原样交给
``compose_region_output``。原因见 ``entry_to_effect_spec``：并集框 +
area=1 与「双框 + area=2/3」在 border 为空时**不等价**，曾导致第三步
预览是整页、而提交产物与 PDF 被紧裁（用户报的「PDF 成了 area=1 效果」）。

#### `entry_to_effect_spec(entry: dict, border) -> dict`

提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。

⚠️ 必须把**原始检测框 + 原始 area** 交给 ``compose_region_output``，
不能擅自"化简"成并集框 + area=1。``utils.box_geometry.build_output_layout``
在 border 为空（padding=None）时两条分支并不等价：

- area=2/3（含多框）→ ``full_page=True``：整页画布，各框**写回原位置**；
- area=1            → 紧裁成「框 + border」的小画布。

此前双框 area=2/3 被记成"并集框 + parea=1"，于是第三步预览（用原始框
+ 原始 area）显示整页、提交产物与 PDF 却是紧裁——用户报的「第三步 area=2、
预览也是 area=2，生成的 PDF 却是 area=1 的效果」就是这么来的（紧裁观感
与 area=1 的半页裁剪一致）。

``full`` 原样透传给合成层：整幅内容(fullcontent)页的内容区＝**整页**，
合成时按 area=4 处理（不拆 `-l`/`-r`、不镜像、不紧裁）——见
``desktop.workers.preview_worker.region_canvas_specs``。

#### `plan_print_effects(list_entries: list[dict], composed: list[dict], rembg_dir: Path, submitted_labels: set[str], border) -> list[dict]`

第四步列表 + 第三步当前 area/border → worker 合成规格。

与「提交本次任务」复用同一套派生规则（plan_rembg_submit_entries）：
源图为 stages/rembgpreview 去底图，effect 携带检测框/area/border，
由 run_print_stage 在子进程内实时合成后再排版为 PDF。

与用户在第四步保存的列表（拖动排序/删除/外部插入）按 label 对齐：
- 命中当前 area 派生集合的条目，按用户列表顺序输出合成规格；
- 列表 label 与当前派生集合**形态不同**（用户改过 area 而未重新提交）时，
  按 `_base_label` 重映射到该页派生的全部条目——**顺序仍取列表顺序**，
  这样本步的删除/排序在参数变化后依然生效；
- 用户插入的外部图片（不在 stages/rembg 目录）整图透传；
- 兜底补漏：当前派生集合里、列表与已提交产物都没有的条目才补在末尾。

#### `plan_print_entries(rembg_files: list[Path], doc: dict | None) -> tuple[list[dict], dict]`

第四步待打印图片列表的规划。

直接使用第三步「提交本次任务」产出的 stages/rembg 最终图片
（已按 area/border 合成），按古籍阅读顺序（cover/menu 优先、
同编号 r→l、数字自然序）排列。

列表不再使用源 PDF 缩略图，直接显示 rembg 最终图片本身；
print.json 仅持久化用户的拖动/删除/插入顺序。

返回 (entries, doc)。

---

## `desktop.services.rembg_live`

源码：[`desktop/services/rembg_live.py`](../../desktop/services/rembg_live.py)

第三步「改参数实时预览当前页」的计算与落盘。

与「生成预览」的分工
--------------------
- **「生成预览」**：全量正式产物，写 ``stages/rembgpreview``，会被「提交本次
  任务」读取。参数一变它就过期（见 ``services/submit_state`` 的 PREVIEW_STALE）。
- **本模块**：只算用户当前看着的**那一页**，落到系统临时目录，仅供预览区显示。
  **绝不碰 rembgpreview** —— 否则各页是不同参数下算出来的，提交时新旧混用，
  成品会不自洽。

计算入口统一走 ``utils.rembg_page``，与 CLI 产物逐像素同源（``functions.rembg``
用的是同一个函数）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `live_dir(task_id: str) -> Path` | 该任务的实时预览暂存目录（系统临时目录下，按 task_id 隔离）。 |
| `reset(task_id: str) -> None` | 清空该任务的实时暂存（参数回到「生成预览」状态时调用）。 |
| `render_page(image_path: str, args: dict, out_dir: str \| Path) -> str` | 对单页执行去底色并写入 ``out_dir``，返回结果文件路径。 |

#### `render_page(image_path: str, args: dict, out_dir: str | Path) -> str`

对单页执行去底色并写入 ``out_dir``，返回结果文件路径。

⚠️ 重依赖（numpy / PIL，以及 ``utils.image_utils`` 背后的 cv2）在这里
**延迟导入**：GUI 主进程只有在用户真的动了参数时才付出这点加载成本，
启动路径不受影响。

PNG 用 ``compress_level=1``：这是**临时预览**，编码速度比压缩率重要
（正式产物走 ``functions.rembg``，那里仍是 level=9）。

---

## `desktop.services.stale_chain`

源码：[`desktop/services/stale_chain.py`](../../desktop/services/stale_chain.py)

跨阶段「上游重新执行 → 下游产物已过期」的判定（纯函数，无 Qt 依赖）。

只看**成功运行的时间戳链**：某个下游阶段最近一次成功运行，比它的前置阶段里
某一个的最近一次成功运行还旧 → 这个下游产物可能已经不是最新参数下的结果。

⚠️ 只做判定，不做任何动作：**不自动重跑、不删产物、不改参数**。界面据此给一句
提示（第四步状态行 + 主按钮高亮），要不要重跑由用户决定。

⚠️ 不比对参数。参数级的"待更新"另有专门机制（见 `submit_state.py`：
生成预览 → 提交本次任务的 new_version / preview_stale），本模块只回答
"上游又跑过一次、而下游还是那之前的产物吗"。

### 模块常量

| 名称 | 值 |
| --- | --- |
| TIMESTAMP_TOLERANCE_S | `2.0` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `latest_success(records) -> dict \| None` | 一组运行记录里最近一次**成功**的那条（按 finished_at 取最大）。 |
| `stale_upstream(runs: dict) -> dict[str, dict]` | runs（``{阶段: [记录, ...]}``）→ 过期判定 ``{下游阶段: 详情}``。 |

#### `latest_success(records) -> dict | None`

一组运行记录里最近一次**成功**的那条（按 finished_at 取最大）。

失败/中断的跑动不算数：它们没产出可用于比对的产物。

#### `stale_upstream(runs: dict) -> dict[str, dict]`

runs（``{阶段: [记录, ...]}``）→ 过期判定 ``{下游阶段: 详情}``。

详情：``{"stage": 更新了的上游阶段, "upstream_at": ts, "downstream_at": ts}``。
下游**从未成功过**时不判过期——那种情况界面本来就在说"未执行"，再叠一句
"已过期"只会让人困惑。

---

## `desktop.services.submit_state`

源码：[`desktop/services/submit_state.py`](../../desktop/services/submit_state.py)

rembg「提交本次任务」按钮的版本状态机（纯函数）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| PREVIEW_STALE | `"preview_stale"` |
| NEW_VERSION | `"new_version"` |
| UP_TO_DATE | `"up_to_date"` |
| NO_PREVIEW | `"no_preview"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `rembg_submit_version_state(preview_run: dict \| None, submit_run: dict \| None, panel_args: dict, preview_param_keys) -> str` | 提交按钮版本状态： |

#### `rembg_submit_version_state(preview_run: dict | None, submit_run: dict | None, panel_args: dict, preview_param_keys) -> str`

提交按钮版本状态：

- no_preview   ：从未成功生成预览（或最近一次失败/中断）→ 禁止提交；
- preview_stale：面板去底参数相对最近一次成功预览已修改，
                 磁盘上的预览图不是最新 → 建议重新生成预览；
- new_version  ：预览有新版本（重新生成过、或 area/border 已改），
                 最终图片落后于预览 → 提示需要提交；
- up_to_date   ：最终图片已是最新预览版本。

---

## `desktop.single_instance`

源码：[`desktop/single_instance.py`](../../desktop/single_instance.py)

desktop 单例守卫：**同一个构建**同时只允许一个 GUI 实例。

用户原则：开发版（源码 / hupper 启动）与正式版（安装的 guji-desktop.exe）是
两个不同的程序，**可以同时存在**——所以互斥体按「构建身份」区分：

- 同一个构建第二次启动 → 检测到已有实例，把已有窗口带到前台、自己退出；
- 两个构建各跑各的，互不阻拦（即便它们共用 `~/Documents/guji` 数据区）。

实现（win32）：
- **互斥体**判定"是否已有本构建实例"：`CreateMutexW`，若 `GetLastError` 返回
  ERROR_ALREADY_EXISTS 则说明已有。句柄必须**存进模块级变量**——句柄被垃圾回收
  互斥体就销毁了，守卫随之失效（活到进程退出，正合需求）。
- **把已有窗口带到前台**：`FindWindowW` 按窗口标题找，`ShowWindow(SW_RESTORE)`
  + `SetForegroundWindow`。不做跨进程消息通道，够用且零依赖。

⚠️ 仅 win32 生效；其它平台直接放行（本项目只在 Windows 打包发行）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _MUTEX_PREFIX | `"Local\GujiZhiZuo-Desktop-"` |
| _ERROR_ALREADY_EXISTS | `183` |
| _SW_RESTORE | `9` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `mutex_name(identity: str) -> str` | 由构建身份推出互斥体名。 |
| `acquire(identity: str) -> bool` | 尝试持有本构建的单例互斥体。False = 已有本构建实例（调用方应退出）。 |
| `activate_existing_window(title: str) -> bool` | 把已有实例的窗口恢复并带到前台。找不到（返回 False）也不影响退出。 |

#### `mutex_name(identity: str) -> str`

由构建身份推出互斥体名。

identity 用 **desktop 包目录**（`desktop.utils.files.package_dir()`）：
源码是 `D:\...\desktop`，打包是 `...\guji\_internal\desktop`——同一构建
稳定不变，两个构建互不相同。

---

## `desktop.stages.detect_stage`

源码：[`desktop/stages/detect_stage.py`](../../desktop/stages/detect_stage.py)

detect 阶段执行器：单图检测 + 批量检测。

重依赖（torch/ultralytics）由**常驻 YOLO 服务**承担（见
`functions/yolo_service.py`）：本进程只发「图片路径」过去等结果，因此一个
worker 起来只需几百毫秒，模型全局只加载一次、多次检测共用。

日志按用户要求逐张留痕——「模型加载用时」+「每张 detect 了哪个文件、结果
如何、花了多久」+「总计用时」。没有这些，一次检测跑完日志里只有进度条在动，
用户根本不知道到底执行了什么。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `run_detect(config: dict) -> int` | 检测单张图片的内容框（半幅左右 / 整幅），返回像素坐标（重依赖由常驻服务承担）。 |
| `run_detect_stage(config: dict) -> int` | detect 阶段：逐图检测内容框（半幅左右 / 整幅）并上报坐标，不切割、不生成任何文件。 |

#### `run_detect_stage(config: dict) -> int`

detect 阶段：逐图检测内容框（半幅左右 / 整幅）并上报坐标，不切割、不生成任何文件。

检测算法复用 `functions.detect.detect_page_boxes_by_path`（内部即 CLI crop /
cropremove 用的同一入口），最终裁剪框由 GUI 按同一套规则
（`utils.box_geometry.compute_final_boxes`）从检测框实时推导，用于预览标注。

---

## `desktop.stages.events`

源码：[`desktop/stages/events.py`](../../desktop/stages/events.py)

worker 子进程的事件输出层。

分两层职责，**顺序很重要**：

1. **结构化通道**（主）：`JsonLinesReporter` 实现 `core.reporter.Reporter` 协议，
   由阶段执行器注入给功能模块。进度、检测框、页尺寸等「给程序读的信号」直接
   以字典形式写成 JSON Lines，不经过任何字符串解析 —— 改文案不会再静默打断
   GUI 进度条。
2. **兜底通道**（辅）：`ProgressStream` 拦截功能模块（以及第三方库）的 print，
   把**人读日志**转发为 ``{"type": "log"}`` 事件。它不再做正则解析。

历史包袱说明：以前没有结构化通道，所有信号都靠 ProgressStream 跑正则从中文
提示里捞（`进度: d/t`、`图片总数: n`、`[boxes] …`、`[imgsize] …`）。那种
「文案即契约」的耦合已移除；`[boxes]`/`[imgsize]` 两行文本仍在 functions 侧
兼容保留一个版本，便于对照验证，但本文件不再解析它们。

### `class JsonLinesReporter`

把功能模块的结构化汇报写成 JSON Lines（worker → GUI 的正式协议）。

context 提供 task_id/stage/run_id，附加到每条事件上供 GUI 归位到具体任务。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(context: dict, stream=None)` | — |
| `progress(done: int, total: int) -> None` | — |
| `event(name: str, **payload: Any) -> None` | 转发具名事件。 |
| `log(message: str) -> None` | — |

##### `event(name: str, **payload: Any) -> None`

转发具名事件。

`progress_total`（引擎先给出总数、尚无完成量）在协议上仍是一条
progress 事件：GUI 只关心 total 用来设进度条 range，因此这里
统一映射为 done=0 的 progress，避免新增一种 GUI 不认识的事件类型。

### `class ProgressStream(io.TextIOBase)`

拦截功能模块的 print 输出，原样转发为人读日志事件。

⚠️ 这里**刻意不做任何解析**。以前它跑四条正则从中文提示里捞进度与结构化
数据，属于「文案即契约」——改一句提示就静默断掉 GUI 进度条。现在信号走
`JsonLinesReporter`，本类只负责让日志视图不漏行（含第三方库的 print）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(real_stdout, context: dict)` | real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到 |
| `writable() -> bool` | 恒为 True：本流始终接受写入。 |
| `write(text: str) -> int` | 按换行或回车切分输出边界，逐行转发日志；返回写入字符数（满足 io.TextIOBase 约定）。 |
| `flush() -> None` | 空实现（行缓冲已在 write 中处理，无需真正刷盘）。 |

##### `__init__(real_stdout, context: dict)`

real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到
本流发出的每条事件上，供 GUI 归位到具体任务与阶段。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `emit(payload: dict, stream=None) -> None` | 向 GUI 输出一条 JSON Lines 事件（线程安全）。 |

#### `emit(payload: dict, stream=None) -> None`

向 GUI 输出一条 JSON Lines 事件（线程安全）。

stream 缺省写真实 stdout；窗口化打包运行时 sys.stdout 可能为 None，
此时由 _real_stdout() 兜底到文件描述符 1。

⚠️ 序列化与写入必须在同一把锁里：先序列化再抢锁会让两个线程的
payload 交替入队、输出的仍是交错行。

---

## `desktop.stages.generic_stage`

源码：[`desktop/stages/generic_stage.py`](../../desktop/stages/generic_stage.py)

通用阶段执行器：CLI 功能阶段（run_stage）+ PDF 渲染阶段（run_extract_stage）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `run_stage(config: dict) -> int` | 在子进程中执行一个 CLI 功能阶段，返回进程退出码（0/130/1）。 |
| `run_extract_stage(config: dict) -> int` | extract 阶段：直接把 PDF 提取到任务目录 stages/extract/（无嵌套布局）。 |

#### `run_stage(config: dict) -> int`

在子进程中执行一个 CLI 功能阶段，返回进程退出码（0/130/1）。

config 需含 task_id/stage/run_id/args。结构与人类日志走两条通道：

- **结构化**：`JsonLinesReporter` 注入给功能模块，进度 / 检测框 / 页尺寸
  直接以字典写成 JSON Lines（不再靠正则解析中文提示）；
- **人读日志**：ProgressStream 仍拦截 stdout 转发为 log 事件，保证日志
  视图一行不漏（含第三方库的输出）。

通过 args['_outpath'] 可覆盖功能模块计算出的输出目录。异常以 error 事件
回报，不抛到上层。

#### `run_extract_stage(config: dict) -> int`

extract 阶段：直接把 PDF 提取到任务目录 stages/extract/（无嵌套布局）。

复用 utils.pdf_extract.render_pages_parallel 的提取/并发实现（与 CLI 同一份），
但不走 CLI 的 <out_root>/<pdf名>/images 输出规则。

⚠️ 这里曾经直接调 process_page_batch(全部页码) —— 那是**串行**的，
GUI 提取因此比 CLI 慢数倍。并发逻辑在 render_pages_parallel 里。

---

## `desktop.stages.print_stage`

源码：[`desktop/stages/print_stage.py`](../../desktop/stages/print_stage.py)

print 阶段执行器：合成效果图后按**有序清单**生成 PDF。

页序完全由 ``args["files"]``（GUI 第四步列表顺序）决定，不再依赖文件名
排序——因此不再需要把顺序「烧」进文件名的 workset 目录。合成结果写入
一次性临时目录，交给 print 时同时给出有序清单，执行结束即随临时目录删除。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _STAGING_ROOT_NAME | `"guji-print-staging"` |
| _OWNER_FILE | `"owner.pid"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `staging_root() -> Path` | 所有效果图暂存目录的固定根。 |
| `sweep_orphan_staging(exclude: Path \| None=None) -> int` | 删掉「属主进程已死」的暂存目录，返回删除个数。 |
| `run_print_stage(config: dict) -> int` | print 阶段：把 rembg 结果按 area/border 合成为效果图，再生成 PDF。 |

#### `sweep_orphan_staging(exclude: Path | None=None) -> int`

删掉「属主进程已死」的暂存目录，返回删除个数。

`exclude` 传自己正在用的目录（绝不删自己）。

#### `run_print_stage(config: dict) -> int`

print 阶段：把 rembg 结果按 area/border 合成为效果图，再生成 PDF。

效果合成放在子进程而非 GUI 线程：既不阻塞界面，也避免 GUI 侧
QProcess 从回调链启动时 Windows 下通知丢失的问题。

args["_effects"] = [
    {"file": 源图路径, "label": 输出条目名,
     "effect": {"boxes": [[x1,y1,x2,y2]], "area": int, "border": str|None}},
    …
]

合成结果按**列表顺序**以 ``0001.png`` 命名写入临时暂存目录，并把
``args["files"]`` 设为这份有序清单——CLI 侧不再读目录、不再解析
文件名，页序与第四步列表严格一致（拖拽重排无需任何物理文件改动）。

---

## `desktop.stages.rembg_stage`

源码：[`desktop/stages/rembg_stage.py`](../../desktop/stages/rembg_stage.py)

rembg_submit 阶段执行器：把「生成预览」产出的整页去底图合成为最终交付图片。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `run_rembg_submit_stage(config: dict) -> int` | rembg 提交：把「生成预览」产出的整页去底图，按 area/border + 检测框 |

#### `run_rembg_submit_stage(config: dict) -> int`

rembg 提交：把「生成预览」产出的整页去底图，按 area/border + 检测框
合成为真正想要的最终图片，写入任务 output 目录。

与 run_print_stage 的效果合成复用同一套几何规则
（desktop/workers/preview_worker.compose_region_output），
但结果是持久化的交付图片而非一次性暂存，且不再生成 PDF。

args["_effects"] = [
    {"file": 预览结果路径, "label": 输出文件名(无扩展名),
     "effect": {"boxes": [[x1,y1,x2,y2]], "area": int, "border": str|None} | None},
    …
]

---

## `desktop.store.annotations`

源码：[`desktop/store/annotations.py`](../../desktop/store/annotations.py)

页面标注数据：boxes.json（检测框）与 sizes.json（页面图片原始尺寸）。

坐标均为原始图片像素坐标 [x1, y1, x2, y2]，按阅读顺序存 [左框, 右框]。
image_key 取页面文件名去后缀（stem）——检测/去底直接以 extract 目录为
输入，不再物化副本，故同一 stem 恒指向同一页。

### `class AnnotationMixin`

boxes.json / sizes.json 读写。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `boxes_path(task_id: str) -> Path` | 检测框存储文件：任务目录下的 boxes.json。 |
| `detect_boxes_entry(task_id: str, image_key: str) -> tuple[list, str] \| None` | 返回 (boxes, origin)；无记录时返回 None。origin: 'auto' \| 'manual'。 |
| `save_detect_boxes(task_id: str, image_key: str, boxes: list, origin: str='auto') -> None` | 写入某页的检测框及其来源标记（auto=自动检测，manual=人工编辑）。 |
| `save_detect_boxes_batch(task_id: str, entries: dict[str, list]) -> None` | 批量写入某阶段的检测框（origin=auto）：**一次读改写**。 |
| `save_image_sizes_batch(task_id: str, entries: dict[str, tuple[int, int]]) -> None` | 批量写入页面原始尺寸：一次读改写（理由同 save_detect_boxes_batch）。 |
| `sizes_path(task_id: str) -> Path` | 页面原始尺寸文件：任务目录下的 sizes.json。 |
| `save_image_size(task_id: str, image_key: str, width: int, height: int) -> None` | 记录某页图片的原始像素尺寸，作为框坐标与预览映射的坐标系基准。 |
| `image_size(task_id: str, image_key: str) -> tuple[int, int] \| None` | 返回某页原始像素尺寸 (width, height)；无记录时返回 None。 |

##### `save_detect_boxes_batch(task_id: str, entries: dict[str, list]) -> None`

批量写入某阶段的检测框（origin=auto）：**一次读改写**。

⚠️ 为什么必须攒批：detect 跑 320 页时逐页 `save_detect_boxes` 是
「读整个 boxes.json + 改写」× 页数，实测 320 页累计 **1.8 秒**主线程
阻塞（2400 页的书记忆里是 47.5s，见
``.workbuddy/perf/2026-09-23-sqlite-vs-json.md``）；攒批后一次落盘
~0.02s。人工框（origin=manual）在这里跳过，不被自动结果覆盖——
与单条版同一条规矩，但只读一次文件。

---

## `desktop.store.drafts`

源码：[`desktop/store/drafts.py`](../../desktop/store/drafts.py)

参数暂存（``drafts/<阶段>.json``）：用户改过、但**还没执行**的阶段参数。

为什么需要它：进入某个阶段时表单按「最近一次执行参数」回填（见
``desktop/pages/taskdetail/history.py``），用户改完参数却没执行就切阶段 /
切任务 / 关程序，改动全部丢失——再回来看到的还是上一次执行的值，等于白调。

存什么：``get_args()`` 的结果（已归一化：边距是列表、颜色是 "r,g,b"、
跳过页是列表…）。读取方是同一个面板的 ``apply_args()``，所以"存—取"天然
按同一套键名对称，不需要第二份字段表。

- 与 ``pages.json``/``print.json`` 一样是任务目录下的 JSON，删除任务即清掉；
- 系统管理字段（input/output/workers/clean…）不入暂存，与历史回填的跳过
  清单一致；
- 参数非法时调用方**不写**（见 ``save_draft`` 的返回值），保留上一份有效暂存。

### `class DraftMixin`

``drafts/<阶段>.json`` 的读写。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `drafts_dir(task_id: str) -> Path` | 暂存目录：``tasks/<任务号>/drafts``。 |
| `draft_path(task_id: str, stage: str) -> Path` | 某阶段的暂存文件：``drafts/<阶段>.json``。 |
| `load_draft(task_id: str, stage: str) -> dict \| None` | 读取暂存参数；没有/格式不对返回 None。 |
| `save_draft(task_id: str, stage: str, params: dict) -> bool` | 写入暂存参数，返回是否真的写了。 |
| `clear_draft(task_id: str, stage: str) -> None` | 删除某阶段的暂存（用户点「恢复默认配置」并执行后想彻底归零时用）。 |

##### `save_draft(task_id: str, stage: str, params: dict) -> bool`

写入暂存参数，返回是否真的写了。

任务目录已删除时跳过（与 ``save_pages`` 同规矩：不把已删任务重新
创建出来）；``params`` 为空则视为"没有可暂存的内容"，返回 False。

---

## `desktop.store.json_io`

源码：[`desktop/store/json_io.py`](../../desktop/store/json_io.py)

JSON 持久化的原子读写工具。

任务状态全部存在 JSON 文件里，一旦写入过程中进程崩溃/断电，直接
``write_text`` 会留下半截文件；而读取侧把解析失败当作"没有数据"，
结果是全部任务或执行历史静默消失。因此统一改为：

1. 写入同目录的临时文件，``fsync`` 落盘后 ``os.replace`` 原子替换；
2. 读取失败时不返回空值，而是把损坏文件改名成 ``*.corrupt-<时间>``
   保留现场，再返回默认值——避免用户"数据被悄悄清空"。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _SUFFIX | `".tmp"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `read_json(path: Path, default)` | 读取 JSON；文件不存在返回 default，损坏则备份后返回 default。 |
| `write_json(path: Path, data, indent: int=1) -> None` | 原子写 JSON（临时文件 + fsync + os.replace）。 |

#### `read_json(path: Path, default)`

读取 JSON；文件不存在返回 default，损坏则备份后返回 default。

⚠️ 「损坏」有两种，必须一起兜住：**语法坏了**（`JSONDecodeError`）与
**不是合法 UTF-8**（`UnicodeDecodeError`，外部编辑器/磁盘损坏/异构工具写坏
都能造成）。后者是 `ValueError` 的子类、**不是** `OSError`，早期实现只 try
`OSError` + `JSONDecodeError`，于是它会一路穿透到调用它的 Qt 槽里——在事件
处理中抛异常比"备份后返回默认值"糟糕得多。

#### `write_json(path: Path, data, indent: int=1) -> None`

原子写 JSON（临时文件 + fsync + os.replace）。

父目录不存在时直接放弃写入并返回 False 语义——任务目录被删除后
仍在跑的子进程回调不应该把目录重新创建出来。

---

## `desktop.store.pages`

源码：[`desktop/store/pages.py`](../../desktop/store/pages.py)

页面清单（pages.json）：当前任务参与处理的页集合。

### `class PageManifestMixin`

pages.json 的读写与按阶段输出目录重建。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `pages_path(task_id: str) -> Path` | 当前任务的页面清单文件：任务目录下的 pages.json。 |
| `load_pages(task_id: str) -> list[dict]` | 读取页面清单；文件缺失或格式异常时返回空列表。 |
| `save_pages(task_id: str, pages: list[dict]) -> None` | 写回页面清单；任务目录已删除时跳过（不重建目录）。 |
| `refresh_pages_from_dir(task_id: str, directory: Path) -> list[dict]` | 用某阶段输出目录重建页面清单（大任务当前的页集合）。 |
| `print_pages_path(task_id: str) -> Path` | 待打印列表文件：任务目录下的 print.json。 |
| `load_print_doc(task_id: str) -> dict \| None` | 读取 print.json 全文（含 area/border/pages）；缺失或非字典时返回 None。 |
| `save_print_doc(task_id: str, doc: dict) -> None` | 写回 print.json；任务目录已被删除时静默跳过（不重建目录）。 |
| `load_print_pages(task_id: str) -> list[dict]` | 只取 print.json 的 pages 列表；无文档时返回空列表。 |
| `save_print_pages(task_id: str, entries: list[dict]) -> None` | 只替换 print.json 的 pages 字段，保留 area/border 等其它配置。 |

---

## `desktop.store.runs`

源码：[`desktop/store/runs.py`](../../desktop/store/runs.py)

阶段运行历史（runs.json）：每个阶段保留最近多次执行的记录，最新在前。

结构：{stage: [record, ...]}
record: {run_id, status, parameters, done, total, started_at, finished_at,
         output_path, error}
历史记录既用于页面状态渲染（最新一条），也作为阶段面板的历史配置选项。
``error`` 只在失败时写：worker 起不来的那类失败（0 条事件、0.2 秒退出）
以前在记录里只有 ``done=0 total=0``，事后完全没法查。

### 模块常量

| 名称 | 值 |
| --- | --- |
| MAX_RUN_HISTORY | `20` |

### `class RunMixin`

runs.json 读写。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `runs_path(task_id: str) -> Path` | 运行历史文件：任务目录下的 runs.json。 |
| `create_stage_run(task_id: str, stage: str, parameters: dict, resume: bool=False) -> str` | 登记一次新的阶段执行并返回 run_id。 |
| `set_progress(task_id: str, run_id: str, done: int, total: int) -> None` | 按 run_id 更新 done/total；run_id 不在任何阶段时静默忽略。 |
| `finish_stage(task_id: str, run_id: str, status: str, output_path: str \| None=None, progress: tuple[int, int] \| None=None, error: str \| None=None) -> None` | 结束某次运行：写入 status/finished_at/output_path（可选 error）。 |
| `list_stage_runs(task_id: str, stage: str) -> list[dict]` | 某阶段的历史执行记录，最新在前。 |
| `all_stage_runs(task_id: str) -> dict[str, list[dict]]` | 整份运行历史（**一次读盘**），键为阶段名、值为最新在前的记录列表。 |
| `stage_states(task_id: str) -> dict[str, dict]` | 每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。 |

##### `create_stage_run(task_id: str, stage: str, parameters: dict, resume: bool=False) -> str`

登记一次新的阶段执行并返回 run_id。

新记录插在该阶段历史最前，初始状态 running、进度 0/0；每阶段只保留
最近 MAX_RUN_HISTORY 条。resume 标记本次是否为续跑。

##### `finish_stage(task_id: str, run_id: str, status: str, output_path: str | None=None, progress: tuple[int, int] | None=None, error: str | None=None) -> None`

结束某次运行：写入 status/finished_at/output_path（可选 error）。

status 取 success/failed/cancelled 等；output_path 为该次执行的
主产物路径（如 print.pdf、rembg 输出目录），供历史面板回链。
任务目录已删除时静默跳过。

progress 为 (done, total)，用于补齐最终计数。worker 的 finished 事件
不再携带 done/total（进度由结构化 progress 事件实时汇报），因此调用方
传入「最近一次进度」即可让历史记录落到真实完成数，而不是停在中间值。

error 为失败原因（退出码 / worker 的最后一行错误 / "子进程启动失败"）。
⚠️ 必须落盘：worker 起不来的那类失败**没有任何输出**，界面上只有一条
转瞬即逝的 toast，记录里若也只有 ``done=0 total=0``，事后就彻底查不出
原因（用户报「提交失败但没说为什么」，只能靠猜）。

##### `all_stage_runs(task_id: str) -> dict[str, list[dict]]`

整份运行历史（**一次读盘**），键为阶段名、值为最新在前的记录列表。

给"跨阶段比对时间戳"这类一次要看全的场景用：逐个 ``list_stage_runs()``
会把整份 runs.json 读 N 遍（任务多跑过几次就有几十上百 KB）。

##### `stage_states(task_id: str) -> dict[str, dict]`

每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。

``status/done/total`` 取自最近一次运行；``completed`` 表示该阶段历史上
是否成功执行过——重试失败不应把已经产出结果的步骤变回未完成。

---

## `desktop.store.store`

源码：[`desktop/store/store.py`](../../desktop/store/store.py)

TaskStore：任务、阶段、页面标注的统一文件存储入口。

### `class TaskStore(TaskMixin, RunMixin, PageManifestMixin, AnnotationMixin, DraftMixin)`

唯一数据入口：组合任务/运行/页面/标注/暂存五个 Mixin，统一读写文件存储。

数据根目录下含 tasks/（每任务一子目录）及各 JSON 清单
（tasks.json/runs.json/boxes.json/sizes.json/pages.json/print.json）；
每任务目录下另有 drafts/<阶段>.json（用户改过但未执行的参数暂存）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(root: Path \| None=None)` | 初始化数据根。 |

##### `__init__(root: Path | None=None)`

初始化数据根。

root 省略时默认用 guji_data_dir()（~/Documents/guji）；传入自定义
root 主要用于测试隔离。构造时只确保 tasks/ 存在——存储一直是纯
JSON 文件，没有旧数据（SQLite）需要迁移。

---

## `desktop.store.tasks`

源码：[`desktop/store/tasks.py`](../../desktop/store/tasks.py)

任务索引（tasks.json）与任务目录布局。

### `class TaskMixin`

任务索引读写与任务目录/阶段输出目录的路径推导。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `find_tasks(source_hash: str) -> list[dict]` | 按源文件指纹查重，返回全部命中的任务记录（可能多条）。 |
| `list_tasks() -> list[dict]` | 全部任务，按 updated_at 倒序（最近改动的排在前面）。 |
| `get_task(task_id: str) -> dict \| None` | 按任务号取任务记录；不存在返回 None。 |
| `create_task(source_path: Path, source_hash: str, name: str, duplicate_confirmed: bool=False) -> str` | 新建任务并返回任务号（四位零填充）。 |
| `update_task(task_id: str, status: str) -> None` | 更新任务状态与 updated_at；任务号不存在时静默忽略。 |
| `delete_task(task_id: str) -> bool` | 删除任务及其中间产物，返回是否真的删掉。 |
| `task_dir(task_id: str) -> Path` | 任务根目录：tasks/<任务号>。 |
| `stage_dir(task_id: str, stage: str) -> Path` | 某阶段的输出目录：tasks/<任务号>/stages/<阶段>。 |
| `extract_output_dir(task_id: str) -> Path` | 提取图片直接位于 stages/extract（无 PDF 名/嵌套子目录）。 |
| `rembg_output_dir(task_id: str) -> Path` | 步骤三最终图片目录（「提交本次任务」产出，print 阶段从此取图）。 |
| `rembg_preview_output_dir(task_id: str) -> Path` | 「生成预览」产出的整页去底预览图目录（中间产物，不参与 print）。 |
| `print_output_pdf(task_id: str) -> Path` | print 阶段产物 print.pdf 的完整路径。 |
| `stage_output_dir(task_id: str, stage: str) -> Path` | 返回某阶段（GUI）应写入的输出目录。 |
| `workset_dir(task_id: str) -> Path` | 已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。 |
| `runs_config_dir(task_id: str) -> Path` | 子进程执行配置（run-*.json / detect-config.json）。 |
| `source_thumbnails_dir(task_id: str) -> Path` | 源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。 |
| `rembg_thumbnails_dir(task_id: str) -> Path` | 第四步缩略图缓存：提交阶段（rembg_submit）随最终图片一并生成， |
| `copy_source_to_task(task_id: str, source_path: Path) -> Path` | 导入时在任务目录下保留一份源文件副本（原子落地）。 |
| `source_copy_path(task_id: str) -> Path \| None` | 任务目录里的 PDF 备份路径；没有备份返回 None。 |
| `ensure_source_copy(task_id: str) -> Path \| None` | 保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。 |

##### `create_task(source_path: Path, source_hash: str, name: str, duplicate_confirmed: bool=False) -> str`

新建任务并返回任务号（四位零填充）。

任务号取当前最大号 +1，同时参考索引与磁盘目录；若两者不一致导致号被
占用则继续顺延。创建时会预建 stages/runs/thumbnails/source
子目录，但不复制源文件（由 copy_source_to_task 负责）。

⚠️ **取号靠"目录创建的原子性"，不靠"先查后建"**（2026-09-26 审计）：
单例守卫是**按构建目录**判定的，开发版与安装版会同时运行、共用同一个
数据目录（`desktop/single_instance.py` 明说了）。两个进程会算出同一个
`_next_task_no()`、同时通过"号没被占用"的检查 → 拿到同一个任务号、
写同一个目录、索引里互相覆盖（一个任务凭空消失）。
`mkdir(exist_ok=False)` 在文件系统层是原子的：抢不到就顺延取号。

##### `delete_task(task_id: str) -> bool`

删除任务及其中间产物，返回是否真的删掉。

⚠️ 顺序是「**先删目录、成功才删索引**」：反过来的话目录一旦被占用
没删掉、索引却先没了，任务目录就变成没人认领的孤儿，用户还看不见。

⚠️ Windows 上 PDF 被后台渲染线程打开时 ``rmtree`` 抛 PermissionError，
原先 ``ignore_errors=True`` 会让它**静默残留**——列表里显示已删除，
磁盘上目录还在。这里重试若干次再判定失败，失败时保留任务让用户重试。

##### `task_dir(task_id: str) -> Path`

任务根目录：tasks/<任务号>。

⚠️ **必须校验形状**（2026-09-26 审计）：`task_id` 会被直接拼进路径，而
`delete_task` 对它做 `rmtree`。`tasks.json` 就在用户的文档目录下、可被
外部编辑或别的工具写坏，一旦出现 `"id": "..\..\somewhere"` 就会
**越界删除任务目录之外的东西**。这里只认 `create_task` 生成的形状。

##### `stage_output_dir(task_id: str, stage: str) -> Path`

返回某阶段（GUI）应写入的输出目录。

注意 rembg 阶段返回 rembgpreview 预览目录，rembg_submit 才指向
rembg 最终目录；print 返回 print.pdf 所在目录。

##### `workset_dir(task_id: str) -> Path`

已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。

仅为清理历史遗留目录保留（老版本任务目录下可能仍有 workset/）。

##### `rembg_thumbnails_dir(task_id: str) -> Path`

第四步缩略图缓存：提交阶段（rembg_submit）随最终图片一并生成，
缩略条直接复用，不必每次现解码 6000px 的原图。

##### `copy_source_to_task(task_id: str, source_path: Path) -> Path`

导入时在任务目录下保留一份源文件副本（原子落地）。

⚠️ 复制本身可能是在**后台线程**里做的（见
``desktop/workers/serial_jobs.py``），而详情页/预览随时会来读这份
副本，所以走 ``copy_file_atomic``：写 ``.part`` 再 ``os.replace``，
别人不会读到半截 PDF。

##### `source_copy_path(task_id: str) -> Path | None`

任务目录里的 PDF 备份路径；没有备份返回 None。

⚠️ 后续所有操作（详情页预览、extract 入参…）**都必须用它**，不能用
``task['source_path']``：源文件在用户磁盘上，会被移动/改名/删除，
一走就「渲染失败」。备份随任务走，任务才是自包含的。

##### `ensure_source_copy(task_id: str) -> Path | None`

保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。

老任务（导入时复制失败）或备份被误删时靠它自愈；源也一起没了就
返回 None，调用方负责提示。

---

## `desktop.ui.font_setup`

源码：[`desktop/ui/font_setup.py`](../../desktop/ui/font_setup.py)

缺中文字体时的启动引导：体检 → 一键从软件源安装 → 失败给手装命令。

为什么必须是"阻塞式引导"而不是一句 warning：缺中文字体时 PDF 里的标题、
页码会静默退回 Helvetica，检测框标注退回 ASCII 的 ``L``/``R``/``U``——
**产物已经错了，而流程一路绿灯**。与其让用户加工到第四步才发现汉字是方块，
不如在进门前把话说清楚。

分工严格遵守分层：

- 「有没有字体、该装哪个包、失败算网络还是权限」全部在
  ``utils.font_setup``（纯标准库，可自测、可命令行复用）；
- 本模块只管 **Qt 外壳**：体检结果要不要弹窗、按钮状态、流式日志、用户勾选
  "以后不提示"。判断逻辑一行都不在这里。

线程：安装要跑 apt/dnf 并可能弹系统的 pkexec 授权框，必须进子线程，
否则界面卡死；日志与结果都通过 **绑到本对话框方法**的信号回到主线程
（跨线程自动排队，不需要 connect_queued 中继——接收者是主线程的 QObject）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| SKIP_ENV | `"GUJI_SKIP_FONT_CHECK"` |
| _SETTINGS_KEY | `"fontCheck/skip"` |
| _MONO_FONT | `"Consolas, 'Courier New', monospace"` |

### `class FontInstallWorker(QThread)`

子线程里跑 `install_cjk_fonts`，把输出逐行抛回主线程。

单独一个类的原因：`utils.font_setup.install_cjk_fonts` 里会有 pkexec
授权框阻塞十几秒到几分钟（`fonts-noto-cjk` 有上百 MB），放进主线程会
直接把窗口画成"未响应"。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(packages=None, parent=None)` | — |
| `run() -> None` | — |

### `class FontFixDialog(QDialog)`

缺字体引导框：自动安装 / 复制手装命令 / 暂时跳过。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(plan, parent=None)` | plan 是 `utils.font_setup.install_plan()` 的候选（可能为空 = 无法自动装）。 |
| `closeEvent(event) -> None` | 关窗前先停掉还在跑的安装线程，避免子进程变成孤儿。 |
| `installed() -> bool` | 本次会话里是否真的装上了中文字体。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `font_check_suppressed() -> bool` | 用户是否勾过「不再提示」。 |
| `reset_font_check() -> None` | 清掉「不再提示」，下次启动重新体检（自测 / 排错用）。 |
| `ensure_cjk_fonts(parent=None) -> bool` | 启动体检：没有中文字体就弹引导框。 |

#### `ensure_cjk_fonts(parent=None) -> bool`

启动体检：没有中文字体就弹引导框。

正常情况（Windows、装了中文字体的 Linux）会**立刻静默返回 True**；
``GUJI_SKIP_FONT_CHECK=1`` 可整体跳过（打包冒烟与 GUI 自测）。

---

## `desktop.ui.fonts`

源码：[`desktop/ui/fonts.py`](../../desktop/ui/fonts.py)

界面字体：统一的字体族解析与构造。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）。
`ui_font` 跟「控件」没什么关系，却被日志面板、分段开关等多处共用；留在
widgets 里会让 `segmented_toggle` 反向 import widgets，形成循环导入。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _FONT_FAMILY | `None` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `ui_font(size: int=T.SIZE_BODY, bold: bool=False) -> QFont` | 统一的界面字体（族名 + 像素字号）。 |

#### `ui_font(size: int=T.SIZE_BODY, bold: bool=False) -> QFont`

统一的界面字体（族名 + 像素字号）。

族名走 ``resolve_font_family()`` 解析出的系统实际字体，与
``apply_app_style`` 给整个应用设置的字体保持一致；否则在没有
``Microsoft YaHei UI`` 的机器上，这些控件会各自回退到默认字体，
和应用其它文字对不上。

---

## `desktop.ui.help_dialog`

源码：[`desktop/ui/help_dialog.py`](../../desktop/ui/help_dialog.py)

用户手册：Markdown → HTML → 系统默认浏览器渲染。

为什么不再用 ``QTextBrowser`` / ``QTextDocument`` 直接渲染 Markdown：

- Qt 的 ``setMarkdown()`` 只支持 GFM 的**子集**，表格、围栏代码块、深层嵌套
  列表的渲染都很勉强，长文档读起来发闷；
- ``setHtml()`` 走的是**同一条富文本引擎**，CSS 只是 HTML 的一个小子集
  （没有 flex、没有伪元素、 ``nth-child`` 之类选择器也不全），多绕一圈
  换不来真正的样式自由度；
- ``QWebEngineView`` 能彻底解决，但会拖进 ``QtWebEngineProcess.exe`` 与
  百 MB 级资源包，和 ``guji.spec`` 现有的 excludes 裁剪策略直接冲突。

于是走第三条路：**用 Python 的 ``markdown`` 库（纯 Python、无二进制依赖）
把 ``docs/guide/*.md`` 转成完整 HTML，内嵌匹配应用主题的 CSS，交给系统默认
浏览器打开。**

**两条路，按模式分流**（判据见 ``prefer_static_manual``，是"打包与否"而不是
"文件在不在"）：

| 模式 | 手册来源 | 截图 | 何时用 |
| --- | --- | --- | --- |
| 开发（源码运行） | 每次现渲染到 %TEMP% | 绝对 ``file://`` URL | md 随时在改，改完立刻可见 |
| 打包（生产） | 构建期预生成的 ``desktop/static/manual.html`` | **内联 data URI** | 内容已定死，点开即用 |

生产侧预生成是必须的，不只是"快一点"：``docs/guide/`` 整目录**不进安装包**
（对最终用户无用的 md 与截图，白占体积），所以安装后既读不到 md、也找不到
截图——只有把手册连同截图压成一个自包含 HTML 放进包里才成立。

这样做的好处：

1. **零重量依赖** —— ``markdown`` 纯 Python 单包；且**只有构建环境需要它**，
   打包产物里已把它排除（运行时不渲染 md，缺了它也只是退化成占位提示）；
2. **完整 GFM** —— 表格、围栏代码块、嵌套列表都按规范渲染；
3. **图片永远不碎** —— 开发靠 ``<base>`` 指回 ``docs/guide/``，生产靠内联，
   两种模式都不存在"相对路径解析错"的可能；
4. **样式自由** —— 真实浏览器渲染，CSS 不受 Qt 富文本子集限制；
5. **性能与产物一致** —— 生产端点开就是浏览器那一下，没有首次渲染延迟，
   也不再有"临时文件堆积 + 防缓存文件名"那套绕法。

三条关键实现约束（改动时别踩）：

- **开发模式的 ``<base>`` 必须指向手册目录且带结尾斜杠**：HTML 落在临时目录，
  不设 base 就会把 ``screenshots/guide/*.png`` 解析成碎图；
- **指南之间的互链要改成页内 tab 跳转**：``user-guide.md`` 里有
  ``[cli.md]\(cli.md)``，浏览器会把 .md 当纯文本显示，必须改写为
  ``#tab-cli`` 交给 JS 切页；
- **打开时只把「原生路径」交给系统，绝不传 ``file:///`` URI**：见
  ``_open_with_system`` 的注释，这是「点了按钮没反应」的元凶。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _HTML_PREFIX | `"guji_manual_"` |
| _KEEP_RECENT | `3` |
| STATIC_MANUAL_NAME | `"manual.html"` |
| _JS | `" (function () {   const tocNav = document.getElementById(…"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `manual_dir() -> Path` | 手册目录（源码与打包两种模式下都可用）。 |
| `static_manual_path() -> Path` | 构建期预生成的自包含手册路径（**只有打包版才有**；可能不存在）。 |
| `prefer_static_manual() -> bool` | 当前是否该走「构建期静态手册」这条路。 |
| `generate_manual_html(entry: str \| None=None) -> Path` | 把手册渲染成一个带分段开关的 HTML 文件（临时目录），返回其路径。 |
| `generate_static_manual(output_path: Path \| None=None) -> Path` | **构建期**把手册渲染成单个自包含 HTML（默认 ``desktop/static/manual.html``）。 |
| `open_manual(entry: str \| None=None) -> Path` | 打开用户手册，返回被打开的 HTML 路径。 |

#### `manual_dir() -> Path`

手册目录（源码与打包两种模式下都可用）。

与 ``package_dir()`` 同源：源码模式下 ``desktop/`` 的上一级就是仓库根，
打包后数据文件由 ``guji.spec`` 的 ``gui_datas`` 落到 ``_internal/``，
``package_dir()`` 在 frozen 下返回 ``_MEIPASS/desktop``，再上一级同样是
资源根，因此 ``package_dir().parent / "docs" / "guide"`` 两种模式通用。

#### `prefer_static_manual() -> bool`

当前是否该走「构建期静态手册」这条路。

判据是**打包与否（frozen）**，不是「静态文件在不在」：

- 开发模式：``docs/guide/*.md`` 随时在改，必须每次现渲染，改完立刻能看到
  效果；若按「文件存在」判断，仓库里哪天留了一个 ``manual.html``（手动生成
  过一次、或从安装包里拷回来的），开发者就会一直看到旧内容；
- 生产模式（PyInstaller 打包后）：手册内容在构建那一刻就定死了，直接打开
  预生成的静态 HTML，不渲染、不写临时文件。

``GUJI_MANUAL_STATIC=1`` / ``=0`` 可强制指定，供冒烟与自测用。

#### `generate_manual_html(entry: str | None=None) -> Path`

把手册渲染成一个带分段开关的 HTML 文件（临时目录），返回其路径。

entry 为 ``MANUAL_ENTRIES`` 里的键，决定默认激活哪个标签页；
不传则激活第一项。**这是打包版用不到的老路**：打包版读
``docs/guide/manual.html``（见 ``generate_static_manual``），只有源码模式
（没有静态文件）才现渲染到这里。

⚠️ ``<base>`` 指向手册目录（带结尾斜杠）是图片能加载的唯一保证：
Markdown 里写的是 ``screenshots/guide/xxx.png`` 这样的相对路径，
而 HTML 落在临时目录，不设 base 就会相对临时目录解析成碎图。

#### `generate_static_manual(output_path: Path | None=None) -> Path`

**构建期**把手册渲染成单个自包含 HTML（默认 ``desktop/static/manual.html``）。

打包版点「用户手册」时直接打开这个文件：不渲染 md、不读截图、不写临时文件。
自包含（截图内联成 data URI）是硬要求——``docs/guide/`` 整目录**不进安装包**，
安装后既没有 md 也没有 screenshots，任何外部引用都会变成碎图。

⚠️ 源码模式下调用**务必传 ``output_path``**（写进待打包目录），别默认写到
``desktop/static/manual.html``——那个位置会被打包版优先打开，万一留在仓库里
容易让人以为改了 md 就生效（实际必须重新打包）。

#### `open_manual(entry: str | None=None) -> Path`

打开用户手册，返回被打开的 HTML 路径。

**按模式分流**（见 ``prefer_static_manual``）：

- 打包版（frozen）：直接打开构建期预生成的 ``docs/guide/manual.html``——
  不渲染、不写临时文件，点下去就只剩开浏览器那一下；万一产物里没有这个
  文件（老包 / 构建步骤没跑到），退回现渲染，功能不受影响；
- 开发模式：**一律现渲染**到临时目录，改完 md 立刻看到新内容，不会被仓库里
  可能存在的旧静态文件顶掉。

返回路径是为了调用方（或测试）能拿到产物做进一步处理。
打不开浏览器时不抛异常——手册文件仍然在，用户可以手动打开，
界面上会弹一个带路径的提示框。

⚠️ 不要给 URL 加 ``?v=<时间戳>`` 去防缓存：Windows 上最终还是要走系统 shell，
查询串会被当成路径的一部分，实测地址栏里根本不出现。临时文件靠**文件名本身
带时间戳**（见 ``_HTML_PREFIX``）保证 URL 唯一；静态文件靠"重装即替换"。

⚠️ 不要把 ``html_path.as_uri()`` 直接丢给系统（见 ``_open_with_system``）。

---

## `desktop.ui.icons`

源码：[`desktop/ui/icons.py`](../../desktop/ui/icons.py)

自定义矢量图标：补 qfluentwidgets 内置图标里没有的图形（带圆圈的问号）。

为什么不能直接继承 ``FluentIconBase`` 了事
----------------------------------------
``FluentIcon.path()`` 返回的是 **Qt 资源里的文件路径**
``:/qfluentwidgets/images/icons/Xxx_black.svg``，基类两条渲染链都靠
``path.endswith('.svg')`` 判断「是文件还是源码」：

* ``FluentIconBase.icon()``：只有 ``path.endswith('.svg') and color`` 时才包
  ``SvgIconEngine``，否则 ``QIcon(path)`` —— 把 SVG **源码字符串** 当文件名，
  得到一个空图标；
* ``FluentIconBase.render()``：只有 ``endswith('.svg')`` 时才 ``drawSvgIcon``
  （内存渲染），否则同样按文件走 ``QIcon(path).pixmap()``。

所以自绘 SVG 必须 **两个方法都重写**：只重写 ``icon()`` 的话，按钮自绘走的是
``paintEvent → _drawIcon → render()``，而 ``PushButton.paintEvent`` 在
``icon().isNull()`` 时直接 return，结果就是「只剩文字、图标不见了」。

几何
----
24×24 视图，外圈直径与内置 ``INFO`` 图标一致（几乎满幅，r=10、描边 1.6），
问号高度 ~12（与 INFO 里 ``i`` 的高度相当），整体上下居中，不出现内置
``HELP`` / ``QUESTION`` 那种被裁到边框上的偏移。

### 模块常量

| 名称 | 值 |
| --- | --- |
| QUESTION_CIRCLE | `"<svg xmlns="http://www.w3.org/2000/svg" width="24" height…"` |

### `class SvgIcon(FluentIconBase)`

用**内存里的 SVG 源码**造图标（内置 FluentIcon 没有的图形）。

模板里用 ``{c}`` 占位颜色，由 ``getIconColor(theme)``（black/white）或
调用方显式给的 ``color`` 填入；深浅色主题自动跟随。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(template: str)` | — |
| `path(theme: Theme=Theme.AUTO) -> str` | 返回填好颜色的 SVG 源码（不是文件路径）。 |
| `icon(theme: Theme=Theme.AUTO, color: QColor \| str \| None=None) -> QIcon` | 包成 ``QIcon``：必须走 ``SvgIconEngine``，否则得到空图标。 |
| `render(painter, rect, theme: Theme=Theme.AUTO, indexes=None, **attributes) -> None` | 自绘入口（按钮/菜单走这条）：直接把源码交给 ``QSvgRenderer``。 |

### `class CustomIcon`

自定义图标集合：用法与 ``FluentIcon`` 一致（直接传给按钮等控件）。

---

## `desktop.ui.segmented_toggle`

源码：[`desktop/ui/segmented_toggle.py`](../../desktop/ui/segmented_toggle.py)

分段开关控件：一行内互斥选择几个视图形态。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）——
它独占 170 行，且只被「去底色结果 / 原图」这类视图切换用到，与 widgets 里
其余通用控件不是一回事。

原 widgets.py 仍 re-export 本类，调用点无需改动。

### `class SegmentedToggle(QWidget)`

分段开关：一行内互斥选择几个视图形态。

用于「去底色结果 / 原图」这类同一视图的形态切换。自绘而非用
qfluentwidgets 的 ``SegmentedWidget``——后者是给页面导航设计的
（底部指示条、无法单独禁用某一项），而这里需要「还没有去底色结果时
禁用其中一项」的语义。

**选中态要一眼看得出**，所以三处一起给对比度（只靠白底滑块是不够的，
浅底卡片上白滑块几乎看不出来）：

- 轨道用 ``SURFACE_SUNKEN``（比 ``SURFACE_SOFT`` 明显重一档的灰底），
  白滑块压在上面才有边界；
- 选中项文字用主色 ``ACCENT`` 且加粗，未选中项用 ``INK_SOFT``；
- 禁用项转 ``INK_DISABLED``，比「未选中但可用」再淡一档，不会混淆。

只有用户点击才发 ``current_changed``；``set_current`` 是程序化切换，
不发信号（否则回流切换会自我递归）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(items: Sequence[Sequence[str]], parent=None)` | items 为 ``[(键, 文案), ...]``，默认选中第一项。 |
| `current() -> str` | 当前选中项的键。 |
| `set_current(key: str) -> None` | 程序化切换选中项，不发 ``current_changed``。 |
| `set_item_enabled(key: str, enabled: bool) -> None` | 启用/禁用某一项；禁用项不可悬停、不可点击，文案变灰。 |
| `is_item_enabled(key: str) -> bool` | 某一项当前是否可用。 |
| `sizeHint() -> QSize` | Qt 覆写：建议尺寸。 |
| `minimumSizeHint() -> QSize` | Qt 覆写：最小建议尺寸。 |
| `mouseMoveEvent(event) -> None` | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。 |
| `leaveEvent(event) -> None` | Qt 事件覆写：鼠标移出时恢复常态。 |
| `mousePressEvent(event) -> None` | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

---

## `desktop.ui.style`

源码：[`desktop/ui/style.py`](../../desktop/ui/style.py)

应用级外观设置：字体、主题色、全局样式表。

只覆盖三类东西，其余交给 qfluentwidgets 自己的绘制，避免和它的
代理/动画打架：

1. 全局字体（中文优先，Windows/Linux 都有回退）；
2. 窗口底色与滚动条：默认的浅灰偏冷、滚动条过粗；
3. 少数原生控件（表格）的描边与圆角。

注意：日志文本域（`#logView`）的样式**不在**这里——qfluentwidgets 的
`TextEdit` 构造时会给控件自身设样式表，控件级优先级高于应用级，写在全局
QSS 里不会生效；它由 `desktop.components.log_panel.apply_log_view_style`
在控件上设置。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `resolve_font_family() -> str` | 挑一个系统里存在的中文字体族，避免落到无衬线默认字体。 |
| `apply_app_style(app) -> None` | 统一字体/主题色/全局样式（在创建主窗口前调用）。 |
| `global_stylesheet() -> str` | 生成应用全局样式表（底色 / 滚动条 / 表格边框）。 |

#### `global_stylesheet() -> str`

生成应用全局样式表（底色 / 滚动条 / 表格边框）。

只给窗口与 #pageRoot 上色，避免把嵌套的 QStackedWidget 刷灰；其余外观
交给 qfluentwidgets 自绘，不与它的代理/动画打架。字体族不在这里设，
由 ``apply_app_style`` 通过 ``app.setFont`` 统一指定。

---

## `desktop.ui.theme`

源码：[`desktop/ui/theme.py`](../../desktop/ui/theme.py)

界面设计令牌：颜色、间距、圆角、字号。

全应用只在这里定义视觉常量，页面/组件一律引用这里的名字，避免出现
"这里 #E5E9F0、那里 #EEF1F4" 的散落色值。换算关系（Fluent 基准）:

- 间距按 4 的倍数：XS=4 / SM=8 / MD=12 / LG=16 / XL=24
- 圆角三档：控件 6、卡片 10、大容器 14
- 文本三级：正文 INK、次要 INK_SOFT、辅助/占位 INK_FAINT

### 模块常量

| 名称 | 值 |
| --- | --- |
| INK | `"#1A1D21"` |
| INK_SOFT | `"#4E5862"` |
| INK_FAINT | `"#8B949D"` |
| INK_DISABLED | `"#B7BEC5"` |
| CANVAS | `"#F3F5F7"` |
| SURFACE | `"#FFFFFF"` |
| SURFACE_SOFT | `"#F7F9FB"` |
| SURFACE_HOVER | `"#EEF3F6"` |
| SURFACE_SUNKEN | `"#E4EAEF"` |
| BORDER | `"#E2E7EC"` |
| BORDER_SOFT | `"#EDF1F4"` |
| BORDER_STRONG | `"#C9D1D8"` |
| ACCENT | `"#0E7C8B"` |
| ACCENT_HOVER | `"#0B6A77"` |
| ACCENT_SOFT | `"#E6F2F4"` |
| SUCCESS | `"#0F7B3F"` |
| SUCCESS_SOFT | `"#E7F4EC"` |
| WARNING | `"#B9760A"` |
| WARNING_SOFT | `"#FBF2E2"` |
| DANGER | `"#C93A3A"` |
| DANGER_HOVER | `"#B03333"` |
| DANGER_PRESSED | `"#962B2B"` |
| DANGER_SOFT | `"#FBEAEA"` |
| NEUTRAL | `"#7A838C"` |
| NEUTRAL_SOFT | `"#EFF2F4"` |
| SPACE_XS | `4` |
| SPACE_SM | `8` |
| SPACE_MD | `12` |
| SPACE_LG | `16` |
| SPACE_XL | `24` |
| RADIUS_SM | `6` |
| RADIUS_MD | `10` |
| RADIUS_LG | `14` |
| SCROLLBAR_WIDTH | `10` |
| SCROLLBAR_MARGIN | `2` |
| SIZE_CAPTION | `12` |
| SIZE_BODY | `13` |
| SIZE_LABEL | `14` |
| SIZE_SUBTITLE | `16` |
| SIZE_TITLE | `22` |
| SIZE_HERO | `26` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `status_colors(status: str) -> tuple[str, str]` | 状态 → (前景色, 底色)，未知状态按未执行处理。 |
| `status_label(status: str) -> str` | 状态键 → 中文短标签，未知或空状态回退到"未知"。 |

#### `status_label(status: str) -> str`

状态键 → 中文短标签，未知或空状态回退到"未知"。

取值来自 STATUS_LABELS（如 "running"→"执行中"）。

---

## `desktop.ui.widgets`

源码：[`desktop/ui/widgets.py`](../../desktop/ui/widgets.py)

基础视觉控件：卡片、分区标题、状态胶囊、空状态、页头。

统一用自绘而非样式表：Qt 的样式表引擎会在子树里有任何 ``setStyleSheet``
时把 QFrame 底色刷成白色，之前步骤条的卡片底就因此被整片盖掉过。自绘
（``paintEvent``）不受此影响，颜色完全可控，也不会污染子控件。

表单控件则相反，一律用 qfluentwidgets 的现成控件（它们自带绘制与焦点
动画），只把高度对齐到 ``CONTROL_HEIGHT``——见 ``combo_box()``。

### 模块常量

| 名称 | 值 |
| --- | --- |
| CONTROL_HEIGHT | `33` |

### `class Card(QFrame)`

白底圆角卡片，可选描边与内边距。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None, padding: int=T.SPACE_LG, spacing: int=T.SPACE_MD, radius: int=T.RADIUS_LG, fill: str=T.SURFACE, border: str=T.BORDER, layout: str='v')` | layout="v"/"h" 选择内部盒方向；padding 同时作为四边内边距。 |
| `set_colors(fill: str \| None=None, border: str \| None=None) -> None` | 改底色/描边后立即重绘；传 None 表示该项保持不变。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

##### `__init__(parent=None, padding: int=T.SPACE_LG, spacing: int=T.SPACE_MD, radius: int=T.RADIUS_LG, fill: str=T.SURFACE, border: str=T.BORDER, layout: str='v')`

layout="v"/"h" 选择内部盒方向；padding 同时作为四边内边距。

内部布局通过 ``self.box`` 暴露，调用方直接往里加控件。

### `class Divider(QFrame)`

1px 水平分隔线。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 固定高 1px、水平拉伸的水平分隔线。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class SectionTitle(QLabel)`

控制面板里的分组小标题（比正文略重，前面带一条主色短竖线）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(text: str, parent=None)` | 左侧预留 10px 给主色竖线，控件固定高 20px。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class StatusChip(QWidget)`

状态胶囊：圆点 + 文案 + 浅色底，用于表格里的阶段状态。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(text: str='', status: str='pending', parent=None)` | status 决定圆点与底色，取值见 theme.status_colors。 |
| `set_state(text: str, status: str) -> None` | 更新文案与状态色，并按新文案重算最小尺寸。 |
| `sizeHint() -> QSize` | Qt 覆写：建议尺寸。 |
| `minimumSizeHint() -> QSize` | Qt 覆写：最小建议尺寸。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class ProgressLine(QWidget)`

细进度条：圆角轨道 + 主色填充。

比 qfluent 的 ProgressBar 更克制（没有文字、没有内边距），
适合嵌在参数卡片里表示"这一步执行到多少页"。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None, height: int=6)` | height 为轨道像素高度（默认 6）。 |
| `setRange(minimum: int, maximum: int) -> None` | 设置上限，并把当前值夹到 [0, maximum]；上限为 0 时归零。 |
| `setValue(value: int) -> None` | 设置当前值（超出上限时夹到上限）。 |
| `value() -> int` | 当前值。 |
| `ratio() -> float` | 完成比例（0.0~1.0）；尚未设置上限时返回 0.0。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class Pill(QWidget)`

无圆点的文字胶囊（用于源文件名、计数等标签）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(text: str='', fg: str=T.INK_SOFT, bg: str=T.SURFACE_SOFT, parent=None)` | fg/bg 分别是文字色与胶囊底色。 |
| `setText(text: str) -> None` | 更新文案并按新文案重算宽度。 |
| `text() -> str` | 返回胶囊当前文案。 |
| `sizeHint() -> QSize` | Qt 覆写：建议尺寸。 |
| `minimumSizeHint() -> QSize` | Qt 覆写：最小建议尺寸。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class EmptyState(QWidget)`

浅色空状态：图标 + 主文案 + 补充说明 + 可选提示。

原先各预览控件用的是深灰底 + 白字占位，面积大且显得像报错；这里
统一成浅底 + 灰色图标 + 说明文字，和"还没有内容"的语义一致。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(text: str, hint: str='', icon=None, parent=None)` | icon 传 FluentIcon，会渲染成 44px 灰色图标；hint 为空时该行不占位。 |
| `set_text(text: str) -> None` | 更新主文案。 |
| `set_hint(hint: str) -> None` | 更新补充说明；传空串则隐藏该行。 |

### `class PageHeader(QWidget)`

页面头部：左侧标题 + 副标题，右侧操作区。

带一条底部分隔线，把页头和内容区分开——原来只有一行孤立的标题，
和下面的内容混在一起，层次不清。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(title: str, subtitle: str='', parent=None)` | 固定高 64px；右侧操作区通过 ``self.actions`` 布局添加按钮。 |
| `set_subtitle(text: str) -> None` | 设置副标题文案，空串则隐藏副标题行。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `apply_to(widget: QWidget, size: int=T.SIZE_BODY, bold: bool=False, color: str \| None=None) -> QLabel` | 给 QLabel 统一设置字体与颜色。 |
| `bold_button(button: QWidget, bold: bool) -> None` | 把按钮文字加粗 / 还原（高亮用）。 |
| `combo_box(items: Iterable[str \| Sequence[Any]] \| None=None, width: int \| None=None) -> ComboBox` | 创建与输入框同高的下拉框（统一表单的行高节奏）。 |
| `icon_pixmap(icon, size: int=24, color: str=T.INK_FAINT) -> QPixmap` | 把 FluentIcon 渲染成指定颜色的 pixmap（用于空状态插画）。 |
| `install_button_pointer_cursor(app: QApplication) -> None` | 给整个应用的按钮启用 hover 手型光标（见 :class:`_ButtonCursorFilter`）。 |

#### `apply_to(widget: QWidget, size: int=T.SIZE_BODY, bold: bool=False, color: str | None=None) -> QLabel`

给 QLabel 统一设置字体与颜色。

⚠️ **上色有两条路，按控件类型分流**：

- qfluentwidgets 的标签（``FluentLabelBase`` 子类：CaptionLabel / BodyLabel /
  StrongBodyLabel / TitleLabel / SubtitleLabel）**不读调色板**——它们用
  ``setStyleSheet("color: …")`` 自己画（``setTextColor``）。对它们只 ``setPalette``
  的话调色板里明明写着红色、**渲染出来仍是黑的**（2026-09-23 用户报「这个红色
  没有修改过来」就是这么来的）。所以必须走 ``setTextColor``。
- 原生 ``QLabel`` 仍走调色板（原来的做法；对它用样式表反而会牵连子控件，
  见模块头那段"样式表会把 QFrame 底色刷白"的教训）。

判据用 ``isinstance`` 而不是 ``hasattr(widget, "setTextColor")``：
``QTextEdit`` 也有同名方法，但它设的是"以后输入的文字颜色"，语义完全不同。

#### `bold_button(button: QWidget, bold: bool) -> None`

把按钮文字加粗 / 还原（高亮用）。

⚠️ **别用 ``setStyleSheet("…{font-weight:bold;}")`` 干这件事**：qfluentwidgets
给每个按钮的样式表是**整串 setStyleSheet 进去的**（约 7.6KB），里面有一条
``PushButton[hasIcon=true] { padding: 5px 12px 6px 36px; }`` —— 图标是
``paintEvent`` 手绘在左边 12px 处的，**全靠这 36px 左边距让居中的文字让开**。
整串替换后 padding 全没了，图标就画到文字上了（2026-09-23 用户报
「执行本子任务按钮中的图片显示在了文字上面」）。``setFont`` 只动字体，
不碰样式表；按钮 qss 里没有 ``font:`` 规则，所以控件字体生效。

#### `combo_box(items: Iterable[str | Sequence[Any]] | None=None, width: int | None=None) -> ComboBox`

创建与输入框同高的下拉框（统一表单的行高节奏）。

直接在表单里 ``ComboBox()`` 会比同列的 ``LineEdit``/``SafeSpinBox`` 矮
6px（见 ``CONTROL_HEIGHT`` 的说明），所以下拉框一律用本函数建。

``items`` 传字符串序列时只填显示文案；传 ``(文案, 值)`` 二元组序列时
值写进 ``itemData``，读出用 ``currentData()``。``width`` 非空则固定宽度
（用于节点行这类需要横向对齐的窄列）。

---

## `desktop.utils.files`

源码：[`desktop/utils/files.py`](../../desktop/utils/files.py)

文件与目录相关的通用工具：哈希、自然排序、阶段输出清单、预览缓存键。

### 模块常量

| 名称 | 值 |
| --- | --- |
| THUMBNAIL_EDGE | `256` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `guji_data_dir() -> Path` | GUI 数据根目录：用户文档目录下的 guji。 |
| `default_open_dir() -> Path` | 文件对话框的默认打开目录：用户文档目录。 |
| `project_root() -> Path` | 项目根目录（`desktop` 包的上一级）。 |
| `package_dir() -> Path` | `desktop` 包目录（源码与 PyInstaller 打包两种模式下都可用）。 |
| `file_hash(path: Path, chunk_size: int=1024 * 1024) -> str` | 流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。 |
| `copy_file_atomic(source: Path, target: Path) -> Path` | 把 source 复制到 target，**要么没有、要么完整**。 |
| `natural_key(name: str)` | 生成自然排序键：数字段按整数、其余转小写，使 2 排在 10 前。 |
| `list_stage_images(directory: Path) -> list[Path]` | 某阶段输出目录中的图片（自然排序）。 |

#### `default_open_dir() -> Path`

文件对话框的默认打开目录：用户文档目录。

QFileDialog 传空串会回退到进程工作目录（打包后就是程序所在目录），
入口落在安装/项目目录很不合适；统一改从文档目录起步。目录不存在时
回退到用户主目录，再不行返回空 Path 由调用方保持空串行为。

#### `project_root() -> Path`

项目根目录（`desktop` 包的上一级）。

源码模式下 worker 子进程用 `-m desktop.worker` 启动，工作目录必须是
能解析出 `desktop` 包的那一级；用本函数取，避免依赖某个文件的层数
（文件挪一层就会算错）。

#### `package_dir() -> Path`

`desktop` 包目录（源码与 PyInstaller 打包两种模式下都可用）。

打包后 `desktop` 作为 PYZ 内的字节码存档存在，磁盘上没有真正的
``desktop/static/icon.png``；数据文件由 spec 的 ``datas`` 额外落到
``_internal/desktop/``，因此 frozen 下直接指向 ``sys._MEIPASS``。

#### `copy_file_atomic(source: Path, target: Path) -> Path`

把 source 复制到 target，**要么没有、要么完整**。

⚠️ 不能用裸 ``shutil.copy2(source, target)``：导入后的复制是在**后台
线程**里跑的，而详情页/PDF 预览随时会来看任务目录里的副本。直接往
target 写，复制途中它就 ``is_file() == True`` 了，读到的却是半截
PDF——渲染失败、甚至静默出一张残缺页。

所以先写同目录的临时文件，落盘后再 ``os.replace`` 原子改名。临时名带
.part 后缀，``glob("*.pdf")`` 之类的兜底查找也扫不到它。

⚠️ 临时名里要带 **pid + 线程号**：同一个副本可能被两个地方同时复制
（后台队列复制中，用户已经点进详情页 → ``ensure_source_copy`` 又复制
一遍）。共用一个临时名的话两边会交叉写同一个文件；各自写自己的临时
文件则内容相同，谁最后 replace 都对。

---

## `desktop.utils.icon`

源码：[`desktop/utils/icon.py`](../../desktop/utils/icon.py)

窗口图标的圆角渲染。

图标的**形状由像素决定**——窗口标题栏/任务栏/Alt-Tab 都是 Windows 拿
Qt 给的位图去画，Qt 管不了圆不圆角。所以要在交给 ``setWindowIcon`` 之前
把源图裁成圆角，这样：

* 源图（``desktop/static/icon.png``）保持直角原图，**换图标不用手工修图**；
* 圆角比例只有一处定义（``ICON_RADIUS_RATIO``），与打包用的
  ``tools/make_icon.py::DEFAULT_RADIUS_PCT`` 保持一致；
* 同时往 QIcon 里塞多个尺寸帧——Windows 会按场景挑帧，避免它自己把
  295px 缩到 16px 时把圆角外的透明平均成半透明（浅色标题栏上会显出一圈淡边）。

### 模块常量

| 名称 | 值 |
| --- | --- |
| ICON_RADIUS_RATIO | `0.08` |
| MIN_CORNER_PX | `2.0` |
| _ALPHA_CUT | `140` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `effective_ratio(size: int, ratio: float=ICON_RADIUS_RATIO) -> float` | 按帧尺寸自适应圆角比例（16px 需 ~12.5% 才能真正裁掉四角）。 |
| `rounded_pixmap(source: QPixmap, size: int, ratio: float=ICON_RADIUS_RATIO) -> QPixmap` | 把源图等比居中裁成 ``size × size`` 的圆角图（圆角外透明）。 |
| `rounded_window_icon(path: Path \| str, ratio: float=ICON_RADIUS_RATIO) -> QIcon \| None` | 读取图片并生成圆角窗口图标；读取失败返回 None。 |

#### `rounded_window_icon(path: Path | str, ratio: float=ICON_RADIUS_RATIO) -> QIcon | None`

读取图片并生成圆角窗口图标；读取失败返回 None。

返回的 QIcon 内含 16~256 多帧，小帧已做 alpha 二值化。

---

## `desktop.worker`

源码：[`desktop/worker.py`](../../desktop/worker.py)

Process entry for one GUI stage task (worker 子进程统一入口)。

The worker emits JSON Lines on stdout so the GUI remains independent from
heavy libraries. 阶段执行器按职责拆分在 desktop/stages/ 包：

- desktop.stages.events        事件输出 + print 拦截/进度解析
- desktop.stages.detect_stage  detect（YOLO 文本框检测）
- desktop.stages.generic_stage 通用 CLI 阶段 + extract 渲染
- desktop.stages.print_stage   print（效果图合成 + 生成 PDF）
- desktop.stages.rembg_stage   rembg_submit（最终图片合成）

本文件只负责进程初始化与阶段路由。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `main() -> int` | GUI worker 子进程入口：读取 --config 并按阶段路由执行。 |

#### `main() -> int`

GUI worker 子进程入口：读取 --config 并按阶段路由执行。

--config 为必填，指向一个 JSON 文件路径，解析后按 mode/stage 字段分派到
对应阶段执行器（detect/extract/print/rembg_submit 等，未匹配则走通用
run_stage）。进程启动即启用 faulthandler 并统一 stdout/stderr 为 UTF-8，
以输出 JSON Lines 进度供 GUI 解析。返回阶段执行器的退出码。

⚠️ 启动期（读配置 / 解析 JSON / 路由之前）的异常一律转成 error 事件
+ stderr 堆栈，绝不让它变成"静默的退出码 1"（见 `_emit_fatal`）。
SystemExit 放行（argparse 的用法错误已经写到 stderr 了）。

---

## `desktop.workers.copy_source_worker`

源码：[`desktop/workers/copy_source_worker.py`](../../desktop/workers/copy_source_worker.py)

后台补一份源文件副本（**绝不在主线程复制**）。

背景：导入后台任务会顺手把源 PDF 复制进任务目录，之后一切都用副本
（源文件在用户磁盘上会被移动/改名/删除）。但两种情况副本会缺：

1. 导入时复制失败（磁盘满/权限）；
2. 早期版本导入的老任务，压根没做备份。

老实现是在详情页 `set_task()` 里**同步**调 `ensure_source_copy()` 补——
一本 800MB 的书就是主线程卡住几秒到几十秒（用户报「进详情页要等一会」）。
现在改成：先照常用源文件显示，**延时几秒**后如果副本还是没出现，再由这个
worker 在后台线程里补一份；补的期间界面照常可用。

### `class CopySourceWorker(QObject)`

把源 PDF 原子复制到任务目录（后台线程里跑）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(source: Path, target: Path)` | source 为源文件；target 为任务目录里的副本路径。 |
| `run() -> None` | 执行复制：失败只报 failed，不影响任务使用源文件继续干活。 |

### `class CopyFilesWorker(QObject)`

批量复制文件到目标目录（后台线程里跑；审计 D2）。

「插入图片」「下载 PDF」原先在主线程 `shutil.copy2`——一本 463MB 的 PDF
就把界面冻住整个复制时长。现在主线程只算好 (源, 目标) 对，这里逐对复制；
单个失败不中断整批（跳过并在结果里注明）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(jobs: list[tuple[Path, Path]])` | — |
| `run() -> None` | — |

---

## `desktop.workers.hash_worker`

源码：[`desktop/workers/hash_worker.py`](../../desktop/workers/hash_worker.py)

文件指纹（SHA-256）后台计算。

### `class HashWorker(QObject)`

后台计算单个文件 SHA-256 的 worker（QObject，运行于子线程）。

完成时发 finished(path, hash)，异常发 failed(message)；用于导入时
异步计算源文件指纹以做任务查重。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(path: Path)` | 待计算指纹的文件路径。 |
| `run() -> None` | 执行哈希计算并通过 finished 信号回报结果（异常走 failed）。 |

---

## `desktop.workers.image_list_worker`

源码：[`desktop/workers/image_list_worker.py`](../../desktop/workers/image_list_worker.py)

图片清单缩略图生成（用于阶段页面列表）。

### `class ImageListWorker(QObject)`

为一份图片路径清单生成缩略图（用于阶段页面列表）。

使用 QImageReader 的缩放解码，避免把原始分辨率扫描图整张解入内存。
effects 与 paths 对齐：非空时先按 area/border 规则合成效果再缩放
（用于 print 列表的效果预览）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(paths: list[Path], edge: int=96, effects: list \| None=None, crops: list \| None=None)` | 构造图片清单缩略图 worker。 |
| `run() -> None` | 逐图生成缩略图，发 thumbnail_ready(index, image, path)，结束发 completed。 |

##### `__init__(paths: list[Path], edge: int=96, effects: list | None=None, crops: list | None=None)`

构造图片清单缩略图 worker。

paths 为目标图片；edge 为缩略图最长边（默认 96）。effects/crops
与 paths 对齐：非空时先按 area/border 合成效果或按像素框裁剪，
再缩放到 edge（用于 print 列表效果预览）。

---

## `desktop.workers.preview_worker`

源码：[`desktop/workers/preview_worker.py`](../../desktop/workers/preview_worker.py)

PDF/图片渲染：整页大图、页缩略图（带磁盘缓存）与去底色效果合成。

区域合成（rembg 预览）在本线程内完成，避免主线程处理原始分辨率大图导致卡顿。

### 模块常量

| 名称 | 值 |
| --- | --- |
| PRINT_PREVIEW_TARGET_EDGE | `1600` |
| PRINT_PREVIEW_MIN_PX_PER_MM | `2.0` |
| PRINT_PREVIEW_MAX_PX_PER_MM | `8.0` |
| THUMB_YIELD_RATIO | `0.5` |
| _PDF_DOC_CACHE_MAX | `2` |

### `class PreviewWorker(QObject)`

渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(path: Path, page: int=0, longest_edge: int \| None=1200, thumbnails: bool=False, cache_dir: Path \| None=None, effect: dict \| None=None, print_spec: dict \| None=None, render_missing: bool=True, pages: list[int] \| None=None)` | 构造预览渲染 worker。 |
| `cancel() -> None` | 请求中止。 |
| `run() -> None` | 按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。 |

##### `__init__(path: Path, page: int=0, longest_edge: int | None=1200, thumbnails: bool=False, cache_dir: Path | None=None, effect: dict | None=None, print_spec: dict | None=None, render_missing: bool=True, pages: list[int] | None=None)`

构造预览渲染 worker。

PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
effect 为去底色合成参数 {boxes, area, border}，仅对单图生效。
print_spec 为第四步「打印效果」参数
{"args": print 参数, "index": 0-based 页序, "total": 总页数, "name": 文件名}，
非空时把图片按 utils.page_layout 的几何排进一张纸（仅内存，不落盘）；
另可给 "target_edge"：按该边长反推像素密度**重新排版**（标题/页码是
重新绘制的，放到 4000px 依然锐利）。⚠️ 这个密度应当**高于屏幕需求**
（超采样）——Qt 一次大比例缩小的质量明显差于分两档温和缩放，实测
「合成 3000px」的锐度接近理论理想，而「合成 = 显示尺寸」反而最糊。
密度的上限由 compose_print_page 夹住（不超过源图原生密度）。
⚠️ 给了 target_edge 时，longest_edge 应传 0（画布已按该密度合成，
再缩一次纯粹白扔细节）。

`render_missing=False`：**只读缓存，不渲染缺页**。给「另一个生产者
正在填这个缓存目录」的场景用（导入后台任务在逐页写缩略图）——两边
各跑一遍全量渲染等于把工作量翻倍，而且两个 PyMuPDF 循环会互相抢
GIL，界面直接冻住（2026-09-25 实测）。
`pages`：只处理这些页（None = 全部）；配合 render_missing=False 就是
「只把我还没有的那几页从缓存里读出来」。

##### `cancel() -> None`

请求中止。

批量缩略图（整本几百上千页）会在**下一页开头**退出——已经渲好的页都已
落盘，重进会命中缓存，不会白干。单页渲染不可中断（一次 get_pixmap
只有 ~160ms，等它一下比打断安全）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `region_canvas_specs(image_size: tuple[int, int], boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list` | compose_region_output 的**纯几何**部分：返回 ``[(画布尺寸, sources)]``。 |
| `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list` | 按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。 |
| `close_cached_documents() -> None` | 关掉共享文档缓存里的全部文档，释放 Windows 文件句柄。 |
| `preview_px_per_mm(page_w_mm: float, page_h_mm: float, target_edge: int=PRINT_PREVIEW_TARGET_EDGE) -> float` | 按纸张尺寸给出效果预览的像素密度（px/mm）。 |
| `qt_family_for_file(path: str) -> str \| None` | 按**字体文件**加载并取回 Qt 族名；失败返回 None。 |
| `preview_text_font(spec, px_per_mm: float) -> QFont` | 按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。 |
| `compose_print_page(image: QImage, plan, px_per_mm: float \| None=None) -> QImage` | 按 ``utils.page_layout.PrintPagePlan`` 合成"打印效果"位图。 |
| `compose_outputs_horizontal(outputs: list, gap: int=12) -> QImage` | 多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。 |

#### `region_canvas_specs(image_size: tuple[int, int], boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list`

compose_region_output 的**纯几何**部分：返回 ``[(画布尺寸, sources)]``。

不碰位图——只依据图片**尺寸**（QImageReader 读文件头即可拿到）就能
算出每张输出画布的大小与贴图来源。第三步提交据此**预先算好输出
文件名**（张数 × 名称），再并行处理各页；规则仍然只有这一份。

``full=True`` 表示这一页是整幅内容(fullcontent)。整幅页整页只有一个内容区，
area 1/2/3 对「怎么分栏/怎么合并」的规则都不适用，因此这里把它的框**归一并
整页**（`utils.box_geometry.whole_page_box`）——于是整幅页在 area 1/2/3/4 下
行为一致，都等价 area=4（整页）；既不做对称镜像，也不紧裁掉页边。
调用方通常直接传 ``is_full_content(原始槽位列表)`` 的结果。

#### `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list`

按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

**几何规则来自 utils.box_geometry**（与 functions/text_region.py 的 CLI
输出共用同一份实现），本函数只负责用 QImage 把布局画出来——这样规则
不会因数像素后端不同而被复制成两份。几何部分见 `region_canvas_specs`。

与原实现的一处行为修正：area=3 + 双框 + border=None 时，并集区域现在
**写回原位置**（此前被搬到画布左上角）。规格见
docs/functions/cropremove.md:57「area=3 → 单图，ROI 写回原位置」。

``full`` 语义见 `region_canvas_specs`（整幅页内容区＝整页，area 1/2/3/4 一致）。

#### `close_cached_documents() -> None`

关掉共享文档缓存里的全部文档，释放 Windows 文件句柄。

⚠️ 删除任务/关闭文档前必须调用：缓存里的 Document 一直握着 PDF 文件，
Windows 上不先关掉，`rmtree` 会一直 PermissionError（store 的重试兜底
救不了"永远不关"的句柄）。会等到当前正在跑的那次渲染结束（≤几百 ms）。

#### `qt_family_for_file(path: str) -> str | None`

按**字体文件**加载并取回 Qt 族名；失败返回 None。

为什么要按文件而不是按族名：PDF 侧（`utils.pdf_draw.build_font_chain`）
也是按文件注册字体的，两边用同一个文件才能保证「预览 = 成品」。按族名
查表在离屏/精简环境下会落空（那时 `QFontDatabase.families()` 几乎是
空的），预览就退回默认字体，与成品对不上。

#### `preview_text_font(spec, px_per_mm: float) -> QFont`

按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。

字体族走 ``_pick_content_font``（内容是标题 / 页码，仿宋优先）——与
``pdf_draw.register_fonts`` 取到的字体同一种，预览与成品才对得上。

⚠️ 不能直接用 ``setPointSizeF(spec.font_size_pt)``：那是固定像素大小，
而逐字步进是 ``char_h_mm × px_per_mm``（随密度缩放）。两处口径不同时，
密度一变小（第四步版面编辑画布把整页缩到可视区，≈2 px/mm，远小于效果
预览的 ≈5.4 px/mm），字仍是原大小、步进却按比例缩小 → **字叠在一起**。

统一口径后：字高 = 字号(mm) × 密度，与步进同源，任何密度下都不重叠，
且与成品 PDF 的真实字号（pt → mm）一致。

``spec.font`` 是用户为这段文字（标题 / 页码各自独立）指定的字体，
能解析到文件就按文件加载——与成品 PDF 用同一个字体文件。

#### `compose_print_page(image: QImage, plan, px_per_mm: float | None=None) -> QImage`

按 ``utils.page_layout.PrintPagePlan`` 合成"打印效果"位图。

**只画内存位图，不写任何文件**——第四步的效果预览就是它；真正生成
PDF 仍要走「生成 PDF」按钮（functions/print.py）。

几何全部取自 ``plan``，而 ``plan`` 由 PDF 生成与预览共用，所以用户
按预览调好的边距/纸张/标题，与最终 PDF 必然一致。

---

## `desktop.workers.rembg_live_worker`

源码：[`desktop/workers/rembg_live_worker.py`](../../desktop/workers/rembg_live_worker.py)

单页实时去底色的后台 worker（第三步「改参数实时预览」专用）。

与 ``PreviewWorker`` 的分工：那个只负责**显示**（读图 / 按区域裁剪 / 缩放），
本 worker 负责**计算**（真正的去底色）。二者接力：本 worker 先把结果落到
临时目录，预览区再按 ``live_dir`` 找到它并走原有的显示管线。

去底色对整页图（数千像素）要百毫秒级 CPU，放主线程会卡住界面，因此一律
丢到 QThread 里跑。结果通过 token 回传，宿主据此丢弃"已经过期的"结果
（用户连拖两次滑块时，慢的那次回来得晚，不能覆盖新的）。

### `class RembgLiveWorker(QObject)`

一次性 worker：单页去底色 → 写临时文件。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(image_path: str, args: dict, out_dir: str, token: object) -> None` | 参数: |
| `cancel() -> None` | 请求放弃计算。token 守卫只丢**结果**不省**算力**：连拖滑块时 |
| `run() -> None` | 线程入口：算完发 finished，异常发 failed（不抛到线程外）。 |

##### `__init__(image_path: str, args: dict, out_dir: str, token: object) -> None`

参数:
image_path: 待去底色的源图（extract 产物）。
args: rembg 面板收集的参数（offset/type/seal/…）。
out_dir: 实时暂存目录（``services.rembg_live.live_dir``）。
token: 本次请求的标识，供宿主判断结果是否已过期。

##### `cancel() -> None`

请求放弃计算。token 守卫只丢**结果**不省**算力**：连拖滑块时
每次派发都先取消上一单，别让几个 numpy 重活同时抢 GIL
（2026-09-26 第二轮审计 L2）。

##### `run() -> None`

线程入口：算完发 finished，异常发 failed（不抛到线程外）。

⚠️ 取消路径也必须发终态信号（finished/failed 之一），否则线程事件
循环永不退出（SourceThumbnailsWorker 同款教训）；空路径结果由宿主
按 token 丢弃。

---

## `desktop.workers.render_lock`

源码：[`desktop/workers/render_lock.py`](../../desktop/workers/render_lock.py)

PDF 页渲染的**单飞锁**：全进程同一时刻只允许一个 PyMuPDF 页渲染。

⚠️ 为什么单独成模块（不放在 ``preview_worker`` 里）
    导入后台任务（``source_thumbnails_worker``）也要用这把锁，而
    ``preview_worker`` 是 500+ 行的重模块（还带着第四步效果合成的整套依赖）。
    从它 import 会把这些依赖拖进**启动路径**——`desktop/workers/__init__.py`
    的惰性导出正是为了避免这件事。所以锁放在这个零依赖的小模块里，谁都能引。

⚠️ 谁必须走它
    **任何**从 PDF 页渲位图的代码：单页预览（``PreviewWorker._render_pdf_page``）、
    批量缩略图（``PreviewWorker._render_all_thumbnails``）、导入后台任务
    （``SourceThumbnailsWorker._render_page``）。渲染全程攥 GIL ~105–180ms
    （实测），两个渲染并行 = GIL 互相抢，界面停顿叠加成 N×180ms——用户看到的
    就是「切缩略图卡、多点几下直接卡死」。串行化之后停顿上限收敛到**单次渲染**，
    且不随点击次数/页数增长。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `single_flight() -> threading.Lock` | 取单飞锁。用法：``with single_flight(): ...渲染一页...``。 |

#### `single_flight() -> threading.Lock`

取单飞锁。用法：``with single_flight(): ...渲染一页...``。

⚠️ 只把**渲染本身**（load_page + get_pixmap + tobytes）包进锁：写盘、
``QImage.fromData``、让出 GIL 的 sleep 都放锁外——否则别的渲染请求要陪着
等 I/O，锁的粒度就过粗了。

---

## `desktop.workers.serial_jobs`

源码：[`desktop/workers/serial_jobs.py`](../../desktop/workers/serial_jobs.py)

串行后台任务队列：同一时刻只跑一个 job，且**等界面画完再开工**。

## 为什么必须串行

导入 PDF 后要跑「复制源文件 + 渲染整本缩略图」，那是 PyMuPDF 的密集 C 调用。
原先每次导入都起一个线程、且不设上限，多个渲染线程同时跑就会争抢 GIL，
主线程的每一次文件操作都被排到 GIL 队列后面：

| 并发渲染线程 | 0 | 1 | 4 | 8 | 15 |
|---|---|---|---|---|---|
| 主线程 `create_task` 中位 | 5.5ms | 98ms | 216ms | 608ms | **1500ms** |

对照实验排除了磁盘因素：后台**纯写盘**（狂写 8KB 文件、期间落盘 1110 个文件）
对主线程 0 影响（stat 0.09ms、读 3KB 0.11ms、写 0.7ms）——是 GIL/线程调度，
不是 I/O、不是 fsync、也不是 tasks.json 的体积。串行 + 每页让出 GIL 后
主线程回到 16ms（脚本见 ``.workbuddy/perf/``）。

## 为什么还要「扣住不放行」

列表出现新行必须读 N 个任务的 runs.json。无争抢时 18 个任务只要 7.5ms；
一旦和渲染线程撞上，每个文件操作都要等 GIL，实测「导入 → 看见新行」从
0.2s 变成 0.5~2.5s。所以新 job 提交后先**扣住**，等页面把列表画完调
``release()`` 再开工；同时留一个超时兜底，信号丢了也不会永远不干活。

### `class SerialJobQueue(QObject)`

把一次性后台 job 串成一条队列，并支持「界面画完再放行」。

用法：``submit(worker, label, on_warning=..., on_failed=...)`` 排队，
``release()`` 放行，``shutdown()`` 收尾。

进度信号（job_started / progress / job_finished）供页面显示「正在导入」
提示条：整本缩略图可能要跑几十秒，用户必须看得到它还在干活。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(owner: QObject)` | owner 为宿主 widget（主线程）；线程与中继都挂在它下面。 |
| `submit(worker: QObject, label: str='', on_warning=None, on_failed=None, tag: str \| None=None) -> None` | 排队一个 job；等 ``release()``（或超时）后按提交顺序执行。 |
| `release() -> None` | 界面画完了：放行排队中的 job（重复调用无副作用）。 |
| `running_count() -> int` | 正在跑的 job 数（0 或 1）。 |
| `pending_count() -> int` | 排队中的 job 数。 |
| `current_label() -> str` | 正在跑的 job 的名字（没在跑就是空串）。 |
| `busy() -> bool` | 还有 job 在跑或排队。 |
| `cancel_tag(tag: str \| None, wait_ms: int=3000) -> bool` | 取消某个 tag（任务）名下的活：丢掉排队的、让在跑的收手并等它。 |
| `shutdown(wait_ms: int=800) -> None` | 退出收尾：停表、丢弃排队的活、让当前 job 尽快退出。 |

##### `submit(worker: QObject, label: str='', on_warning=None, on_failed=None, tag: str | None=None) -> None`

排队一个 job；等 ``release()``（或超时）后按提交顺序执行。

`tag` 给这个 job 打归属标记（本项目传 task_id），供 `cancel_tag` 精确
取消"某个任务的活"——删任务时必须先停掉它自己的后台导入，否则
`rmtree` 会撞上正在写的文件（见 `cancel_tag`）。

##### `cancel_tag(tag: str | None, wait_ms: int=3000) -> bool`

取消某个 tag（任务）名下的活：丢掉排队的、让在跑的收手并等它。

⚠️ 为什么需要它（2026-09-26 审计）：`delete_task` 只关预览缓存就删目录，
不管该任务**自己的**后台导入（复制源文件 + 渲染整本缩略图，2400 页要
69s）。`rmtree` 撞上正在写的文件 → 重试 8 次后失败，用户看到
「文件正被占用」；更糟的是删完后台线程还按旧路径继续写。

返回 True 表示该任务名下的活已经全部停下（可以安全删目录）；
False 表示超时仍未收手（调用方应告知用户稍后重试，别硬删）。

##### `shutdown(wait_ms: int=800) -> None`

退出收尾：停表、丢弃排队的活、让当前 job 尽快退出。

当前 job 的 ``cancel()`` 让它在下一次循环检查时收手（整本可能几千页，
不能傻等）；随后 ``quit()`` 结束线程事件循环。

---

## `desktop.workers.source_thumbnails_worker`

源码：[`desktop/workers/source_thumbnails_worker.py`](../../desktop/workers/source_thumbnails_worker.py)

导入后的一次性后台准备：**保住源文件副本 + 逐页渲染缩略图**。

命名与 PDF 预览查看器的页缩略图缓存一致（{page}.jpg，0 起始），
预览打开时直接命中缓存，不再重复渲染；该目录永不清理。

⚠️ 顺序：**缩略图先行、复制并行**（2026-09-25 改）
    原先「先复制 802MB、再从副本渲染缩略图」是串行的。复制本身不慢
    （SSD 实测 0.73s / 794MB），但慢盘上它可能是几十秒；而这段时间里
    用户已经点进详情页、要看的就是缩略图——他等的是**缩略图**，不是副本。
    现在：复制丢进独立线程（纯 I/O，不占 GIL），缩略图**立刻从源文件**
    开渲，首批（一屏可见量）先出；首批做完再等副本落地，后续页改从副本
    继续渲染（源文件之后被挪走/删掉也不影响剩下的页）。

⚠️ 为什么要每页让出 GIL
    PyMuPDF 渲染一页扫描件（5000×4400 的内嵌 JPEG）要 ~160ms，而且这
    160ms 里几乎一直持有 GIL：实测另一线程每 1ms 的心跳被拖到 175ms，
    只让 3ms 的话主线程只拿到 ~2% 的时间片——用户看到的正是「导入期间
    整个界面卡住」。现在让出量**按刚花掉的耗时成比例**（×0.5，上限 60ms），
    界面拿到约 1/3 的时间片；代价是整本渲染慢约 50%，而它是纯后台活。

### 模块常量

| 名称 | 值 |
| --- | --- |
| FIRST_SCREEN_PAGES | `16` |
| BATCH_PAGES | `8` |
| BATCH_GAP_MS | `120` |
| GIL_YIELD_RATIO | `0.5` |
| GIL_YIELD_MIN_MS | `3` |
| GIL_YIELD_MAX_MS | `60` |
| MIN_THUMB_BYTES | `512` |
| FINAL_COPY_WAIT_S | `5.0` |

### `class SourceThumbnailsWorker(QObject)`

导入 PDF 后渲染全部页面缩略图（256px，与预览查看器缓存一致）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(pdf_path: Path, out_dir: Path, edge: int=THUMBNAIL_EDGE, copy_to: Path \| None=None)` | 构造源 PDF 页缩略图 worker。 |
| `cancel() -> None` | 请求中止：渲染循环在下一页之前退出（关程序用，不必等整本跑完）。 |
| `wait_copy(timeout: float) -> bool` | 等复制线程收手，最多 `timeout` 秒；返回是否已结束。 |
| `run() -> None` | 并行复制 + 逐页渲染缩略图；任务目录被删时中止并报 failed。 |

##### `__init__(pdf_path: Path, out_dir: Path, edge: int=THUMBNAIL_EDGE, copy_to: Path | None=None)`

构造源 PDF 页缩略图 worker。

pdf_path 为源文件；out_dir 为 thumbnails/source/；edge 最长边
（默认 256）。缩略图命名 {page+1:04d}.jpg，与预览缓存一致。

copy_to 给了就**另起一个线程**把它复制成任务目录里的源文件副本
（原子落地）；缩略图不等它——先用源文件渲首批，副本落地后剩下的页
再从副本渲。源文件随后被移动/删除都不影响已落地的副本。

##### `wait_copy(timeout: float) -> bool`

等复制线程收手，最多 `timeout` 秒；返回是否已结束。

⚠️ 为什么需要（2026-09-26 审计）：复制是在**独立 daemon 线程**里做的，
`cancel()` 只置渲染循环的中止标志，打不断正在写的复制。而复制中的
`.part` 文件是**打开的句柄**——删任务时 `rmtree` 会一直
`PermissionError`（Windows）。所以删任务前必须给复制一个收手的机会。

##### `run() -> None`

装饰器：`Slot()`

并行复制 + 逐页渲染缩略图；任务目录被删时中止并报 failed。

⚠️ **顺序：缩略图一秒都不等复制**。复制丢进独立线程，缩略图立刻从
**源文件**开渲、首批（一屏）先出；页间只顺路看一眼复制好了没
（`is_alive()`，**不 join**），好了就换成从副本继续——源文件之后被
挪走/删掉也不影响剩下的页。慢盘上复制 700MB 要几十秒，任何"等它"
都会把整本缩略图停住，用户看到的就是"导入是串行的"。

⚠️ **每页先查缓存**：命名与预览查看器的缓存一致（``0001.jpg``），
已存在且不比源 PDF 旧的直接跳过。否则重复导入同一份 PDF（或把任务
目录复制过来）时，80 页的书要白渲染 80 页——用户看到的正是「明明
已经有缩略图了还在重新生成」。

---

## `desktop.workers.task_rows_worker`

源码：[`desktop/workers/task_rows_worker.py`](../../desktop/workers/task_rows_worker.py)

任务列表行的读取（后台线程）。

列表页刷新要遍历全部任务、逐个读它的 ``runs.json`` 才能拿到四个阶段的状态。
任务一多、或单个任务的 runs 记录一多，这串读盘就会把 **UI 线程**占住——窗口
明明已经画出来了，内容却要再等一截才出现。

放到这里在后台线程读，读完一次性把整批行回传主线程渲染。只读不写，因此
与主线程的 store 访问不冲突。

### `class TaskRowsWorker(QObject)`

读全量任务行（只读，不落任何盘）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(store) -> None` | store 只用于读（list_tasks / stage_states），不写。 |
| `run() -> None` | 遍历任务生成摘要行；异常回传 failed，不抛到线程外。 |

---

## `desktop.workers.worker_host`

源码：[`desktop/workers/worker_host.py`](../../desktop/workers/worker_host.py)

WorkerHost：在拥有者 widget 内启动一次性后台 worker 线程并自动回收。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _DETACHED_THREADS | `[]` |

### `class WorkerHost`

Mixin：在拥有者 widget 内启动一次性后台 worker 线程。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `run_worker(factory, wire) -> None` | 启动一次性 worker 线程并登记引用以便回收。 |
| `shutdown_workers() -> None` | 退出并等待所有后台线程，随后清空引用表。 |

##### `run_worker(factory, wire) -> None`

启动一次性 worker 线程并登记引用以便回收。

factory() 负责造 worker，wire(worker, thread) 负责连信号；线程结束后
worker 自动 deleteLater 并移出引用表，避免长会话下线程对象堆积。

##### `shutdown_workers() -> None`

退出并等待所有后台线程，随后清空引用表。

先给每个 worker 发一次 `cancel()`（有的话）——批量缩略图那种长循环
只有收到中止信号才会在页边界退出（见 `PreviewWorker.cancel`），
不然 `wait` 注定超时、线程被摘出去后还在后台啃 GIL。
等不到的线程交给 `stop_thread` 摘出父对象（否则 QThread 在运行中被销毁
会让 Qt abort —— 见 `stop_thread` 的说明）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `connect_queued(owner, signal, slot, thread=None) -> QObject` | worker 信号 → 主线程闭包的**唯一正确写法**，返回中继对象。 |
| `stop_thread(thread: QThread, timeout_ms: int, label: str) -> bool` | 请线程收手并最多等 `timeout_ms`；等不到就**摘下来别让它被销毁**。 |

#### `connect_queued(owner, signal, slot, thread=None) -> QObject`

worker 信号 → 主线程闭包的**唯一正确写法**，返回中继对象。

⚠️ 直接 ``signal.connect(lambda ...)`` 会让闭包在 **worker 线程**执行。
里面一旦碰 widget（``strip.set_item_icon``、``view.clear_image``、
``set_image``…），Qt 内部就在子线程启动定时器，控制台刷屏
``QBasicTimer::start: Timers cannot be started from another thread``
（每张缩略图一条——用户报告的就是这个）。连到**宿主 QObject 的绑定
方法**（``worker.finished.connect(self._ready)``）本来就安全，无需本
助手；闭包 / lambda 一律走这里。

owner 为宿主 widget（主线程），thread 给了就在线程结束时回收中继，
避免长会话反复加载累积出一批中继对象。

#### `stop_thread(thread: QThread, timeout_ms: int, label: str) -> bool`

请线程收手并最多等 `timeout_ms`；等不到就**摘下来别让它被销毁**。

返回 True 表示已结束。

为什么不能只 `quit()+wait()+丢引用`（2026-09-26 审计）
    `quit()` 只结束线程的事件循环，打不断正在执行的槽。本项目里
    `PreviewWorker._render_all_thumbnails`（整本缩略图）与 `PreviewWorker`
    的单页渲染都是长阻塞循环，`HashWorker` 要算完整本 PDF 的 SHA-256
    （800MB 约 1~2s）。这些线程都 parent 在 widget 上，而项目的退出路径是
    「worker 线程仍在跑时先销毁 widget」→ QThread 对象被销毁 → Qt abort
    （用户看到的是"关程序时崩一下"）。等不到时的正确做法不是假装成功，
    而是把线程从父对象上摘下来、由模块级列表持有引用，让它自然跑完。

---
