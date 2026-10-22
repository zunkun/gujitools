# crop 功能说明

基于 YOLO 目标检测定位图片中的文本框，**把每个检测框各自裁剪出来**并导出原图像素。

与 `cropremove` 共享相同的检测与裁剪规则（共同继承 `TextRegionProcessor` 基类），区别是 crop **不做 Otsu 去底色**，仅裁剪原始彩色像素。

> ⚠️ 2026-10-22 起**没有 `--area` 参数**：检测出几个文本框就裁几张图。
> 半幅页（左右两栏）输出 `-l`/`-r`，整幅页用页名输出一张，无框页原样输出。

## 命令

```bash
guji crop -i <输入> -o <输出> [选项]
guji crop --config ./book.yaml
```

指定 `--config` 时读取配置文件中的 `crop:` 配置块；命令行显式提供的参数会
覆盖配置值，例如 `guji crop --config ./book.yaml --border 20`。

## 核心算法

### YOLO 检测 + 按类别分流

> **检测来自 `functions/detect.py`**：`crop` 不自己实现检测，而是调用
> `functions.detect.detect_page_content(img, model)` 取框——这正是
> 「`crop` = `detect` + 裁剪」在代码里字面成立的原因。GUI 的第 2 步
> （detect 阶段）走的是同一个函数，所以命令行与界面看到的框完全一致。
> 需要单独查看检测结果时用 `guji detect -i ./images --save`。
>
> 内容框有两类（模型 `static/weights/bookcontent.pt`，对一页互斥）：`harfcontent`
> 半幅（左右两栏）→ 分 left / right 两组；`fullcontent` 整幅（整页单一
> 内容区）→ 只有一个框，**不拆左右**（用页名输出一张）。

1. 使用 YOLO 模型对图片推理，获取所有内容框；
2. `fullcontent` 直接作为整幅框；其余（`harfcontent`）按水平中心分左右：
   - 计算水平中心 `cx = (x1 + x2) / 2`；
   - 以图像宽度一半 `w/2` 为分界线：
   - `cx < w/2` → 归入 left 组
   - `cx >= w/2` → 归入 right 组
4. 每组按面积降序排序，取 `[0]` 作为最大候选框。

### 模型加载

- 权重文件：`static/weights/` 下**当前生效**的那份（`utils.data_package.resolve_weights`
  按 `bookcontent.version.json` 判定；目录里可留多份 `bookcontent-v<版本>.pt`）
- 延迟加载 + 模块级单例 + 双重检查锁，确保多线程下只加载一次
- 强制 CPU 模式运行

## 参数说明

| 参数        | 默认值   | 说明                                |
| ----------- | -------- | ----------------------------------- |
| -i/--input  | .        | 输入图片文件或目录                  |
| -o/--output | None     | 输出目录名称                        |
| --border    | None     | 边框控制（mm），CSS 风格 1~4 值写法 |
| --clean     | False    | 清空输出目录                        |
| --workers   | CPU 核数 | 并行线程数                          |

### --border（边框控制，单位 mm）

控制每张裁剪图在框外再外扩多少留白。**默认 0**（紧裁到文本框边界）：
第四步会把图重新排进 A4，前面再外扩留白等于「图片内留白 + 页面边距」双重留白。

| border 值     | 输出                              |
| ------------- | --------------------------------- |
| None / 0      | 裁剪到每个框的边界（紧裁）        |
| 有值（如 30） | 每个框边界 + 外扩空白             |

**CSS 风格写法**（mm→px 按 300 DPI 换算）：

```
--border 30              # [30,30,30,30] 四边统一
--border 20,30           # [20,30,20,30] 上下20，左右30
--border 20,30,25        # [20,30,25,30] 上20，左右30，下25
--border 10,20,30,40     # [10,20,30,40] 上右下左
```

## 输出命名规则

```
输入: page3.jpg（检测到左右两个框）
输出: page3-l.png（左框裁剪）
      page3-r.png（右框裁剪）

输入: page5.jpg（仅检测到右框）
输出: page5-r.png

输入: page6.jpg（整幅页，一个框）
输出: page6.png

输入: page7.jpg（未检测到任何框）
输出: page7.png（原图拷贝，状态为 no_detect）
```

- 输出格式由 `--ext` 决定（默认 **PNG**，300 DPI）
- 左框加 `-l` 后缀，右框加 `-r` 后缀；整幅页不带后缀
- 无检测框时原样输出整页（返回 `no_detect` 状态）

## 处理流程

```
图片输入
  │
  ├─ 文件过小？ → 跳过
  │
  ├─ cv2 读取（BGR）
  │
  ├─ YOLO 检测 → 左右分组（按面积降序取最大框）
  │
  ├─ 无文本框？→ 输出原图，返回 no_detect
  │
  ├─ border 参数解析 (mm→px @300dpi)
  │
  ├─ 逐框循环：每个框 → 一张图（框 + border）
  │
  └─ 保存（PNG / jpg / tiff，300 DPI）
```

## 示例

```bash
# 每个检测框各裁一张（半幅页输出 -l/-r）
guji crop -i ./images -o ./cropped

# 单文件
guji crop -i page3.jpg -o ./output

# 外扩 30mm 边距
guji crop -i ./images -o ./output --border 30

# 自定义边距（上20 右30 下20 左25）
guji crop -i ./images -o ./output --border 20,30,20,25

# 清空输出目录重新处理
guji crop -i ./images -o ./output --clean
```

## 实现要点

- **继承 TextRegionProcessor**：与 `cropremove` 共享 YOLO 检测 + 逐框裁剪 + 输出构建流程，仅 `_process_roi` 不同（crop 裁剪原图像素，cropremove 做 Otsu）。
- **不做去底色处理**：仅裁剪，保留原始图像质量，后续可配合 `rembg` 命令处理。
- **并发处理**：基于 FunctionBase 的 ThreadPoolExecutor 并发引擎。
- **无检测 fallback**：直接输出原图到输出目录，返回 `no_detect` 状态，便于后续人工排查。
- **与 cropremove 的关系**：`cropremove` 等同于 `crop` + 对每个裁剪结果执行 Otsu 去底色。
