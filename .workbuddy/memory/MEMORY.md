# 项目长期记忆（gujitools）

## 环境与命令
- 完整依赖（PySide6 + cv2 + torch）在 conda `py310`；anaconda base 也可；`yolobuild` 无 PySide6。
- GUI 自测（已拆成功能模块）：`QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE C:/Users/liuzu/anaconda3/envs/py310/python.exe -u tests/gui_selftest.py`（**135 项断言，全量约 37s**）。`--list` / `--only a,b`（自动补依赖）/ `--skip a,b` / `--module-timeout N`。判据以「全部 N 项断言通过 ✅」为准；增删用例 = 增删 `tests/selftests/*.py`（`_` 开头跳过），约定 `NAME/DEPENDS/TITLE/run(ctx)` + 可选 `TEARDOWN`（清场模块恒排最后）。
- **文档工具**：`python tools/gen_api_docs.py`（`--check` 比对）、`python tools/check_docs.py`（链接/锚点/表格）。改完源码/docstring 重跑。
- **改界面的标准回归流程**：①离屏探针渲染 PNG 对比（先 `tests/gui_shot.load_fonts(app)` 注册中文字体，否则全是方框）；②实现 + 自测断言（守卫要**双向验证**：注入回归形态确认断言真会失败）；③`tests/gui_shot.py` 出图覆盖 `docs/gui/screenshots/`（**文件名是中文，用 Python 脚本复制，别在 bash 写中文路径**；Python 脚本参数用 Windows 原生路径，`/d/...` 会被当字面量）；④重跑三条文档工具。探针放 `D:\tmp`，用完删。

## 测试断言的坑（血泪教训）
- **`wait_worker()` 后别立刻读状态**：最后的 `finished` 事件（带最终 `done`）可能还在队列里，先 `processEvents()` 轮询到目标值。
- **别在 QStackedWidget 未选中页面上量几何**：qfluent `ScrollArea` 懒构建，未显示时 `layout()` 为 None、viewport/inner 全是 480×640 脏值。测布局先走 `_context.show_detail()`。
- **自测模块间无残留**：拆分后 `set_task()`/历史回填会重置控件（如 rembg `border` 清空），每个模块自己显式设好前置条件。
- **没 `setFixedHeight` 的控件未 `show()` 时 `height()` 返回 480**；断言用 `LineEdit().height()`（33）当基准。
- **像素断言踩空白页陷阱**：自测 PDF 渲染不出中文 → 两半裁切后像素相同、假失败。改用确定性契约断言（monkeypatch 抓参数/坐标）。
- **双向验证注入前，先确认真实旧实现的路径/行为**：曾把「删除 workset」的回归注入写到 `output.parent/workset`（= `stages/workset`），而真实旧位置是 `output.parents[1]/workset`（= `tasks/<id>/workset`）→ 守卫不报错，差点误判「守卫失灵」。**注入无效 ≠ 守卫有效**，先让注入确实产生副作用再断言。
- **阶段子进程用 `TaskStore()` 默认根（`~/Documents/guji`）**：GUI 测试只重定向了主进程的 store（`w.store = repo`），子进程读 `config["args"]` 里的绝对路径。凡是「子进程内计算出的路径」都不会落在临时目录——注入回归时可能污染**真实用户数据**。
- **守卫断言要拆开、别串成一条**：`a == b == 0` 里 `==0` 会掩盖「拖拽是否产生文件」的真实语义，拆成「前后相等」+「恒为 0」两条。

## 危险操作红线
- **别在 bash 命令里写含中文/非 ASCII 的路径**（曾致整个 `docs/` 被误回收）。操作这类文件用 Python 脚本（`pathlib` + UTF-8）。
- 误删恢复：回收站 `D:\$RECYCLE.BIN\<SID>\` 下 `$R<id>` 是内容、`$I<id>` 是元数据（含 UTF-16LE 原始路径），`ls -lat` 找到后 `cp -r`。

## 架构约定（desktop 包分层）
- 职责：pages 页面骨架 + Mixin / services 纯业务规则（无 Qt）/ store 数据 / workers 后台线程 / stages 子进程阶段执行器。纯业务规则放 `services/` 便于脱离 Qt 测试。
- 页面层按页面分子包（tasklist/page.py、taskdetail/{page,view,manifest,history,submit,print_list,runner,detect}.py）；新增职责优先加 Mixin。
- `desktop/worker.py` 只做初始化与路由（实现在 `stages/`）；保持 `python -m desktop.worker` 可用。子进程：`sys.executable -m desktop.worker --config <json>` + `setWorkingDirectory(project_root())`。
- **desktop 包内一律绝对导入**（`from desktop.ui import theme as T`），相对导入挪目录会静默指错；**项目根用 `desktop.utils.files.project_root()`**，别用 `Path(__file__).parents[N]`。
- **print 页序 = 数据层**：`print.json` 的 `pages` 数组顺序是唯一事实来源，执行时作为 `args["files"]` 传给 CLI（**不读目录、不解析文件名**）；**已废弃 workset**（不再把顺序烧进文件名）。新增/删除/重排只改数组，零物理文件。不传 `files` 时 CLI 回退 `pdf_custom_sort_key` 文件名排序（独立用法兼容）。`title_switch_nodes` 填**原始页码**、`skip_pages` 纯数字按**清单序号**（1 起）。

## 界面样式约定（详见 docs/gui/gui-ui-system.md）
- 视觉常量只在 `desktop/ui/theme.py`（`SCROLLBAR_*`、`DANGER_*`、`SURFACE_SUNKEN`、`BORDER_STRONG` 等），不写魔法值；状态颜色走 `theme.status_colors/label`。
- **基础视觉控件自绘 `paintEvent`，不用样式表**；全局 QSS 只选 `QMainWindow`、`QWidget#pageRoot`（+滚动条+`#taskTable`）。实例级 setStyleSheet 会顶掉库样式，按钮四态写全。
- **qfluent 控件自带控件级样式表**，优先级高于应用级 QSS；定制必须设控件自身（见 `log_panel.apply_log_view_style`）。
- **表单控件高统一 `widgets.CONTROL_HEIGHT = 33`**：下拉框用 `widgets.combo_box()` 建；qfluent `ComboBox` 继承 `QPushButton` 默认 27px，类名判断单独列出。
- 形态切换用 `widgets.SegmentedToggle`（高 30）：轨道 `SURFACE_SUNKEN` + 选中文字 `ACCENT` 加粗 + 滑块投影；`set_current()` 不发信号；别用两个 PushButton 或 qfluent `SegmentedWidget` 拼。
- 各阶段参数表单由 `StagePanel.build_form()` 统一装进透明 `ScrollArea`（可滚动不压扁）；print 面板自带滚动区、覆盖此法。
- 别硬编码表格行高：qfluent TableWidget `defaultSectionSize()` 实测 38px，按实测 API 算。
- **表格单元格容器必须 `setFixedHeight(ROW_HEIGHT)` 锁整行高**：qfluent `TableItemDelegate.updateEditorGeometry` 用「改高度前」的容器高算居中偏移、随后又把高度改成整格高，高度≠行高时位置随几何更新时序漂移（运行中胶囊/按钮偏到行底、行与行还不一致），且离屏探针因时序不同**未必能复现**——别相信"探针里是居中的"就断定没问题。tasklist.py 有直调 delegate 的守卫断言。

## 缩略图/预览数据供给链
- `_page_thumb_for(...)` spec 唯一有效键 **`effect`**（boxes/area/border/dpi）；`ImageListWorker` 互斥入参 `crops=`/`effects=`。凡「区域/边框/DPI 参与渲染」一律传 `effect`（曾误读 `crop` 致 area=1 显示整页）。
- `gui_shot.py` 演示数据：缩略图 4 位名、调 `save_pages()/save_image_size()/save_detect_boxes()`、文字铺满整页。

## 文档约定
- docstring：中文，首行一句话以「。」结尾（≤40 字）；Qt 事件覆写不必手写（生成器自动标注）。
- `docs/api/*.md` 生成物勿手改；表格单元格 `|` 转义 `\|`；路径规则单一来源 `docs/io_path_rules.md`。
