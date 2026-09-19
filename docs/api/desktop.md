<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# desktop API 参考

桌面端：GUI 主进程、worker 子进程、存储、界面系统

覆盖 66 个模块、70 个公开类、317 个公开函数/方法（生成于 2026-09-19）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`desktop.app`](#desktopapp) | 1 | 2 |
| [`desktop.components.common.safecomment`](#desktopcomponentscommonsafecomment) | 6 | 12 |
| [`desktop.components.log_panel`](#desktopcomponentslog_panel) | 1 | 9 |
| [`desktop.components.pagination`](#desktopcomponentspagination) | 2 | 11 |
| [`desktop.components.panels.base`](#desktopcomponentspanelsbase) | 1 | 7 |
| [`desktop.components.panels.detect_panel`](#desktopcomponentspanelsdetect_panel) | 1 | 2 |
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
| [`desktop.components.viewers.image_view`](#desktopcomponentsviewersimage_view) | 1 | 12 |
| [`desktop.components.viewers.image_viewer`](#desktopcomponentsviewersimage_viewer) | 1 | 6 |
| [`desktop.components.viewers.pdf_viewer`](#desktopcomponentsviewerspdf_viewer) | 1 | 2 |
| [`desktop.components.viewers.print_layout_canvas`](#desktopcomponentsviewersprint_layout_canvas) | 1 | 9 |
| [`desktop.components.viewers.print_preview`](#desktopcomponentsviewersprint_preview) | 1 | 8 |
| [`desktop.components.viewers.rembg_viewer`](#desktopcomponentsviewersrembg_viewer) | 1 | 3 |
| [`desktop.components.viewers.thumb_strip`](#desktopcomponentsviewersthumb_strip) | 1 | 5 |
| [`desktop.components.viewers.thumbs_loader`](#desktopcomponentsviewersthumbs_loader) | 1 | 0 |
| [`desktop.pages.taskdetail.detect`](#desktoppagestaskdetaildetect) | 1 | 0 |
| [`desktop.pages.taskdetail.history`](#desktoppagestaskdetailhistory) | 1 | 0 |
| [`desktop.pages.taskdetail.manifest`](#desktoppagestaskdetailmanifest) | 1 | 2 |
| [`desktop.pages.taskdetail.page`](#desktoppagestaskdetailpage) | 1 | 5 |
| [`desktop.pages.taskdetail.params_draft`](#desktoppagestaskdetailparams_draft) | 1 | 1 |
| [`desktop.pages.taskdetail.print_list`](#desktoppagestaskdetailprint_list) | 1 | 0 |
| [`desktop.pages.taskdetail.runner`](#desktoppagestaskdetailrunner) | 1 | 2 |
| [`desktop.pages.taskdetail.submit`](#desktoppagestaskdetailsubmit) | 1 | 1 |
| [`desktop.pages.taskdetail.view`](#desktoppagestaskdetailview) | 1 | 0 |
| [`desktop.pages.tasklist.page`](#desktoppagestasklistpage) | 1 | 5 |
| [`desktop.services.print_plan`](#desktopservicesprint_plan) | 0 | 5 |
| [`desktop.services.submit_state`](#desktopservicessubmit_state) | 0 | 1 |
| [`desktop.stages.detect_stage`](#desktopstagesdetect_stage) | 0 | 2 |
| [`desktop.stages.events`](#desktopstagesevents) | 2 | 9 |
| [`desktop.stages.generic_stage`](#desktopstagesgeneric_stage) | 0 | 2 |
| [`desktop.stages.print_stage`](#desktopstagesprint_stage) | 0 | 1 |
| [`desktop.stages.rembg_stage`](#desktopstagesrembg_stage) | 0 | 1 |
| [`desktop.store.annotations`](#desktopstoreannotations) | 1 | 6 |
| [`desktop.store.drafts`](#desktopstoredrafts) | 1 | 5 |
| [`desktop.store.json_io`](#desktopstorejson_io) | 0 | 2 |
| [`desktop.store.pages`](#desktopstorepages) | 1 | 9 |
| [`desktop.store.runs`](#desktopstoreruns) | 1 | 6 |
| [`desktop.store.store`](#desktopstorestore) | 1 | 1 |
| [`desktop.store.tasks`](#desktopstoretasks) | 1 | 19 |
| [`desktop.ui.font_setup`](#desktopuifont_setup) | 2 | 8 |
| [`desktop.ui.fonts`](#desktopuifonts) | 0 | 1 |
| [`desktop.ui.help_dialog`](#desktopuihelp_dialog) | 0 | 3 |
| [`desktop.ui.icons`](#desktopuiicons) | 2 | 4 |
| [`desktop.ui.segmented_toggle`](#desktopuisegmented_toggle) | 1 | 11 |
| [`desktop.ui.style`](#desktopuistyle) | 0 | 3 |
| [`desktop.ui.theme`](#desktopuitheme) | 0 | 2 |
| [`desktop.ui.widgets`](#desktopuiwidgets) | 8 | 33 |
| [`desktop.utils.files`](#desktoputilsfiles) | 0 | 6 |
| [`desktop.utils.icon`](#desktoputilsicon) | 0 | 3 |
| [`desktop.worker`](#desktopworker) | 0 | 1 |
| [`desktop.workers.hash_worker`](#desktopworkershash_worker) | 1 | 2 |
| [`desktop.workers.image_list_worker`](#desktopworkersimage_list_worker) | 1 | 2 |
| [`desktop.workers.preview_worker`](#desktopworkerspreview_worker) | 1 | 7 |
| [`desktop.workers.source_thumbnails_worker`](#desktopworkerssource_thumbnails_worker) | 1 | 2 |
| [`desktop.workers.worker_host`](#desktopworkersworker_host) | 1 | 3 |

---

## `desktop.app`

源码：[`desktop/app.py`](../../desktop/app.py)

gujitools 桌面端主窗口：任务列表页 + 任务详情页切换。

### `class MainWindow(QMainWindow)`

主窗口：在任务列表页与任务详情页之间切换。
创建时设定窗口最小尺寸并套用全局底色；通过 QStackedWidget 持有两页，
并连接列表页「打开详情」与详情页「返回」信号完成页面跳转。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `closeEvent(event) -> None` | 关闭窗口时先让详情页收尾 worker 子进程。 |

##### `closeEvent(event) -> None`

关闭窗口时先让详情页收尾 worker 子进程。
详情页持有 worker 子进程与后台线程的引用，直接退出会让进程被强杀；
这里把事件转交给详情页的 closeEvent 完成 kill/等待/清理后再接受关闭。

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

阶段控制面板基类：标题 + 说明 + 参数表单骨架。

标题与说明都开启换行——右侧参数卡片只有 340~580px 宽，长说明不换行会
把面板撑出横向边界（原来靠各子类自己调 setWordWrap 兜着）。

### `class StagePanel(QWidget)`

阶段控制面板：标题 + 说明 + 参数表单。子类实现 _build_form/get_args。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 构建面板骨架：标题 + 说明 + 参数表单容器。 |
| `mark_params_edited() -> None` | 补一次"用户改了参数"通知——给**按钮**这类不经过控件信号的入口用。 |
| `build_form() -> QWidget` | 参数表单容器：统一装进透明滚动区，窗口过矮时出滚动条而非压扁表单。 |
| `get_args() -> dict` | 从表单收集该阶段参数（不含 input/output/clean）。 |
| `apply_args(parameters: dict) -> None` | 把一次历史执行/暂存的参数回填到表单（多余键忽略）。 |
| `reset_to_default() -> None` | 恢复控件初始默认值。 |

##### `__init__(parent=None)`

构建面板骨架：标题 + 说明 + 参数表单容器。

title/description 来自子类类属性并开启换行，避免窄面板被长说明撑破；
随后调用 build_form 生成子类表单并占满剩余垂直空间，最后统一把表单
里输入控件的信号接到 ``param_edited``（供参数暂存）。

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

YOLO 检测每张图的左右文本框坐标，供预览标注与去底色/裁剪使用；
本阶段无表单参数，get_args 返回空字典，手动检测经信号触发。

「整页模式」是第三步 area=4 的入口开关：勾选后整页即唯一文本框，
**不加载也不调用 YOLO**，预览里框画在页面边界，仍可手动拖动/重画。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 返回空参数字典（detect 阶段无表单参数）。 |
| `set_whole_page(on: bool) -> None` | 外部（第三步 area）回填勾选状态；blockSignals 避免回抛造成循环。 |

##### `get_args() -> dict`

返回空参数字典（detect 阶段无表单参数）。

整页模式不在这里上报：area 归第三步 rembg 面板所有，本开关只负责
把 area 切到 4 / 切回 1（见宿主的 _set_whole_page_mode）。

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
| `parse_margin4(text: str)` | 解析边距简写：1 值→四边；2 值→上下/左右；4 值→上右下左；空→None。 |
| `margin_to_text(value) -> str` | 边距列表转简写文本：四边相等→单值；上下/左右相等→两值；否则四值。 |
| `skip_pages_to_text(value) -> str` | skip_pages 参数 → 表单文本（逗号分隔的页名）。 |
| `text_to_skip_pages(text: str) -> list[str]` | 表单文本 → skip_pages 参数。 |

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
| `set_boxes_editable(editable: bool) -> None` | 开关框编辑；开启时接受点击焦点以响应键盘删除。 |
| `set_reference_boxes(boxes: list) -> None` | 设置参考框（橙色虚线，不参与编辑）并重绘。 |
| `set_image(image, boxes=None, image_size: QSize \| None=None) -> None` | 装入图片并重置编辑状态。 |
| `set_boxes(boxes: list, image_size: QSize) -> None` | 仅更新切割框与图片原始尺寸并重绘（不换图）。 |
| `clear_image(text: str='无预览') -> None` | 清空图片与全部框（含参考框），显示占位文案。 |
| `resizeEvent(event) -> None` | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。 |
| `mousePressEvent(event) -> None` | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。 |
| `mouseMoveEvent(event) -> None` | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。 |
| `mouseReleaseEvent(event) -> None` | Qt 事件覆写：松开（提交本次编辑）。 |
| `keyPressEvent(event) -> None` | Qt 事件覆写：键盘操作（如 Delete 删除选中项）。 |

##### `set_image(image, boxes=None, image_size: QSize | None=None) -> None`

装入图片并重置编辑状态。

image 为 QImage；image_size 非空时作为框坐标的坐标系基准（大图可能被
降采样显示，坐标必须按原始尺寸算）。

##### `set_boxes(boxes: list, image_size: QSize) -> None`

仅更新切割框与图片原始尺寸并重绘（不换图）。

boxes 为图片像素坐标；image_size 为坐标映射基准，与显示缩放无关。

---

## `desktop.components.viewers.image_viewer`

源码：[`desktop/components/viewers/image_viewer.py`](../../desktop/components/viewers/image_viewer.py)

图片查看器：缩略图条 + 大图，支持切割框叠加与页面增删按钮。

### `class ImageViewerWidget(QWidget, ThumbsMixin)`

图片查看器：缩略图条 + 大图，支持切割框叠加、拖动与页面增删按钮。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(editable: bool=False, show_boxes: bool=False, empty_hint: str='暂无图片', image_size_provider=None, thumb_provider=None, parent=None)` | 构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。 |
| `paths() -> list[Path]` | 当前页面清单（按显示顺序）。 |
| `current_path() -> Path \| None` | 当前选中的页面路径；无选中或无清单时为 None。 |
| `set_images(paths: list[Path], boxes_map: dict \| None=None) -> None` | 设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。 |
| `apply_boxes(boxes: list[tuple], image_size: QSize, info_text: str='') -> None` | 在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。 |
| `set_reference_boxes(boxes: list) -> None` | 设置参考框（最终裁剪大框，虚线显示，不参与编辑）。 |

##### `__init__(editable: bool=False, show_boxes: bool=False, empty_hint: str='暂无图片', image_size_provider=None, thumb_provider=None, parent=None)`

构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。

image_size_provider 供大图降采样时还原原始像素尺寸；thumb_provider
让缩略图条改用预生成小图，避免反复解码原图。

##### `set_images(paths: list[Path], boxes_map: dict | None=None) -> None`

设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。

paths 为 Path 列表；boxes_map 预留（当前未用）。清单不变时跳过
重建，但仍 emit current_changed 让宿主重新读取该页检测框/参数。

---

## `desktop.components.viewers.pdf_viewer`

源码：[`desktop/components/viewers/pdf_viewer.py`](../../desktop/components/viewers/pdf_viewer.py)

PDF 查看器：左侧页面缩略图 + 右侧大图。

### `class PdfViewerWidget(QWidget, WorkerHost)`

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
- 框内拖动 → 整体移动；四角手柄拖动 → 缩放；松手 emit ``rect_changed``；
- 框始终被夹在页面内（夹到纸边即停），不会拖出页面；
- 悬停手柄/框时显示对应光标。

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

### `class PrintLayoutCanvas(QWidget)`

A4 纸上的图片拖拽/缩放画布；rect_changed 发出页面 mm 坐标。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | — |
| `set_page(page_w_mm: float, page_h_mm: float, image: QImage \| None, rect_mm: Sequence[float], plan=None) -> None` | 设置页面尺寸、待绘制图片与初始图片框（页面 mm）。 |
| `current_rect() -> list[float]` | 当前图片框（页面 mm），供宿主落盘前读取。 |
| `resizeEvent(event) -> None` | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。 |
| `showEvent(event) -> None` | 显示时重算：首次进入第四步可能在布局完成前就 ``set_page`` 过， |
| `mousePressEvent(event) -> None` | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。 |
| `mouseMoveEvent(event) -> None` | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。 |
| `mouseReleaseEvent(event) -> None` | Qt 事件覆写：松开（提交本次编辑）。 |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

##### `set_page(page_w_mm: float, page_h_mm: float, image: QImage | None, rect_mm: Sequence[float], plan=None) -> None`

设置页面尺寸、待绘制图片与初始图片框（页面 mm）。

``plan`` 为 ``utils.page_layout.PrintPagePlan``：本控件据它画标题/
页码与「已跳过」提示——版面编辑不能只看图片，否则无从判断挪动后
会不会压到字。传 None 表示纯图片编辑（无标题/页码）。

##### `showEvent(event) -> None`

显示时重算：首次进入第四步可能在布局完成前就 ``set_page`` 过，
那时 ``width()/height()`` 还是 0，``_px_per_mm`` 会退化为 1.0。
仅靠 resizeEvent 兜不住「已分配尺寸但从未显示」的情况。

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

### `class PrintPreviewWidget(QWidget, ThumbsMixin)`

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
| `refresh_layout() -> None` | 参数（纸张/方向）变化后刷新画布：保留已存坐标，仅重算页面尺寸。 |

##### `__init__(empty_hint: str='暂无图片，请先完成去底色', params_provider=None, thumb_provider=None, parent=None)`

构建工具栏 + 左缩略图条 + 右效果预览。

params_provider: () -> print 参数字典；非法时抛异常（由本控件捕获
    并退回「原图」显示）。为 None 时关闭「打印效果」项。
thumb_provider: (path_text) -> Path | dict | None，可选的小图来源。

---

## `desktop.components.viewers.rembg_viewer`

源码：[`desktop/components/viewers/rembg_viewer.py`](../../desktop/components/viewers/rembg_viewer.py)

去底色预览：单视图显示，去底色结果优先，顶部用分段开关切换原图。

左侧缩略图条按"输出条目"组织：
- area=1：每个文本框一条（标签 <页>-l / <页>-r），右侧显示该框 + border 区域；
- area=2/3：每页一条，右侧显示按 crop/cropremove 规则合成的效果区域。

区域合成在 worker 线程完成，不生成文件；通过请求令牌避免快速切换串台。

### `class RembgPreviewWidget(QWidget, ThumbsMixin)`

去底色预览：左侧输出条目列表 + 右侧单视图（去底色结果 / 原图切换）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(empty_hint: str='暂无图片', parent=None)` | 构建缩略图条与「去底色结果 / 原图」切换行，默认显示去底色结果。 |
| `set_images(paths: list[Path], rembg_dir: Path \| None, boxes_provider=None, region_params_provider=None, thumb_provider=None) -> None` | 设置图片清单与去底色目录，重建输出条目并加载显示。 |
| `refresh_display() -> None` | detect 框/area/border 变化后，重建输出条目并按新区域重新加载。 |

##### `set_images(paths: list[Path], rembg_dir: Path | None, boxes_provider=None, region_params_provider=None, thumb_provider=None) -> None`

设置图片清单与去底色目录，重建输出条目并加载显示。

paths 为源图；rembg_dir 为去底色结果目录（存在才显示结果）；
各 provider 给出检测框 / 区域参数 / 缩略图来源。清单变化时重建
缩略图条，否则按最新区域重加载当前显示。

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
| `__init__(parent=None)` | 初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。 |
| `set_reorderable(on: bool) -> None` | 打开/关闭条目内部拖放排序（第四步待打印列表用）。 |
| `add_placeholder(text: str) -> None` | 追加一个纯文字占位条目（无图标，如"缩略图加载中…"）。 |
| `add_page_item(label: str, path: str='') -> None` | 新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。 |
| `set_item_icon(index: int, image, path: str, label: str) -> None` | 替换某条目的图标/文字/路径（缩略图异步就绪后回调）。 |

##### `__init__(parent=None)`

初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。

⚠️ 必须监听 ``currentRowChanged`` 而不是只接 ``itemClicked``：
键盘翻页（方向键 / PageUp / PageDown）与程序化 ``setCurrentRow``
只会改 currentRow、**不产生点击**，只接 itemClicked 就会出现
「翻页了但右侧预览不更新，切到别的视图模式再切回来才正常」。

##### `add_page_item(label: str, path: str='') -> None`

新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。

占位图按满框（ICON_SIZE）给 sizeHint——此时还不知道这张图的宽高比；
真实缩略图一到就由 set_item_icon 按实际比例改小。

---

## `desktop.components.viewers.thumbs_loader`

源码：[`desktop/components/viewers/thumbs_loader.py`](../../desktop/components/viewers/thumbs_loader.py)

缩略图异步装载混入：为 ThumbStrip 批量加载图片缩略图。

### `class ThumbsMixin(WorkerHost)`

为持有 ThumbStrip 的查看器提供批量缩略图加载。

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

### `class TaskDetailPage(StageRunnerMixin, SubmitMixin, PrintListMixin, ParamDraftMixin, HistoryMixin, DetectMixin, PageListMixin, DetailViewMixin, QWidget, WorkerHost)`

任务详情页：由多个 Mixin 组合，固定四阶段流程。

编排 extract→detect→rembg→print 四阶段；各职责（预览、清单、历史、
提交、执行、检测）分散到同级 Mixin，本类只持有任务切换与阶段切换骨架。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(store, parent=None)` | 初始化详情页：建 worker 宿主、清运行态并组装 UI。 |
| `set_task(task_id: str) -> None` | 切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。 |
| `current_stage() -> str` | 返回当前所处阶段的 key（extract/detect/rembg/print）。 |
| `closeEvent(event) -> None` | 关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。 |
| `shutdown_all_workers() -> None` | 连同各预览控件自己的缩略图线程一起收尾。 |

##### `__init__(store, parent=None)`

初始化详情页：建 worker 宿主、清运行态并组装 UI。

创建 store 引用与 _init_worker_host 后台线程宿主；初始化全部运行态
字段（task_id/process/run_id/detect_cache 等）为空，再构建界面骨架。

##### `set_task(task_id: str) -> None`

切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。

加载任务后先调用各面板 reset_to_default 清掉上一任务手改参数，再清
detect 缓存/运行态引用并刷新清单与预览；防止参数或 run_id 串到新任务。

##### `current_stage() -> str`

返回当前所处阶段的 key（extract/detect/rembg/print）。

以步骤条高亮下标映射到 STAGES 序列；下标为负时按 0 兜底处理。

##### `closeEvent(event) -> None`

关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。

详情页持有 QProcess 与多个 WorkerHost 线程；先 kill 正在跑的执行/
检测子进程并等待（最多 1.5s），再 shutdown_all_workers 收尾其余线程，
最后接受关闭事件，避免解释器退出时被强杀崩溃。

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
| `run_stage(resume: bool=False) -> None` | 启动当前阶段的 worker 子进程。 |
| `cancel_stage() -> None` | 中断正在执行的阶段：先落 cancelled 再 kill 子进程。 |

##### `run_stage(resume: bool=False) -> None`

启动当前阶段的 worker 子进程。

resume=True 表示续跑：extract 只补缺失页、其余阶段跳过已有输出，
否则 clean=True 全量重跑。会取面板参数、写运行配置、起子进程并连接
输出/错误/完成信号，再挂看门狗兜底 Windows 偶发的 finished 丢失。

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

### `class DetailViewMixin`

依赖宿主页面提供的方法：_on_back、_select_stage、各预览联动槽、
current_stage()、_update_run_buttons() 等。

---

## `desktop.pages.tasklist.page`

源码：[`desktop/pages/tasklist/page.py`](../../desktop/pages/tasklist/page.py)

任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。

### `class TaskListPage(QWidget)`

任务管理页：搜索 + 分页的任务列表，支持导入 PDF 与删除。

数据流是单向的：``refresh()`` 从 store 读出**全量**行并缓存，
``_render()`` 负责「按关键词过滤 → 分页切片 → 填表」。搜索框只触发
``_render()``（不再读盘），所以打字时不会每次都去扫一遍任务目录。

含表格/空状态二选一的内容区；导入走「后台算指纹→查重→确认建任务」
流程，缩略图另行后台生成，全程不阻塞界面。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(store: TaskStore, parent=None)` | 初始化页面：构建 UI、绑定信号并刷新首次列表。 |
| `refresh() -> None` | 从 store 重新读出全量任务行并渲染（会读盘，不要在打字时调）。 |
| `focus_task(task_id: str) -> bool` | 翻到任务所在页并选中它；不在当前过滤结果里则返回 False。 |
| `import_pdf() -> None` | 导入 PDF：选文件后后台算指纹并查重确认建任务。 |
| `delete_task(task_id: str) -> None` | 删除指定任务及其全部中间产物（带确认弹窗）。 |

##### `__init__(store: TaskStore, parent=None)`

初始化页面：构建 UI、绑定信号并刷新首次列表。

parent 一般为 MainWindow；会创建 store 引用与导入按钮状态占位，
随后调用 refresh 重建表格与空状态。

##### `refresh() -> None`

从 store 重新读出全量任务行并渲染（会读盘，不要在打字时调）。

遍历各任务取四个阶段的 status/done/total 生成摘要行，结果缓存在
``_all_rows``；随后走 ``_render()`` 做过滤与分页。

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

#### `plan_print_effects(list_entries: list[dict], composed: list[dict], rembg_dir: Path, submitted_labels: set[str], border) -> list[dict]`

第四步列表 + 第三步当前 area/border → worker 合成规格。

与「提交本次任务」复用同一套派生规则（plan_rembg_submit_entries）：
源图为 stages/rembgpreview 去底图，effect 携带检测框/area/border，
由 run_print_stage 在子进程内实时合成后再排版为 PDF。

与用户在第四步保存的列表（拖动排序/删除/外部插入）按 label 对齐：
- 命中当前 area 派生集合的条目，按用户列表顺序输出合成规格；
- 用户插入的外部图片（不在 stages/rembg 目录）整图透传；
- area 模式切换后已失效的旧提交图（如旧 82-r/82-l 被新 82 取代）
  丢弃，当前集合中新派生的条目按默认顺序补在末尾，避免漏页或重复。

#### `plan_print_entries(rembg_files: list[Path], doc: dict | None) -> tuple[list[dict], dict]`

第四步待打印图片列表的规划。

直接使用第三步「提交本次任务」产出的 stages/rembg 最终图片
（已按 area/border 合成），按古籍阅读顺序（cover/menu 优先、
同编号 r→l、数字自然序）排列。

列表不再使用源 PDF 缩略图，直接显示 rembg 最终图片本身；
print.json 仅持久化用户的拖动/删除/插入顺序。

返回 (entries, doc)。

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

## `desktop.stages.detect_stage`

源码：[`desktop/stages/detect_stage.py`](../../desktop/stages/detect_stage.py)

detect 阶段执行器：单图检测 + 批量检测（重依赖只在本子进程加载）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `run_detect(config: dict) -> int` | 检测单张图片的左右文本框，返回像素坐标（重依赖只在本子进程加载）。 |
| `run_detect_stage(config: dict) -> int` | detect 阶段：逐图检测左右文本框并上报坐标，不切割、不生成任何文件。 |

#### `run_detect_stage(config: dict) -> int`

detect 阶段：逐图检测左右文本框并上报坐标，不切割、不生成任何文件。

检测算法复用 `functions.detect.detect_page_boxes`（与 CLI crop /
cropremove 同源），最终裁剪框由 GUI 按同一套规则
（utils.box_geometry.compute_final_boxes）从检测框实时推导，用于预览标注。

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
| `emit(payload: dict, stream=None) -> None` | 向 GUI 输出一条 JSON Lines 事件。 |

#### `emit(payload: dict, stream=None) -> None`

向 GUI 输出一条 JSON Lines 事件。

stream 缺省写真实 stdout；窗口化打包运行时 sys.stdout 可能为 None，
此时由 _real_stdout() 兜底到文件描述符 1。

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

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `run_print_stage(config: dict) -> int` | print 阶段：把 rembg 结果按 area/border 合成为效果图，再生成 PDF。 |

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
| `sizes_path(task_id: str) -> Path` | 页面原始尺寸文件：任务目录下的 sizes.json。 |
| `save_image_size(task_id: str, image_key: str, width: int, height: int) -> None` | 记录某页图片的原始像素尺寸，作为框坐标与预览映射的坐标系基准。 |
| `image_size(task_id: str, image_key: str) -> tuple[int, int] \| None` | 返回某页原始像素尺寸 (width, height)；无记录时返回 None。 |

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
record: {run_id, status, parameters, done, total, started_at, finished_at, output_path}
历史记录既用于页面状态渲染（最新一条），也作为阶段面板的历史配置选项。

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
| `finish_stage(task_id: str, run_id: str, status: str, output_path: str \| None=None, progress: tuple[int, int] \| None=None) -> None` | 结束某次运行：写入 status/finished_at/output_path。 |
| `list_stage_runs(task_id: str, stage: str) -> list[dict]` | 某阶段的历史执行记录，最新在前。 |
| `stage_states(task_id: str) -> dict[str, dict]` | 每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。 |

##### `create_stage_run(task_id: str, stage: str, parameters: dict, resume: bool=False) -> str`

登记一次新的阶段执行并返回 run_id。

新记录插在该阶段历史最前，初始状态 running、进度 0/0；每阶段只保留
最近 MAX_RUN_HISTORY 条。resume 标记本次是否为续跑。

##### `finish_stage(task_id: str, run_id: str, status: str, output_path: str | None=None, progress: tuple[int, int] | None=None) -> None`

结束某次运行：写入 status/finished_at/output_path。

status 取 success/failed/cancelled 等；output_path 为该次执行的
主产物路径（如 print.pdf、rembg 输出目录），供历史面板回链。
任务目录已删除时静默跳过。

progress 为 (done, total)，用于补齐最终计数。worker 的 finished 事件
不再携带 done/total（进度由结构化 progress 事件实时汇报），因此调用方
传入「最近一次进度」即可让历史记录落到真实完成数，而不是停在中间值。

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
| `copy_source_to_task(task_id: str, source_path: Path) -> Path` | 导入时在任务目录下保留一份源文件副本。 |
| `source_copy_path(task_id: str) -> Path \| None` | 任务目录里的 PDF 备份路径；没有备份返回 None。 |
| `ensure_source_copy(task_id: str) -> Path \| None` | 保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。 |

##### `create_task(source_path: Path, source_hash: str, name: str, duplicate_confirmed: bool=False) -> str`

新建任务并返回任务号（四位零填充）。

任务号取当前最大号 +1，同时参考索引与磁盘目录；若两者不一致导致号被
占用则继续顺延。创建时会预建 stages/runs/thumbnails/source
子目录，但不复制源文件（由 copy_source_to_task 负责）。

##### `delete_task(task_id: str) -> bool`

删除任务及其中间产物，返回是否真的删掉。

⚠️ 顺序是「**先删目录、成功才删索引**」：反过来的话目录一旦被占用
没删掉、索引却先没了，任务目录就变成没人认领的孤儿，用户还看不见。

⚠️ Windows 上 PDF 被后台渲染线程打开时 ``rmtree`` 抛 PermissionError，
原先 ``ignore_errors=True`` 会让它**静默残留**——列表里显示已删除，
磁盘上目录还在。这里重试若干次再判定失败，失败时保留任务让用户重试。

##### `stage_output_dir(task_id: str, stage: str) -> Path`

返回某阶段（GUI）应写入的输出目录。

注意 rembg 阶段返回 rembgpreview 预览目录，rembg_submit 才指向
rembg 最终目录；print 返回 print.pdf 所在目录。

##### `workset_dir(task_id: str) -> Path`

已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。

仅为清理历史遗留目录保留（老版本任务目录下可能仍有 workset/）。

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
把 ``docs/guide/*.md`` 转成完整 HTML，内嵌匹配应用主题的 CSS，写到临时文件
后用系统默认浏览器打开。**

这样做的好处：

1. **零重量依赖** —— ``markdown`` 是纯 Python 单包，不引入 Qt 之外的二进制；
2. **完整 GFM** —— 表格、围栏代码块、嵌套列表都按规范渲染；
3. **图片照旧可用** —— 靠 ``<base>`` 把文档基准指向 ``docs/guide/``，
   12 张相对路径的中文名截图正常加载，Markdown 里的写法一个字都不用改；
4. **样式自由** —— 真实浏览器渲染，CSS 不受 Qt 富文本子集限制；
5. **不做构建步骤** —— HTML 是**运行时**生成的，改了 Markdown 重新打开
   手册就是新的，不存在产物与源漂移的问题。

两条关键实现约束（改动时别踩）：

- **``<base>`` 必须指向手册目录且带结尾斜杠**：否则
  ``screenshots/guide/*.png`` 会相对临时文件解析，全变成碎图。
- **指南之间的互链要改成页内 tab 跳转**：``gui-guide.md`` 里有
  ``[cli.md]\(cli.md)``，浏览器会把 .md 当纯文本显示，必须改写为
  ``#tab-cli`` 交给 JS 切页。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _HTML_PREFIX | `"guji_manual_"` |
| _KEEP_RECENT | `3` |
| _JS | `" (function () {   function activate(tabId) {     var tabs…"` |

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `manual_dir() -> Path` | 手册目录（源码与打包两种模式下都可用）。 |
| `generate_manual_html(entry: str \| None=None) -> Path` | 把全部手册渲染成一个带分段开关的 HTML 文件，返回其路径。 |
| `open_manual(entry: str \| None=None) -> Path` | 生成手册 HTML 并用系统默认浏览器打开，返回该文件路径。 |

#### `manual_dir() -> Path`

手册目录（源码与打包两种模式下都可用）。

与 ``package_dir()`` 同源：源码模式下 ``desktop/`` 的上一级就是仓库根，
打包后数据文件由 ``guji.spec`` 的 ``gui_datas`` 落到 ``_internal/``，
``package_dir()`` 在 frozen 下返回 ``_MEIPASS/desktop``，再上一级同样是
资源根，因此 ``package_dir().parent / "docs" / "guide"`` 两种模式通用。

#### `generate_manual_html(entry: str | None=None) -> Path`

把全部手册渲染成一个带分段开关的 HTML 文件，返回其路径。

entry 为 ``MANUAL_ENTRIES`` 里的键，决定默认激活哪个标签页；
不传则激活第一项。

⚠️ ``<base>`` 指向手册目录（带结尾斜杠）是图片能加载的唯一保证：
Markdown 里写的是 ``screenshots/guide/xxx.png`` 这样的相对路径，
而 HTML 落在临时目录，不设 base 就会相对临时目录解析成碎图。

#### `open_manual(entry: str | None=None) -> Path`

生成手册 HTML 并用系统默认浏览器打开，返回该文件路径。

返回路径是为了调用方（或测试）能拿到产物做进一步处理。
浏览器打不开时 ``webbrowser.open`` 只是返回 False，不抛异常——
手册文件仍然生成好了，用户可以手动打开。

⚠️ 不要给 URL 加 ``?v=<时间戳>`` 去防缓存：Windows 上
``webbrowser.open`` 最终走 ``os.startfile``，查询串会被当成路径的
一部分，实测地址栏里根本不出现。防缓存靠的是**文件名本身带时间戳**
（见 ``_HTML_PREFIX``），每次都是新 URL。

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
| `apply_to(widget: QWidget, size: int=T.SIZE_BODY, bold: bool=False, color: str \| None=None) -> QLabel` | 给 QLabel 统一设置字体与颜色（颜色用调色板，不用样式表）。 |
| `combo_box(items: Iterable[str \| Sequence[Any]] \| None=None, width: int \| None=None) -> ComboBox` | 创建与输入框同高的下拉框（统一表单的行高节奏）。 |
| `icon_pixmap(icon, size: int=24, color: str=T.INK_FAINT) -> QPixmap` | 把 FluentIcon 渲染成指定颜色的 pixmap（用于空状态插画）。 |

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
| `project_root() -> Path` | 项目根目录（`desktop` 包的上一级）。 |
| `package_dir() -> Path` | `desktop` 包目录（源码与 PyInstaller 打包两种模式下都可用）。 |
| `file_hash(path: Path, chunk_size: int=1024 * 1024) -> str` | 流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。 |
| `natural_key(name: str)` | 生成自然排序键：数字段按整数、其余转小写，使 2 排在 10 前。 |
| `list_stage_images(directory: Path) -> list[Path]` | 某阶段输出目录中的图片（自然排序）。 |

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

### `class PreviewWorker(QObject)`

渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(path: Path, page: int=0, longest_edge: int \| None=1200, thumbnails: bool=False, cache_dir: Path \| None=None, effect: dict \| None=None, print_spec: dict \| None=None)` | 构造预览渲染 worker。 |
| `run() -> None` | 按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。 |

##### `__init__(path: Path, page: int=0, longest_edge: int | None=1200, thumbnails: bool=False, cache_dir: Path | None=None, effect: dict | None=None, print_spec: dict | None=None)`

构造预览渲染 worker。

PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
effect 为去底色合成参数 {boxes, area, border}，仅对单图生效。
print_spec 为第四步「打印效果」参数
{"args": print 参数, "index": 0-based 页序, "total": 总页数, "name": 文件名}，
非空时把图片按 utils.page_layout 的几何排进一张纸（仅内存，不落盘）。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300) -> list` | 按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。 |
| `preview_px_per_mm(page_w_mm: float, page_h_mm: float, target_edge: int=PRINT_PREVIEW_TARGET_EDGE) -> float` | 按纸张尺寸给出效果预览的像素密度（px/mm）。 |
| `preview_text_font(spec, px_per_mm: float) -> QFont` | 按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。 |
| `compose_print_page(image: QImage, plan, px_per_mm: float \| None=None, annotate: bool=False) -> QImage` | 按 ``utils.page_layout.PrintPagePlan`` 合成"打印效果"位图。 |
| `compose_outputs_horizontal(outputs: list, gap: int=12) -> QImage` | 多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。 |

#### `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300) -> list`

按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

**几何规则来自 utils.box_geometry**（与 functions/text_region.py 的 CLI
输出共用同一份实现），本函数只负责用 QImage 把布局画出来——这样规则
不会因数像素后端不同而被复制成两份。

与原实现的一处行为修正：area=3 + 双框 + border=None 时，并集区域现在
**写回原位置**（此前被搬到画布左上角）。规格见
docs/functions/cropremove.md:57「area=3 → 单图，ROI 写回原位置」。

#### `preview_text_font(spec, px_per_mm: float) -> QFont`

按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。

⚠️ 不能直接用 ``setPointSizeF(spec.font_size_pt)``：那是固定像素大小，
而逐字步进是 ``char_h_mm × px_per_mm``（随密度缩放）。两处口径不同时，
密度一变小（第四步版面编辑画布把整页缩到可视区，≈2 px/mm，远小于效果
预览的 ≈5.4 px/mm），字仍是原大小、步进却按比例缩小 → **字叠在一起**。

统一口径后：字高 = 字号(mm) × 密度，与步进同源，任何密度下都不重叠，
且与成品 PDF 的真实字号（pt → mm）一致。

#### `compose_print_page(image: QImage, plan, px_per_mm: float | None=None, annotate: bool=False) -> QImage`

按 ``utils.page_layout.PrintPagePlan`` 合成"打印效果"位图。

**只画内存位图，不写任何文件**——第四步的效果预览就是它；真正生成
PDF 仍要走「生成 PDF」按钮（functions/print.py）。

几何全部取自 ``plan``，而 ``plan`` 由 PDF 生成与预览共用，所以用户
按预览调好的边距/纸张/标题，与最终 PDF 必然一致。

---

## `desktop.workers.source_thumbnails_worker`

源码：[`desktop/workers/source_thumbnails_worker.py`](../../desktop/workers/source_thumbnails_worker.py)

导入 PDF 后逐页渲染缩略图，落盘到任务目录的 thumbnails/source/。

命名与 PDF 预览查看器的页缩略图缓存一致（{page}.jpg，0 起始），
预览打开时直接命中缓存，不再重复渲染；该目录永不清理。

### `class SourceThumbnailsWorker(QObject)`

导入 PDF 后渲染全部页面缩略图（256px，与预览查看器缓存一致）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(pdf_path: Path, out_dir: Path, edge: int=THUMBNAIL_EDGE)` | 构造源 PDF 页缩略图 worker。 |
| `run() -> None` | 逐页渲染缩略图落盘；任务目录被删时中止并报 failed。 |

##### `__init__(pdf_path: Path, out_dir: Path, edge: int=THUMBNAIL_EDGE)`

构造源 PDF 页缩略图 worker。

pdf_path 为源文件；out_dir 为 thumbnails/source/；edge 最长边
（默认 256）。缩略图命名 {page+1:04d}.jpg，与预览缓存一致。

---

## `desktop.workers.worker_host`

源码：[`desktop/workers/worker_host.py`](../../desktop/workers/worker_host.py)

WorkerHost：在拥有者 widget 内启动一次性后台 worker 线程并自动回收。

### `class WorkerHost`

Mixin：在拥有者 widget 内启动一次性后台 worker 线程。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `run_worker(factory, wire) -> None` | 启动一次性 worker 线程并登记引用以便回收。 |
| `shutdown_workers() -> None` | 退出并等待所有后台线程（最多 800ms/线程），随后清空引用。 |

##### `run_worker(factory, wire) -> None`

启动一次性 worker 线程并登记引用以便回收。

factory() 负责造 worker，wire(worker, thread) 负责连信号；线程结束后
worker 自动 deleteLater 并移出引用表，避免长会话下线程对象堆积。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `connect_queued(owner, signal, slot, thread=None) -> QObject` | worker 信号 → 主线程闭包的**唯一正确写法**，返回中继对象。 |

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

---
