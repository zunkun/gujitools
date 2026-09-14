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
  worker.py             # 子进程入口：extract/detect 专用实现 + rembg/print 转发
  pages/                # 任务列表页、任务详情页 + 执行控制器/检测控制器（Mixin）
  components/           # 步骤条、任务表格、查看器（PDF/图片/rembg）、阶段参数面板
  workers/              # 后台 Qt worker：指纹、预览渲染、缩略图、清单缩略图
  store/                # 文件持久化：tasks/runs/pages/annotations + 旧数据迁移
  utils/                # file_hash、natural_key、清单工具
```

配套（desktop 之外）：

- `utils/box_geometry.py` — area/border 几何规则唯一实现，GUI 预览与 CLI 共用；
- `functions/`、`cli/` — CLI 层，`rembg`/`print` 阶段经 `CommandArgs` 转发执行，
  `extract`/`detect` 由 desktop worker 直接实现（不走 CLI 输出目录规则）。

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
    workset/            # 阶段执行输入物化（硬链接，不复制图片）
    thumbnails/
      source/0001.jpg…  # 源 PDF 页缩略图（256px，导入即生成，永不清理）
      print/            # 输出 PDF 预览缩略图（print 成功后重建）
    stages/
      extract/          # 提取图片（1.jpg…，直接平铺）
      rembg/            # 去底色整页结果（1.png…）
      print/print.pdf
```

旧数据迁移（`store/migrate.py`，启动时自动执行）：

- `guji.db`（SQLite）→ 各 JSON 文件，保留运行历史与手动框，旧库改名备份；
- uuid 任务目录 → 按创建时间重编号为任务号；
- 旧目录布局：extract 嵌套上移、imported 并入 extract、previews/logs/detect 删除、
  散落 run-*.json 归档、低分辨率/旧命名缩略图清理。

## 4. 关键算法位置

| 算法 | 位置 |
| --- | --- |
| YOLO 左右文本框检测 | `utils.yolo_utils.detect_left_right_boxes`（单例，CPU） |
| area/border → 效果区域合成 | `desktop/workers/preview_worker.compose_region_output` |
| 几何规则（GUI/CLI 共用） | `utils/box_geometry.py`（parse_border_mm、compute_final_boxes） |
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
