# gujitools 文档

古籍处理工具文档，涵盖 PDF 提取、文本框裁剪、去底色和图片生成 PDF 等功能的使用
说明、算法实现与参数详解。桌面端（GUI）与命令行（CLI）共用同一套算法，本目录
同时收录两套入口的文档。

- 桌面端文档入口：[gui/readme.md](gui/readme.md)
- 命令行文档入口：[cli.md](cli.md)
- 全量 API 参考：[api/README.md](api/README.md)

## 文档索引

| 文档                                               | 内容                                                           |
| -------------------------------------------------- | -------------------------------------------------------------- |
| [cli.md](cli.md)                                   | 命令行使用说明、参数表、示例、退出码、架构                     |
| [utils.md](utils.md)                               | 工具函数 API：Otsu 阈值、印章提取、border 解析、YOLO、PDF 渲染 |
| [io_path_rules.md](io_path_rules.md)               | 输入/输出路径规则（供开发参考）                                |
| [functions/overview.md](functions/overview.md)     | 功能模块概览与命令关系                                         |
| [functions/extract.md](functions/extract.md)       | PDF 提取：页码解析、缩放计算、渲染模式                         |
| [functions/detect.md](functions/detect.md)         | 文本框检测：YOLO 推理、左右分割、坐标上报、`--save` 标注图     |
| [functions/crop.md](functions/crop.md)             | 文本框裁剪：area/border 规则、左右分割算法                     |
| [functions/rembg.md](functions/rembg.md)           | 去底色：Otsu 阈值、HSV 印章提取、形态学去噪                    |
| [functions/cropremove.md](functions/cropremove.md) | 复合流程：area 区域模式、border 边框控制                       |
| [functions/print.md](functions/print.md)           | 图片生成 PDF：纸张、排序、标题和页码                           |

## 桌面端（GUI）文档

桌面端已实现，与 `desktop/` 当前代码对齐；完整索引见
[gui/readme.md](gui/readme.md)。

| 文档                                                   | 内容                                      |
| ------------------------------------------------------ | ----------------------------------------- |
| [gui/gui-ui-system.md](gui/gui-ui-system.md)           | 界面系统：设计令牌、基础自绘控件、全局样式 |
| [gui/gui-architecture.md](gui/gui-architecture.md)     | 模块结构、进程模型、文件存储与任务目录    |
| [gui/gui-technical-spec.md](gui/gui-technical-spec.md) | Worker 消息协议、JSON 数据格式、区域合成几何、缩略图规范 |
| [gui/gui-design.md](gui/gui-design.md)                 | 交互设计：导入流程、步骤条、历史配置、检测框编辑、去底色预览 |
| [gui/gui-requirements.md](gui/gui-requirements.md)     | 功能需求、非功能需求（与 desktop/ 实现对齐） |
| [gui/gui-layout.md](gui/gui-layout.md)                 | 主窗口、预览区、控制面板与日志布局        |

## API 参考（自动生成）

[`api/`](api/README.md) 由 [tools/gen_api_docs.py](../tools/gen_api_docs.py) 用标准库
`ast` **静态解析源码**生成（不导入模块，因此不依赖 cv2/torch/PySide6，离线可跑）。
源码改动后重跑即可同步：

```bash
python tools/gen_api_docs.py          # 生成 / 覆盖 docs/api/*.md
python tools/gen_api_docs.py --check  # 只校验：与源码不一致时退出码非 0
python tools/check_docs.py            # 校验全部文档：相对链接、锚点、GFM 表格列数
```

`tools/check_docs.py` 会遍历本目录与根 `README.md` 的所有 Markdown，检查相对链接
目标是否存在、`#锚点` 是否命中、表格每行列数是否与表头一致；发现问题时列出文件与
行号并以非 0 退出码结束，适合接入 CI 或提交前自检。

| 文档                                             | 内容                                     |
| ------------------------------------------------ | ---------------------------------------- |
| [api/README.md](api/README.md)                   | 索引、收录范围与同步方式                  |
| [api/desktop.md](api/desktop.md)                 | 桌面端全部公开 API（52 个模块）           |
| [api/cli.md](api/cli.md)                         | 命令行层公开 API                          |
| [api/functions.md](api/functions.md)             | 图像处理功能模块公开 API                  |
| [api/utils.md](api/utils.md)                     | 通用工具函数公开 API                      |
| [api/entrypoints.md](api/entrypoints.md)         | 顶层入口脚本（main.py / desktop.py / config.py） |

## 快速开始

```bash
# 从 PDF 提取图片
guji extract -i book.pdf -o ./images

# 只看检测结果（不落盘）
guji detect -i ./images

# 裁剪文本框
guji crop -i ./images -o ./cropped

# 去底色（二值化）
guji rembg -i ./images -o ./output

# 一步完成裁剪 + 去底色
guji cropremove -i ./images -o ./output

# 从 YAML 配置生成 PDF
guji run print
```

## 命令一览

| 命令         | 别名  | 功能                                           |
| ------------ | ----- | ---------------------------------------------- |
| `extract`    | `-e`  | 从 PDF 提取页面为图片                          |
| `detect`     | —     | 检测左右文本框坐标（**非必要**，默认不落盘）   |
| `crop`       | —     | 基于 YOLO 裁剪文本框（支持 area/border）       |
| `rembg`      | `-r`  | 整图去底色/二值化/印章保留（输出固定 PNG）     |
| `cropremove` | `-cr` | 复合流程：裁剪 + 去底色                        |
| `print`      | —     | 将图片目录生成为 PDF                           |

`detect` 是**非必要**步骤：`crop` / `cropremove` 内部已调用同一套检测算法，
配置模板里的 `detect:` 段落可以整段删除。它只在需要单独查看检测结果时使用。
