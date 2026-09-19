# 用户操作手册与截图：维护说明

这份文档讲**怎么写/怎么维护用户手册**，以及从手册里挪出来的技术注解。
手册本身在 [`docs/guide/user-guide.md`](../../guide/user-guide.md)（应用内「用户手册」
按钮打开的就是它，渲染/打包见 [gui-ui-system.md](gui-ui-system.md) §7）。

## 1. 分工原则：用户操作手册里**不许**出现什么

手册的读者是「不懂 Python、不懂命令行的使用者」。以下内容一律留在 `docs/dev/`，
**不要写进手册**（2026-09-19 按用户要求清理过一次）：

| 不属于手册的内容 | 例子（都真出现过） | 该放哪 |
| --- | --- | --- |
| 内部文件名 | `boxes.json` / `print.json` / `stages/pdf/` | 本文件 §4 |
| CLI 命令与参数 | 「与命令行 `detect`/`crop` 同源」（仅步骤标题里的 `（extract）` 保留，用于对齐阶段名） | 本文 §4 |
| 旧版本行为 | 「想回到旧的 72 DPI 才填 72」 | 本文 §4 |
| 配置文件字段 | `title_position` / `title_orientation` 只能改配置文件 | 本文 §4 |
| 设计取舍与实现口径 | 「口径是文字轮廓边缘」「这里选了后者」「不是 2mm，而是由页边距推导」 | 本文 §4 |
| 文档/工具的维护说明 | 「截图由 `tests/gui_shot.py --guide` 生成（见文末「维护」）」 | 本文 §3 |

判断标准很简单：**用户能不能照着一句话去做一件事**。不能，就是技术说明。

## 2. 文件位置与改名时要同步的地方

手册：`docs/guide/user-guide.md`（曾名 `gui-guide.md`）。
CLI 手册是另一份：`docs/guide/cli.md`。两者在应用内以分段开关切换。

改名/换标题要同步这 6 处（漏一处就红或断链）：

| 位置 | 内容 |
| --- | --- |
| `desktop/ui/help_dialog.py` | `MANUAL_ENTRIES` 里的文件名字符串 |
| `docs/guide/readme.md` | 使用方式表里的链接 |
| `docs/README.md` | 文档树与索引表 |
| `README.md` | 文档索引一节 |
| `docs/dev/gui/readme.md` | 指向操作手册的链接 |
| 护栏 | `tests/selftests/gui_guide.py`（路径 + 三处索引断言）、`tests/selftests/docs_layout.py`（白名单与索引） |

## 3. 截图怎么刷新

```bash
cd /d/workspace/gujitools
QT_QPA_PLATFORM=offscreen KMP_DUPLICATE_LIB_OK=TRUE \
  "C:/Users/liuzu/anaconda3/envs/py310/python.exe" -u tests/gui_shot.py --guide \
  "C:/Users/liuzu/AppData/Local/Temp/guji_shots_new"
```

产出 `<输出目录>/guide/` 下 12 张（文件名是脚本里的字面量，**不得改名**）。

1. **先 md5 比对**：`md5sum guide/*.png | sort`，出现重复说明某一屏的交互态没生效
   （历史事故：三张检测截图完全相同，根因是 `ImageViewerWidget` 的递归回调导致
   两个 `PreviewWorker` 抢着 `set_image()`）；
2. 覆盖 `docs/guide/screenshots/guide/`（用 Python 脚本走 `pathlib`，别在 bash 里写中文路径）；
3. 跑护栏 `tests/gui_selftest.py --only gui_guide`；
4. 让**打包版**生效：`python build.py --manual-only`（约 2.5 分钟，见 gui-ui-system §7）。

演示数据契约（护栏会逐条核对）：优先真实古籍
（`REAL_PDF_PREFERRED`，本机在 `C:/Users/liuzu/Documents/test` 下的「龍譚精舍叢刻」），
保留合成占位图回退；演示页由 `DEMO_PAGE`（当前 4）控制，且手册里必须写明
「第 4 页」与书名——改常量就要同步改手册。

## 4. 从手册里挪出来的技术注解（存档，别丢）

这些是原先写在用户手册里、现在挪到这里的信息：

1. **渲染 DPI**：`dpi` 是**整页渲染**的分辨率下限（默认 300）。历史上默认值是 72，
   填 `72` 是"回到旧行为"的逃生口；手册只讲「一般保持 300」。
2. **整页模式与 area 的关系**：勾「整页模式：不调用 YOLO」等价于第三步
   `area = 4 (整页/不检测)`；取消勾选回到 `area = 1 (左右分开)`。整页模式
   **不写自动框**（`boxes.json` 里不会有自动检测结果），只认手动框。
3. **检测与 CLI 同源**：GUI 的检测与命令行 `detect` / `crop` / `cropremove` 走同一份
   实现，两个入口看到的框一致（`utils/box_geometry.py` 是唯一权威）。
4. **去底色输出的条目命名**：`area=1` 时按输出拆成 `N-r`（右页）/ `N-l`（左页），
   缩略图只显示所属那半页——手册里改写成「按「右页 / 左页」分开显示」。
5. **版面坐标的落盘**：第四步拖动后的逐页坐标记在任务里（`print.json`），
   只对**手动改过**的页生效，其余页按纸张/边距参数自动排版。
6. **标题/页码的位置与方向改不了**：界面刻意不提供「位置」「文字方向」两个下拉——
   标题只可能在上、页码只可能在下，摆着选项只会与「左右边距 + 上/下边距」两行自相矛盾
   （要么做动态联动，要么不要这两个参数，**这里选了后者**）。真要改位置/方向，
   只能改配置文件里的 `title_position` / `title_orientation`（见 `docs/functions/print.md`）。
7. **「距页边」的口径**：数值是**文字轮廓边缘**到纸边的距离；左右一个值同时管两边，
   所以右页的落点会自动往左退一个字宽来兑现它。不勾「自定义」时的默认值
   **不是**硬编码的 2mm，而是由页边距推导（见 `docs/functions/print.md`）。
8. **缩略图"发白"的真实原因**：页面尺寸记录（`image_size`）必须是**阶段图**尺寸；
   若被记成缩略图尺寸，检测框换算后会越界裁白，看起来像缩略图没加载完。
