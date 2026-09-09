# gujitools 文档

古籍处理命令行工具文档，涵盖 PDF 提取、文本框裁剪、去底色和图片生成 PDF 等功能的使用说明、算法实现与参数详解。

## 文档索引

| 文档                                               | 内容                                                           |
| -------------------------------------------------- | -------------------------------------------------------------- |
| [cli.md](cli.md)                                   | 命令行使用说明、参数表、示例、退出码、架构                     |
| [utils.md](utils.md)                               | 工具函数 API：Otsu 阈值、印章提取、border 解析、YOLO、PDF 渲染 |
| [io_path_rules.md](io_path_rules.md)               | 输入/输出路径规则（供开发参考）                                |
| [functions/overview.md](functions/overview.md)     | 功能模块概览与命令关系                                         |
| [functions/extract.md](functions/extract.md)       | PDF 提取：页码解析、缩放计算、渲染模式                         |
| [functions/crop.md](functions/crop.md)             | 文本框裁剪：YOLO 检测、area/border 规则、左右分割算法          |
| [functions/rembg.md](functions/rembg.md)           | 去底色：Otsu 阈值、HSV 印章提取、形态学去噪                    |
| [functions/cropremove.md](functions/cropremove.md) | 复合流程：area 区域模式、border 边框控制                       |
| [functions/print.md](functions/print.md)           | 图片生成 PDF：纸张、排序、标题和页码                           |

## 快速开始

```bash
# 从 PDF 提取图片
guji extract -i book.pdf -o ./images

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

| 命令         | 别名  | 功能                                     |
| ------------ | ----- | ---------------------------------------- |
| `extract`    | `-e`  | 从 PDF 提取页面为图片                    |
| `crop`       | —     | 基于 YOLO 裁剪文本框（支持 area/border） |
| `rembg`      | `-r`  | 整图去底色/二值化/印章保留               |
| `cropremove` | `-cr` | 复合流程：裁剪 + 去底色                  |
| `print`      | —     | 将图片目录生成为 PDF                     |
