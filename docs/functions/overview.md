# 功能模块概览

核心功能位于 `functions/` 包下，每个命令对应一个实现类，通过工厂方法 `get_function(command, command_args)` 进行映射。

## 使用顺序

推荐首次使用时先执行 `guji init` 生成 `guji.yaml`，再通过配置执行流程：

```bash
guji init
guji run extract
guji run crop
guji run rembg
guji run cropremove
guji run print
```

临时处理或不需要配置文件时，可以直接执行 `guji extract`、`guji crop`、
`guji rembg` 和 `guji cropremove`。`print` 需要从 YAML 读取较多排版参数，
因此只能使用 `guji run print`。

## 模块清单

| 模块             | 类名                  | 命令         | 别名  | 职责                                                                      |
| ---------------- | --------------------- | ------------ | ----- | ------------------------------------------------------------------------- |
| `base.py`        | `FunctionBase`        | —            | —     | 基类：输入/输出路径解析、并发执行引擎、日志与重试                         |
| `text_region.py` | `TextRegionProcessor` | —            | —     | 中间基类：YOLO 检测 + area/border 规则 + 输出构建（crop/cropremove 共享） |
| `extract.py`     | `ExtractFunction`     | `extract`    | `-e`  | 从 PDF 批量提取页面为图片                                                 |
| `crop.py`        | `CropFunction`        | `crop`       | —     | 基于 YOLO 检测裁剪文本框，支持 area/border，输出原图像素                  |
| `rembg.py`       | `RembgFunction`       | `rembg`      | `-r`  | 整图 Otsu 去底色/二值化/印章保留                                          |
| `crop_remove.py` | `CropRemoveFunction`  | `cropremove` | `-cr` | 复合流程：YOLO 裁剪 + 区域 Otsu 去底色，支持 area/border                  |
| `print.py`       | `PrintFunction`       | `print`      | —     | 将图片目录按规则生成为 PDF                                                |

## 命令关系

```
extract   ── PDF → 图片（前置步骤）
   │
   ▼
crop      ── 裁剪文本框原图像素（支持 area/border，不做去底色）
   │
   ▼
rembg     ── 整图去底色（无文本框检测）

cropremove = crop + rembg（一步完成，支持 area/border 精细控制）
   │
   ▼
print     ── 图片目录 → PDF（支持 A3/A4/A5/B5、标题和页码）
```

- `crop` 与 `cropremove` 共享相同的 area/border 规则（继承 `TextRegionProcessor`），区别仅是 crop 不做 Otsu 去底色；
- `rembg` 对整图去底，不依赖文本框检测；
- `cropremove` 结合 crop 与 rembg，通过 `--area` 控制 Otsu 作用区域与输出方式，`--border` 控制裁剪与外扩边距。
- `print` 从 YAML 配置读取参数，按图片文件名排序生成 PDF，并支持标题节点和页码左右交替标注。

## FunctionBase 执行引擎

所有功能类继承 `FunctionBase`，只需实现 `_process_single_image(path)`：

- **输入收集**：`_collect_input_files()` 默认调用 `utils.collect_image_files`，按自然排序返回；
- **并发调度**：`ThreadPoolExecutor` 并行处理，默认线程数 = CPU 核数；
- **失败重试**：出错文件最多重试 2 轮，失败信息写入 `{cmd}_failures.log`；
- **日志记录**：处理过程写入 `{cmd}_process.log`，按文件名排序输出最终统计。

`extract` 是例外——PDF 渲染的并发逻辑在 `pdf_utils` 内部实现，`ExtractFunction` 重写了 `execute()`。

## TextRegionProcessor 文本区域处理基类

`crop` 和 `cropremove` 共同继承 `TextRegionProcessor`（继承自 `FunctionBase`），封装了 YOLO 检测 → area/border 规则 → 输出构建的完整流程。两者唯一区别是 ROI 处理：

| 方法                 | crop 实现                            | cropremove 实现                               |
| -------------------- | ------------------------------------ | --------------------------------------------- |
| `_on_boxes_detected` | 返回 None（无需预处理）              | 计算 img_rgb/gray/印章掩码/共享阈值，返回 ctx |
| `_process_roi`       | 裁剪原图像素 `img_bgr[y1:y2, x1:x2]` | 对 ROI 做 Otsu 去底色                         |
| `_handle_no_boxes`   | 输出原图（无视 area_mode）           | area=1 输出原图；area=2/3 整图 Otsu           |
| `_save_output`       | 保存为 RGB PNG                       | 按 type 保存（二值/1bit/灰度）                |

**线程安全（ctx 模式）**：每张图的 img_rgb/gray/threshold/red_mask 通过 `_on_boxes_detected` 返回的 ctx 字典传递，绝不写入 self 实例变量。`FunctionBase.execute()` 使用 `ThreadPoolExecutor` 并发处理多张图，若状态存于 self 会被并发覆盖。

area/border 规则由基类统一处理，详见各命令文档：

- area=1：逐框 `-l`/`-r` 输出；area=2：逐框单图；area=3：合并框单图
- border=None/0/值 控制裁剪边界与外扩边距
- 特殊：area=2/3 + border有值 + 仅单框 → 对称输出（实际框+空白镜像+10mm间隔，构成完整双栏版面）

## 输出路径规则

所有命令统一遵循 `docs/io_path_rules.md`：

- 未传 `-o`：文件输入 → 父目录/默认目录；目录输入 → 输入目录/默认目录；
- 传纯名称：相对于 `parent_path` 创建；
- 传完整路径：直接作为绝对输出目录。

各命令的默认输出目录名（`default_temp_name`）：extract=文件名、crop=`crop`、rembg=`rembg`、cropremove=`rembg`。

## 各功能详细文档

- [extract.md](extract.md) — PDF 提取：页码解析、缩放计算、渲染模式
- [crop.md](crop.md) — 文本框裁剪：YOLO 检测、左右分割算法
- [rembg.md](rembg.md) — 去底色：Otsu 阈值、HSV 印章提取、形态学去噪
- [cropremove.md](cropremove.md) — 复合流程：area 区域模式、border 边框控制
- [print.md](print.md) — 图片生成 PDF：纸张、排序、标题和页码
