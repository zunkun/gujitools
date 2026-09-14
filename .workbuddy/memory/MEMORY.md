# 项目长期记忆（gujitools）

## 环境与命令
- 完整依赖（PySide6 + cv2 + torch）在 conda `py310`；anaconda base 现也可（实测含 torch 2.14+cpu），`yolobuild` 无 PySide6。
- GUI 自测：`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE C:/Users/liuzu/anaconda3/envs/py310/python.exe -u tests/gui_selftest.py`（102 项断言）。历史上正常结束退出码为 127，但用 anaconda3 base 直跑时为 0；判据以输出「全部 102 项断言通过 ✅」为准，不要只看退出码。
- 无回归验证方式：`git worktree add ../gujitools-baseline HEAD` 拉基线，两侧跑同一自测比对输出。
- **文档工具**：`python tools/gen_api_docs.py`（生成 `docs/api/*.md`，AST 静态解析、离线可跑）、`python tools/gen_api_docs.py --check`（与源码比对，CI 用）、`python tools/check_docs.py`（校验全部 Markdown 的相对链接、锚点、GFM 表格列数）。改完源码/docstring 后重跑这三条。

## 危险操作红线（血泪教训）
- **不要在 bash/shell 命令里直接写含中文或任何非 ASCII 的路径**。曾因 `git rm "docs/outputpath说明.md"` 导致整个 `docs/` 目录被 shell/沙箱误回收。要操作这类文件，改用 Python 脚本（`pathlib` + UTF-8）或先重命名为 ASCII。
- 误删先别慌：Windows 回收站 `D:\$RECYCLE.BIN\<SID>\` 下 `$R<id>` 是内容、`$I<id>` 是元数据（内含 UTF-16LE 原始路径）。`ls -lat` 按时间找到条目，`cp -r` 即可恢复。

## 架构约定（desktop 包分层）
- 每层职责：pages 页面骨架 + 控制器 Mixin / services 纯业务规则（无 Qt）/ store 数据 / workers 后台线程 / stages 子进程阶段执行器。
- 页面层按**页面分子包**：`desktop/pages/tasklist/page.py`、`desktop/pages/taskdetail/{page,view,manifest,history,submit,print_list,runner,detect}.py`。
- `desktop/worker.py` 仅做初始化与阶段路由，阶段实现在 `desktop/stages/`；必须保持 `python -m desktop.worker` 与 `desktop.worker.run_*` 可用。
- Mixin 依赖宿主页面的属性/方法，跨文件引用 self.* 是本项目既定模式（新增职责优先加 Mixin 而非塞进页面骨架）。
- 新增纯业务规则放 `desktop/services/`，便于脱离 Qt 测试。

## 导入与路径约定（强制）
- **desktop 包内一律绝对导入**，不用 `from .x` / `from ..x`：写 `from desktop.ui import theme as T`、`from desktop.pages.taskdetail.page import TaskDetailPage`。相对导入层数绑定文件位置，挪目录会静默指向错模块（pages 拆子包时已踩坑）。
- **不要用 `Path(__file__).parents[N]` 推算项目根**，挪一层就错（worker 子进程 cwd 因此坏过）。用 `desktop.utils.files.project_root()`。
- worker 子进程源码模式：`sys.executable -m desktop.worker --config <json>`，`setWorkingDirectory(project_root())`。

## 界面样式约定（desktop/ui/）
- 视觉常量只在 `desktop/ui/theme.py` 定义，页面/组件一律引用（`from ...ui import theme as T`），不写魔法色值/间距；状态颜色统一走 `theme.status_colors/label`。
- **基础视觉控件一律自绘 `paintEvent`，不用样式表**。Qt 样式表引擎在子树出现任何 `setStyleSheet` 时会接管背景：把 `QFrame` 刷白、把 `QStackedWidget` 刷成 QSS 指定色。
- **全局 QSS 只选中 `QMainWindow` 和 `QWidget#pageRoot`**，不要再写 `QStackedWidget`（会导致卡片内嵌套栈露出灰块）+ 滚动条 + `#logView`/`#taskTable`。详见 `docs/gui/gui-ui-system.md`。
- 图片预览画布用浅色底（`SURFACE_SOFT`+`BORDER`），古籍白底页面配深底会像悬浮贴片。
- 需要「按需出现且**不改变布局**」的面板（如执行日志浮层）用**覆盖式子控件**：挂在页面（不是窗口）上、`raise_()` 提到最前，描边用 `BORDER_STRONG`（`#C9D1D8`）才压得住底下的白卡片；内部字段用 `SURFACE_SOFT` 浅底与浮层白底分层。开合用 `QApplication` eventFilter 处理 Esc / 点击外部关闭，收起时务必卸载过滤器。

## PySide6 / qfluentwidgets 注意点
- **不要硬编码表格行高/表头高度**：qfluent TableWidget 的 `verticalHeader().defaultSectionSize()` 实测为 38px，与写死的 30px 不一致会导致 setFixedHeight 算出的高度不足、单元格控件被压扁或裁掉。应按 `defaultSectionSize()` / cellWidget `sizeHint()` / `horizontalHeader().sizeHint()` / `frameWidth()` 实测计算。
- qfluent `ComboBox` 不是 `QComboBox` 子类，焦点/类型判断需单独检查。
- `ToolButton` 的样式表不识别类选择器（会告警 "Could not parse stylesheet"），直接设属性。
- **qfluentwidgets 控件自带控件级样式表**（如 `TextEdit.__init__` 里 `FluentStyleSheet.LINE_EDIT.apply(self)`）：控件级优先级高于应用级，**写在 `style.py` 全局 QSS 里的规则会被它盖掉**——`QTextEdit#logView` 的底色/描边曾因此长期不生效（底色始终纯白）。要定制这类控件的样式，必须 `setStyleSheet` 设在控件自身（见 `log_panel.apply_log_view_style`）。

## 文档约定
- **docstring**：模块与公开类/函数一律写中文 docstring；首行一句话概括、以「。」结尾（≤40 字），多行细节与「参数/返回」跟在空行之后。Qt 事件覆写（`paintEvent`/`mouse*Event`/`resizeEvent`）不必手写，`gen_api_docs.py` 会按方法名自动标注。
- **API 参考是生成的**：`docs/api/*.md` 顶部有「请勿手工编辑」标记，改源码后重跑生成器；不要手改。
- **Markdown 表格**：单元格里出现 `|` 必须转义为 `\|`，否则整行错格（`check_docs.py` 会报列数不一致）。
- **单一事实来源**：路径规则只在 `docs/io_path_rules.md`，不要另建重复文档（`outputpath说明.md` 曾与它完全重复，已删）。
