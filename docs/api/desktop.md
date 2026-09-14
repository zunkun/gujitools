<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# desktop API 参考

桌面端：GUI 主进程、worker 子进程、存储、界面系统

覆盖 52 个模块、49 个公开类、221 个公开函数/方法（生成于 2026-09-15）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`desktop.app`](#desktopapp) | 1 | 2 |
| [`desktop.components.log_panel`](#desktopcomponentslog_panel) | 1 | 9 |
| [`desktop.components.panels.base`](#desktopcomponentspanelsbase) | 1 | 5 |
| [`desktop.components.panels.detect_panel`](#desktopcomponentspanelsdetect_panel) | 1 | 1 |
| [`desktop.components.panels.extract_panel`](#desktopcomponentspanelsextract_panel) | 1 | 1 |
| [`desktop.components.panels.print_form`](#desktopcomponentspanelsprint_form) | 1 | 1 |
| [`desktop.components.panels.print_nodes`](#desktopcomponentspanelsprint_nodes) | 2 | 9 |
| [`desktop.components.panels.print_panel`](#desktopcomponentspanelsprint_panel) | 1 | 6 |
| [`desktop.components.panels.print_params`](#desktopcomponentspanelsprint_params) | 0 | 5 |
| [`desktop.components.panels.rembg_panel`](#desktopcomponentspanelsrembg_panel) | 1 | 1 |
| [`desktop.components.step_bar`](#desktopcomponentsstep_bar) | 2 | 15 |
| [`desktop.components.task_table`](#desktopcomponentstask_table) | 2 | 4 |
| [`desktop.components.viewers.image_view`](#desktopcomponentsviewersimage_view) | 1 | 12 |
| [`desktop.components.viewers.image_viewer`](#desktopcomponentsviewersimage_viewer) | 1 | 6 |
| [`desktop.components.viewers.pdf_viewer`](#desktopcomponentsviewerspdf_viewer) | 1 | 2 |
| [`desktop.components.viewers.print_preview`](#desktopcomponentsviewersprint_preview) | 1 | 6 |
| [`desktop.components.viewers.rembg_viewer`](#desktopcomponentsviewersrembg_viewer) | 1 | 3 |
| [`desktop.components.viewers.thumb_strip`](#desktopcomponentsviewersthumb_strip) | 1 | 4 |
| [`desktop.components.viewers.thumbs_loader`](#desktopcomponentsviewersthumbs_loader) | 1 | 0 |
| [`desktop.pages.taskdetail.detect`](#desktoppagestaskdetaildetect) | 1 | 0 |
| [`desktop.pages.taskdetail.history`](#desktoppagestaskdetailhistory) | 1 | 0 |
| [`desktop.pages.taskdetail.manifest`](#desktoppagestaskdetailmanifest) | 1 | 2 |
| [`desktop.pages.taskdetail.page`](#desktoppagestaskdetailpage) | 1 | 5 |
| [`desktop.pages.taskdetail.print_list`](#desktoppagestaskdetailprint_list) | 1 | 0 |
| [`desktop.pages.taskdetail.runner`](#desktoppagestaskdetailrunner) | 1 | 2 |
| [`desktop.pages.taskdetail.submit`](#desktoppagestaskdetailsubmit) | 1 | 1 |
| [`desktop.pages.taskdetail.view`](#desktoppagestaskdetailview) | 1 | 0 |
| [`desktop.pages.tasklist.page`](#desktoppagestasklistpage) | 1 | 4 |
| [`desktop.services.print_plan`](#desktopservicesprint_plan) | 0 | 5 |
| [`desktop.services.submit_state`](#desktopservicessubmit_state) | 0 | 1 |
| [`desktop.stages.detect_stage`](#desktopstagesdetect_stage) | 0 | 2 |
| [`desktop.stages.events`](#desktopstagesevents) | 1 | 5 |
| [`desktop.stages.generic_stage`](#desktopstagesgeneric_stage) | 0 | 2 |
| [`desktop.stages.print_stage`](#desktopstagesprint_stage) | 0 | 1 |
| [`desktop.stages.rembg_stage`](#desktopstagesrembg_stage) | 0 | 1 |
| [`desktop.store.annotations`](#desktopstoreannotations) | 1 | 6 |
| [`desktop.store.json_io`](#desktopstorejson_io) | 0 | 2 |
| [`desktop.store.migrate`](#desktopstoremigrate) | 0 | 1 |
| [`desktop.store.pages`](#desktopstorepages) | 1 | 9 |
| [`desktop.store.runs`](#desktopstoreruns) | 1 | 6 |
| [`desktop.store.store`](#desktopstorestore) | 1 | 1 |
| [`desktop.store.tasks`](#desktopstoretasks) | 1 | 17 |
| [`desktop.ui.style`](#desktopuistyle) | 0 | 3 |
| [`desktop.ui.theme`](#desktopuitheme) | 0 | 2 |
| [`desktop.ui.widgets`](#desktopuiwidgets) | 8 | 33 |
| [`desktop.utils.files`](#desktoputilsfiles) | 0 | 5 |
| [`desktop.worker`](#desktopworker) | 0 | 1 |
| [`desktop.workers.hash_worker`](#desktopworkershash_worker) | 1 | 2 |
| [`desktop.workers.image_list_worker`](#desktopworkersimage_list_worker) | 1 | 2 |
| [`desktop.workers.preview_worker`](#desktopworkerspreview_worker) | 1 | 4 |
| [`desktop.workers.source_thumbnails_worker`](#desktopworkerssource_thumbnails_worker) | 1 | 2 |
| [`desktop.workers.worker_host`](#desktopworkersworker_host) | 1 | 2 |

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
| `build_form() -> QWidget` | 参数表单容器（子类可整体替换，如 print 面板换成滚动区）。 |
| `get_args() -> dict` | 从表单收集该阶段参数（不含 input/output/clean）。 |
| `apply_args(parameters: dict) -> None` | 把一次历史执行的参数回填到表单（多余键忽略）。 |
| `reset_to_default() -> None` | 恢复控件初始默认值。 |

##### `__init__(parent=None)`

构建面板骨架：标题 + 说明 + 参数表单容器。

title/description 来自子类类属性并开启换行，避免窄面板被长说明撑破；
随后调用 build_form 生成子类表单并占满剩余垂直空间。

##### `reset_to_default() -> None`

恢复控件初始默认值。

各子类的 ``_apply_args`` 对缺失键都取自身默认值，因此传空字典
即可复位——用于切换任务时清掉上一个任务残留的手改参数。

---

## `desktop.components.panels.detect_panel`

源码：[`desktop/components/panels/detect_panel.py`](../../desktop/components/panels/detect_panel.py)

检测文本框（detect）阶段面板：本阶段只识别坐标，不生成文件。

### `class DetectPanel(StagePanel)`

检测文本框阶段面板：仅识别坐标，不生成文件。

YOLO 检测每张图的左右文本框坐标，供预览标注与去底色/裁剪使用；
本阶段无表单参数，get_args 返回空字典，手动检测经信号触发。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 返回空参数字典（detect 阶段无表单参数）。 |

---

## `desktop.components.panels.extract_panel`

源码：[`desktop/components/panels/extract_panel.py`](../../desktop/components/panels/extract_panel.py)

提取图片阶段面板。

### `class ExtractPanel(StagePanel)`

提取图片阶段面板：设置缩放、格式与页码范围。

extract 阶段把源 PDF 每页渲染为图片；参数经 get_args 收集后由 runner
写入子进程配置，input/output 由系统接管。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 收集提取参数：zoom/ext/pages（不含 input/output）。 |

##### `get_args() -> dict`

收集提取参数：zoom/ext/pages（不含 input/output）。

pages 留空表示全部页；非法页码由 runner 在取参时以 ValueError 拦截。

---

## `desktop.components.panels.print_form`

源码：[`desktop/components/panels/print_form.py`](../../desktop/components/panels/print_form.py)

生成 PDF（print）阶段的表单构建 Mixin：控件创建、标题切换节点表、焦点策略。

参数定义/解析见 print_params.py，面板状态见 print_panel.py。

### `class PrintFormMixin`

print 面板的表单构建（由 PrintPanel 继承）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `build_form() -> QWidget` | 构建 print 面板表单：滚动区 + 各分区控件 + 节点表。 |

##### `build_form() -> QWidget`

构建 print 面板表单：滚动区 + 各分区控件 + 节点表。

用 ScrollArea 承载全部分区（输出/边距/标题/页码/过滤），顶部放恢复
默认/重置按钮，构建后连接 pdf_name 与 title 联动信号；焦点策略延后到
面板 __init__ 末尾统一设置。

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

表单控件构建见 print_form.py，参数定义/解析见 print_params.py。
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
| `reset_to_default() -> None` | 恢复为该面板的内置默认参数（不依赖任何历史执行）。 |
| `reset_edits() -> None` | 撤销本次修改：恢复到最近一次执行的参数。 |
| `mark_applied(parameters: dict) -> None` | 记录最近一次执行使用的参数（供「重置」恢复）。 |
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

##### `reset_edits() -> None`

撤销本次修改：恢复到最近一次执行的参数。

与 reset_to_default（恢复内置默认）不同，本方法回到 mark_applied
记录的上一轮执行参数；若从未执行过则退化为恢复默认。

##### `get_args() -> dict`

收集 PDF 生成参数（校验颜色/边距，缺省回落内置默认）。

input/output/workers/clean 不在此列；颜色或边距非法会抛 ValueError
阻止执行；title_switch_nodes 取节点行、skip_pages 解析为文件名列表。

---

## `desktop.components.panels.print_params`

源码：[`desktop/components/panels/print_params.py`](../../desktop/components/panels/print_params.py)

生成 PDF（print）阶段的参数定义与解析/序列化纯函数。

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

## `desktop.components.panels.rembg_panel`

源码：[`desktop/components/panels/rembg_panel.py`](../../desktop/components/panels/rembg_panel.py)

图片去底色（rembg）阶段面板：area 决定裁剪方式，border 决定四周留白。

### `class RembgPanel(StagePanel)`

图片去底色阶段面板：area/border/印章等参数。

整图 Otsu 二值化/灰度化去底（可保留印章）；area 决定裁剪方式、
border 决定四周留白，参数经 get_args 收集后传给子进程。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `get_args() -> dict` | 收集去底色参数：area/type/offset/seal/border 等。 |

##### `get_args() -> dict`

收集去底色参数：area/type/offset/seal/border 等。

area/type 取下拉首字符数字；border 留空表示 0，由 runner 在续跑时
与 detect 框坐标实时合成裁剪区域。

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

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 初始化表格：5 列布局、行高与表头对齐。 |
| `set_data(rows: list[dict]) -> None` | rows: [{id, name, source_path, created_at, stages}] |
| `select_task(task_id: str) -> bool` | 选中并滚动到指定任务所在行，返回是否找到。 |

##### `__init__(parent=None)`

初始化表格：5 列布局、行高与表头对齐。

表头对齐跟随各列内容（序号/时间居中、名称/状态左对齐）；
子任务状态列自适应拉伸，其余列按 _COLUMN_WIDTHS 固定宽度。

##### `set_data(rows: list[dict]) -> None`

rows: [{id, name, source_path, created_at, stages}]

stages 为 ``[{"short": "提取", "status": "success", "tip": "..."}]``；
source_path 不单独成列，仅作任务名的悬浮提示。

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

## `desktop.components.viewers.print_preview`

源码：[`desktop/components/viewers/print_preview.py`](../../desktop/components/viewers/print_preview.py)

生成 PDF 预览：图片列表（IconMode 流式排列）。

展示待打印图片列表（第三步「提交本次任务」产出的最终图片），
支持拖动排序、删除选中、插入图片；仅操作列表数据，不生成/删除图片文件。

### `class PrintPreviewWidget(QWidget, WorkerHost)`

生成 PDF 页面列表：可拖动排序、删除选中、请求插入。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(empty_hint: str='暂无图片，请先完成去底色', parent=None)` | 构建待打印列表与空状态占位。 |
| `set_entries(entries: list[dict]) -> None` | 重建列表：entries = [{file, label}]。 |
| `entries() -> list[dict]` | 当前视觉顺序的富条目列表。 |
| `count() -> int` | 列表当前条目数。 |
| `set_pdf_path(path: str \| Path \| None) -> None` | 设置已生成 PDF 的路径；存在则启用下载按钮，否则禁用。 |
| `remove_selected() -> None` | 删除所有选中条目，未选中则通过 hint 信号提示。 |

##### `__init__(empty_hint: str='暂无图片，请先完成去底色', parent=None)`

构建待打印列表与空状态占位。

列表开启 InternalMove 以支持拖动排序；提示类反馈通过 hint 信号
交给宿主弹 toast，而不是在控件内直接弹窗。

##### `remove_selected() -> None`

删除所有选中条目，未选中则通过 hint 信号提示。

多选用 ExtendedSelection，按行倒序移除避免下标错位；删除后同步
缓存顺序并 emit order_changed。

---

## `desktop.components.viewers.rembg_viewer`

源码：[`desktop/components/viewers/rembg_viewer.py`](../../desktop/components/viewers/rembg_viewer.py)

去底色预览：单视图显示，去底色结果优先，顶部可切换查看原图。

左侧缩略图条按"输出条目"组织：
- area=1：每个文本框一条（标签 <页>-l / <页>-r），右侧显示该框 + border 区域；
- area=2/3：每页一条，右侧显示按 crop/cropremove 规则合成的效果区域。

区域合成在 worker 线程完成，不生成文件；通过请求令牌避免快速切换串台。

### 模块常量

| 名称 | 值 |
| --- | --- |
| _ACTIVE_STYLE | `" PushButton {     background-color: #0078d4;     color: w…"` |

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

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(parent=None)` | 初始化条目尺寸与流式布局；点击条目发出 current_path_changed(行号, 路径)。 |
| `add_placeholder(text: str) -> None` | 追加一个纯文字占位条目（无图标，如"缩略图加载中…"）。 |
| `add_page_item(label: str, path: str='') -> None` | 新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。 |
| `set_item_icon(index: int, image, path: str, label: str) -> None` | 替换某条目的图标/文字/路径（缩略图异步就绪后回调）。 |

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
- history.HistoryMixin       历史执行配置回填
- submit.SubmitMixin         rembg 提交控制器与按钮状态
- print_list.PrintListMixin  第四步待打印列表
- runner.StageRunnerMixin    阶段执行（worker 子进程编排）
- detect.DetectMixin         detect 检测控制

### `class TaskDetailPage(StageRunnerMixin, SubmitMixin, PrintListMixin, HistoryMixin, DetectMixin, PageListMixin, DetailViewMixin, QWidget, WorkerHost)`

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

任务管理页：列表展示任务并支持导入 PDF 与删除。

含表格/空状态二选一的内容区；导入走「后台算指纹→查重→确认建任务」
流程，缩略图另行后台生成，全程不阻塞界面。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(store: TaskStore, parent=None)` | 初始化页面：构建 UI、绑定信号并刷新首次列表。 |
| `refresh() -> None` | 重建任务表格与状态摘要，并切换空状态。 |
| `import_pdf() -> None` | 导入 PDF：选文件后后台算指纹并查重确认建任务。 |
| `delete_task(task_id: str) -> None` | 删除指定任务及其全部中间产物（带确认弹窗）。 |

##### `__init__(store: TaskStore, parent=None)`

初始化页面：构建 UI、绑定信号并刷新首次列表。

parent 一般为 MainWindow；会创建 store 引用与导入按钮状态占位，
随后调用 refresh 重建表格与空状态。

##### `refresh() -> None`

重建任务表格与状态摘要，并切换空状态。

遍历各任务取四个阶段的 status/done/total 生成摘要行，列表为空时
切到空状态卡片，并更新底部数据目录提示文案。

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
- area=2/3 双框：取双框并集，单条输出；
- 单框：area=2/3 走对称画布（parea=2），area=1 按普通框；
- 无框：整页预览图透传。
最终按 CLI natural sort 排序（同页 r 在 l 前）。

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

最终裁剪框由 GUI 按同一套规则（utils.box_geometry.compute_final_boxes）
从检测框实时推导，用于预览标注。

---

## `desktop.stages.events`

源码：[`desktop/stages/events.py`](../../desktop/stages/events.py)

worker 子进程的事件输出层。

- emit：向 GUI 输出一条 JSON Lines 事件；
- ProgressStream：拦截功能模块的 print 输出，解析进度并转发日志。

The worker emits JSON Lines on stdout so the GUI remains independent from heavy
libraries. While the stage function runs, sys.stdout is intercepted so that:
- progress messages produced by functions/* (处理完成 / 进度: d/t / 写入进度 等)
  are converted into {"type": "progress"} events;
- every other text line is forwarded as {"type": "log"} events for the GUI log view.

### `class ProgressStream(io.TextIOBase)`

拦截功能模块的 print 输出，解析进度并转发日志。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(real_stdout, context: dict)` | real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到 |
| `writable() -> bool` | 恒为 True：本流始终接受写入。 |
| `write(text: str) -> int` | 按换行或回车切分输出边界，逐行解析成事件；返回本次写入的字符数（满足 io.TextIOBase 约定）。 |
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
| `run_extract_stage(config: dict) -> int` | extract 阶段：直接把 PDF 渲染到任务目录 stages/extract/（无嵌套布局）。 |

#### `run_stage(config: dict) -> int`

在子进程中执行一个 CLI 功能阶段，返回进程退出码（0/130/1）。

config 需含 task_id/stage/run_id/args。期间用 ProgressStream 拦截
功能模块的 print 输出并转为进度/日志事件；通过 args['_outpath']
可覆盖功能模块计算出的输出目录。异常以 error 事件回报，不抛到上层。

#### `run_extract_stage(config: dict) -> int`

extract 阶段：直接把 PDF 渲染到任务目录 stages/extract/（无嵌套布局）。

复用 utils.pdf_utils.process_page_batch 的渲染/并发实现，
但不走 CLI 的 <out_root>/<pdf名>/images 输出规则。

---

## `desktop.stages.print_stage`

源码：[`desktop/stages/print_stage.py`](../../desktop/stages/print_stage.py)

print 阶段执行器：先在子进程内合成效果图（顺序编号），再用 CLI print 生成 PDF。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `run_print_stage(config: dict) -> int` | print 阶段：先在子进程内把 rembg 结果按 area/border 合成为 |

#### `run_print_stage(config: dict) -> int`

print 阶段：先在子进程内把 rembg 结果按 area/border 合成为
效果图（顺序编号），再用 CLI print 生成 PDF。

效果合成放在子进程而非 GUI 线程：既不阻塞界面，也避免
GUI 侧 QProcess 从回调链启动时 Windows 下通知丢失的问题。
args["_effects"] = [{"file": rembg结果, "effect": {boxes,area,border}|None}, …]

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
但结果是持久化的交付图片而非临时 workset，且不再生成 PDF。

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
image_key 取页面文件名去后缀（stem），workset 副本与 extract 清单里的
同名页面共享同一份数据。

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

## `desktop.store.migrate`

源码：[`desktop/store/migrate.py`](../../desktop/store/migrate.py)

旧数据一次性迁移：SQLite（guji.db）与旧目录布局 → 纯文件 + 新目录布局。

旧布局：
- 数据根目录 guji.db（tasks / stage_runs / stage_settings / detect_boxes / image_meta 表）
- 任务目录：stages/extract/<pdf名>/images、stages/detect（旧 crop 切图）、
  previews/（PDF 预览缓存）、imported/（手动插入图片）、logs/、
  根下散落的 run-*.json / detect-config.json

迁移规则：
- SQLite 各表 → tasks.json / runs.json / boxes.json / sizes.json，完成后
  guji.db 改名为 guji.db.migrated 保留备份；
- stages/extract/<pdf名>/images/* 上移到 stages/extract/；
- stages/detect、previews、logs 删除（可重新生成或已无用）；
- imported/* 的图片移到 stages/extract/，pages.json 中对应路径同步改写；
- run-*.json / detect-config.json 移入 runs/ 子目录。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `migrate_legacy(root: Path) -> None` | 一次性迁移旧数据（SQLite + 旧目录布局）→ 纯文件新布局。 |

#### `migrate_legacy(root: Path) -> None`

一次性迁移旧数据（SQLite + 旧目录布局）→ 纯文件新布局。

存在 guji.db 时导出 tasks/runs/boxes/sizes 的 JSON 并改名
guji.db.migrated 备份；uuid 任务目录重编号为 0001… 顺序号；
旧嵌套 extract、散落配置等按本模块规则归位。迁移失败（sqlite3.Error）
不抛异常，旧库保留、启动不阻塞。

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
| `finish_stage(task_id: str, run_id: str, status: str, output_path: str \| None=None) -> None` | 结束某次运行：写入 status/finished_at/output_path。 |
| `list_stage_runs(task_id: str, stage: str) -> list[dict]` | 某阶段的历史执行记录，最新在前。 |
| `stage_states(task_id: str) -> dict[str, dict]` | 每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。 |

##### `create_stage_run(task_id: str, stage: str, parameters: dict, resume: bool=False) -> str`

登记一次新的阶段执行并返回 run_id。

新记录插在该阶段历史最前，初始状态 running、进度 0/0；每阶段只保留
最近 MAX_RUN_HISTORY 条。resume 标记本次是否为续跑。

##### `finish_stage(task_id: str, run_id: str, status: str, output_path: str | None=None) -> None`

结束某次运行：写入 status/finished_at/output_path。

status 取 success/failed/cancelled 等；output_path 为该次执行的
主产物路径（如 print.pdf、rembg 输出目录），供历史面板回链。
任务目录已删除时静默跳过。

##### `stage_states(task_id: str) -> dict[str, dict]`

每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。

``status/done/total`` 取自最近一次运行；``completed`` 表示该阶段历史上
是否成功执行过——重试失败不应把已经产出结果的步骤变回未完成。

---

## `desktop.store.store`

源码：[`desktop/store/store.py`](../../desktop/store/store.py)

TaskStore：任务、阶段、页面标注的统一文件存储入口。

### `class TaskStore(TaskMixin, RunMixin, PageManifestMixin, AnnotationMixin)`

唯一数据入口：组合任务/运行/页面/标注四个 Mixin，统一读写文件存储。

数据根目录下含 tasks/（每任务一子目录）及各 JSON 清单
（tasks.json/runs.json/boxes.json/sizes.json/pages.json/print.json）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(root: Path \| None=None)` | 初始化数据根。 |

##### `__init__(root: Path | None=None)`

初始化数据根。

root 省略时默认用 guji_data_dir()（~/Documents/guji）；传入自定义
root 主要用于测试隔离。构造时确保 tasks/ 存在并自动执行旧数据迁移。

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
| `delete_task(task_id: str) -> None` | 从索引移除任务并删除整个任务目录；目录不存在时只改索引。 |
| `task_dir(task_id: str) -> Path` | 任务根目录：tasks/<任务号>。 |
| `stage_dir(task_id: str, stage: str) -> Path` | 某阶段的输出目录：tasks/<任务号>/stages/<阶段>。 |
| `extract_output_dir(task_id: str) -> Path` | 提取图片直接位于 stages/extract（无 PDF 名/嵌套子目录）。 |
| `rembg_output_dir(task_id: str) -> Path` | 步骤三最终图片目录（「提交本次任务」产出，print 阶段从此取图）。 |
| `rembg_preview_output_dir(task_id: str) -> Path` | 「生成预览」产出的整页去底预览图目录（中间产物，不参与 print）。 |
| `print_output_pdf(task_id: str) -> Path` | print 阶段产物 print.pdf 的完整路径。 |
| `stage_output_dir(task_id: str, stage: str) -> Path` | 返回某阶段（GUI）应写入的输出目录。 |
| `workset_dir(task_id: str) -> Path` | 阶段执行的输入物化目录（用硬链接指向源图，不复制文件）。 |
| `runs_config_dir(task_id: str) -> Path` | 子进程执行配置（run-*.json / detect-config.json）。 |
| `source_thumbnails_dir(task_id: str) -> Path` | 源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。 |
| `copy_source_to_task(task_id: str, source_path: Path) -> Path` | 导入时在任务目录下保留一份源文件副本。 |

##### `create_task(source_path: Path, source_hash: str, name: str, duplicate_confirmed: bool=False) -> str`

新建任务并返回任务号（四位零填充）。

任务号取当前最大号 +1，同时参考索引与磁盘目录；若两者不一致导致号被
占用则继续顺延。创建时会预建 stages/workset/runs/thumbnails/source
子目录，但不复制源文件（由 copy_source_to_task 负责）。

##### `stage_output_dir(task_id: str, stage: str) -> Path`

返回某阶段（GUI）应写入的输出目录。

注意 rembg 阶段返回 rembgpreview 预览目录，rembg_submit 才指向
rembg 最终目录；print 返回 print.pdf 所在目录。

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
| FONT_FAMILY | `"Microsoft YaHei UI"` |
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

### 模块常量

| 名称 | 值 |
| --- | --- |
| _FONT_FAMILY | `None` |

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
| `ui_font(size: int=T.SIZE_BODY, bold: bool=False) -> QFont` | 统一的界面字体（族名 + 像素字号）。 |
| `apply_to(widget: QWidget, size: int=T.SIZE_BODY, bold: bool=False, color: str \| None=None) -> QLabel` | 给 QLabel 统一设置字体与颜色（颜色用调色板，不用样式表）。 |
| `icon_pixmap(icon, size: int=24, color: str=T.INK_FAINT) -> QPixmap` | 把 FluentIcon 渲染成指定颜色的 pixmap（用于空状态插画）。 |

#### `ui_font(size: int=T.SIZE_BODY, bold: bool=False) -> QFont`

统一的界面字体（族名 + 像素字号）。

族名走 ``resolve_font_family()`` 解析出的系统实际字体，与
``apply_app_style`` 给整个应用设置的字体保持一致；否则在没有
``Microsoft YaHei UI`` 的机器上，这些控件会各自回退到默认字体，
和应用其它文字对不上。

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
| `file_hash(path: Path, chunk_size: int=1024 * 1024) -> str` | 流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。 |
| `natural_key(name: str)` | 生成自然排序键：数字段按整数、其余转小写，使 2 排在 10 前。 |
| `list_stage_images(directory: Path) -> list[Path]` | 某阶段输出目录中的图片（自然排序）。 |

#### `project_root() -> Path`

项目根目录（`desktop` 包的上一级）。

源码模式下 worker 子进程用 `-m desktop.worker` 启动，工作目录必须是
能解析出 `desktop` 包的那一级；用本函数取，避免依赖某个文件的层数
（文件挪一层就会算错）。

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
| SYMMETRIC_GAP_MM | `10` |

### `class PreviewWorker(QObject)`

渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。

#### 方法

| 方法 | 说明 |
| --- | --- |
| `__init__(path: Path, page: int=0, longest_edge: int \| None=1200, thumbnails: bool=False, cache_dir: Path \| None=None, effect: dict \| None=None)` | 构造预览渲染 worker。 |
| `run() -> None` | 按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。 |

##### `__init__(path: Path, page: int=0, longest_edge: int | None=1200, thumbnails: bool=False, cache_dir: Path | None=None, effect: dict | None=None)`

构造预览渲染 worker。

PDF 渲染第 page 页（最长边 longest_edge，0 表示不缩放）；
thumbnails=True 时渲染全部页缩略图到 cache_dir（命中则复用缓存）。
effect 为去底色合成参数 {boxes, area, border}，仅对单图生效。

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300) -> list` | 按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。 |
| `compose_outputs_horizontal(outputs: list, gap: int=12) -> QImage` | 多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。 |

#### `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300) -> list`

按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

与 functions/text_region.py 的输出几何完全一致：
- area=1：每个文本框各一张（框 + border，border 缺省为 0）；
- area=2 双框：并集画布 + border，两框内容按原位置粘贴，
  **框之间的内容丢弃（留白）**；
- area=3 双框：并集区域**整块**作为一个 ROI 取出（框间内容保留）+ border；
- area=2/3 单框：对称画布（框宽×2 + 10mm 间隔，内容在一侧）；
- area=2/3 border 未填：整页尺寸画布，仅框内（area=3 为并集内）保留内容。

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

---
