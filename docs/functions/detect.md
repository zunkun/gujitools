# detect 功能说明

在整页图片中检测**左右两个文本框**，输出像素坐标。

**命令行下必须加 `--save`**：检测结果会画到图片上落地（与 GUI 的 detect
预览视觉一致）。不带 `--save` 直接执行会被拒绝——命令行里检测不落盘等于
白算一趟，没有任何产出去处。

作为**代码调用**（`functions.detect.detect_page_boxes` /
`DetectFunction`）时不受此限制，可以只取坐标不落盘，作为中间步骤使用。

这是「检测」这一步的唯一实现：`crop = detect + 裁剪`、
`cropremove = detect + 裁剪 + 去底色`，两者内部的检测都走这里；
桌面端 GUI 的第二步（detect 阶段）同样复用同一份算法。

## 命令

```bash
guji detect -i <输入> --save [选项]
guji detect -i <输入> --save -o <输出根目录>
guji detect --config ./book.yaml
```

- `-i, --input`：图片文件或目录。
- `--save`：**把检测结果画到图片上并保存**（命令行下必填）。
- `-o, --output`：标注图**输出根目录**，其下自动追加 `detect` 子目录。
- `--ext`：标注图格式（`jpg`/`png`/`tiff`，默认 `png`）。
- `--workers`：并发线程数。
- `--clean`：清空输出目录。
- `--config`：配置文件路径，读取其中的 `detect:` 配置块。

### 不带 `--save` 会被拒绝

```bash
$ guji detect -i ./images
ERROR: 'detect' 不接受空跑（既未指定 --save，就不会产生任何文件）。
```

**为什么拒绝**：命令行执行 detect 的唯一目的就是把标注图落地。不落盘时
坐标只会打到 stdout，既没有文件产出，也没有下游步骤会读取它们——
`crop` / `cropremove` 各自内部都会重新检测一遍。所以这属于空耗一次
YOLO 推理，程序直接拒绝并给出替代方案。

**只在 CLI 层拒绝**，因为只有命令行语境下「不落盘」才等于「白算」：

| 调用方式 | 不带 `--save` | 原因 |
|---|---|---|
| 命令行 `guji detect` | ❌ 拒绝 | 无产出去处，纯浪费资源 |
| `guji run detect`（配置 `save: false`） | ❌ 拒绝 | 同上 |
| 代码 `DetectFunction(...)` | ✅ 可用 | 中间步骤，坐标由调用方消费 |
| 代码 `detect_page_boxes(img)` | ✅ 可用 | 纯函数，crop/cropremove 在用 |
| GUI detect 阶段 | ✅ 可用 | 坐标经事件通道交给界面画框 |

拦截放在 CLI 入口（`cli.__main__._reject_dry_run`）而非
`CommandArgs.validate()`，因为后者是 CLI 与 GUI **共用**的——若在校验层
强制 `save`，会把 GUI 的 detect 阶段一并拦死（它本来就不落盘）。

## 落地标注图（`--save`）

开启后每页输出一张标注图，在原图上绘制：

- **左框**：绿色 `#21c178`（RGB），标注「左框 (x1,y1,x2,y2)」；
- **右框**：蓝色 `#3b82f6`（RGB），标注「右框 (x1,y1,x2,y2)」。

配色与命名跟 GUI 预览（`desktop/components/viewers/image_view.py` 的
`BOX_COLORS` / `BOX_NAMES`）**完全一致**，实现集中在
`utils/box_draw.py`，因此「命令行看到的」和「界面看到的」是同一套视觉。

只画**真正检测到的框**：某侧无框时对应的框不绘制，不会画出错误的
右框位置。

输出路径规则与 `crop` **完全相同**（都用
`utils.path_utils.resolve_final_output_dir`，见 `docs/dev/io_path_rules.md`）——
detect 与 crop 是同级步骤，输出都落在**输入目录的旁边**：

- 未传 `-o`：`<输入目录的父目录>/detect/`
  （例：输入 `.../test/a/images` → 输出 `.../test/a/detect`，与 `images` 并列）；
- 传纯名称 `-o out`：`<输入目录的父目录>/out/detect/`；
- 传完整路径 `-o /abs/out`：`/abs/out/detect/`。

标注文字用 PIL + 系统中文字体绘制（OpenCV 的 `putText` 不支持中文）。
字体按与 `utils/pdf_utils.register_fonts` 相同的候选顺序探测
（fsgb2312 → simfang → simsun → msyh）；全部缺失时退化为 ASCII 标签
（`L` / `R`），保证任何环境都不会崩。

## 核心算法

### YOLO 检测 + 左右分割

1. 使用 YOLO 模型对图片推理，获取所有文本框；
2. 计算每个框的水平中心 `cx = (x1 + x2) / 2`；
3. 以图像宽度一半 `w/2` 为分界线：
   - `cx < w/2` → 归入 left 组
   - `cx >= w/2` → 归入 right 组
4. 每组按面积降序排序，取 `[0]` 作为最大候选框（即该侧面积最大者）。

坐标实现位于 `utils/yolo_utils.detect_left_right_boxes`；
`functions/detect.py` 在其上统一了「取最大框的前 4 个坐标」这一步。

### 模型加载

- 权重文件路径：`gujitools/weights/detect.pt`
- 进程内单例加载（双重检查锁定），多线程复用同一实例。

## 输出

### 结构化事件（reporter）

每张图上报一次 `page_boxes` 事件：

```json
{"type": "page_boxes", "image": "0001", "left": [..], "right": [..]}
```

- `image`：图片 stem（不含扩展名、不是绝对路径）。
- `left` / `right`：`[x1, y1, x2, y2]`，该侧未检出时为 `null`。

事件名与 `crop` / `cropremove` 上报的完全一致，因此
桌面端对 detect 阶段与 crop 阶段看到的是同一种事件。

### 命令行输出

```
图片总数: 3
检测完成: 0001.jpg -> success
检测完成: 0002.jpg -> no_detect
检测完成: 共 3 页，左框 2 页，右框 2 页，失败 0 页
标注图已保存: 2 张 -> <输出目录>
```

不带 `--save` 不会走到这里——命令在参数解析后即被拒绝。

`success` 表示至少检出 1 个框，`no_detect` 表示两侧都没检出
（正常情况，不算失败）。

## 与 crop 的关系

| | detect | crop |
| --- | --- | --- |
| 检测 | ✅ | ✅（复用 detect） |
| 裁剪导出 | ❌ | ✅ |
| 产出文件 | 总是（标注图，命令行强制 `--save`） | 总是（裁剪图） |
| 默认输出目录 | `<输入父目录>/detect` | `<输入父目录>/crop` |
| `--output` | 总是生效 | 总是生效 |
| area/border | 不涉及 | ✅ |

两者是**同级步骤**，输出路径规则同源（都调
`utils.path_utils.resolve_final_output_dir`），因此默认目录只差最后的
子目录名（`detect` vs `crop`），且都是「与输入目录并列」。

`crop` 与 `cropremove` 继承 `TextRegionProcessor`，其中
`detect_page_boxes(img, model)` 是它们拿到左右框的唯一途径——检测逻辑
不在各自类里重复实现。

## 无检测框时的行为

detect 本身只是如实上报 `left` / `right` 为 `null`，不做任何兜底输出。
「无框时怎么办」是**下游**的决定：

- `crop`：输出原图（`_handle_no_boxes`）；
- `cropremove`：area=1 输出原图，area=2/3 整图 Otsu 去底。

## 并发与失败处理

- 使用 `ThreadPoolExecutor` 并行检测，默认线程数 = `min(8, 图片数)`；
- 出错图片最多重试 2 轮；仍失败则计入统计的「失败」项，不影响其它图片；
- 进度通过 `reporter.progress(done, total)` 实时上报。

