<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# desktop API 参考

桌面端：GUI 主进程、worker 子进程、存储、界面系统

覆盖 112 个模块、127 个公开类、878 个公开函数/方法（生成于 2026-10-03）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块                                                                                             | 类  | 函数 |
| ------------------------------------------------------------------------------------------------ | --- | ---- |
| [`desktop.app`](#desktopapp)                                                                     | 1   | 8    |
| [`desktop.components.common.safecomment`](#desktopcomponentscommonsafecomment)                   | 6   | 12   |
| [`desktop.components.detect_stats`](#desktopcomponentsdetect_stats)                              | 1   | 4    |
| [`desktop.components.imposition.canvas`](#desktopcomponentsimpositioncanvas)                     | 1   | 26   |
| [`desktop.components.imposition.confirm_delete`](#desktopcomponentsimpositionconfirm_delete)     | 1   | 1    |
| [`desktop.components.imposition.page_list`](#desktopcomponentsimpositionpage_list)               | 1   | 9    |
| [`desktop.components.imposition.panel`](#desktopcomponentsimpositionpanel)                       | 1   | 7    |
| [`desktop.components.imposition.picker`](#desktopcomponentsimpositionpicker)                     | 1   | 9    |
| [`desktop.components.imposition.view`](#desktopcomponentsimpositionview)                         | 1   | 11   |
| [`desktop.components.log_panel`](#desktopcomponentslog_panel)                                    | 1   | 9    |
| [`desktop.components.pagination`](#desktopcomponentspagination)                                  | 2   | 11   |
| [`desktop.components.panels.base`](#desktopcomponentspanelsbase)                                 | 1   | 7    |
| [`desktop.components.panels.detect_panel`](#desktopcomponentspanelsdetect_panel)                 | 1   | 3    |
| [`desktop.components.panels.extract_panel`](#desktopcomponentspanelsextract_panel)               | 1   | 1    |
| [`desktop.components.panels.params_spec`](#desktopcomponentspanelsparams_spec)                   | 0   | 2    |
| [`desktop.components.panels.print_form`](#desktopcomponentspanelsprint_form)                     | 1   | 1    |
| [`desktop.components.panels.print_inset`](#desktopcomponentspanelsprint_inset)                   | 1   | 0    |
| [`desktop.components.panels.print_nodes`](#desktopcomponentspanelsprint_nodes)                   | 2   | 9    |
| [`desktop.components.panels.print_panel`](#desktopcomponentspanelsprint_panel)                   | 1   | 9    |
| [`desktop.components.panels.print_params`](#desktopcomponentspanelsprint_params)                 | 0   | 5    |
| [`desktop.components.panels.print_sections`](#desktopcomponentspanelsprint_sections)             | 1   | 0    |
| [`desktop.components.panels.print_text_layout`](#desktopcomponentspanelsprint_text_layout)       | 1   | 0    |
| [`desktop.components.panels.rembg_panel`](#desktopcomponentspanelsrembg_panel)                   | 1   | 1    |
| [`desktop.components.progress_row`](#desktopcomponentsprogress_row)                              | 1   | 8    |
| [`desktop.components.step_bar`](#desktopcomponentsstep_bar)                                      | 2   | 18   |
| [`desktop.components.task_table`](#desktopcomponentstask_table)                                  | 3   | 10   |
| [`desktop.components.viewers.image_editor`](#desktopcomponentsviewersimage_editor)               | 3   | 83   |
| [`desktop.components.viewers.image_view`](#desktopcomponentsviewersimage_view)                   | 1   | 23   |
| [`desktop.components.viewers.image_viewer`](#desktopcomponentsviewersimage_viewer)               | 1   | 18   |
| [`desktop.components.viewers.image_zoom_dialog`](#desktopcomponentsviewersimage_zoom_dialog)     | 4   | 34   |
| [`desktop.components.viewers.pdf_viewer`](#desktopcomponentsviewerspdf_viewer)                   | 1   | 2    |
| [`desktop.components.viewers.print_layout_canvas`](#desktopcomponentsviewersprint_layout_canvas) | 1   | 12   |
| [`desktop.components.viewers.print_preview`](#desktopcomponentsviewersprint_preview)             | 1   | 11   |
| [`desktop.components.viewers.rembg_viewer`](#desktopcomponentsviewersrembg_viewer)               | 1   | 12   |
| [`desktop.components.viewers.thumb_strip`](#desktopcomponentsviewersthumb_strip)                 | 1   | 10   |
| [`desktop.components.viewers.thumbs_loader`](#desktopcomponentsviewersthumbs_loader)             | 1   | 1    |
| [`desktop.modules`](#desktopmodules)                                                             | 1   | 1    |
| [`desktop.modules.base`](#desktopmodulesbase)                                                    | 2   | 19   |
| [`desktop.modules.detect.page`](#desktopmodulesdetectpage)                                       | 1   | 7    |
| [`desktop.modules.extract.page`](#desktopmodulesextractpage)                                     | 1   | 4    |
| [`desktop.modules.imposition.page`](#desktopmodulesimpositionpage)                               | 1   | 4    |
| [`desktop.modules.print.page`](#desktopmodulesprintpage)                                         | 1   | 4    |
| [`desktop.modules.rembg.page`](#desktopmodulesrembgpage)                                         | 1   | 5    |
| [`desktop.modules.shell`](#desktopmodulesshell)                                                  | 1   | 15   |
| [`desktop.modules.thumb_source`](#desktopmodulesthumb_source)                                    | 1   | 4    |
| [`desktop.pages.taskdetail.detect`](#desktoppagestaskdetaildetect)                               | 1   | 0    |
| [`desktop.pages.taskdetail.history`](#desktoppagestaskdetailhistory)                             | 1   | 0    |
| [`desktop.pages.taskdetail.imposition`](#desktoppagestaskdetailimposition)                       | 2   | 4    |
| [`desktop.pages.taskdetail.imposition_layout`](#desktoppagestaskdetailimposition_layout)         | 1   | 1    |
| [`desktop.pages.taskdetail.imposition_pages`](#desktoppagestaskdetailimposition_pages)           | 1   | 0    |
| [`desktop.pages.taskdetail.manifest`](#desktoppagestaskdetailmanifest)                           | 1   | 2    |
| [`desktop.pages.taskdetail.page`](#desktoppagestaskdetailpage)                                   | 1   | 8    |
| [`desktop.pages.taskdetail.params_draft`](#desktoppagestaskdetailparams_draft)                   | 1   | 1    |
| [`desktop.pages.taskdetail.print_list`](#desktoppagestaskdetailprint_list)                       | 1   | 1    |
| [`desktop.pages.taskdetail.rembg_live`](#desktoppagestaskdetailrembg_live)                       | 1   | 0    |
| [`desktop.pages.taskdetail.runner`](#desktoppagestaskdetailrunner)                               | 1   | 2    |
| [`desktop.pages.taskdetail.submit`](#desktoppagestaskdetailsubmit)                               | 1   | 1    |
| [`desktop.pages.taskdetail.view`](#desktoppagestaskdetailview)                                   | 2   | 4    |
| [`desktop.pages.tasklist.page`](#desktoppagestasklistpage)                                       | 1   | 6    |
| [`desktop.services.detect_export`](#desktopservicesdetect_export)                                | 0   | 3    |
| [`desktop.services.font_catalog`](#desktopservicesfont_catalog)                                  | 1   | 6    |
| [`desktop.services.imposition`](#desktopservicesimposition)                                      | 0   | 20   |
| [`desktop.services.print_plan`](#desktopservicesprint_plan)                                      | 0   | 5    |
| [`desktop.services.rembg_live`](#desktopservicesrembg_live)                                      | 0   | 3    |
| [`desktop.services.stale_chain`](#desktopservicesstale_chain)                                    | 0   | 3    |
| [`desktop.services.submit_state`](#desktopservicessubmit_state)                                  | 0   | 1    |
| [`desktop.single_instance`](#desktopsingle_instance)                                             | 0   | 3    |
| [`desktop.stages.detect_stage`](#desktopstagesdetect_stage)                                      | 0   | 2    |
| [`desktop.stages.events`](#desktopstagesevents)                                                  | 2   | 9    |
| [`desktop.stages.generic_stage`](#desktopstagesgeneric_stage)                                    | 0   | 2    |
| [`desktop.stages.print_stage`](#desktopstagesprint_stage)                                        | 0   | 3    |
| [`desktop.stages.rembg_stage`](#desktopstagesrembg_stage)                                        | 0   | 1    |
| [`desktop.steps.control`](#desktopstepscontrol)                                                  | 1   | 11   |
| [`desktop.steps.kernel`](#desktopstepskernel)                                                    | 5   | 11   |
| [`desktop.steps.ports`](#desktopstepsports)                                                      | 0   | 14   |
| [`desktop.steps.process`](#desktopstepsprocess)                                                  | 1   | 7    |
| [`desktop.steps.source_zone`](#desktopstepssource_zone)                                          | 1   | 20   |
| [`desktop.steps.spec`](#desktopstepsspec)                                                        | 1   | 21   |
| [`desktop.store.annotations`](#desktopstoreannotations)                                          | 1   | 9    |
| [`desktop.store.drafts`](#desktopstoredrafts)                                                    | 1   | 5    |
| [`desktop.store.imposition`](#desktopstoreimposition)                                            | 1   | 4    |
| [`desktop.store.json_io`](#desktopstorejson_io)                                                  | 0   | 2    |
| [`desktop.store.pages`](#desktopstorepages)                                                      | 1   | 9    |
| [`desktop.store.runs`](#desktopstoreruns)                                                        | 1   | 7    |
| [`desktop.store.store`](#desktopstorestore)                                                      | 1   | 1    |
| [`desktop.store.tasks`](#desktopstoretasks)                                                      | 1   | 23   |
| [`desktop.store.ui_state`](#desktopstoreui_state)                                                | 1   | 6    |
| [`desktop.ui.color_picker`](#desktopuicolor_picker)                                              | 5   | 30   |
| [`desktop.ui.font_setup`](#desktopuifont_setup)                                                  | 2   | 8    |
| [`desktop.ui.fonts`](#desktopuifonts)                                                            | 0   | 2    |
| [`desktop.ui.help_dialog`](#desktopuihelp_dialog)                                                | 0   | 6    |
| [`desktop.ui.icons`](#desktopuiicons)                                                            | 2   | 5    |
| [`desktop.ui.segmented_toggle`](#desktopuisegmented_toggle)                                      | 1   | 11   |
| [`desktop.ui.style`](#desktopuistyle)                                                            | 0   | 3    |
| [`desktop.ui.theme`](#desktopuitheme)                                                            | 0   | 3    |
| [`desktop.ui.widgets`](#desktopuiwidgets)                                                        | 9   | 42   |
| [`desktop.ui.window_size`](#desktopuiwindow_size)                                                | 0   | 3    |
| [`desktop.utils.files`](#desktoputilsfiles)                                                      | 0   | 15   |
| [`desktop.utils.icon`](#desktoputilsicon)                                                        | 0   | 3    |
| [`desktop.worker`](#desktopworker)                                                               | 0   | 1    |
| [`desktop.workers.copy_source_worker`](#desktopworkerscopy_source_worker)                        | 2   | 4    |
| [`desktop.workers.hash_worker`](#desktopworkershash_worker)                                      | 1   | 2    |
| [`desktop.workers.image_list_worker`](#desktopworkersimage_list_worker)                          | 1   | 2    |
| [`desktop.workers.imposition_worker`](#desktopworkersimposition_worker)                          | 2   | 4    |
| [`desktop.workers.preview_worker`](#desktopworkerspreview_worker)                                | 1   | 11   |
| [`desktop.workers.rembg_live_worker`](#desktopworkersrembg_live_worker)                          | 1   | 3    |
| [`desktop.workers.render_lock`](#desktopworkersrender_lock)                                      | 0   | 1    |
| [`desktop.workers.serial_jobs`](#desktopworkersserial_jobs)                                      | 1   | 9    |
| [`desktop.workers.source_thumbnails_worker`](#desktopworkerssource_thumbnails_worker)            | 1   | 4    |
| [`desktop.workers.task_rows_worker`](#desktopworkerstask_rows_worker)                            | 1   | 2    |
| [`desktop.workers.thumb_cache_worker`](#desktopworkersthumb_cache_worker)                        | 1   | 9    |
| [`desktop.workers.worker_host`](#desktopworkersworker_host)                                      | 1   | 4    |

---

## `desktop.app`

源码：[`desktop/app.py`](../../desktop/app.py)

gujitools 桌面端主窗口：左侧导航壳层（任务管理 + 独立模块）。

### 模块常量

| 名称                   | 值           |
| ---------------------- | ------------ |
| WINDOW_TITLE           | `"古籍重製"` |
| CONTENT_MIN_WIDTH      | `1080`       |
| WINDOW_START_MAXIMIZED | `True`       |

### `class MainWindow(QMainWindow)`

主窗口：左侧导航壳层（任务管理 + 独立模块）与详情页跳转。

2026-10-02 起，窗口中央从「列表页/详情页两页对切」升级为
:class:`desktop.modules.shell.ModuleShell`：左边一条 qfluentwidgets
导航栏，右边页面栈。任务管理仍是首页，其余是彼此独立的工具模块
（图片提取 / 去底色 / 拼图）。

⚠️ **对外的属性名一个都没变**：`list_page` / `detail_page` / `pages`
/ `store` 全部转发给壳层同名成员（见下面几个 property）。`tests/gui_shot.py`
与 `tests/selftests/_context.py` 都按这些名字取页面操作控件，转发一层
既升级了布局、又不改测试契约。

#### 方法

| 方法                           | 说明                                                               |
| ------------------------------ | ------------------------------------------------------------------ |
| `store()`                      | 任务存储：转发壳层（壳层与各页面各自持有引用，见 setter 的说明）。 |
| `store(value) -> None`         | 整体换掉数据目录（测试/截图脚本把 store 指向临时目录时用）。       |
| `pages()`                      | 页面栈（`QStackedWidget`）：转发给壳层，兼容既有调用点。           |
| `list_page()`                  | 任务列表页：转发给壳层。                                           |
| `detail_page()`                | 详情页实例（惰性构造）：转发给壳层。                               |
| `keyPressEvent(event) -> None` | ←/→ 转发给壳层（详情页翻页）。                                     |
| `closeEvent(event) -> None`    | 关闭窗口时让壳层收尾所有 worker 子进程与后台线程。                 |

##### `store(value) -> None`

装饰器：`store.setter`

整体换掉数据目录（测试/截图脚本把 store 指向临时目录时用）。

⚠️ 赋值必须**传到壳层**，不能只改 MainWindow 自己：壳层存了一份（惰性
详情页构造时取它）、列表页存了一份、已建出来的详情页又存了一份。只改
这里的话，惰性构造的详情页会继续读**真实数据目录**——表现是"打开的是
同名任务号的另一个任务"（`tests/selftests/last_stage.py` 实测）：
它给 MainWindow 换 store 后 `_restore_last_task` 打开 0001，而详情页
拿的是真实目录里的 0001，于是落到了那台机器上真正停留的步骤。

##### `detail_page()`

装饰器：`property`

详情页实例（惰性构造）：转发给壳层。

读它本身就等于声明「现在就需要详情页」，因此访问即构造——与启动期
惰性并不冲突。

##### `keyPressEvent(event) -> None`

←/→ 转发给壳层（详情页翻页）。

⚠️ 点击预览大图（QLabel 默认不收焦点）后，焦点落在**主窗口本身**，
按键只会到这里——不转发的话，用户点完图片按左右毫无反应
（用户 18:29 实测）。转发实现见 ModuleShell.keyPressEvent。

##### `closeEvent(event) -> None`

关闭窗口时让壳层收尾所有 worker 子进程与后台线程。

壳层会把收尾分发给任务列表页、懒建的详情页与已构造的模块页；
详情页持有 worker 子进程与后台线程的引用，直接退出会让进程被强杀。

### 模块函数

| 函数            | 说明                                                  |
| --------------- | ----------------------------------------------------- |
| `main() -> int` | 创建 QApplication、套用样式并显示主窗口，返回退出码。 |

#### `main() -> int`

创建 QApplication、套用样式并显示主窗口，返回退出码。

设环境变量 `GUJI_GUI_SELFTEST=1` 时，主窗口构造并短暂跑过事件循环后
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

| 方法                    | 说明                                |
| ----------------------- | ----------------------------------- |
| `__init__(parent=None)` | —                                   |
| `enterEvent(event)`     | Qt 事件覆写：鼠标移入时进入高亮态。 |
| `wheelEvent(event)`     | Qt 事件覆写：滚轮（缩放 / 滚动）。  |

### `class SafeSpinBox(SpinBox)`

QFluentWidgets 整数SpinBox，修复悬浮滚轮修改数值

#### 方法

| 方法                    | 说明                               |
| ----------------------- | ---------------------------------- |
| `__init__(parent=None)` | —                                  |
| `wheelEvent(event)`     | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeDoubleSpinBox(DoubleSpinBox)`

QFluentWidgets 浮点数SpinBox（用于带 mm 单位边距控件）

#### 方法

| 方法                    | 说明                               |
| ----------------------- | ---------------------------------- |
| `__init__(parent=None)` | —                                  |
| `wheelEvent(event)`     | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeCompactSpinBox(CompactSpinBox)`

QFluentWidgets 紧凑版整数SpinBox

#### 方法

| 方法                    | 说明                               |
| ----------------------- | ---------------------------------- |
| `__init__(parent=None)` | —                                  |
| `wheelEvent(event)`     | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class SafeCompactDoubleSpinBox(CompactDoubleSpinBox)`

QFluentWidgets 紧凑版浮点数SpinBox

#### 方法

| 方法                    | 说明                               |
| ----------------------- | ---------------------------------- |
| `__init__(parent=None)` | —                                  |
| `wheelEvent(event)`     | Qt 事件覆写：滚轮（缩放 / 滚动）。 |

### `class FluentSpinWheelFilter(QObject)`

全局事件过滤器（存量界面不想替换控件类时使用）
一次性拦截所有 fluent spinbox 无焦点滚轮事件
使用：
\_filter = FluentSpinWheelFilter()
widget.installEventFilter(\_filter)

#### 方法

| 方法                      | 说明            |
| ------------------------- | --------------- |
| `eventFilter(obj, event)` | Qt 事件过滤器。 |

---

## `desktop.components.detect_stats`

源码：[`desktop/components/detect_stats.py`](../../desktop/components/detect_stats.py)

检测结果统计组件（第二步右侧）：按页形态分类统计，总览 / 明细两级。

数据由宿主（`DetectMixin._refresh_detect_stats`）计算后经 `set_results`
灌入：分类规则唯一实现在 `utils.box_geometry.classify_page_slots`（槽位
形态 → fullcontent / harfcontent / 单独页 / 无文本框），本组件只管展示。

交互：默认显示**总览**（四类的页数，点击某一类）；明细页列出该类每页的
页码，点页码发 `page_clicked(row)` 由宿主跳转预览，另有「返回总览」。

### 模块常量

| 名称            | 值    |
| --------------- | ----- |
| LIST_MAX_HEIGHT | `168` |

### `class DetectStatsWidget(QWidget)`

「检测结果统计」：总览四级分类页数，点进某类查看页码明细。

#### 方法

| 方法                                                                         | 说明                                                              |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `__init__(parent=None)`                                                      | —                                                                 |
| `set_results(total: int, classes: dict[str, list[tuple[int, str]]]) -> None` | 灌入统计结果：`total` 总页数；`classes` 分类键 → [(行号, 页码)]。 |
| `show_overview() -> None`                                                    | 回到总览（返回按钮与数据刷新后的兜底都走这里）。                  |
| `show_detail(class_key: str) -> None`                                        | 打开某分类的页码明细。                                            |

---

## `desktop.components.imposition.canvas`

源码：[`desktop/components/imposition/canvas.py`](../../desktop/components/imposition/canvas.py)

图片拼版操作画布：**白底**上拖动 / 缩放拉伸 / 旋转两张源图。

坐标体系与落盘完全一致——**源图像素，左上原点，x 向右、y 向下**
（`desktop.services.imposition`）。控件把「所有图的外接框」等比缩放到可视区，
用 `px_per_unit` 在「图坐标」与「控件像素」之间换算；用户拖动/缩放/旋转
得到的结果直接写回 `drafts/imposition.json` 的 `items`，由
`compose_page` 原样采用——所见即所得。

**拼版没有纸张**（用户 2026-09-30：「这个拼版不需要设置纸张，只需要背景是
白色的就行，后续提交的时候根据图片的四个区域合并出一张图片」）：画布就是一块
白底，没有纸张矩形、也没有边界线；产出图由服务层按「所有图外接框」紧裁。

交互（用户定的观感）：

- **点击某张图 → 选中**：选中的图带一圈**常显的细虚线**（选中状态，
  **跟着图一起转**——用户 2026-09-30 报过"旋转后高亮框不跟着转"）；
  **按住鼠标操作期间**才升级为带手柄/旋转钮的完整虚线框，**一松手回到
  细框**（2026-09-30：选中态要一直看得见，右侧「当前图片样式」区跟着激活）；
- **切页 / 点空白处 → 取消选中**（右侧图片操作区随之灰掉）；
- **双击某张图 → 预览这张原图**；**双击两图之外的空白处 → 预览左右组合**
  （整页按产出口径合成的效果，`emit` 给控制器开预览弹窗，画布自己不管弹窗）；
- **滚轮 → 缩放视图**（以光标为锚点，松开即停在当前倍率）：缩放只改
  `_px_per_unit` 与偏移两个数，不解码、不重排；重绘**不在滚轮事件里直接
  要**——滚轮/触控板连发时一秒能来上百个事件，直接要就是把大图重绘拉到
  事件率。渲染合并策略见 `wheelEvent` / `_on_wheel_frame`：滚动期间每
  帧最多重绘一次、走**快速档**（不做平滑采样），停稳后补一帧高质量重绘；
- 未按下时靠**光标**提示可抓的位置：图内 `OpenHand`、四角/四边缩放光标、
  框上方圆钮处 `Cross`（命中判定是几何的，不依赖框线可见）；
- 点某张图 → 选中；框内拖动 → 整体移动；**四角**手柄 → 缩放（按住 Shift
  等比）；**四条边整条都是命中带** → 只改一个维度；框**上方的小圆钮** → 旋转
  （按住 Shift 吸附到 15°）；松手 emit `items_changed`（拖动过程中只重绘）；
- **红色对齐线**恒显（**两图页**）：两图 rect 中心中点所在的竖线
  （`SPINE_COLOR`）——整版/单图旋转时拿它当"转没转歪"的对比基准；
  **单图页只认横图（源图宽>高）**（2026-09-30 用户定：单独一张半页图片
  不需要显示中间红线；单独一张整幅对开（横图）仍要）——判据用源图
  宽高比（竖图=半页/单页、横图=整幅对开），文件名后缀认不出"无后缀的
  半页图"；整版旋转走 `rotate_whole`（滑块增量，绕该中点公转+自转），
  单图绝对角度走 `set_item_rotation`，两者都只重绘、由控制器择机 commit；
- **灰色截图范围框**恒显（`CROP_COLOR`）：两图旋转后外接框的并集——
  上下左右最外侧点组成的虚线矩形，与产出图的紧裁范围是同一套几何
  （`services.imposition.page_bounds`），转一转就能看到范围跟着变。

**⚠️ 不限制图片位置/大小**（用户：「图片拉伸、移动后可能超出原本界限，现在是
不显示了，现在不要限制」）：拖动与缩放**都不夹在某个范围内**，画布也**不做
裁剪**——画到哪就是哪，可视范围按所有图的外接框自适应，打开一页就能看全。

⚠️ `rotation` 是**顺时针角度**（与 Qt `QPainter.rotate` 同向），绕该项
`rect` 的中心转——与 PIL 合成侧的取负口径配套（见 services.imposition）。

### 模块常量

| 名称               | 值     |
| ------------------ | ------ |
| HANDLE_RADIUS      | `5`    |
| ROTATE_KNOB_RADIUS | `6`    |
| ROTATE_KNOB_GAP    | `26`   |
| MIN_RECT           | `4.0`  |
| EDGE_HIT_PX        | `6`    |
| SNAP_DEGREES       | `15.0` |
| WHEEL_ZOOM_STEP    | `1.15` |
| ZOOM_MIN           | `0.2`  |
| ZOOM_MAX           | `8.0`  |
| WHEEL_REPAINT_MS   | `30`   |

### `class ImpositionCanvas(QWidget)`

拼版画布：白底上拖动/缩放/旋转两张图；`items_changed` 发出图坐标。

#### 方法

| 方法                                          | 说明                                                               |
| --------------------------------------------- | ------------------------------------------------------------------ |
| `__init__(parent=None)`                       | —                                                                  |
| `set_page(items) -> None`                     | 设置这一页的版面（图坐标即源图像素）；**不选中任何图**。           |
| `clear_page() -> None`                        | 清空（无拼版页时用）：只留白底。                                   |
| `items() -> list[dict]`                       | 当前版面（合成像素，已四舍五入到两位）。                           |
| `selected() -> int`                           | 当前选中的槽位下标（-1 = 未选中）。                                |
| `select(index: int) -> None`                  | 外部选中某个槽位（右侧面板切换时用）。                             |
| `has_items() -> bool`                         | —                                                                  |
| `frame_visible() -> bool`                     | 当前是否画**带手柄的完整操作框**（= 鼠标按住期间）。               |
| `rotate_selected(delta_deg: float) -> None`   | 把选中的图旋转 `delta_deg`（顺时针为正），并立即上报。             |
| `rotate_whole(delta_deg: float) -> None`      | **整版旋转** `delta_deg`（顺时针为正）：两张图绕公共中心转。       |
| `set_item_rotation(angle_deg: float) -> None` | 把选中的图的旋转设为绝对角度（绕自身 rect 中心，只重绘不上报）。   |
| `spread_rotation() -> float \| None`          | 整版当前的"平均旋转角"（收敛到 [-180, 180)；无图返回 None）。      |
| `selected_rotation() -> float \| None`        | 选中图当前的旋转角（无选中返回 None）。                            |
| `refit() -> None`                             | 按当前 items 重新适配可视区并重绘（整版旋转后外接框变了）。        |
| `flush_pending() -> bool`                     | 把"还没松手"的编辑结果补发出去（切页/切步骤/离开时调）。           |
| `resizeEvent(event) -> None`                  | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。                       |
| `showEvent(event) -> None`                    | Qt 事件覆写：显示时刷新状态。                                      |
| `invalidate_image(path: str) -> None`         | 某个源图文件被外部覆盖（编辑器「完成」回写）后：丢掉它的解码       |
| `contextMenuEvent(event) -> None`             | 右键菜单：**预览图片 / 编辑图片**（2026-10-01 用户定）。           |
| `mouseDoubleClickEvent(event) -> None`        | 双击：**图上 → 预览这张原图**；**两图之外的空白 → 预览左右组合**。 |
| `mousePressEvent(event) -> None`              | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。                       |
| `mouseMoveEvent(event) -> None`               | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。                     |
| `mouseReleaseEvent(event) -> None`            | Qt 事件覆写：松开（提交本次编辑）。                                |
| `leaveEvent(event) -> None`                   | 指针离开画布：按下状态收不到 release 时也别留着框线。              |
| `wheelEvent(event) -> None`                   | 滚轮缩放视图（以光标为锚点）；**重绘按帧合并**（减渲染的关键）。   |
| `paintEvent(event) -> None`                   | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。                |

##### `set_page(items) -> None`

设置这一页的版面（图坐标即源图像素）；**不选中任何图**。

⚠️ 参数**只有 items**：拼版没有纸张（用户 2026-09-30），可视范围按
「所有图的外接框」自适应，不再有一个"纸张矩形"要摆。
⚠️ 每次载页都**清空选中**（用户 2026-09-30：切页后右侧「操作当前
图片」区不激活，点击某张图才选中）。

##### `frame_visible() -> bool`

当前是否画**带手柄的完整操作框**（= 鼠标按住期间）。

平时选中的图另有常显细框（`_draw_selected_border`），不算在内。

##### `rotate_whole(delta_deg: float) -> None`

**整版旋转** `delta_deg`（顺时针为正）：两张图绕公共中心转。

公共中心 = 两图 `rect` 中心的**中点**（也就是红色对齐线所在的竖线，
见 `_spread_center_units`）。每张图"中心绕公共中心公转 + 自身
`rotation` 叠加"——两图的相对位置、相对角度都不变，对齐线也不动，
用户拖滑块时看到的就是整版在一根固定的中线上左右倾摆。

⚠️ 只重绘**不上报**：滑块会连续吐增量，落盘交给控制器在停顿后统一
`flush_pending`（与拖动的"松手才上报"同一策略）。

##### `spread_rotation() -> float | None`

整版当前的"平均旋转角"（收敛到 [-180, 180)；无图返回 None）。

单图自转过后两图角度可能不同，这里取平均当作整版角度——滑块就以
这个值为基准继续吐增量，两图的角度差原样保留。

##### `refit() -> None`

按当前 items 重新适配可视区并重绘（整版旋转后外接框变了）。

⚠️ 滚轮缩放倍率一并归一：这里语义就是"回到打开时的样子"。

##### `flush_pending() -> bool`

把"还没松手"的编辑结果补发出去（切页/切步骤/离开时调）。

与 `print_layout_canvas.flush_pending` 同一理由：`items_changed`
只在松手时发，拖住不放直接切走会让这一下改动永久丢失。

##### `invalidate_image(path: str) -> None`

某个源图文件被外部覆盖（编辑器「完成」回写）后：丢掉它的解码
缓存并重绘——不丢的话画布会一直显示覆盖前的旧图。

##### `contextMenuEvent(event) -> None`

右键菜单：**预览图片 / 编辑图片**（2026-10-01 用户定）。

目标规则与双击一致：**图上** → 这张原图；**两图之外的空白** →
整页左右组合（成品口径）。预览与双击走**同一组信号**（行为完全
一样，只是入口多一个）；编辑是新加的直接入口——原本编辑是预览
弹窗工具条里的按钮，现在不经过弹窗、右键直达，由控制器接管。
右键即选中（与左键点击同款语义），右侧「当前图片样式」跟着激活。
空画布没有菜单（没有可预览/可编辑的东西）。

##### `mouseDoubleClickEvent(event) -> None`

双击：**图上 → 预览这张原图**；**两图之外的空白 → 预览左右组合**。

⚠️ 处理了就 `accept`：Qt 对未接受的双击会**再补一个 mousePress**，
那会走进 `mousePressEvent` 把编辑手势带起来（用户双击预览、松手时
画布却以为刚拖动过一下）。

##### `wheelEvent(event) -> None`

滚轮缩放视图（以光标为锚点）；**重绘按帧合并**（减渲染的关键）。

缩放本身只是 `_zoom_at` 里几个乘法——不解码、不重排、不碰图缓存。
真正贵的是重绘：两张几千像素见方的原图 + 平滑采样。高分滚轮/触控板
一秒能吐上百个 wheel 事件，若每个事件都 `update()`，重绘就被拉到
事件率。所以这里**不直接要重绘**：

- 启动帧窗口定时器（`WHEEL_REPAINT_MS`），窗口内再来滚动只置
  `_wheel_paint_pending`；
- 窗口到期画一帧（`_on_wheel_frame`）；窗口内还有滚动就滚到下一帧，
  没有就关掉快速档、补一帧带平滑的高质量重绘收尾。

连发期间 paintEvent 走**快速档**（不做 `SmoothPixmapTransform`，
大图缩放的重头开销在这）——反正下一滚就整帧重画，糊一帧没人看得出。

---

## `desktop.components.imposition.confirm_delete`

源码：[`desktop/components/imposition/confirm_delete.py`](../../desktop/components/imposition/confirm_delete.py)

「批量删除拼版页」确认弹窗（**模块一：选择拼版** 的 UI）。

用户口径（2026-09-30）：

- **宽度固定**：弹窗不再随文字一行拉到很宽，正文允许折成多行；
- **逐页列名**：多选时用户看不清要删的是哪几页，正文下方按
  「第一页：图名 · 图名」逐行列出被勾选的页（与左列清单同源文案）；
- **高度封顶**：勾选的页再多，弹窗也不能无限变高——列表放进滚动区，
  超出封顶高度出现滚动条。

宿主（唤起与删除落盘）见 `desktop/pages/taskdetail/imposition_pages.py`
的 `_on_imposition_batch_delete`。

### 模块常量

| 名称       | 值    |
| ---------- | ----- |
| DIALOG_W   | `520` |
| LIST_MAX_H | `264` |

### `class BatchDeleteConfirmDialog(MessageBoxBase)`

批量删除拼版页的确认框：正文折行 + 逐页列名 + 列表滚动。

#### 方法

| 方法                                 | 说明                                                   |
| ------------------------------------ | ------------------------------------------------------ |
| `__init__(pages: list, parent=None)` | `pages` 是被勾选的 `[(页下标, 页数据), …]`（原顺序）。 |

##### `__init__(pages: list, parent=None)`

`pages` 是被勾选的 `[(页下标, 页数据), …]`（原顺序）。

页数据只读它的 `items`（两张源图），文案与左列清单同源
（`page_source_stems` + `cn_page_label`）。

---

## `desktop.components.imposition.page_list`

源码：[`desktop/components/imposition/page_list.py`](../../desktop/components/imposition/page_list.py)

拼版页清单——**模块一：选择拼版** 的左列（「第一页」「第二页」…）。

虚线的**「＋ 选择拼版」固定钉在左列最底部**（不随页条目增长下移出视野），
点了发 `add_requested`，由模块一控制器
（`desktop/pages/taskdetail/imposition_pages.py`）弹窗挑图建页。

页条目左上有**勾选框**（与页标题紧挨）；勾了页，一条**悬浮操作框**
（「已选 N 页」+「取消选择」「批量删除」）悬在页码栏右侧中部，可拖动
——取消选择即收起。

这里只做控件与信号：清单**只认页标题/副标题文案**，不认拼版文档本身——
页清单的数据（`drafts/imposition.json`）由装配层
`view.ImpositionViewWidget` 灌进来。

### `class ImpositionPageList(QWidget)`

左列拼版页清单：滚动的页条目 + 底部固定的虚线「＋ 选择拼版」。

只认文案：`set_pages(captions)` 灌入每页的副标题（两张源图名），
条目数即页数；当前页高亮由 `set_current` 控制。勾选了页，一条悬浮
操作框（`_SelectBar`）悬在页码栏右侧中部（可拖动），提供
「取消选择 / 批量删除」。

页条目支持**按住上下拖动排序**，交互口径（用户 2026-09-30 三稿：拖动
中清单不留空档）：按下后**本体留在原位置灰**，一张等大的「幽灵卡」
跟着光标走，主色细线指示松手后落到哪——清单全程一动不动。**松手**
后幽灵卡滑进落点槽位、这才真正换位，随后发
`reorder_requested(from, target)`——`target` 是**拖走之后**的插入
下标（调用方据此 pop/insert），拖回原位则不发。

#### 方法

| 方法                                                      | 说明                                                             |
| --------------------------------------------------------- | ---------------------------------------------------------------- |
| `__init__(parent=None)`                                   | —                                                                |
| `resizeEvent(event) -> None`                              | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。                     |
| `set_float_host(host) -> None`                            | 把悬浮框的宿主换成外部装配层（拼版视图整体）。                   |
| `entries() -> list[_PageEntry]`                           | —                                                                |
| `set_pages(captions: list[str], current: int=-1) -> None` | 按页数重建清单（`captions[i]` 是第 i 页的副标题）。              |
| `set_current(index: int) -> None`                         | 高亮当前页（-1 = 无页）。                                        |
| `set_page_thumbs(thumbs: list) -> None`                   | 给每页条目灌缩略图（`thumbs[i]` 是第 i 页的 `QImage`/`QPixmap`， |
| `current() -> int`                                        | —                                                                |
| `checked_indexes() -> list[int]`                          | 勾选了的页下标（升序）。                                         |

##### `set_float_host(host) -> None`

把悬浮框的宿主换成外部装配层（拼版视图整体）。

页码栏只有 150px 宽，框要「浮在页码栏**右侧**」就得允许它超出本列、
悬到右边画布上——挂到视图底下才行。`view.py` 装配时调用；不设置
则兜底贴在清单内右缘、垂直居中。

##### `set_pages(captions: list[str], current: int=-1) -> None`

按页数重建清单（`captions[i]` 是第 i 页的副标题）。

勾选集合**按副标题跨重建保留**：拖动排序/加页不丢勾选；页被删掉
（副标题不在了）自然落选——批量删除自己就是靠这次重建清空的。

##### `set_page_thumbs(thumbs: list) -> None`

给每页条目灌缩略图（`thumbs[i]` 是第 i 页的 `QImage`/`QPixmap`，
`None` 表示还没渲好）。

用户 2026-10-03：所有独立任务左栏都显示缩略图。**本方法只管贴图**，
解码/缓存/异步在宿主那边做（拼图模块页用
:class:`~desktop.workers.thumb_cache_worker.ImageThumbCacheWorker`，
与其余四个独立任务页同一份缓存与同一份逻辑）。

⚠️ 下标要**按条目自己的 index** 灌而不是按参数位置：`set_pages` 重建
后条目的 index 是重建时的下标，两者一致；但拖动排序后条目的 index
仍是它创建时的下标，而 `_entries` 的**列表位置**才是当前页序——
所以这里遍历 `_entries` 并用 `entry.index` 取图。

---

## `desktop.components.imposition.panel`

源码：[`desktop/components/imposition/panel.py`](../../desktop/components/imposition/panel.py)

拼版控制面板——**模块二：拼版操作** 的右列（详情页控制区）。

布局（用户 2026-09-30 晚定稿）：标题行（说明挂**问号按钮**，同其他步骤面板）

- 状态行 + **两块分区** + 底部启用开关：

* **「操作当前图片页」**：页级操作——整体旋转（滑块/输入框，任意角度增量）、
  **复位本页版面**（独占一行 block）、**一行两个**的「新增图片」（只在单图页
  出现）与「删除选中图片」（只在选中某张图时出现；2026-09-30 用户定：删除
  按钮从图片样式区挪进来跟新增图片同行）——「删除本页拼版」按钮已删除
  （删页入口只剩左列的「✕」与批量删除），清空全部拼版保留；
* **「当前图片样式」**：图片级操作——旋转（绕图片中心）。这一块**只在画布里
  选中了某张图时激活并高亮**（`_ItemSection`），切页 / 点空白取消选中后
  整块灰掉；
* **「在流程中启用图片拼版」**复选框**放面板最底部**（用户 2026-09-30）：
  决定第四步取图来源（共享基元 `print_source_dir`）。

「选择拼版」按钮**不在本面板**（2026-09-30 删除）：入口只有左列末尾的
虚线「＋ 选择拼版」格（`page_list.py`），两处同义留一处。

这里只做控件与信号，所有动作都发信号交给模块二控制器
（`desktop/pages/taskdetail/imposition_layout.py`）与共享基元
（`imposition.py`）处理：

- 删除/清空是**页管理**（模块一控制器）；页序在左列**拖动排序**、翻页在
  画布下方「上一页/下一页」（`view.py`），都不在本面板；
- **整体旋转**（增量）与**选中图旋转**（绝对角度）是**版面操作**（模块二
  控制器）。

### 模块常量

| 名称               | 值                                                                                                                |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| ANGLE_SLIDER_SCALE | `100`                                                                                                             |
| PANEL_DESCRIPTION  | `"可选节点：第三步「区域模式」为 1（左右分开）时出现在流程中，位于「图片去底色」与「生成 PDF」之间。勾选下方开…"` |

### `class ImpositionPanel(Card)`

「图片拼版」详情控制面板（control_stack 的第 5 页）。

#### 方法

| 方法                                              | 说明                                                         |
| ------------------------------------------------- | ------------------------------------------------------------ |
| `__init__(parent=None)`                           | —                                                            |
| `set_whole_angle(value: float) -> None`           | 程序化回填整版角度（blockSignals 语义，绝不回抛增量）。      |
| `set_item_rotation(value: float \| None) -> None` | 程序化回填选中图角度；`None` = 没有选中。                    |
| `set_page_available(on: bool) -> None`            | 有没有可操作的拼版页：没有时整版旋转组件一并禁用。           |
| `set_single_page(on: bool) -> None`               | 当前页是不是**单图页**：是才露出「新增图片」（两图页隐藏）。 |
| `set_enabled_checked(on: bool) -> None`           | 程序化回填启用开关（blockSignals 避免回抛覆盖落盘值）。      |
| `set_status(text: str) -> None`                   | 状态行：当前页 + 选中槽位 + 生效与否。                       |

##### `set_item_rotation(value: float | None) -> None`

程序化回填选中图角度；`None` = 没有选中。

`None` 时「当前图片样式」整块灰掉、组件禁用清零，页级区的
「删除选中图片」一并隐藏；有值则高亮激活、删除按钮露出
（用户 2026-09-30：只有某张图片选中 active 时图片区才高亮）。

---

## `desktop.components.imposition.picker`

源码：[`desktop/components/imposition/picker.py`](../../desktop/components/imposition/picker.py)

「选择拼版」弹窗（**模块一：选择拼版** 的 UI）。

从**剩余未被选择拼版的图片**（源清单里还没被任何一页用过的，见
`services.imposition.remaining_files`）里**自由多选**——选择阶段不限
张数、不做任何配对；点「开始拼版」时才把勾选的图按源清单顺序**每两张
配成一页**（序号在前的进右槽），落单的不拼。

「删除图片」把勾选的图移出选择范围（**软删除**：黑名单由宿主落盘到
`drafts/imposition.json` 的 `removed` 字段，源文件不动）；
「查看删除的图片」切换到已删除视图，可勾选批量恢复。

这里只做控件与信号；弹窗怎么被唤起、选中之后怎么建页落盘，见
`desktop/pages/taskdetail/imposition_pages.py`（模块一控制器）。

### 模块常量

| 名称         | 值    |
| ------------ | ----- |
| CARD_HEAD    | `30`  |
| CARD_GAP     | `12`  |
| THUMB_BATCH  | `6`   |
| THUMB_GAP_MS | `150` |

### `class ImpositionPickerDialog(FramelessDialog)`

「选择拼版」弹窗：从剩余未使用的源图里勾选两张。

两种模式（2026-09-30 新增 `mode` 参数）：

- **`"pick"`**（默认，选页）：自由多选，1 张单独成页 / 2 张拼一页；
- **`"append"`**（单图页「新增图片」）：**只能勾 1 张**，确认按钮叫
  「添加」——宿主把这张图并进当前那一页拼版（见模块一控制器）。

**卡片网格**：一行摆好几张（列数随窗口宽度自动变），卡片 `CARD_W×CARD_H`、
缩略图固定 `THUMB_W×THUMB_H`（用户要求「一行好几个、选框宽一些」且
「图片要正常显示、要有文字」）。

**可缩放**（用户 2026-09-30 要求）：底座是 `qframelesswindow.FramelessDialog`，
恢复它的最小化/最大化按钮与「双击标题栏放大/还原」；边缘还能拖拽调整大小，
网格列数跟着窗口宽度自动变。

**删除/恢复**（用户 2026-09-30 要求）：勾选卡片可「删除图片」——移出选择
范围（软删除，源文件不动，黑名单由宿主落盘）；「查看删除的图片」切到
已删除视图，勾选后「恢复选中」或「全部恢复」。

源清单顺序在前的图会被放到拼版页**右侧**（用户口径），这里按同一顺序
展示，勾选结果也按**源清单顺序**返回（不是点选先后）。

#### 方法

| 方法                                                                       | 说明                                                           |
| -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `__init__(files: list, parent=None, removed_files=None, mode: str='pick')` | —                                                              |
| `count() -> int`                                                           | 候选视图的卡片数（已删除的不算）。                             |
| `checked_files() -> list[Path]`                                            | 用户勾选的源图（**按源清单顺序**，不是勾选先后）。             |
| `picked_files() -> list[Path]`                                             | —                                                              |
| `auto_mode_file() -> Path \| None`                                         | 「从这张图片开始自动拼版」生效的那张图（不生效返回 None）。    |
| `auto_sequence() -> list[Path]`                                            | 自动拼版的图片序列：从勾选那张起到候选清单末尾（源清单顺序）。 |
| `removed_files() -> list[Path]`                                            | 当前黑名单（含会话内新删的，不含已恢复的）。                   |
| `removed_changed() -> bool`                                                | 黑名单与打开时是否不同（宿主据此决定要不要落盘）。             |
| `toggle_card(card: _SourceCard) -> None`                                   | 切换一张候选卡片的勾选（自由多选，不设上限）。                 |

##### `checked_files() -> list[Path]`

用户勾选的源图（**按源清单顺序**，不是勾选先后）。

张数不限——配对（每两张一页）由宿主在「开始拼版」后做。

##### `auto_mode_file() -> Path | None`

「从这张图片开始自动拼版」生效的那张图（不生效返回 None）。

生效条件：勾选框被勾上、且**恰好勾了 1 张图**——选项只在恰好
勾 1 张时出现（不限整幅/半幅，用户 2026-10-01 定），多选不走自动。

##### `auto_sequence() -> list[Path]`

自动拼版的图片序列：从勾选那张起到候选清单末尾（源清单顺序）。

「自此之后」= 含勾选的那张本身；它之前的图片不参与（留在候选池，
之后仍可手动拼）。

---

## `desktop.components.imposition.view`

源码：[`desktop/components/imposition/view.py`](../../desktop/components/imposition/view.py)

拼版页装配控件：左列拼版页清单（模块一）+ 右区操作画布（模块二）。

本文件是**两个模块的缝合处**，只做组合与转发，不含业务：

- **模块一（选择拼版）**：左列 `ImpositionPageList` 与
  `ImpositionPickerDialog`（`picker.py`）——选哪两张、拼几页；
- **模块二（拼版操作）**：`ImpositionCanvas`（`canvas.py`）——
  拖动 / 缩放拉伸 / 旋转，以及右侧 `ImpositionPanel`（`panel.py`）。

落盘 / 合成 / 与第四步取图切换由 `desktop/pages/taskdetail/` 下的
拼版控制器负责（`imposition.py` 共享基元 + 模块一/二各自的 Mixin）。

### `class ImpositionViewWidget(QWidget)`

拼版页面：左列拼版页清单 + 右区操作画布。

#### 方法

| 方法                                                    | 说明                                                               |
| ------------------------------------------------------- | ------------------------------------------------------------------ |
| `__init__(parent=None)`                                 | —                                                                  |
| `set_pages(pages: list[dict], current: int=-1) -> None` | 整批灌入拼版页；`current` 是当前显示的下标。                       |
| `set_page_thumbs(thumbs: list) -> None`                 | 把左列每页的缩略图贴上去（`thumbs[i]` 对应第 i 页，可为 `None`）。 |
| `pages() -> list[dict]`                                 | —                                                                  |
| `set_current(index: int) -> None`                       | 切到某一页（-1 = 无页，画布清空）。                                |
| `current_index() -> int`                                | —                                                                  |
| `checked_pages() -> list[int]`                          | 左列勾选了的页下标（升序）——批量操作用。                           |
| `current_items() -> list[dict]`                         | —                                                                  |
| `selected_slot() -> int`                                | —                                                                  |
| `update_current_items(items: list[dict]) -> None`       | 把外部（面板按钮）改过的版面写回当前页并重画画布。                 |
| `flush_pending() -> None`                               | 离开页面前的补发（拖住未松手就切走时别丢改动）。                   |

##### `set_page_thumbs(thumbs: list) -> None`

把左列每页的缩略图贴上去（`thumbs[i]` 对应第 i 页，可为 `None`）。

转交给 :meth:`ImpositionPageList.set_page_thumbs`——本控件只做装配，
不自己碰条目（页条目是 `page_list` 的私产）。

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

| 名称             | 值    |
| ---------------- | ----- |
| BAR_HEIGHT       | `34`  |
| POPUP_HEIGHT     | `260` |
| POPUP_GAP        | `6`   |
| POPUP_MIN_HEIGHT | `140` |

### `class LogPanel(QWidget)`

执行日志状态条：一行摘要，点击唤出日志浮层。

`log_view` 属性指向浮层里的 QTextEdit，页面各处沿用既有的
`self.log_view.append(...)` 调用方式，无需改动调用点。

#### 方法

| 方法                                   | 说明                                                      |
| -------------------------------------- | --------------------------------------------------------- |
| `__init__(parent=None)`                | 构建状态条外观与（尚未挂到页面上的）日志浮层。            |
| `toggle() -> None`                     | 在展开 / 收起之间切换（取反当前状态）。                   |
| `set_expanded(expanded: bool) -> None` | 展开或收起日志浮层，并同步箭头方向与状态条摘要。          |
| `eventFilter(obj, event) -> bool`      | 浮层打开期间：Esc 或点击浮层/状态条之外的任意位置即收起。 |
| `mouseReleaseEvent(event) -> None`     | 点击状态条空白处即可唤出 / 收起浮层。                     |
| `resizeEvent(event) -> None`           | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。              |
| `moveEvent(event) -> None`             | —                                                         |
| `paintEvent(event) -> None`            | 画一条上分隔线与状态圆点（不画卡片底，比整张卡片轻）。    |

##### `set_expanded(expanded: bool) -> None`

展开或收起日志浮层，并同步箭头方向与状态条摘要。

展开时把浮层挂到页面、定位到状态条正上方并显示，同时滚到底部；
收起时仅隐藏浮层（日志内容保留）。

### 模块函数

| 函数                                            | 说明                                 |
| ----------------------------------------------- | ------------------------------------ |
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
`Pager` 不 import Qt，能直接在自测里当普通对象断言（切片区间、页码钳制、
末页删空后的回退）；`Pagination` 只负责把 Pager 的状态画出来、把点击翻译
成 `set_page` 调用。

页码一律 **1-based**——直接显示在界面上的东西就跟人看到的保持一致，
0-based 只在内部切片时用一次（`_offset`）。

### `class Pager`

分页状态与派生量（不可变，改页码/每页条数就换一个新实例）。

total 总条数（**过滤后**的条数，不是全量）
page_size 每页条数
page 当前页码，1-based；越界会在读取时被钳制

#### 方法

| 方法                                        | 说明                                                                        |
| ------------------------------------------- | --------------------------------------------------------------------------- |
| `total_pages() -> int`                      | 总页数；0 条时也是 1 页（界面上显示「第 1 / 1 页」比「第 1 / 0 页」自然）。 |
| `clamped_page() -> int`                     | 钳制到 [1, total_pages] 的页码。                                            |
| `slice_bounds() -> tuple[int, int]`         | 当前页在整表里的 [start, end) 下标区间（左闭右开，直接喂 list 切片）。      |
| `page_slice(items: list) -> list`           | 取当前页的切片；越界页码已钳制，不会返回空页。                              |
| `with_page(page: int) -> 'Pager'`           | —                                                                           |
| `with_page_size(page_size: int) -> 'Pager'` | 换每页条数：页码按比例换算，尽量停在原来看到的那一条附近。                  |
| `with_total(total: int) -> 'Pager'`         | —                                                                           |

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
用户操作时由本控件算出新页码并通过 `changed` 抛回去，宿主再重算并
`set_pager` 刷新。这样「过滤 → 分页 → 渲染」只有一条数据流向。

#### 方法

| 方法                                                      | 说明                                                                 |
| --------------------------------------------------------- | -------------------------------------------------------------------- |
| `__init__(page_size: int=DEFAULT_PAGE_SIZE, parent=None)` | —                                                                    |
| `pager() -> Pager`                                        | —                                                                    |
| `set_pager(pager: Pager) -> None`                         | 用新的分页状态刷新显示（宿主算完过滤/切片后调它）。                  |
| `set_visible_for(total: int) -> None`                     | 总数为 0 时隐藏（配合空状态卡片，避免「共 0 条 第 1/1 页」的噪音）。 |

---

## `desktop.components.panels.base`

源码：[`desktop/components/panels/base.py`](../../desktop/components/panels/base.py)

阶段控制面板基类：标题 + 问号帮助按钮 + 参数表单骨架。

阶段说明（description）不再平铺在标题下方占高度，改由标题右侧的问号按钮
承载：hover 弹 qfluentwidgets 的 ToolTip 气泡，点击弹 Flyout（内容自动换行）。
按钮本体是公共控件 `desktop.ui.widgets.HelpButton`（「图片拼版」面板同款）。

### `class StagePanel(QWidget)`

阶段控制面板：标题（含问号帮助按钮）+ 参数表单。子类实现 \_build_form/get_args。

#### 方法

| 方法                                   | 说明                                                               |
| -------------------------------------- | ------------------------------------------------------------------ |
| `__init__(parent=None)`                | 构建面板骨架：标题行 + 参数表单容器。                              |
| `mark_params_edited() -> None`         | 补一次"用户改了参数"通知——给**按钮**这类不经过控件信号的入口用。   |
| `build_form() -> QWidget`              | 参数表单容器：统一装进透明滚动区，窗口过矮时出滚动条而非压扁表单。 |
| `get_args() -> dict`                   | 从表单收集该阶段参数（不含 input/output/clean）。                  |
| `apply_args(parameters: dict) -> None` | 把一次历史执行/暂存的参数回填到表单（多余键忽略）。                |
| `reset_to_default() -> None`           | 恢复控件初始默认值。                                               |

##### `__init__(parent=None)`

构建面板骨架：标题行 + 参数表单容器。

title 来自子类类属性；description 不再平铺占高度，改挂在标题右侧
问号按钮上（hover 出 ToolTip 气泡、点击出 Flyout）。随后调用
build_form 生成子类表单并占满剩余垂直空间，最后统一把表单里输入
控件的信号接到 `param_edited`（供参数暂存）。

##### `mark_params_edited() -> None`

补一次"用户改了参数"通知——给**按钮**这类不经过控件信号的入口用。

例：「恢复默认」是把默认值 set 回控件（走 `_apply_args`），信号会被
`_applying` 挡掉，但用户确实改动了参数，得让宿主把新值暂存下来。

##### `build_form() -> QWidget`

参数表单容器：统一装进透明滚动区，窗口过矮时出滚动条而非压扁表单。

控制卡片把剩余高度分给 QStackedWidget，窗口一矮表单行就被压得错位
（rembg 的复选框会挤进表单行、说明与行间距被吞掉）。滚动区让表单
始终保持自然高度，高度不足时纵向滚动。print 面板自带分区滚动区，
整体覆盖本方法，不受影响。

##### `reset_to_default() -> None`

恢复控件初始默认值。

各子类的 `_apply_args` 对缺失键都取自身默认值，因此传空字典
即可复位——用于切换任务时清掉上一个任务残留的手改参数。

### 模块函数

| 函数                                                      | 说明                                                                          |
| --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `default_for(parameters: dict, defaults: dict, key: str)` | 取回填值：`parameters` 里有且**不为 None** 时用它，否则回落 `defaults[key]`。 |

#### `default_for(parameters: dict, defaults: dict, key: str)`

取回填值：`parameters` 里有且**不为 None** 时用它，否则回落 `defaults[key]`。

⚠️ 不能写成 `parameters.get(key, defaults[key])`——历史配置里存着
`{"dpi": null}` 时，`get` 会返回 `None`，兜底**永不生效**，直接
`setValue(None)` 就崩（这是本仓库反复踩到的 None 默认值陷阱）。
也不能写成 `parameters.get(key) or ...`——布尔键的合法值 `False`
与数值键的合法值 `0` 会被误判成"没值"而回落到默认。

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

| 方法                                               | 说明                                                             |
| -------------------------------------------------- | ---------------------------------------------------------------- |
| `get_args() -> dict`                               | 返回空参数字典（detect 阶段无表单参数）。                        |
| `set_whole_page(on: bool) -> None`                 | 外部（第三步 area）回填勾选状态；blockSignals 避免回抛造成循环。 |
| `set_box_selection(index: int, kind: str) -> None` | 回填「选中框类型」控件：`index < 0`（无选中）时三段都不高亮。    |

##### `get_args() -> dict`

返回空参数字典（detect 阶段无表单参数）。

整页模式不在这里上报：area 归第三步 rembg 面板所有，本开关只负责
把 area 切到 4 / 切回 1（见宿主的 \_set_whole_page_mode）。

##### `set_box_selection(index: int, kind: str) -> None`

回填「选中框类型」控件：`index < 0`（无选中）时三段都不高亮。

`set_current` 是程序化切换、**不发** `current_changed`，因此不会
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
`params_spec.DEFAULTS["extract"]`（控件初值与回填兜底同一份）。

#### 方法

| 方法                 | 说明                                                          |
| -------------------- | ------------------------------------------------------------- |
| `get_args() -> dict` | 收集提取参数：zoom/dpi/ext/quick/pages（不含 input/output）。 |

##### `get_args() -> dict`

收集提取参数：zoom/dpi/ext/quick/pages（不含 input/output）。

pages 留空表示全部页；非法页码由 runner 在取参时以 ValueError 拦截。
dpi 默认 300，是**整页渲染**的 DPI 下限（内嵌图路径不生效）。

---

## `desktop.components.panels.params_spec`

源码：[`desktop/components/panels/params_spec.py`](../../desktop/components/panels/params_spec.py)

desktop 各阶段面板的**默认参数**集中定义（唯一事实来源）。

面板散着写默认值会漂移：同一个参数在「构建控件初值」「`_apply_args` 缺省
兜底」「`reset_to_default`」三处各写一遍，改一处漏两处（`page_number_font_size`
就曾出现「兜底 12 / 默认 18」两套值）。这里按阶段收成一张表，各消费方统一取用：

1. `DEFAULTS[stage]` —— 面板 `_apply_args()` 的缺键兜底与控件初值；
2. `StagePanel.reset_to_default()` —— 复位到本表；
3. 表单下拉的「中文显示 ↔ 参数值」候选表也在此登记。

## 与 core.command_spec 的关系

`core/command_spec.py` 是**命令行**参数的唯一事实来源，本模块是**桌面表单**的
那一份。两者刻意分开：CLI 的 print 默认是「空表单」（不打印标题、pdf_name=None），
而桌面表单打开就该是一份能直接出 PDF 的配置（有书名、有页码）。print 段的差异
由 `core.command_spec.PRINT_FORM_DEFAULTS` 显式表达，这里直接引用，不再抄一份。

其余阶段（extract/detect/rembg）桌面与 CLI 语义一致，因此**以 command_spec 的
defaults 为底**，只覆盖表单侧特有的键（如 `pages` 表单里是空串而非 None），
见各表的 `_base` 调用。这样 CLI 改默认值时桌面自动跟随，不会再出现两份值。

### 模块函数

| 函数                                                 | 说明                                            |
| ---------------------------------------------------- | ----------------------------------------------- |
| `stage_defaults(stage: str) -> dict`                 | 取某阶段的默认参数（副本，可安全改写）。        |
| `default_value(stage: str, key: str, fallback=None)` | 取某阶段某键的默认值；未登记时返回 `fallback`。 |

#### `default_value(stage: str, key: str, fallback=None)`

取某阶段某键的默认值；未登记时返回 `fallback`。

⚠️ 默认值可能是 `None`（如 print 的 `title_margins`），这里**不做**
`or` 兜底——调用方要区分「默认就是 None」与「没登记」。

---

## `desktop.components.panels.print_form`

源码：[`desktop/components/panels/print_form.py`](../../desktop/components/panels/print_form.py)

生成 PDF（print）阶段的表单构建 Mixin：编排、通用控件工厂、节点表、焦点策略。

本类是**编排层**，按依赖从少到多继承三个专职 Mixin：

- :mod:`desktop.components.panels.print_text_layout` —— 「位置/文字方向」固定取值
- :mod:`desktop.components.panels.print_inset` —— 「距页边」控件组
- :mod:`desktop.components.panels.print_sections` —— 五个分区的控件

参数定义/解析见 print_params.py，面板状态见 print_panel.py。

⚠️ 拆分只改**代码落在哪个文件**，不改任何行为：四个类的成员名对外一律从
`PrintFormMixin` 可见（`PrintPanel` 只继承它一个），
`tests/selftests/print_form_split.py` 钉住这条不变量。

### `class PrintFormMixin(PrintSectionsMixin, PrintTextLayoutMixin)`

print 面板的表单构建（由 PrintPanel 继承）。

MRO：`PrintFormMixin → PrintSectionsMixin → PrintInsetMixin →
PrintTextLayoutMixin`。前三者都只依赖 `self` 上的成员，最终由
`PrintPanel(PrintFormMixin, StagePanel)` 线性化到 `StagePanel`
提供的 `_add_row` 等基础能力。

#### 方法

| 方法                      | 说明                                                |
| ------------------------- | --------------------------------------------------- |
| `build_form() -> QWidget` | 构建 print 面板表单：滚动区 + 各分区控件 + 节点表。 |

##### `build_form() -> QWidget`

构建 print 面板表单：滚动区 + 各分区控件 + 节点表。

用 ScrollArea 承载全部分区（输出/边距/标题/页码/过滤），顶部放恢复
默认配置/放弃修改按钮，构建后连接 pdf_name 与 title 联动信号；焦点策略延后到
面板 **init** 末尾统一设置。

---

## `desktop.components.panels.print_inset`

源码：[`desktop/components/panels/print_inset.py`](../../desktop/components/panels/print_inset.py)

「距页边」控件组：标题 / 页码两段文字各自的两行输入框。

从 `print_form.PrintFormMixin` 拆出。这一段是**完整内聚**的一块：
造控件 → 加行 → 取值 → 回填 → 刷新释义，都只围着 `block` 字典转。

- 依赖：`self._add_row`（`base.StagePanel`）、
  `self._title_inset` / `self._page_number_inset`（由 `print_sections` 创建）
- 被依赖：`PrintSectionsMixin`（造行）、`PrintPanel`（取值 / 回填）

⚠️ **拆出后仍然靠 `self._xxx` 共享状态**——这是 Mixin 拆分的固有代价，
不要为了"看起来独立"去加构造参数：面板的 MRO 是线性的，共享 self
反而是这里最简单正确的做法。共享点全部登记在
`tests/selftests/print_form_split.py` 的白名单里。

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

| 名称     | 值       |
| -------- | -------- |
| PAGE_MIN | `1`      |
| PAGE_MAX | `100000` |
| \_SPIN_W | `120`    |
| \_SIDE_W | `76`     |
| \_DEL_W  | `30`     |
| \_GAP    | `6`      |

### `class NodeRow(QWidget)`

一个标题切换节点：触发页码 + 标题 + 侧别 + 删除按钮。

#### 方法

| 方法                                                                  | 说明                                                    |
| --------------------------------------------------------------------- | ------------------------------------------------------- |
| `__init__(page: int=1, title: str='', side: str='left', parent=None)` | 构造一个标题切换节点行：页码 + 标题 + 侧别 + 删除按钮。 |
| `value() -> list \| None`                                             | 收集本行配置；标题为空返回 None（该行忽略）。           |

##### `__init__(page: int=1, title: str='', side: str='left', parent=None)`

构造一个标题切换节点行：页码 + 标题 + 侧别 + 删除按钮。

用 QHBoxLayout 横向排布，各行自带删除按钮；removeRequested 在点击
删除时带上本行自身，标题空行在收集时被忽略。

### `class NodeListWidget(QWidget)`

节点行容器：行数决定高度，无表头、无内部滚动条。

#### 方法

| 方法                                                               | 说明                                                   |
| ------------------------------------------------------------------ | ------------------------------------------------------ |
| `__init__(parent=None)`                                            | 构造节点容器：QVBoxLayout 逐行堆叠，默认显示空态提示。 |
| `count() -> int`                                                   | 返回当前节点行数量。                                   |
| `rows() -> list[NodeRow]`                                          | 返回节点行副本（防止外部直接改内部列表）。             |
| `collect() -> list`                                                | 按行序收集节点配置，空标题行忽略。                     |
| `add_row(page: int=1, title: str='', side: str='left') -> NodeRow` | 新增一行节点并刷新空态与高度；插入后发出 changed。     |
| `remove_row(row: NodeRow) -> None`                                 | 移除指定行：解绑布局、删除对象并刷新空态与高度。       |
| `clear() -> None`                                                  | 清空所有节点行。                                       |

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

| 方法                                            | 说明                                                            |
| ----------------------------------------------- | --------------------------------------------------------------- |
| `__init__(parent=None)`                         | 构建 print 面板：设滚动拉伸、联动标志并复位到默认。             |
| `set_source_defaults(source_stem: str) -> None` | 切换任务时调用：以源 PDF 名派生默认值并重置表单。               |
| `set_upstream_border(border) -> None`           | 写入上游（第三步 rembg/crop）border，并刷新通用边距默认值显示。 |
| `reset_to_default() -> None`                    | 恢复为该面板的内置默认参数（不依赖任何历史执行）。              |
| `reset_edits() -> None`                         | 撤销本次修改：恢复到最近一次执行的参数。                        |
| `mark_applied(parameters: dict) -> None`        | 记录最近一次执行使用的参数（供「放弃本次修改」恢复）。          |
| `set_inset(which: str, values) -> None`         | 程序化设置某段文字的「距页边」（which=title / page_number）。   |
| `inset(which: str) -> list \| None`             | 读当前「距页边」：`[上,右,下,左]`；未勾选"自定义"时是 None。    |
| `get_args() -> dict`                            | 收集 PDF 生成参数（校验颜色/边距，缺省回落内置默认）。          |

##### `__init__(parent=None)`

构建 print 面板：设滚动拉伸、联动标志并复位到默认。

基类 **init** 构建滚动表单后，这里开启标题/说明换行、初始化
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

⚠️ 默认值（`DEFAULT_PARAMS`）与下拉候选表的**唯一事实来源**已上移到
`panels/params_spec.py`（各阶段共用一张表，避免同一参数在「控件初值 /
`_apply_args` 兜底 / `reset_to_default`」三处各写一遍而漂移）。本模块只保留
print 专用的解析/序列化纯函数，并把 `DEFAULT_PARAMS` 重新导出以兼容既有导入。

表单 UI 见 print_form.py，面板状态见 print_panel.py。

### 模块函数

| 函数                                         | 说明                                                              |
| -------------------------------------------- | ----------------------------------------------------------------- |
| `parse_color(text: str) -> QColor`           | 解析 'r,g,b'（0~255）颜色字符串，非法时抛出 ValueError。          |
| `parse_margin4(text: str)`                   | 解析边距简写：1/2/3/4 值（CSS 简写）→ [上,右,下,左]；空→None。    |
| `margin_to_text(value) -> str`               | 边距列表转简写文本：四边相等→单值；上下/左右相等→两值；否则四值。 |
| `skip_pages_to_text(value) -> str`           | skip_pages 参数 → 表单文本（逗号分隔的页名）。                    |
| `text_to_skip_pages(text: str) -> list[str]` | 表单文本 → skip_pages 参数。                                      |

#### `parse_margin4(text: str)`

解析边距简写：1/2/3/4 值（CSS 简写）→ [上,右,下,左]；空→None。

⚠️ 必须与 CLI 的 `normalize_margin`（utils.margin_utils）同口径
（2026-09-26 审计 #13）：三值「上,左右,下」是合法写法（spec 的
title_margins 报错文案也明说 1/2/3/4），原先这里拒绝三值、同样的值
写进 guji.yaml 却能跑——GUI 比命令行更严，没有道理。

---

## `desktop.components.panels.print_sections`

源码：[`desktop/components/panels/print_sections.py`](../../desktop/components/panels/print_sections.py)

print 表单的五个分区（输出与纸张 / 页边距 / 标题 / 页码 / 过滤）。

从 `print_form.PrintFormMixin` 拆出。每个 `_build_xxx_section` 只负责
"往 root 里加一节的控件并把控件挂到 self 上"，**取值与回填不在这里**
（见 print_panel）。

- 依赖（均来自 `PrintFormMixin` / `PrintPanel`）：
  `_section` `_add_row` `_line_edit` `_make_combo` `_spin_with_unit`
  `_color_row` `_add_node_row` `_clear_node_rows` `_sync_enabled`
- 被依赖：`PrintFormMixin.build_form` 依次调用本模块的五个 builder

⚠️ 控件在**本模块**创建、却在 `PrintPanel` 里读写（`get_args` /
`_apply_args` / `_connect_preview_signals`）——这条跨模块的隐式契约由
`tests/selftests/print_form_split.py` 钉住：新增分区必须同时登记它挂到
self 上的控件名，否则漏挂没人会发现。

### `class PrintSectionsMixin(PrintInsetMixin)`

print 面板的分区构建（由 PrintFormMixin 继承）。

继承 `PrintInsetMixin` 是因为标题节/页码节都要调 `_make_inset` /
`_add_inset_rows`；MRO 上它排在 `PrintFormMixin` 之后，通用工具
（`_section` 等）由最终类 `PrintPanel` 的线性化解析到，无需再继承。

---

## `desktop.components.panels.print_text_layout`

源码：[`desktop/components/panels/print_text_layout.py`](../../desktop/components/panels/print_text_layout.py)

「位置 / 文字方向」的固定取值：桌面端不给选，但历史参数要原样回显。

从 `print_form.PrintFormMixin` 拆出。这一段**不碰任何控件**，只回答
"这段文字的位置 / 方向该导出成什么"，是全类里依赖最少的一块：

- 依赖：`self._fixed_layout_echo`（由 `PrintPanel.__init__` 初始化）
- 被依赖：`PrintFormMixin`（从而 `PrintPanel`）；`print_panel.get_args`
  经 `_fixed_layout` 取值，但不 import 本模块

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
`params_spec.DEFAULTS["rembg"]`。

#### 方法

| 方法                 | 说明                                              |
| -------------------- | ------------------------------------------------- |
| `get_args() -> dict` | 收集去底色参数：area/type/offset/seal/border 等。 |

##### `get_args() -> dict`

收集去底色参数：area/type/offset/seal/border 等。

border 留空时按 area 取默认（area=1/2/3 → 0、area=4 → 不设），
由 runner 在续跑时与 detect 框坐标实时合成裁剪区域。

---

## `desktop.components.progress_row`

源码：[`desktop/components/progress_row.py`](../../desktop/components/progress_row.py)

执行进度：细进度条 + 计数文案（**独立功能页共用的那一条**）。

为什么要有这个组件（2026-10-03）：

- 任务流程页早就有进度条（`desktop/pages/taskdetail/view.py` 的
  `stage_progress`），但**独立功能页一条都没有**——点「开始提取 / 去底色 /
  生成 PDF」之后，右栏只有一行"正在处理…"的文字，几十秒的活儿看不出跑到
  哪儿了；
- 数字必须和条**放在一起**：页头状态行与右栏底部隔着一屏，对不上号；所以
  计数（`12/48　25%`）直接跟在条右边，同一行读完。

四个状态方法（:meth:`start` / :meth:`update` / :meth:`succeed` / :meth:`fail`）
**谁在执行不重要**——`StepControl`（四个步骤页）与拼版页都用它，视觉与
口径只有一份。

⚠️ **总量未知**是常态而不是例外（print 的合成阶段、拼版合成、detect 出框
之前都报不出 total），此时 :class:`~desktop.ui.widgets.ProgressLine` 走
"来回滑动"的未知态，计数文案相应地不写 `x/y`。

### `class ProgressRow(QWidget)`

一行执行进度：左侧细进度条（伸展）+ 右侧计数/状态文案。

对外只认上面那四个状态方法加 :meth:`reset`。**不要**直接去摸
`self.bar.setRange/setValue`——计数文案、颜色、未知态滑块都得跟着一起
变，绕过方法就会漏掉其中一样。

#### 方法

| 方法                                    | 说明                                                                   |
| --------------------------------------- | ---------------------------------------------------------------------- |
| `__init__(parent=None, noun: str='')`   | `noun` 是这一步的计量单位（"页"/"张"），只影响完成文案。               |
| `start(text: str='正在处理…') -> None`  | 开始执行：条先摆出来（未知态滑块），计数位置显示提示文案。             |
| `update(done: int, total: int) -> None` | 一次进度汇报：有 total 就定量显示 `done/total  百分比`。               |
| `succeed(text: str='') -> None`         | 成功：条走到头，文案写最终计数（不给文案就只写"完成"）。               |
| `fail(text: str='执行失败') -> None`    | 失败：条**停住**（不清零——停在出错那一刻才看得出跑到哪儿），文案转红。 |
| `reset() -> None`                       | 收工复位：条与文案都藏起来（下次 :meth:`start` 再点亮）。              |
| `unit() -> str`                         | 计量单位后缀（"页"/"张"；没给单位就是空串）。**公开**访问器。          |
| `done_text() -> str`                    | 按"最后一次已知上限"拼收尾文案（`完成 12/12 页`）。                    |

##### `start(text: str='正在处理…') -> None`

开始执行：条先摆出来（未知态滑块），计数位置显示提示文案。

⚠️ **先显示、后知总量**：多数命令第一步是"数一遍文件"，那之前 total
拿不到；此时若把控件藏起来，用户会以为点了没反应。

##### `done_text() -> str`

按"最后一次已知上限"拼收尾文案（`完成 12/12 页`）。

给宿主（`StepControl`）在成功时用：有些命令最后一页不补发 progress
（print 只在 %10 与末页发，rembg 的失败张不计入 done），靠"最近一次
进度"会停在 90%。总量未知时只说"已完成"——别写"完成 0 页"。

---

## `desktop.components.step_bar`

源码：[`desktop/components/step_bar.py`](../../desktop/components/step_bar.py)

详情页顶部步骤条：编号/对勾徽标 + 连接箭头 + 主副标题。

设计要点：

- 每一步 = 圆形徽标（编号或 ✓）+ 标题 + 状态副标题，用形状表达"第几步"；
- 步骤之间用带箭头的连接线连起来，已完成的线段变色，直观表达先后顺序；
  连接线由 **StepBar 底层统一画**、从节点框**后面**穿过——节点框有实底
  （`_StepItem.pill` / 拼版节点自己画），框内那截线被遮住，线自然"从
  框后面出发"，不用再对齐框边缘；
- 节点框：所有节点**同一套外观**——SURFACE 实底 + 浅色描边 + 高亮底色，
  选中/当前只有底色变化、**没有边框差异**（用户 2026-09-30：其他节点即使
  选中也没有 border，只有背景色；拼版节点生效与否样式统一）；
- 状态色：未执行（灰）· 执行中（蓝）· 成功（绿）· 失败（红）· 已中断（橙）；
- 整步可点击切换，带悬停底色，避免按钮样式的标签堆叠感。

对外接口（兼容旧调用）：

- `buttons`：StepItem 列表（长度 = 步骤数）；
- `_completed`：已完成步骤下标集合；
- `set_steps` / `set_current` / `mark_completed` / `current_changed`。

### 模块常量

| 名称           | 值    |
| -------------- | ----- |
| \_BADGE        | `26`  |
| \_CONNECTOR_W  | `38`  |
| \_BYPASS_CLEAR | `28`  |
| \_NODE_MIN_W   | `140` |

### `class StepItem(QFrame)`

单个步骤：徽标 + 标题 + 状态副标题，整块可点击。

外层只负责在步骤条里占位（等宽拉伸，保证徽标横向均匀），
真正的底色/悬停胶囊是内层 `#stepPill`——它贴合内容宽度，
避免当前步骤的高亮底色被拉成一整格的"按钮"。

#### 方法

| 方法                                                                    | 说明                                                               |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `__init__(index: int, title: str, parent=None)`                         | 初始化单个步骤项：徽标 + 标题 + 副标题，整块可点击。               |
| `set_title(title: str) -> None`                                         | 只替换标题文案，不改动状态与徽标。                                 |
| `set_status(status: str, detail: str='', badge_status: str='') -> None` | status 决定副标题/标题色，badge_status 决定徽标（缺省同 status）。 |
| `set_current(current: bool) -> None`                                    | 设置是否为当前步骤，切换高亮底色与标题字重。                       |
| `paintEvent(_event) -> None`                                            | 自己画胶囊：样式表一旦出现在子树里，Qt 会把 QFrame 底色填白        |
| `enterEvent(event) -> None`                                             | Qt 事件覆写：鼠标移入时进入高亮态。                                |
| `leaveEvent(event) -> None`                                             | Qt 事件覆写：鼠标移出时恢复常态。                                  |
| `mouseReleaseEvent(event) -> None`                                      | Qt 事件覆写：松开（提交本次编辑）。                                |

##### `__init__(index: int, title: str, parent=None)`

初始化单个步骤项：徽标 + 标题 + 副标题，整块可点击。

index 为步骤下标（从 0）；pill 为真身胶囊，底色由 paintEvent 自绘
（不用样式表），current 高亮由 \_apply_style 控制。

##### `set_status(status: str, detail: str='', badge_status: str='') -> None`

status 决定副标题/标题色，badge_status 决定徽标（缺省同 status）。

两者分开是为了表达"这一步有产出，但最近一次重试失败"：
徽标仍是对勾，副标题用失败色写明最近一次的结果。

##### `paintEvent(_event) -> None`

自己画胶囊：样式表一旦出现在子树里，Qt 会把 QFrame 底色填白
（盖住步骤条的卡片底色），所以这里不用样式表。

胶囊**始终**有 SURFACE 实底 + 实线 border：实底用来遮住从框后面
穿过的连接线（见 `StepBar._draw_connectors`），实线 border 是
真实步骤的视觉语言（可选节点才是虚线）。高亮底色（当前/悬停）
叠在实底之上。

### `class StepBar(QWidget)`

横向步骤条：4 个步骤按顺序排列，当前步骤高亮、已完成步骤打勾。

除真实步骤外还支持一个**条件虚线节点**（「图片拼版」可选步骤）：
默认隐藏，`set_imposition_visible(True)` 时插到倒数两个步骤之间。
伪步骤下标 = 真实步骤数（`imposition_index`），`set_current` /
`current_changed` 都以它表达"当前在看拼版详情"。

节点有两条互相独立的状态线（别合并）：

- **选择态**（`set_imposition_selected`）：只管节点自己的外观
  （「已选择/未选择」副标题；节点没有边框差异、也不压高亮底色，
  与真实步骤同一套外观）；
- **生效态**（`set_imposition_active`）：这条支路是否真的承载流程
  （已启用且至少有一页拼版）。生效 → 两侧连接线常规点亮、节点徽标
  转绿色对勾；未生效 → 两侧连接线灰色虚线、徽标灰色「＋」，同时
  「去底色 → 生成 PDF」画一条从节点上方绕过的绕行线
  （`_draw_imposition_bypass`）——选了拼版但还没有拼版页时，
  第四步实际取的仍是第三步产物，线不能说谎。

节点的宽度与间距分成两件事（都踩过坑，别再合并）：

- **槽位**与真实步骤等宽（`imposition_slot` + stretch 1）→ 步骤间距均分；
- **节点框**只在槽位里靠左、宽度不超过内容但有统一默认下限
  （`QSizePolicy.Maximum` + `_NODE_MIN_W`）→ 不被拉宽、宽窄一致。

#### 方法

| 方法                                                                                                           | 说明                                                               |
| -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `__init__(steps, parent=None)`                                                                                 | 按给定步骤标题逐项构建；steps 允许传生成器。                       |
| `paintEvent(_event) -> None`                                                                                   | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。                |
| `set_current(index: int) -> None`                                                                              | 设置当前步骤下标并同步各步骤高亮与徽标。                           |
| `mark_completed(index: int) -> None`                                                                           | 标记某步骤已完成（徽标改为对勾，连接线着色）。                     |
| `set_steps(texts) -> None`                                                                                     | 兼容旧调用：只更新标题文本。                                       |
| `set_imposition_visible(visible: bool) -> None`                                                                | 显示/隐藏「图片拼版」虚线节点（随第三步区域模式是否为 1）。        |
| `set_imposition_selected(selected: bool) -> None`                                                              | 「图片拼版」是否被选择（副标题/徽标口径，不动连接线/绕行线）。     |
| `set_imposition_active(active: bool) -> None`                                                                  | 拼版支路是否**生效**（已启用且至少有一页拼版，宿主判定）。         |
| `set_step_status(index: int, status: str, progress: tuple \| None=None, completed: bool \| None=None) -> None` | 设置某步骤状态；progress 为 (已完成, 总数) 时拼出 "成功 · 84/84"。 |
| `reset_statuses() -> None`                                                                                     | 全部步骤恢复为未执行，并清空已完成标记。                           |

##### `set_imposition_visible(visible: bool) -> None`

显示/隐藏「图片拼版」虚线节点（随第三步区域模式是否为 1）。

⚠️ 槽位要一起隐藏：只藏节点的话，那格等宽槽位还占着位置，流程条上会
留出一段空白（第四步/PDF 看起来被推远）。
另外节点显示时行顶边距 6→18：给绕行线留一条**走线带**——拼版未生效
时「去底色 → 生成 PDF」的线要贴着节点上方绕过去（见
`_draw_imposition_bypass`），不预留高度弧线会顶到卡片边框。

##### `set_imposition_active(active: bool) -> None`

拼版支路是否**生效**（已启用且至少有一页拼版，宿主判定）。

生效 → 两侧连接线常规点亮、节点徽标转绿色对勾（与真实步骤同款）；
未生效 → 两侧连接线灰色虚线、徽标灰色「＋」，主流程改走节点上方
的绕行线。与 `set_imposition_selected`
（节点自己的选择外观）互不取代：选了但还没有拼版页时，节点
显示「已选择」，但线仍然是灰色虚线 + 绕行。

##### `set_step_status(index: int, status: str, progress: tuple | None=None, completed: bool | None=None) -> None`

设置某步骤状态；progress 为 (已完成, 总数) 时拼出 "成功 · 84/84"。

completed=False 但 status='success' 不可能出现；completed=True 而
status 为失败/中断时，徽标保持对勾、副标题仍显示最近一次的结果。

---

## `desktop.components.task_table`

源码：[`desktop/components/task_table.py`](../../desktop/components/task_table.py)

任务列表表格组件：每行带阶段状态胶囊与 详情/删除 操作按钮。
「子任务状态」原来是一整串 `提取图片:成功  检测文本框:成功 …` 纯文本，
列宽一紧就被截断、颜色上也没法区分成败。现在改为状态胶囊，颜色来自统一的
语义色，鼠标悬停能看到完整阶段名与进度。

⚠️ **每行的胶囊数量不固定**（用户 2026-10-03："子任务到底有几个需要根据详情
决定"）：详情里启用了「图片拼版」的任务会多一个「拼版」胶囊，插在「PDF」前面；
没启用的仍是四个。哪些胶囊由 `desktop/workers/task_rows_worker.py` 按任务
逐个判定，本组件只负责把给定的 stages 画出来——**别在这里写死数量**。

### 模块常量

| 名称       | 值   |
| ---------- | ---- |
| ROW_HEIGHT | `56` |

### `class NameLabel(QLabel)`

任务名标签：按可用宽度自动省略中间部分。

`QTableWidgetItem` 会自己省略，换成 QLabel 后得自己来——否则长名字
把拉伸列越撑越宽、表格被挤出横向滚动条。
⚠️ 省略时机放在 `resizeEvent` 而不是建表时：那时表格还没布局、
`columnWidth()` 只有几十像素，会把名字截成空串（已踩，表现为「名称列空白」）。
宽度不足 `_MIN_ELIDE_WIDTH` 时一律显示全名，等真实宽度来了再收。

下划线改为 `paintEvent` 自绘：字体原生下划线紧贴字形底部，间距不可调；
自绘后用 `_UNDERLINE_GAP` 控制【基线】到下划线的留白，线宽 1px，颜色跟随
`linkColor`（hover 切换时同步更新）。

#### 方法

| 方法                                  | 说明                                                   |
| ------------------------------------- | ------------------------------------------------------ |
| `__init__(text: str, parent=None)`    | 记下完整名字，先按全名显示，等布局给出真实宽度再省略。 |
| `setLinkColor(color: QColor) -> None` | 同步文字颜色与下划线颜色。                             |
| `linkColor() -> QColor`               | —                                                      |
| `full_text() -> str`                  | 完整任务名（省略后的 `text()` 可能带 …）。             |
| `resizeEvent(event)`                  | 宽度变化时重算省略；宽度还没定（未布局）就保持全名。   |
| `paintEvent(event)`                   | 先让父类画文字，再在文字下方自绘一条同色下划线。       |

##### `setLinkColor(color: QColor) -> None`

同步文字颜色与下划线颜色。

不再依赖 stylesheet 里的 `color:`（paintEvent 解析不了），
统一走这个方法——hover 进入/离开都调它。

##### `paintEvent(event)`

先让父类画文字，再在文字下方自绘一条同色下划线。
✅ 使用字体基线计算位置，不再依赖boundingRect，gap修改生效。
下划线只覆盖**实际文字宽度**（不铺满整个 label），和网页 <a> 行为一致；

### `class StageChips(QWidget)`

一行若干个阶段状态胶囊（数量由调用方给的 stages 决定，常见 4~5 个）。

#### 方法

| 方法                                        | 说明                                                    |
| ------------------------------------------- | ------------------------------------------------------- |
| `__init__(stages: list[dict], parent=None)` | 按 stages 逐项生成状态胶囊；每项需含 short/status/tip。 |

### `class TaskTable(QWidget)`

任务列表表格：每行带阶段状态胶囊与 详情/删除 操作。

列固定为 序号 / 任务名 / 创建时间 / 子任务状态 / 操作；源文件路径
不成列，仅作为任务名 tooltip。open_detail / delete_request 信号
分别携带任务 id。

「序号」列 = **任务编号**（`0001`、`0002`…，即 `task["id"]` 与
任务目录名），不是行号——排序/搜索/翻页都不改变它。

#### 方法

| 方法                                 | 说明                                                |
| ------------------------------------ | --------------------------------------------------- |
| `__init__(parent=None)`              | 初始化表格：5 列布局、行高与表头对齐。              |
| `set_data(rows: list[dict]) -> None` | rows: [{id, name, source_path, created_at, stages}] |
| `select_task(task_id: str) -> bool`  | 选中并滚动到指定任务所在行，返回是否找到。          |

##### `__init__(parent=None)`

初始化表格：5 列布局、行高与表头对齐。

表头对齐跟随各列内容（序号/时间居中、名称/状态左对齐，均垂直居中）；
任务名称列自适应拉伸（占主要宽度），其余列按 \_COLUMN_WIDTHS 固定宽度。

##### `set_data(rows: list[dict]) -> None`

rows: [{id, name, source_path, created_at, stages}]

stages 为 `[{"short": "提取", "status": "success", "tip": "..."}]`；
source_path 不单独成列，仅作任务名的悬浮提示。

⚠️ 「序号」列显示的是**任务自己的编号**（`task["id"]`，如 `0001`），
不是行号/页内序号：任务号是任务目录名、也是索引里的主键，与排序、
搜索、分页都无关，用户拿它去 `tasks/0001` 就能对上号。
（早先用「页内行号 + 全局偏移」，翻页/搜索后同一条任务的号会变，
用户按号找目录会对不上。）

---

## `desktop.components.viewers.image_editor`

源码：[`desktop/components/viewers/image_editor.py`](../../desktop/components/viewers/image_editor.py)

图片编辑弹窗：裁剪 / 擦除 / 插入文字（Win10 照片风格）。

从图片预览弹窗（`image_zoom_dialog`）的「编辑」按钮进入，编辑的是
**画布当前整分辨率图**（已含翻转/旋转）；「完成」后写回弹窗画布。宿主
给 `save_back=True`（画布显示 1:1 对应真实文件）时，「完成」= 直接
**原子覆盖原图片文件**；虚拟预览（区域合成/打印重排/PDF 页）没有文件
可回写，维持"满意用「下载」落盘、翻页/关窗即丢弃"的旧行为。

五个工具的行为口径：

- **裁剪**：**默认选中整幅图**，沿四边/四角**任意位置**向内拖收边（整条
  边都是命中带，不只手柄小方块）、拖框中间移动；松手后**视图自动适配新
  选区**（选区变小就放大查看）。不做截图式"拖拽画框"——那是截图的交互，
  裁剪的语义是"从原图里收出想要的部分"（用户 20:05 定）。
- **变换**（GIMP「统一变换」口径，处理古籍褶皱/歪斜）：**默认选中整幅
  图**，拖角=缩放（Shift 等比）、拖边=切变、框内拖=移动、框外拖=**绕
  轴心旋转**（Shift 每 15° 吸附）；轴心圆点可拖动，「从轴心」勾选后
  缩放/切变也以轴心为锚。勾选「**调整范围**」后沿边拖动**收小要处理的
  区域**（收完自动回到变换模式）——小范围修褶皱就是"收小区域 → 旋转/
  切变把它正回来"。拖动即实时预览（原区域填白，变换后的内容以
  浮层显示）；「应用变换」（或切走工具/「完成」）才烘焙进像素——原
  区域填白、只把选区内容按仿射矩阵画回去，画布尺寸不变，**区域外的
  像素一动不动**。一批一个撤销点。
- **变形**（**PS 操控变形 Puppet Warp 口径**，处理古籍褶皱/卷曲/线段倾斜）：
  在图上**打图钉**（点一下放一个）→ 拖某个图钉，**它附近的内容跟着走、
  离得越远动得越少、没被钉住的远处几乎不动**（"像扯弹簧"/"像揉面团"）。
  - **加图钉**：工具激活时直接点图上的位置；点已有图钉附近＝选中它而不是
    新建（吸附半径 :data:`PIN_HIT_VIEW_PX`）。
  - **删图钉**：`Alt`+点，或右键点。
  - **图钉拖到图外**：允许（往外拉＝把那块内容往外拉伸），越界部分填底。
  - **网格疏密**：算法把图片切成三角网格，格距在选项行选（见
    :data:`MESH_DENSITY_CHOICES`）；越密越细腻、解方程越慢。
  - ⚠️ **边框自动锚定**：ARAP 能量对整体平移/旋转不变，只钉一个图钉时整张
    网格会"一起漂移"（实测每个顶点都平移 14px）。所以默认把**图片四边**
    视为固定（PS 的做法），拖内部图钉时边框被拉住，形变才收敛成"近处大、
    远处为零"（见 `utils.puppet_warp.solve_puppet`）。
  - 拖动即实时预览（只算动过的网格凸包包围盒 + 按屏幕清晰度降采样，见
    :func:`cage_preview_scale`），松手补一帧更清楚的；「应用变形」（或切走
    工具/「完成」）才烘焙进像素（有等待光标）。
  - ⚠️ 「应用变形」后**图钉留在原地**（`adopt_pins`）：古籍褶皱往往要来回
    试几次，每次应用后都清空图钉的话用户得重新钉一遍。
    算法与口径见 `utils/puppet_warp.py`。
    ⚠️ 进这个工具时图片**不铺满视口**（:data:`DEFORM_FIT_RATIO`），四周留白
    方便把图钉往图外拖。
- **擦除**：按住左键涂抹把污点**擦成白底**（古籍页面去污点就是涂白）；
  直径在选项行可调；光标处有**实圈指示**，直径恒等于实际擦除直径
  （所见即所擦）。一笔一个撤销点。
  （原「拉伸」与笔刷配色已按用户 2026-10-01 要求移除；同日按 GIMP
  变换笼方案重新实现为上面的「变形」。）
- **文字**：点击落点 → 画布上**就地输入**（光标可见，点已有块可继续
  编辑）→ 选项行可调字体 family / 字号 / **颜色选择器**（对整块即时
  生效，样式是段落属性，与手机作图App同口径）→ 鼠标悬停在文字上出现
  **边界虚线框**，按住拖动整块移动（虚线框跟随，松手即消失）→
  「插入文字」把块写进图片（切走工具或点「完成」时未插入的块也自动
  写入）。一个批次一个撤销点。

  选项行的字体下拉**以中文字体为主**、只带几个常用西文字体（系统字体库
  动辄两三百个族，全列出来反而找不到"仿宋"，见 `ui.fonts`）；颜色是
  **一个按钮**，常用色块收在它弹出的面板里（见 `ui.color_picker`）。

  ⚠️ 样式改动作用在"**当前样式块**"（`EditorCanvas.style_target_block`）
  上，而不是"场景焦点项"：选项行的控件（尤其 qfluentwidgets 的 Slider，
  它是 `StrongFocus`）一被点击就会抢走键盘焦点，场景焦点项随之变 None，
  按焦点项找块的话**改字号/颜色全部落空**（用户 2026-10-01 报障）。

⚠️ 撤销栈存的是**整图快照**（QImage 写时复制在就地绘制时仍会共享底层数据，
必须 `copy()`），上限 12 步——4000px 预览约 60MB/步，再多内存吃不消。

### 模块常量

| 名称                         | 值        |
| ---------------------------- | --------- |
| UNDO_LIMIT                   | `12`      |
| WHEEL_STEP                   | `1.15`    |
| MIN_RECT_EDGE                | `4.0`     |
| HANDLE_VIEW_PX               | `12.0`    |
| EDGE_BAND_VIEW_PX            | `8.0`     |
| SEL_FIT_RATIO                | `0.8`     |
| EDIT_FIT_RATIO               | `0.8`     |
| PIVOT_VIEW_PX                | `14.0`    |
| ROTATE_SNAP_DEG              | `15.0`    |
| MESH_DENSITY_DEFAULT         | `40.0`    |
| DEFORM_FIT_RATIO             | `0.8`     |
| PIN_NODE_VIEW_PX             | `9.0`     |
| PIN_HIT_VIEW_PX              | `11.0`    |
| QUAD_HANDLE_VIEW_PX          | `8.0`     |
| QUAD_HIT_VIEW_PX             | `12.0`    |
| RECTIFY_RATIO_DEFAULT        | `"area"`  |
| DEFORM_PREVIEW_PIXELS        | `120000`  |
| DEFORM_PREVIEW_SETTLE_PIXELS | `2500000` |
| DEFORM_PREVIEW_INTERVAL      | `0.08`    |
| CAGE_HANDLE_VIEW_PX          | `8.0`     |
| CAGE_HIT_VIEW_PX             | `12.0`    |
| CAGE_EDGE_BAND_VIEW_PX       | `8.0`     |
| CAGE_PREVIEW_PIXELS          | `250000`  |
| CAGE_PREVIEW_SETTLE_PIXELS   | `2500000` |
| CAGE_PREVIEW_INTERVAL        | `0.08`    |
| CAGE_FIT_RATIO               | `0.8`     |
| CAGE_DENSITY_DEFAULT         | `2`       |

### `class TextBlockItem(QGraphicsTextItem)`

画布上的待插入文字块：就地编辑（光标可见），按住拖动整体移动。

交互口径：**单击**进编辑态放光标（QGraphicsTextItem 原生），**按住
拖动**超过阈值 = 移动整块。刻意不复用 `ItemIsMovable`——它与文本
编辑的"按住选字"打架，这里按位移阈值自己分流。拖动全程由画布的
**边界虚线框**跟随（悬停即显示、松手即消失），用户随时知道"这一块
会被整体挪走"（用户 2026-10-01：手机作图式文字）。

#### 方法

| 方法                                                          | 说明                                                   |
| ------------------------------------------------------------- | ------------------------------------------------------ |
| `__init__(pos: QPointF, px: int, color: QColor, family: str)` | —                                                      |
| `apply_style(family: str, px: int, color: QColor) -> None`    | 选项行改字体/字号/颜色时对块即时生效（编辑中也能改）。 |
| `mousePressEvent(event) -> None`                              | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。           |
| `mouseMoveEvent(event) -> None`                               | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。         |
| `mouseReleaseEvent(event) -> None`                            | Qt 事件覆写：松开（提交本次编辑）。                    |
| `keyPressEvent(event) -> None`                                | Qt 事件覆写：键盘操作（如 Delete 删除选中项）。        |
| `focusInEvent(event) -> None`                                 | —                                                      |
| `focusOutEvent(event) -> None`                                | —                                                      |

##### `apply_style(family: str, px: int, color: QColor) -> None`

选项行改字体/字号/颜色时对块即时生效（编辑中也能改）。

⚠️ 是**整块**生效：setFont/setDefaultTextColor 作用于整个文档，
与手机作图App一致——样式是段落属性，不做逐字混排。

### `class EditorCanvas(QGraphicsView)`

编辑画布：滚轮缩放、中/右键拖拽平移、左键按工具交互。

场景坐标 = 图片像素（pixmap 刻意不设 devicePixelRatio，与预览弹窗同
口径）。选区矩形（裁剪）几何全部落在**图片坐标系**，缩放只影响显示。
裁剪不做"拖拽画框"：**默认全选**，只许收边/框内移动。

#### 方法

| 方法                                                                                 | 说明                                                                   |
| ------------------------------------------------------------------------------------ | ---------------------------------------------------------------------- |
| `__init__(parent=None)`                                                              | —                                                                      |
| `set_image(image: QImage \| None) -> None`                                           | 装入/替换图片并重新适应窗口（裁剪/撤销等"画布换图"也走这里）。         |
| `refresh() -> None`                                                                  | 像素被就地改过（擦除）后只刷显示，不动缩放与滚动位置。                 |
| `replace_image(image: QImage) -> None`                                               | 就地换图（尺寸不变的语义，如文字写入）：不动缩放与滚动位置。           |
| `image() -> QImage \| None`                                                          | —                                                                      |
| `image_rect() -> QRectF`                                                             | 图片占位（= 场景坐标，1 场景单位 = 1 图片像素）。                      |
| `set_tool(tool: str) -> None`                                                        | 切换工具：裁剪/变换/变形默认全选，其余清选区、换光标。                 |
| `set_eraser(size: int) -> None`                                                      | 设置橡皮擦直径（图片像素）；擦除固定涂白，没有颜色可选。               |
| `selection() -> QRectF \| None`                                                      | 当前选区（图片坐标）；不足最小边视为没有。                             |
| `add_text_block(pos: QPointF, px: int, color: QColor, family: str) -> TextBlockItem` | 在落点放一个可就地编辑的文字块并给它焦点（光标闪烁）。                 |
| `text_blocks() -> list[TextBlockItem]`                                               | 画布上所有待插入文字块。                                               |
| `focused_text_block() -> TextBlockItem \| None`                                      | 正在编辑的文字块（场景焦点项；键盘输入路由用）。                       |
| `style_target_block() -> TextBlockItem \| None`                                      | 选项行改样式时作用的那一块：优先正在编辑的，其次"当前样式块"。         |
| `focus_text_block(block: TextBlockItem \| None=None) -> None`                        | 把键盘焦点还给文字块（颜色面板关掉后接着打字用）。                     |
| `clear_text_blocks() -> None`                                                        | 清掉所有文字块（插入/换图/关编辑时）。                                 |
| `set_transform_about_pivot(about: bool) -> None`                                     | 「从轴心」：缩放/切变以轴心为锚（旋转永远绕轴心）。                    |
| `set_transform_reshape(on: bool) -> None`                                            | 「调整范围」模式：拖手柄/边=收小变换区域，而不是缩放内容。             |
| `reset_transform() -> None`                                                          | 「重置」：丢弃未应用的变换，选区回到整幅、轴心回到中心。               |
| `transform_pending() -> tuple[QRectF, QTransform, QImage] \| None`                   | 未应用的变换 `(选区, 矩阵, 选区像素快照)`；没有则 None。               |
| `transform_move(dx: float, dy: float) -> None`                                       | 整体平移 `dx, dy`（图片像素）。                                        |
| `transform_rotate(degrees: float) -> None`                                           | 绕**轴心当前视觉位置**旋转（轴心保持不动）。                           |
| `transform_scale(sx: float, sy: float, anchor: QPointF \| None=None) -> None`        | 缩放（局部空间，锚点缺省=轴心；sx/sy 是相对当前内容的倍率）。          |
| `transform_shear(edge: str, k: float) -> None`                                       | 拖边切变：`edge` 是被抓的边（l/r/t/b），`k` 是切变系数，               |
| `mesh_density() -> float`                                                            | 当前网格格距（图片像素档位）。                                         |
| `set_mesh_density(cell: float) -> None`                                              | 改网格格距：**重建网格并清空图钉**（顶点下标全变了，旧钉无意义）。     |
| `reset_pins() -> None`                                                               | 「重置」：清空所有图钉，丢掉未应用的形变（网格本身保留）。             |
| `pins() -> list`                                                                     | 当前图钉的副本（`(顶点下标, QPointF)` 列表）——给自测与外部读。         |
| `pin_count() -> int`                                                                 | 当前图钉个数。                                                         |
| `pin_add(pos: QPointF) -> int \| None`                                               | 在 `pos`（图片坐标）加一个图钉，返回它在 `_pins` 里的下标。            |
| `pin_remove(index: int) -> None`                                                     | 删掉第 `index` 个图钉（形变随之重解）。                                |
| `pin_move(index: int, pos: QPointF) -> None`                                         | 把第 `index` 个图钉拖到 `pos`（图片坐标）。                            |
| `pins_pending()`                                                                     | 未应用的形变 `(vertices_rest, vertices_moved, triangles)`；无则 None。 |
| `adopt_pins(pin_vertices=None) -> None`                                              | 「应用变形」后用：把图钉**原地保留**（目标位置 = 新网格的原位）。      |
| `reset_cage() -> None`                                                               | 「重置」：把手回到整幅图原位（丢掉未应用的形变）。                     |
| `cage_density() -> int`                                                              | 当前每边把手数档位。                                                   |
| `set_cage_density(per_side: int) -> None`                                            | 改每边把手数：**重建笼并清掉未应用的形变**（把手序号全变了）。         |
| `cage() -> list`                                                                     | 当前把手副本 `[(原位, 当前位置), ...]`——给自测与外部读。               |
| `cage_source() -> list[QPointF]`                                                     | 把手**原位**序列（形变映射的左端）。                                   |
| `cage_target() -> list[QPointF]`                                                     | 把手**当前位置**序列（形变映射的右端）。                               |
| `cage_pending()`                                                                     | 未应用的笼形变 `(cage_src, cage_dst)`；没动过返回 `None`。             |
| `cage_move(index: int, pos: QPointF) -> None`                                        | 把第 `index` 个把手拖到 `pos`（图片坐标，允许图外）。                  |
| `cage_move_all(delta: QPointF) -> None`                                              | 整体平移笼（拖边/拖笼内部）：把所有把手在**按下时的快照**上位移。      |
| `reset_quad() -> None`                                                               | 「重置」：四角回到整幅图四角（丢掉未应用的校正）。                     |
| `quad() -> list`                                                                     | 当前四边形四角副本（`QPointF` 列表）——给自测与外部读。                 |
| `rectify_ratio() -> str`                                                             | 目标矩形宽高比口径（见 RECTIFY_RATIO_CHOICES）。                       |
| `set_rectify_ratio(mode: str) -> None`                                               | 改目标矩形口径：只影响**之后的**预览，不必丢掉当前四角。               |
| `quad_move(index: int, pos: QPointF) -> None`                                        | 把第 `index` 个角拖到 `pos`（图片坐标）。                              |
| `quad_pending()`                                                                     | 未应用的校正 `(quad, mode)`；四角没动过则 None。                       |
| `fit(ratio: float \| None=None) -> None`                                             | 适应窗口（整图完整可见）；`ratio` < 1 时四周留白。                     |
| `set_fit_ratio(ratio: float) -> None`                                                | 设「适应窗口」时图片占视口的比例（1.0 = 铺满，< 1 = 四周留白）。       |
| `zoom_in() -> None`                                                                  | 放大一档（工具栏按钮用；无档位表，连续乘 1.25）。                      |
| `zoom_out() -> None`                                                                 | 缩小一档。                                                             |
| `set_zoom(zoom: float, anchor_view: QPointF \| None=None) -> None`                   | 锚点缩放（同预览弹窗的 translate 补偿法，缩放不漂移）。                |
| `resizeEvent(event) -> None`                                                         | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。                           |
| `fit_selection() -> None`                                                            | 视图适配当前选区（选区约占视口 80%，四周留出可操作白边）。             |
| `wheelEvent(event) -> None`                                                          | Qt 事件覆写：滚轮（缩放 / 滚动）。                                     |
| `mousePressEvent(event) -> None`                                                     | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。                           |
| `mouseMoveEvent(event) -> None`                                                      | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。                         |
| `mouseReleaseEvent(event) -> None`                                                   | Qt 事件覆写：松开（提交本次编辑）。                                    |
| `leaveEvent(event) -> None`                                                          | Qt 事件覆写：鼠标移出时恢复常态。                                      |
| `keyPressEvent(event) -> None`                                                       | Qt 事件覆写：键盘操作（如 Delete 删除选中项）。                        |

##### `add_text_block(pos: QPointF, px: int, color: QColor, family: str) -> TextBlockItem`

在落点放一个可就地编辑的文字块并给它焦点（光标闪烁）。

⚠️ 顺便把键盘焦点拿回视图：场景焦点项的输入要靠「视图持有键盘
焦点 → keyPressEvent 转发」这条链，视图没焦点时打字全落空。

##### `style_target_block() -> TextBlockItem | None`

选项行改样式时作用的那一块：优先正在编辑的，其次"当前样式块"。

⚠️ 与 :meth:`focused_text_block` 分开是刻意的：点选项行的滑杆/按钮
会抢走键盘焦点，此时"正在编辑"已经没了，但用户**期望**改动仍落在他
刚点的那个文字块上（用户 2026-10-01 报"字号不生效"就是这个原因）。

##### `set_transform_reshape(on: bool) -> None`

「调整范围」模式：拖手柄/边=收小变换区域，而不是缩放内容。

进入时必须丢掉未应用的变换预览——浮层与填白底都是按**旧区域**
快照做的，区域一变它们就与画布对不上了。退出（收边完成/取消
勾选）后保留收小的区域，下一次拖动即以它为变换对象。

##### `transform_shear(edge: str, k: float) -> None`

拖边切变：`edge` 是被抓的边（l/r/t/b），`k` 是切变系数，
对边为锚（抓右边往下拖 = 内容随 x 增大而下斜）。

##### `pin_add(pos: QPointF) -> int | None`

在 `pos`（图片坐标）加一个图钉，返回它在 `_pins` 里的下标。

图钉**吸附到最近的网格顶点**（ARAP 的硬约束只能钉在顶点上）；同一
顶点已有图钉时不再重复加，直接返回已有的那个。

##### `pin_move(index: int, pos: QPointF) -> None`

把第 `index` 个图钉拖到 `pos`（图片坐标）。

⚠️ **允许拖到图片外面**（用户 2026-10-01：「任意点只能向内，不能向外」）。
往外拖＝把那块内容往外**拉伸**，拉出画布的部分按越界填底。这里只留一个
"一张图那么远"的宽松上限，免得图钉被甩到天外、再也找不回来。

##### `pins_pending()`

未应用的形变 `(vertices_rest, vertices_moved, triangles)`；无则 None。

「未应用」= 解出的网格确实动过。全都没动时返回 None，调用方据此
跳过烘焙（不产生多余的撤销点）。

##### `adopt_pins(pin_vertices=None) -> None`

「应用变形」后用：把图钉**原地保留**（目标位置 = 新网格的原位）。

⚠️ 为什么不清空：古籍褶皱往往要来回试几次，每次应用后都清空图钉的话
用户得重新钉一遍。保留图钉、并让它们落在**刚烘焙完的图**的原位，
就可以接着微调同一块。

⚠️ `pin_vertices` 必须由调用方在 `set_image` **之前**快照传入：
:meth:`set_image` 换图时会把 `_pins` 清空（换图后旧钉无意义），
所以这里不能指望调用时 `self._pins` 还在。传 `None` 时退回读
当前 `self._pins`（兼容直接调用）。

##### `cage_pending()`

未应用的笼形变 `(cage_src, cage_dst)`；没动过返回 `None`。

口径与 :meth:`pins_pending` 一致：只有"把手真的动过"才算待应用。

##### `cage_move_all(delta: QPointF) -> None`

整体平移笼（拖边/拖笼内部）：把所有把手在**按下时的快照**上位移。

必须基于快照位移，不能逐帧累加——否则每帧都从"当前值"再位移一次，
手一停位置就漂（浮点累积）。

##### `quad_move(index: int, pos: QPointF) -> None`

把第 `index` 个角拖到 `pos`（图片坐标）。

⚠️ **允许拖到图片外面**（四角要能框住"拍摄时把纸张也拍进来了"的
边界）。只留一个"一张图那么远"的宽松上限，免得角点被甩丢。

##### `fit(ratio: float | None=None) -> None`

适应窗口（整图完整可见）；`ratio` < 1 时四周留白。

留白的做法是把"要装进去的矩形"按比例放大——图片因此只占视口的
`ratio`（见 :data:`DEFORM_FIT_RATIO`：进「变形」时图片不顶满视口，
用户才有地方把笼把手往图外拖）。

##### `set_fit_ratio(ratio: float) -> None`

设「适应窗口」时图片占视口的比例（1.0 = 铺满，< 1 = 四周留白）。

只在用户**没手动缩放过**时立刻生效——手动缩放是明确意图，不该被悄悄
改掉；但他下次点「适应窗口」或改窗口大小时就按新比例来。

##### `fit_selection() -> None`

视图适配当前选区（选区约占视口 80%，四周留出可操作白边）。

裁剪区收小后松手时调用——选区变小了就要放大查看（用户 20:18 定）。
⚠️ 不填满视口：顶满时选区边界贴着视口边缘，看不到上下文、手柄
也挤在边上不好抓（用户 20:28 定"缩放至选区时留出边距"）。
视图从此锚定选区（`_user_zoomed`），窗口 resize 不再拉回整图。

### `class ImageEditorDialog(QDialog)`

图片编辑弹窗：顶部工具/选项行 + 中央画布 + 底部状态行。

`accepted` 后用 :meth:`result_image` 取编辑结果；关闭/拒绝即放弃。

#### 方法

| 方法                                                                       | 说明                                                        |
| -------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `__init__(parent=None, image: QImage \| None=None, save_back: bool=False)` | —                                                           |
| `closeEvent(event) -> None`                                                | 关闭时确保**没有在飞的后台线程**。                          |
| `result_image() -> QImage \| None`                                         | 编辑结果（无图时 None；是否采纳由调用方的 exec 结果决定）。 |

##### `closeEvent(event) -> None`

关闭时确保**没有在飞的后台线程**。

⚠️ 烘焙 worker 以对话框为 `parent`。若在它还在跑的时候对话框被
析构，Qt 会直接 **abort 整个进程**
（`QThread: Destroyed while thread is still running`）。
正常流程里 :func:`run_with_progress` 自己同步等线程结束，但
`processEvents` 期间用户仍可能关窗/宿主强制退出，所以这里要兜底。

同时清画布：撤销栈是**整图快照**，大图下最多 12 份（见 `UNDO_LIMIT`），
关窗后必须释放，不能靠 Python GC（Qt 侧 C++ 对象不由引用计数托管）。

### 模块函数

| 函数                                                                                                                          | 说明                                                                     |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `clamp_rect(rect: QRectF, bounds: QRectF) -> QRectF`                                                                          | 把矩形夹进边界内（先平移、超界再缩边）；空矩形原样返回。                 |
| `rotate_about(point: QPointF, degrees: float) -> QTransform`                                                                  | 绕 `point` 旋转 `degrees`（正=顺时针）。                                 |
| `scale_about(point: QPointF, sx: float, sy: float) -> QTransform`                                                             | 绕 `point` 缩放（sx/sy 为 0 会退化，调用方保证非零）。                   |
| `shear_about(point: QPointF, sh: float, sv: float) -> QTransform`                                                             | 绕 `point` 切变：水平 sh（x 随 y 斜切）、垂直 sv（y 随 x 斜切）。        |
| `bake_transform(image: QImage, rect: QRectF, xf: QTransform, region: QImage, grow: bool=False)`                               | 把「选区内容经 `xf` 变换」烘焙进图片。                                   |
| `transform_region(image: QImage, rect: QRectF, xf: QTransform)`                                                               | `grow` 模式的目标画布：`(ox, oy, width, height)`。                       |
| `bake_puppet(image: QImage, vertices_rest, vertices_moved, triangles, grow=False, progress=None)`                             | 把「网格 `vertices_rest` → `vertices_moved`」的形变烘焙进图片。          |
| `cage_preview_scale(span_x: float, span_y: float, on_screen: float=1.0, budget_pixels: float=DEFORM_PREVIEW_PIXELS) -> float` | 拖动预览的降采样倍率：清晰度与成本的**取小**。                           |
| `wait_cursor()`                                                                                                               | 耗时操作期间挂等待光标。                                                 |
| `run_with_progress(parent: QWidget \| None, title: str, label: str, work, params: dict)`                                      | 在后台线程跑 `work(params, progress)` 并显示进度对话框。                 |
| `draw_text(image: QImage, pos: QPointF, text: str, px: int, color: QColor, family: str \| None=None) -> QImage`               | 在 `pos`（文字块左上角）画文字（可多行，行距 1.25 倍）；空文本原样返回。 |

#### `bake_transform(image: QImage, rect: QRectF, xf: QTransform, region: QImage, grow: bool=False)`

把「选区内容经 `xf` 变换」烘焙进图片。

`grow=False`（旧行为）：画布尺寸不变——先把**原区域**填白（内容被挪走/
变形后空出来的地方），再在 `xf` 变换下把选区快照画回去。古籍整页白底，
填白视觉上最干净。

`grow=True`（用户 2026-10-02）：「图片倾斜后一部分区域超出原本边界，
现在会被截掉」——**不截**。最终画布 = 「原图边界 ∪ 变换后选区的外框」
（:func:`transform_region`）。返回 `(QImage, (ox, oy))`，`(ox, oy)` =
新画布左上角在原坐标系里的位置（可为负）。

#### `transform_region(image: QImage, rect: QRectF, xf: QTransform)`

`grow` 模式的目标画布：`(ox, oy, width, height)`。

用户口径（2026-10-02）：「一切以新图为准，新图什么样就什么样，老图不要了」
——最终图 = **变换后内容的完整外框**，而不是"原图 ∪ 变换后"。

内容 = ①变换后的选区（仿射把矩形映成平行四边形，落在四角外接框内）
∪ ②**选区之外**原本就留着的那部分原图（选区整体移走时这块为空）。
选区原位被移走、内容被填白，所以**不再算进外框**——若按"原图边界"取并，
整体平移就会凭空多出一条填白边（用户要的正是把它去掉）。

#### `bake_puppet(image: QImage, vertices_rest, vertices_moved, triangles, grow=False, progress=None)`

把「网格 `vertices_rest` → `vertices_moved`」的形变烘焙进图片。

与 :func:`bake_transform` 同口径：**没动过的网格区域**逐字节不动，只是
这里不是仿射矩阵，而是 ARAP 三角网格逐像素重映射（PS 操控变形口径，
见 `utils.puppet_warp`）。
⚠️ **保留 alpha**：桌面侧编辑的常常是第三步产物「白底透明 PNG」，
丢掉 alpha 会让整片透明背景变成不透明黑（用户 2026-10-01 报过）。

`grow=True`：图钉拖出原边界时不裁，画布放大，返回 `(QImage, (ox, oy))`
（用户 2026-10-02：「超出原本区域的不要截，最终结果按最后图片的范围」）。

`progress` 透传（见 `utils.puppet_warp.puppet_warp`）；被中止时
返回 `None`。

#### `cage_preview_scale(span_x: float, span_y: float, on_screen: float=1.0, budget_pixels: float=DEFORM_PREVIEW_PIXELS) -> float`

拖动预览的降采样倍率：清晰度与成本的**取小**。

两个约束：

1. **清晰度**：`on_screen` = 场景 1 单位对应多少**设备像素**
   （= 当前缩放 × dpr）。预览取到这个倍率时，预览图上的 1 像素正好
   落在屏幕 1 设备像素上——看着与原图一样清楚，再取大就是纯浪费。
2. **成本**：处理面积不超过 `budget_pixels`。

缩到 1/3 看整页时清晰度约束直接给出 1/3：比按成本算还省 9 倍工作量，
而且屏幕上看不出区别（这正是"预览"该有的样子）。

`budget_pixels` 由调用方按场合给：拖动中给
:data:`DEFORM_PREVIEW_PIXELS`（要跟手），松手后给
:data:`DEFORM_PREVIEW_SETTLE_PIXELS`（停下来看结果，宁可慢一点也要清楚）。

#### `wait_cursor()`

装饰器：`contextlib.contextmanager`

耗时操作期间挂等待光标。

⚠️ 必须 `processEvents` 一下，否则光标要等界面回到事件循环才换，
而那时的等待已经结束了（等于没挂）。调用方负责别在里面重入。

#### `run_with_progress(parent: QWidget | None, title: str, label: str, work, params: dict)`

在后台线程跑 `work(params, progress)` 并显示进度对话框。

返回工作结果；被用户取消时返回 `None`。`work` 必须是**纯计算**
（只用到形参，不碰 Qt 部件/画布），这样才能安全地放进工作线程。
小任务（预估很快）也不亏：线程启动 + 对话框开销在毫秒级。

⚠️ 工作函数**抛异常**时**重新抛出**（`raise worker.error`），
调用方负责弹错误框并退回撤销点。绝不能把它折叠成 `None` ——
`None` 的既定含义是"用户取消"，混同的结果是"点了 20 秒什么都没发生
且无提示"（用户报过的现象，见 :meth:`_BakeWorker.run`）。

⚠️ 本函数**不吞异常、也不留孤儿线程**：整体 `try/finally`，
`finally` 里 `cancel() + wait()`。异常逃出等待循环时若不收尾，
worker 会变成孤儿线程，而它是被 `parent`（编辑器对话框）持有的 ——
对话框一析构就是 `QThread: Destroyed while thread is still running`，
**Qt 直接 abort 整个进程**（本项目 `worker_host` 已记过这条）。

#### `draw_text(image: QImage, pos: QPointF, text: str, px: int, color: QColor, family: str | None=None) -> QImage`

在 `pos`（文字块左上角）画文字（可多行，行距 1.25 倍）；空文本原样返回。

`family` 缺省用主题字体；文字块（就地编辑）烧进图片时传块当时的
family，保证"所见即所得"。

---

## `desktop.components.viewers.image_view`

源码：[`desktop/components/viewers/image_view.py`](../../desktop/components/viewers/image_view.py)

大图查看控件：随控件尺寸缩放，支持叠加切割框。

坐标基准是图片原始像素坐标（\_image_size），与预览显示缩放无关。

开启 boxes_editable 后：

- 点击框选中（四角出现缩放手柄），拖动框内移动整框，拖手柄缩放；
- 在空白处按下并拖动可手绘一个新框；
- Delete/Backspace 删除选中框；
- 每次修改结束通过 boxes_edited 发出全部框（仅内存与信号，不落盘）。

reference_boxes 为参考框（如按 area/border 规则推导的最终裁剪大框），
橙色虚线显示，不参与编辑。

### 模块常量

| 名称          | 值  |
| ------------- | --- |
| HANDLE_RADIUS | `5` |

### `class ImageView(QLabel)`

大图查看：随控件尺寸实时缩放，支持在图片坐标系叠加切割框。

#### 方法

| 方法                                                                                              | 说明                                                               |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `__init__(placeholder: str='无预览', parent=None)`                                                | 初始化画布与框编辑状态；placeholder 为空图时的占位文案。           |
| `has_image() -> bool`                                                                             | 当前是否已装入图片。                                               |
| `full_mode() -> bool`                                                                             | 本页是否为整幅(fullcontent)——整幅页只有「整幅」一种框类型。        |
| `max_boxes() -> int`                                                                              | 本页允许的框数上限：整幅 1 个；半幅左右各一，共 2 个。             |
| `selected_index() -> int`                                                                         | 当前选中的框下标；无选中为 -1。                                    |
| `select_box(index: int) -> None`                                                                  | 程序化选中第 index 个框（-1 = 取消选中）并重绘。                   |
| `box_kinds() -> list`                                                                             | 当前每个框的类型：`"left"` / `"right"` / `"full"`。                |
| `preview_edge() -> int`                                                                           | 当前控件需要多高的预览分辨率（**最长边**像素数）。                 |
| `set_boxes_editable(editable: bool) -> None`                                                      | 开关框编辑；开启时接受点击焦点以响应键盘删除。                     |
| `set_reference_boxes(boxes: list) -> None`                                                        | 设置参考框（橙色虚线，不参与编辑）并重绘。                         |
| `set_image(image, boxes=None, image_size: QSize \| None=None) -> None`                            | 装入图片并重置编辑状态。                                           |
| `set_boxes(boxes: list, image_size: QSize, full: bool=False, selected: int \| None=None) -> None` | 仅更新切割框、形态与图片原始尺寸并重绘（不换图）。                 |
| `clear_image(text: str='无预览') -> None`                                                         | 清空图片与全部框（含参考框），显示占位文案。                       |
| `resizeEvent(event) -> None`                                                                      | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。                       |
| `event(event) -> bool`                                                                            | 跨显示器拖动（dpr 变化）时按新 dpr 重画。                          |
| `mousePressEvent(event) -> None`                                                                  | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。                       |
| `mouseMoveEvent(event) -> None`                                                                   | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。                     |
| `mouseReleaseEvent(event) -> None`                                                                | Qt 事件覆写：松开（提交本次编辑）。                                |
| `mouseDoubleClickEvent(event) -> None`                                                            | 双击 → `double_clicked`（宿主打开图片预览弹窗）。                  |
| `contextMenuEvent(event) -> None`                                                                 | 右键大图 → `context_menu_requested`（宿主弹「查看 / 编辑」菜单）。 |
| `keyPressEvent(event) -> None`                                                                    | Qt 事件覆写：键盘操作（如 Delete 删除选中项）。                    |

##### `box_kinds() -> list`

当前每个框的类型：`"left"` / `"right"` / `"full"`。

与 :meth:`_draw_boxes` 用的是**同一份规则**（整幅页恒为 full；半幅页按
中心位置判左右），所以面板高亮与实际画出的标签永远一致。

##### `preview_edge() -> int`

当前控件需要多高的预览分辨率（**最长边**像素数）。

按控件的**物理**像素算（逻辑尺寸 × dpr），取宽高较大者：图片按等比
缩放适配控件，长边必定落在控件的长边上，所以按较大边给就够。

交给 `PreviewWorker(longest_edge=...)` 用。⚠️ 早先四处调用点都写死
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
`full=True` 表示本页是整幅(fullcontent)：框显示为「整幅」且**只允许
一个**；否则是半幅页，框按中心位置显示为左/右，最多两个。
`selected` 非负时把选中态落到该下标（宿主切换框类型后保持选中）。

⚠️ 名称/颜色不在这里传：它们由 `box_styles` 按**中心位置**每帧现算，
这样拖动框跨过中线时名字与颜色会立刻跟着换（用户 2026-09-29 要求）。

##### `event(event) -> bool`

跨显示器拖动（dpr 变化）时按新 dpr 重画。

Qt 在窗口 dpr 变化时发 `DevicePixelRatioChange`，**不保证**同时发
`resizeEvent`。不接这个事件的话，把窗口从 100% 屏拖到 200% 屏，
图会一直停在按旧 dpr 出的那版（明显发糊），要等下次换页才恢复。

##### `mouseDoubleClickEvent(event) -> None`

双击 → `double_clicked`（宿主打开图片预览弹窗）。

⚠️ 必须把本次按下可能已经开始的"手绘新框"清干净：双击的第一下会先落到
`mousePressEvent` 的"空白处 → 手绘"分支，不清就会在图上留一个跟着
鼠标跑的橡皮筋残影，而且第二下松开还会真的落一个框。

##### `contextMenuEvent(event) -> None`

右键大图 → `context_menu_requested`（宿主弹「查看 / 编辑」菜单）。

没有图时不弹（没有可查看/可编辑的东西），交给默认处理。框编辑用的是
左键（见 mousePressEvent），右键不参与，两者不打架。

### 模块函数

| 函数                                                          | 说明                                                               |
| ------------------------------------------------------------- | ------------------------------------------------------------------ |
| `box_styles(boxes, image_size=None, full: bool=False)`        | 框列表 → `(names, colors)`，与 `boxes`（去掉空项后）等长。         |
| `box_names(boxes, image_size=None, full: bool=False) -> list` | 框名称列表（大图信息条文案用）——与 :func:`box_styles` 同一份规则。 |

#### `box_styles(boxes, image_size=None, full: bool=False)`

框列表 → `(names, colors)`，与 `boxes`（去掉空项后）等长。

- `full=True`（整幅页 / fullcontent）：每个框都是「整幅」+ 靛蓝——
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

| 方法                                                                                                                                             | 说明                                                                  |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| `__init__(editable: bool=False, show_boxes: bool=False, empty_hint: str='暂无图片', image_size_provider=None, thumb_provider=None, parent=None)` | 构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。            |
| `paths() -> list[Path]`                                                                                                                          | 当前页面清单（按显示顺序）。                                          |
| `current_path() -> Path \| None`                                                                                                                 | 当前选中的页面路径；无选中或无清单时为 None。                         |
| `navigate(forward: bool) -> None`                                                                                                                | 方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。 |
| `set_images(paths: list[Path \| str], boxes_map: dict \| None=None) -> None`                                                                     | 设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。                |
| `set_thumb_source(paths: list[Path], cache_dir: Path, edge: int \| None=None) -> None`                                                           | 清单是真实图片，但左侧缩略图走 `cache_dir` 下的**缓存小图**。         |
| `set_pdf_source(pdf: Path \| str, cache_dir: Path \| None=None, gen: int=0) -> None`                                                             | 源是一本 **PDF**：左栏显示它的页缩略图，右侧大图按需渲高清页。        |
| `begin_pdf_pages(count: int, path: str='') -> None`                                                                                              | PDF 页数已known：按「第 N 页」建缩略图条目并选中第一页。              |
| `set_pdf_thumb(gen: int, index: int, image) -> None`                                                                                             | PDF 第 index 页的缩略图就绪：填进缩略图条第 index 条。                |
| `apply_boxes(boxes: list[tuple], image_size: QSize, info_text: str='', full: bool=False, selected: int=-1) -> None`                              | 在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。        |
| `set_reference_boxes(boxes: list) -> None`                                                                                                       | 设置参考框（最终裁剪大框，虚线显示，不参与编辑）。                    |
| `select_box(index: int) -> None`                                                                                                                 | 程序化选中第 index 个框（-1 = 取消选中）。                            |
| `selected_index() -> int`                                                                                                                        | 当前选中的框下标；无选中为 -1。                                       |
| `box_full_mode() -> bool`                                                                                                                        | 本页是否为整幅(fullcontent)。                                         |
| `box_kinds() -> list`                                                                                                                            | 当前每个框的类型（"left"/"right"/"full"）。                           |
| `apply_edited_image(path_text: str, image) -> None`                                                                                              | 编辑结果**立即上屏**（不等文件重解码/缩略图重生成）。                 |
| `refresh_page(path_text: str) -> None`                                                                                                           | 某页缩略图缓存重生成后刷新条目图标（大图由 apply_edited_image         |
| `reload_thumb(path_text: str) -> None`                                                                                                           | 某张图的**文件内容**被覆盖后：忘掉旧缓存记忆并按新文件重取缩略图。    |

##### `__init__(editable: bool=False, show_boxes: bool=False, empty_hint: str='暂无图片', image_size_provider=None, thumb_provider=None, parent=None)`

构建左侧缩略图条与右侧大图；editable 时追加删除/插入按钮。

image_size_provider 供大图降采样时还原原始像素尺寸；thumb_provider
让缩略图条改用预生成小图，避免反复解码原图。

##### `set_images(paths: list[Path | str], boxes_map: dict | None=None) -> None`

设置页面清单并重建缩略图条；清单未变则仅通知宿主重读。

`paths` 元素可以是 `Path` **或** `str`——统一在这里转成 `Path`
再往下传。⚠️ 这不是顺手为之：内部 `_select_image` 把元素直接交给
:class:`~desktop.workers.PreviewWorker`，而那个 worker 在 `run()` 里
要读 `self.path.suffix`；调用方传字符串的话，异常发生在**子线程
run() 内部**，只经 `failed` 信号回到预览区显示成
「加载失败：'str' object has no attribute 'suffix'」（用户 2026-10-03 报）。
在边界一次收干净，比让每个调用点各自记得 `str(p)`→`p` 可靠。

`boxes_map` 预留（当前未用）。清单不变时跳过重建，但仍 emit
current_changed 让宿主重新读取该页检测框/参数。

##### `set_thumb_source(paths: list[Path], cache_dir: Path, edge: int | None=None) -> None`

清单是真实图片，但左侧缩略图走 `cache_dir` 下的**缓存小图**。

用户 2026-10-03：所有独立任务左侧都显示缩略图，且统一缓存在
`~/Documents/guji/singletask`。清单本身**仍然是真实图片路径**——
右侧大图、检测框按 `Path(path).stem` 取键、放大弹窗的编辑回写，
全都指着真实文件；缓存只喂缩略图条。

实现方式是**替换缩略图来源**而不是替换清单：`_thumb_provider` 由
:meth:`set_thumb_source` 装上，:meth:`set_images` 的
`_load_thumbs` 会自动走它（它本来就支持 `thumb_provider`）。

##### `set_pdf_source(pdf: Path | str, cache_dir: Path | None=None, gen: int=0) -> None`

源是一本 **PDF**：左栏显示它的页缩略图，右侧大图按需渲高清页。

这是「图片提取」页未提取时的形态（用户 2026-10-03：「在未提取图片之前
是按照缩略图，单独图片显示」）——选完 PDF 就能翻页看，不必先跑一遍提取。

⚠️ 缩略图条显示的是 256px 缓存小图，但**右侧大图不是拿小图放大**：
点哪页就按需从 PDF 渲那一页（`_select_image` 见 `_page_source`），
所以放大事先看得清。缩略图由宿主用
:class:`~desktop.modules.thumb_source.ThumbSourceMixin` 起 pass 填充，
本方法只负责建条目（:meth:`begin_pdf_pages`）。

`gen` 是代际号：换书时宿主递增，本控件据此丢弃旧书迟到的缩略图信号。

##### `begin_pdf_pages(count: int, path: str='') -> None`

PDF 页数已known：按「第 N 页」建缩略图条目并选中第一页。

⚠️ 与 `PdfViewerWidget._metadata_ready` 同一道护栏：后续轮次
（回扫/补缺页）页数没变时**不能清空重建**——那会把已经加载好的图标
全丢掉，只剩占位符。

##### `set_pdf_thumb(gen: int, index: int, image) -> None`

PDF 第 index 页的缩略图就绪：填进缩略图条第 index 条。

`gen` 与 :meth:`set_pdf_source` 传的一致才算数——旧书那个还在跑的
worker 迟到时会被丢弃，否则**旧书的页会画进新书的缩略图条**。

##### `apply_boxes(boxes: list[tuple], image_size: QSize, info_text: str='', full: bool=False, selected: int=-1) -> None`

在当前大图上叠加切割框（图片像素坐标）；大图未就绪时挂起等待。

`full=True` 表示本页是整幅(fullcontent)：框显示为「整幅」且只允许一个；
否则按框的**中心位置**显示为左/右框。名称/颜色由控件每帧现算，不用传。
`selected` 为要选中的框下标（-1 = 不选），用于切换类型后保持选中。

##### `apply_edited_image(path_text: str, image) -> None`

编辑结果**立即上屏**（不等文件重解码/缩略图重生成）。

编辑弹窗确认后由宿主调用：当前页大图直接换成编辑结果，条目图标
用编辑结果现缩一张，缩略图缓存随后由宿主后台重生兜底。清单里没有
这个路径（或图无效）时是空操作。

##### `refresh_page(path_text: str) -> None`

某页缩略图缓存重生成后刷新条目图标（大图由 apply_edited_image
即时同步过，不再重载）。路径不在清单里时是空操作。

##### `reload_thumb(path_text: str) -> None`

某张图的**文件内容**被覆盖后：忘掉旧缓存记忆并按新文件重取缩略图。

⚠️ 必须真的"忘掉"（:attr:`_thumb_cache_ready` 里那条）：缓存文件名带
**大小**（`book_key` 含 size），编辑器改了像素尺寸就换了文件名，
而记忆里那条旧路径仍指向**覆盖前**的缓存文件——只刷不丢会一直显示
编辑前的样子（用户报「独立步骤里编辑不生效」就是这么来的）。

---

## `desktop.components.viewers.image_zoom_dialog`

源码：[`desktop/components/viewers/image_zoom_dialog.py`](../../desktop/components/viewers/image_zoom_dialog.py)

图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。

为什么不把缩放直接做在 `ImageView` 上：那是**框编辑**画布——点击选中、
拖拽移动整框、四角缩放、空白拖拽手绘。再叠一层"滚轮缩放 + 拖拽平移"，
两种拖拽立刻打架（拖框 vs 拖画布），而框坐标是 detect/rembg 的实际输出依据，
误操作代价高。所以编辑仍留在原处（固定"适应窗口"），弹窗只做**只读**查看。

渲染密度由弹窗自己算（`_render_edge`：视口物理长边 × `RENDER_HEADROOM`，
再受宿主给的 `ZoomTarget.cap` 与 :data:`MAX_RENDER_EDGE` 约束），宿主只提供
`render(edge) -> worker`。这样「图片按最长边解码」「PDF 按该边长渲染」
「打印效果按该边长反推 px/mm 重新排版」三种口径各归各家，弹窗不必区分。

⚠️ 缩放倍率的语义：**1.0 = 100% = 1 图片像素对 1 设备像素**（QGraphicsView 的
变换比例 = 倍率 ÷ dpr）。所以场景里的 pixmap 刻意**不设** devicePixelRatio
（1 场景单位 = 1 图片像素），否则这套换算会再叠一个 dpr。

### 模块常量

| 名称                   | 值     |
| ---------------------- | ------ |
| WHEEL_STEP             | `1.15` |
| RENDER_HEADROOM        | `1.5`  |
| MIN_RENDER_EDGE        | `1600` |
| MAX_RENDER_EDGE        | `4000` |
| JPEG_QUALITY           | `90`   |
| PAN_MARGIN_RATIO       | `0.25` |
| OVERWRITE_JPEG_QUALITY | `95`   |

### `class ZoomTarget`

弹窗某一页的数据来源（宿主在**主线程**里按页现造）。

`render` 会在 **worker 线程**被调用，所以它只能读构造时快照下来的值
（路径、参数字典……），**不得**碰任何 QWidget——同 `worker_thread_affinity`
的约束。

#### 方法

| 方法                                                                                                                               | 说明                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `__init__(render, note: str='', stem: str='', count: int=1, original=None, cap: int \| None=None, save_path=None, edit_path=None)` | render: `(edge:int) -> worker`；cap: 渲染密度上限（如原图原生边长）。 |

##### `__init__(render, note: str='', stem: str='', count: int=1, original=None, cap: int | None=None, save_path=None, edit_path=None)`

render: `(edge:int) -> worker`；cap: 渲染密度上限（如原图原生边长）。

`save_path`：本页显示的像素**就是**这个真实文件（Path | None）。
给了它，编辑器「完成」后把编辑结果覆盖回该文件（编辑器加载的也是
该文件的全分辨率原图，预览的降采样不掺和）；**只允许在"画布显示的
内容 1:1 就是这个文件"时给**——区域合成（effect）、打印重排、PDF
矢量页都是虚拟图，写回会把整张文件覆盖成一块裁剪区域，绝不能开。

`edit_path`：本页**编辑时要写回的真实文件**（Path | None），
可以不同于 `save_path`——区域合成/打印效果这类派生显示，
显示的不是某个文件的全部像素，但它**派生自**一个真实文件；编辑
要改的是那个文件（各步骤改动因此串成一条链，最终落到 PDF）。
不传时回落 `save_path`（1:1 显示的情形）。两者都为 None 表示
没有可回写的文件（PDF 矢量页等），右键菜单不提供「编辑图片」。

### `class ZoomableCanvas(QGraphicsView)`

缩放画布：滚轮以光标为锚点缩放、左键拖拽平移、双击切换适应/100%。

#### 方法

| 方法                                                              | 说明                                                                |
| ----------------------------------------------------------------- | ------------------------------------------------------------------- |
| `__init__(parent=None)`                                           | 初始化场景、拖拽平移与锚点缩放（锚点由 QGraphicsView 原生支持）。   |
| `has_image() -> bool`                                             | 当前是否已装入图片。                                                |
| `zoom() -> float`                                                 | 当前缩放倍率（1.0 = 100% = 1 图片像素对 1 设备像素）。              |
| `set_image(image: QImage \| None) -> None`                        | 装入图片并复位（适应窗口、清空翻转旋转）。                          |
| `clear() -> None`                                                 | 卸载图片（关窗时释放大图内存）。                                    |
| `fit() -> None`                                                   | 适应窗口：整图完整可见（保持宽高比）。                              |
| `set_zoom(zoom: float, anchor_pos: QPointF \| None=None) -> None` | 设置缩放倍率。                                                      |
| `zoom_in() -> None`                                               | 放大到下一档。                                                      |
| `zoom_out() -> None`                                              | 缩小到上一档。                                                      |
| `image_rect() -> QRectF`                                          | 图片在**场景坐标**里的实际占位（1 场景单位 = 1 图片像素）。         |
| `rotate_clockwise() -> None`                                      | 顺时针旋转 90°。                                                    |
| `rotate_counterclockwise() -> None`                               | 逆时针旋转 90°。                                                    |
| `flip_horizontal() -> None`                                       | 水平翻转（左右镜像）。                                              |
| `flip_vertical() -> None`                                         | 垂直翻转（上下镜像）。                                              |
| `keyPressEvent(event) -> None`                                    | ←/→ 翻页（工具条 tooltip 承诺过的快捷键，此前一直没实现）。         |
| `wheelEvent(event) -> None`                                       | 滚轮缩放：以**光标下的那一点**为锚点（自己算，见 set_zoom）。       |
| `mouseDoubleClickEvent(event) -> None`                            | 双击在「100%」与「适应窗口」之间切换。                              |
| `resizeEvent(event) -> None`                                      | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。                        |
| `orientation() -> QTransform`                                     | 当前翻转/旋转矩阵（恒等 = 没动过朝向）。                            |
| `export_image() -> QImage \| None`                                | 导出用图：已应用翻转/旋转的**整分辨率**图（缩放的屏幕比例不参与）。 |

##### `set_zoom(zoom: float, anchor_pos: QPointF | None=None) -> None`

设置缩放倍率。

`anchor_pos` 是**视口坐标**下的不动点（滚轮传光标位置）；不传则以
视口中心为不动点。

⚠️ 刻意**不用** Qt 的 `AnchorUnderMouse`：它依赖私有的
`lastMouseEventPosition`，弹窗刚打开就滚轮时那个值可能是陈旧的
（实测会退化成左上角），缩放会突然跳到一边。这里自己按"锚点处的场景
点在缩放前后保持不动"来算，结果只取决于传入的位置，既可预期也可测。

##### `image_rect() -> QRectF`

图片在**场景坐标**里的实际占位（1 场景单位 = 1 图片像素）。

⚠️ 与 `sceneRect()` 区分：场景矩形为了"没缩放也能拖"会被**居中扩展**
到至少视口那么大（见 :meth:`_sync_scene_rect`），所以几何/朝向判断一律
用本方法，只有滚动范围与 fitInView 的留白才看 `sceneRect()`。

##### `keyPressEvent(event) -> None`

←/→ 翻页（工具条 tooltip 承诺过的快捷键，此前一直没实现）。

⚠️ 主动 ignore 掉：QGraphicsView 默认用方向键**滚动视图**，焦点落在
画布上时事件到不了对话框，翻页就死了；这里显式放行给父级。

##### `orientation() -> QTransform`

当前翻转/旋转矩阵（恒等 = 没动过朝向）。

编辑器回写原图时用它把朝向"烤"进全分辨率原图——见
`ImageZoomDialog._edit_image`。

### `class ImageZoomDialog(QDialog, WorkerHost)`

图片预览弹窗：拖拽平移、滚轮/按钮缩放、翻转旋转、下载、翻页。

#### 方法

| 方法                                                                 | 说明                                                                    |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `__init__(parent=None, factory=None, max_edge: int=MAX_RENDER_EDGE)` | `factory(index) -> ZoomTarget \| None`，在**主线程**里现造该页来源。    |
| `show_for(factory=None, index: int=0) -> None`                       | 打开/翻到某一页。`factory(index) -> ZoomTarget \| None`（主线程现造）。 |
| `mouseDoubleClickEvent(event) -> None`                               | 双击**顶部工具栏**空白 → 全屏/还原。                                    |
| `eventFilter(obj, event) -> bool`                                    | 点「百分比」标签 → 回 100%（标签兼做缩放复位的入口）。                  |
| `keyPressEvent(event) -> None`                                       | 快捷键：←/→ 翻页、+/- 缩放、0 适应窗口、1 原始比例、R 旋转。            |
| `closeEvent(event) -> None`                                          | 关窗即作废在飞的渲染并释放大图（一张 4000px 预览约 45MB）。             |

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

宿主侧混入：双击/右键大图打开图片预览弹窗与「预览 / 编辑」菜单。

子类需要实现 :meth:`_zoom_target` 与 :meth:`_zoom_index`，并在
`__init__` 里调 :meth:`_init_zoom_popup`。

#### 方法

| 方法                           | 说明                                                               |
| ------------------------------ | ------------------------------------------------------------------ |
| `close_zoom_popup() -> None`   | 内容被换掉时关掉弹窗（弹窗里那页是打开时的快照，留着就是旧数据）。 |
| `edit_current_image() -> bool` | 右键「编辑图片」：直接编辑当前显示图对应的**真实文件**并覆盖回写。 |

##### `edit_current_image() -> bool`

右键「编辑图片」：直接编辑当前显示图对应的**真实文件**并覆盖回写。

用户原则（2026-10-01）：图片编辑不是"本步骤看看"，各步骤改动要串成
一条链、最终落到 PDF。目标由 `ZoomTarget.edit_path` 决定——

- 显示的是**处理前**的图（如第三步「原图」）→ 改该源图文件；
- 显示的是**处理后**的图（如第三步「去底色结果」、第四步待打印图）
  → 改该结果文件（本步产出，下一步读的就是它）。

编辑器「完成」后：原子覆盖该文件 → `_on_zoom_image_saved` 通知宿主
刷新（尺寸 / 缩略图 / 各处大图）。返回是否真的写回了文件。

### 模块函数

| 函数                                                                                             | 说明                                                                |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------- |
| `display_transform(rotation: int=0, flip_h: bool=False, flip_v: bool=False) -> QTransform`       | 翻转/旋转的变换矩阵——**屏幕与导出必须共用这一个**。                 |
| `mirrored_rotate_icon() -> QIcon`                                                                | `FIF.ROTATE` 的水平镜像 = **逆时针（左旋）**。                      |
| `flip_icon(horizontal: bool=True, color: QColor \| None=None) -> QIcon`                          | 翻转按钮的图标（水平/垂直 = 同一个图形转 90°）。                    |
| `save_image(image: QImage, path: str \| Path, quality: int=JPEG_QUALITY) -> bool`                | 把 QImage 写到磁盘：`.jpg`/`.jpeg` 走有损（quality），其余交给 Qt。 |
| `overwrite_image_file(image: QImage, target: Path, quality: int=OVERWRITE_JPEG_QUALITY) -> bool` | 把 `image` **原子**覆盖到 `target`（格式按目标后缀）。              |

#### `display_transform(rotation: int=0, flip_h: bool=False, flip_v: bool=False) -> QTransform`

翻转/旋转的变换矩阵——**屏幕与导出必须共用这一个**。

⚠️ 屏幕侧走 `QGraphicsPixmapItem.setTransform`、导出侧走
`QImage.transformed`。两处若各写一份，改一处就会出现「看到的和下载的
不一样」（翻转轴或旋转方向不一致）。

#### `mirrored_rotate_icon() -> QIcon`

`FIF.ROTATE` 的水平镜像 = **逆时针（左旋）**。

qfluentwidgets 只提供一个旋转图标：ROTATE 的箭头在弧线底部**指向左**，
即顺时针（右旋）。左旋用它的镜像，两颗按钮的笔触天然一致、只差方向。

多档位 pixmap 是为了高分屏下不掉清晰度（图标源是 SVG，按需渲染）。

#### `flip_icon(horizontal: bool=True, color: QColor | None=None) -> QIcon`

翻转按钮的图标（水平/垂直 = 同一个图形转 90°）。

qfluentwidgets 没有可用的翻转图标：`SEARCH_MIRROR` 是"带镜子的放大镜"，
语义不对；`SYNC` 是循环箭头。自绘还有个好处——一对图标笔触完全一致，
且按需渲染，任意 dpr 下都锐利。

#### `save_image(image: QImage, path: str | Path, quality: int=JPEG_QUALITY) -> bool`

把 QImage 写到磁盘：`.jpg`/`.jpeg` 走有损（quality），其余交给 Qt。

单独抽出来是为了可测——保存对话框在离屏环境里弹不出来。

#### `overwrite_image_file(image: QImage, target: Path, quality: int=OVERWRITE_JPEG_QUALITY) -> bool`

把 `image` **原子**覆盖到 `target`（格式按目标后缀）。

⚠️ 必须走「临时文件 + os.replace」，不能就地写：任务目录里的页面图
可能是硬链接（workset 时代的遗产），就地写会把链接另一头的源文件一起
改掉；且覆盖途中被 200ms 一次的 extract 轮询/预览读到半截也是事故。
`os.replace` 换的是目录项——读者要么看到完整旧图、要么看到完整新图，
旧 inode 原样留在硬链接另一头。

---

## `desktop.components.viewers.pdf_viewer`

源码：[`desktop/components/viewers/pdf_viewer.py`](../../desktop/components/viewers/pdf_viewer.py)

PDF 查看器：左侧页面缩略图 + 右侧大图。

### `class PdfViewerWidget(QWidget, WorkerHost, ZoomPopupMixin)`

PDF 查看器：左侧页面缩略图 + 右侧大图。

#### 方法

| 方法                                                                                               | 说明                                                                    |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `__init__(placeholder: str='暂无 PDF', parent=None)`                                               | 初始化 PDF 查看器：左侧页缩略图条 + 右侧大图。                          |
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

坐标体系与 `utils.page_layout.plan_print_page` 算出的 `plan.image` 完全一致
——**页面毫米，左上原点，x 向右、y 向下**。控件把页面等比缩放到可视区，
用 `px_per_mm` 在「页面 mm」与「控件像素」之间换算；用户拖拽/缩放得到的
`[x_mm, y_mm, w_mm, h_mm]` 直接写回 `print.json` 的 `pages[].rect`，
生成 PDF 时由 `plan_print_page(image_rect=...)` 原样采用——所见即所得。

交互（与 detect/rembg 的裁剪框编辑同款手感）：

- 框内拖动 → 整体移动；**四角**手柄拖动 → 缩放（勾「原比例缩放」时等比）；
  **四条边整条都是命中带**（不限边中点的小圆点）→ 拖上/下边只改高度、
  拖左/右边只改宽度（自由拉伸改变比例）；松手 emit `rect_changed`；
- 框始终被夹在页面内（夹到纸边即停），不会拖出页面；
- 悬停手柄/边/框时显示对应光标。

**标题与页码照画**：它们是「版面」的一部分，去掉就无从判断图片挪动后会不会
压到字（曾误判为「标题页码被去除」）。绘制复用 `preview_worker` 的
`_draw_print_text`——与成品 PDF 同源，只是多了画布自身的居中偏移。
标题/页码的落点只取决于 `page_margins`，**不随图片框移动**，与 PDF 一致。

图片在框内按目标矩形**拉伸**绘制，与成品 `pdf.image(img, x, y, w, h)` 的
拉伸规则一致（PDF 用 w/h 直接定最终尺寸，不保比例）。

### 模块常量

| 名称          | 值    |
| ------------- | ----- |
| HANDLE_RADIUS | `6`   |
| MIN_RECT_MM   | `2.0` |
| EDGE_HIT_PX   | `6`   |

### `class PrintLayoutCanvas(QWidget)`

A4 纸上的图片拖拽/缩放画布；rect_changed 发出页面 mm 坐标。

#### 方法

| 方法                                                                                                                                      | 说明                                                                   |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `__init__(parent=None)`                                                                                                                   | —                                                                      |
| `set_page(page_w_mm: float, page_h_mm: float, image: QImage \| None, rect_mm: Sequence[float], plan=None, keep_ratio: bool=True) -> None` | 设置页面尺寸、待绘制图片与初始图片框（页面 mm）。                      |
| `current_rect() -> list[float]`                                                                                                           | 当前图片框（页面 mm），供宿主落盘前读取。                              |
| `resizeEvent(event) -> None`                                                                                                              | Qt 事件覆写：尺寸变化时重算布局 / 重新缩放。                           |
| `showEvent(event) -> None`                                                                                                                | 显示时重算：首次进入第四步可能在布局完成前就 `set_page` 过，           |
| `mousePressEvent(event) -> None`                                                                                                          | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。                           |
| `mouseMoveEvent(event) -> None`                                                                                                           | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。                         |
| `mouseDoubleClickEvent(event) -> None`                                                                                                    | 双击 → `double_clicked`（宿主打开预览弹窗）。                          |
| `contextMenuEvent(event) -> None`                                                                                                         | 右键 → `context_menu_requested`（宿主弹「预览图片 / 编辑图片」菜单）。 |
| `flush_pending() -> bool`                                                                                                                 | 把"还没松手"的拖动结果补发出去（关窗口/切步骤/切页时调）。             |
| `mouseReleaseEvent(event) -> None`                                                                                                        | Qt 事件覆写：松开（提交本次编辑）。                                    |
| `paintEvent(event) -> None`                                                                                                               | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。                    |

##### `set_page(page_w_mm: float, page_h_mm: float, image: QImage | None, rect_mm: Sequence[float], plan=None, keep_ratio: bool=True) -> None`

设置页面尺寸、待绘制图片与初始图片框（页面 mm）。

`plan` 为 `utils.page_layout.PrintPagePlan`：本控件据它画标题/
页码与「已跳过」提示——版面编辑不能只看图片，否则无从判断挪动后
会不会压到字。传 None 表示纯图片编辑（无标题/页码）。

`keep_ratio`（print 参数 `keep_ratio`）：True（默认）= 四角拖拽
**保持宽高比**、不提供四边手柄；False = 四角自由拉伸 + 上/下/左/右
四个边手柄可单独拉伸（与「铺满可用区域」的自动排版语义配套）。

##### `showEvent(event) -> None`

显示时重算：首次进入第四步可能在布局完成前就 `set_page` 过，
那时 `width()/height()` 还是 0，`_px_per_mm` 会退化为 1.0。
仅靠 resizeEvent 兜不住「已分配尺寸但从未显示」的情况。

##### `contextMenuEvent(event) -> None`

右键 → `context_menu_requested`（宿主弹「预览图片 / 编辑图片」菜单）。

左键的拖拽/缩放不受影响（右键不参与编辑手势）；空页不弹菜单。

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

布局与前三步保持一致（`ImageViewerWidget` / `RembgPreviewWidget` 的
「左缩略图 + 右大图」），右侧不再是网格瀑布流：

- **打印效果**：按右侧表单参数（纸张/方向/边距/标题/页码）把图片排进一
  张纸里给用户在屏幕上看到——**只是效果，不执行、不提交、不生成 PDF**；
- **原图**：待打印图片本身（第三步「提交本次任务」的最终图）。

几何全部来自 `utils.page_layout.plan_print_page`，而真正生成 PDF 的
`functions/print.py` 用的是同一个函数，所以预览与成品不会漂移。

缩略图默认用条目图片本身（`ImageListWorker` 走 QImageReader 缩放解码，
等于现算缩略图）；传入 `thumb_provider` 时改用它给出的预生成小图。

### `class PrintPreviewWidget(QWidget, ThumbsMixin, ZoomPopupMixin)`

生成 PDF 预览：左侧待打印缩略图条（可拖动排序）+ 右侧单页效果。

#### 方法

| 方法                                                                                                           | 说明                                                                  |
| -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `__init__(empty_hint: str='暂无图片，请先完成去底色', params_provider=None, thumb_provider=None, parent=None)` | 构建工具栏 + 左缩略图条 + 右效果预览。                                |
| `set_entries(entries: list[dict]) -> None`                                                                     | 重建列表：entries = [{file, label}]，可按条目自带 thumb 指定小图。    |
| `entries() -> list[dict]`                                                                                      | 当前视觉顺序的富条目列表。                                            |
| `count() -> int`                                                                                               | 列表当前条目数。                                                      |
| `set_pdf_path(path: str \| Path \| None) -> None`                                                              | 设置已生成 PDF 的路径；存在则启用下载按钮，否则禁用。                 |
| `remove_selected() -> None`                                                                                    | 删除所有选中条目，未选中则通过 hint 信号提示。                        |
| `refresh_display() -> None`                                                                                    | 右侧参数变化后按最新参数重画当前页（不生成任何文件）。                |
| `navigate(forward: bool) -> None`                                                                              | 方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。 |
| `refresh_layout() -> None`                                                                                     | 参数（纸张/方向）变化后刷新画布：保留已存坐标，仅重算页面尺寸。       |
| `export_default_name() -> str \| None`                                                                         | 导出对话框的默认文件名；没有可导出的页时返回 None。                   |
| `export_current_effect(target: str \| Path) -> None`                                                           | 把**当前页**排进纸面后的 A4 效果图按 300dpi 写到 `target`。           |

##### `__init__(empty_hint: str='暂无图片，请先完成去底色', params_provider=None, thumb_provider=None, parent=None)`

构建工具栏 + 左缩略图条 + 右效果预览。

params_provider: () -> print 参数字典；非法时抛异常（由本控件捕获
并退回「原图」显示）。为 None 时关闭「打印效果」项。
thumb_provider: (path_text) -> Path | dict | None，可选的小图来源。

##### `export_current_effect(target: str | Path) -> None`

把**当前页**排进纸面后的 A4 效果图按 300dpi 写到 `target`。

单页、不生成 PDF。走 worker 合成（与预览同一条 `compose_print_page`
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

| 方法                                                                                                                                           | 说明                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `__init__(empty_hint: str='暂无图片', parent=None)`                                                                                            | 构建缩略图条与「去底色结果 / 原图」切换行，默认显示去底色结果。       |
| `set_images(paths: list[Path \| str], rembg_dir: Path \| None, boxes_provider=None, region_params_provider=None, thumb_provider=None) -> None` | 设置图片清单与去底色目录，重建输出条目并加载显示。                    |
| `refresh_display() -> None`                                                                                                                    | detect 框/area/border 变化后，重建输出条目并按新区域重新加载。        |
| `navigate(forward: bool) -> None`                                                                                                              | 方向键翻页（详情页 ←/→ 调用；联动预览刷新，见 ThumbStrip.navigate）。 |
| `set_live_dir(path: Path \| None) -> None`                                                                                                     | 设置（或传 None 清除）「实时预览」暂存目录。                          |
| `live_dir() -> Path \| None`                                                                                                                   | 当前生效的实时预览暂存目录（未启用为 None）。                         |
| `current_entry_path() -> str \| None`                                                                                                          | 当前选中条目的源图路径（无条目时为 None）。                           |
| `show_live_pending() -> None`                                                                                                                  | 实时预览正在计算：先给个即时反馈，别让界面看起来没反应。              |
| `refresh_page(path_text: str) -> None`                                                                                                         | 某文件被覆盖后刷新本查看器：受影响条目图标 + 当前大图。               |
| `set_cached_thumbs(mapping: dict[str, str]) -> None`                                                                                           | 告诉本控件哪些图已有缓存小图（`真实图路径 → 缓存路径`）。             |
| `set_cached_thumb(path_text: str, cache: str) -> None`                                                                                         | **单张**：记下它的缓存小图并只刷相关条目 + 当前大图。                 |
| `reload_thumb(path_text: str) -> None`                                                                                                         | 某张图的**文件内容**被覆盖后：丢掉它的缓存映射并按新文件重取。        |

##### `set_images(paths: list[Path | str], rembg_dir: Path | None, boxes_provider=None, region_params_provider=None, thumb_provider=None) -> None`

设置图片清单与去底色目录，重建输出条目并加载显示。

`paths` 为源图，元素允许是 `str`（统一转 `Path`，同
:meth:`desktop.components.viewers.ImageViewerWidget.set_images`）；
`rembg_dir` 为去底色结果目录（存在才显示结果）；
各 provider 给出检测框 / 区域参数 / 缩略图来源。清单变化时重建
缩略图条，否则按最新区域重加载当前显示。

##### `set_live_dir(path: Path | None) -> None`

设置（或传 None 清除）「实时预览」暂存目录。

非 None 时结果图优先从这里取：它是按**此刻**面板参数现算的当前页；
而 `_rembg_dir`（stages/rembgpreview）是上一次「生成预览」的全量产物，
参数可能已经改过。

##### `refresh_page(path_text: str) -> None`

某文件被覆盖后刷新本查看器：受影响条目图标 + 当前大图。

由宿主在缩略图重生成完毕后调用；路径与本查看器无关时是空操作。

##### `set_cached_thumbs(mapping: dict[str, str]) -> None`

告诉本控件哪些图已有缓存小图（`真实图路径 → 缓存路径`）。

用户 2026-10-03：所有独立任务左栏都显示缩略图，且统一缓存在
`~/Documents/guji/singletask`。这里**只换缩略图来源**、不动条目与
大图——所以宿主渲好一张就能立刻刷那一条（`refresh_page`），
不必重建整个缩略图条。

⚠️ 缓存里存的是**整页**小图；条目若按检测框裁了一块/合成区域
（area=1 的 `-l`/`-r`），仍由 :meth:`_load_page_thumbs` 走区域合成
——只是输入图从「原图」换成「已缩好的整页小图」，省掉整张解码。

⚠️ 语义是**整体替换**（调用点给的就是完整的映射）。只更新一条请用
:meth:`set_cached_thumb`。

##### `set_cached_thumb(path_text: str, cache: str) -> None`

**单张**：记下它的缓存小图并只刷相关条目 + 当前大图。

与 :meth:`set_cached_thumbs` 的差别是**合并一条**而不是整体替换——
宿主在"某张图被编辑后重渲缩略图"这条路上只关心这一条，整体替换会
把其余条目的缓存映射一起丢掉（它们随后只能回落去解码原图）。

##### `reload_thumb(path_text: str) -> None`

某张图的**文件内容**被覆盖后：丢掉它的缓存映射并按新文件重取。

⚠️ 与 :meth:`desktop.components.viewers.ImageViewerWidget.reload_thumb`
同一个理由：缓存文件名带**大小**，编辑改了像素尺寸就换了文件名，
留着旧映射会一直显示覆盖前的缩略图。

---

## `desktop.components.viewers.thumb_strip`

源码：[`desktop/components/viewers/thumb_strip.py`](../../desktop/components/viewers/thumb_strip.py)

垂直缩略图条控件。

### `class ThumbStrip(QListWidget)`

垂直缩略图条：图标在上、标签在下，加载完成前显示占位图。

默认**不可拖动**（前三步的页面顺序由数据层决定）；第四步的待打印
列表调 `set_reorderable(True)` 打开内部拖放排序，顺序变化发
`order_changed`。

⚠️ 条目尺寸只有一个事实来源（本类的 `ICON_SIZE` / `GRID_SIZE` /
`STRIP_WIDTH` / `DECODE_EDGE`）：调用方解码缩略图时必须用
`DECODE_EDGE` 当"最长边"，不要写字面量 96——竖开本页面受**高度**
约束，解码边取小了缩略图就只剩条目宽度的一半（缩略图看起来"没占满"）。

#### 方法

| 方法                                                              | 说明                                                                        |
| ----------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `decode_edge(dpr: float=1.0, base: int \| None=None) -> int`      | 按 dpr 给出的缩略图**解码最长边**（调用方在**主线程**算好后传进 worker）。  |
| `__init__(parent=None)`                                           | 初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。 |
| `wheelEvent(event) -> None`                                       | 滚轮按**条目**翻页：一格滚轮 = `WHEEL_STEP_ITEMS` 个条目。                  |
| `set_reorderable(on: bool) -> None`                               | 打开/关闭条目内部拖放排序（第四步待打印列表用）。                           |
| `set_deletable(on: bool) -> None`                                 | 打开/关闭 Delete/Backspace 删除（只发信号，删不删由宿主定）。               |
| `navigate(forward: bool) -> None`                                 | 方向键翻页：移动当前行（夹在两端，不回绕）。                                |
| `keyPressEvent(event) -> None`                                    | Delete/Backspace → `delete_requested`。                                     |
| `add_placeholder(text: str) -> None`                              | 追加一个纯文字占位条目（无图标，如"缩略图加载中…"）。                       |
| `add_page_item(label: str, path: str='') -> None`                 | 新增一个带占位图的条目，缩略图就绪后由 set_item_icon 替换。                 |
| `set_item_icon(index: int, image, path: str, label: str) -> None` | 替换某条目的图标/文字/路径（缩略图异步就绪后回调）。                        |

##### `decode_edge(dpr: float=1.0, base: int | None=None) -> int`

装饰器：`staticmethod`

按 dpr 给出的缩略图**解码最长边**（调用方在**主线程**算好后传进 worker）。

`base` 是逻辑像素下的基准边，默认取 `DECODE_EDGE`（= 图标框长边）。

⚠️ 高分屏下条目本身是按 dpr 放大绘制的，只解码到逻辑尺寸就等于让 Qt
再放大一次 → 缩略图发糊。这与右侧大图 `ImageView.preview_edge` 是
同源问题（那边实测 150% 缩放下锐度差 7.6 倍）。

##### `__init__(parent=None)`

初始化条目尺寸与流式布局；当前行变化发出 current_path_changed(行号, 路径)。

⚠️ 必须监听 `currentRowChanged` 而不是只接 `itemClicked`：
键盘翻页（方向键 / PageUp / PageDown）与程序化 `setCurrentRow`
只会改 currentRow、**不产生点击**，只接 itemClicked 就会出现
「翻页了但右侧预览不更新，切到别的视图模式再切回来才正常」。

##### `wheelEvent(event) -> None`

滚轮按**条目**翻页：一格滚轮 = `WHEEL_STEP_ITEMS` 个条目。

刻意不调 `super()`：Qt 那条路径按 singleStep / 系统"滚动行数"算步长
（见 WHEEL_STEP_ITEMS 的说明），会把一格变成十几页。这里自己算目标行号
并把该行落到顶端，翻页量恒定。

##### `navigate(forward: bool) -> None`

方向键翻页：移动当前行（夹在两端，不回绕）。

主预览的方向键导航入口——「焦点在哪里，哪里就切换」：焦点在主界面
的非输入控件上时由详情页转到这里（四个步骤的预览组件共用本方法）；
焦点落在本条上时 QListWidget 的方向键本来就移动选择，语义一致。
`setCurrentRow` 会触发 `currentRowChanged`，预览刷新由各组件
既有的联动完成。

##### `keyPressEvent(event) -> None`

Delete/Backspace → `delete_requested`。

⚠️ 第四步工具条的提示写着「Delete 删除选中」，原先没有任何地方接这个
键——提示是空头支票，按下去毫无反应。这里只负责把键翻成信号，
「删哪些、要不要落盘」仍归宿主（`PrintPreviewWidget.remove_selected`）。

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

| 方法                         | 说明                                               |
| ---------------------------- | -------------------------------------------------- |
| `shutdown_workers() -> None` | 停掉分批定时器与未完成的批次，再走基类的线程收尾。 |

---

## `desktop.modules`

源码：[`desktop/modules/__init__.py`](../../desktop/modules/__init__.py)

独立功能模块包：**左侧导航**里的每个条目对应一个模块。

设计目标（用户 2026-10-02 要求）：
「使用 qfluentwidget 组件，左侧开发「图片提取 / 去底色 / 拼图」等模块功能，
这些功能**独立**，但是**复用先有功能**。」

两个关键词决定了这一层的形状：

- **独立**：每个模块是一个自包含的 `QWidget` 页面，只依赖
  `desktop.components.*` / `desktop.services.*` / `functions.*` 这些
  **共享底座**；模块之间**零 import 依赖**，也不依赖 `TaskDetailPage`
  （那条「任务 → 四步」的重编排流程）。删掉一个模块只需从 :data:`MODULES`
  里去掉一行，其余代码一行都不用动。
- **复用**：模块页面**不重新发明控件**——参数表单直接用现成的
  `ExtractPanel` / `RembgPanel`，拼版用现成的 `ImpositionViewWidget` +
  `ImpositionPanel`，执行直接调 `functions.get_function()`。新增模块的
  成本因此只有「选文件 + 放控件 + 起线程」这一层胶水。

壳层（`desktop/modules/shell.py`）只从本模块拿**元数据**（key/标题/图标/
工厂），从不 import 具体页面——工厂是惰性的，只有用户真正点进某个模块时
才触发那个页面的 import。这与 `desktop.pages` 的 PEP 562 惰性导出同一套路：
启动时不该为「用户可能不点」的模块付构造/导入开销。

### `class Module`

左侧导航的一个模块条目（纯元数据，不含任何控件/导入）。

- `key`：唯一路由键，同时用作 `QStackedWidget` 的寻址依据；
- `title`：导航栏文案；
- `icon`：`nav_icon` 字符串（`FluentIcon` 成员名或 `svg:名字` 自绘图），
  壳层经 `desktop.ui.icons.resolve_nav_icon` 解析成图标对象
  （延迟到壳层再取，避免这里 import 重物）；
- `subtitle`：页头副标题；
- `factory`：`() -> QWidget`，**首次进入该模块时才调用**。

### 模块函数

| 函数                                        | 说明                                                              |
| ------------------------------------------- | ----------------------------------------------------------------- |
| `module_by_key(key: str) -> Module \| None` | 按路由键取模块元数据；不存在返回 None（调用方自己决定怎么提示）。 |

---

## `desktop.modules.base`

源码：[`desktop/modules/base.py`](../../desktop/modules/base.py)

独立模块页面的**基类**：把「页头 + 左预览 + 右控制 + 日志」这套骨架收在一处。

为什么需要它（而不是每个模块各写一遍 QVBoxLayout）：

- 三个模块（图片提取 / 去底色 / 拼图）的**外壳**长得一样——都是「选文件 →
  调参数 → 出结果」。骨架统一后，模块页只剩「参数面板是谁、执行怎么跑」两件事，
  新增模块的成本降到几十行；
- 骨架统一也保证了**左导航切换时页面不跳变**：三页的页头高度、内容内边距、
  控制列宽度都来自同一组常量（`desktop.ui.theme`）。

⚠️ 本类**只依赖共享底座**（`desktop.ui.*`、`desktop.workers`），不 import
任何模块页、不 import `TaskDetailPage`——「模块独立」这条底线由本文件守住。

### `class ModulePage(QWidget, WorkerHost)`

独立模块页面骨架：页头（标题 + 副标题 + 操作区）+ 左右两栏 + 状态行。

子类需要做的三件事：

1. `TITLE` / `SUBTITLE`：页头文案（`__init__` 里已经摆好控件，
   有需要在构建后改文案的走 `self.header.title_label`）；
2. `_build_preview()`：左栏预览控件（**必须实现**，返回 QWidget）；
3. `_build_control()`：右栏控制控件（**必须实现**，返回 QWidget）。

`status(text)` 往页头的状态行写字，`toast(kind, title, content)` 弹
InfoBar —— 这两个是各模块反馈执行结果的标准出口，别自己 new InfoBar。

⚠️ **初始只显示大输入区**（用户 2026-10-03）：

    > 初始就只有一个输入框，下面的操作面板和预览这些都要选择输入文件后
    > 才显示出来

所以左右分栏与日志区在构造完成后就被收起来，由
:meth:`show_workspace` / :meth:`sync_workspace_visible` 在"用户真的给了
输入"之后才点亮。⚠️ 收起来的只是**可见性**，控件照旧构造 —— 惰性构造
会让各模块页的控件引用（`self.viewer` / `self.control`…）在
`_on_source_changed` 里才存在，而那个信号恰好在构造期之后才发，
早绑信号会 AttributeError；而且隐藏的控件不占布局，首帧也更快。

子类**只需在"源变了"的回调里调一次**
:meth:`sync_workspace_visible`（传"有没有源"），清空源时传 `False`
就自动收回去。

#### 方法

| 方法                                                 | 说明                                                           |
| ---------------------------------------------------- | -------------------------------------------------------------- |
| `__init__(parent=None)`                              | 组装骨架：页头 → 整幅输入区（可选）→ 左右分栏 → 状态行。       |
| `show_workspace(shown: bool) -> None`                | 显隐"操作界面"（左右分栏 + 日志区）。                          |
| `sync_workspace_visible(has_source) -> None`         | 按"当前有没有源"开关操作界面（各模块在源变化时调一次即可）。   |
| `workspace_shown() -> bool`                          | 操作界面当前是否显示（自测与截图脚本用）。                     |
| `dragEnterEvent(event) -> None`                      | 拖到页面空白处：当作拖向输入区（点亮它），避免"拖上去没反应"。 |
| `dragMoveEvent(event) -> None`                       | 拖拽移动中：保持接受（Qt 要求显式接受才会给 drop）。           |
| `dragLeaveEvent(event) -> None`                      | 拖出页面：熄灭输入区高亮。                                     |
| `dropEvent(event) -> None`                           | 松手：把路径交给输入区，由它按步骤规则归一成源。               |
| `status(text: str, kind: str='info') -> None`        | 写页头状态行；`kind` 取 info/success/warning/error 决定颜色。  |
| `toast(kind: str, title: str, content: str) -> None` | 弹 InfoBar（右下角，与详情页 `_toast` 同一位置/时长）。        |
| `log(text: str) -> None`                             | 往底部日志区追加一行。                                         |
| `closeEvent(event) -> None`                          | 关闭时收尾后台线程，避免解释器退出时被强杀（同详情页规矩）。   |

##### `show_workspace(shown: bool) -> None`

显隐"操作界面"（左右分栏 + 日志区）。

初始为 `False`（用户 2026-10-03：「初始就只有一个输入框，下面的操作
面板和预览这些都要选择输入文件后才显示出来」）。有输入之后由
:meth:`sync_workspace_visible` 打开。

大输入区同时切成**独占模式**（自己撑满整幅，见
:meth:`desktop.steps.source_zone.SourceZone.set_solo_mode`）——
否则收起分栏后页面上半屏是框、下半屏一片空白，看着像没加载完。

##### `sync_workspace_visible(has_source) -> None`

按"当前有没有源"开关操作界面（各模块在源变化时调一次即可）。

`has_source` 传 `Path` / `None` 都行，判的是"是不是空"。

##### `log(text: str) -> None`

往底部日志区追加一行。

⚠️ 用 `append` 而不是 `appendPlainText`：日志区换成了
:class:`desktop.components.log_panel.LogPanel`，它的文本域是
qfluentwidgets 的 `TextEdit`（与详情页同款），只有 `append`。

### `class StepModulePage(ModulePage)`

**带完整步骤控制**的模块页：绝大多数步骤页的直接基类（需求 2 的落点）。

一个"独立步骤"的页面真正只差两件事：

1. 左栏用哪个预览控件（:meth:`_build_preview`）；
2. 跑完之后怎么把产物交给它（:meth:`on_result`）。

其余全是**每个步骤都一样**的外设：摆一块横跨整幅的大输入区、建
:class:`~desktop.steps.control.StepControl`（参数 + 输出目录 + 执行/中断）、
把控制区的状态/日志/失败接到页面的反馈出口、源变了怎么改副标题与显隐、
收尾执行线程。这些此前在 extract/rembg/print/detect 四个页面里**逐字抄了
四遍**——加第五个步骤就再抄一遍。现在全部收在这里。

子类要做的**全部**事情：

.. code-block:: python

    class MyPage(StepModulePage):
        SPEC = spec_by_key("my_step")        # 1. 认领步骤元数据

        def _build_preview(self):            # 2. 左栏预览控件
            self.viewer = SomeViewer()
            return self.viewer

        def on_result(self, output, result): # 3. 产物怎么上屏
            self.viewer.set_images(...)

⚠️ **拼版页不继承它**（`desktop/modules/imposition/page.py`）：它的"源"是
**一批图片**而非一个源（要 `collect_files` 摊平），执行也是纯函数导出
而非 `StepSpec.command`，外壳因此对不上。它继续直接继承
:class:`ModulePage`。

#### 方法

| 方法                                            | 说明                                                               |
| ----------------------------------------------- | ------------------------------------------------------------------ |
| `idle_text() -> str`                            | —                                                                  |
| `on_result(output: Path, result: dict) -> None` | 执行成功：把产物交给左栏（子类实现）。                             |
| `on_failed(message: str) -> None`               | 执行失败：给一句人话（状态行与日志已由控制区写过）。               |
| `__init__(parent=None)`                         | 先把页头文案从 spec 落成实例属性，再建骨架。                       |
| `source_summary(source) -> str`                 | 副标题里那一行 `<源> → <输出>`；子类可加图片张数等信息。           |
| `source_images() -> list[Path]`                 | 源里的图片清单：源是文件就是它自己，是目录就取顶层（认本步后缀）。 |
| `shutdown_workers() -> None`                    | 收尾执行线程（壳层关窗口时会调到这里）。                           |

##### `on_result(output: Path, result: dict) -> None`

执行成功：把产物交给左栏（子类实现）。

`output` 是内核回传的产物路径——**目录还是文件取决于这一步**
（`StepSpec.artifact_is_file`：`print` 回传 PDF 文件，其余回传目录）。
`result` 是 job 在 worker 线程里攒下的少量数据（如导出张数）。

##### `__init__(parent=None)`

先把页头文案从 spec 落成实例属性，再建骨架。

⚠️ 必须在 `super().__init__()` **之前**赋值：`ModulePage.__init__`
构造期就会读 `self.TITLE` / `self.SUBTITLE` 去建页头，晚一步就
建出一张空标题的页头（而它之后不会再被重建）。实例属性遮蔽类属性，
所以各页面不必再各自写一遍 `TITLE = _SPEC.title`。

##### `source_images() -> list[Path]`

源里的图片清单：源是文件就是它自己，是目录就取顶层（认本步后缀）。

⚠️ 只在"这一步的输入物本身就是图片"时有意义（rembg/print）；提取的
源是 PDF、检测的源是图片但不这么用，子类别硬调。

---

## `desktop.modules.detect.page`

源码：[`desktop/modules/detect/page.py`](../../desktop/modules/detect/page.py)

「检测文本框」独立模块页：与任务流程无关，选一批图片直接检测内容框。

**复用共用组件**（`desktop/steps`）：页头下方横跨整幅的**大输入区**（拖图片 /
拖文件夹 / 点选），右栏是 :class:`StepControl`（输出目录 + 执行/中断），执行走
`StepKernel` → `functions.get_function("detect")`——与任务流程第二步是同一条
代码路径。

**和别的模块页最大的不同：这一步的产物不是文件，是坐标。**

`detect` 默认不落盘（`--save` 关着），框只经 `page_boxes` 结构化事件回来
（见 `functions.detect.DetectFunction._report_boxes`）。所以：

1. 内核必须把**非 progress/log 的事件**原样透传上来（`StepKernel.event`，
   2026-10-02 补的通道）——改造前它只转进度和日志，这一步的结果到不了界面；
2. 本页把每页的框收在内存里（`self._boxes`，键 = 文件名去后缀），左栏用共享
   查看器把框画在图上，用户可直接**手绘 / 拖动 / 缩放手柄 / Delete** 修正；
3. 交付有两条路（用户 2026-10-03 定的）：
   - 「**导出标注图**」：把框画回原图写成 PNG，一眼能核对框对不对；
   - 「**导出坐标 JSON**」：写 `<输出目录>/boxes.json`，格式与任务流程的
     `tasks/<id>/boxes.json` **逐字段一致**（`{stem: {boxes, origin,
updated_at}}`），可直接当作下一步（或将来自定义流程里任意一步）的输入。

⚠️ **槽位约定**（半幅 2 槽 `[左, 右]`、整幅 1 槽 `[整幅]`）的全部规则来自
`utils.box_geometry`（`page_box_slots_from_event` 读事件、`half_slots` 收
人工框、`set_box_full` / `set_box_half` / `drop_box` 做人工干预），本页不
自己数"还剩几个框"——按个数推类型会造成"删掉整幅框后右边的框自动变成整幅"
（用户 2026-09-29 报过的老问题）。

⚠️ **框类型控件摆在这里、检测按钮不搬过来**（用户 2026-10-03）：

- 「选中框类型 / 删除选中框」**摆出来**并接线——它们只依赖查看器，本页完全
  驱动得了，而用户要的"手绘之后能标成左框/右框/整幅"正需要它们；
- `DetectPanel` 里的「整页模式」与「检测本页」**不摆**：前者切的是**第三步**
  的 area（单文件模式没有下游），后者由任务流程宿主用子进程驱动单页检测，
  本页的执行入口是整批的 :class:`StepControl`。留着就是两个点不动的死控件。

### 模块常量

| 名称        | 值             |
| ----------- | -------------- |
| EXPORT_NAME | `"boxes.json"` |

### `class DetectModulePage(StepModulePage, ThumbSourceMixin)`

检测文本框模块页：拖入图片 → 检测内容框 → 图上修正 → 导出坐标 JSON。

#### 方法

| 方法                                              | 说明                                                            |
| ------------------------------------------------- | --------------------------------------------------------------- |
| `__init__(parent=None)`                           | 建骨架、共用步骤控件与内存中的框表。                            |
| `source_summary(source) -> str`                   | 在共用的 `<源> → <输出>` 之外，**补上待检测张数**。             |
| `edit_effect_note(path: Path) -> str`             | 编辑器改了待检测的图片：框坐标以**图片原始像素**为基准。        |
| `on_result(out_dir: Path, _result: dict) -> None` | 检测跑完：重画当前页，并把「检出几页 / 几页无框」写到状态行。   |
| `export_boxes() -> None`                          | 把各页框坐标写成 `<输出目录>/boxes.json`（与任务流程同格式）。  |
| `export_annotated_images() -> None`               | 把框画回原图导出成 PNG：先选目录，**目录已存在就问是否覆盖**。  |
| `shutdown_workers() -> None`                      | 收尾：查看器自己的后台线程 + 两个执行线程（检测、导出标注图）。 |

##### `edit_effect_note(path: Path) -> str`

编辑器改了待检测的图片：框坐标以**图片原始像素**为基准。

改了尺寸就必须重跑检测（旧框还按旧图的坐标系画，会整体偏移）；只改
像素不改尺寸时旧框仍然对得上，所以提示里区分这两种情况而不是一律要求
重跑。

##### `on_result(out_dir: Path, _result: dict) -> None`

检测跑完：重画当前页，并把「检出几页 / 几页无框」写到状态行。

`out_dir` 是输出目录（`detect` 默认不落盘，这里只是共用控件回传的
那个路径），导出按钮会用到它。

##### `export_boxes() -> None`

把各页框坐标写成 `<输出目录>/boxes.json`（与任务流程同格式）。

格式（`desktop/store/annotations.py` 的 `boxes.json`）::

    {"<页名去后缀>": {"boxes": [[x1,y1,x2,y2], ...],
                     "origin": "auto" | "manual",
                     "updated_at": <秒级时间戳>}}

用 `desktop.store.json_io.write_json`（临时文件 + `os.replace` 原子
落盘）——与任务流程写这份文件走的是同一个 IO，不另写一套。

##### `export_annotated_images() -> None`

把框画回原图导出成 PNG：先选目录，**目录已存在就问是否覆盖**。

用户 2026-10-03 的原话是「导出的时候提示选择输出目录，如果输出目录
已经存在了，则提示是否覆盖」，所以这里**一定先弹目录选择**，再用
「目录已存在且非空」作为覆盖确认的条件：

- 目录不存在 → 直接写（没什么可覆盖的）；
- 目录存在但**空** → 直接写，不必为一个空目录打断用户；
- 目录存在且**有文件** → 弹确认，说清"会覆盖同名标注图"。

⚠️ 确认框里**不列文件名**：一屏几十页列出来反而看不过来，只说清
「同名覆盖、其余保留」——本模块只写自己的 `<stem>.png`，绝不动
目录里别的文件（`export_annotated` 没有任何删除逻辑）。

---

## `desktop.modules.extract.page`

源码：[`desktop/modules/extract/page.py`](../../desktop/modules/extract/page.py)

「图片提取」独立模块页。

**复用共用组件**：页头下方是横跨整幅的**大输入区**
（:class:`~desktop.steps.source_zone.SourceZone`：拖 PDF、点选），右栏是
:class:`~desktop.steps.control.StepControl`（参数 + 输出目录 + 执行/中断），
执行走 :class:`~desktop.steps.kernel.StepKernel` →
`functions.get_function("extract")`——与 CLI 同一条代码路径，本页不再
自己写 worker 线程；这些外设全部由 :class:`StepModulePage` 收口。

**左栏是「缩略图条 + 右侧大图」一种形态走到底**（用户 2026-10-03）：

- **未提取**：选完 PDF 立刻把每页渲成缩略图（缓存在
  `~/Documents/guji/singletask/图片提取/thumbnails/<书>/`），左栏按「第 N 页」
  列出，点哪页右侧就按需渲那一页的**高清**大图；
- **提取完成**：清单换成输出目录里的**提取出的图片**，直接看结果。

⚠️ 此前这里是个**上下分栏**（上半 PDF 预览 + 下半提取结果），两个控件各带一套
缩略图条与线程。现在只剩一个 :class:`ImageViewerWidget`——「所有独立任务左侧
都是缩略图」这条要求在本页就落在这一个控件上。

⚠️ **产物位置不动**：输出目录仍默认在源 PDF 旁边
（:meth:`desktop.steps.spec.StepSpec.default_output`）。singletask 下面**只放
缩略图缓存**，不放产物（用户 2026-10-03 明确「生成目录按照原先的」）。

### `class ExtractModulePage(StepModulePage, ThumbSourceMixin)`

图片提取模块页：选 PDF → 看页缩略图 → 调参数 → 执行 → 看提取结果。

#### 方法

| 方法                                               | 说明                                                         |
| -------------------------------------------------- | ------------------------------------------------------------ |
| `edit_effect_note(path: Path) -> str`              | 编辑器改了提取出来的图片：**这张图本身就是这一步的产物**。   |
| `on_result(out_root: Path, _result: dict) -> None` | 成功：清单换成输出目录里的图片（**从此左栏就是提取结果**）。 |
| `shutdown_workers() -> None`                       | 收尾查看器自己的后台线程（页缩略图 pass / 大图渲染）。       |

##### `edit_effect_note(path: Path) -> str`

编辑器改了提取出来的图片：**这张图本身就是这一步的产物**。

未提取时左栏列的是 PDF 的页缩略图（虚拟页，没有可回写的文件，右键
不提供「编辑图片」），所以能走到这里的只有产物图。

##### `on_result(out_root: Path, _result: dict) -> None`

成功：清单换成输出目录里的图片（**从此左栏就是提取结果**）。

`show_images` 内部会经 `set_images` 退出 PDF 页模式
（见 :meth:`ImageViewerWidget.set_images` 的注释）——不退出的话点哪页
都会回到 PDF 的同一页。

### 模块函数

| 函数                                                         | 说明                                   |
| ------------------------------------------------------------ | -------------------------------------- |
| `collect_result_images(out_root: str \| Path) -> list[Path]` | 收集提取产物图片，**同名只保留一份**。 |

#### `collect_result_images(out_root: str | Path) -> list[Path]`

收集提取产物图片，**同名只保留一份**。

⚠️ 为什么要去重（用户 2026-10-03 报）：`rglob("*")` 会把
`<输出>/1.jpg`（单 PDF 时的平铺产物）**和**
`<输出>/<PDF名>/images/1.jpg`（命令自己的嵌套布局残留）一起收进来，
同一个 PDF 跑两遍就会留下两套 ⇒ 预览里**每页出现两次**（截图里两个
`1.jpg`），用户以为程序重复处理了。

规则：**顶层优先，其次按路径排序取第一个**。顶层就是"应该在那儿"的位置
（平铺的产物），嵌套里的是残留；同名冲突时不覆盖、不删除——**只影响
预览显示**，产物原样留给用户。

---

## `desktop.modules.imposition.page`

源码：[`desktop/modules/imposition/page.py`](../../desktop/modules/imposition/page.py)

「拼图」独立模块页（= 图片拼版）。

**复用共用组件**：

- 输入：:class:`~desktop.steps.source_zone.SourceZone`——页头下方横跨整幅的
  **大输入区**（拖一批图片、拖一个图片文件夹、或点选），与"图片提取 / 去底色"
  是同一块控件；
- 执行：:class:`~desktop.steps.kernel.StepKernel` + `CallableJob`——
  拼版不是 CLI 命令，所以走"纯函数 job"这条路（内核同样只认"输出目录"）；
- 界面：`ImpositionViewWidget`（左页清单 + 右拖拽画布）、
  `ImpositionPanel`（右侧控制面板）、`ImpositionPickerDialog`（选图弹窗）；
- 规则：`desktop.services.imposition` 是**纯函数模块**（无 Qt），版面默认
  摆放、自动拼版、合成紧裁全部直接用；
- 元数据：`desktop/steps/spec.py` 的 imposition 条目（标题/副标题/过滤串/
  后缀/输出名）。

**独立**：不依赖任务目录、不依赖 `TaskDetailPage` 的拼版控制器。用户选了
一批图片作为「源清单」，模块自己维护一份 `doc`（内存 + 可导出），
点「导出成品」把每页合成为 PNG。

⚠️ 与任务流程的差别（有意为之）：任务流程里拼版的产物供第四步生成 PDF，
且「启用开关」决定取图来源；单文件模式下没有下游，所以这里把面板里的
「启用开关」隐掉，只留版面操作与导出。

### 模块常量

| 名称           | 值         |
| -------------- | ---------- |
| EDITED_DIRNAME | `"edited"` |

### `class ImpositionModulePage(ModulePage)`

拼图模块页：选图 → 自动/手动拼版 → 调整版面 → 导出成品。

#### 方法

| 方法                          | 说明                                                 |
| ----------------------------- | ---------------------------------------------------- |
| `__init__(parent=None)`       | 先建骨架，再补「选图 / 自动拼版 / 导出」这条操作链。 |
| `close_zoom_dialog() -> None` | 关掉预览弹窗（内容失效时调：换源 / 清空）。          |
| `shutdown_workers() -> None`  | 关闭页面前中止并等待导出线程。                       |

### 模块函数

| 函数                        | 说明                                                   |
| --------------------------- | ------------------------------------------------------ |
| `edited_page_dir() -> Path` | 手工修饰过的整页组合的存放目录（**缓存**，不是产物）。 |

#### `edited_page_dir() -> Path`

手工修饰过的整页组合的存放目录（**缓存**，不是产物）。

「编辑整页组合」在独立拼图页里没有现成的落点：成品是点「导出成品」那一刻
才写进用户选的目录的。所以手改的那张先存在 singletask 下（用户 2026-10-03
定的独立任务缓存区），导出时再盖到对应成品上——输出目录归用户，程序只往
里写最终成品。

⚠️ 目录名走 `spec.disk_key()`（= `imposition`）而不是标题：这里存着
用户手改过的版面图，标题一改就再也读不到（"明明改过版面，重新打开又变回
原样"）。见 :meth:`desktop.steps.spec.StepSpec.disk_key`。

---

## `desktop.modules.print.page`

源码：[`desktop/modules/print/page.py`](../../desktop/modules/print/page.py)

独立模块「生成 PDF」：与任务流程无关，选一批成品图直接合成 PDF。

**复用共用组件**：页头下方横跨整幅的**大输入区**（拖图片文件夹 / 拖一批图片 /
点选），右栏是 :class:`~desktop.steps.control.StepControl`（打印参数 + 输出目录 +
执行/中断），执行走 :class:`~desktop.steps.kernel.StepKernel` →
`functions.get_function("print")`——与任务流程第四步是同一条代码路径（连参数
面板都是同一个 `PrintPanel`）。外设由 :class:`StepModulePage` 收口。

⚠️ **与任务流程第四步的有意差别：页序。** 流程里页序 = 第四步列表里用户手动排的
那份清单（`functions/print` 的 `files` 参数）。独立页面按用户 2026-10-02 的
选择**不提供手动排序**——页序就是文件名顺序
（`utils.sort_utils.pdf_custom_sort_key`，与 CLI 直跑 `guji run print <目录>`
一致）。要调页序，先用「拼图」模块把版面排好再拖过来。

⚠️ **产物形态与别的模块不同**：`print` 产出的是**一个 PDF 文件**，不是一目录
图片。所以 `StepSpec.artifact_is_file=True`——执行内核**不会**把
`function.outpath` 覆盖成输出目录（那样会拿目录当文件路径写），并且把**真正的
PDF 路径**回传给 `on_result`；本页据此把左栏切到「产物 PDF 的页缩略图」。

⚠️ **左栏前后两个形态**（用户 2026-10-03：「所有独立任务左侧都是缩略图」）：

- **未生成**：左侧是**待打印图片**的缩略图（缓存在 `singletask/生成 PDF/`），
  选完源就能翻看要合进去的是哪几张；
- **生成后**：左侧换成**产物 PDF 的页缩略图**，看成品。

两种形态共用同一个 :class:`~desktop.components.viewers.ImageViewerWidget`——
它既能显示一批图片，也能把一本 PDF 的页当"图片"列出来（`set_pdf_source`）。

### `class PrintModulePage(StepModulePage, ThumbSourceMixin)`

生成 PDF 模块页：拖入成品图（一批或一个文件夹）→ 调版面 → 合成 PDF。

#### 方法

| 方法                                          | 说明                                                                  |
| --------------------------------------------- | --------------------------------------------------------------------- |
| `source_summary(source) -> str`               | 在共用的 `<源> → <输出>` 之外，**补上待合成张数**。                   |
| `edit_effect_note(path: Path) -> str`         | 编辑器改了待打印图：那张图就是最终进 PDF 的那张。                     |
| `on_result(pdf: Path, _result: dict) -> None` | 成功：`pdf` 是**PDF 文件路径**（见 `StepSpec.artifact_is_file`）。    |
| `shutdown_workers() -> None`                  | 收尾左栏自己的后台线程（缩略图缓存 / 大图渲染）+ 共用控件的执行线程。 |

##### `edit_effect_note(path: Path) -> str`

编辑器改了待打印图：那张图就是最终进 PDF 的那张。

⚠️ 生成完成之后左栏切成了**产物 PDF 的页缩略图**——矢量页没有可回写
的图片文件，右键不提供「编辑图片」，所以能走到这里的都是待打印图。

##### `on_result(pdf: Path, _result: dict) -> None`

成功：`pdf` 是**PDF 文件路径**（见 `StepSpec.artifact_is_file`）。

左栏从「待打印图片」切到「产物 PDF 的页缩略图」——页缩略图缓存在
`singletask/生成 PDF/thumbnails/<产物>/`，所以第二次看同一个成品
是秒开。

---

## `desktop.modules.rembg.page`

源码：[`desktop/modules/rembg/page.py`](../../desktop/modules/rembg/page.py)

「去底色」独立模块页。

**复用共用组件**：页头下方是横跨整幅的**大输入区**（拖图片、拖整个文件夹、
点选），右栏是 :class:`~desktop.steps.control.StepControl`（参数 + 输出目录 +
执行/中断），执行走 :class:`~desktop.steps.kernel.StepKernel` →
`functions.get_function("rembg")`——与任务流程第三步是同一条代码路径。
这些外设由 :class:`StepModulePage` 收口，本页只补两件事：左栏用哪个预览
控件、产物怎么上屏（附带的"副标题带图片张数"由 `source_summary` 覆盖）。

**独立**：不需要任务、不需要检测框——用户拖入**一整个图片文件夹**（批量）或
**单张图片**，结果用原图/结果对比控件（`RembgPreviewWidget`）看。

⚠️ 与任务流程的差别（有意为之）：第三步的 area/border 依赖第二步的检测框，
单文件模式下没有框可用，所以这里**只暴露「整图/去底参数」这一层**，area 固定
按「图像本身」处理，不参与框裁剪。

### `class RembgModulePage(StepModulePage, ThumbSourceMixin)`

去底色模块页：拖入图片（单张或文件夹）→ 调参数 → 批量去底 → 对比看结果。

#### 方法

| 方法                                              | 说明                                                          |
| ------------------------------------------------- | ------------------------------------------------------------- |
| `__init__(parent=None)`                           | —                                                             |
| `source_summary(source) -> str`                   | 在共用的 `<源> → <输出>` 之外，**补上图片张数**。             |
| `edit_effect_note(path: Path) -> str`             | 编辑器改了图：**改的是源图还是去底色结果**，生效方式不一样。  |
| `on_result(out_dir: Path, _result: dict) -> None` | 成功：把「原图 → 结果」两组图塞进对比控件。                   |
| `shutdown_workers() -> None`                      | 收尾查看器自己的后台线程（缩略图缓存 / 大图渲染）+ 执行线程。 |

##### `edit_effect_note(path: Path) -> str`

编辑器改了图：**改的是源图还是去底色结果**，生效方式不一样。

- 源图（左栏「原图」形态）→ 结果还是按旧图算的，重跑一次才用上；
- 结果文件（「去底色结果」形态）→ 它自己就是这一步的产物，下游
  （生成 PDF）读的就是它。

##### `shutdown_workers() -> None`

收尾查看器自己的后台线程（缩略图缓存 / 大图渲染）+ 执行线程。

与 extract / detect / print 三页一致：查看器是独立于页面外壳的
`WorkerHost`，不给它收尾，退出时那些线程还在跑。

---

## `desktop.modules.shell`

源码：[`desktop/modules/shell.py`](../../desktop/modules/shell.py)

左侧导航壳层：qfluentwidgets 的 `NavigationInterface` + 页面栈。

布局照搬 `FluentWindow` 的做法（导航栏在左、页面栈在右、拉伸因子给页面栈），
但不继承 `FluentWindow`——那个类自带标题栏/亚克力/Mica 一整套窗口装饰，
而本程序用的是原生标题栏（`desktop/app.py` 有最大化/还原尺寸与单例逻辑），
换标题栏会连带影响窗口尺寸夹紧与截图脚本。所以只借它的**布局套路**：

    hBoxLayout { navigationInterface, pageStack( stretch=1 ) }

导航条目分两组：

- `TOP`：**任务管理**（原 `TaskListPage`，点任务仍在栈内打开详情页）+
  各独立模块（图片提取 / 去底色 / 拼图，来自 `desktop.modules.MODULES`）；
- 模块条目全部**惰性构造**：第一次点进去才 `factory()`，不点不建。

⚠️ 导航栏**默认折叠**（用户 2026-10-02：「左侧的目录，默认关闭」）：启动后
只剩一列图标，正文区拿到整幅宽度；想看到条目文字就点左上角的菜单按钮展开，
再点一次收回。**不要**再在 resizeEvent 里替用户 `expand()`——那会让"默认
关闭"失效（见 :meth:`resizeEvent` 的说明）。

⚠️ 壳层**不 import 任何具体模块页**，只认 :class:`desktop.modules.Module` 的
元数据与工厂——这是「模块独立」在壳层侧的落实：删模块只需要改 `MODULES`。

### 模块常量

| 名称                  | 值         |
| --------------------- | ---------- |
| NAV_COMPACT_WIDTH     | `48`       |
| NAV_WIDTH             | `200`      |
| NAV_MIN_EXPAND_WINDOW | `720`      |
| ROUTE_TASKS           | `"tasks"`  |
| ROUTE_DETAIL          | `"detail"` |

### `class ModuleShell(QWidget)`

壳层根控件：左侧导航 + 右侧页面栈。

对外暴露 :meth:`open_detail` / :meth:`back_to_list` 供 `MainWindow`
转发（两者都走栈切换，行为与 `app.py` 原来的 `_open_detail` /
`_back_to_list` 一致）。

#### 方法

| 方法                                       | 说明                                                                      |
| ------------------------------------------ | ------------------------------------------------------------------------- |
| `__init__(store: TaskStore, parent=None)`  | 建导航与页面栈，挂上「任务管理」页，模块条目按注册表登记。                |
| `show_tasks() -> None`                     | 切回任务列表页并刷新列表。                                                |
| `detail_page()`                            | 任务详情页（惰性构造）。                                                  |
| `prewarm_detail_page() -> None`            | 预构造详情页骨架与**第一步**面板（同 app.py 原 `_prewarm_detail_page`）。 |
| `open_detail(task_id: str) -> None`        | 打开某个任务的详情页（行为与 `app.py::_open_detail` 一致）。              |
| `back_to_list() -> None`                   | 详情页「返回」→ 切回列表并刷新。                                          |
| `show_module(key: str) -> None`            | 切到某个模块页；首次进入时惰性构造。                                      |
| `module_page(key: str) -> QWidget \| None` | 已构造的模块页；**没建过返回 None**（自测用它断言"惰性没被破坏"）。       |
| `rebind_store(store: TaskStore) -> None`   | 把壳层与**已建页面**上的 store 引用一起换掉（换数据目录用）。             |
| `current_route() -> str`                   | 当前**显示中**页面的路由键。                                              |
| `selected_route() -> str`                  | 导航栏**当前高亮**的条目路由键。                                          |
| `nav_is_expanded() -> bool`                | 导航栏当前是否展开（`EXPAND`）。                                          |
| `toggle_nav() -> None`                     | 展开/收回导航栏（等价于点左上角的菜单按钮）。                             |
| `shutdown_workers() -> None`               | 收尾所有页面的后台线程（壳层 + 惰性页 + 已建模块页）。                    |
| `keyPressEvent(event) -> None`             | ←/→ 在详情页内转发翻页（同 app.py 原逻辑，焦点链不消费时兜底）。          |

##### `show_tasks() -> None`

切回任务列表页并刷新列表。

⚠️ 不去手动 `setCurrentItem`：切页会触发 `pages.currentChanged`
→ :meth:`_sync_nav_to_page` 统一同步高亮，单点维护不易漏。

##### `detail_page()`

装饰器：`property`

任务详情页（惰性构造）。

保留这个名字：`tests/selftests/_context.py` 与 `tests/gui_shot.py`
都按 `window.detail_page` 取页面来操作控件（原来在 MainWindow 上，
现在壳层转发一层，外部契约不变）。

##### `show_module(key: str) -> None`

切到某个模块页；首次进入时惰性构造。

找不到该 key（注册表被改过、或旧导航项残留）时安静退回任务管理并提示，
不让壳层抛异常——导航项是用户能点的东西，任何输入都不该让程序崩。

##### `rebind_store(store: TaskStore) -> None`

把壳层与**已建页面**上的 store 引用一起换掉（换数据目录用）。

⚠️ 必须一起换：壳层自己持一份（惰性详情页构造时取的就是它）、列表页
持一份、已经建出来的详情页又持一份。只改 `MainWindow.store` 而漏掉
这里，惰性构造的详情页会继续指向**老目录**——表现是"打开的是同名任务
号的另一个任务"（`tests/selftests/last_stage.py` 就是这么红的：真实数据
目录里恰好也有 0001，而它停在拼版步）。测试与截图脚本的
「换 store 指向临时目录」这一手（`_context.prepare` / `gui_shot`）全靠它。

##### `current_route() -> str`

当前**显示中**页面的路由键。

`QStackedWidget` 里的页面对象与路由的映射在这里反查；模块页按
`_module_pages` 的键匹配，任务列表/详情页按对象身份匹配。

##### `selected_route() -> str`

导航栏**当前高亮**的条目路由键。

⚠️ `NavigationInterface` 没有公开的"取当前项"接口（只有
`setCurrentItem`），所以这里自己记一份 `_selected_route`——
高亮是我们在 :meth:`_sync_nav_to_page` 里设的，记它准确且无副作用。

##### `nav_is_expanded() -> bool`

导航栏当前是否展开（`EXPAND`）。

测试/截图脚本用它断言"默认是折叠的、点菜单按钮能展开"——qfluentwidgets
没有公开的 displayMode 读取接口，所以在这里封一层。

##### `toggle_nav() -> None`

展开/收回导航栏（等价于点左上角的菜单按钮）。

供菜单按钮之外的入口（自测、快捷键、将来的命令面板）复用同一条逻辑：
折叠时展开、展开时收回，**不改变**默认折叠这条约定。

⚠️ 必须走 `NavigationInterface.toggle()`：`NavigationInterface`
**只有 `expand()` 没有 `collapse()`**（收回在 `panel` 上），
自己拼 expand/collapse 会踩 `AttributeError`。

---

## `desktop.modules.thumb_source`

源码：[`desktop/modules/thumb_source.py`](../../desktop/modules/thumb_source.py)

独立任务页左栏的**缩略图源**：把「当前源的缩略图」统一喂给查看器。

用户 2026-10-03 的要求：「**所有独立任务左侧显示的都是缩略图**」。此前五个
独立任务页各写各的：图片提取页自己拿 `PdfViewerWidget` 渲 PDF 页缩略图，
detect/rembg/print 直接把**原图**塞进查看器（缩略图条每次现解码），
拼图页压根没有缩略图条。

本模块把这件事收成**一个混入**，各页只回答两个问题：

1. **源是什么** → :meth:`ThumbSourceMixin.show_pdf` 或 :meth:`show_images`；
2. **源换了/结果出来了** → 再调一次即可（同一个查看器，不重建控件）。

⚠️ **只管缩略图，不管右侧大图**：大图仍是各查看器自己的事（extract 未提取时
要从 PDF 按需渲高清页，见 :class:`~desktop.components.viewers.ImageViewerWidget`
的 `page_renderer`）。这一层刻意不做「一个万能预览控件」——检测框编辑、
去底色对比、拼版画布三类左栏差异极大，硬合并只会得到一个谁都不合身的控件。

⚠️ **只写缓存，不碰产物**：输出目录仍由
:meth:`desktop.steps.spec.StepSpec.default_output` 决定。

### `class ThumbSourceMixin`

让一个「持有 :class:`ImageViewerWidget` 的宿主」按源类型接上缩略图缓存。

使用前提：宿主自身是 :class:`~desktop.workers.WorkerHost`（所有模块页都是，
`ModulePage` 已 `_init_worker_host()`），且有 `self.SPEC` 与
`self.viewer`。

用法::

    class MyPage(StepModulePage, ThumbSourceMixin): ...
    # _on_source_changed 里：
    self.show_source(source)          # PDF 给路径，图片/目录给清单
    # 跑完之后：
    self.show_images(collect_result_images(out))

#### 方法

| 方法                                      | 说明                                                           |
| ----------------------------------------- | -------------------------------------------------------------- |
| `show_source(source, paths=None) -> None` | 按源的类型接上左栏缩略图。                                     |
| `show_pdf(pdf: Path \| str) -> None`      | 源是 PDF：渲页缩略图并交给查看器（大图按需渲高清页）。         |
| `show_images(images) -> None`             | 源是一批图片：清单进查看器，缩略图走 singletask 缓存。         |
| `edit_effect_note(path: Path) -> str`     | 编辑后日志里那句「**什么时候生效**」；各步骤按自己的下游覆盖。 |

##### `show_source(source, paths=None) -> None`

按源的类型接上左栏缩略图。

`source` 是这一步归一化后的源（`Path` 或 `None`）；`paths`
给了就按图片清单处理（detect/rembg/print/拼图这类「源是一批图」的步骤
直接把清单传进来，省得各页再各自判断一遍）。

- 源是 **PDF** → 渲页缩略图到 `singletask/<子任务>/thumbnails/<书>/`，
  条目标签「第 N 页」，大图由查看器按需渲高清页；
- 源是**图片或目录** → 用 `spec.listing` 取清单，每张渲一张缓存小图，
  条目标签是文件名。

##### `show_pdf(pdf: Path | str) -> None`

源是 PDF：渲页缩略图并交给查看器（大图按需渲高清页）。

⚠️ 缓存目录**必须带书**（:func:`singletask_thumbnails_dir` 的第二个
参数）：缩略图文件名是页号（`0001.jpg`…），共用目录会让 A 书第 1 页
被当成 B 书第 1 页的命中缓存 ⇒ 翻出别本书的内容。

##### `show_images(images) -> None`

源是一批图片：清单进查看器，缩略图走 singletask 缓存。

清单**仍然是真实图片路径**（不是缓存路径）：右侧大图、检测框按
`Path(path).stem` 取键、放大弹窗的编辑回写，全都指着真实文件。
缓存只喂左侧缩略图条（查看器的 `thumb_provider`）。

##### `edit_effect_note(path: Path) -> str`

编辑后日志里那句「**什么时候生效**」；各步骤按自己的下游覆盖。

默认按"本步骤的源图被改了"写——重新执行本步骤就会读新图。产物形态
不同的步骤（提取的结果图、去底色的结果文件）各自覆盖成准确的说法。

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
history_combo、\_toast()。

---

## `desktop.pages.taskdetail.imposition`

源码：[`desktop/pages/taskdetail/imposition.py`](../../desktop/pages/taskdetail/imposition.py)

任务详情页的「图片拼版」共享基元与 Mixin 装配。

流程条上的「图片拼版」是**虚线可选节点**（`desktop.components.step_bar`）：
仅当第三步（图片去底色）的「区域模式」为 1（左右分开）时出现在「图片去底色」
与「生成 PDF」之间；用户可以选择它（启用）也可以不选择。

按操作逻辑拆成三个文件（后续可由不同 agent 分头维护，互不影响）：

- **本文件** `ImpositionBaseMixin`：两个模块都要用的**共享基元**——
  area 读取与节点可见性、拼版文档读写（`drafts/imposition.json`）、
  源图清单与「拼版生效」判定、第四步取图切换（`print_source_dir`）、
  视图灌装、详情进出与切任务复位；
- **`imposition_pages.ImpositionPagesMixin`**（模块一「选择拼版」）：
  启用开关、弹窗加页、删页/页序/清空；
- **`imposition_layout.ImpositionLayoutMixin`**（模块二「拼版操作」）：
  旋转/复位、版面落盘、防抖后台合成、状态行。

⚠️ 拼版本身**不是** STAGES 里的一步：runs.json / 阶段面板机制一概不感知它，
执行按钮组在拼版详情里整组隐藏。

### 模块常量

| 名称            | 值  |
| --------------- | --- |
| IMPOSITION_AREA | `1` |

### `class ImpositionBaseMixin`

拼版共享基元：节点可见性、文档读写、取图切换、详情进出。

依赖宿主页面提供：store/task_id、control_stack、step_bar、
\_select_stage()、\_set_stage_status()、\_toast()、log_view。

#### 方法

| 方法                                      | 说明                                                                |
| ----------------------------------------- | ------------------------------------------------------------------- |
| `imposition_source_files() -> list[Path]` | 可挑选的源图：第三步「提交本次任务」的成品图（stages/rembg）。      |
| `imposition_active() -> bool`             | 拼版**是否已启用**（用户勾了「在流程中启用图片拼版」就是启用）。    |
| `imposition_has_pages() -> bool`          | 拼版文档里**至少有一页**版面（能不能真的合成出图）。                |
| `print_source_dir() -> Path`              | 第四步的取图目录：拼版生效 → stages/imposition，否则 stages/rembg。 |

##### `imposition_active() -> bool`

拼版**是否已启用**（用户勾了「在流程中启用图片拼版」就是启用）。

⚠️ **只看勾没勾，不看有没有拼版页**（用户 2026-10-03 口径："如果启用了
拼板，则最后一步生成 pdf 的数据来源就是拼板"）。早先这里额外要求
"至少有一页"，于是勾了开关却还没拼页时——取图仍走去底色、流程条仍是
灰虚线 + 绕行线，用户看到的就是"启用了却不生效"。「有没有拼版页」是
另一件事（能不能真出东西），走 :meth:`imposition_has_pages`。

本方法是"**流程走不走拼板**"的唯一判据：第四步取图来源
(:meth:`print_source_dir`) 与流程条生效态
(:meth:`_sync_imposition_step_bar`) 都只看它。

##### `imposition_has_pages() -> bool`

拼版文档里**至少有一页**版面（能不能真的合成出图）。

与 :meth:`imposition_active` 分开：启用是**用户意图**（决定取图来源），
有页是**当前进度**（决定要不要提示"还没拼版，生成 PDF 没有输入"）。

##### `print_source_dir() -> Path`

第四步的取图目录：拼版生效 → stages/imposition，否则 stages/rembg。

⚠️ 走的是 :mod:`desktop.steps.ports` 的**条件连线**（"print 的 pages
端口由谁供给"），不是在这里 if/else 挑目录——BPM 换上游时只改连线表，
这一行不用动。

### `class ImpositionMixin(ImpositionPagesMixin, ImpositionLayoutMixin, ImpositionBaseMixin)`

「图片拼版」节点控制器 = 模块一（页管理） + 模块二（版面/合成） + 基元。

方法查找顺序：模块一 → 模块二 → 共享基元；三个文件互不 import，
只经 `self` 在组合后的宿主页面上协作。

---

## `desktop.pages.taskdetail.imposition_layout`

源码：[`desktop/pages/taskdetail/imposition_layout.py`](../../desktop/pages/taskdetail/imposition_layout.py)

**模块二「拼版操作」控制器**：画布版面操作与拼版合成落盘。

对应 UI 模块二（`desktop/components/imposition/canvas.py` +
`panel.py`）：

- 画布里拖动 / 缩放拉伸 / 旋转 → `items_changed` → 落盘 + 防抖合成；
- **双击预览**（用户 2026-09-30）：双击某张图 → 弹窗预览这张原图；
  双击两图之外的空白处 → 弹窗预览整页左右组合（按产出口径合成）；
- **右键菜单「预览图片 / 编辑图片」**（2026-10-01）：目标规则与双击一致
  （图上 → 这张原图；空白 → 整页组合）；预览与双击同一条路，「编辑图片」
  则**不经预览弹窗**直达编辑器——单张图编辑源图原图并覆盖回写（含刷新链），
  整页组合按产出口径现场合成全分辨率图、「完成」写回该页拼版成品文件；
- 面板的**整体旋转**（滑块/输入框增量）、复位本页版面（对当前页或
  选中槽位做版面变换）、**删除选中图片**（2026-09-30 用户定：选中哪张
  就能删哪张，页保留、图回未选择列表）；
- 状态行（当前页 / 选中槽位 / 拼版是否生效 / 单图页显隐「新增图片」）；
- **后台防抖合成**（`stages/imposition/`，列表顺序即页序）与生成 PDF 前
  的同步兜底合成。

只通过 `self` 依赖共享基元（`imposition.ImpositionBaseMixin`）与宿主
页面（`store`、`log_view`、`run_worker`、`_toast`），本文件
**不 import** 其它拼版控制器模块。

### 模块常量

| 名称                    | 值    |
| ----------------------- | ----- |
| COMPOSE_DEBOUNCE_MS     | `500` |
| EDIT_COMMIT_DEBOUNCE_MS | `250` |

### `class ImpositionLayoutMixin`

拼版版面操作（模块二）：旋转/复位、版面落盘、防抖后台合成。

#### 方法

| 方法                                    | 说明                                         |
| --------------------------------------- | -------------------------------------------- |
| `close_imposition_zoom_popup() -> None` | 关掉拼版预览弹窗（内容失效时调：切任务等）。 |

---

## `desktop.pages.taskdetail.imposition_pages`

源码：[`desktop/pages/taskdetail/imposition_pages.py`](../../desktop/pages/taskdetail/imposition_pages.py)

**模块一「选择拼版」控制器**：拼版页的增删与选择状态。

对应 UI 模块一（`desktop/components/imposition/page_list.py` +
`picker.py`）与右侧面板的页管理按钮（`panel.py`）：

- 启用/取消拼版（决定第四步取图来源，落盘到 `drafts/imposition.json`）；
- 「选择拼版」→ 弹窗挑两张加一页；或挑一张勾「自动拼版」批量加页；
  弹窗里还能「删除图片」（黑名单 `removed` 字段，软删除）与恢复；
- **单图页「新增图片」**（2026-09-30）：append 模式弹窗挑 1 张并进当前页；
- 删页入口只剩**左列**：「✕」释放单页 / 勾选悬浮框批量删除 / 清空全部
  ——右侧面板的「删除本页拼版」按钮已删（2026-09-30 用户定）；
  页序在左列**拖动排序**，翻页在画布下方「上一页/下一页」。

只通过 `self` 依赖共享基元（`imposition.ImpositionBaseMixin` 提供的
`_imposition_doc` / `_save_imposition_pages` / `imposition_active` /
`_refresh_print_source` / `_update_imposition_status` 等）与宿主页面
（`step_bar`、`log_view`、`_toast`），本文件**不 import** 其它拼版
控制器模块——两个模块的 agent 可以互不影响地改。

### `class ImpositionPagesMixin`

拼版页管理（模块一）：启用开关、加页、删页、清空。

---

## `desktop.pages.taskdetail.manifest`

源码：[`desktop/pages/taskdetail/manifest.py`](../../desktop/pages/taskdetail/manifest.py)

任务详情页的页面清单控制器：manifest 维护、缩略图/尺寸提供、页面增删。

### `class PageListMixin`

依赖宿主页面提供的属性：store/task_id、pages、pdf_page_count、
preview_stack、detect_viewer、extract_result_viewer、log_view、\_toast()。

#### 方法

| 方法                             | 说明                                                       |
| -------------------------------- | ---------------------------------------------------------- |
| `delete_selected_page() -> None` | 删除当前选中的页面：按路径反查 manifest 下标后落盘。       |
| `insert_pages() -> None`         | 插入图片到清单：按路径反查锚点下标，避免行号错位插错位置。 |

##### `delete_selected_page() -> None`

删除当前选中的页面：按路径反查 manifest 下标后落盘。

预览行号不能直接用于删除——文件缺失会导致查看器行号与清单下标错位；
故先经 \_viewer_index_to_manifest_index 按路径反查真实下标再 pop，
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

- view.DetailViewMixin UI 组装（头部/步骤条/预览区/控制列/日志）
- manifest.PageListMixin 页面清单、缩略图、页面增删
- history.HistoryMixin 历史执行配置回填（暂存优先）
- params_draft.ParamDraftMixin 参数暂存（改过没执行也不丢）
- submit.SubmitMixin rembg 提交控制器与按钮状态
- print_list.PrintListMixin 第四步待打印列表
- runner.StageRunnerMixin 阶段执行（worker 子进程编排）
- detect.DetectMixin detect 检测控制
- rembg_live.RembgLiveMixin 第三步改参数/翻页时只重算当前页的实时预览
- imposition.ImpositionMixin 流程条「图片拼版」可选节点
  （共享基元 imposition.py + 模块一 imposition_pages.py「选择拼版」
  - 模块二 imposition_layout.py「拼版操作」）

### `class TaskDetailPage(StageRunnerMixin, SubmitMixin, RembgLiveMixin, PrintListMixin, ParamDraftMixin, HistoryMixin, DetectMixin, ImpositionMixin, PageListMixin, DetailViewMixin, QWidget, WorkerHost)`

任务详情页：由多个 Mixin 组合，固定四阶段流程。

编排 extract→detect→rembg→print 四阶段；各职责（预览、清单、历史、
提交、执行、检测）分散到同级 Mixin，本类只持有任务切换与阶段切换骨架。

#### 方法

| 方法                                       | 说明                                                                |
| ------------------------------------------ | ------------------------------------------------------------------- |
| `__init__(store, parent=None)`             | 初始化详情页：建 worker 宿主、清运行态并组装 UI。                   |
| `set_task(task_id: str) -> bool`           | 切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。            |
| `current_stage() -> str`                   | 返回当前所处阶段的 key（extract/detect/rembg/print/imposition）。   |
| `navigate_by_arrow(forward: bool) -> bool` | 方向键切换当前步骤的页面（主窗口 ←/→ 转发入口）。                   |
| `keyPressEvent(event) -> None`             | ←/→ 切换当前步骤的页面（焦点链不消费时兜底到达这里）。              |
| `closeEvent(event) -> None`                | 关闭页面时杀掉并等待 worker/detect 子进程，并关停所有后台线程。     |
| `flush_layout_pending() -> None`           | 把各处"未提交的界面改动"补发/落盘（关窗口、切步骤、切页前都要调）。 |
| `shutdown_all_workers() -> None`           | 连同各预览控件自己的缩略图线程一起收尾。                            |

##### `__init__(store, parent=None)`

初始化详情页：建 worker 宿主、清运行态并组装 UI。

创建 store 引用与 \_init_worker_host 后台线程宿主；初始化全部运行态
字段（task_id/process/run_id/detect_cache 等）为空，再构建界面骨架。

##### `set_task(task_id: str) -> bool`

切换当前任务：复位所有阶段面板与运行态，避免跨任务泄漏。

加载任务后先调用各面板 reset_to_default 清掉上一任务手改参数，再清
detect 缓存/运行态引用并刷新清单与预览；防止参数或 run_id 串到新任务。
返回 False = 拒绝切换（任务不存在 / 子任务执行中），调用方应留在原地。

##### `current_stage() -> str`

返回当前所处阶段的 key（extract/detect/rembg/print/imposition）。

以步骤条高亮下标映射到 STAGES 序列；下标为负时按 0 兜底处理。
「图片拼版」是**伪步骤**（下标 = IMPOSITION_INDEX），返回它的专用 key：
调用方凡是拿这个 key 去 STAGES/STAGE_LABELS/runs 里查的，都必须先
挡掉（见 \_refresh_stage_views / \_apply_control_width 等处的守卫）。

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

目前是第四步的版面画布与拼版画布：拖动中不落盘，只在松手/补发时提交。

⚠️ **只按具体的类 `findChildren`，绝不用 `getattr(widget, ...)` 探测能力**：
四个阶段面板是 `LazyPanelHost`，属性转发（`__getattr__`）会**立刻把面板
构造出来**——那就把用户要求的「不进去就不建」破坏掉了。（2026-09-26 自己
踩到：写成 `getattr(w, "flush_pending", None)` 之后，`detail_prewarm`
护栏直接红成"四个面板全建"。）
⚠️ 拼版画布是**直接构造**的（不在 LazyPanelHost 里），按类查安全。

##### `shutdown_all_workers() -> None`

连同各预览控件自己的缩略图线程一起收尾。

页面自身、PDF 预览、打印预览、缩略图条分别持有 WorkerHost 的线程，
只停页面的会让其余线程在解释器退出时被强杀（偶发崩溃/卡顿）。

---

## `desktop.pages.taskdetail.params_draft`

源码：[`desktop/pages/taskdetail/params_draft.py`](../../desktop/pages/taskdetail/params_draft.py)

任务详情页的「参数暂存」：用户改过、但还没执行的阶段参数，切走也还在。

问题：进入某阶段时表单按**最近一次执行参数**回填（`history.py`）。用户改完
参数却没执行就切阶段、切任务或关程序，改动全丢——再回来看到的还是上一次执行
的值，等于白调一遍（尤其第四步参数多）。

做法：

- 面板把"用户改了参数"通过 `StagePanel.param_edited` 报上来（程序化回填由
  面板自己的 `_applying` 挡住，不会误报）；
- 这里按 400ms 防抖写 `tasks/<任务号>/drafts/<阶段>.json`（`store.DraftMixin`）；
- 进入阶段回填时的优先级是 **暂存 > 最近一次执行参数 > 内置默认**，
  实现在 `HistoryMixin._restore_stage_params`。

为什么参数非法时不覆盖暂存：颜色/边距是逐字符输入的，"0,0" 这种半截状态
`get_args()` 会抛 ValueError；此时保留上一份**有效**暂存，比写进去一份
用不了的值更合理（面板本来也会在说明行提示参数不合法）。

### `class ParamDraftMixin`

依赖宿主提供：store、task_id、control_stack。

#### 方法

| 方法                                   | 说明                                                                  |
| -------------------------------------- | --------------------------------------------------------------------- |
| `save_stage_draft(index: int) -> bool` | 暂存某阶段当前表单值；参数非法/没有任务时返回 False（不覆盖旧暂存）。 |

---

## `desktop.pages.taskdetail.print_list`

源码：[`desktop/pages/taskdetail/print_list.py`](../../desktop/pages/taskdetail/print_list.py)

任务详情页的第四步（print）列表控制器：条目规划、排序持久化、插入、下载。

### `class PrintListMixin`

依赖宿主页面提供的属性：store/task_id、print_preview、log_view、
\_toast()。

#### 方法

| 方法                          | 说明                                                                 |
| ----------------------------- | -------------------------------------------------------------------- |
| `print_source_stage() -> str` | 第四步**当前**的取图来源阶段 key（`rembg_submit` 或 `imposition`）。 |

##### `print_source_stage() -> str`

第四步**当前**的取图来源阶段 key（`rembg_submit` 或 `imposition`）。

⚠️ 与 :meth:`print_source_dir` 同源：那边取路径、这边取 key，都走
`ports.print_pages_supplier(imposition_active())` 这一次判定——
"PDF 是从哪儿取的"只有一个答案，不许两处各判一次。

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
3. **只影响显示，不落正式产物**。结果写系统临时目录（`services.rembg_live`），
   绝不碰 `stages/rembgpreview` —— 那里一旦被单页结果覆盖，「提交本次任务」
   就会把不同参数下算出来的图混在一起。

滑块拖动时 `valueChanged` 会连发，所以统一走 `LIVE_DEBOUNCE_MS` 防抖；
每次请求带 token，迟到的旧结果直接丢弃（否则慢的旧结果会盖掉新的）。

### `class RembgLiveMixin`

依赖宿主页面提供：store / task_id / process / control_stack /
rembg_viewer / log_view / current_stage() / run_worker /
\_latest_success_run() / PREVIEW_PARAM_KEYS。

---

## `desktop.pages.taskdetail.runner`

源码：[`desktop/pages/taskdetail/runner.py`](../../desktop/pages/taskdetail/runner.py)

任务详情页的阶段执行控制器：构建参数、启动 worker 子进程、解析进度日志。

纯业务派生规则见 desktop/services/print_plan.py，
rembg 提交控制器见 desktop/pages/taskdetail/submit.py，
历史配置回填见 desktop/pages/taskdetail/history.py。

### `class StageRunnerMixin`

依赖宿主页面提供的属性：store/task*id/source_path/pages、
control_stack、stage*\* 控件、log_view、process/run_id 等。

#### 方法

| 方法                                    | 说明                                                         |
| --------------------------------------- | ------------------------------------------------------------ |
| `run_stage(resume: bool=False) -> None` | 启动当前阶段的 worker 子进程（带执行权守卫，防连点起两个）。 |
| `cancel_stage() -> None`                | 中断正在执行的阶段：先落 cancelled 再 kill 子进程。          |

##### `run_stage(resume: bool=False) -> None`

启动当前阶段的 worker 子进程（带执行权守卫，防连点起两个）。

⚠️ 守卫必须包在**最外层**：下面要做参数校验、effects 组装、写运行配置，
这些都是同步重活，做完才 `QProcess.start()`。若只在 start 之前判断
`self.process`，那段时间它还是 None，连点第二下就能再起一个 worker，
两个 torch 同时加载、同时写同一批输出目录。

守卫由 :meth:`TaskDetailPage._acquire_run` 提供（受理标记 + 防抖窗口）；
真正干活的是 :meth:`_run_stage_unchecked`。

⚠️ 「图片拼版」伪步骤没有可执行内容（占位详情页，执行按钮组处于
隐藏态）；这里再挡一道，防自动化/快捷路径绕过可见性直接触发。

##### `cancel_stage() -> None`

中断正在执行的阶段：先落 cancelled 再 kill 子进程。

先立即把运行记录置为 cancelled——防止进程被强杀来不及回调时状态永远
停留 running（重启后按钮状态错乱）；随后置 cancel_requested 并 kill。

---

## `desktop.pages.taskdetail.submit`

源码：[`desktop/pages/taskdetail/submit.py`](../../desktop/pages/taskdetail/submit.py)

任务详情页的 rembg「提交本次任务」控制器。

- run_rembg_submit ：提交动作（派生条目 → worker 子进程）；
- \_update_submit_button 等 ：提交按钮的版本状态与提示。

纯版本判定规则见 services/submit_state.py，
条目/效果派生规则见 services/print_plan.py。

### `class SubmitMixin`

依赖宿主页面提供的属性：store/task_id/source_path、process、
control_stack、submit_button/submit_hint、log_view、\_toast()。

#### 方法

| 方法                         | 说明                                                      |
| ---------------------------- | --------------------------------------------------------- |
| `run_rembg_submit() -> None` | 提交本次任务：把「生成预览」的去底色图片按 area/border 等 |

##### `run_rembg_submit() -> None`

提交本次任务：把「生成预览」的去底色图片按 area/border 等
合成为真正想要的最终图片，输出到 stages/rembg 目录。

⚠️ 与「执行本子任务」共用同一份执行权（`_acquire_run`）：提交与
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

为什么需要：详情页一进来停在第一步，而第四步的 `PrintPanel` 构造要
~128 ms（占整个详情页构造的**一半**——它那张参数表单 `build_form` 单项
就 106 ms）。用户可能从头到尾都不点第四步，却每次进详情页都在为它买单。

属性访问一律转发给内部面板，所以 `control_stack.widget(3).get_args()`
这类既有写法照常工作。Qt 自己的 `sizeHint` / `paintEvent` 等由 C++
层调用，**不走 Python 的 **getattr****，不会误触发构造。

#### 方法

| 方法                                       | 说明                                                               |
| ------------------------------------------ | ------------------------------------------------------------------ |
| `__init__(factory, hooks=(), parent=None)` | factory() 造真面板；hooks 是"内部面板构造完成"后的回调（接线用）。 |
| `add_created_hook(fn) -> None`             | 注册"内部面板构造完成"回调；**若已构造则立刻执行**。               |
| `peek() -> QWidget \| None`                | **不触发构造**地看内部面板；尚未构造时返回 None。                  |
| `panel() -> QWidget`                       | 内部真面板，首次访问时构造（并把挂着的回调全部执行一遍）。         |

##### `add_created_hook(fn) -> None`

注册"内部面板构造完成"回调；**若已构造则立刻执行**。

⚠️ 必须支持挂多个回调：视图层要接预览刷新、暂存层要接 param_edited，
它们分属不同 Mixin，各自只知道自己的接线，不能互相覆盖。

### `class DetailViewMixin`

依赖宿主页面提供的方法：\_on_back、\_select_stage、各预览联动槽、
current_stage()、\_update_run_buttons() 等。

---

## `desktop.pages.tasklist.page`

源码：[`desktop/pages/tasklist/page.py`](../../desktop/pages/tasklist/page.py)

任务管理页：表格列表 + 导入PDF（先算指纹查重，确认后建任务并落副本/缩略图）。

### 模块常量

| 名称            | 值                                  |
| --------------- | ----------------------------------- |
| HEADER_SUBTITLE | `"导入 PDF 后按四个子任务依次处理"` |

### `class TaskListPage(QWidget, WorkerHost)`

任务管理页：搜索 + 分页的任务列表，支持导入 PDF 与删除。

数据流是单向的：`refresh()` 从 store 读出**全量**行并缓存，
`_render()` 负责「按关键词过滤 → 分页切片 → 填表」。搜索框只触发
`_render()`（不再读盘），所以打字时不会每次都去扫一遍任务目录。

含表格/空状态二选一的内容区。导入刻意分两段：**主线程**只做「算指纹 →
查重 → 确认 → 建任务 → 刷新列表」（毫秒级，用户立刻看到新行）；**后台**
串行做「复制源文件 + 生成整本缩略图」，且等列表画完才开工，期间挂一条
「正在导入」提示条。

#### 方法

| 方法                                      | 说明                                                            |
| ----------------------------------------- | --------------------------------------------------------------- |
| `__init__(store: TaskStore, parent=None)` | 初始化页面：构建 UI、绑定信号并刷新首次列表。                   |
| `refresh() -> None`                       | 刷新任务行：**读盘放后台线程**，读完回主线程渲染。              |
| `focus_task(task_id: str) -> bool`        | 翻到任务所在页并选中它；不在当前过滤结果里则返回 False。        |
| `import_pdf() -> None`                    | 导入 PDF：选文件后后台算指纹并查重确认建任务。                  |
| `shutdown_workers() -> None`              | 关程序前的收尾：先停导入后台队列（复制/缩略图），再走基类线程。 |
| `delete_task(task_id: str) -> None`       | 删除指定任务及其全部中间产物（带确认弹窗）。                    |

##### `__init__(store: TaskStore, parent=None)`

初始化页面：构建 UI、绑定信号并刷新首次列表。

parent 一般为 MainWindow；会创建 store 引用与导入按钮状态占位，
随后调用 refresh 重建表格与空状态。

##### `refresh() -> None`

刷新任务行：**读盘放后台线程**，读完回主线程渲染。

⚠️ 读盘不能占着 UI 线程：这里要遍历全部任务、逐个读它的 runs.json
（任务一多就是几十次文件 IO），同步做会把已经画出来的窗口卡住。行的
组装挪进了 `TaskRowsWorker`，结果走 `_on_rows_ready` 回来渲染。

⚠️ 每次刷新带一个**代际令牌**：连续调用（导入任务后紧跟着又刷新）会让
多个 worker 并发跑，先发的可能后回来，把新数据盖成旧的——只认最后
一次发出的那个令牌，其余结果直接丢弃。

##### `focus_task(task_id: str) -> bool`

翻到任务所在页并选中它；不在当前过滤结果里则返回 False。

⚠️ 分页后不能直接用 `table.select_task`：任务可能不在当前页，
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

## `desktop.services.detect_export`

源码：[`desktop/services/detect_export.py`](../../desktop/services/detect_export.py)

把「每页的框」画回原图并落盘（**纯函数模块，无 Qt**）。

这一块原本只存在于 CLI 那条路上（`functions.detect` 的 `--save`），
独立「检测文本框」模块页要导出同样的标注图时，若在页面里再写一遍，就会
出现两套「按槽位取名/配色」的代码——那正是 :mod:`utils.box_draw` 当初被
抽出来的原因（配色与命名必须处处一致）。所以规则本体在
:func:`utils.box_draw.draw_slots`，本模块只做**遍历 + 落盘**。

⚠️ **重依赖的导入时机**：本模块在**worker 线程**里被 :class:`CallableJob`
调用（见 `desktop/modules/detect/page.py`），而画框/读写图都要 `cv2`。
GUI 主进程**绝不能**在这里 import 到 cv2（实测 `import functions.detect`
会把 cv2 拖进启动路径）——所以 cv2 相关导入全部放进函数内部，让它发生
在子线程里。这也是本模块不 import 任何 Qt 的原因：它必须能被线程安全调用。

输出命名沿用 detect 的口径：`<原文件名去后缀>.png`（全分辨率无损位图，
适合线框标注）。用 `.png` 而不是原图的后缀，是因为标注图是**中间核对
产物**，不该让人误以为能替换原图。

### 模块常量

| 名称          | 值       |
| ------------- | -------- |
| EXPORT_SUFFIX | `".png"` |

### 模块函数

| 函数                                                                                                                                                                       | 说明                                                                 |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `annotated_name(source: Path \| str) -> str`                                                                                                                               | 原图路径 → 标注图**文件名**（`<stem>.png`）。                        |
| `export_annotated(entries: Iterable[tuple], dest: Path \| str, report: Optional[Callable[[str], None]]=None, progress: Optional[Callable[[int, int], None]]=None) -> list` | 把一批 `(图片路径, 槽位)` 画框后写到 `dest`。                        |
| `entries_from_mapping(images: Sequence, boxes: Mapping[str, Sequence]) -> list`                                                                                            | `(图片清单, {页名去后缀: 槽位})` → :func:`export_annotated` 的入参。 |

#### `export_annotated(entries: Iterable[tuple], dest: Path | str, report: Optional[Callable[[str], None]]=None, progress: Optional[Callable[[int, int], None]]=None) -> list`

把一批 `(图片路径, 槽位)` 画框后写到 `dest`。

参数：

- `entries`：`[(图片路径, 槽位), …]`。`槽位` 是
  :mod:`utils.box_geometry` 的槽位表示（半幅 2 槽 / 整幅 1 槽，缺失侧
  `None`）；外观（名字与颜色）由 :func:`utils.box_draw.slot_names_colors`
  按**槽位**给，调用方不传也不该自己拼；
- `dest`：输出目录，**已存在直接写**（覆盖由调用方与用户确认过，见
  模块页的「目录已存在，是否覆盖」）；
- `report`：人读日志回调（`Callable[[str], None]`），每页调一次；
- `progress`：结构化进度回调（`Callable[[done, total], None]`），
  每处理完一页调一次（**含读不出来/画框失败的那页**——它也被走过了）。
  与 `report` 分开是因为两者用途不同、频率与内容也不同（一个给人看、
  一个驱动进度条）；`progress` 是可选的，CLI 那条路不传。

返回：写出的文件路径列表（成功的那几张）。

⚠️ **一页框都没有也照样写**（就是一张没画的原图）：用户导出的是"这批
页面图 + 我认定的框"，漏掉没框的页会让他以为程序跳过了它。
单页失败（文件被删、图片损坏、磁盘满）不中断整批——记进返回值之外的
日志，由调用方决定要不要提示；只有 `cv2`/`numpy` 装不上这种
整批性的问题才会抛出去。

#### `entries_from_mapping(images: Sequence, boxes: Mapping[str, Sequence]) -> list`

`(图片清单, {页名去后缀: 槽位})` → :func:`export_annotated` 的入参。

⚠️ **只取** `boxes` 里有的页：没有框的页不导出，用户要的是"我标了框
的那些页"。（若产品口径要"整批都导出"，改这里一处即可，别改导出循环。）

---

## `desktop.services.font_catalog`

源码：[`desktop/services/font_catalog.py`](../../desktop/services/font_catalog.py)

第四步的字体候选目录：已知候选 + 后台扫一次的系统字体。

## 为什么要这个模块

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

| 名称       | 值                   |
| ---------- | -------------------- |
| AUTO_LABEL | `"自动（仿宋优先）"` |
| AUTO_VALUE | `""`                 |
| \_CATALOG  | `None`               |

### `class FontCatalog(QObject)`

字体候选目录（进程内单例，见 `catalog()`）。

- `choices()`：立刻给出可用列表（静态候选 + 已扫到的），**不阻塞**；
- `start_scan()`：后台扫一次系统字体，完成后发 `scan_finished`，
  界面据此把新字体补进下拉。重复调用直接返回。

#### 方法

| 方法                                 | 说明                                                    |
| ------------------------------------ | ------------------------------------------------------- |
| `__init__(parent=None)`              | —                                                       |
| `choices() -> list[tuple[str, str]]` | 下拉候选 `(中文显示, 参数值)`：自动 + 已知 + 扫描到的。 |
| `is_scanning() -> bool`              | 后台扫描是否在跑（界面可据此显示"扫描中"）。            |
| `start_scan() -> None`               | 启动后台扫描；**只启动一次**。                          |

##### `choices() -> list[tuple[str, str]]`

下拉候选 `(中文显示, 参数值)`：自动 + 已知 + 扫描到的。

⚠️ 按**显示名**去重：扫描结果里常出现与已知候选同名的字体（都叫
"楷体"），留两个同名项对用户没有意义，还容易选错。

##### `start_scan() -> None`

启动后台扫描；**只启动一次**。

调用时机无所谓（进第四步、回到第一步都行）——扫描在后台线程里跑，
主线程不被拖住。

### 模块函数

| 函数                              | 说明                                                            |
| --------------------------------- | --------------------------------------------------------------- |
| `catalog() -> FontCatalog`        | 进程内唯一的字体目录（首次调用时创建，需要已有 QApplication）。 |
| `start_background_scan() -> None` | 在空闲时把系统字体列表补齐（只跑一次，后台线程）。              |

---

## `desktop.services.imposition`

源码：[`desktop/services/imposition.py`](../../desktop/services/imposition.py)

图片拼版的派生与合成规则（纯函数 + PIL，无 Qt 依赖，便于独立测试）。

一句话职责：**把每页的两张源图按版面摆到白底上，落成 `stages/imposition`
里的成品页图**，供第四步「生成 PDF」当整页图片直接用。

三件事在这里定死（别在别处再写一份）：

1. **槽位约定**：一页拼版恒两项，`items[0]` = **右槽**、`items[1]` = **左槽**。
   用户口径「序号排前面的在右侧、序号大的在左侧」——所以按源清单顺序取两张
   （序号小的在前）时，序号小的进右槽。
2. **坐标口径**：`rect` 是**源图像素**，左上原点、x 向右、y 向下；
   `rotation` 是**顺时针角度**（Qt 口径；PIL 侧取负），绕该项 `rect` 的中心。
3. **没有"纸张"**（用户 2026-09-30：「这个拼版不需要设置纸张，只需要背景是白色的
   就行，后续提交的时候根据图片的四个区域合并出一张图片」）：版面只有白底，
   图可以随意移动/拉伸；**产出图 = 所有图外接框的紧裁**（`page_bounds` →
   `compose_page`），所以加多少留白、挪多远，用户自己说了算。

### 模块常量

| 名称           | 值                       |
| -------------- | ------------------------ |
| ITEMS_PER_PAGE | `2`                      |
| FILE_FMT       | `"{:04d}.png"`           |
| \_CN_DIGITS    | `"零一二三四五六七八九"` |
| SOURCE_LEFT    | `"left"`                 |
| SOURCE_RIGHT   | `"right"`                |
| SOURCE_FULL    | `"full"`                 |

### 模块函数

| 函数                                                                 | 说明                                                                   |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `normalize_page(page) -> dict \| None`                               | 把任意来源的一页拼版收敛成合法形状；不可修复时返回 None。              |
| `normalize_doc(doc) -> dict`                                         | 整份文档收敛：`{"enabled", "pages", "removed"}`（永不为 None）。       |
| `cn_page_label(index: int) -> str`                                   | 页序（0 起）→ 中文页码标签：`第一页` / `第十二页` / `第100页`。        |
| `image_size(path) -> tuple[int, int]`                                | 图片像素尺寸（读文件头，不解码整图）；读不到返回 (0, 0)。              |
| `used_source_files(doc: dict) -> set[str]`                           | 已被任何一页拼版引用的源图（用于算「剩余未被选择拼版的图片」）。       |
| `remaining_files(files: list, doc: dict) -> list`                    | 源清单里**还没被任何拼版页用过、也没被删除**的图片（顺序沿用源清单）。 |
| `removed_source_files(doc: dict) -> set[str]`                        | 被用户「删除图片」移出选择范围的源图路径集合（软删除黑名单）。         |
| `excluded_files(files: list, doc: dict) -> list`                     | 源清单里被删除的图（**按源清单顺序**）——给弹窗的「已删除」视图展示。   |
| `page_source_stems(page: dict) -> list[str]`                         | 一页拼版两张源图的名字（去扩展名），按槽位顺序（右、左）。             |
| `default_items(files: list) -> list[dict] \| None`                   | 两张源图 → **默认并排版面**（各按原始像素，不改动用户的图）。          |
| `make_page(sources: list) -> dict \| None`                           | 按**源清单顺序**取两张图造一页拼版版面。                               |
| `single_items(file) -> list[dict] \| None`                           | 一张源图 → **单图版面**（整幅图 / 落单图专用：原始像素、不旋转）。     |
| `make_single_page(file) -> dict \| None`                             | 一张源图**自成一页**（整幅不拼、落单）：版面里只有一项。               |
| `append_item_to_page(items: list[dict], file) -> list[dict] \| None` | 单图页「新增图片」：把 `file` 并进当前页，返回**新的 items**。         |
| `classify_source(path) -> str`                                       | 源图形态：左半幅 / 右半幅 / 整幅（**判据唯一处：文件名后缀**）。       |
| `source_page_number(path) -> int \| None`                            | 源图**页号**：文件名开头的连续数字（`3-r` → 3、`004-l` → 4）。         |
| `auto_impose_pages(files: list) -> list[dict]`                       | 自动拼版（用户 2026-09-30 规则，**唯一实现**）：                       |
| `page_bounds(page: dict) -> tuple[float, float, float, float]`       | 一页的**内容范围**：所有图外接框的并集（用户说的「图片的四个区域」）。 |
| `compose_page(page: dict)`                                           | 一页拼版 → PIL RGB 图：**白底 + 所有图外接框的紧裁**。                 |
| `compose_doc(doc: dict, dest_dir, report=None) -> list[Path]`        | 把整份拼版文档落成 `dest_dir/0001.png` …（列表顺序即页序）。           |

#### `normalize_page(page) -> dict | None`

把任意来源的一页拼版收敛成合法形状；不可修复时返回 None。

⚠️ 校验必须严：`rect` 会直接喂给合成函数当落点，坏值（缺字段、0 宽、
非数字）会让合成抛异常或产出空图，而这份文档在用户的文档目录里、可被
外部编辑写坏。

⚠️ 老版本存过 `"sheet": [w, h]`（有纸张的时代）。现在**忽略它**：
版面以两张图为准，纸张已经不存在了，读老任务照样能合成。

#### `normalize_doc(doc) -> dict`

整份文档收敛：`{"enabled", "pages", "removed"}`（永不为 None）。

`removed` 是**黑名单**（用户在「选择拼版」弹窗里删掉的图，软删除——
文件不动，只是不再进入候选范围）。存字符串路径列表，去重保序；
读老任务没有这个键时为空列表。

#### `cn_page_label(index: int) -> str`

页序（0 起）→ 中文页码标签：`第一页` / `第十二页` / `第100页`。

只覆盖 1~99 的中文写法（古籍拼版页数够用），超出退回阿拉伯数字——
这里只是**界面文案**，不参与任何匹配，宁可难看也不要写错数字。

#### `remaining_files(files: list, doc: dict) -> list`

源清单里**还没被任何拼版页用过、也没被删除**的图片（顺序沿用源清单）。

「删除」是黑名单（`removed`，弹窗里用户主动移出选择范围的图），
不是删文件——恢复后重新回到候选范围。

#### `default_items(files: list) -> list[dict] | None`

两张源图 → **默认并排版面**（各按原始像素，不改动用户的图）。

`files` 顺序即槽位顺序 `[右槽, 左槽]`：左槽贴 x=0，右槽紧挨在它右边，
两者顶部对齐。古籍一页的两半通常同尺寸，摆出来就是标准对开。

尺寸读不到 / 少于两张时返回 None（调用方负责提示）。

#### `make_page(sources: list) -> dict | None`

按**源清单顺序**取两张图造一页拼版版面。

`sources` 顺序即源清单顺序（序号小在前）；本函数把 `sources[0]`
放进**右槽**、`sources[1]` 放进**左槽**——这就是用户的口径
「序号排前面的在右侧，序号大的在左侧」。版面本身见 `default_items`。

#### `single_items(file) -> list[dict] | None`

一张源图 → **单图版面**（整幅图 / 落单图专用：原始像素、不旋转）。

尺寸读不到返回 None（调用方负责跳过 / 提示）。

#### `append_item_to_page(items: list[dict], file) -> list[dict] | None`

单图页「新增图片」：把 `file` 并进当前页，返回**新的 items**。

槽位与摆放口径（用户 2026-09-30：单图页可以再导一张图拼成对页）：

- 原图是**左半幅**（文件名 `-l`/`_l` 结尾）→ 新图进**右槽**
  （`items[0]`），摆在原图**右边**；
- 其余（右半幅 / 整幅 / 无后缀）→ 新图进**左槽**（`items[1]`），
  摆在原图**左边**；
- 新图按**原始像素**进版面、顶边与原图对齐、紧贴原图边缘（用户可再
  拖动/缩放）；原图的版面（位置/大小/旋转）**原样保留**，不重排。

`items` 不是恰好一项（只有单图页能加图）或尺寸读不到时返回 None，
调用方负责提示。

#### `classify_source(path) -> str`

源图形态：左半幅 / 右半幅 / 整幅（**判据唯一处：文件名后缀**）。

自动拼版只能靠文件名认图——拼版侧读不到检测框，而第三步的落盘口径是
半幅页 `<页号>-l` / `<页号>-r`、整幅页 `<页号>`（见
`functions/text_region._area1_outputs` 与单图输出）。

#### `source_page_number(path) -> int | None`

源图**页号**：文件名开头的连续数字（`3-r` → 3、`004-l` → 4）。

「不连续的图片不可以合并在一页」的判据。文件名不带数字前缀的图
（如 `cover`）返回 None——永不参与配对，只能单独成页。

#### `auto_impose_pages(files: list) -> list[dict]`

自动拼版（用户 2026-09-30 规则，**唯一实现**）：

1. **默认两张半栏拼一页**：配对必须是「前一个左半幅 + 当前右半幅」
   （序号在前的进右槽，与手动配对口径一致）。例：`3-r, 3-l, 4-r,
4-l, 5-r` 从 `3-l` 起 → `(3-l, 4-r)、(4-l, 5-r)`；从 `3-r`
   起 → `[3-r]、(3-l, 4-r)、(4-l, 5-r)`（首位右半幅前面没有左半幅，
   单独一页）；
2. **页号必须连续**：不连续的图片不可以合并在一页——`3-l` 之后隔着
   已用掉的 4 直接来 `5-r`，则 `3-l` 单独一页、`5-r` 重新开始；
   文件名无数字前缀的图永不配对；
3. **整幅(fullcontent)标注的图单独一页**，不与任何图配对；等配对的
   上一张因此落单、也单独一页；整幅之后拼版重新开始；末尾落单的
   左半幅同样单独一页。

遍历按源清单顺序（`pdf_custom_sort_key`：同页号 r 在前），产出的
页清单顺序即 PDF 页序。尺寸读不到的图跳过（不产出残页）。

#### `page_bounds(page: dict) -> tuple[float, float, float, float]`

一页的**内容范围**：所有图外接框的并集（用户说的「图片的四个区域」）。

没有纸张概念之后，产出图就是这块范围的紧裁——所以用户把图挪远/拉大，
产出就跟着变大，不会被裁掉。

#### `compose_page(page: dict)`

一页拼版 → PIL RGB 图：**白底 + 所有图外接框的紧裁**。

⚠️ 旋转方向必须与画布一致：`rotation` 按 **Qt 顺时针**口径存，
PIL `rotate` 是**逆时针**，所以这里取负。两边口径写反的话，画布上
转 90°、落盘却反向 90°，用户会看到"生成的 PDF 和图里不一样"。

留白处为白：去底图的透明在此压到白底上（与 `functions.print` 加载图片
时的压平规则一致）。

#### `compose_doc(doc: dict, dest_dir, report=None) -> list[Path]`

把整份拼版文档落成 `dest_dir/0001.png` …（列表顺序即页序）。

返回写出的文件列表（顺序与页序一致）。**多余的旧文件会被清掉**——否则
用户删掉一页后，上一轮多出来的 `0007.png` 还会被第四步当成一页打进 PDF。
只清理本函数自己命名形态的文件（`\d{4}.png`），不碰目录里的别的东西。

单页合成失败时跳过该页（不写文件），其余页照常。任务目录不存在时
（任务被删）直接返回空列表。

⚠️ 整轮**持 :data:`_COMPOSE_LOCK`**：后台防抖合成与生成 PDF 前的同步合成
会打到同一个目录，不串行化就会出现"一个线程在写、另一个在清"——详见该锁
的注释。

`report`：可选的进度回调 `(done, total)`，每处理完一页调一次（**含
失败的那页**——它也被处理过了，只是不写文件）。独立拼图页靠它显示进度
（任务流程里后台防抖那条路不传，用户不需要看）。
⚠️ 回调在 :data:`_COMPOSE_LOCK` **内**调用，所以它只许发信号、不许做
可能重入本模块的事（例如再调一次 `compose_doc` 会死锁）。

---

## `desktop.services.print_plan`

源码：[`desktop/services/print_plan.py`](../../desktop/services/print_plan.py)

打印/提取条目的派生规则（纯函数，无 Qt 依赖，便于独立测试）。

这里的规则是 GUI 各阶段共享的「单一事实来源」：

- 提取缺页 → 续跑 extract 时的 pages 参数；
- 提交条目 → rembg「提交本次任务」的最终图片派生；
- 待打印列表 → 第四步左侧列表的默认排序与持久化合并。

⚠️ 第四步**没有**「按当前参数临时合成」的规则（2026-10-01 用户口径：
去底色那一步必须提交才能传给下一步）：print 只排版「提交本次任务」落盘的
成品图，见 `taskdetail.submit.SubmitMixin._build_print_effects`。

### 模块函数

| 函数                                                                                                         | 说明                                                                          |
| ------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------- |
| `missing_extract_pages_spec(output_dir: Path, total: int) -> str \| None`                                    | 提取输出目录中缺失的页码，压缩为 CLI pages 参数（如 "3,7-9"）。               |
| `plan_rembg_submit_entries(manifest_paths: list[Path], result_path_for, boxes_for, area: int) -> list[dict]` | 预览结果 + 检测框 + area/border → 最终图片条目。                              |
| `entry_to_effect_spec(entry: dict, border) -> dict`                                                          | 提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。 |
| `drop_foreign_stage_pages(pages: list[dict] \| None, source_dir: Path, stages_root: Path) -> list[dict]`     | 从待打印清单里剔除「属于本任务**别的阶段**产物」的条目。                      |
| `plan_print_entries(rembg_files: list[Path], doc: dict \| None) -> tuple[list[dict], dict]`                  | 第四步待打印图片列表的规划。                                                  |

#### `missing_extract_pages_spec(output_dir: Path, total: int) -> str | None`

提取输出目录中缺失的页码，压缩为 CLI pages 参数（如 "3,7-9"）。

页文件名以数字开头（0001.jpg / 0002.jpg …）。无缺失或 total 为 0
时返回 None（无需续跑）。

#### `plan_rembg_submit_entries(manifest_paths: list[Path], result_path_for, boxes_for, area: int) -> list[dict]`

预览结果 + 检测框 + area/border → 最终图片条目。

## 参数

manifest_paths : 页面清单路径（stages/extract 内的页图片）
result_path_for : (stem) -> Path|None，某页对应的「生成预览」去底结果
boxes_for : (path_str) -> list，某页的检测框 [左框, 右框]
area : 区域模式（1=左右分页，2/3=并集/对称画布）

派生规则与 rembg 预览条目、print 待打印列表完全一致：

- area=1 双框：拆 <页>-r / <页>-l 两条（古籍阅读顺序 r 在前）；
- area=1 半幅漏检一侧：单条也保留左右身份（<页>-l / <页>-r，按缺失侧
  所在槽位判定）——否则产物叫 <页>.png，第四步拼版按文件名后缀判
  左右半幅时会把这页误当整幅（用户 2026-10-01 报）；
- area=2/3 双框：合成一条（不再分栏）；
- 单框：area=2/3 走对称画布（整页形态，不带后缀），其余按普通框；
- 无框：整页预览图透传。
  最终按 CLI natural sort 排序（同页 r 在 l 前）。

⚠️ `parea` 是**原始 area**（不是"降级"后的合成 area），`boxes` 是
**原始检测框**（不是并集后的单框）——两者必须原样交给
`compose_region_output`。原因见 `entry_to_effect_spec`：并集框 +
area=1 与「双框 + area=2/3」在 border 为空时**不等价**，曾导致第三步
预览是整页、而提交产物与 PDF 被紧裁（用户报的「PDF 成了 area=1 效果」）。

#### `entry_to_effect_spec(entry: dict, border) -> dict`

提交条目 → worker 效果合成规格（run_print_stage/run_rembg_submit_stage 用）。

⚠️ 必须把**原始检测框 + 原始 area** 交给 `compose_region_output`，
不能擅自"化简"成并集框 + area=1。`utils.box_geometry.build_output_layout`
在 border 为空（padding=None）时两条分支并不等价：

- area=2/3（含多框）→ `full_page=True`：整页画布，各框**写回原位置**；
- area=1 → 紧裁成「框 + border」的小画布。

此前双框 area=2/3 被记成"并集框 + parea=1"，于是第三步预览（用原始框

- 原始 area）显示整页、提交产物与 PDF 却是紧裁——用户报的「第三步 area=2、
  预览也是 area=2，生成的 PDF 却是 area=1 的效果」就是这么来的（紧裁观感
  与 area=1 的半页裁剪一致）。

`full` 原样透传给合成层：整幅(fullcontent)页的框**原样下传**——
area=4 保留整页内容、area 1/2/3 统一按合并语义走单框布局（不拆
`-l`/`-r`、不镜像）——见 `desktop.workers.preview_worker.region_canvas_specs`。

#### `drop_foreign_stage_pages(pages: list[dict] | None, source_dir: Path, stages_root: Path) -> list[dict]`

从待打印清单里剔除「属于本任务**别的阶段**产物」的条目。

⚠️ 为什么必须剔（2026-09-30 引入「图片拼版」时暴露）：`plan_print_entries`
的规则是「不在当前来源目录里的条目 = 用户手动插入的外部图片，原样保留」。
可第四步的来源会**切换**——拼版生效时用 `stages/imposition`，否则用
`stages/rembg`。切过去之后，原先那一批还留在 `print.json` 里、又不在
新来源目录下，就会被当成"用户插入的图"**追加到列表末尾**：生成 PDF 时
新旧两套整页全打进去（实测 2 页拼版 + 4 页去底色 = 6 页）。

判据写死在"路径是否落在本任务的 `stages/` 下"：同任务其它阶段的产物
永远是**上一轮来源**的残留，绝不可能是用户从磁盘上手动挑来的外部图片。
真正的外部图片（桌面/下载目录…）一律保留。

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

## 与「生成预览」的分工

- **「生成预览」**：全量正式产物，写 `stages/rembgpreview`，会被「提交本次
  任务」读取。参数一变它就过期（见 `services/submit_state` 的 PREVIEW_STALE）。
- **本模块**：只算用户当前看着的**那一页**，落到系统临时目录，仅供预览区显示。
  **绝不碰 rembgpreview** —— 否则各页是不同参数下算出来的，提交时新旧混用，
  成品会不自洽。

计算入口统一走 `utils.rembg_page`，与 CLI 产物逐像素同源（`functions.rembg`
用的是同一个函数）。

### 模块函数

| 函数                                                                    | 说明                                                          |
| ----------------------------------------------------------------------- | ------------------------------------------------------------- |
| `live_dir(task_id: str) -> Path`                                        | 该任务的实时预览暂存目录（系统临时目录下，按 task_id 隔离）。 |
| `reset(task_id: str) -> None`                                           | 清空该任务的实时暂存（参数回到「生成预览」状态时调用）。      |
| `render_page(image_path: str, args: dict, out_dir: str \| Path) -> str` | 对单页执行去底色并写入 `out_dir`，返回结果文件路径。          |

#### `render_page(image_path: str, args: dict, out_dir: str | Path) -> str`

对单页执行去底色并写入 `out_dir`，返回结果文件路径。

⚠️ 重依赖（numpy / PIL，以及 `utils.image_utils` 背后的 cv2）在这里
**延迟导入**：GUI 主进程只有在用户真的动了参数时才付出这点加载成本，
启动路径不受影响。

PNG 用 `compress_level=1`：这是**临时预览**，编码速度比压缩率重要
（正式产物走 `functions.rembg`，那里仍是 level=9）。

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

另有一类**不是**时间戳的过期：第四步「生成 PDF」的取图来源可以整体换掉
（勾上「图片拼版」后从去底色产物改成拼版产物）。换来源之后磁盘上那份 PDF
就属于旧数据了——由 :func:`print_source_switched` 判定（比对运行记录里
记下的来源，而不是时间）。

### 模块常量

| 名称                  | 值    |
| --------------------- | ----- |
| TIMESTAMP_TOLERANCE_S | `2.0` |

### 模块函数

| 函数                                                             | 说明                                                            |
| ---------------------------------------------------------------- | --------------------------------------------------------------- |
| `latest_success(records) -> dict \| None`                        | 一组运行记录里最近一次**成功**的那条（按 finished_at 取最大）。 |
| `stale_upstream(runs: dict) -> dict[str, dict]`                  | runs（`{阶段: [记录, ...]}`）→ 过期判定 `{下游阶段: 详情}`。    |
| `print_source_switched(runs: dict, current_source: str) -> bool` | 已生成的 PDF 是不是在**换了取图来源之后**生成的（旧数据）。     |

#### `latest_success(records) -> dict | None`

一组运行记录里最近一次**成功**的那条（按 finished_at 取最大）。

失败/中断的跑动不算数：它们没产出可用于比对的产物。

#### `stale_upstream(runs: dict) -> dict[str, dict]`

runs（`{阶段: [记录, ...]}`）→ 过期判定 `{下游阶段: 详情}`。

详情：`{"stage": 更新了的上游阶段, "upstream_at": ts, "downstream_at": ts}`。
下游**从未成功过**时不判过期——那种情况界面本来就在说"未执行"，再叠一句
"已过期"只会让人困惑。

#### `print_source_switched(runs: dict, current_source: str) -> bool`

已生成的 PDF 是不是在**换了取图来源之后**生成的（旧数据）。

用户 2026-10-03 的口径：

> 任务详情里面如果启用了拼板，则最后一步生成 pdf 的数据来源就是拼板，
> 如果之前流程里面没有启用拼板，但是生成了 pdf，此时再次启用拼板，
> 则生成 PDF 的数据要来源于拼板，旧的数据不显示

所以第四步要能回答"磁盘上那份 PDF 还是当前来源下的产物吗"——不能
变了来源还让用户下载/预览上一轮的去底色 PDF，那正是"旧数据"。

判据：最近一次**成功**的 print 运行记录里存了当时的取图来源
（`parameters["source_stage"]`，见 runner 注入），与当前来源不同即过期。

- 下游从未成功过 → 不判过期（界面本来就说"未执行"）；
- 老任务的记录里没有 `source_stage`（本字段引入前生成的）→ **不判过期**，
  宁可少提示也不凭空说用户的 PDF 有问题。

---

## `desktop.services.submit_state`

源码：[`desktop/services/submit_state.py`](../../desktop/services/submit_state.py)

rembg「提交本次任务」按钮的版本状态机（纯函数）。

### 模块常量

| 名称          | 值                |
| ------------- | ----------------- |
| PREVIEW_STALE | `"preview_stale"` |
| NEW_VERSION   | `"new_version"`   |
| UP_TO_DATE    | `"up_to_date"`    |
| NO_PREVIEW    | `"no_preview"`    |

### 模块函数

| 函数                                                                                                                           | 说明               |
| ------------------------------------------------------------------------------------------------------------------------------ | ------------------ |
| `rembg_submit_version_state(preview_run: dict \| None, submit_run: dict \| None, panel_args: dict, preview_param_keys) -> str` | 提交按钮版本状态： |

#### `rembg_submit_version_state(preview_run: dict | None, submit_run: dict | None, panel_args: dict, preview_param_keys) -> str`

提交按钮版本状态：

- no_preview ：从未成功生成预览（或最近一次失败/中断）→ 禁止提交；
- preview_stale：面板去底参数相对最近一次成功预览已修改，
  磁盘上的预览图不是最新 → 建议重新生成预览；
- new_version ：预览有新版本（重新生成过、或 area/border 已改），
  最终图片落后于预览 → 提示需要提交；
- up_to_date ：最终图片已是最新预览版本。

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
  - `SetForegroundWindow`。不做跨进程消息通道，够用且零依赖。

⚠️ 仅 win32 生效；其它平台直接放行（本项目只在 Windows 打包发行）。

### 模块常量

| 名称                   | 值                            |
| ---------------------- | ----------------------------- |
| \_MUTEX_PREFIX         | `"Local\GujiZhiZuo-Desktop-"` |
| \_ERROR_ALREADY_EXISTS | `183`                         |
| \_SW_RESTORE           | `9`                           |
| \_SW_SHOW              | `5`                           |

### 模块函数

| 函数                                           | 说明                                                                 |
| ---------------------------------------------- | -------------------------------------------------------------------- |
| `mutex_name(identity: str) -> str`             | 由构建身份推出互斥体名。                                             |
| `acquire(identity: str) -> bool`               | 尝试持有本构建的单例互斥体。False = 已有本构建实例（调用方应退出）。 |
| `activate_existing_window(title: str) -> bool` | 把已有实例的窗口恢复并带到前台。找不到（返回 False）也不影响退出。   |

#### `mutex_name(identity: str) -> str`

由构建身份推出互斥体名。

identity 用 **desktop 包目录**（`desktop.utils.files.package_dir()`）：
源码是 `D:\...\desktop`，打包是 `...\guji\_internal\desktop`——同一构建
稳定不变，两个构建互不相同。

#### `activate_existing_window(title: str) -> bool`

把已有实例的窗口恢复并带到前台。找不到（返回 False）也不影响退出。

⚠️ **只在窗口被最小化时才用 SW_RESTORE**。`SW_RESTORE` 的语义是"把最小化
**或最大化**的窗口还原到原始尺寸"，主窗口默认就是最大化（见 app.py 的
WINDOW_START_MAXIMIZED），一律 SW_RESTORE 会让"再点一次快捷方式"变成
"把窗口缩回去"——用户会以为程序自己变小了。非最小化一律 SW_SHOW。

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

| 函数                                    | 说明                                                                               |
| --------------------------------------- | ---------------------------------------------------------------------------------- |
| `run_detect(config: dict) -> int`       | 检测单张图片的内容框（半幅左右 / 整幅），返回像素坐标（重依赖由常驻服务承担）。    |
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
   把**人读日志**转发为 `{"type": "log"}` 事件。它不再做正则解析。

历史包袱说明：以前没有结构化通道，所有信号都靠 ProgressStream 跑正则从中文
提示里捞（`进度: d/t`、`图片总数: n`、`[boxes] …`、`[imgsize] …`）。那种
「文案即契约」的耦合已移除；`[boxes]`/`[imgsize]` 两行文本仍在 functions 侧
兼容保留一个版本，便于对照验证，但本文件不再解析它们。

### `class JsonLinesReporter`

把功能模块的结构化汇报写成 JSON Lines（worker → GUI 的正式协议）。

context 提供 task_id/stage/run_id，附加到每条事件上供 GUI 归位到具体任务。

#### 方法

| 方法                                       | 说明           |
| ------------------------------------------ | -------------- |
| `__init__(context: dict, stream=None)`     | —              |
| `progress(done: int, total: int) -> None`  | —              |
| `event(name: str, **payload: Any) -> None` | 转发具名事件。 |
| `log(message: str) -> None`                | —              |

##### `event(name: str, **payload: Any) -> None`

转发具名事件。

`progress_total`（引擎先给出总数、尚无完成量）在协议上仍是一条
progress 事件：GUI 只关心 total 用来设进度条 range，因此这里
统一映射为 done=0 的 progress，避免新增一种 GUI 不认识的事件类型。

⚠️ 这条规则与 :class:`core.reporter.CallbackReporter`（进程内那条路）
**必须同时存在且一致**——两处曾分叉过一次，导致独立功能页永远拿不到
上限。判定用的是同一个常量 :data:`~core.reporter.PROGRESS_TOTAL_EVENT`。

### `class ProgressStream(io.TextIOBase)`

拦截功能模块的 print 输出，原样转发为人读日志事件。

⚠️ 这里**刻意不做任何解析**。以前它跑四条正则从中文提示里捞进度与结构化
数据，属于「文案即契约」——改一句提示就静默断掉 GUI 进度条。现在信号走
`JsonLinesReporter`，本类只负责让日志视图不漏行（含第三方库的 print）。

#### 方法

| 方法                                   | 说明                                                                                |
| -------------------------------------- | ----------------------------------------------------------------------------------- |
| `__init__(real_stdout, context: dict)` | real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到               |
| `writable() -> bool`                   | 恒为 True：本流始终接受写入。                                                       |
| `write(text: str) -> int`              | 按换行或回车切分输出边界，逐行转发日志；返回写入字符数（满足 io.TextIOBase 约定）。 |
| `flush() -> None`                      | 空实现（行缓冲已在 write 中处理，无需真正刷盘）。                                   |

##### `__init__(real_stdout, context: dict)`

real_stdout 为真实输出流；context 提供 task_id/stage/run_id，会附加到
本流发出的每条事件上，供 GUI 归位到具体任务与阶段。

### 模块函数

| 函数                                       | 说明                                          |
| ------------------------------------------ | --------------------------------------------- |
| `emit(payload: dict, stream=None) -> None` | 向 GUI 输出一条 JSON Lines 事件（线程安全）。 |

#### `emit(payload: dict, stream=None) -> None`

向 GUI 输出一条 JSON Lines 事件（线程安全）。

stream 缺省写真实 stdout；窗口化打包运行时 sys.stdout 可能为 None，
此时由 \_real_stdout() 兜底到文件描述符 1。

⚠️ 序列化与写入必须在同一把锁里：先序列化再抢锁会让两个线程的
payload 交替入队、输出的仍是交错行。

---

## `desktop.stages.generic_stage`

源码：[`desktop/stages/generic_stage.py`](../../desktop/stages/generic_stage.py)

通用阶段执行器：CLI 功能阶段（run_stage）+ PDF 渲染阶段（run_extract_stage）。

### 模块函数

| 函数                                     | 说明                                                                    |
| ---------------------------------------- | ----------------------------------------------------------------------- |
| `run_stage(config: dict) -> int`         | 在子进程中执行一个 CLI 功能阶段，返回进程退出码（0/130/1）。            |
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

页序完全由 `args["files"]`（GUI 第四步列表顺序）决定，不再依赖文件名
排序——因此不再需要把顺序「烧」进文件名的 workset 目录。合成结果写入
一次性临时目录，交给 print 时同时给出有序清单，执行结束即随临时目录删除。

### 模块常量

| 名称                | 值                     |
| ------------------- | ---------------------- |
| \_STAGING_ROOT_NAME | `"guji-print-staging"` |
| \_OWNER_FILE        | `"owner.pid"`          |

### 模块函数

| 函数                                                      | 说明                                                               |
| --------------------------------------------------------- | ------------------------------------------------------------------ |
| `staging_root() -> Path`                                  | 所有效果图暂存目录的固定根。                                       |
| `sweep_orphan_staging(exclude: Path \| None=None) -> int` | 删掉「属主进程已死」的暂存目录，返回删除个数。                     |
| `run_print_stage(config: dict) -> int`                    | print 阶段：把 rembg 结果按 area/border 合成为效果图，再生成 PDF。 |

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

合成结果按**列表顺序**以 `0001.png` 命名写入临时暂存目录，并把
`args["files"]` 设为这份有序清单——CLI 侧不再读目录、不再解析
文件名，页序与第四步列表严格一致（拖拽重排无需任何物理文件改动）。

---

## `desktop.stages.rembg_stage`

源码：[`desktop/stages/rembg_stage.py`](../../desktop/stages/rembg_stage.py)

rembg_submit 阶段执行器：把「生成预览」产出的整页去底图合成为最终交付图片。

产物一律是**白底透明**的 PNG（规则与编码形态的唯一实现在
`utils/transparent_png.py`）：用户 2026-09-30 定的「无论 type 是什么，
提交产物都把黑字白底里的白底改成透明」。

### 模块函数

| 函数                                          | 说明                                                                |
| --------------------------------------------- | ------------------------------------------------------------------- |
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

## `desktop.steps.control`

源码：[`desktop/steps/control.py`](../../desktop/steps/control.py)

共用步骤控制组件：把「选源 → 调参数 → 执行/中断」这条链装成一块控件。

这一块就是三个模块页右栏的**全部内容**：一块**大输入区**（拖文件/拖文件夹/
点选，见 :class:`~desktop.steps.source_zone.SourceZone`）、一个输出目录按钮、
一个参数面板（来自 :class:`StepSpec`）、执行与中断按钮。
三个模块各持**自己的一份实例**（各自的 :class:`StepKernel`、各自的源/输出），
因此**互不影响**——没有共享的可变状态，一个模块在跑不会让另一个模块的按钮变灰。

对外 API 与用户口径一一对应（"入口文件目录，输出文件目录"）：

- :meth:`source` / :meth:`set_source` —— 入口（文件或目录）；
- :meth:`output` / :meth:`set_output` —— 出口目录；
- :meth:`args` —— 参数面板收集到的参数；
- :meth:`run` / :meth:`cancel` / :meth:`busy` / :meth:`shutdown`。

「用户给的路径 → 一个源」的归一化**不在这里**：它住在
:meth:`desktop.steps.spec.StepSpec.resolve_source`（纯逻辑、可单测），
本类只负责把结果画出来并发出 `source_changed`。

⚠️ 本组件**只发信号、不弹 InfoBar**：提示语由宿主页面（模块页有页头状态行与
日志区）决定怎么呈现。这样同一块控件既能放进模块页，也能放进将来的批处理界面。

### `class StepControl(QWidget)`

一个步骤的控制区（无卡片外壳，宿主自己包 :class:`Card`）。

信号：

- `status(text, kind)`：状态文案 + 语义（info/success/warning/error）；
- `progress(done, total)`：执行进度（`total=0` 表示未知）。
  ⚠️ 本组件**自己**也消费它来驱动 `progress_row`，信号照常往外发——
  宿主页面要另做呈现（例如拼图页有两条执行线）时仍接得到；
- `finished(output)`：成功，参数是输出目录；
- `failed(message)`：失败原因；
- `log(text)`：一行人读日志；
- `source_changed(path)`：源变了（宿主可据此更新副标题/预览）；
- `running_changed(bool)`：开始/结束执行（宿主可据此禁用别的入口）；
- `event(name, payload)`：步骤私有的结构化事件（如 `page_boxes`），
  给"产物不是文件"的步骤用（detect 报框坐标）。

#### 方法

| 方法                                                                             | 说明                                                                    |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `__init__(spec: StepSpec, job=None, zone: SourceZone \| None=None, parent=None)` | 按 `spec` 组装控件；`job` 省略时按 `spec.command` 造命令 job。          |
| `source() -> Path \| None`                                                       | 当前源（文件或目录）；未选为 `None`。                                   |
| `set_source(path: Path \| str \| None) -> None`                                  | 设置源；未手动选过输出时，按 :meth:`StepSpec.default_output` 重推输出。 |
| `output() -> Path \| None`                                                       | 当前输出目录；未定则为 `None`（执行时按默认规则补）。                   |
| `set_output(path: Path \| str \| None) -> None`                                  | 显式设置输出目录（会被记为"手动选择"，不再自动覆盖）。                  |
| `args() -> dict`                                                                 | 参数面板收集到的参数（面板为 `None` 时是空字典）。                      |
| `zone_detail(source: Path \| None=None) -> str`                                  | 大输入区第二行的说明文案（宿主想知道"显示里写了什么"时用）。            |
| `run() -> None`                                                                  | 校验前置条件并起后台执行。校验不通过只发 `status`，不弹窗。             |
| `cancel() -> None`                                                               | 请求中止当前执行。                                                      |
| `busy() -> bool`                                                                 | 是否正在执行。                                                          |
| `shutdown(timeout_ms: int=1500) -> None`                                         | 收尾执行线程（页面关闭时必须调）。                                      |

##### `__init__(spec: StepSpec, job=None, zone: SourceZone | None=None, parent=None)`

按 `spec` 组装控件；`job` 省略时按 `spec.command` 造命令 job。

`zone`：宿主已经建好的**大输入区**。模块页把它横跨整幅放在页头下方
（用户要的"页面上有一个大的输入框"），这时候传进来，本组件只接线、
不重复摆放；不传就自己建一个摆在自己顶部（给"整块塞进卡片"的用法）。

##### `set_source(path: Path | str | None) -> None`

设置源；未手动选过输出时，按 :meth:`StepSpec.default_output` 重推输出。

同时把源画进大输入区（已选态）——宿主（模块页 / 拼版页）也走这里，
保证"输入的显示"与"真正的源"永远一致，只有一份事实。

##### `cancel() -> None`

请求中止当前执行。

⚠️ 进度条**不清零也不前进**：能不能真的停下取决于功能层是否检查标记
（见 :meth:`StepKernel.cancel`），此刻说"0%"或"100%"都是骗人，就让
它停在最后一格。真正收尾时 :meth:`_on_failed` / :meth:`_on_finished`
才会改它。

---

## `desktop.steps.kernel`

源码：[`desktop/steps/kernel.py`](../../desktop/steps/kernel.py)

执行内核：把「输入路径 + 输出路径 + 参数」跑成一个后台任务。

用户口径（2026-10-02）：

> 公共组件定义好 API 就行，比如入口文件目录，输出文件目录等；
> 新的功能可以批量处理也可以处理一张图片。

所以这里的 API 只有三样东西——**源（文件或目录）、输出目录、参数**：

    kernel = StepKernel(command_job("rembg"))
    kernel.progress.connect(on_progress)
    kernel.finished.connect(on_finished)   # 参数 = 输出目录
    kernel.failed.connect(on_failed)
    kernel.run(StepRequest(source=src, dest=dst, args=panel.get_args()))

- **单张 / 批量**不是两套代码：源是文件就是单张、是目录就是批量，判断在
  功能层（`FunctionBase.is_file`）里，本内核只负责把路径递下去；
- **与流程无关**：内核不知道自己是第几步、上游是谁——任务管理的那套顺序
  编排留在 `desktop/pages/taskdetail`，本层只做"跑一步"；
- **不卡界面**：任务跑在 QThread 里，进度/结果经 Qt 信号排队回主线程。

⚠️ 这里跑的是**进程内**线程（与任务流程的子进程隔离不同）。模块页要的是
"点一下就开始、看得见进度"，进程内更轻；崩溃隔离由任务流程那条
`desktop.steps.process.StageProcess` 负责——两条路各取所需，共用同一份
:class:`StepSpec` 与参数面板。

### `class StepRequest`

一次处理请求：**入口 + 出口 + 参数**（内核唯一认识的输入形状）。

- `source`：源文件或源目录；`None` 表示这一步不需要源（罕见）；
- `dest`：输出目录（或输出文件）；`None` 表示由功能层自行推导；
- `args`：参数面板 `get_args()` 的结果（不含 input/output）。

### `class StepJob`

一次处理任务：给定请求与进度回调，跑完返回输出路径。

子类只需实现 :meth:`__call__`；抛出的任何异常都会被内核转成 `failed`
信号（调用方不必自己 try）。

### `class CommandJob(StepJob)`

把 `functions.get_function(command)` 包成一个 job。

⚠️ 输出目录**精确生效**：显式把 `function.outpath` 设成 `request.dest`。
不设的话，rembg / cropremove 这类命令会在用户给的目录后再追加一层自己的
子目录（`resolve_final_output_dir` 的规则），产物落到 `dest/rembg/`，
调用方按 `dest/<name>.png` 找结果就永远找不到（模块页改版前的实测坑）。
显式覆盖后，"输出目录"就真的等于用户选的那个目录——这正是本层对外的承诺。

仍然有命令会**无视**这个覆盖（自己在 `dest` 下面再建目录），extract 就是
一个：它的布局由 `utils.pdf_extract.run_on_input_directory` 决定，是
`<dest>/<PDF名>/<子目录>/`。这类"命令自己的目录习惯"由 `after` 钩子
（见 :func:`extract_job`）擦屁股，而不是让每个调用方各自去认路。

还有一类相反的情况：`artifact_is_file=True` 的命令（`print`）**不能**被
覆盖——它的 `--output` 是目录、`outpath` 是目录下的**文件**
（`<输出>/output.pdf`），覆盖成目录会拿目录当文件路径写。这种命令由它自己
算 outpath，内核只负责把真正的产物路径回传。

#### 方法

| 方法                                                                                                      | 说明 |
| --------------------------------------------------------------------------------------------------------- | ---- |
| `__init__(command: str, after: Callable[[StepRequest], None] \| None=None, artifact_is_file: bool=False)` | —    |

### `class CallableJob(StepJob)`

把任意纯函数包成一个 job（拼版走这条路：`compose_doc` 不是 CLI 命令）。

`fn(request, report) -> str | None`：与 :meth:`StepJob.__call__` 同形。

#### 方法

| 方法                                                         | 说明 |
| ------------------------------------------------------------ | ---- |
| `__init__(fn: Callable[[StepRequest, Report], str \| None])` | —    |

### `class StepKernel(QObject)`

一个步骤的执行内核：跑一次 :class:`StepJob`，信号回报进度与结果。

生命周期：`run()` → `started` → 若干 `progress`/`log` →
`finished` 或 `failed`。同一时刻只允许一次运行（`busy()` 为真时
`run()` 直接返回 False，调用方据此提示"上一次还没结束"）。

#### 方法

| 方法                                          | 说明                                                             |
| --------------------------------------------- | ---------------------------------------------------------------- |
| `__init__(job: StepJob \| None, parent=None)` | —                                                                |
| `run(request: StepRequest) -> bool`           | 起后台线程跑一次；已在跑则返回 False（调用方应提示并放弃本次）。 |
| `cancel() -> None`                            | 请求中止（尽力而为；能否立刻停下取决于功能层是否检查标记）。     |
| `busy() -> bool`                              | 是否正在运行（线程还在跑）。                                     |
| `shutdown(timeout_ms: int=1500) -> None`      | 收尾：请求中止并等待线程结束（页面关闭/退出时必须调）。          |

### 模块函数

| 函数                                                                            | 说明                                                                  |
| ------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `command_job(command: str) -> CommandJob`                                       | 按命令名造一个 :class:`CommandJob`（最常用的入口）。                  |
| `extract_job() -> CommandJob`                                                   | 图片提取的 job：跑 `extract`，**单 PDF 时把产物平铺到输出目录**。     |
| `job_for(spec) -> StepJob \| None`                                              | 按 :class:`~desktop.steps.spec.StepSpec` 造执行 job（**唯一入口**）。 |
| `callable_job(fn: Callable[[StepRequest, Report], str \| None]) -> CallableJob` | 按纯函数造一个 :class:`CallableJob`。                                 |

#### `extract_job() -> CommandJob`

图片提取的 job：跑 `extract`，**单 PDF 时把产物平铺到输出目录**。

⚠️ 为什么需要它（2026-10-02 实测）：`functions.extract` 按
`<输出>/<PDF名>/images/` 铺图（`run_on_input_directory`，与 CLI 同源）。

- 源是**目录**（一次多个 PDF）时这是对的做法：每个 PDF 各自一个文件夹，
  否则大家的 `1.jpg` 会互相覆盖；
- 源是**单个 PDF**时这层嵌套纯属多余，而且**违背本层"输出目录精确生效"的
  承诺**：用户选的是 `样书_提取`，图片却在 `样书_提取/样书/images/`。
  更糟的是下一步——把输出目录直接拖给「去底色」，功能层只扫顶层，报
  "未找到图片文件"（实测：提取 → 去底色连不上）。

所以单 PDF 时把 `<输出>/<PDF名>/**` 搬平到 `<输出>/` 再删空壳；有同名
文件时**整个不动**（宁可留着嵌套，也不能覆盖或丢文件）。

#### `job_for(spec) -> StepJob | None`

按 :class:`~desktop.steps.spec.StepSpec` 造执行 job（**唯一入口**）。

调用方（模块页 / 将来的批处理界面）不要自己拼 `command_job`：哪一步需要
额外的收尾（如 extract 的平铺）只有这里知道，散出去就一定会漏。
没有命令的步骤（拼版）返回 `None`——那种步骤由调用方给 `CallableJob`。

---

## `desktop.steps.ports`

源码：[`desktop/steps/ports.py`](../../desktop/steps/ports.py)

步骤的**输入 / 输出端口**：把「这一步吃什么、吐什么」写成可连线的声明。

用户 2026-10-03 的口径：

> 任务流程每一步解耦，后续我会使用 bpm 流程处理不同的任务流程顺序，
> 因此每一步都有输入，输出就可以了

本模块只回答三个问题，**不碰界面、不碰算法、不决定顺序**：

1. **数据"是什么"** —— :data:`ARTIFACTS` 里的**产物类型**（PDF / 图片 /
   检测框）。BPM 连线按它匹配：上游只要吐出 `pages`，无论它来自图片提取
   还是图片拼版，下游都接得上。**这是"解耦"真正落地的地方**——下游不认
   上游是谁，只认产物类型。
2. **这一步要什么、给什么** —— :func:`stage_inputs` / :func:`stage_outputs`，
   它们从 :class:`~desktop.steps.spec.StepSpec` 的 `inputs` / `outputs`
   字段派生（那是**唯一的端口声明处**），不在这里另写一份。
3. **产物落在哪** —— :data:`STAGE_LOCATIONS` 给出每个端口在
   `tasks/<任务号>/` 下的相对落点，:func:`artifact_path` 解析成绝对路径。

**顺序与连线**由 :data:`SUPPLIERS` 一处决定：键是消费阶段，值是
`{端口名: 供给阶段}`。将来的 BPM 换顺序 / 换连线只改这张表，算法、界面、
任务目录布局全都不用动。

⚠️ **运行阶段名与步骤 key 不是一回事**（本模块唯一的额外概念）：

- 步骤 key 是 :data:`~desktop.steps.spec.STEP_KEYS` 里的 `extract` /
  `detect` / `rembg` / `print` / `imposition`，描述"这是什么功能"；
- **运行阶段**多一个 `rembg_submit`——它是第三步「去底色」面板上的
  「提交本次任务」按钮触发的**同一步骤的第二个动作**（先生成整页预览图到
  `stages/rembgpreview`，用户确认后才把最终图落到 `stages/rembg`）。
  端口系统必须认得它，否则第三步的产物没有落点、第四步也没有输入。

  ==================== ==========================================
  运行阶段 步骤 key / 端口
  ==================== ==========================================
  `extract` `extract`：in=pdf / out=pages
  `detect` `detect`：in=pages / out=boxes
  `rembg` `rembg`：in=pages,boxes / out=pages（预览）
  `rembg_submit` `rembg`：in=pages / out=pages（最终图）
  `print` `print`：in=pages / out=pdf
  ==================== ==========================================

⚠️ 本模块**纯逻辑、不 import 任何 Qt**，因此可以被自测、CLI 与将来的
BPM 编排引擎安全导入（与 :mod:`desktop.steps.spec` 同一约束）。

### 模块常量

| 名称               | 值         |
| ------------------ | ---------- |
| ARTIFACT_PDF       | `"pdf"`    |
| ARTIFACT_PAGES     | `"pages"`  |
| ARTIFACT_BOXES     | `"boxes"`  |
| SUPPLY_TASK_SOURCE | `"<task>"` |
| IMPOSITION_ANCHOR  | `"print"`  |

### 模块函数

| 函数                                                                                                                              | 说明                                                               |
| --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `artifact_of(port: str) -> str`                                                                                                   | 端口名 → 产物类型；未知端口按"页面图片"兜底（别让界面崩）。        |
| `stage_inputs(stage: str) -> tuple[str, ...]`                                                                                     | 这一步**消费**哪些端口（来自 `StepSpec.inputs`，不另写一份）。     |
| `stage_outputs(stage: str) -> tuple[str, ...]`                                                                                    | 这一步**产出**哪些端口（来自 `StepSpec.outputs`，不另写一份）。    |
| `spec_for_stage(stage: str) -> StepSpec \| None`                                                                                  | 运行阶段 → 它对应的 :class:`StepSpec`（界面查表统一走这里）。      |
| `stage_artifacts(stage: str) -> tuple[str, ...]`                                                                                  | 这一步消费哪些**产物类型**（端口名翻译过来）。                     |
| `location_of(stage: str, port: str) -> str \| None`                                                                               | 运行阶段某端口的相对落点；没有登记返回 `None`。                    |
| `artifact_path(task_dir: Path \| str, stage: str, port: str) -> Path \| None`                                                     | 产物在任务目录下的**绝对路径**；该阶段没登记这个端口则 `None`。    |
| `supplier_of(stage: str, port: str) -> str \| None`                                                                               | 某阶段某端口由谁供给；没有连线返回 `None`。                        |
| `print_pages_supplier(imposition_active: bool) -> str`                                                                            | 生成 PDF 取图的上游：拼版生效时是 `imposition`，否则是第三步提交。 |
| `print_input_overrides(imposition_active: bool) -> dict[tuple[str, str], str]`                                                    | 打印阶段的运行时连线覆盖（拼版开关 → 上游换成 imposition）。       |
| `resolve_input(task_dir: Path \| str, stage: str, port: str, overrides: dict[tuple[str, str], str] \| None=None) -> Path \| None` | **按连线**解析某阶段某端口的输入绝对路径。                         |
| `input_ready(task_dir: Path \| str, stage: str, port: str, overrides: dict[tuple[str, str], str] \| None=None) -> bool`           | 这个端口的输入**已经就位**吗（落点存在且非空）。                   |
| `missing_stages(order: list[str], *, start: str \| None=None) -> list[str]`                                                       | 给定顺序，返回**输入还缺上游**的阶段（按顺序）。                   |
| `describe(stage: str) -> str`                                                                                                     | 一行可读描述（`去底色：图片 + 检测框 → 图片`，日志/自测用）。      |

#### `stage_inputs(stage: str) -> tuple[str, ...]`

这一步**消费**哪些端口（来自 `StepSpec.inputs`，不另写一份）。

`rembg_submit` 是"把预览图定稿"的提交动作，不重新检测，所以它**不吃**
`boxes`（框在预览那一步已经用过了）；这里显式覆盖，其余阶段直接取 spec。

#### `spec_for_stage(stage: str) -> StepSpec | None`

运行阶段 → 它对应的 :class:`StepSpec`（界面查表统一走这里）。

⚠️ 这一层映射（:data:`STAGE_STEPS`）在：`rembg_submit` 要拿 `rembg` 的
声明（它是同一步骤的第二个动作），而 `imposition` 虽是**伪步骤**（不在
`STAGES` 里）却也有自己的 spec。页面里凡是"按 stage 取这一步的界面元数据"
（按钮文案、控制列宽度、预览控件名、右栏专属区块）都必须走本函数，
**不要**自己 `spec_by_key(stage)`——那会在 `rembg_submit` 上拿到 None。

#### `artifact_path(task_dir: Path | str, stage: str, port: str) -> Path | None`

产物在任务目录下的**绝对路径**；该阶段没登记这个端口则 `None`。

`task_dir` 传 `tasks/<任务号>/`（不是数据根）。

#### `print_pages_supplier(imposition_active: bool) -> str`

生成 PDF 取图的上游：拼版生效时是 `imposition`，否则是第三步提交。

⚠️ 抽成函数而不是在 :data:`SUPPLIERS` 里写死，是为了让"拼版生效"这种
**运行态开关**（用户在详情页勾了拼版节点）有一个明确、可测的出口：
BPM 编排时这正是"条件连线"的落点。

#### `print_input_overrides(imposition_active: bool) -> dict[tuple[str, str], str]`

打印阶段的运行时连线覆盖（拼版开关 → 上游换成 imposition）。

传给 :func:`resolve_input` / :func:`input_ready`。⚠️ 返回**新字典**：
调用方可能缓存它，别让一次运行的状态漏进下一次。

#### `resolve_input(task_dir: Path | str, stage: str, port: str, overrides: dict[tuple[str, str], str] | None=None) -> Path | None`

**按连线**解析某阶段某端口的输入绝对路径。

`overrides` 是 `{(阶段, 端口): 供给阶段}` 的运行时覆盖（拼版开关
就是用它），优先级高于 :data:`SUPPLIERS`。解析不出来返回 `None`。

#### `input_ready(task_dir: Path | str, stage: str, port: str, overrides: dict[tuple[str, str], str] | None=None) -> bool`

这个端口的输入**已经就位**吗（落点存在且非空）。

只看"有没有东西"，不判断内容对不对——那是功能层的事。

#### `missing_stages(order: list[str], *, start: str | None=None) -> list[str]`

给定顺序，返回**输入还缺上游**的阶段（按顺序）。

:data:`SUPPLIERS` 是静态声明，它默认"每个上游都跑过"。真要上线 BPM
编排时，用它在执行前先做一次依赖检查：某个阶段的输入端口若由一个
**还没执行**的上游供给，它就是当前不该跑的。

⚠️ 不在这里判断"目录里有没有文件"——那要读磁盘、不是纯逻辑。运行态
的就绪判断走 :func:`input_ready`。

---

## `desktop.steps.process`

源码：[`desktop/steps/process.py`](../../desktop/steps/process.py)

子进程传输层：把 worker 子进程的启动、看门狗与收尾收成一个可复用零件。

**为什么在"共用步骤组件层"里**：任务详情页原先自己攥着这坨代码
（`StageRunnerMixin` 里一百多行 QProcess/看门狗/兜底收尾），它和页面耦合在
一起，谁都复用不了。抽到本模块后，它只依赖 Qt，不知道"第几步""任务是什么"，
于是和 :mod:`desktop.steps.kernel`（进程内执行内核）并列成为这一层的两种
"把一步跑起来"的方式：

- :class:`~desktop.steps.kernel.StepKernel`：**进程内**线程，轻，模块页用；
- :class:`StageProcess`：**子进程**隔离，重，任务管理用（torch 崩溃不带走
  GUI、能真正 kill 掉）。

职责边界（有意划在这里）：

- 本类**只做传输**：起进程、把管道里的**原始字节**转出来、Windows 偶发丢
  `finished` 时用看门狗兜底、保证"完成"只报一次；
- **不解析** stdout 的 JSON Lines、不认 stderr 里哪行像错误、不碰 runs.json
  ——那些是宿主的业务（写运行记录、刷进度条、落 boxes.json），放这里会让
  本类重新长出"任务流程"的触手，也就失去了复用价值。

### `class StageProcess(QObject)`

一个阶段子进程：起进程、转字节流、兜底收尾。

信号（全部在**主线程**发出）：

- `stdout(bytes)`：标准输出的**原始字节**（宿主自己做半行重组与 JSON 解析）；
- `stderr(bytes)`：标准错误的原始字节（宿主决定哪行算错误）；
- `started()`：进程真的起来了；
- `finished(int, object)`：`(退出码, exit_status)`，**保证只发一次**；
- `process_error(object)`：QProcess 报的错（含启动失败）；
- `stalled(float)`：已 N 分钟没有任何输出（只提醒，不自动杀）；
- `unclean_exit()`：OS 进程已退出、Qt 却没能正常收尾（看门狗兜底）；
  宿主据此把"未正常收尾"记成失败原因——本类只报"发生了"，不管怎么记。

#### 方法

| 方法                                                                                                                              | 说明                                                       |
| --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| `__init__(parent=None, stall_warn_s: float \| None=None)`                                                                         | —                                                          |
| `process() -> QProcess \| None`                                                                                                   | 底层 `QProcess`（宿主用它查状态/杀进程；测试也按它等待）。 |
| `running() -> bool`                                                                                                               | 进程是否还在跑。                                           |
| `start(program: str, arguments: list[str], workdir: Path \| str \| None=None, env: QProcessEnvironment \| None=None) -> QProcess` | 起子进程并接好输出/看门狗；返回底层 `QProcess`。           |
| `kill() -> None`                                                                                                                  | 杀掉子进程（不等待；等待由宿主决定）。                     |

##### `start(program: str, arguments: list[str], workdir: Path | str | None=None, env: QProcessEnvironment | None=None) -> QProcess`

起子进程并接好输出/看门狗；返回底层 `QProcess`。

调用方通常紧接着把返回值存到自己的属性上（既有测试按
`page.process` 取进程）。

### 模块函数

| 函数                                               | 说明                                                               |
| -------------------------------------------------- | ------------------------------------------------------------------ |
| `worker_arguments(config_path: Path) -> list[str]` | 按运行环境给出启动 worker 子进程的参数表。                         |
| `worker_env() -> QProcessEnvironment`              | 子进程强制 UTF-8：GUI 按 UTF-8 解析 JSON Lines，CLI 输出含 emoji。 |

#### `worker_arguments(config_path: Path) -> list[str]`

按运行环境给出启动 worker 子进程的参数表。

- 打包（`sys.frozen`）：主程序即入口，`--worker --config` 路由到子任务执行；
- 源码：按模块启动（`-m desktop.worker`），不依赖入口文件名（`desktop.py`
  改名无影响），工作目录必须是项目根（能解析出 `desktop` 包的那一级）。

---

## `desktop.steps.source_zone`

源码：[`desktop/steps/source_zone.py`](../../desktop/steps/source_zone.py)

共用「大输入区」：拖拽 / 点选，把**文件或文件夹**交给一个步骤。

用户 2026-10-02 的要求（原话）：

> 你就在左侧这些目录点上去，页面上有一个大的输入框，可以输入图片和输入文件，
> 或者输入目录，也可以把文件拖进去，目录投进去。

于是有了这一块：**一个控件同时承担"选择"和"放下"两件事**，三条入口都通——

1. 拖**文件**进来；
2. 拖**文件夹**进来（含图片/PDF 的目录）；
3. **点按钮**选（空态底部两个真按钮「选择文件 / 选择文件夹」；已选态右端
   「更换」）——也可以点空态空白处或按回车，那条老入口仍留着。

⚠️ 第 3 条为什么要做成**看得见的按钮**（用户 2026-10-03 报）：原先只有"点
空白处弹两选项小菜单"这一条隐式入口，界面上没有任何东西提示它能点，用户看到
的只是一句"把 PDF 拖到这里"，于是报「不能直接点击按钮选择文件或文件夹」。
入口既然是主路径，就得画出来。

⚠️⚠️ **点空白处不再弹"选文件 / 选文件夹"那个两选项小菜单**（用户 2026-10-03
第二次提要求：「能否底部不设置选择图片或者目录的弹窗」）。那个小菜单锚在控件
**底部**，正是用户说的"底部弹窗"。现在点空白处 = **直接开选择对话框**（选文件），
不再先问一遍"你要文件还是目录"。

⚠️⚠️⚠️ **"选择对话框" ≠ "资源管理器窗口"**（2026-10-03 用户第三次纠正）。
曾经误实现成"弹一个 `explorer.exe` 窗口 + 监听用户在窗口里的选中项"，用户
明确否掉：「不对，现在直接打开资源浏览器了，而不是调用资源浏览器选择文件或者
目录」。二者区别很大：

- **要的**：资源管理器那套**选文件/选目录的对话框**，选完直接拿到结果 ——
  也就是 :class:`QFileDialog` 的**原生**对话框（不设 `DontUseNativeDialog`，
  Windows 上它本来就是资源管理器式的那套界面），有"打开/取消"、结果确定；
- **不要的**：另开一个**浏览用的资源管理器窗口**，再靠轮询/监听去猜他点了谁 ——
  用户还得自己双击文件夹去定位，程序只能猜，且弹出的窗口与"选文件"无关。

它是 :mod:`desktop.steps` 层的一部分，所以左侧三个模块与任务流程**共用同一份
实现**——这正是用户要的"抽成公共组件、定义好入口/出口 API"。

设计要点（改之前先读）：

- **只管"用户给了哪些路径"，不管"这算不算合法输入"**。归一化（一堆文件/文件夹
  → 一个"源"）由 :meth:`desktop.steps.spec.StepSpec.resolve_source` 负责，
  那是纯逻辑、可以脱离 Qt 单测；本控件只把原始路径经 `paths_chosen` 发出去。
  这样"拼图"这种要整份清单的调用方也能直接复用本控件。
- **虚框自绘、按钮用真控件**：外框、图标、两行文案、清空 ✕ 都是 `paintEvent`
  画的（项目规矩：基础控件不引样式表），但「选择文件 / 选择文件夹 / 更换」
  必须是 :class:`qfluentwidgets.PushButton` —— 它们要 hover、按下、焦点态，
  自绘等于把这些交互重写一遍还写不好。因此本控件内部**有一个子控件层**，
  几何由 :meth:`SourceZone._relayout_buttons` 手工摆（空态摆在文案下方、
  已选态右端一枚），自绘内容按同一个基准排（见 :meth:`_empty_block_top`）。
- **空态的"文案 + 按钮"是一整块、垂直居中**（用户 2026-10-03 截图反馈）：
  独占模式下控件高达 700px+，若文案贴顶、按钮钉在框底，中间是一大片空白，
  看着像两个不相干的区域。`_empty_block_height` 把按钮也算进整块高度，
  两边共用 `_empty_block_top` ⇒ 文案与按钮永远贴在一起、一起居中。
- **拖拽热区**：拖到控件上（或宿主页面上，见 `ModulePage`）时描边与底色变主色，
  给"松手就放这儿"的反馈。

### 模块常量

| 名称           | 值    |
| -------------- | ----- |
| EMPTY_HEIGHT   | `168` |
| FILLED_HEIGHT  | `74`  |
| ICON_BOX       | `30`  |
| CLOSE_BOX      | `26`  |
| BUTTON_HEIGHT  | `30`  |
| BUTTON_GAP     | `10`  |
| SOLO_HEIGHT    | `320` |
| SOLO_MIN_WIDTH | `360` |

### `class SourceZone(QWidget)`

一个步骤的**大输入区**：拖入 / 点选文件或文件夹（自绘，可清空）。

信号：

- `paths_chosen(list)`：用户拖入或选中了一批路径（`list[str]`，**原始**，
  未做任何合法性判断）；空拖拽不会发。
- `cleared()`：用户点了右上角的清空。
- `rejected(str)`：拖进来的东西一件都用不了（一句给用户看的话）。
  调用方通常转成页头的 toast/状态行。

显示与语义分离：`set_source()` 只负责"把现在选中的源画出来"，不发信号，
因此宿主（:class:`~desktop.steps.control.StepControl`）说了算——它才是
"文件/目录 → 一个源"的归一化权威。

#### 方法

| 方法                                                            | 说明                                                                    |
| --------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `__init__(spec: StepSpec, parent=None)`                         | 按 `spec` 取文案/图标/过滤串；初始为空态。                              |
| `source() -> Path \| None`                                      | 当前**显示**的源（宿主设进来的；未设为 `None`）。                       |
| `set_source(path: Path \| str \| None, detail: str='') -> None` | 把"当前源"画出来（不发 `paths_chosen`，避免与宿主来回打环）。           |
| `offer(paths) -> None`                                          | 把一批路径当作用户给的输入送出去（拖拽/点选/宿主转发都走这里）。        |
| `set_hot(hot: bool) -> None`                                    | 外部（宿主页面的整页拖拽）切换"正在拖入"高亮。                          |
| `clear() -> None`                                               | 清空当前源并发 `cleared`（点右上角 ✕ 与宿主主动复位走同一条）。         |
| `busy_lock(locked: bool) -> None`                               | 执行中禁用（拖拽也不收），并保持当前画面。                              |
| `set_solo_mode(solo: bool) -> None`                             | 切**独占模式**：页面上再没有别的控件，本控件撑满整幅（空态）。          |
| `paths_from_mime(mime) -> list[str]`                            | 从拖拽数据里取**本地**路径（URL 形式的文件/文件夹，非本地的丢掉）。     |
| `dragEnterEvent(event) -> None`                                 | 有东西拖上来：认得本地文件/文件夹就收，并亮起来。                       |
| `dragMoveEvent(event) -> None`                                  | 拖拽移动中：保持接受（Qt 要求显式接受才会给 drop）。                    |
| `dragLeaveEvent(event) -> None`                                 | 拖出控件：熄灭高亮。                                                    |
| `dropEvent(event) -> None`                                      | 松手放下：把原始路径交给宿主。                                          |
| `enterEvent(event) -> None`                                     | 鼠标进来：底色淡一档（可点的暗示）。                                    |
| `leaveEvent(event) -> None`                                     | 鼠标离开：恢复底色。                                                    |
| `keyPressEvent(event) -> None`                                  | 回车/空格 = 点一下（键盘可达）。                                        |
| `mousePressEvent(event) -> None`                                | 点清空 = 清空；点已选态的 ✕ = 清空；点其余任何地方 = 换源（开对话框）。 |
| `browse() -> None`                                              | 点空白处 / 按回车 = 直接开**选文件**对话框。                            |
| `resizeEvent(event) -> None`                                    | 尺寸变了：按钮行跟着重新居中。                                          |
| `paintEvent(event) -> None`                                     | 画底（圆角虚线框）+ 内容（空态两行 / 已选态一行）。                     |

##### `set_source(path: Path | str | None, detail: str='') -> None`

把"当前源"画出来（不发 `paths_chosen`，避免与宿主来回打环）。

`path=None` 回到空态；`detail` 是已选态的第二行小字（如"文件夹 ·
12 个文件"），留空时按路径自动生成。

##### `offer(paths) -> None`

把一批路径当作用户给的输入送出去（拖拽/点选/宿主转发都走这里）。

空列表不进主流程（避免下游收到"什么都没有"的信号），改为发一条
`rejected` 让界面说话。

##### `set_solo_mode(solo: bool) -> None`

切**独占模式**：页面上再没有别的控件，本控件撑满整幅（空态）。

由 :meth:`desktop.modules.base.ModulePage.show_workspace` 调用——
用户 2026-10-03 要求「初始就只有一个输入框，下面的操作面板和预览
这些都要选择输入文件后才显示出来」。分栏一收，页面上半屏是框、
下半屏一片空白，看着像没加载完；独占模式把这个观感补回来。

⚠️ **已选态不参与**：源一旦选中就切回常规高度（`FILLED_HEIGHT`），
因为那时分栏会回来，输入区要还给预览让出纵向空间。

##### `paths_from_mime(mime) -> list[str]`

装饰器：`staticmethod`

从拖拽数据里取**本地**路径（URL 形式的文件/文件夹，非本地的丢掉）。

单独抽成 staticmethod 是为了能直接单测——不用去合成 Qt 拖拽事件。

##### `mousePressEvent(event) -> None`

点清空 = 清空；点已选态的 ✕ = 清空；点其余任何地方 = 换源（开对话框）。

⚠️ **已选态"点哪都能换源"是 2026-10-03 改回来的**（此前是"只有右上角那枚
「更换」按钮能点"，因为担心用户只是想点空白让控件失焦）。改回来的理由是
用户报「更换点了没反应」：那一枚按钮是**子控件**（见 :meth:`_build_buttons`），
它能否收到点击取决于几何是否已随布局重排——一旦布局晚一步（懒构造的模块页
正是如此），按钮画出来了却还不在正确位置，事件就落到了父控件上，而父控件
那时又什么都不做 ⇒ 用户看到的就是"点了完全没反应"。

把整条已选态都做成入口，就**不再依赖任何子控件的几何**：无论按钮在哪、
是否被盖住，点这块区域都能换源。右上角 ✕ 优先（它更靠右、语义不同）。

##### `browse() -> None`

点空白处 / 按回车 = 直接开**选文件**对话框。

⚠️ 2026-10-03 用户要求「底部不设置选择图片或者目录的弹窗」：原先这里
会先弹一个"选文件 / 选文件夹"的两选项小菜单（锚点就在控件**底部**，
见旧的 `_anchor_point`），用户点完小菜单**紧接着**才看到真正的选择
界面——两层弹窗叠着，正对应用户说的"底部弹窗"。现在那一层整个去掉：
点空白处直接进选择对话框。

⚠️ 只能默认"选文件"：`accepts_dir=True` 的步骤想选目录有专门的
「选择文件夹」按钮（那是显式入口），不必在这里再问一遍。

---

## `desktop.steps.spec`

源码：[`desktop/steps/spec.py`](../../desktop/steps/spec.py)

步骤的**声明式元数据**：一个步骤"是什么"，与流程顺序无关。

用户口径（2026-10-02）：

> 任务管理每个步骤组件有先后关系，因此我们的组件不需要相互关联，
> 公共组件定义好 API 就行，比如入口文件目录，输出文件目录等。

所以 :class:`StepSpec` 只描述**这一步自己**：跑哪个命令、用哪个参数面板、
输入是 PDF 还是图片（单张 / 目录 / 一批）、默认输出目录怎么从输入推出来。
「上一步是谁、下一步是谁、产物给谁用」**一概不写**——那是任务管理自己的
编排，不是步骤的属性。正因如此，同一个 spec 既能被任务流程用，也能被左侧
导航的独立模块用。

「入口」这一侧的三件事也都收在这里，**不散到界面代码**去（用户 2026-10-02：
「页面上有一个大的输入框，可以输入图片和输入文件，或者输入目录，也可以把
文件拖进去」）：

1. 认哪些后缀 —— :meth:`StepSpec.suffixes`（从 `file_filter` 里抠，过滤串
   仍是唯一事实来源）；
2. 允不允许直接拿目录当输入 —— `accepts_dir`；
3. 用户给了一堆东西（拖进来的文件/文件夹混在一起）**到底算哪个源** ——
   :meth:`StepSpec.resolve_source`。这是纯逻辑，可以脱离 Qt 单测。

⚠️ 面板只记**类名**（字符串），到用的时候才从 `desktop.components.panels`
惰性取——本模块因此不 import 任何 Qt 面板，可以被纯逻辑（CLI、自测、未来的
批处理）安全导入。

### 模块常量

| 名称               | 值                                                      |
| ------------------ | ------------------------------------------------------- |
| IMAGE_FILTER       | `"图片 (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)"` |
| PDF_FILTER         | `"PDF 文件 (*.pdf)"`                                    |
| AUTO_DESCEND_DEPTH | `2`                                                     |

### `class StepSpec`

一个处理步骤的元数据（不可变，可当字典键/常量用）。

字段含义：

- `key`：唯一路由键，与 `desktop.modules.MODULES` 的 key 同名同义；
- `command`：`functions.get_function` 的命令名；`None` 表示这一步
  不是 CLI 命令（如拼版是纯函数 `compose_doc`，由调用方给 job）；
- `title`：**模块页头大标题**的名字（"图片提取"）。⚠️ 左侧导航那一列
  用自己的 `nav_title`（见下），磁盘目录用 `disk_key()`——三者互不相干；
- `nav_title`：**左侧导航条目**的名字（空则用 `title`）；
- `subtitle`：**模块页头副标题**（"选择一个 PDF（…），把每页渲染成图片"）；
- `nav_tooltip`：**导航条目悬停提示**（空则用 `subtitle`）；
- `nav_icon`：**导航条目图标**（`FluentIcon` 成员名；或 `svg:名字`
  引用 `desktop.ui.icons.CustomIcon` 的自绘图——内置图标没有的图形），
  由 `desktop.ui.icons.resolve_nav_icon` 统一解析；
- `panel`：参数面板**类名**（`desktop.components.panels` 里的名字）；
  `None` 表示这一步没有可调参数；
- `pick_label`：源选择对话框的标题（"选择 PDF" / "选择图片"）；
- `run_label`：执行按钮文案（空则回落到"开始 + 标题"）；
- `file_filter`：`QFileDialog` 的文件过滤串，**同时是后缀的唯一来源**
  （见 :meth:`suffixes`）；
- `accepts_dir`：源能不能直接是目录（拖进来一个文件夹算不算一个源）；
- `allow_multi`：对话框允许一次多选（拖拽天然支持多选，此项只管对话框）；
- `flat_output`：单源时要不要把产物**平铺到输出目录根下**。置 `True` 的
  只有 `extract`——它的命令习惯是 `<输出>/<PDF名>/images/`（见
  :func:`desktop.steps.kernel.job_for`），单 PDF 时这层嵌套既多余又断链；
- `artifact_is_file`：这一步的产物是**单个文件**（而不是一目录文件）。
  `print` 为 `True`——它的 `--output` 是**目录**，文件名由命令自己在其下
  取（`<输出>/output.pdf`），所以执行内核**不能**把 `function.outpath`
  覆盖成那个目录（覆盖了就会拿目录当文件路径写，直接报错）；内核还会把
  **真正的产物路径**（而不是目录）回传给 `finished`；
- `output_suffix`：默认输出目录名 = 源名 + 这个后缀；
- `output_name`：给了就用**固定名**（如"拼图成品"），不再用后缀规则；
- `drop_icon` / `drop_title` / `drop_hint`：共用大输入区
  （:class:`desktop.steps.source_zone.SourceZone`）的图标与两行文案；
  后两者留空时按 `title` 生成兜底文案。

⚠️ **文案字段按"界面上有哪几个地方要显示"逐个建，不合并**。同一步在流程条
和左侧导航里叫法确实不一样（流程条说的是**动作**「提取图片」，导航说的是
**东西**「图片提取」），硬合成一个名字就会改动其中一处界面。所以：

=============== ==========================================
字段 用在哪
=============== ==========================================
`title` 模块页头大标题（**不含**左侧导航，见 `nav_title`）
`nav_title` 左侧导航条目的名字（空则用 `title`）
`subtitle` 模块页头副标题
`nav_tooltip` 导航条目悬停提示
`stage_title` 流程步骤条上的名字（空则用 `title`）
`short` 流程步骤条上的短名（空则用 `stage_title`）
=============== ==========================================

**详情页侧**（`run_button_text` / `has_submit` / `control_width` /
`preview_attr` / `panel_extra` / `history_skip` / `auto_fill_skip`）：
"这一步在任务流程详情页里长什么样"。⚠️ 这些**曾经散在页面的 if-else 里**
（`page._select_stage` 按 stage 改按钮文案与区块显隐、`view.
_apply_control_width` 按 stage 换宽度、`history._history_fill_keys`
按 stage 跳过不同键）——加一步就得改那几处 if，BPM 换顺序更是无从下手。
现在都是**声明**：页面只查表，不认哪个 step 是谁。

**流程侧**：

- `role`：`"stage"` = 默认流程主链上的一步；`"optional"` = 流程条上的
  **可选节点**（拼版就是：`STAGES` 里没有它，但它有自己的模块页）。
  见 :data:`FLOW_STAGES` / :data:`OPTIONAL_STEPS`；
- `nav`：这一步**有没有独立的模块页**、要不要进左侧导航。`False` 表示
  还没抽出来——壳层据此不过去建页面（`desktop.modules.MODULES` 会把它
  过滤掉），免得出现"清单里有、页面不存在"；
- `inputs` / `outputs`：**BPM 端口**——这一步消费/产出哪些产物
  （`pages` 图片 / `boxes` 检测框 / `pdf`）。⚠️ **已接线**（2026-10-03
  补完）：:mod:`desktop.steps.ports` 按这两个字段 + 它的连线表把步骤连起来，
  任务流程不再靠"约定目录布局"。**声明必须与事实一致**——端口模型靠它做
  依赖检查，写漏一个就等于给 BPM 一条假的边（`rembg` 漏写 `boxes` 就是
  这样被 `tests/selftests/step_ports.py` 逮到的）。

#### 方法

| 方法                                                                                      | 说明                                                                   |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `panel_class()`                                                                           | 惰性取参数面板类（`None` 表示这一步没有面板）。                        |
| `suffixes() -> tuple[str, ...]`                                                           | 本步骤认的文件后缀（小写，含点）；从 `file_filter` 推导。              |
| `input_noun() -> str`                                                                     | 输入物的中文称呼（"PDF" / "图片"），由 `pick_label` 派生，用于提示语。 |
| `accepts_path(path: Path \| str) -> bool`                                                 | 这个路径能不能当源：目录看 `accepts_dir`，文件看后缀。                 |
| `collect_files(paths) -> list[Path]`                                                      | 把一批路径展开成**文件清单**（给"要一批文件"的调用方，如拼图）。       |
| `listing(directory: Path \| str) -> list[Path]`                                           | 目录里符合本步骤后缀的文件（**只看顶层**，与功能层                     |
| `nested_listing(directory: Path \| str, max_depth: int=AUTO_DESCEND_DEPTH) -> list[Path]` | 在下面 1~`max_depth` 层里找**装着本步骤文件的子目录**（广度优先）。    |
| `resolve_source(paths) -> tuple[Path \| None, str]`                                       | 把用户给的一批路径**归一成"这一步的源"**（文件或目录）。               |
| `default_output(source: Path \| None) -> Path \| None`                                    | 从源路径推出默认输出目录（源为空则返回 `None`）。                      |
| `accepts_files() -> bool`                                                                 | 源可以是一批文件吗（多选 / 单选都算）。                                |
| `run_text() -> str`                                                                       | 执行按钮文案（`run_label` 为空时回落到"开始 + 标题"）。                |
| `progress_unit() -> str`                                                                  | 进度计量的单位（`progress_noun` 为空时回落到 `input_noun`）。          |
| `short_name() -> str`                                                                     | 流程步骤条上的短名（`short` 为空时用 `stage_name()`）。                |
| `stage_name() -> str`                                                                     | 流程步骤条上的名字（`stage_title` 为空时用 `title`）。                 |
| `nav_tip() -> str`                                                                        | 导航条目悬停提示（`nav_tooltip` 为空时用 `subtitle`）。                |
| `nav_name() -> str`                                                                       | 左侧导航条目上的名字（`nav_title` 为空时用 `title`）。                 |
| `disk_key() -> str`                                                                       | `singletask/` 下这个子任务的**目录名**（缓存/手改件的归属）。          |
| `drop_title_text() -> str`                                                                | 大输入区空态的标题（`drop_title` 为空时兜底）。                        |
| `drop_hint_text() -> str`                                                                 | 大输入区空态的提示行（`drop_hint` 为空时按能否选目录兜底）。           |
| `summary() -> str`                                                                        | 一行可读描述（日志/自测用，别拿它做判断）。                            |

##### `panel_class()`

惰性取参数面板类（`None` 表示这一步没有面板）。

`panel` 支持两种写法：

- `"ExtractPanel"`：在 `desktop.components.panels` 里找（四个阶段
  面板都在那儿，是绝大多数情况）；
- `"desktop.components.imposition:ImpositionPanel"`：**指定模块**再找
  ——拼版面板住在 `desktop.components.imposition`，不在上面那个包里。

##### `suffixes() -> tuple[str, ...]`

本步骤认的文件后缀（小写，含点）；从 `file_filter` 推导。

⚠️ 故意**解析过滤串**而不是另写一份后缀表：两处一旦并存就一定会漂移
（用户看到的对话框按过滤串，拖拽判定却按另一份表）。

##### `collect_files(paths) -> list[Path]`

把一批路径展开成**文件清单**（给"要一批文件"的调用方，如拼图）。

与 :meth:`resolve_source` 的分工：那个把一堆路径收成**一个源**（文件
提取 / 去底色要的），这个把它们**摊平成一份清单**（拼图要的）。

- 文件：后缀对就留下；
- 目录：先取顶层的；顶层没有、但只有**一个**子目录装着 → 用那一层
  （同 :meth:`resolve_source` 的下钻理由：提取模块的产物是
  `<输出根>/<PDF名>/images/`）；
- 结果去重并按文件名排序（"前一页左半幅 + 当前页右半幅"的配对规则
  依赖一个稳定顺序）。

##### `listing(directory: Path | str) -> list[Path]`

目录里符合本步骤后缀的文件（**只看顶层**，与功能层
`collect_image_files` / `run_on_input_directory` 同口径）。

读不了（不存在/没权限）时返回空表——调用方据此给"这里没有可用文件"。

##### `nested_listing(directory: Path | str, max_depth: int=AUTO_DESCEND_DEPTH) -> list[Path]`

在下面 1~`max_depth` 层里找**装着本步骤文件的子目录**（广度优先）。

命中一层就停在该层——找到更浅的就不再往下挖，避免把"某一层唯一"误判成
"最深处唯一"。返回的是目录清单（不是文件），调用方按数量决定怎么办。

##### `resolve_source(paths) -> tuple[Path | None, str]`

把用户给的一批路径**归一成"这一步的源"**（文件或目录）。

返回 `(源, 说明)`：说明为空 = 顺利且无需交代；非空是一句给用户看的
话（可能是我替你选了哪一个，也可能是不接受的理由）。

规则（顺序即优先级）：

1. 混着文件夹进来时，只要 `accepts_dir` 就**取第一个文件夹当源**
   （拖一个文件夹进来是最自然的批量用法）；**不接受目录的步骤直接
   拒绝**（`accepts_dir=False`，如"PDF 只支持文件"的图片提取）——
   别在这里"从文件夹里挑出符合后缀的文件"替用户做主：挑到哪几个、
   为什么是这几个，用户在界面上看不见，而下一步的产物又依赖这个
   选择，错了要等到看结果时才发现；
2. 文件夹**顶层没有**本步骤能用的文件时，往下钻一~两层（见
   :meth:`nested_listing`）：恰好一个子目录装着 → 自动指向它并说明；
   多个 → 拒绝并让用户挑一个（混着处理会把不同书的页拼在一起）；
3. 单个文件 → 它自己；
4. 多个文件 → 它们的**共同父目录**（批量语义就是"处理这个目录"）；
   共同父目录不存在（跨盘）时退到第一个文件所在的目录；
5. 一件都不匹配 → `(None, 理由)`。

##### `default_output(source: Path | None) -> Path | None`

从源路径推出默认输出目录（源为空则返回 `None`）。

规则（与三个模块改造前的行为逐字一致，改动会让老用户找不到产物）：

- 固定名（`output_name`）优先，放在源的**同级目录**下；
- 否则：源是目录 → `<父目录>/<目录名><后缀>`；
  源是文件 → `<父目录>/<文件名去后缀><后缀>`。

##### `progress_unit() -> str`

进度计量的单位（`progress_noun` 为空时回落到 `input_noun`）。

给 :class:`~desktop.components.progress_row.ProgressRow` 用；回落到
`input_noun` 是为了"没显式声明也能说出个大概"，总比空着强。

##### `stage_name() -> str`

流程步骤条上的名字（`stage_title` 为空时用 `title`）。

⚠️ 与 `title`（模块页头/导航）**有意分开**：见类 docstring 的文案表。

##### `nav_name() -> str`

左侧导航条目上的名字（`nav_title` 为空时用 `title`）。

⚠️ 与 `title` **有意分开**（同 :attr:`stage_title` 与 `title` 的
道理）：导航那一列是"这一步做什么"的**短标签**，页头是完整标题，
两处可以各说各的。用户 2026-10-03 就导航文案提过一轮（"图片提取"
→ "PDF图片提取" 等），只改这里不会连带改掉页头与流程条。

##### `disk_key() -> str`

`singletask/` 下这个子任务的**目录名**（缓存/手改件的归属）。

⚠️ **不是** `title` 也不是 `nav_title`：这两者都是会随文案需求改的
人类可读名字，而这里是**已经在磁盘上存在的路径**。`singletask/` 里
已经躺着按旧标题建的目录（`去底色` / `图片提取` / `拼图` /
`检测文本框` / `生成 PDF`），其中 `拼图/edited/` 存着用户手改过
的版面图——标题一改，这些缓存与手改件就再也找不到了（表现是"我明明
改过版面，重新打开又变回原样"）。

所以这里锚在 `key` 上（步骤的唯一路由键，改名不会动它）。改动此值
等于换一整个子任务目录，**必须**先做旧目录迁移。

### 模块函数

| 函数                                        | 说明                                     |
| ------------------------------------------- | ---------------------------------------- |
| `spec_by_key(key: str) -> StepSpec \| None` | 按 key 取步骤元数据；不存在返回 `None`。 |

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

| 方法                                                                                       | 说明                                                                  |
| ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| `boxes_path(task_id: str) -> Path`                                                         | 检测框存储文件：任务目录下的 boxes.json。                             |
| `detect_boxes_entry(task_id: str, image_key: str) -> tuple[list, str] \| None`             | 返回 (boxes, origin)；无记录时返回 None。origin: 'auto' \| 'manual'。 |
| `detect_boxes_all(task_id: str) -> dict[str, tuple[list, str]]`                            | 整份 boxes.json：`image_key → (boxes, origin)`，**一次读盘**。        |
| `save_detect_boxes(task_id: str, image_key: str, boxes: list, origin: str='auto') -> None` | 写入某页的检测框及其来源标记（auto=自动检测，manual=人工编辑）。      |
| `save_detect_boxes_batch(task_id: str, entries: dict[str, list]) -> None`                  | 批量写入某阶段的检测框（origin=auto）：**一次读改写**。               |
| `save_image_sizes_batch(task_id: str, entries: dict[str, tuple[int, int]]) -> None`        | 批量写入页面原始尺寸：一次读改写（理由同 save_detect_boxes_batch）。  |
| `sizes_path(task_id: str) -> Path`                                                         | 页面原始尺寸文件：任务目录下的 sizes.json。                           |
| `save_image_size(task_id: str, image_key: str, width: int, height: int) -> None`           | 记录某页图片的原始像素尺寸，作为框坐标与预览映射的坐标系基准。        |
| `image_size(task_id: str, image_key: str) -> tuple[int, int] \| None`                      | 返回某页原始像素尺寸 (width, height)；无记录时返回 None。             |

##### `detect_boxes_all(task_id: str) -> dict[str, tuple[list, str]]`

整份 boxes.json：`image_key → (boxes, origin)`，**一次读盘**。

逐页统计（第二步右侧的检测结果统计）要遍历全部页面，若逐页调
`detect_boxes_entry` 就是「读整个文件」× 页数；这里一次读完。

##### `save_detect_boxes_batch(task_id: str, entries: dict[str, list]) -> None`

批量写入某阶段的检测框（origin=auto）：**一次读改写**。

⚠️ 为什么必须攒批：detect 跑 320 页时逐页 `save_detect_boxes` 是
「读整个 boxes.json + 改写」× 页数，实测 320 页累计 **1.8 秒**主线程
阻塞（2400 页的书记忆里是 47.5s，见
`.workbuddy/perf/2026-09-23-sqlite-vs-json.md`）；攒批后一次落盘
~0.02s。人工框（origin=manual）在这里跳过，不被自动结果覆盖——
与单条版同一条规矩，但只读一次文件。

---

## `desktop.store.drafts`

源码：[`desktop/store/drafts.py`](../../desktop/store/drafts.py)

参数暂存（`drafts/<阶段>.json`）：用户改过、但**还没执行**的阶段参数。

为什么需要它：进入某个阶段时表单按「最近一次执行参数」回填（见
`desktop/pages/taskdetail/history.py`），用户改完参数却没执行就切阶段 /
切任务 / 关程序，改动全部丢失——再回来看到的还是上一次执行的值，等于白调。

存什么：`get_args()` 的结果（已归一化：边距是列表、颜色是 "r,g,b"、
跳过页是列表…）。读取方是同一个面板的 `apply_args()`，所以"存—取"天然
按同一套键名对称，不需要第二份字段表。

- 与 `pages.json`/`print.json` 一样是任务目录下的 JSON，删除任务即清掉；
- 系统管理字段（input/output/workers/clean…）不入暂存，与历史回填的跳过
  清单一致；
- 参数非法时调用方**不写**（见 `save_draft` 的返回值），保留上一份有效暂存。

### `class DraftMixin`

`drafts/<阶段>.json` 的读写。

#### 方法

| 方法                                                         | 说明                                                               |
| ------------------------------------------------------------ | ------------------------------------------------------------------ |
| `drafts_dir(task_id: str) -> Path`                           | 暂存目录：`tasks/<任务号>/drafts`。                                |
| `draft_path(task_id: str, stage: str) -> Path`               | 某阶段的暂存文件：`drafts/<阶段>.json`。                           |
| `load_draft(task_id: str, stage: str) -> dict \| None`       | 读取暂存参数；没有/格式不对返回 None。                             |
| `save_draft(task_id: str, stage: str, params: dict) -> bool` | 写入暂存参数，返回是否真的写了。                                   |
| `clear_draft(task_id: str, stage: str) -> None`              | 删除某阶段的暂存（用户点「恢复默认配置」并执行后想彻底归零时用）。 |

##### `save_draft(task_id: str, stage: str, params: dict) -> bool`

写入暂存参数，返回是否真的写了。

任务目录已删除时跳过（与 `save_pages` 同规矩：不把已删任务重新
创建出来）；`params` 为空则视为"没有可暂存的内容"，返回 False。

---

## `desktop.store.imposition`

源码：[`desktop/store/imposition.py`](../../desktop/store/imposition.py)

图片拼版文档（`drafts/imposition.json`）：选择态 + 逐页拼版版面。

为什么放在 `drafts/` 而不是任务根目录：这个文件从「图片拼版」占位节点
时代就在那里（当时只有 `{"enabled": bool}`），换位置会让老任务的选择态
凭空丢失。现在扩成一句话能读完的形状：

    {
      "enabled": true,                      # 是否把拼版接进流程（第四步取图开关）
      "pages": [                            # 拼版清单，列表顺序即产出页序
        {
          "items": [                        # 恒 2 项：0=右槽（序号在前），1=左槽
            {"file": "...", "rect": [x, y, w, h], "rotation": 0.0},
            {"file": "...", "rect": [x, y, w, h], "rotation": 0.0}
          ]
        }
      ]
    }

`rect` 的单位是**源图像素**（左上原点、x 向右、y 向下）。`rotation` 是
**顺时针角度**（与 Qt `QPainter.rotate` 同向；PIL 侧取负）。

⚠️ **没有 `sheet`**（用户 2026-09-30：「拼版不需要设置纸张，只需要背景是
白色的就行，后续提交的时候根据图片的四个区域合并出一张图片」）：早期版本存过
`"sheet": [w, h]`，现在读进来**直接忽略**——版面完全以两张图为准，产出图按
所有图的外接框紧裁（`services.imposition.page_bounds`）。

形状校验与合成规则都在 `desktop.services.imposition`（**唯一实现处**）——
这里只负责「按任务目录读写这份 JSON」，读出来的东西一律过一遍
`normalize_doc`，调用点不用判空、不用自己验字段。

⚠️ 只做「读—写」，不碰 Qt。

### `class ImpositionMixin`

`drafts/imposition.json` 的读写。

#### 方法

| 方法                                                   | 说明                                                             |
| ------------------------------------------------------ | ---------------------------------------------------------------- |
| `imposition_doc_path(task_id: str) -> Path`            | 拼版文档：`tasks/<任务号>/drafts/imposition.json`。              |
| `load_imposition_doc(task_id: str) -> dict`            | 读拼版文档（缺失/损坏一律回落成空文档，调用点不用判空）。        |
| `imposition_enabled(task_id: str) -> bool`             | 这个任务**是否启用了拼版**（只有 `enabled`，不看有没有拼版页）。 |
| `save_imposition_doc(task_id: str, doc: dict) -> bool` | 写拼版文档，返回是否真的写了。                                   |

##### `imposition_enabled(task_id: str) -> bool`

这个任务**是否启用了拼版**（只有 `enabled`，不看有没有拼版页）。

给**任务列表**用：列表要回答"这条任务有几个子任务"，而拼版是个可选
节点——详情页勾了「在流程中启用图片拼版」才把它算进流程（用户 2026-10-03
口径："子任务到底有几个需要根据详情决定"）。所以判据是**勾没勾**，
不是"生不生效"（生效还要至少一页，那是 `imposition_active` 的口径）。

⚠️ 这里**只读 enabled 一个键**，不走 `load_imposition_doc`：那份文档
逐页带 rect/rotation，200 页的书能有几百 KB，列表页每个任务都要读一次，
没必要把整份版面都反序列化。缺文件/坏文件一律当"没启用"。

##### `save_imposition_doc(task_id: str, doc: dict) -> bool`

写拼版文档，返回是否真的写了。

任务目录已删除时跳过（与 `save_pages` 同规矩：不把已删任务重新
创建出来）。

---

## `desktop.store.json_io`

源码：[`desktop/store/json_io.py`](../../desktop/store/json_io.py)

JSON 持久化的原子读写工具。

任务状态全部存在 JSON 文件里，一旦写入过程中进程崩溃/断电，直接
`write_text` 会留下半截文件；而读取侧把解析失败当作"没有数据"，
结果是全部任务或执行历史静默消失。因此统一改为：

1. 写入同目录的临时文件，`fsync` 落盘后 `os.replace` 原子替换；
2. 读取失败时不返回空值，而是把损坏文件改名成 `*.corrupt-<时间>`
   保留现场，再返回默认值——避免用户"数据被悄悄清空"。

### 模块常量

| 名称     | 值       |
| -------- | -------- |
| \_SUFFIX | `".tmp"` |

### 模块函数

| 函数                                                  | 说明                                                          |
| ----------------------------------------------------- | ------------------------------------------------------------- |
| `read_json(path: Path, default)`                      | 读取 JSON；文件不存在返回 default，损坏则备份后返回 default。 |
| `write_json(path: Path, data, indent: int=1) -> None` | 原子写 JSON（临时文件 + fsync + os.replace）。                |

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

| 方法                                                                  | 说明                                                                    |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `pages_path(task_id: str) -> Path`                                    | 当前任务的页面清单文件：任务目录下的 pages.json。                       |
| `load_pages(task_id: str) -> list[dict]`                              | 读取页面清单；文件缺失或格式异常时返回空列表。                          |
| `save_pages(task_id: str, pages: list[dict]) -> None`                 | 写回页面清单；任务目录已删除时跳过（不重建目录）。                      |
| `refresh_pages_from_dir(task_id: str, directory: Path) -> list[dict]` | 用某阶段输出目录重建页面清单（大任务当前的页集合）。                    |
| `print_pages_path(task_id: str) -> Path`                              | 待打印列表文件：任务目录下的 print.json。                               |
| `load_print_doc(task_id: str) -> dict \| None`                        | 读取 print.json 全文（含 area/border/pages）；缺失或非字典时返回 None。 |
| `save_print_doc(task_id: str, doc: dict) -> None`                     | 写回 print.json；任务目录已被删除时静默跳过（不重建目录）。             |
| `load_print_pages(task_id: str) -> list[dict]`                        | 只取 print.json 的 pages 列表；无文档时返回空列表。                     |
| `save_print_pages(task_id: str, entries: list[dict]) -> None`         | 只替换 print.json 的 pages 字段，保留 area/border 等其它配置。          |

---

## `desktop.store.runs`

源码：[`desktop/store/runs.py`](../../desktop/store/runs.py)

阶段运行历史（runs.json）：每个阶段保留最近多次执行的记录，最新在前。

结构：{stage: [record, ...]}
record: {run_id, status, parameters, done, total, started_at, finished_at,
output_path, error}
历史记录既用于页面状态渲染（最新一条），也作为阶段面板的历史配置选项。
`error` 只在失败时写：worker 起不来的那类失败（0 条事件、0.2 秒退出）
以前在记录里只有 `done=0 total=0`，事后完全没法查。

### 模块常量

| 名称            | 值   |
| --------------- | ---- |
| MAX_RUN_HISTORY | `20` |

### `class RunMixin`

runs.json 读写。

#### 方法

| 方法                                                                                                                                                           | 说明                                                               |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `runs_path(task_id: str) -> Path`                                                                                                                              | 运行历史文件：任务目录下的 runs.json。                             |
| `create_stage_run(task_id: str, stage: str, parameters: dict, resume: bool=False) -> str`                                                                      | 登记一次新的阶段执行并返回 run_id。                                |
| `set_progress(task_id: str, run_id: str, done: int, total: int) -> None`                                                                                       | 按 run_id 更新 done/total；run_id 不在任何阶段时静默忽略。         |
| `finish_stage(task_id: str, run_id: str, status: str, output_path: str \| None=None, progress: tuple[int, int] \| None=None, error: str \| None=None) -> None` | 结束某次运行：写入 status/finished_at/output_path（可选 error）。  |
| `list_stage_runs(task_id: str, stage: str) -> list[dict]`                                                                                                      | 某阶段的历史执行记录，最新在前。                                   |
| `all_stage_runs(task_id: str) -> dict[str, list[dict]]`                                                                                                        | 整份运行历史（**一次读盘**），键为阶段名、值为最新在前的记录列表。 |
| `stage_states(task_id: str) -> dict[str, dict]`                                                                                                                | 每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。             |

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
转瞬即逝的 toast，记录里若也只有 `done=0 total=0`，事后就彻底查不出
原因（用户报「提交失败但没说为什么」，只能靠猜）。

##### `all_stage_runs(task_id: str) -> dict[str, list[dict]]`

整份运行历史（**一次读盘**），键为阶段名、值为最新在前的记录列表。

给"跨阶段比对时间戳"这类一次要看全的场景用：逐个 `list_stage_runs()`
会把整份 runs.json 读 N 遍（任务多跑过几次就有几十上百 KB）。

##### `stage_states(task_id: str) -> dict[str, dict]`

每个阶段最近一次运行的状态与进度（页面步骤条渲染用）。

`status/done/total` 取自最近一次运行；`completed` 表示该阶段历史上
是否成功执行过——重试失败不应把已经产出结果的步骤变回未完成。

---

## `desktop.store.store`

源码：[`desktop/store/store.py`](../../desktop/store/store.py)

TaskStore：任务、阶段、页面标注的统一文件存储入口。

### `class TaskStore(TaskMixin, RunMixin, PageManifestMixin, AnnotationMixin, DraftMixin, ImpositionMixin, UIStateMixin)`

唯一数据入口：组合任务/运行/页面/标注/暂存/拼版/界面状态七个 Mixin，
统一读写文件存储。

数据根目录下含 tasks/（每任务一子目录）及各 JSON 清单
（tasks.json/runs.json/boxes.json/sizes.json/pages.json/print.json）；
每任务目录下另有 drafts/<阶段>.json（用户改过但未执行的参数暂存）、
drafts/imposition.json（图片拼版的选择态 + 逐页版面）与 ui.json
（上次停留的步骤，用于再次打开任务时回到那一步）。

#### 方法

| 方法                                | 说明           |
| ----------------------------------- | -------------- |
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

| 方法                                                                                                      | 说明                                                             |
| --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `find_tasks(source_hash: str) -> list[dict]`                                                              | 按源文件指纹查重，返回全部命中的任务记录（可能多条）。           |
| `list_tasks() -> list[dict]`                                                                              | 全部任务，按 updated_at 倒序（最近改动的排在前面）。             |
| `get_task(task_id: str) -> dict \| None`                                                                  | 按任务号取任务记录；不存在返回 None。                            |
| `create_task(source_path: Path, source_hash: str, name: str, duplicate_confirmed: bool=False) -> str`     | 新建任务并返回任务号（四位零填充）。                             |
| `update_task(task_id: str, status: str) -> None`                                                          | 更新任务状态与 updated_at；任务号不存在时静默忽略。              |
| `delete_task(task_id: str) -> bool`                                                                       | 删除任务及其中间产物，返回是否真的删掉。                         |
| `task_dir(task_id: str) -> Path`                                                                          | 任务根目录：tasks/<任务号>。                                     |
| `stage_dir(task_id: str, stage: str) -> Path`                                                             | 某阶段的输出目录：tasks/<任务号>/stages/<阶段>。                 |
| `artifact(task_id: str, stage: str, port: str='pages') -> Path`                                           | 某阶段某端口的产物绝对路径（**落点的唯一入口**）。               |
| `extract_output_dir(task_id: str) -> Path`                                                                | 提取图片直接位于 stages/extract（无 PDF 名/嵌套子目录）。        |
| `rembg_output_dir(task_id: str) -> Path`                                                                  | 步骤三最终图片目录（「提交本次任务」产出，print 阶段从此取图）。 |
| `rembg_preview_output_dir(task_id: str) -> Path`                                                          | 「生成预览」产出的整页去底预览图目录（中间产物，不参与 print）。 |
| `imposition_output_dir(task_id: str) -> Path`                                                             | 「图片拼版」产出的成品拼版页图目录（列表顺序即页序）。           |
| `print_output_pdf(task_id: str) -> Path`                                                                  | print 阶段产物 print.pdf 的完整路径。                            |
| `stage_input(task_id: str, stage: str, port: str='pages', imposition_active: bool=False) -> Path \| None` | 按**连线**解析某阶段某端口的输入绝对路径。                       |
| `stage_output_dir(task_id: str, stage: str) -> Path`                                                      | 返回某阶段（GUI）应写入的输出目录。                              |
| `workset_dir(task_id: str) -> Path`                                                                       | 已废弃：检测/去底直接读 extract 输出目录，不再物化输入副本。     |
| `runs_config_dir(task_id: str) -> Path`                                                                   | 子进程执行配置（run-\*.json / detect-config.json）。             |
| `source_thumbnails_dir(task_id: str) -> Path`                                                             | 源 PDF 页缩略图：导入即生成，PDF 预览直接复用，永不清理。        |
| `rembg_thumbnails_dir(task_id: str) -> Path`                                                              | 第四步缩略图缓存：提交阶段（rembg_submit）随最终图片一并生成，   |
| `copy_source_to_task(task_id: str, source_path: Path) -> Path`                                            | 导入时在任务目录下保留一份源文件副本（原子落地）。               |
| `source_copy_path(task_id: str) -> Path \| None`                                                          | 任务目录里的 PDF 备份路径；没有备份返回 None。                   |
| `ensure_source_copy(task_id: str) -> Path \| None`                                                        | 保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。 |

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

⚠️ Windows 上 PDF 被后台渲染线程打开时 `rmtree` 抛 PermissionError，
原先 `ignore_errors=True` 会让它**静默残留**——列表里显示已删除，
磁盘上目录还在。这里重试若干次再判定失败，失败时保留任务让用户重试。

##### `task_dir(task_id: str) -> Path`

任务根目录：tasks/<任务号>。

⚠️ **必须校验形状**（2026-09-26 审计）：`task_id` 会被直接拼进路径，而
`delete_task` 对它做 `rmtree`。`tasks.json` 就在用户的文档目录下、可被
外部编辑或别的工具写坏，一旦出现 `"id": "..\..\somewhere"` 就会
**越界删除任务目录之外的东西**。这里只认 `create_task` 生成的形状。

##### `artifact(task_id: str, stage: str, port: str='pages') -> Path`

某阶段某端口的产物绝对路径（**落点的唯一入口**）。

⚠️ 这四个 `*_output_dir` 方法以前各自写死了路径，是"加一步要改四处"
的根源；现在它们都转调到这里，而落点表
（:data:`desktop.steps.ports.STAGE_LOCATIONS`）是唯一事实来源。
加一步 = 加一行表，不用动 store。

##### `imposition_output_dir(task_id: str) -> Path`

「图片拼版」产出的成品拼版页图目录（列表顺序即页序）。

拼版节点**生效**时（选择态为真且有拼版页），第四步「生成 PDF」与它的
待打印列表一律从这里取图；否则仍从 `rembg_output_dir` 取。

##### `stage_input(task_id: str, stage: str, port: str='pages', imposition_active: bool=False) -> Path | None`

按**连线**解析某阶段某端口的输入绝对路径。

⚠️ 这是 BPM 化的关键入口：调用方不再问"第三步的图片在哪"，而是问
"这一步的 `pages` 输入在哪"——连线（谁供给它）由
:data:`desktop.steps.ports.SUPPLIERS` 决定，`imposition_active`
是那条唯一的**条件连线**（拼版生效时换上游）。

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
`desktop/workers/serial_jobs.py`），而详情页/预览随时会来读这份
副本，所以走 `copy_file_atomic`：写 `.part` 再 `os.replace`，
别人不会读到半截 PDF。

##### `source_copy_path(task_id: str) -> Path | None`

任务目录里的 PDF 备份路径；没有备份返回 None。

⚠️ 后续所有操作（详情页预览、extract 入参…）**都必须用它**，不能用
`task['source_path']`：源文件在用户磁盘上，会被移动/改名/删除，
一走就「渲染失败」。备份随任务走，任务才是自包含的。

##### `ensure_source_copy(task_id: str) -> Path | None`

保证任务目录里有 PDF 备份；缺了就按索引里的 source_path 补一份。

老任务（导入时复制失败）或备份被误删时靠它自愈；源也一起没了就
返回 None，调用方负责提示。

---

## `desktop.store.ui_state`

源码：[`desktop/store/ui_state.py`](../../desktop/store/ui_state.py)

界面状态（`ui.json`）：与"用户上次看到哪"有关的小状态，分两层记。

**任务级**——`tasks/<任务号>/ui.json`（删除任务即清掉）：

    {"last_stage": "rembg"}      # 上次在这个任务里停留的步骤 key

**为什么记 key 而不是下标**：流程里的步骤会增减（「图片拼版」虚线节点就是
条件出现的可选步骤），下标一旦错位就会把用户送到**另一个**步骤去；key 是按
语义匹配的，步骤没了自然"匹配不上"，调用方据此回落第一步。

key 取自 `desktop.store.tasks`：`STAGES` 里的一项，或伪步骤
`IMPOSITION_STAGE`（"imposition"）。

**全局**——数据根目录下的 `ui.json`（跨任务共享，只一项）：

    {"last_task": "0012", "source_hash": "…"}

程序重启后靠它找到"上次待的那个任务"，再由该任务自己的 `last_stage`
落到具体步骤——两层记录各管一半。`source_hash` 是防撞号的：任务号
**顺序复用**（删掉 0012 再新建，新任务也叫 0012），指纹对不上说明这个号
已经是别的任务，恢复时当"任务不存在"处理。

⚠️ 只做「读—写」，不碰 Qt。

### `class UIStateMixin`

`ui.json` 的读写（任务级 + 全局）。

#### 方法

| 方法                                                | 说明                                                                 |
| --------------------------------------------------- | -------------------------------------------------------------------- |
| `app_ui_path() -> Path`                             | 全局界面状态文件：数据根目录下的 `ui.json`（跨任务共享）。           |
| `load_last_task() -> dict \| None`                  | 上次停留的任务记录 `{"id":…, "source_hash":…}`；没有/写坏返回 None。 |
| `save_last_task(task_id: str) -> bool`              | 记录「上次停留的任务」，程序重启后直接回到这里。                     |
| `ui_state_path(task_id: str) -> Path`               | 任务界面状态文件：`tasks/<任务号>/ui.json`。                         |
| `load_last_stage(task_id: str) -> str \| None`      | 上次停留的步骤 key；没有记录/格式不对返回 None。                     |
| `save_last_stage(task_id: str, stage: str) -> bool` | 记录上次停留的步骤 key，返回是否真的写了。                           |

##### `load_last_task() -> dict | None`

上次停留的任务记录 `{"id":…, "source_hash":…}`；没有/写坏返回 None。

恢复方拿到后**必须**用 `get_task` + 指纹比对确认"这个号还是当初
那个任务"（见模块注释的防撞号说明），不能只看 id 就往里跳。

##### `save_last_task(task_id: str) -> bool`

记录「上次停留的任务」，程序重启后直接回到这里。

只在任务真实存在时写（不给不存在的任务留指针）；指纹一并入库，
见 :meth:`load_last_task`。

##### `save_last_stage(task_id: str, stage: str) -> bool`

记录上次停留的步骤 key，返回是否真的写了。

任务目录已删除时跳过（与 `save_pages`/`save_imposition_doc`
同一条规矩：不把已删任务重新创建出来）。文件里只覆盖 `last_stage`
一项，将来加别的界面状态互不影响。

---

## `desktop.ui.color_picker`

源码：[`desktop/ui/color_picker.py`](../../desktop/ui/color_picker.py)

文字颜色选择器：触发器按钮 + 弹出面板（内置常用色块 + 完整取色）。

用户 2026-10-01 定的三件事（图片编辑 → 文字工具）：

1. **常用色块搬进面板里**——原来 6 个色块散在选项行上，既挤、又和"颜色"这个
   概念分了家；现在统一收进选择器，选项行只留一个颜色按钮；
2. 选择器要**好看**：当前色预览、饱和度/明度方块、色相条、常用色、十六进制
   输入，全部走 `desktop.ui.theme` 的令牌，跟其它界面同一套配色；
3. 任意色仍要能取（色相/明度方块 + 十六进制可输入）。

## 为什么不用 qfluentwidgets 的 `ColorPickerButton`

- 它把常用色块留在**外面**（本需求正是要收进去）；
- 它开的是 488×696 的遮罩大对话框 `ColorDialog`，而且本应用**不加载 .qm
  翻译**，里面全是英文 `OK` / `Cancel` / `Edit Color`，与全中文界面不搭。

⚠️ 面板里所有可点控件都是 `NoFocus`：选项行一旦抢走键盘焦点，画布上正在
就地编辑的文字块就丢焦点、光标消失（用户 2026-10-01 报的"字号不生效"根因
就是焦点被抢）。触发器在面板关闭时补发 `panelClosed`，宿主据此把焦点还给
文字块，接着打字不中断。

### 模块常量

| 名称        | 值    |
| ----------- | ----- |
| SWATCH_SIZE | `30`  |
| PANEL_WIDTH | `268` |

### `class SwatchButton(QAbstractButton)`

面板里的预设色块：圆角方块，悬停描边、选中打勾。

底色描边是必需的：白粉/浅色块压在白色面板上，没有描边就"不存在"。
打勾颜色按底色明度自适应（亮底用墨色、暗底用白色），任何色都看得清。

#### 方法

| 方法                                                 | 说明                                                |
| ---------------------------------------------------- | --------------------------------------------------- |
| `__init__(color: QColor, name: str='', parent=None)` | —                                                   |
| `color() -> QColor`                                  | 这个色块代表的颜色。                                |
| `is_selected() -> bool`                              | 当前是否被标为"选中的那一个"。                      |
| `set_selected(selected: bool) -> None`               | —                                                   |
| `enterEvent(event) -> None`                          | Qt 事件覆写：鼠标移入时进入高亮态。                 |
| `leaveEvent(event) -> None`                          | Qt 事件覆写：鼠标移出时恢复常态。                   |
| `paintEvent(event) -> None`                          | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class ColorArea(QWidget)`

饱和度 / 明度方块：横轴 = 饱和度（左灰右艳），纵轴 = 明度（上亮下暗）。

底色用**三层渐变**叠出来（纯色相 → 白到透明 → 透明到黑），而不是逐像素
算 HSV：200×120 的方块逐像素在 Python 里要几十毫秒，拖动色相条时会卡。
渐变结果按 (尺寸, 色相) 缓存，拖动游标时一次都不用重画。

#### 方法

| 方法                                                  | 说明                                                |
| ----------------------------------------------------- | --------------------------------------------------- |
| `__init__(parent=None)`                               | —                                                   |
| `set_hsv(hue: float, sat: float, val: float) -> None` | 程序化同步（不发 `picked`）。                       |
| `paintEvent(event) -> None`                           | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |
| `mousePressEvent(event) -> None`                      | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。        |
| `mouseMoveEvent(event) -> None`                       | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。      |

### `class HueBar(QWidget)`

色相条：0~359 的彩虹渐变，拖动/点击改色相。

#### 方法

| 方法                             | 说明                                                |
| -------------------------------- | --------------------------------------------------- |
| `__init__(parent=None)`          | —                                                   |
| `set_hue(hue: float) -> None`    | 程序化同步（不发 `picked`）。                       |
| `paintEvent(event) -> None`      | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |
| `mousePressEvent(event) -> None` | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。        |
| `mouseMoveEvent(event) -> None`  | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。      |

### `class ColorPickerPopup(QWidget)`

颜色面板（弹出层）：当前色 + 明度/饱和度方块 + 色相条 + 常用色 + 十六进制。

⚠️ 自己开一个 `Qt.Popup` 顶层窗口，而不是用 `RoundMenu`：面板里有可
输入的 `QLineEdit`，塞进 QMenu 里键盘事件会被菜单抢走，十六进制根本没法
敲。`Qt.Popup` 自带"点外面就关"的语义，正是要的。

#### 方法

| 方法                                                          | 说明                                              |
| ------------------------------------------------------------- | ------------------------------------------------- |
| `__init__(color: QColor, swatches: Iterable=(), parent=None)` | —                                                 |
| `color() -> QColor`                                           | 面板当前颜色。                                    |
| `set_color(color: QColor, notify: bool=False) -> None`        | 程序化设色（不发 `colorChanged` 除非 `notify`）。 |
| `hideEvent(event) -> None`                                    | Qt 事件覆写：隐藏时收尾。                         |

### `class ColorPickerButton(QAbstractButton)`

文字颜色触发器：色点 + 十六进制 + 下拉箭头；点开弹出颜色面板。

自带绘制（不走 qfluentwidgets 的 `ColorPickerButton`）：那个是个 96×32
的纯色块，看不出当前色值，也不带下拉指示。

#### 方法

| 方法                                                                                 | 说明                                                |
| ------------------------------------------------------------------------------------ | --------------------------------------------------- |
| `__init__(color: QColor, swatches: Iterable=(), title: str='文字颜色', parent=None)` | —                                                   |
| `color() -> QColor`                                                                  | 当前颜色。                                          |
| `set_color(color: QColor, notify: bool=False) -> None`                               | 程序化设色（同步面板，不发信号除非 `notify`）。     |
| `popup() -> ColorPickerPopup \| None`                                                | 当前面板（没开过/已销毁则 None）——自测用。          |
| `sizeHint() -> QSize`                                                                | Qt 覆写：建议尺寸。                                 |
| `minimumSizeHint() -> QSize`                                                         | Qt 覆写：最小建议尺寸。                             |
| `enterEvent(event) -> None`                                                          | Qt 事件覆写：鼠标移入时进入高亮态。                 |
| `leaveEvent(event) -> None`                                                          | Qt 事件覆写：鼠标移出时恢复常态。                   |
| `paintEvent(event) -> None`                                                          | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

---

## `desktop.ui.font_setup`

源码：[`desktop/ui/font_setup.py`](../../desktop/ui/font_setup.py)

缺中文字体时的启动引导：体检 → 一键从软件源安装 → 失败给手装命令。

为什么必须是"阻塞式引导"而不是一句 warning：缺中文字体时 PDF 里的标题、
页码会静默退回 Helvetica，检测框标注退回 ASCII 的 `L`/`R`/`U`——
**产物已经错了，而流程一路绿灯**。与其让用户加工到第四步才发现汉字是方块，
不如在进门前把话说清楚。

分工严格遵守分层：

- 「有没有字体、该装哪个包、失败算网络还是权限」全部在
  `utils.font_setup`（纯标准库，可自测、可命令行复用）；
- 本模块只管 **Qt 外壳**：体检结果要不要弹窗、按钮状态、流式日志、用户勾选
  "以后不提示"。判断逻辑一行都不在这里。

线程：安装要跑 apt/dnf 并可能弹系统的 pkexec 授权框，必须进子线程，
否则界面卡死；日志与结果都通过 **绑到本对话框方法**的信号回到主线程
（跨线程自动排队，不需要 connect_queued 中继——接收者是主线程的 QObject）。

### 模块常量

| 名称           | 值                                     |
| -------------- | -------------------------------------- |
| SKIP_ENV       | `"GUJI_SKIP_FONT_CHECK"`               |
| \_SETTINGS_KEY | `"fontCheck/skip"`                     |
| \_MONO_FONT    | `"Consolas, 'Courier New', monospace"` |

### `class FontInstallWorker(QThread)`

子线程里跑 `install_cjk_fonts`，把输出逐行抛回主线程。

单独一个类的原因：`utils.font_setup.install_cjk_fonts` 里会有 pkexec
授权框阻塞十几秒到几分钟（`fonts-noto-cjk` 有上百 MB），放进主线程会
直接把窗口画成"未响应"。

#### 方法

| 方法                                   | 说明 |
| -------------------------------------- | ---- |
| `__init__(packages=None, parent=None)` | —    |
| `run() -> None`                        | —    |

### `class FontFixDialog(QDialog)`

缺字体引导框：自动安装 / 复制手装命令 / 暂时跳过。

#### 方法

| 方法                          | 说明                                                                        |
| ----------------------------- | --------------------------------------------------------------------------- |
| `__init__(plan, parent=None)` | plan 是 `utils.font_setup.install_plan()` 的候选（可能为空 = 无法自动装）。 |
| `closeEvent(event) -> None`   | 关窗前先停掉还在跑的安装线程，避免子进程变成孤儿。                          |
| `installed() -> bool`         | 本次会话里是否真的装上了中文字体。                                          |

### 模块函数

| 函数                                    | 说明                                                  |
| --------------------------------------- | ----------------------------------------------------- |
| `font_check_suppressed() -> bool`       | 用户是否勾过「不再提示」。                            |
| `reset_font_check() -> None`            | 清掉「不再提示」，下次启动重新体检（自测 / 排错用）。 |
| `ensure_cjk_fonts(parent=None) -> bool` | 启动体检：没有中文字体就弹引导框。                    |

#### `ensure_cjk_fonts(parent=None) -> bool`

启动体检：没有中文字体就弹引导框。

正常情况（Windows、装了中文字体的 Linux）会**立刻静默返回 True**；
`GUJI_SKIP_FONT_CHECK=1` 可整体跳过（打包冒烟与 GUI 自测）。

---

## `desktop.ui.fonts`

源码：[`desktop/ui/fonts.py`](../../desktop/ui/fonts.py)

界面字体：统一的字体族解析与构造，以及「文字工具」的可选字体清单。

从 `desktop/ui/widgets.py` 拆出（见 docs/dev/refactor-modularity.md §3.B）。
`ui_font` 跟「控件」没什么关系，却被日志面板、分段开关等多处共用；留在
widgets 里会让 `segmented_toggle` 反向 import widgets，形成循环导入。

### 模块常量

| 名称               | 值     |
| ------------------ | ------ |
| \_FONT_FAMILY      | `None` |
| \_TEXT_FONTS_CACHE | `None` |

### 模块函数

| 函数                                                        | 说明                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------ |
| `ui_font(size: int=T.SIZE_BODY, bold: bool=False) -> QFont` | 统一的界面字体（族名 + 像素字号）。                          |
| `text_font_families(refresh: bool=False) -> list[str]`      | 文字工具可选字体：**中文字体在前**，其后是几个常用西文字体。 |

#### `ui_font(size: int=T.SIZE_BODY, bold: bool=False) -> QFont`

统一的界面字体（族名 + 像素字号）。

族名走 `resolve_font_family()` 解析出的系统实际字体，与
`apply_app_style` 给整个应用设置的字体保持一致；否则在没有
`Microsoft YaHei UI` 的机器上，这些控件会各自回退到默认字体，
和应用其它文字对不上。

#### `text_font_families(refresh: bool=False) -> list[str]`

文字工具可选字体：**中文字体在前**，其后是几个常用西文字体。

⚠️ 离屏（`QT_QPA_PLATFORM=offscreen`）与精简镜像里 `QFontDatabase`
可能是空的——此时退回 `utils.fonts` 的候选族名 + 西文常量，保证下拉不空、
控件可用；真实机器上取到的当然是系统里**实际装了**的字体。

结果缓存：逐个族查 `writingSystems()` 在 200+ 字体的机器上要 ~150ms，
而文字工具每次切换都会重建选项行。装了新字体想立刻看到就传 `refresh`。

---

## `desktop.ui.help_dialog`

源码：[`desktop/ui/help_dialog.py`](../../desktop/ui/help_dialog.py)

用户手册：Markdown → HTML → 系统默认浏览器渲染。

为什么不再用 `QTextBrowser` / `QTextDocument` 直接渲染 Markdown：

- Qt 的 `setMarkdown()` 只支持 GFM 的**子集**，表格、围栏代码块、深层嵌套
  列表的渲染都很勉强，长文档读起来发闷；
- `setHtml()` 走的是**同一条富文本引擎**，CSS 只是 HTML 的一个小子集
  （没有 flex、没有伪元素、 `nth-child` 之类选择器也不全），多绕一圈
  换不来真正的样式自由度；
- `QWebEngineView` 能彻底解决，但会拖进 `QtWebEngineProcess.exe` 与
  百 MB 级资源包，和 `guji.spec` 现有的 excludes 裁剪策略直接冲突。

于是走第三条路：**用 Python 的 `markdown` 库（纯 Python、无二进制依赖）
把 `docs/guide/*.md` 转成完整 HTML，内嵌匹配应用主题的 CSS，交给系统默认
浏览器打开。**

**两条路，按模式分流**（判据见 `prefer_static_manual`，是"打包与否"而不是
"文件在不在"）：

| 模式             | 手册来源                                    | 截图               | 何时用                    |
| ---------------- | ------------------------------------------- | ------------------ | ------------------------- |
| 开发（源码运行） | 每次现渲染到 %TEMP%                         | 绝对 `file://` URL | md 随时在改，改完立刻可见 |
| 打包（生产）     | 构建期预生成的 `desktop/static/manual.html` | **内联 data URI**  | 内容已定死，点开即用      |

生产侧预生成是必须的，不只是"快一点"：`docs/guide/` 整目录**不进安装包**
（对最终用户无用的 md 与截图，白占体积），所以安装后既读不到 md、也找不到
截图——只有把手册连同截图压成一个自包含 HTML 放进包里才成立。

这样做的好处：

1. **零重量依赖** —— `markdown` 纯 Python 单包；且**只有构建环境需要它**，
   打包产物里已把它排除（运行时不渲染 md，缺了它也只是退化成占位提示）；
2. **完整 GFM** —— 表格、围栏代码块、嵌套列表都按规范渲染；
3. **图片永远不碎** —— 开发靠 `<base>` 指回 `docs/guide/`，生产靠内联，
   两种模式都不存在"相对路径解析错"的可能；
4. **样式自由** —— 真实浏览器渲染，CSS 不受 Qt 富文本子集限制；
5. **性能与产物一致** —— 生产端点开就是浏览器那一下，没有首次渲染延迟，
   也不再有"临时文件堆积 + 防缓存文件名"那套绕法。

三条关键实现约束（改动时别踩）：

- **开发模式的 `<base>` 必须指向手册目录且带结尾斜杠**：HTML 落在临时目录，
  不设 base 就会把 `screenshots/guide/*.png` 解析成碎图；
- **指南之间的互链要改成页内 tab 跳转**：`user-guide.md` 里有
  `[cli.md]\(cli.md)`，浏览器会把 .md 当纯文本显示，必须改写为
  `#tab-cli` 交给 JS 切页；
- **打开时只把「原生路径」交给系统，绝不传 `file:///` URI**：见
  `_open_with_system` 的注释，这是「点了按钮没反应」的元凶。

### 模块常量

| 名称               | 值                                                             |
| ------------------ | -------------------------------------------------------------- |
| \_HTML_PREFIX      | `"guji_manual_"`                                               |
| \_KEEP_RECENT      | `3`                                                            |
| STATIC_MANUAL_NAME | `"manual.html"`                                                |
| \_JS               | `" (function () {   const tocNav = document.getElementById(…"` |

### 模块函数

| 函数                                                             | 说明                                                                         |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `manual_dir() -> Path`                                           | 手册目录（源码与打包两种模式下都可用）。                                     |
| `static_manual_path() -> Path`                                   | 构建期预生成的自包含手册路径（**只有打包版才有**；可能不存在）。             |
| `prefer_static_manual() -> bool`                                 | 当前是否该走「构建期静态手册」这条路。                                       |
| `generate_manual_html(entry: str \| None=None) -> Path`          | 把手册渲染成一个带分段开关的 HTML 文件（临时目录），返回其路径。             |
| `generate_static_manual(output_path: Path \| None=None) -> Path` | **构建期**把手册渲染成单个自包含 HTML（默认 `desktop/static/manual.html`）。 |
| `open_manual(entry: str \| None=None) -> Path`                   | 打开用户手册，返回被打开的 HTML 路径。                                       |

#### `manual_dir() -> Path`

手册目录（源码与打包两种模式下都可用）。

与 `package_dir()` 同源：源码模式下 `desktop/` 的上一级就是仓库根，
打包后数据文件由 `guji.spec` 的 `gui_datas` 落到 `_internal/`，
`package_dir()` 在 frozen 下返回 `_MEIPASS/desktop`，再上一级同样是
资源根，因此 `package_dir().parent / "docs" / "guide"` 两种模式通用。

#### `prefer_static_manual() -> bool`

当前是否该走「构建期静态手册」这条路。

判据是**打包与否（frozen）**，不是「静态文件在不在」：

- 开发模式：`docs/guide/*.md` 随时在改，必须每次现渲染，改完立刻能看到
  效果；若按「文件存在」判断，仓库里哪天留了一个 `manual.html`（手动生成
  过一次、或从安装包里拷回来的），开发者就会一直看到旧内容；
- 生产模式（PyInstaller 打包后）：手册内容在构建那一刻就定死了，直接打开
  预生成的静态 HTML，不渲染、不写临时文件。

`GUJI_MANUAL_STATIC=1` / `=0` 可强制指定，供冒烟与自测用。

#### `generate_manual_html(entry: str | None=None) -> Path`

把手册渲染成一个带分段开关的 HTML 文件（临时目录），返回其路径。

entry 为 `MANUAL_ENTRIES` 里的键，决定默认激活哪个标签页；
不传则激活第一项。**这是打包版用不到的老路**：打包版读
`docs/guide/manual.html`（见 `generate_static_manual`），只有源码模式
（没有静态文件）才现渲染到这里。

⚠️ `<base>` 指向手册目录（带结尾斜杠）是图片能加载的唯一保证：
Markdown 里写的是 `screenshots/guide/xxx.png` 这样的相对路径，
而 HTML 落在临时目录，不设 base 就会相对临时目录解析成碎图。

#### `generate_static_manual(output_path: Path | None=None) -> Path`

**构建期**把手册渲染成单个自包含 HTML（默认 `desktop/static/manual.html`）。

打包版点「用户手册」时直接打开这个文件：不渲染 md、不读截图、不写临时文件。
自包含（截图内联成 data URI）是硬要求——`docs/guide/` 整目录**不进安装包**，
安装后既没有 md 也没有 screenshots，任何外部引用都会变成碎图。

⚠️ 源码模式下调用**务必传 `output_path`**（写进待打包目录），别默认写到
`desktop/static/manual.html`——那个位置会被打包版优先打开，万一留在仓库里
容易让人以为改了 md 就生效（实际必须重新打包）。

#### `open_manual(entry: str | None=None) -> Path`

打开用户手册，返回被打开的 HTML 路径。

**按模式分流**（见 `prefer_static_manual`）：

- 打包版（frozen）：直接打开构建期预生成的 `docs/guide/manual.html`——
  不渲染、不写临时文件，点下去就只剩开浏览器那一下；万一产物里没有这个
  文件（老包 / 构建步骤没跑到），退回现渲染，功能不受影响；
- 开发模式：**一律现渲染**到临时目录，改完 md 立刻看到新内容，不会被仓库里
  可能存在的旧静态文件顶掉。

返回路径是为了调用方（或测试）能拿到产物做进一步处理。
打不开浏览器时不抛异常——手册文件仍然在，用户可以手动打开，
界面上会弹一个带路径的提示框。

⚠️ 不要给 URL 加 `?v=<时间戳>` 去防缓存：Windows 上最终还是要走系统 shell，
查询串会被当成路径的一部分，实测地址栏里根本不出现。临时文件靠**文件名本身
带时间戳**（见 `_HTML_PREFIX`）保证 URL 唯一；静态文件靠"重装即替换"。

⚠️ 不要把 `html_path.as_uri()` 直接丢给系统（见 `_open_with_system`）。

---

## `desktop.ui.icons`

源码：[`desktop/ui/icons.py`](../../desktop/ui/icons.py)

自定义矢量图标：补 qfluentwidgets 内置图标里没有的图形（带圆圈的问号）。

## 为什么不能直接继承 `FluentIconBase` 了事

`FluentIcon.path()` 返回的是 **Qt 资源里的文件路径**
`:/qfluentwidgets/images/icons/Xxx_black.svg`，基类两条渲染链都靠
`path.endswith('.svg')` 判断「是文件还是源码」：

- `FluentIconBase.icon()`：只有 `path.endswith('.svg') and color` 时才包
  `SvgIconEngine`，否则 `QIcon(path)` —— 把 SVG **源码字符串** 当文件名，
  得到一个空图标；
- `FluentIconBase.render()`：只有 `endswith('.svg')` 时才 `drawSvgIcon`
  （内存渲染），否则同样按文件走 `QIcon(path).pixmap()`。

所以自绘 SVG 必须 **两个方法都重写**：只重写 `icon()` 的话，按钮自绘走的是
`paintEvent → _drawIcon → render()`，而 `PushButton.paintEvent` 在
`icon().isNull()` 时直接 return，结果就是「只剩文字、图标不见了」。

## 几何

24×24 视图，外圈直径与内置 `INFO` 图标一致（几乎满幅，r=10、描边 1.6），
问号高度 ~12（与 INFO 里 `i` 的高度相当），整体上下居中，不出现内置
`HELP` / `QUESTION` 那种被裁到边框上的偏移。

### 模块常量

| 名称            | 值                                                             |
| --------------- | -------------------------------------------------------------- |
| QUESTION_CIRCLE | `"<svg xmlns="http://www.w3.org/2000/svg" width="24" height…"` |
| SCAN_TEXT_BOX   | `"<svg xmlns="http://www.w3.org/2000/svg" width="24" height…"` |
| PDF_FILE        | `"<svg xmlns="http://www.w3.org/2000/svg" width="24" height…"` |

### `class SvgIcon(FluentIconBase)`

用**内存里的 SVG 源码**造图标（内置 FluentIcon 没有的图形）。

模板里用 `{c}` 占位颜色，由 `getIconColor(theme)`（black/white）或
调用方显式给的 `color` 填入；深浅色主题自动跟随。

#### 方法

| 方法                                                                                 | 说明                                                         |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------ |
| `__init__(template: str)`                                                            | —                                                            |
| `path(theme: Theme=Theme.AUTO) -> str`                                               | 返回填好颜色的 SVG 源码（不是文件路径）。                    |
| `icon(theme: Theme=Theme.AUTO, color: QColor \| str \| None=None) -> QIcon`          | 包成 `QIcon`：必须走 `SvgIconEngine`，否则得到空图标。       |
| `render(painter, rect, theme: Theme=Theme.AUTO, indexes=None, **attributes) -> None` | 自绘入口（按钮/菜单走这条）：直接把源码交给 `QSvgRenderer`。 |

### `class CustomIcon`

自定义图标集合：用法与 `FluentIcon` 一致（直接传给按钮等控件）。

### 模块函数

| 函数                          | 说明                                                   |
| ----------------------------- | ------------------------------------------------------ |
| `resolve_nav_icon(name: str)` | 按 `nav_icon` 的字符串取导航图标对象（壳层专用入口）。 |

#### `resolve_nav_icon(name: str)`

按 `nav_icon` 的字符串取导航图标对象（壳层专用入口）。

- `"svg:名字"` → :class:`CustomIcon` 里的自绘图（内置图标没有的图形，
  如检测文本框的取景框）；
- 其它 → `FluentIcon` 的同名成员（历史行为，`spec.nav_icon` 的注释
  与各步骤的取值都按这个写）。

名字不存在时**抛 AttributeError**——图标名是代码里写死的常量，写错了
应该在启动第一时间炸出来，而不是渲染出一列空导航。

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
qfluentwidgets 的 `SegmentedWidget`——后者是给页面导航设计的
（底部指示条、无法单独禁用某一项），而这里需要「还没有去底色结果时
禁用其中一项」的语义。

**选中态要一眼看得出**，所以三处一起给对比度（只靠白底滑块是不够的，
浅底卡片上白滑块几乎看不出来）：

- 轨道用 `SURFACE_SUNKEN`（比 `SURFACE_SOFT` 明显重一档的灰底），
  白滑块压在上面才有边界；
- 选中项文字用主色 `ACCENT` 且加粗，未选中项用 `INK_SOFT`；
- 禁用项转 `INK_DISABLED`，比「未选中但可用」再淡一档，不会混淆。

只有用户点击才发 `current_changed`；`set_current` 是程序化切换，
不发信号（否则回流切换会自我递归）。

#### 方法

| 方法                                                    | 说明                                                  |
| ------------------------------------------------------- | ----------------------------------------------------- |
| `__init__(items: Sequence[Sequence[str]], parent=None)` | items 为 `[(键, 文案), ...]`，默认选中第一项。        |
| `current() -> str`                                      | 当前选中项的键。                                      |
| `set_current(key: str) -> None`                         | 程序化切换选中项，不发 `current_changed`。            |
| `set_item_enabled(key: str, enabled: bool) -> None`     | 启用/禁用某一项；禁用项不可悬停、不可点击，文案变灰。 |
| `is_item_enabled(key: str) -> bool`                     | 某一项当前是否可用。                                  |
| `sizeHint() -> QSize`                                   | Qt 覆写：建议尺寸。                                   |
| `minimumSizeHint() -> QSize`                            | Qt 覆写：最小建议尺寸。                               |
| `mouseMoveEvent(event) -> None`                         | Qt 事件覆写：移动（拖拽 / 缩放中的实时更新）。        |
| `leaveEvent(event) -> None`                             | Qt 事件覆写：鼠标移出时恢复常态。                     |
| `mousePressEvent(event) -> None`                        | Qt 事件覆写：按下（选中 / 开始拖拽或绘制）。          |
| `paintEvent(event) -> None`                             | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。   |

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

| 函数                           | 说明                                                   |
| ------------------------------ | ------------------------------------------------------ |
| `resolve_font_family() -> str` | 挑一个系统里存在的中文字体族，避免落到无衬线默认字体。 |
| `apply_app_style(app) -> None` | 统一字体/主题色/全局样式（在创建主窗口前调用）。       |
| `global_stylesheet() -> str`   | 生成应用全局样式表（底色 / 滚动条 / 表格边框）。       |

#### `global_stylesheet() -> str`

生成应用全局样式表（底色 / 滚动条 / 表格边框）。

只给窗口与 #pageRoot 上色，避免把嵌套的 QStackedWidget 刷灰；其余外观
交给 qfluentwidgets 自绘，不与它的代理/动画打架。字体族不在这里设，
由 `apply_app_style` 通过 `app.setFont` 统一指定。

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

| 名称             | 值          |
| ---------------- | ----------- |
| INK              | `"#1A1D21"` |
| INK_SOFT         | `"#4E5862"` |
| INK_FAINT        | `"#8B949D"` |
| INK_DISABLED     | `"#B7BEC5"` |
| CANVAS           | `"#F3F5F7"` |
| SURFACE          | `"#FFFFFF"` |
| SURFACE_SOFT     | `"#F7F9FB"` |
| SURFACE_HOVER    | `"#EEF3F6"` |
| SURFACE_SUNKEN   | `"#E4EAEF"` |
| BORDER           | `"#E2E7EC"` |
| BORDER_SOFT      | `"#EDF1F4"` |
| BORDER_STRONG    | `"#C9D1D8"` |
| ACCENT           | `"#0E7C8B"` |
| ACCENT_HOVER     | `"#0B6A77"` |
| ACCENT_SOFT      | `"#E6F2F4"` |
| SUCCESS          | `"#0F7B3F"` |
| SUCCESS_SOFT     | `"#E7F4EC"` |
| WARNING          | `"#B9760A"` |
| WARNING_SOFT     | `"#FBF2E2"` |
| DANGER           | `"#C93A3A"` |
| DANGER_HOVER     | `"#B03333"` |
| DANGER_PRESSED   | `"#962B2B"` |
| DANGER_SOFT      | `"#FBEAEA"` |
| NEUTRAL          | `"#7A838C"` |
| NEUTRAL_SOFT     | `"#EFF2F4"` |
| SPACE_XS         | `4`         |
| SPACE_SM         | `8`         |
| SPACE_MD         | `12`        |
| SPACE_LG         | `16`        |
| SPACE_XL         | `24`        |
| RADIUS_SM        | `6`         |
| RADIUS_MD        | `10`        |
| RADIUS_LG        | `14`        |
| SCROLLBAR_WIDTH  | `10`        |
| SCROLLBAR_MARGIN | `2`         |
| SIZE_CAPTION     | `12`        |
| SIZE_BODY        | `13`        |
| SIZE_LABEL       | `14`        |
| SIZE_SUBTITLE    | `16`        |
| SIZE_TITLE       | `22`        |
| SIZE_HERO        | `26`        |

### 模块函数

| 函数                                                  | 说明                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------ |
| `status_colors(status: str) -> tuple[str, str]`       | 状态 → (前景色, 底色)，未知状态按未执行处理。                |
| `status_label(status: str) -> str`                    | 状态键 → 中文短标签，未知或空状态回退到"未知"。              |
| `danger_button_qss(padding: str \| None=None) -> str` | 危险操作按钮（删除）的实例级样式表，各处删除按钮共用这一份。 |

#### `status_label(status: str) -> str`

状态键 → 中文短标签，未知或空状态回退到"未知"。

取值来自 STATUS_LABELS（如 "running"→"执行中"）。

#### `danger_button_qss(padding: str | None=None) -> str`

危险操作按钮（删除）的实例级样式表，各处删除按钮共用这一份。

实例样式表会把 qfluent 自带按钮样式整体顶掉，四个状态必须写全——
缺哪态哪态就退回默认渲染、没有视觉反馈。

`padding`：给**不定尺寸**的按钮传 qfluent 按钮同款内边距
（"5px 12px 6px 12px"），高度才会跟旁边 qfluent 按钮一致；
定尺寸按钮（如任务表格 52×30）不传。

---

## `desktop.ui.widgets`

源码：[`desktop/ui/widgets.py`](../../desktop/ui/widgets.py)

基础视觉控件：卡片、分区标题、状态胶囊、空状态、页头。

统一用自绘而非样式表：Qt 的样式表引擎会在子树里有任何 `setStyleSheet`
时把 QFrame 底色刷成白色，之前步骤条的卡片底就因此被整片盖掉过。自绘
（`paintEvent`）不受此影响，颜色完全可控，也不会污染子控件。

表单控件则相反，一律用 qfluentwidgets 的现成控件（它们自带绘制与焦点
动画），只把高度对齐到 `CONTROL_HEIGHT`——见 `combo_box()`。

### 模块常量

| 名称               | 值    |
| ------------------ | ----- |
| CONTROL_HEIGHT     | `33`  |
| HELP_TOOLTIP_WIDTH | `26`  |
| HELP_BUBBLE_WIDTH  | `360` |

### `class Card(QFrame)`

白底圆角卡片，可选描边与内边距。

#### 方法

| 方法                                                                                                                                                           | 说明                                                        |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `__init__(parent=None, padding: int=T.SPACE_LG, spacing: int=T.SPACE_MD, radius: int=T.RADIUS_LG, fill: str=T.SURFACE, border: str=T.BORDER, layout: str='v')` | layout="v"/"h" 选择内部盒方向；padding 同时作为四边内边距。 |
| `set_colors(fill: str \| None=None, border: str \| None=None) -> None`                                                                                         | 改底色/描边后立即重绘；传 None 表示该项保持不变。           |
| `paintEvent(event) -> None`                                                                                                                                    | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。         |

##### `__init__(parent=None, padding: int=T.SPACE_LG, spacing: int=T.SPACE_MD, radius: int=T.RADIUS_LG, fill: str=T.SURFACE, border: str=T.BORDER, layout: str='v')`

layout="v"/"h" 选择内部盒方向；padding 同时作为四边内边距。

内部布局通过 `self.box` 暴露，调用方直接往里加控件。

### `class Divider(QFrame)`

1px 水平分隔线。

#### 方法

| 方法                        | 说明                                                |
| --------------------------- | --------------------------------------------------- |
| `__init__(parent=None)`     | 固定高 1px、水平拉伸的水平分隔线。                  |
| `paintEvent(event) -> None` | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class SectionTitle(QLabel)`

控制面板里的分组小标题（比正文略重，前面带一条主色短竖线）。

#### 方法

| 方法                               | 说明                                                |
| ---------------------------------- | --------------------------------------------------- |
| `__init__(text: str, parent=None)` | 左侧预留 10px 给主色竖线，控件固定高 20px。         |
| `paintEvent(event) -> None`        | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class StatusChip(QWidget)`

状态胶囊：圆点 + 文案 + 浅色底，用于表格里的阶段状态。

#### 方法

| 方法                                                         | 说明                                                |
| ------------------------------------------------------------ | --------------------------------------------------- |
| `__init__(text: str='', status: str='pending', parent=None)` | status 决定圆点与底色，取值见 theme.status_colors。 |
| `set_state(text: str, status: str) -> None`                  | 更新文案与状态色，并按新文案重算最小尺寸。          |
| `sizeHint() -> QSize`                                        | Qt 覆写：建议尺寸。                                 |
| `minimumSizeHint() -> QSize`                                 | Qt 覆写：最小建议尺寸。                             |
| `paintEvent(event) -> None`                                  | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class ProgressLine(QWidget)`

细进度条：圆角轨道 + 主色填充。

比 qfluent 的 ProgressBar 更克制（没有文字、没有内边距），
适合嵌在参数卡片里表示"这一步执行到多少页"。

**总量未知**（上限为 0）时自动切成"来回滑动"的未知态：并不是所有执行
一开始就知道总量（print 的合成阶段、拼版合成、detect 找齐框之前都是），
这时若还画一根不动的空条，用户会以为界面卡住了。

#### 方法

| 方法                                           | 说明                                                                 |
| ---------------------------------------------- | -------------------------------------------------------------------- |
| `__init__(parent=None, height: int=6)`         | height 为轨道像素高度（默认 6）。                                    |
| `setRange(minimum: int, maximum: int) -> None` | 设置上限，并把当前值夹到 [0, maximum]；上限为 0 时归零（切未知态）。 |
| `setValue(value: int) -> None`                 | 设置当前值（超出上限时夹到上限）。                                   |
| `value() -> int`                               | 当前值。                                                             |
| `maximum() -> int`                             | 上限（0 = 总量未知）。                                               |
| `ratio() -> float`                             | 完成比例（0.0~1.0）；尚未设置上限时返回 0.0。                        |
| `is_unknown() -> bool`                         | 当前是不是"总量未知"的滑动态。                                       |
| `finish() -> None`                             | 走到终点（成功收尾时用）；总量未知时什么也不做。                     |
| `refresh_animation() -> None`                  | 按当前可见性与上限重新启停动画（从隐藏切到显示时调一次）。           |
| `showEvent(event) -> None`                     | Qt 事件覆写：显示时刷新状态。                                        |
| `hideEvent(event) -> None`                     | Qt 事件覆写：隐藏时收尾。                                            |
| `paintEvent(event) -> None`                    | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。                  |

##### `finish() -> None`

走到终点（成功收尾时用）；总量未知时什么也不做。

给上层一个**公开**的收尾入口，是为了不必伸手去摸 `_maximum`——
进度行组件只该用这里与 :meth:`setRange` / :meth:`setValue`。

##### `refresh_animation() -> None`

按当前可见性与上限重新启停动画（从隐藏切到显示时调一次）。

单独开这个公开方法，是因为 Qt 的 `showEvent` 只在**控件自己**被
隐藏过再显示时才重入；父容器整块显隐（独立页初始只有输入区那种情形）
不保证触发它，滑块就会停在原地不动。

### `class Pill(QWidget)`

无圆点的文字胶囊（用于源文件名、计数等标签）。

#### 方法

| 方法                                                                              | 说明                                                |
| --------------------------------------------------------------------------------- | --------------------------------------------------- |
| `__init__(text: str='', fg: str=T.INK_SOFT, bg: str=T.SURFACE_SOFT, parent=None)` | fg/bg 分别是文字色与胶囊底色。                      |
| `setText(text: str) -> None`                                                      | 更新文案并按新文案重算宽度。                        |
| `text() -> str`                                                                   | 返回胶囊当前文案。                                  |
| `sizeHint() -> QSize`                                                             | Qt 覆写：建议尺寸。                                 |
| `minimumSizeHint() -> QSize`                                                      | Qt 覆写：最小建议尺寸。                             |
| `paintEvent(event) -> None`                                                       | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。 |

### `class EmptyState(QWidget)`

浅色空状态：图标 + 主文案 + 补充说明 + 可选提示。

原先各预览控件用的是深灰底 + 白字占位，面积大且显得像报错；这里
统一成浅底 + 灰色图标 + 说明文字，和"还没有内容"的语义一致。

#### 方法

| 方法                                                        | 说明                                                                |
| ----------------------------------------------------------- | ------------------------------------------------------------------- |
| `__init__(text: str, hint: str='', icon=None, parent=None)` | icon 传 FluentIcon，会渲染成 44px 灰色图标；hint 为空时该行不占位。 |
| `set_text(text: str) -> None`                               | 更新主文案。                                                        |
| `set_hint(hint: str) -> None`                               | 更新补充说明；传空串则隐藏该行。                                    |

### `class PageHeader(QWidget)`

页面头部：左侧标题 + 副标题，右侧操作区。

带一条底部分隔线，把页头和内容区分开——原来只有一行孤立的标题，
和下面的内容混在一起，层次不清。

#### 方法

| 方法                                                  | 说明                                                      |
| ----------------------------------------------------- | --------------------------------------------------------- |
| `__init__(title: str, subtitle: str='', parent=None)` | 固定高 64px；右侧操作区通过 `self.actions` 布局添加按钮。 |
| `set_subtitle(text: str) -> None`                     | 设置副标题文案，空串则隐藏副标题行。                      |
| `paintEvent(event) -> None`                           | Qt 事件覆写：自绘控件外观（本项目控件不走样式表）。       |

### `class HelpButton(TransparentToolButton)`

问号帮助按钮：hover 弹 ToolTip 气泡，点击弹/收说明 Flyout。

各阶段面板（`StagePanel`）与「图片拼版」面板的标题旁都用它——
说明文字不再平铺在标题下方占高度，全部收进这个按钮。

#### 方法

| 方法                                                        | 说明 |
| ----------------------------------------------------------- | ---- |
| `__init__(title: str='', description: str='', parent=None)` | —    |

### 模块函数

| 函数                                                                                                    | 说明                                                                     |
| ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| `apply_to(widget: QWidget, size: int=T.SIZE_BODY, bold: bool=False, color: str \| None=None) -> QLabel` | 给 QLabel 统一设置字体与颜色。                                           |
| `bold_button(button: QWidget, bold: bool) -> None`                                                      | 把按钮文字加粗 / 还原（高亮用）。                                        |
| `combo_box(items: Iterable[str \| Sequence[Any]] \| None=None, width: int \| None=None) -> ComboBox`    | 创建与输入框同高的下拉框（统一表单的行高节奏）。                         |
| `icon_pixmap(icon, size: int=24, color: str=T.INK_FAINT) -> QPixmap`                                    | 把 FluentIcon 渲染成指定颜色的 pixmap（用于空状态插画）。                |
| `install_button_pointer_cursor(app: QApplication) -> None`                                              | 给整个应用的按钮启用 hover 手型光标（见 :class:`_ButtonCursorFilter`）。 |

#### `apply_to(widget: QWidget, size: int=T.SIZE_BODY, bold: bool=False, color: str | None=None) -> QLabel`

给 QLabel 统一设置字体与颜色。

⚠️ **上色有两条路，按控件类型分流**：

- qfluentwidgets 的标签（`FluentLabelBase` 子类：CaptionLabel / BodyLabel /
  StrongBodyLabel / TitleLabel / SubtitleLabel）**不读调色板**——它们用
  `setStyleSheet("color: …")` 自己画（`setTextColor`）。对它们只 `setPalette`
  的话调色板里明明写着红色、**渲染出来仍是黑的**（2026-09-23 用户报「这个红色
  没有修改过来」就是这么来的）。所以必须走 `setTextColor`。
- 原生 `QLabel` 仍走调色板（原来的做法；对它用样式表反而会牵连子控件，
  见模块头那段"样式表会把 QFrame 底色刷白"的教训）。

判据用 `isinstance` 而不是 `hasattr(widget, "setTextColor")`：
`QTextEdit` 也有同名方法，但它设的是"以后输入的文字颜色"，语义完全不同。

#### `bold_button(button: QWidget, bold: bool) -> None`

把按钮文字加粗 / 还原（高亮用）。

⚠️ **别用 `setStyleSheet("…{font-weight:bold;}")` 干这件事**：qfluentwidgets
给每个按钮的样式表是**整串 setStyleSheet 进去的**（约 7.6KB），里面有一条
`PushButton[hasIcon=true] { padding: 5px 12px 6px 36px; }` —— 图标是
`paintEvent` 手绘在左边 12px 处的，**全靠这 36px 左边距让居中的文字让开**。
整串替换后 padding 全没了，图标就画到文字上了（2026-09-23 用户报
「执行本子任务按钮中的图片显示在了文字上面」）。`setFont` 只动字体，
不碰样式表；按钮 qss 里没有 `font:` 规则，所以控件字体生效。

#### `combo_box(items: Iterable[str | Sequence[Any]] | None=None, width: int | None=None) -> ComboBox`

创建与输入框同高的下拉框（统一表单的行高节奏）。

直接在表单里 `ComboBox()` 会比同列的 `LineEdit`/`SafeSpinBox` 矮
6px（见 `CONTROL_HEIGHT` 的说明），所以下拉框一律用本函数建。

`items` 传字符串序列时只填显示文案；传 `(文案, 值)` 二元组序列时
值写进 `itemData`，读出用 `currentData()`。`width` 非空则固定宽度
（用于节点行这类需要横向对齐的窄列）。

---

## `desktop.ui.window_size`

源码：[`desktop/ui/window_size.py`](../../desktop/ui/window_size.py)

窗口尺寸适配：把「默认尺寸」夹进当前屏幕的可用区域，并摆到合适位置。

背景（2026-10-01 用户报障「不最大化就显示不完整 / 被任务栏遮挡」）：
窗口尺寸一直是**逻辑像素的固定值**（主窗口 1440×920），既不看屏幕、也不看
系统缩放。实测这台机器 1920×1080 @125% → 逻辑屏 1536×864，减去任务栏后
**可用高度只有 824**：920 > 824，窗口底部（日志状态条、第四步按钮）永远
压在任务栏后面，非最大化下够不着。1366×768 或 150%/175% 缩放的机器更紧，
可用区域甚至**小于窗口的最小尺寸**——那种情况下用户连拖小都做不到。

规则（**只夹不涨**，屏幕够大时与改动前逐像素一致）：

1. 期望宽高先扣掉**窗口边框预留**（标题栏那 30 逻辑像素不算在客户端尺寸里，
   不扣就会出现"客户端刚好等于屏幕、却仍被标题栏顶出去"），再各夹到可用区域的
   :data:`FIT_RATIO`；
2. 最小宽高**跟着夹**——否则"可用高 672 < 最小高 720"时窗口被卡死，
   用户没有任何办法把它缩进屏幕；
3. 位置也一并摆好：有可见父窗口的弹窗居中到父窗口（Qt 的默认观感，这里
   显式写出来才夹得住），顶层窗口居中到屏幕可用区域；居中与夹紧都按**含边框**
   的外框尺寸算，最后再把外框夹回可用区域，免得 1440 宽的窗口在 1536 宽的屏
   上被系统摆出半截。

⚠️ 两个必须守住的边界：

- **只在构造那一刻算一次**，不做持续约束（不装事件过滤器、不重写
  `resizeEvent`）。自测与截图脚本会显式 `resize()` 到指定尺寸
  （`tests/gui_shot.py`、`tests/selftests/_context.py`），持续夹紧会让
  它们拿到别的尺寸，护栏随即失真。
- 拿不到屏幕信息时**原样返回、不做任何猜测**：宁可维持旧行为，也不要凭空
  给一个尺寸（离屏/无头环境下 `primaryScreen()` 可能为空）。

### 模块常量

| 名称      | 值     |
| --------- | ------ |
| FIT_RATIO | `0.95` |

### 模块函数

| 函数                                                                                                      | 说明                                                               |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `available_area(reference=None) -> QRect \| None`                                                         | 参考控件所在屏幕的**可用区域**（已扣除任务栏）；拿不到返回 None。  |
| `fit_sizes(preferred: QSize, minimum: QSize \| None, area: QRect \| None) -> tuple[QSize, QSize \| None]` | 把期望尺寸与最小尺寸夹进 `area`，返回 (客户端尺寸, 最小尺寸)。     |
| `apply_window_size(window, preferred: QSize, minimum: QSize \| None=None) -> QSize`                       | 把 `window` 设成「期望尺寸夹进屏幕可用区域」的样子，返回最终尺寸。 |

#### `fit_sizes(preferred: QSize, minimum: QSize | None, area: QRect | None) -> tuple[QSize, QSize | None]`

把期望尺寸与最小尺寸夹进 `area`，返回 (客户端尺寸, 最小尺寸)。

纯函数（不碰 Qt 控件），便于直接断言边界；`area` 为空时原样返回。

#### `apply_window_size(window, preferred: QSize, minimum: QSize | None=None) -> QSize`

把 `window` 设成「期望尺寸夹进屏幕可用区域」的样子，返回最终尺寸。

调用点全是各窗口 `__init__` 里原本写 `resize()` / `setMinimumSize()`
的位置，一行换一行。

---

## `desktop.utils.files`

源码：[`desktop/utils/files.py`](../../desktop/utils/files.py)

文件与目录相关的通用工具：哈希、自然排序、阶段输出清单、预览缓存键。

### 模块常量

| 名称               | 值             |
| ------------------ | -------------- | ----- |
| THUMBNAIL_EDGE     | `256`          |
| SINGLETASK_DIRNAME | `"singletask"` |
| \_SAFE_CHARS       | `"<>:"/\\      | ?\*"` |

### 模块函数

| 函数                                                                                         | 说明                                                                          |
| -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `guji_data_dir() -> Path`                                                                    | GUI 数据根目录：用户文档目录下的 guji。                                       |
| `safe_dirname(name: str) -> str`                                                             | 把任意标题洗成能当目录名的一串（去掉非法字符、收敛空白）。                    |
| `singletask_dir(subtask: str) -> Path`                                                       | 独立任务区下某个**子任务**的目录：`~/Documents/guji/singletask/<子任务>`。    |
| `migrate_legacy_singletask_dirs() -> list[str]`                                              | 把按旧标题建的 `singletask/<中文名>/` 搬到新名（见 `_LEGACY_SUBTASK_DIRS`）。 |
| `singletask_thumbnails_dir(subtask: str, book: str \| Path \| None=None) -> Path`            | 子任务的**页缩略图缓存**：`singletask/<子任务>/thumbnails[/<书>]`。           |
| `book_key(book: str \| Path) -> str`                                                         | 一本书在缓存目录里的唯一名字：`<文件名去后缀>-<大小>-<路径指纹前8位>`。       |
| `image_thumb_cache_path(subtask: str, image: str \| Path, edge: int=THUMBNAIL_EDGE) -> Path` | 一张**源图片**在 singletask 缓存里的缩略图路径。                              |
| `image_thumbs_dir(subtask: str, edge: int=THUMBNAIL_EDGE) -> Path`                           | 一批**图片源**的缩略图缓存**目录**：`singletask/<子任务>/thumbs/<边长>`。     |
| `default_open_dir() -> Path`                                                                 | 文件对话框的默认打开目录：用户文档目录。                                      |
| `project_root() -> Path`                                                                     | 项目根目录（`desktop` 包的上一级）。                                          |
| `package_dir() -> Path`                                                                      | `desktop` 包目录（源码与 PyInstaller 打包两种模式下都可用）。                 |
| `file_hash(path: Path, chunk_size: int=1024 * 1024) -> str`                                  | 流式计算文件 SHA-256（分块读取，避免大 PDF 撑爆内存）。                       |
| `copy_file_atomic(source: Path, target: Path) -> Path`                                       | 把 source 复制到 target，**要么没有、要么完整**。                             |
| `natural_key(name: str)`                                                                     | 生成自然排序键：数字段按整数、其余转小写，使 2 排在 10 前。                   |
| `list_stage_images(directory: Path) -> list[Path]`                                           | 某阶段输出目录中的图片（自然排序）。                                          |

#### `migrate_legacy_singletask_dirs() -> list[str]`

把按旧标题建的 `singletask/<中文名>/` 搬到新名（见 `_LEGACY_SUBTASK_DIRS`）。

**幂等**：目标已存在就跳过（只当新目录存在的老数据，不会来回搬）；旧目录
**不删**——里面可能有用户还在意的东西，误删不可恢复。

返回实际搬动过的目录名（给自测与日志用）。

#### `singletask_thumbnails_dir(subtask: str, book: str | Path | None=None) -> Path`

子任务的**页缩略图缓存**：`singletask/<子任务>/thumbnails[/<书>]`。

导入 PDF 时**立刻**渲染到这里（用户 2026-10-03："从上一层导入PDF，没有立即
提取缩略图"）。命中即复用，缺页才渲染——所以第二次打开同一本书几乎不花时间。

⚠️⚠️ **必须带 `book` 分一层目录**（2026-10-03 自测当场逮到）：缩略图文件名是
**页号**（`0001.jpg`…），而这个缓存目录是**所有书共用**的。不按书分开，A 书
第 1 页的缩略图会被当成 B 书第 1 页的命中缓存 ⇒ 翻页翻出**别本书的内容**。
（任务流程那边没事，是因为 `tasks/<id>/thumbnails/source` 一本书一个目录。）

目录名用 `书名-大小-路径指纹前 8 位`：同名不同书靠指纹区分，同一本书改名后
仍能命中旧缓存。

⚠️ **只放缓存，不放产物**：模块页的输出目录仍然默认在源文件旁边
（:meth:`desktop.steps.spec.StepSpec.default_output`），别把用户已经习惯的
产物位置改掉。

#### `book_key(book: str | Path) -> str`

一本书在缓存目录里的唯一名字：`<文件名去后缀>-<大小>-<路径指纹前8位>`。

路径参与指纹：`D:/书/甲.pdf` 与 `E:/书/甲.pdf` 同名同大小，但不是同一本书。

#### `image_thumb_cache_path(subtask: str, image: str | Path, edge: int=THUMBNAIL_EDGE) -> Path`

一张**源图片**在 singletask 缓存里的缩略图路径。

`singletask/<子任务>/thumbs/<边缘边长>/<book_key>.jpg`

用户 2026-10-03 定的口径：**所有独立任务的左侧都显示缩略图**，且缩略图
统一缓存在 `~/Documents/guji/singletask` 下（PDF 用
:func:`singletask_thumbnails_dir` 的按页编号那套，这里是按图文件本身）。

- **按图分文件**（不是按页号）：图片源的条目名五花八门（`1.jpg` /
  `右-01.png`…），按页号命名必然撞名，撞名就是**别人的图被当成本图的
  缓存**——与 PDF 那条护栏（`book_key` 分目录）是同一个坑。
- **按边长分层**：`ThumbStrip.decode_edge` 会随 dpr 变，1.5 倍屏要
  234px、小图要 156px。混在一个目录里，改一次 dpr 就会拿旧尺寸的缓存
  当命中（条目里发糊），所以边长进目录名。
- 键里带**大小与路径指纹**（复用 :func:`book_key`）：同名不同图靠它区分，
  同图改名后仍能命中旧缓存。

#### `image_thumbs_dir(subtask: str, edge: int=THUMBNAIL_EDGE) -> Path`

一批**图片源**的缩略图缓存**目录**：`singletask/<子任务>/thumbs/<边长>`。

与 :func:`image_thumb_cache_path` 是同一套规则的两种用法：那个给**单张图**
的缓存文件路径，这个给**目录**（一批图共用、或宿主需要"重渲一张"时交给
`ImageThumbCacheWorker`）。

⚠️ 目录**只按「子任务 + 边长」分层**，不按单图键：单图键里带着大小与路径
指纹，拿它当目录名既很长，也会让"同一张图被编辑后尺寸变了"直接换目录
（旧缓存全成孤儿）。⚠️ 边长必须进目录名（`decode_edge` 随 dpr 变）。

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
`desktop/static/icon.png`；数据文件由 spec 的 `datas` 额外落到
`_internal/desktop/`，因此 frozen 下直接指向 `sys._MEIPASS`。

#### `copy_file_atomic(source: Path, target: Path) -> Path`

把 source 复制到 target，**要么没有、要么完整**。

⚠️ 不能用裸 `shutil.copy2(source, target)`：导入后的复制是在**后台
线程**里跑的，而详情页/PDF 预览随时会来看任务目录里的副本。直接往
target 写，复制途中它就 `is_file() == True` 了，读到的却是半截
PDF——渲染失败、甚至静默出一张残缺页。

所以先写同目录的临时文件，落盘后再 `os.replace` 原子改名。临时名带
.part 后缀，`glob("*.pdf")` 之类的兜底查找也扫不到它。

⚠️ 临时名里要带 **pid + 线程号**：同一个副本可能被两个地方同时复制
（后台队列复制中，用户已经点进详情页 → `ensure_source_copy` 又复制
一遍）。共用一个临时名的话两边会交叉写同一个文件；各自写自己的临时
文件则内容相同，谁最后 replace 都对。

---

## `desktop.utils.icon`

源码：[`desktop/utils/icon.py`](../../desktop/utils/icon.py)

窗口图标的圆角渲染。

图标的**形状由像素决定**——窗口标题栏/任务栏/Alt-Tab 都是 Windows 拿
Qt 给的位图去画，Qt 管不了圆不圆角。所以要在交给 `setWindowIcon` 之前
把源图裁成圆角，这样：

- 源图（`desktop/static/icon.png`）保持直角原图，**换图标不用手工修图**；
- 圆角比例只有一处定义（`ICON_RADIUS_RATIO`），与打包用的
  `tools/make_icon.py::DEFAULT_RADIUS_PCT` 保持一致；
- 同时往 QIcon 里塞多个尺寸帧——Windows 会按场景挑帧，避免它自己把
  295px 缩到 16px 时把圆角外的透明平均成半透明（浅色标题栏上会显出一圈淡边）。

### 模块常量

| 名称              | 值     |
| ----------------- | ------ |
| ICON_RADIUS_RATIO | `0.08` |
| MIN_CORNER_PX     | `2.0`  |
| \_ALPHA_CUT       | `140`  |

### 模块函数

| 函数                                                                                      | 说明                                                        |
| ----------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| `effective_ratio(size: int, ratio: float=ICON_RADIUS_RATIO) -> float`                     | 按帧尺寸自适应圆角比例（16px 需 ~12.5% 才能真正裁掉四角）。 |
| `rounded_pixmap(source: QPixmap, size: int, ratio: float=ICON_RADIUS_RATIO) -> QPixmap`   | 把源图等比居中裁成 `size × size` 的圆角图（圆角外透明）。   |
| `rounded_window_icon(path: Path \| str, ratio: float=ICON_RADIUS_RATIO) -> QIcon \| None` | 读取图片并生成圆角窗口图标；读取失败返回 None。             |

#### `rounded_window_icon(path: Path | str, ratio: float=ICON_RADIUS_RATIO) -> QIcon | None`

读取图片并生成圆角窗口图标；读取失败返回 None。

返回的 QIcon 内含 16~256 多帧，小帧已做 alpha 二值化。

---

## `desktop.worker`

源码：[`desktop/worker.py`](../../desktop/worker.py)

Process entry for one GUI stage task (worker 子进程统一入口)。

The worker emits JSON Lines on stdout so the GUI remains independent from
heavy libraries. 阶段执行器按职责拆分在 desktop/stages/ 包：

- desktop.stages.events 事件输出 + print 拦截/进度解析
- desktop.stages.detect_stage detect（YOLO 检测文本框）
- desktop.stages.generic_stage 通用 CLI 阶段 + extract 渲染
- desktop.stages.print_stage print（效果图合成 + 生成 PDF）
- desktop.stages.rembg_stage rembg_submit（最终图片合成）

本文件只负责进程初始化与阶段路由。

### 模块函数

| 函数            | 说明                                                    |
| --------------- | ------------------------------------------------------- |
| `main() -> int` | GUI worker 子进程入口：读取 --config 并按阶段路由执行。 |

#### `main() -> int`

GUI worker 子进程入口：读取 --config 并按阶段路由执行。

--config 为必填，指向一个 JSON 文件路径，解析后按 mode/stage 字段分派到
对应阶段执行器（detect/extract/print/rembg_submit 等，未匹配则走通用
run_stage）。进程启动即启用 faulthandler 并统一 stdout/stderr 为 UTF-8，
以输出 JSON Lines 进度供 GUI 解析。返回阶段执行器的退出码。

⚠️ 启动期（读配置 / 解析 JSON / 路由之前）的异常一律转成 error 事件

- stderr 堆栈，绝不让它变成"静默的退出码 1"（见 `_emit_fatal`）。
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

| 方法                                   | 说明                                                      |
| -------------------------------------- | --------------------------------------------------------- |
| `__init__(source: Path, target: Path)` | source 为源文件；target 为任务目录里的副本路径。          |
| `run() -> None`                        | 执行复制：失败只报 failed，不影响任务使用源文件继续干活。 |

### `class CopyFilesWorker(QObject)`

批量复制文件到目标目录（后台线程里跑；审计 D2）。

「插入图片」「下载 PDF」原先在主线程 `shutil.copy2`——一本 463MB 的 PDF
就把界面冻住整个复制时长。现在主线程只算好 (源, 目标) 对，这里逐对复制；
单个失败不中断整批（跳过并在结果里注明）。

#### 方法

| 方法                                      | 说明 |
| ----------------------------------------- | ---- |
| `__init__(jobs: list[tuple[Path, Path]])` | —    |
| `run() -> None`                           | —    |

---

## `desktop.workers.hash_worker`

源码：[`desktop/workers/hash_worker.py`](../../desktop/workers/hash_worker.py)

文件指纹（SHA-256）后台计算。

### `class HashWorker(QObject)`

后台计算单个文件 SHA-256 的 worker（QObject，运行于子线程）。

完成时发 finished(path, hash)，异常发 failed(message)；用于导入时
异步计算源文件指纹以做任务查重。

#### 方法

| 方法                   | 说明                                                        |
| ---------------------- | ----------------------------------------------------------- |
| `__init__(path: Path)` | 待计算指纹的文件路径。                                      |
| `run() -> None`        | 执行哈希计算并通过 finished 信号回报结果（异常走 failed）。 |

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

| 方法                                                                                              | 说明                                                                       |
| ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `__init__(paths: list[Path], edge: int=96, effects: list \| None=None, crops: list \| None=None)` | 构造图片清单缩略图 worker。                                                |
| `run() -> None`                                                                                   | 逐图生成缩略图，发 thumbnail_ready(index, image, path)，结束发 completed。 |

##### `__init__(paths: list[Path], edge: int=96, effects: list | None=None, crops: list | None=None)`

构造图片清单缩略图 worker。

paths 为目标图片；edge 为缩略图最长边（默认 96）。effects/crops
与 paths 对齐：非空时先按 area/border 合成效果或按像素框裁剪，
再缩放到 edge（用于 print 列表效果预览）。

---

## `desktop.workers.imposition_worker`

源码：[`desktop/workers/imposition_worker.py`](../../desktop/workers/imposition_worker.py)

后台把图片拼版文档合成为成品页图（写 `stages/imposition`）。

为什么要后台：版面拖动/删除会频繁触发重合成，而一页拼版要打开两张原图、
缩放、旋转、alpha 合成再编 PNG——几十页叠起来在主线程做就是明显卡顿。
合成只用 PIL，不碰 Qt，也没有共享可变状态，天然适合放线程里。

⚠️ 入参 `doc` 是**构造时的快照**（调用方先落盘再把文档交进来），worker 期间
用户又改版面不会写坏文件——最多是这一批略旧，下一批（防抖到期后再跑一轮）
会覆盖成最新。

### `class ImpositionComposeWorker(QObject)`

把整份拼版文档落成一页一张的成品图（后台线程里跑）。

#### 方法

| 方法                           | 说明                                                      |
| ------------------------------ | --------------------------------------------------------- |
| `__init__(doc: dict, out_dir)` | doc 为拼版文档；out_dir 为目标目录（stages/imposition）。 |
| `run() -> None`                | 合成全部拼版页；失败只报 failed，由宿主提示并落日志。     |

### `class ImpositionPagePreviewWorker(QObject)`

把**一页拼版**合成内存预览图（后台线程里跑，不落盘）。

给画布双击空白处的「左右组合预览」弹窗用：`page` 是构造时的**快照**，
弹窗开着的时候用户继续拖版面不影响已经打开的这一张。信号口径与
`PreviewWorker` 一致（`finished(int, QImage, str)` / `failed(int, str)`），
`ImageZoomDialog` 的接线原样可用。

#### 方法

| 方法                                           | 说明                                                              |
| ---------------------------------------------- | ----------------------------------------------------------------- |
| `__init__(page: dict, longest_edge: int=1600)` | `longest_edge` 是预览密度上限；**传 0 = 不缩**（全分辨率，        |
| `run() -> None`                                | PIL 合成（services.imposition.compose_page）→ QImage → 缩到边长。 |

##### `__init__(page: dict, longest_edge: int=1600)`

`longest_edge` 是预览密度上限；**传 0 = 不缩**（全分辨率，
右键空白处「编辑图片」用：编辑器要的是与落盘成品同一分辨率的图）。

---

## `desktop.workers.preview_worker`

源码：[`desktop/workers/preview_worker.py`](../../desktop/workers/preview_worker.py)

PDF/图片渲染：整页大图、页缩略图（带磁盘缓存）与去底色效果合成。

区域合成（rembg 预览）在本线程内完成，避免主线程处理原始分辨率大图导致卡顿。

### 模块常量

| 名称                        | 值     |
| --------------------------- | ------ |
| PRINT_PREVIEW_TARGET_EDGE   | `1600` |
| PRINT_PREVIEW_MIN_PX_PER_MM | `2.0`  |
| PRINT_PREVIEW_MAX_PX_PER_MM | `8.0`  |
| THUMB_YIELD_RATIO           | `0.5`  |
| \_PDF_DOC_CACHE_MAX         | `2`    |

### `class PreviewWorker(QObject)`

渲染 PDF 某一页，或 PDF 全部页缩略图（带磁盘缓存）。

#### 方法

| 方法                                                                                                                                                                                                                                                 | 说明                                                                  |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `__init__(path: Path \| str, page: int=0, longest_edge: int \| None=1200, thumbnails: bool=False, cache_dir: Path \| None=None, effect: dict \| None=None, print_spec: dict \| None=None, render_missing: bool=True, pages: list[int] \| None=None)` | 构造预览渲染 worker。                                                 |
| `cancel() -> None`                                                                                                                                                                                                                                   | 请求中止。                                                            |
| `run() -> None`                                                                                                                                                                                                                                      | 按构造参数渲染单页大图或批量页缩略图，发出 finished/thumbnail_ready。 |

##### `__init__(path: Path | str, page: int=0, longest_edge: int | None=1200, thumbnails: bool=False, cache_dir: Path | None=None, effect: dict | None=None, print_spec: dict | None=None, render_missing: bool=True, pages: list[int] | None=None)`

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

| 函数                                                                                                                          | 说明                                                                   |
| ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `region_canvas_specs(image_size: tuple[int, int], boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list` | compose_region_output 的**纯几何**部分：返回 `[(画布尺寸, sources)]`。 |
| `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list`             | 按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。         |
| `close_cached_documents() -> None`                                                                                            | 关掉共享文档缓存里的全部文档，释放 Windows 文件句柄。                  |
| `preview_px_per_mm(page_w_mm: float, page_h_mm: float, target_edge: int=PRINT_PREVIEW_TARGET_EDGE) -> float`                  | 按纸张尺寸给出效果预览的像素密度（px/mm）。                            |
| `qt_family_for_file(path: str) -> str \| None`                                                                                | 按**字体文件**加载并取回 Qt 族名；失败返回 None。                      |
| `preview_text_font(spec, px_per_mm: float) -> QFont`                                                                          | 按 PrintTextSpec 与像素密度给出**已设好像素大小**的字体。              |
| `compose_print_page(image: QImage, plan, px_per_mm: float \| None=None) -> QImage`                                            | 按 `utils.page_layout.PrintPagePlan` 合成"打印效果"位图。              |
| `compose_outputs_horizontal(outputs: list, gap: int=12) -> QImage`                                                            | 多张输出横向拼接为一张展示图（灰底间隔，便于区分各框输出）。           |

#### `region_canvas_specs(image_size: tuple[int, int], boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list`

compose_region_output 的**纯几何**部分：返回 `[(画布尺寸, sources)]`。

不碰位图——只依据图片**尺寸**（QImageReader 读文件头即可拿到）就能
算出每张输出画布的大小与贴图来源。第三步提交据此**预先算好输出
文件名**（张数 × 名称），再并行处理各页；规则仍然只有这一份。

`full=True` 表示这一页是整幅内容(fullcontent)。整幅框本质是"大一点的
单独内容框"，**框原样参与布局**（用户 2026-09-29 改定，推翻旧的"整幅＝整页"）：

- area=4：保留框外内容 → 框归一成整页（`utils.box_geometry.whole_page_box`）；
- area=1/2/3：统一按 **area=3 的合并语义**走单框布局（不拆 `-l`/`-r`、
  不做对称镜像），几何由 border 决定：给了 border（面板默认 `"0"`）→
  紧裁「框 + border」；border 留空（None）→ 整页画布、框写回原位置（框外白）。
  三种 area 因此效果一致。

调用方通常直接传 `is_full_content(原始槽位列表)` 的结果。

#### `compose_region_output(image: QImage, boxes: list, area: int, border_mm, dpi: int=300, full: bool=False) -> list`

按 crop/cropremove 的 area/border 规则，合成"效果预览图"列表。

**几何规则来自 utils.box_geometry**（与 functions/text_region.py 的 CLI
输出共用同一份实现），本函数只负责用 QImage 把布局画出来——这样规则
不会因数像素后端不同而被复制成两份。几何部分见 `region_canvas_specs`。

与原实现的一处行为修正：area=3 + 双框 + border=None 时，并集区域现在
**写回原位置**（此前被搬到画布左上角）。规格见
docs/functions/cropremove.md:57「area=3 → 单图，ROI 写回原位置」。

`full` 语义见 `region_canvas_specs`（整幅框原样下传：area=4 保留整页、
area 1/2/3 统一按合并语义）。

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

字体族走 `_pick_content_font`（内容是标题 / 页码，仿宋优先）——与
`pdf_draw.register_fonts` 取到的字体同一种，预览与成品才对得上。

⚠️ 不能直接用 `setPointSizeF(spec.font_size_pt)`：那是固定像素大小，
而逐字步进是 `char_h_mm × px_per_mm`（随密度缩放）。两处口径不同时，
密度一变小（第四步版面编辑画布把整页缩到可视区，≈2 px/mm，远小于效果
预览的 ≈5.4 px/mm），字仍是原大小、步进却按比例缩小 → **字叠在一起**。

统一口径后：字高 = 字号(mm) × 密度，与步进同源，任何密度下都不重叠，
且与成品 PDF 的真实字号（pt → mm）一致。

`spec.font` 是用户为这段文字（标题 / 页码各自独立）指定的字体，
能解析到文件就按文件加载——与成品 PDF 用同一个字体文件。

#### `compose_print_page(image: QImage, plan, px_per_mm: float | None=None) -> QImage`

按 `utils.page_layout.PrintPagePlan` 合成"打印效果"位图。

**只画内存位图，不写任何文件**——第四步的效果预览就是它；真正生成
PDF 仍要走「生成 PDF」按钮（functions/print.py）。

几何全部取自 `plan`，而 `plan` 由 PDF 生成与预览共用，所以用户
按预览调好的边距/纸张/标题，与最终 PDF 必然一致。

---

## `desktop.workers.rembg_live_worker`

源码：[`desktop/workers/rembg_live_worker.py`](../../desktop/workers/rembg_live_worker.py)

单页实时去底色的后台 worker（第三步「改参数实时预览」专用）。

与 `PreviewWorker` 的分工：那个只负责**显示**（读图 / 按区域裁剪 / 缩放），
本 worker 负责**计算**（真正的去底色）。二者接力：本 worker 先把结果落到
临时目录，预览区再按 `live_dir` 找到它并走原有的显示管线。

去底色对整页图（数千像素）要百毫秒级 CPU，放主线程会卡住界面，因此一律
丢到 QThread 里跑。结果通过 token 回传，宿主据此丢弃"已经过期的"结果
（用户连拖两次滑块时，慢的那次回来得晚，不能覆盖新的）。

### `class RembgLiveWorker(QObject)`

一次性 worker：单页去底色 → 写临时文件。

#### 方法

| 方法                                                                         | 说明                                                         |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `__init__(image_path: str, args: dict, out_dir: str, token: object) -> None` | 参数:                                                        |
| `cancel() -> None`                                                           | 请求放弃计算。token 守卫只丢**结果**不省**算力**：连拖滑块时 |
| `run() -> None`                                                              | 线程入口：算完发 finished，异常发 failed（不抛到线程外）。   |

##### `__init__(image_path: str, args: dict, out_dir: str, token: object) -> None`

参数:
image_path: 待去底色的源图（extract 产物）。
args: rembg 面板收集的参数（offset/type/seal/…）。
out_dir: 实时暂存目录（`services.rembg_live.live_dir`）。
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

⚠️ 为什么单独成模块（不放在 `preview_worker` 里）
导入后台任务（`source_thumbnails_worker`）也要用这把锁，而
`preview_worker` 是 500+ 行的重模块（还带着第四步效果合成的整套依赖）。
从它 import 会把这些依赖拖进**启动路径**——`desktop/workers/__init__.py`
的惰性导出正是为了避免这件事。所以锁放在这个零依赖的小模块里，谁都能引。

⚠️ 谁必须走它
**任何**从 PDF 页渲位图的代码：单页预览（`PreviewWorker._render_pdf_page`）、
批量缩略图（`PreviewWorker._render_all_thumbnails`）、导入后台任务
（`SourceThumbnailsWorker._render_page`）。渲染全程攥 GIL ~105–180ms
（实测），两个渲染并行 = GIL 互相抢，界面停顿叠加成 N×180ms——用户看到的
就是「切缩略图卡、多点几下直接卡死」。串行化之后停顿上限收敛到**单次渲染**，
且不随点击次数/页数增长。

### 模块函数

| 函数                                | 说明                                                     |
| ----------------------------------- | -------------------------------------------------------- |
| `single_flight() -> threading.Lock` | 取单飞锁。用法：`with single_flight(): ...渲染一页...`。 |

#### `single_flight() -> threading.Lock`

取单飞锁。用法：`with single_flight(): ...渲染一页...`。

⚠️ 只把**渲染本身**（load_page + get_pixmap + tobytes）包进锁：写盘、
`QImage.fromData`、让出 GIL 的 sleep 都放锁外——否则别的渲染请求要陪着
等 I/O，锁的粒度就过粗了。

---

## `desktop.workers.serial_jobs`

源码：[`desktop/workers/serial_jobs.py`](../../desktop/workers/serial_jobs.py)

串行后台任务队列：同一时刻只跑一个 job，且**等界面画完再开工**。

## 为什么必须串行

导入 PDF 后要跑「复制源文件 + 渲染整本缩略图」，那是 PyMuPDF 的密集 C 调用。
原先每次导入都起一个线程、且不设上限，多个渲染线程同时跑就会争抢 GIL，
主线程的每一次文件操作都被排到 GIL 队列后面：

| 并发渲染线程              | 0     | 1    | 4     | 8     | 15         |
| ------------------------- | ----- | ---- | ----- | ----- | ---------- |
| 主线程 `create_task` 中位 | 5.5ms | 98ms | 216ms | 608ms | **1500ms** |

对照实验排除了磁盘因素：后台**纯写盘**（狂写 8KB 文件、期间落盘 1110 个文件）
对主线程 0 影响（stat 0.09ms、读 3KB 0.11ms、写 0.7ms）——是 GIL/线程调度，
不是 I/O、不是 fsync、也不是 tasks.json 的体积。串行 + 每页让出 GIL 后
主线程回到 16ms（脚本见 `.workbuddy/perf/`）。

## 为什么还要「扣住不放行」

列表出现新行必须读 N 个任务的 runs.json。无争抢时 18 个任务只要 7.5ms；
一旦和渲染线程撞上，每个文件操作都要等 GIL，实测「导入 → 看见新行」从
0.2s 变成 0.5~2.5s。所以新 job 提交后先**扣住**，等页面把列表画完调
`release()` 再开工；同时留一个超时兜底，信号丢了也不会永远不干活。

### `class SerialJobQueue(QObject)`

把一次性后台 job 串成一条队列，并支持「界面画完再放行」。

用法：`submit(worker, label, on_warning=..., on_failed=...)` 排队，
`release()` 放行，`shutdown()` 收尾。

进度信号（job_started / progress / job_finished）供页面显示「正在导入」
提示条：整本缩略图可能要跑几十秒，用户必须看得到它还在干活。

#### 方法

| 方法                                                                                                     | 说明                                                           |
| -------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `__init__(owner: QObject)`                                                                               | owner 为宿主 widget（主线程）；线程与中继都挂在它下面。        |
| `submit(worker: QObject, label: str='', on_warning=None, on_failed=None, tag: str \| None=None) -> None` | 排队一个 job；等 `release()`（或超时）后按提交顺序执行。       |
| `release() -> None`                                                                                      | 界面画完了：放行排队中的 job（重复调用无副作用）。             |
| `running_count() -> int`                                                                                 | 正在跑的 job 数（0 或 1）。                                    |
| `pending_count() -> int`                                                                                 | 排队中的 job 数。                                              |
| `current_label() -> str`                                                                                 | 正在跑的 job 的名字（没在跑就是空串）。                        |
| `busy() -> bool`                                                                                         | 还有 job 在跑或排队。                                          |
| `cancel_tag(tag: str \| None, wait_ms: int=3000) -> bool`                                                | 取消某个 tag（任务）名下的活：丢掉排队的、让在跑的收手并等它。 |
| `shutdown(wait_ms: int=800) -> None`                                                                     | 退出收尾：停表、丢弃排队的活、让当前 job 尽快退出。            |

##### `submit(worker: QObject, label: str='', on_warning=None, on_failed=None, tag: str | None=None) -> None`

排队一个 job；等 `release()`（或超时）后按提交顺序执行。

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

当前 job 的 `cancel()` 让它在下一次循环检查时收手（整本可能几千页，
不能傻等）；随后 `quit()` 结束线程事件循环。

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

| 名称               | 值    |
| ------------------ | ----- |
| FIRST_SCREEN_PAGES | `16`  |
| BATCH_PAGES        | `8`   |
| BATCH_GAP_MS       | `120` |
| GIL_YIELD_RATIO    | `0.5` |
| GIL_YIELD_MIN_MS   | `3`   |
| GIL_YIELD_MAX_MS   | `60`  |
| MIN_THUMB_BYTES    | `512` |
| FINAL_COPY_WAIT_S  | `5.0` |

### `class SourceThumbnailsWorker(QObject)`

导入 PDF 后渲染全部页面缩略图（256px，与预览查看器缓存一致）。

#### 方法

| 方法                                                                                            | 说明                                                             |
| ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `__init__(pdf_path: Path, out_dir: Path, edge: int=THUMBNAIL_EDGE, copy_to: Path \| None=None)` | 构造源 PDF 页缩略图 worker。                                     |
| `cancel() -> None`                                                                              | 请求中止：渲染循环在下一页之前退出（关程序用，不必等整本跑完）。 |
| `wait_copy(timeout: float) -> bool`                                                             | 等复制线程收手，最多 `timeout` 秒；返回是否已结束。              |
| `run() -> None`                                                                                 | 并行复制 + 逐页渲染缩略图；任务目录被删时中止并报 failed。       |

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

⚠️ **每页先查缓存**：命名与预览查看器的缓存一致（`0001.jpg`），
已存在且不比源 PDF 旧的直接跳过。否则重复导入同一份 PDF（或把任务
目录复制过来）时，80 页的书要白渲染 80 页——用户看到的正是「明明
已经有缩略图了还在重新生成」。

---

## `desktop.workers.task_rows_worker`

源码：[`desktop/workers/task_rows_worker.py`](../../desktop/workers/task_rows_worker.py)

任务列表行的读取（后台线程）。

列表页刷新要遍历全部任务、逐个读它的 `runs.json` 才能拿到四个阶段的状态。
任务一多、或单个任务的 runs 记录一多，这串读盘就会把 **UI 线程**占住——窗口
明明已经画出来了，内容却要再等一截才出现。

放到这里在后台线程读，读完一次性把整批行回传主线程渲染。只读不写，因此
与主线程的 store 访问不冲突。

⚠️ **每个任务的子任务数量不是固定的**（用户 2026-10-03 口径："任务列表子任务
到底有几个需要根据详情决定"）：「图片拼版」是可选节点，只有在任务详情里勾了
「在流程中启用图片拼版」才进流程，此时「PDF」前面多一个「拼版」胶囊；没勾的
任务仍是四个。两处判据必须同源：

- **插不插 / 详情里流程走不走** → `store.imposition_enabled()`（只看勾没勾，
  与 `ImpositionMixin.imposition_active` 同一口径）；
- **胶囊的颜色** → 再叠一层"有没有拼版页"（绿=已能出图，灰=还没拼版）。
  拼版没有 runs.json 记录（它是纯合成、不走 worker），所以状态只能这么派生。

### `class TaskRowsWorker(QObject)`

读全量任务行（只读，不落任何盘）。

#### 方法

| 方法                      | 说明                                                                     |
| ------------------------- | ------------------------------------------------------------------------ |
| `__init__(store) -> None` | store 只用于读（list_tasks / stage_states / imposition_enabled），不写。 |
| `run() -> None`           | 遍历任务生成摘要行；异常回传 failed，不抛到线程外。                      |

---

## `desktop.workers.thumb_cache_worker`

源码：[`desktop/workers/thumb_cache_worker.py`](../../desktop/workers/thumb_cache_worker.py)

**独立任务左栏缩略图的统一缓存层**（`~/Documents/guji/singletask/<子任务>/`）。

用户 2026-10-03 的要求之一是「**所有独立任务左侧显示的都是缩略图**」。此前
只有图片提取页有 PDF 页缩略图（走 `PdfViewerWidget` 自己的缩略图通道），
其余四页左栏塞的是**原图**或各自的专用预览控件——同一件「看一批图」的事在五个
页面有五种实现，缓存也无处安放。

本模块管**非 PDF 源**（一批图片）这一半：把每张图渲成
`singletask/<子任务>/thumbs/<边长>/<键>.jpg`（路径规则见
:func:`desktop.utils.files.image_thumb_cache_path`）。

PDF 源**不在这里**——它已有了一份成熟实现（`PreviewWorker` 的缩略图通道：
单飞锁、按耗时让出 GIL、原子写、命中缓存直接读、页边界可取消），再写一份必然
漂移，而且那份代码里每条注释都在解释踩过的坑。PDF 侧由
:class:`~desktop.components.viewers.pdf_page_source.PdfPageSource` 直接驱动
那个通道。

⚠️ 本模块只写**缓存**，不碰产物：模块页的输出目录仍由
:meth:`desktop.steps.spec.StepSpec.default_output` 决定（用户明确要求「生成
目录按照原先的」）。

### 模块常量

| 名称            | 值    |
| --------------- | ----- |
| MIN_THUMB_BYTES | `512` |

### `class ImageThumbCacheWorker(QObject)`

把一批**源图片**的缩略图渲进 singletask 缓存，逐张就绪即发一次。

信号口径与既有的 `ImageListWorker` 一致（`thumbnail_ready(int, QImage,
str)` / `completed` / `failed`），所以各查看器的分批装载
(:class:`~desktop.components.viewers.thumbs_loader.ThumbsMixin`) 能原样复用
——只是这里第三参数是**缓存文件路径**而不是源图路径（缓存写完前它可能是
空串：那一张仍然会显示，只是不承诺下次命中）。

#### 方法

| 方法                                                                                 | 说明                                                               |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------ |
| `__init__(paths: list[Path \| str], out_dir: Path \| str, edge: int=THUMBNAIL_EDGE)` | `paths` 为源图清单；`out_dir` 是这一批共用的缓存目录               |
| `cancel() -> None`                                                                   | 请求中止：在**下一张**之前退出（已写好的都在盘上，重进直接命中）。 |
| `cache_path(index: int) -> Path`                                                     | 第 index 张图的缓存路径（宿主拿去当 `thumb_provider` 的答案）。    |
| `run() -> None`                                                                      | 逐张：命中缓存直接读，否则渲一张并原子写盘。                       |

##### `__init__(paths: list[Path | str], out_dir: Path | str, edge: int=THUMBNAIL_EDGE)`

`paths` 为源图清单；`out_dir` 是这一批共用的缓存目录
（`singletask/<子任务>/thumbs/<边长>/`）；`edge` 为缩略图最长边。

### 模块函数

| 函数                                                                 | 说明                                                              |
| -------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `thumb_cache_file(out_dir: Path \| str, image: Path \| str) -> Path` | 一张源图在 `out_dir` 下的缓存文件名（去后缀 + 大小 + 路径指纹）。 |
| `stat_mtime(path) -> float`                                          | 文件 mtime；取不到返回 0（拿不到就当"缓存都是新的"→ 不重渲）。    |
| `cache_usable(target: Path, source_mtime: float) -> bool`            | 缓存缩略图能不能用：不比源图旧，且体积不像截断。                  |
| `decode_sized(path: Path, edge: int) -> QImage`                      | 按最长边 `edge` 缩放解码一张图（尽量不把整张原图读进内存）。      |
| `encode_jpeg(image: QImage, quality: int=80) -> bytes`               | QImage → JPEG 字节。                                              |

#### `thumb_cache_file(out_dir: Path | str, image: Path | str) -> Path`

一张源图在 `out_dir` 下的缓存文件名（去后缀 + 大小 + 路径指纹）。

⚠️ 键**必须逐图算**、不能按序号：图片源的条目名五花八门（`1.jpg` /
`右-01.png`…），按序号命名一旦清单顺序变了就会张冠李戴——拿到的是
**别张图的缓存**。这与 PDF 侧「按页号命名 ⇒ 必须按书分目录」是同一个坑。

#### `decode_sized(path: Path, edge: int) -> QImage`

按最长边 `edge` 缩放解码一张图（尽量不把整张原图读进内存）。

与 :class:`~desktop.workers.image_list_worker.ImageListWorker` 同一套做法：
`QImageReader.setScaledSize` 让解码器直接出目标尺寸；少数格式/异常文件
缩放解码会失败，回退到整图解码后内存缩放。

#### `encode_jpeg(image: QImage, quality: int=80) -> bytes`

QImage → JPEG 字节。

⚠️ `QImage.save` 只能写**文件**，这里借 `QBuffer` 拿字节——因为落盘
必须走 :func:`utils.file_utils.write_bytes_atomic`（非原子写留下的截断
JPEG，mtime 也是新的，会被上面的 :func:`cache_usable` 永久当成有效缓存
且没有任何自愈路径）。

---

## `desktop.workers.worker_host`

源码：[`desktop/workers/worker_host.py`](../../desktop/workers/worker_host.py)

WorkerHost：在拥有者 widget 内启动一次性后台 worker 线程并自动回收。

### 模块常量

| 名称               | 值   |
| ------------------ | ---- |
| \_DETACHED_THREADS | `[]` |

### `class WorkerHost`

Mixin：在拥有者 widget 内启动一次性后台 worker 线程。

#### 方法

| 方法                                | 说明                                       |
| ----------------------------------- | ------------------------------------------ |
| `run_worker(factory, wire) -> None` | 启动一次性 worker 线程并登记引用以便回收。 |
| `shutdown_workers() -> None`        | 退出并等待所有后台线程，随后清空引用表。   |

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

| 函数                                                                | 说明                                                              |
| ------------------------------------------------------------------- | ----------------------------------------------------------------- |
| `connect_queued(owner, signal, slot, thread=None) -> QObject`       | worker 信号 → 主线程闭包的**唯一正确写法**，返回中继对象。        |
| `stop_thread(thread: QThread, timeout_ms: int, label: str) -> bool` | 请线程收手并最多等 `timeout_ms`；等不到就**摘下来别让它被销毁**。 |

#### `connect_queued(owner, signal, slot, thread=None) -> QObject`

worker 信号 → 主线程闭包的**唯一正确写法**，返回中继对象。

⚠️ 直接 `signal.connect(lambda ...)` 会让闭包在 **worker 线程**执行。
里面一旦碰 widget（`strip.set_item_icon`、`view.clear_image`、
`set_image`…），Qt 内部就在子线程启动定时器，控制台刷屏
`QBasicTimer::start: Timers cannot be started from another thread`
（每张缩略图一条——用户报告的就是这个）。连到**宿主 QObject 的绑定
方法**（`worker.finished.connect(self._ready)`）本来就安全，无需本
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
