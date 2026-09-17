# 技术细节文档（给开发者）

> **日常使用者请到此为止**：如果你只是想处理古籍，
> 请看 [操作指南 `../guide/`](../guide/)（桌面端点鼠标、命令行敲命令）。
> 本目录讲「为什么这么实现」，不是「怎么操作」。

## 目录

| 文档 | 内容 |
| --- | --- |
| [gui/readme.md](gui/readme.md) | **桌面端技术文档索引**：术语、开发约定、快速开始 |
| [io_path_rules.md](io_path_rules.md) | 输入 / 输出路径规则（输出目录解析的唯一权威） |
| [utils.md](utils.md) | 工具模块算法：Otsu 阈值、印章提取、border 解析、YOLO、PDF 渲染 |

桌面端（6 份）见 [gui/readme.md](gui/readme.md)：架构、技术规范、交互设计、
布局、需求、界面系统。

## 相关

- [../functions/](../functions/) — CLI 命令手册（⚠️ 被 `guji help` 运行时读取，勿移动）
- [../api/README.md](../api/README.md) — 自动生成的 API 参考
- [../README.md](../README.md) — 文档总索引

## ⚠️ 目录约定

`docs/` 按**读者**而非按模块划分：

- `guide/` — 给使用者（操作指南 + 命令用法 + 配图）
- `dev/` — 给开发者（架构 / 协议 / 布局 / 路径规则）
- `functions/` — **位置固定**，`guji help` 的文档来源（`utils/help.py`）
- `api/` — 自动生成产物

新增文档时按这四类归位；移动 `functions/` 会破坏打包后的 `guji help`。
