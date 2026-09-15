# gujitools 桌面端（desktop）文档索引

本目录文档与 `desktop/` 当前实现保持同步（2026-09）。历史设计稿中与实现不符的
内容（SQLite 存储、crop 阶段、版本树等）已移除。

## 术语

| 术语 | 含义 |
| --- | --- |
| Task / 任务 | 一个 PDF 一个任务，顺序任务号 `0001`、`0002`… 即任务目录名 |
| Stage / 阶段（子任务） | `extract` → `detect` → `rembg` → `print`，固定顺序 |
| StageRun / 运行记录 | 某阶段的一次执行（状态、进度、参数），存于任务目录 `runs.json` |
| 检测框 | YOLO（`detect_left_right_boxes`）识别的左右文本框，存于 `boxes.json` |

## 文档

| 文档 | 内容 |
| --- | --- |
| [gui-requirements.md](gui-requirements.md) | 功能需求与非功能需求（与当前实现对齐） |
| [gui-architecture.md](gui-architecture.md) | 模块结构、进程模型、文件存储与任务目录布局 |
| [gui-technical-spec.md](gui-technical-spec.md) | Worker 消息协议、JSON 数据格式、area/border 合成几何、缩略图规范 |
| [gui-design.md](gui-design.md) | 交互设计：导入流程、步骤条、历史配置、检测框编辑、去底色预览 |
| [gui-layout.md](gui-layout.md) | 窗口布局：预览区 / 控制面板 / 日志 |
| [gui-ui-system.md](gui-ui-system.md) | 界面系统：设计令牌、基础自绘控件、全局样式与自绘约束 |
| [screenshots/](screenshots/) | 界面截图（由 `tests/gui_shot.py` 离屏生成，改界面后重跑覆盖） |
| [../api/desktop.md](../api/desktop.md) | 桌面端全部公开 API（由 `tools/gen_api_docs.py` 自动生成） |

## 快速开始

```powershell
# 启动 GUI（开发热重载）
hupper -m desktop
# 或
python desktop.py

# 运行全功能自测（102 项断言）
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py

# 离屏渲染界面截图（视觉自查，输出到指定目录）
QT_QPA_PLATFORM=offscreen python tests/gui_shot.py D:/tmp/shots
```

## 当前实现要点（速览）

- **存储**：纯 JSON 文件（`tasks.json` / `runs.json` / `pages.json` / `boxes.json` /
  `sizes.json`），无数据库、无旧数据迁移。所有写入走
  `store/json_io.py`（临时文件 + `os.replace` 原子落盘，损坏文件自动备份）。
- **界面**：视觉常量集中在 `desktop/ui/theme.py`，基础控件（卡片/状态胶囊/进度条/
  空状态等）为 `desktop/ui/widgets.py` 的**自绘控件**；详见
  [gui-ui-system.md](gui-ui-system.md)。
- **阶段**：`extract`（PDF → 图片，直接输出 `stages/extract`）、`detect`（只检测
  文本框坐标，不生成文件）、`rembg`（整页去底色）、`print`（合成 PDF）。
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
  # 功能回归（102 项断言，含真实 worker 子进程全流程）
  QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py

  # 重新生成 / 校验 API 参考
  python tools/gen_api_docs.py
  python tools/gen_api_docs.py --check

  # 校验全部文档的相对链接、锚点与表格列数
  python tools/check_docs.py
  ```
