# gujitools 桌面端（desktop）技术文档索引

> **面向开发者**：日常使用者请看
> [用户操作手册 `docs/guide/user-guide.md`](../../guide/user-guide.md)。
> 本目录及其下的 6 份文档讲的都是实现细节（架构、协议、布局、需求），
> 使用者无需阅读。

本目录文档与 `desktop/` 当前实现保持同步（2026-09）。历史设计稿中与实现不符的
内容（SQLite 存储、crop 阶段、版本树等）已移除。

## 术语

| 术语 | 含义 |
| --- | --- |
| Task / 任务 | 一个 PDF 一个任务，顺序任务号 `0001`、`0002`… 即任务目录名 |
| Stage / 阶段（子任务） | `extract` → `detect` → `rembg` → `print`，固定顺序 |
| StageRun / 运行记录 | 某阶段的一次执行（状态、进度、参数），存于任务目录 `runs.json` |
| 检测框 | YOLO（`functions.detect.detect_page_content`，与 CLI 同源）识别的内容框（半幅左右 / 整幅），存于 `boxes.json` |

## 文档

| 文档 | 内容 |
| --- | --- |
| [gui-requirements.md](gui-requirements.md) | 功能需求与非功能需求（与当前实现对齐） |
| [gui-architecture.md](gui-architecture.md) | 模块结构、进程模型、文件存储与任务目录布局 |
| [gui-technical-spec.md](gui-technical-spec.md) | Worker 消息协议、JSON 数据格式、area/border 合成几何、缩略图规范 |
| [gui-design.md](gui-design.md) | 交互设计：导入流程、步骤条、历史配置、检测框编辑、去底色预览 |
| [gui-layout.md](gui-layout.md) | 窗口布局：预览区 / 控制面板 / 日志 |
| [gui-ui-system.md](gui-ui-system.md) | 界面系统：设计令牌、基础自绘控件、全局样式与自绘约束 |
| [../../api/desktop.md](../../api/desktop.md) | 桌面端全部公开 API（由 `tools/gen_api_docs.py` 自动生成） |

配图不在本目录（已随用户操作手册迁走）：

| 资源 | 说明 |
| --- | --- |
| [../../guide/screenshots/](../../guide/screenshots/) | 界面总览截图（`tests/gui_shot.py` 离屏生成） |
| [../../guide/screenshots/guide/](../../guide/screenshots/guide/) | 用户操作手册配图（`tests/gui_shot.py --guide` 生成） |

## 快速开始

```powershell
# 启动 GUI（开发热重载）
hupper -m desktop
# 或
python desktop.py

# 只跑与本次改动相关的自测模块（日常推荐，自动带上其依赖）
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only <模块名>

# 全量自测：仅动了共享底层或发布打包前才需要（详见 .workbuddy/memory/details-testing.md）
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py

# 离屏渲染界面截图（视觉自查，输出到指定目录）
QT_QPA_PLATFORM=offscreen python tests/gui_shot.py D:/tmp/shots

# 生成用户操作手册配图（写入 <目录>/guide/）
QT_QPA_PLATFORM=offscreen python tests/gui_shot.py --guide D:/tmp/shots
```

## 当前实现要点（速览）

- **存储**：纯 JSON 文件（`tasks.json` / `runs.json` / `pages.json` / `boxes.json` /
  `sizes.json`），无数据库、无旧数据迁移。所有写入走
  `store/json_io.py`（临时文件 + `os.replace` 原子落盘，损坏文件自动备份）。
- **界面**：视觉常量集中在 `desktop/ui/theme.py`，基础控件（卡片/状态胶囊/进度条/
  空状态等）为 `desktop/ui/widgets.py` 的**自绘控件**；详见
  [gui-ui-system.md](gui-ui-system.md)。
- **左侧导航与独立模块**：主窗口中央是 `desktop/modules/shell.py` 的壳层
  （导航栏默认折叠，点左上角菜单按钮展开）。导航条目 = 「任务管理」+ `MODULES`
  注册表里的独立模块（图片提取 / 去底色 / 拼图）。模块页**惰性构造**、彼此零
  import 依赖，复用 `desktop/steps/` 的**共用步骤组件**（`StepSpec` 步骤元数据 +
  `StepKernel` 执行内核 + `SourceZone` 大输入区 + `StepControl` 控制块）。
  目录布局与边界详见 [gui-architecture.md](gui-architecture.md) 的 §2.3。
- **大输入区**：三个模块页在页头下方都有一块横跨整幅的 `SourceZone`——
  拖文件、拖文件夹、点底部「选择文件 / 选择文件夹」按钮、已选态点右端「更换」、
  右上角一键清空；拖到页面空白处也认。
  ⚠️ 那两个选择按钮是**必须有**的（用户 2026-10-03 报「有框说可以拖入，但没法
  直接点击按钮选择文件或文件夹」）：此前只有"点空白处弹两选项小菜单"这一条
  隐式入口，界面上没有任何东西提示它能点。入口是主路径就得画出来。
  它只负责"用户给了哪些路径"，"这些路径算哪个源"由纯逻辑
  `StepSpec.resolve_source()` 决定（可脱离 Qt 单测）；顶层没可用文件时
  自动下钻 1~2 层，所以可以**直接把提取的输出根拖给「去底色」**。
- **单步的出口**：`StepSpec.flat_output` 置真的步骤（目前只有 `extract`）在
  **单 PDF** 时把 `<输出>/<PDF名>/**` 平铺到输出目录根下（批量仍每个 PDF
  一个子目录）。⚠️ 同名先**比内容**：同内容是重跑副本（当成同一份、嵌套壳清掉），
  不同内容才是真冲突（保留嵌套树、绝不覆盖）——只判"已存在"会让重跑后的输出
  目录永久留两套，预览里每页出现两次。预览侧用
  `collect_result_images()` 兜底（同名只收一份、顶层优先，不删产物）。
  造 job 一律走 `kernel.job_for(spec)`，别自己拼 `command_job`。
- **阶段**：`extract`（PDF → 图片，直接输出 `stages/extract`）、`detect`（只检测
  文本框坐标，**不生成文件**——坐标经事件通道交给界面画框，与命令行
  `detect --save` 的落盘语义不同）、`rembg`（整页去底色）、`print`（合成 PDF）。
- **area/border**：属于第三步 rembg，决定预览与裁剪区域；规则与 CLI
  `crop`/`cropremove` 完全一致（见 technical-spec）。
- **检测框**：持久化到 `boxes.json`，预览可拖拽/缩放/删除/手绘，手动结果不被
  自动结果覆盖。

## 开发约定

- **导入**：`desktop` 包内一律绝对导入（`from desktop.store import TaskStore`），
  不使用 `from .x`；取项目根用 `desktop.utils.files.project_root()`，不用
  `Path(__file__).parents[N]`。理由见
  [gui-architecture.md](gui-architecture.md) 第 2.1 节。
- **界面**：颜色 / 间距 / 圆角 / 字号只从 `desktop/ui/theme.py` 取；基础控件在
  `desktop/ui/widgets.py` 中以 `paintEvent` 自绘，不引入样式表
  （原因见 [gui-ui-system.md](gui-ui-system.md)）。
- **存储**：JSON 读写必须走 `desktop/store/json_io.py`（临时文件 + `os.replace`
  原子落盘，损坏自动备份）。
- **docstring**：模块与公开类/函数都写中文 docstring，首行一句话概括、以「。」结尾；
  Qt 事件覆写（`paintEvent`、`mouse*Event`、`resizeEvent` 等）无需手写，
  API 参考会按方法名自动标注语义。
- **改完源码同步文档**：

  ```bash
  # 功能回归：先 --only 跑相关模块；只有动到共享底层才全量
  QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only <模块名>

  # 重新生成 / 校验 API 参考
  python tools/gen_api_docs.py
  python tools/gen_api_docs.py --check

  # 校验全部文档的相对链接、锚点与表格列数
  python tools/check_docs.py
  ```
