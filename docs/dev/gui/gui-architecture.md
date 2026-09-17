# 桌面端架构文档（与 desktop/ 当前实现对齐）

## 1. 进程模型

```
desktop.py（入口）
  ├─ GUI 主进程        python desktop.py        PySide6 + qfluentwidgets
  └─ worker 子进程     python -m desktop.worker --config <json>   每阶段一个
```

- **GUI 主进程不加载重依赖**（cv2/YOLO/PyMuPDF）：预览用已生成缩略图或
  worker 渲染结果；算法全部隔离在子进程。
- worker 子进程执行完即退出，操作系统回收模型/内存，无需手动释放。
- worker 与 GUI 通过 stdout 的 **JSON Lines** 通信（见 technical-spec）。

## 2. 模块划分

```text
desktop.py              # GUI 与 worker 统一入口
desktop/
  app.py                # 主窗口与启动逻辑
  __main__.py           # 支持 python -m desktop / hupper -m desktop
  worker.py             # 子进程入口：仅做初始化与阶段路由（薄壳）
  stages/               # 子进程阶段执行器：events 事件输出、detect/generic/print/rembg
  pages/                # 页面层：一个页面一个子包
    tasklist/page.py    #   任务列表页（首页：表格、导入、详情/删除）
    taskdetail/         #   任务详情页：一个骨架 + 按职责拆分的控制器 Mixin
      page.py           #     骨架（任务切换/阶段切换/状态刷新），组合下列 Mixin
      view.py           #     UI 组装（头部/步骤条/预览区/控制列/日志）
      manifest.py       #     页面清单、缩略图、页面增删
      history.py        #     历史执行配置回填
      submit.py         #     rembg 提交控制器与按钮状态
      print_list.py     #     第四步待打印列表
      runner.py         #     阶段执行（worker 子进程编排）
      detect.py         #     detect 检测控制
  services/             # 纯业务规则（无 Qt）：print_plan 条目派生、submit_state 版本状态机
  ui/                   # 界面系统：设计令牌 + 基础自绘控件 + 全局样式（详见 gui-ui-system.md）
    theme.py            #   颜色/间距/圆角/字号/状态色映射（唯一色值来源）
    style.py            #   全局字体、主题色、极简全局 QSS
    widgets.py          #   Card/StatusChip/ProgressLine/EmptyState/PageHeader…（paintEvent 自绘）
  components/           # 步骤条、任务表格、查看器（PDF/图片/rembg）、阶段参数面板、日志
    step_bar.py             # 顶部步骤条：编号/对勾徽标 + 连接箭头 + 状态色（自绘，不用样式表）
    task_table.py           # 任务表格：子任务状态用状态胶囊组显示
    log_panel.py            # 执行日志：底部状态条 + 点击唤出的浮层（出错自动标红）
    panels/print_params.py  # print 参数定义与解析/序列化纯函数
    panels/print_form.py    # print 表单控件构建（分区与控件组装）
    panels/print_nodes.py   # 标题切换节点列表（逐行堆叠，高度随行数自适应）
    panels/print_panel.py   # print 面板状态（取值/回填/重置）
    panels/base.py          # 阶段参数面板基类（表单构建 / 重置默认值）
  workers/              # 后台 Qt worker：指纹、预览渲染、缩略图、清单缩略图
  store/                # 文件持久化：tasks/runs/pages/annotations + 旧数据迁移
    json_io.py              # 原子读写 JSON（临时文件 + os.replace，损坏自动备份）
  utils/                # file_hash、natural_key、清单工具
```

配套（desktop 之外）：

- `utils/box_geometry.py` — area/border 几何规则唯一实现，GUI 预览与 CLI 共用；
- `utils/box_draw.py` — 检测框标注绘制唯一实现，GUI 预览与 CLI `detect --save` 共用；
- `functions/`、`cli/` — CLI 层，`rembg`/`print` 阶段经 `CommandArgs` 转发执行，
  `extract`/`detect` 由 desktop worker 直接实现（不走 CLI 输出目录规则）。
  不过 **`detect` 的检测算法仍复用 `functions.detect.detect_page_boxes`**——
  只有「输出目录规则」被绕开，算法没有第二份实现。

### 2.1 导入约定：一律使用绝对导入

全项目（`desktop/`、`cli/`、`functions/`、`utils/`）**不使用相对导入**
（`from .x` / `from ..x`），统一写自顶向下的完整路径：

```python
from desktop.store import TaskStore
from desktop.ui import theme as T
from desktop.pages.taskdetail.page import TaskDetailPage
from desktop.components.viewers import ImageViewerWidget
```

理由：相对导入的层数绑定文件位置，**文件一挪目录就静默指向错误模块**（本次把
`pages/` 拆成子包时就踩到：`from ..services...` 在深一层后解析成了
`desktop.pages.services`）。绝对导入与文件位置解耦，移动/重命名文件只需改引用点。

包内动态导入同样走绝对路径：

```python
# functions/__init__.py
_COMMAND_MAP = {"crop": ("functions.crop", "CropFunction"), ...}
mod = importlib.import_module("functions.crop")   # 不用 import_module(".crop", __name__)

# utils/__init__.py 的延迟加载表 _LAZY 同理，值为 "utils.image_utils" 这类全路径
```

> 与之配套的一条：**不要用 `Path(__file__).parents[N]` 推算项目根**。文件挪一层
> 就会算错（worker 子进程的工作目录就是这么坏的）。取项目根用
> `desktop.utils.files.project_root()`，它基于 `desktop` 包自身位置计算。

## 3. 数据存储：纯 JSON 文件（无数据库）

数据根目录 `~/Documents/guji`：

```text
guji/
  tasks.json            # 任务索引（id=任务号、名称、源路径、hash、状态、时间…）
  tasks/<任务号>/
    <源文件名>.pdf      # 导入时复制的源文件副本
    pages.json          # 页面清单 [{file, label}]
    runs.json           # 各阶段执行历史（最新在前，≤20 条）
    boxes.json          # 检测框 {页stem: {boxes:[左,右], origin: auto|manual}}
    sizes.json          # 页面图片原始尺寸 {页stem: [w, h]}
    runs/               # 子进程执行配置 run-*.json / detect-config.json
    thumbnails/
      source/0001.jpg…  # 源 PDF 页缩略图（256px，导入即生成，永不清理）
      print/            # 输出 PDF 预览缩略图（print 成功后重建）
    stages/
      extract/          # 提取图片（1.jpg…，直接平铺）
      rembg/            # 去底色整页结果（1.png…）
      print/print.pdf
```

所有 JSON 读写统一走 `store/json_io.py`：

- **写**：先写同目录临时文件，`flush` + `fsync` 后再 `os.replace` 原子替换——中途
  崩溃不会留下半截文件，也让并发读者永远看到完整内容；
- **读**：解析失败时把损坏文件备份为 `<名>.corrupt-<时间>` 并返回默认值，而不是
  让整个界面崩掉；
- **删除任务竞态**：任务目录已被删除时，写入直接跳过（回调晚于删除时不报错）。

存储一直是纯 JSON 文件，**没有旧数据需要迁移**：`TaskStore` 构造时只确保
`tasks/` 存在（`store/store.py`）。曾经的 `store/migrate.py`（SQLite `guji.db`
与旧目录布局的一次性迁移）已随 SQLite 一并移除，因此打包产物不再包含
`sqlite3.dll`。

## 4. 关键算法位置

| 算法 | 位置 |
| --- | --- |
| 文本框检测（GUI/CLI 唯一入口） | `functions.detect.detect_page_boxes` → 底层 `utils.yolo_utils.detect_left_right_boxes`（单例，CPU） |
| area/border → 效果区域合成 | `desktop/workers/preview_worker.compose_region_output` |
| 几何规则（GUI/CLI 共用） | `utils/box_geometry.py`（parse_border_mm、compute_final_boxes） |
| 检测框标注绘制（GUI/CLI 共用） | `utils/box_draw.py`（draw_boxes，配色与 GUI 预览一致） |
| 自然排序（r 在 l 前） | `utils/sort_utils.pdf_custom_sort_key` |
| 页缩略图生成 | `desktop/workers/source_thumbnails_worker.py` |
| 文件指纹 | `desktop/utils/files.file_hash` |

## 5. 性能设计

- **重负载隔离**：图像解码、区域合成、YOLO 推理全部在 worker 线程/子进程；
  主线程只接收最终小图。
- **缩略图直读**：列表条目图标读取 256px 预生成缩略图（QImageReader 缩放解码），
  不解码原始扫描图；rembg 预览的区域合成也以缩略图/worker 完成为主。
- **防重复**：阶段切换时页面清单未变化则跳过重建；加载请求带令牌，
  仅最后一次生效。
- **请求取消**：阶段执行中可 kill worker 子进程；续跑按缺失页/缺失输出补齐。
