# 桌面端界面系统（设计令牌 + 基础控件）

界面视觉常量与可复用控件集中在 `desktop/ui/`，页面只做组装，不再各写各的色值、
间距和描边。目标是把"能用"的演示界面收敛成一套一致的观感。

```
desktop/ui/
  theme.py     设计令牌：颜色 / 间距 / 圆角 / 字号 / 状态色映射
  style.py     应用级外观：全局字体、主题色、极简全局 QSS
  widgets.py   基础视觉控件：Card / StatusChip / ProgressLine / …（全部自绘）
  __init__.py  统一导出：from desktop.ui import theme as T；from desktop.ui import Card
```

各控件与函数的完整签名见 [../api/desktop.md](../../api/desktop.md) 的
`desktop.ui.theme` / `desktop.ui.style` / `desktop.ui.widgets` 三节。

## 1. 设计令牌（`theme.py`）

任何页面/组件需要颜色、间距、圆角、字号时，一律从 `theme` 取，禁止再写字面量。

### 颜色

| 分组 | 令牌 | 值 | 用途 |
| --- | --- | --- | --- |
| 中性色 | `INK` | `#1A1D21` | 正文 |
| | `INK_SOFT` | `#4E5862` | 次要说明 |
| | `INK_FAINT` | `#8B949D` | 辅助信息 / 占位符 |
| | `INK_DISABLED` | `#B7BEC5` | 禁用文字 |
| 面 | `CANVAS` | `#F3F5F7` | 窗口底色 |
| | `SURFACE` | `#FFFFFF` | 卡片 |
| | `SURFACE_SOFT` | `#F7F9FB` | 表头 / 空状态 / 图片画布 |
| | `SURFACE_HOVER` | `#EEF3F6` | 悬停 |
| | `SURFACE_SUNKEN` | `#E4EAEF` | 内凹底：分段开关轨道等「容器槽」（要衬得出白滑块） |
| | `BORDER` | `#E2E7EC` | 常规描边 |
| | `BORDER_SOFT` | `#EDF1F4` | 分隔线 |
| | `BORDER_STRONG` | `#C9D1D8` | 浮层 / 悬浮面板描边（需压过底下卡片时） |
| 语义色 | `ACCENT` | `#0E7C8B` | 主色（深青，取自古籍纸张 + 靛青） |
| | `SUCCESS` | `#0F7B3F` | 成功 |
| | `WARNING` | `#B9760A` | 中断 / 警告 |
| | `DANGER` | `#C93A3A` | 失败 / 危险操作 |
| | `NEUTRAL` | `#7A838C` | 未执行 / 中性 |

每个语义色都有对应的 `*_SOFT` 浅底色（`ACCENT_SOFT`、`SUCCESS_SOFT`…），用于
胶囊、状态底等大面积淡色块。

### 状态 → 颜色 / 文案

阶段状态在列表、步骤条、控制列都要出现，映射统一放在 `theme`：

```python
STATUS_COLORS  # {"running": (ACCENT, ACCENT_SOFT), "success": (SUCCESS, SUCCESS_SOFT), ...}
STATUS_LABELS  # {"running": "执行中", "success": "成功", ...}
status_colors(status)  # -> (前景色, 底色)，未知状态按 pending
status_label(status)   # -> 中文文案，未知状态原样返回
```

新增状态时只改这一处，列表 / 步骤条 / 控制列自动一致。

### 间距 / 圆角 / 字号

- 间距按 4 的倍数：`SPACE_XS=4`、`SPACE_SM=8`、`SPACE_MD=12`、`SPACE_LG=16`、`SPACE_XL=24`
- 圆角三档：`RADIUS_SM=6`（控件）、`RADIUS_MD=10`（卡片）、`RADIUS_LG=14`（大容器）
- 字号六级：`SIZE_CAPTION=12`、`SIZE_BODY=13`、`SIZE_LABEL=14`、`SIZE_SUBTITLE=16`、`SIZE_TITLE=22`、`SIZE_HERO=26`

### 控件高度

表单控件统一 `CONTROL_HEIGHT=33`（在 `widgets.py`）：

- qfluentwidgets 的 `LineEdit` 在构造里写死 `setFixedHeight(33)`，`SpinBox` /
  `DoubleSpinBox` / `EditableComboBox` 都继承它，所以输入类天然同高；
- 而 **`ComboBox` 继承的是 `QPushButton`，没有这个约束，实测只有 27px**——
  和同列输入框并排会明显矮一截（`PushButton` 同理）。所以
  **下拉框一律用 `widgets.combo_box()` 创建**，由它抬到 `CONTROL_HEIGHT`；
  表单里单独出现的按钮也要显式 `setFixedHeight(CONTROL_HEIGHT)`。
- `tests/gui_selftest.py` 有断言锁住这点：所有阶段面板的下拉框高度必须等于
  `LineEdit().height()`，且 `CONTROL_HEIGHT` 常量不能和库里的实际高度脱节。
- `CheckBox` / `SwitchButton`（均 22px）是行内开关，**不**参与表单行高对齐。

> 另一个相关坑：裸 `ComboBox` 在未布局时 `height()` 返回 480（默认窗口高），
> 只有 `setFixedHeight` 过的控件才能在不 `show()` 的情况下取到真实高度。
> 写自测断言时不能拿裸 `ComboBox().height()` 当基准。

## 2. 基础控件（`widgets.py`）

| 控件 | 说明 |
| --- | --- |
| `Card` | 圆角白底卡片，`padding` 控制内边距；自绘圆角矩形 |
| `Divider` | 1px 水平分隔线（固定高 1px、水平拉伸） |
| `SectionTitle` | 带主色竖条的分区标题 |
| `StatusChip` | 状态胶囊：圆点 + 文案 + 淡色底，`set_state(text, status)` |
| `ProgressLine` | 细进度条，`setRange/setValue/ratio`，`height` 可调 |
| `Pill` | 文本自适应宽度的信息胶囊（超长省略） |
| `SegmentedToggle` | 分段开关：一行内互斥选择视图形态，`current/set_current/set_item_enabled`，点击发 `current_changed` |
| `EmptyState` | 空状态：图标 + 主文案 + 提示行，`set_text/set_hint` |
| `PageHeader` | 页面头：标题 + 副标题，右侧可放操作按钮 |
| `combo_box(items, width)` | 与输入框同高的下拉框；`items` 可传 `(文案, 值)` 二元组（值入 `itemData`） |
| `CONTROL_HEIGHT` | 表单控件统一高度常量（33） |
| `ui_font(size, bold)` | 生成统一字体的 `QFont` |
| `apply_to(widget, size, bold, color)` | 给控件套统一字体/颜色 |
| `icon_pixmap(icon, size, color)` | 把 `FluentIcon` 渲染成指定颜色的 `QPixmap` |

### 分段开关（`SegmentedToggle`）

同一视图的形态切换（如去底色预览的「去底色结果 / 原图」）用 `SegmentedToggle`，
**不要用两个 `PushButton` 拼一个开关**：

- 自绘胶囊，颜色全部取自 `theme`。之前用 `PushButton` 加一段写死 `#0078d4` 的样式表：
  饱和蓝和主题色（深青 `ACCENT`）打架，两个按钮之间还留着一道缝，看着像两颗不相干的
  按钮而不是一组开关；启用态还各自带白字粗体，一块实心色块压在浅色预览区上方很突兀。
- **选中态必须一眼看得出**，靠三处一起给对比度（只做「白滑块」是不够的）：
  1. 轨道用 `SURFACE_SUNKEN`（`#E4EAEF`）——**不是** `SURFACE_SOFT`。后者近白，
     白滑块压上去几乎分不出哪边是选中的（实测评均亮度差只有 6，等于没有对比度）；
  2. 选中项文字用主色 `ACCENT` 且**加粗**，未选中项用 `INK_SOFT`，禁用项 `INK_DISABLED`；
  3. 白滑块垫一层 `rgba(26,29,33,28)` 投影，滑块边界不靠色差硬撑。
  段宽按**粗体**度量算，否则选中项变粗后文字会顶到滑块边缘。
- 不用 qfluentwidgets 的 `SegmentedWidget`：那是给页面导航设计的（底部指示条），
  而且**无法单独禁用某一项**——这里需要「还没有去底色结果时禁用结果项」的语义。
- 高度 `SegmentedToggle.HEIGHT = 30`：比表单控件（`CONTROL_HEIGHT=33`）略矮，
  它不在表单里，是压在预览视图上的一条轻量开关。
- 只有用户点击才发 `current_changed`；`set_current()` 是程序化切换、不发信号
  （否则「回流刷新选中项」会自我递归）。
- `tests/gui_selftest.py` 锁住三点：去底色预览里不许再出现 `QPushButton` 子控件、
  不许有 `#0078d4` 这类硬编码样式表，以及**离屏渲染采样像素**确认轨道比白滑块
  明显更深（平均亮度差 ≥ 12）——最后这条是防止「选中态没对比度」回归。

## 3. 关键约束：自绘控件，慎用样式表

**这是本套件最重要的一条经验，改界面时务必遵守。**

Qt 的样式表有一个副作用：只要某个控件的祖先链上存在任何 `setStyleSheet`，
Qt 就会接管该控件（及其子控件）的背景绘制。这时 `QFrame` 会被刷成**白色**，
`QStackedWidget` 会被刷成样式表里写的背景色——即使这些控件本来没设背景。

历史上踩过两次坑：

1. **卡片内部灰块**：全局 QSS 里写了 `QStackedWidget { background: CANVAS }`，
   结果详情页预览区/控制列内部嵌套的 `QStackedWidget` 被刷成灰底，在白卡片上
   露出一块突兀的灰块。→ 全局 QSS 只给 `QMainWindow` 和 `QWidget#pageRoot`
   上色，**不要再选中 `QStackedWidget`**。
2. **卡片白底盖住内容**：给 `Card` 设样式表会连带影响内部子控件。→ 所有基础
   视觉控件（`Card`、`StatusChip`、`ProgressLine`、`SectionTitle`…）改为
   **重写 `paintEvent` 自绘**，完全不依赖样式表。

因此：**新增基础控件优先自绘 `paintEvent`**；`style.py` 的全局 QSS 只负责
窗口底色、滚动条、以及原生控件 `#taskTable` 的描边圆角。

还有一个相关坑：**qfluentwidgets 的 `TextEdit` 在构造时会给控件自身套一份样式表**
（`FluentStyleSheet.LINE_EDIT.apply(self)`）。控件级样式表优先级高于应用级，所以在
全局 QSS 里写 `QTextEdit#logView` **不会生效**（实测底色始终是白的、描边也看不到）。
日志文本域的样式改由 `desktop/components/log_panel.py` 的
`apply_log_view_style()` 直接设在控件上。

## 4. 应用级样式（`style.py`）

在创建主窗口前调用一次：

```python
from desktop.ui.style import apply_app_style
apply_app_style(app)
```

它做三件事：

1. **全局字体**：`resolve_font_family()` 在系统字体库里按
   `FONT_FAMILY → FONT_FALLBACK` 顺序挑一个真正存在的中文字体族，避免落到
   无衬线默认字体（Linux 尤其明显）；`QFontDatabase.families()` 查不到就
   回退到 `Microsoft YaHei UI`。
2. **主题色**：调用 qfluentwidgets 的 `setThemeColor(ACCENT)`，让框架自带控件
   （按钮、下拉框等）与我们的主色一致。
3. **极简全局 QSS**：仅覆盖
   - `QMainWindow, QWidget#pageRoot` 底色；
   - 细滚动条（10px、圆角手柄、隐藏加减行）；
   - `QTableWidget#taskTable` 边框/圆角。

   其余一律交给 qfluentwidgets 自己绘制，避免和它的代理/动画打架。（日志文本域
   `#logView` 由控件自身设样式，不在全局 QSS 里，原因见上一节。）

## 5. 页面改造约定

- 页面根节点 `setObjectName("pageRoot")`，让全局 QSS 能定位并上底色。
- 分区用 `Card`；卡片内部按 `SPACE_*` 排布，标题用 `SectionTitle`。
- 任何"状态"展示都走 `StatusChip` + `theme.status_colors/label`，不要各页自造。
- 空列表统一 `EmptyState`，给出下一步提示（如"请先完成提取"）。
- 阶段参数表单里，**下拉框用 `combo_box()`、单独出现的按钮设 `CONTROL_HEIGHT`**，
  别直接 `ComboBox()` / `PushButton()`——否则会比同列输入框矮 6px（见 §1 控件高度）。
- 预览图片画布用浅色底（`SURFACE_SOFT` + `BORDER`）：古籍页面本身是白底，
  深色底会把页面衬得像悬浮贴片。
- 需要"按需出现、且不改变布局"的面板（如执行日志浮层）用**覆盖式子控件**：
  挂在页面上、`raise_()` 提到最前，描边用 `BORDER_STRONG` 才能压过底下的白色
  卡片；内部字段用 `SURFACE_SOFT` 浅底与浮层的白底区分层级。

## 6. 视觉自查

离屏渲染截图工具（无需真机窗口，可脚本化回归）：

```bash
QT_QPA_PLATFORM=offscreen python tests/gui_shot.py D:/tmp/shots
```

它会注册 Windows 中文字体、造 3 条演示任务，输出 **6 张**截图（任务列表页、四步
详情页、以及点击日志状态条唤出的日志浮层），文件名与 `docs/guide/screenshots/` 下的
文件一致，可直接覆盖使用。便于逐张核对排版；改完界面后建议至少跑一次，配合
`tests/gui_selftest.py`（功能断言）一起作为回归。

## 7. 用户手册页（浏览器里渲染的那一页）

手册不是 Qt 界面，但**视觉仍属本系统**：`desktop/ui/help_dialog.py` 把
`docs/guide/*.md` 转成 HTML + 内嵌 CSS，交系统浏览器打开。CSS 用
`string.Template`（`$TOKEN`）从 `theme.py` 注入令牌，**色值不许在
help_dialog.py 里硬编码**。

### 7.0 两条路：开发现渲染，生产预生成（判据是 frozen，不是"文件在不在"）

| 模式 | 渲染时机 | 产物 | 截图 |
| --- | --- | --- | --- |
| 开发（源码运行） | 每次点按钮现渲染 | `%TEMP%/guji_manual_<毫秒>.html` | 绝对 `file://` URL |
| 打包（生产） | **构建期一次** | `desktop/static/manual.html` | **内联 data URI** |

判据在 `prefer_static_manual()`：看 `sys.frozen`（`GUJI_MANUAL_STATIC=1/0`
可强制）。**不能按"静态文件在不在"判断**——那样仓库里残留一个 `manual.html`
就会让开发者改完 md 仍看到旧内容。

生产侧为什么必须预生成：`docs/guide/` 整目录**不进安装包**（md 与 6MB 截图对
最终用户没用），安装后既没有 md 也没有 `screenshots/`，所以手册必须被压成
**单个自包含 HTML**（12 张截图内联，约 8MB）才拿得出手；顺带把运行时的
markdown 渲染、临时文件、防缓存文件名、旧文件清理整套绕法都省掉了。
`guji.spec` 因此有两个配套动作：`gui_datas` **不再**收 `docs/guide`，
`excludes` 里加上 `markdown`（只有构建环境需要它，缺了它运行时只是退化成
占位提示，而生产根本不需要渲染）。

版式（从外到内）：

- **吸顶栏**：品牌（古籍重製 / 用户手册）+ 分段开关（`桌面端操作` / `命令行`，
  沿用 `SURFACE_SUNKEN` 轨道 + 白滑块那套）+ 右侧 `打印 / 另存为 PDF`；
- **版心 1200px**：左侧「纸面」卡片（`SURFACE` + `BORDER` + 大圆角 + 浅阴影，
  正文行宽约 900px，长文档才读得下去），右侧**吸顶「本页目录」**（`< 1260px` 收掉）；
- **右栏目录的版式**（返工过两次：先是 196px 太窄、中文标题普遍折两行，后来用户
  还要求再宽一点）：
  - 宽度 `--toc-w: 272px`，与正文的 `gap` 收到 32px；窄屏断点 `1260px`；
  - 整列一条 2px 引导线（`#toc-nav::before`），当前小节在引导线上叠一段主色
    （条目里的 `::before` 用 `left: -12px` 压回去）——读起来像大纲，而不是一堆
    孤立文字；
  - 二级条目（`lv3`）更小更淡、多缩进，前面加一小段短横（`::after`），层级一眼分得开；
  - 「本页目录」标题右侧拉一条渐隐细线，与条目分隔；
  - 到顶时**第一条自动高亮**（否则页面刚打开、还没越过任何小节时目录一片灰）;
- **目录与锚点由页面 JS 现采**当前激活分段的 `h2/h3`（两份手册各自成目录），
  滚动高亮，`#tab-cli` 这样的深链可直达；标题 hover 出 `#` 锚点；
  ⚠️ **目录条目的 `id` 必须按页签加前缀**：两份手册都从 `sec-0` 起编，无前缀
  时 id 跨页签撞车 —— 在 CLI 页签点目录，浏览器会按文档顺序跳到**隐藏的**
  GUI 页签里同名元素（`display:none` 无法滚动），表现出来就是「点目录跳到
  别处 / 没定位」。另外标题要有 `scroll-margin-top`（吸顶栏高度），否则跳过去
  标题被顶栏盖住，同样像"没定位"；
  ⚠️ **`history.replaceState` 在 `file://` 下会抛 `SecurityError`**（origin 是
  opaque），必须 `try/catch` 接住——曾经的调用顺序是
  `preventDefault() → replaceState() → scrollIntoView()`，异常一抛，原生跳转已被
  取消、滚动又执行不到，用户看到的就是**点目录完全没反应**。现在统一收进
  `setHash()`，且**先滚动后改 hash**；
- **手册页 JS 用 `let`/`const`**（不再用 `var`），且**记住上次看的分段**：
  `file://` 页面在 Edge/Chrome 下同样能读写 `localStorage`（实测跨次打开生效），
  于是下次点「用户手册」落回上次那一页，而不是每次都被打回第一页；
  存储被禁用时静默降级；
- **截图可点开看原图**：1500px 宽的界面截图在 900px 行宽里必然被压缩；
  ⚠️ 放大浮层的 `img` **必须由 JS 动态创建**——在 HTML 里静态写一个空
  `<img ...>` 会让护栏「12 张截图都被引用」的计数变成 13 而报红
  （见 `tests/selftests/manual_dialog.py` 第 7 节）；
- **`@media print`** 去掉吸顶栏/目录，只留正文，配合顶栏的「另存为 PDF」；
- ⚠️ **绝对不要给手册页加 `<base>` 标签**（曾经加过，为的是让相对截图路径能解析）：
  **片段链接是按 base 解析的**，base 一旦指向 `docs/guide/`，点标题旁那个 `#`
  锚点就等于「打开手册目录」——浏览器把**目录列表**当页面显示（用户直接截图报过）。
  现在开发模式的截图写成绝对 `file://` URL、生产模式内联成 data URI，两边都不需要
  base。护栏：`tests/selftests/manual_dialog.py` 第 8 节（断言页面里没有 base 标签，
  并对照"塞回 base 后点击会导航走"的真机实验）。

护栏在 `tests/selftests/manual_dialog.py` 第 8 / 14 / 15 / 19 节：钉住"没有 base 标签"
"开发不启用静态" "打包打开静态文件" "静态页自包含（12 张 data URI、无外部引用）"
"目录 id 带页签前缀 + 有滚动处理" "replaceState 被接住且滚动在前"。

### 7.1 ⚠️ 打开方式：只把「原生路径」交给系统，别传 `file:///` URI

`open_manual()` 打开手册走 `help_dialog._open_with_system()`，**第一跳是
`os.startfile(str(path))`（原生路径）**，之后才会回退到 Qt
`QDesktopServices` → `cmd /c start`。这条约束是拿真实故障换来的：

- 症状：点「用户手册」按钮，界面冻住、浏览器永远不出现；
- 原因：原来写的是 `webbrowser.open(html_path.as_uri())`。Windows 上
  `ShellExecute` 拿到 `file:///...` 会走 **file: 协议处理器**
  （`HKCR\file` → `CLSID {00000303-0000-0000-C000-000000000046}`），该 CLSID
  在部分机器上没注册成功，`os.startfile` 于是**卡死不返回**（实测 >8s 仍未返回）；
- 对照：同一台机器上把**原生路径**交给 `os.startfile`，0.3s 秒开 Edge —— 原生
  路径走的是扩展名关联（`.html` → 默认浏览器），跟 file: 协议无关；
- 回退链里**刻意不放 `webbrowser.open`**：它在 Windows 上就是 `os.startfile`，
  且同样会挂；只有非 Windows 平台才用它。

护栏在 `tests/selftests/manual_dialog.py` 第 13 节：拦 `os.startfile` /
`webbrowser.open`，行为断言「第一跳是原生路径、且不出现 `file:` 前缀」。
全部打开方式都失败时会弹一个带路径的提示框（可选中复制），别让用户对着
按钮干瞪眼。
