# gujitools 文档

古籍处理工具文档，涵盖 PDF 提取、文本框裁剪、去底色和图片生成 PDF 等功能的使用
说明、算法实现与参数详解。桌面端（GUI）与命令行（CLI）共用同一套算法，本目录
同时收录两套入口的文档。

## 先看这里：按读者分流

| 你是谁 | 从哪看起 |
| --- | --- |
| **日常使用者**（处理古籍，不想管代码） | [`guide/`](guide/) — 操作指南，照着点 / 照着敲即可 |
| **开发者 / 维护者** | [`dev/`](dev/) — 架构、协议、布局、路径规则等实现细节 |
| **查函数签名** | [`api/`](api/README.md) — 由源码自动生成 |

```
docs/
├── guide/      给使用者：操作指南 + 命令用法 + 配图
│   ├── gui-guide.md     桌面端操作指南（配真实截图）
│   ├── cli.md           命令行使用说明
│   └── screenshots/     界面截图与操作指南配图
├── dev/        给开发者：技术细节
│   ├── gui/             桌面端 6 份技术文档（架构/规范/设计/布局/需求/界面系统）
│   ├── io_path_rules.md 输入 / 输出路径规则
│   └── utils.md         工具模块算法说明
├── functions/  CLI 命令手册（⚠️ 位置固定：被 `guji help` 运行时读取）
└── api/        自动生成的 API 参考
```

> ⚠️ **`docs/functions/` 不要移动**。它是 `guji help <命令>` 的文档来源
> （见 `utils/help.py`），且已列入 `guji.spec` 打包清单。移动会导致
> 打包后的 `guji help` 找不到手册。

## 使用指南（guide/）

| 文档 | 内容 |
| --- | --- |
| [guide/gui-guide.md](guide/gui-guide.md) | **桌面端操作指南**：从导入 PDF 到出 PDF 的完整步骤（配操作截图） |
| [guide/cli.md](guide/cli.md) | **命令行使用说明**：参数表、示例、退出码、架构 |

## 技术细节（dev/）

| 文档 | 内容 |
| --- | --- |
| [dev/gui/readme.md](dev/gui/readme.md) | 桌面端技术文档索引（术语、开发约定） |
| [dev/gui/gui-architecture.md](dev/gui/gui-architecture.md) | 模块结构、进程模型、文件存储与任务目录 |
| [dev/gui/gui-technical-spec.md](dev/gui/gui-technical-spec.md) | Worker 消息协议、JSON 数据格式、区域合成几何、缩略图规范 |
| [dev/gui/gui-design.md](dev/gui/gui-design.md) | 交互设计：导入流程、步骤条、历史配置、检测框编辑、去底色预览 |
| [dev/gui/gui-layout.md](dev/gui/gui-layout.md) | 主窗口、预览区、控制面板与日志布局 |
| [dev/gui/gui-requirements.md](dev/gui/gui-requirements.md) | 功能需求、非功能需求 |
| [dev/gui/gui-ui-system.md](dev/gui/gui-ui-system.md) | 界面系统：设计令牌、基础自绘控件、全局样式 |
| [dev/io_path_rules.md](dev/io_path_rules.md) | 输入 / 输出路径规则（供开发参考） |
| [dev/utils.md](dev/utils.md) | 工具函数算法：Otsu 阈值、印章提取、border 解析、YOLO、PDF 渲染 |

## 命令手册（functions/）

⚠️ 由 `guji help <命令>` 在运行时读取，**位置固定**。

| 文档 | 内容 |
| --- | --- |
| [functions/overview.md](functions/overview.md) | 功能模块概览与命令关系 |
| [functions/extract.md](functions/extract.md) | PDF 提取：页码解析、缩放计算、渲染模式 |
| [functions/detect.md](functions/detect.md) | 文本框检测：YOLO 推理、左右分割、坐标上报、`--save` 标注图 |
| [functions/crop.md](functions/crop.md) | 文本框裁剪：area/border 规则、左右分割算法 |
| [functions/rembg.md](functions/rembg.md) | 去底色：Otsu 阈值、HSV 印章提取、形态学去噪 |
| [functions/cropremove.md](functions/cropremove.md) | 复合流程：area 区域模式、border 边框控制 |
| [functions/print.md](functions/print.md) | 图片生成 PDF：纸张、排序、标题和页码 |

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

| 文档 | 内容 |
| --- | --- |
| [api/README.md](api/README.md) | 索引、收录范围与同步方式 |
| [api/desktop.md](api/desktop.md) | 桌面端全部公开 API（52 个模块） |
| [api/cli.md](api/cli.md) | 命令行层公开 API |
| [api/functions.md](api/functions.md) | 图像处理功能模块公开 API |
| [api/utils.md](api/utils.md) | 通用工具函数公开 API |
| [api/entrypoints.md](api/entrypoints.md) | 顶层入口脚本（main.py / desktop.py / config.py） |

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

| 命令 | 别名 | 功能 |
| --- | --- | --- |
| `extract` | `-e` | 从 PDF 提取页面为图片 |
| `detect` | — | 检测左右文本框坐标（**非必要**，默认不落盘） |
| `crop` | — | 基于 YOLO 裁剪文本框（支持 area/border） |
| `rembg` | `-r` | 整图去底色 / 二值化 / 印章保留（输出固定 PNG） |
| `cropremove` | `-cr` | 复合流程：裁剪 + 去底色 |
| `print` | — | 将图片目录生成为 PDF |

`detect` 是**非必要**步骤：`crop` / `cropremove` 内部已调用同一套检测算法，
配置模板里的 `detect:` 段落可以整段删除。它只在需要单独查看检测结果时使用。
