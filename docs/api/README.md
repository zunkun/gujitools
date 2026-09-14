<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# API 参考

本目录由 `tools/gen_api_docs.py` 从源码静态解析生成，**与代码逐次同步、不要手工编辑**。

重新生成：

```bash
python tools/gen_api_docs.py          # 生成/覆盖
python tools/gen_api_docs.py --check  # 校验是否与源码一致（CI 用）
```

## 收录范围

- **包含**：模块顶层公开类/函数、类的公开方法与 `__init__`、模块级全大写常量；
- **不含**：私有成员（`_` 开头）、第三方库符号；
- **Qt 事件覆写**（`paintEvent`、`mouse*Event`、`resizeEvent` 等）不写 docstring，由生成器按方法名统一标注语义；
- 无参数且无说明的 `__init__`（如多数控件）不单列，类说明已覆盖。

生成器只读源码（`ast` 静态解析），**不导入任何模块**，因此离线可跑、不会拉起 cv2 / torch / PySide6 等重依赖。

生成时间：2026-09-15

| 文档 | 内容 |
| --- | --- |
| [desktop](desktop.md) | 桌面端：GUI 主进程、worker 子进程、存储、界面系统 |
| [cli](cli.md) | 命令行入口层：参数解析、子命令调度 |
| [functions](functions.md) | 图像处理功能模块：GUI 与 CLI 共用同一套算法 |
| [utils](utils.md) | 通用工具函数：几何、排序、图像 IO、PDF、YOLO |
| [入口脚本](entrypoints.md) | 仓库顶层的可执行入口与配置读取 |
