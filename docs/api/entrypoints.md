<!-- 本文件由 tools/gen_api_docs.py 自动生成，请勿手工编辑。修改源码后重跑生成命令即可。 -->

# 入口脚本 API 参考

仓库顶层的可执行入口与配置读取

覆盖 3 个模块、0 个公开类、2 个公开函数/方法（生成于 2026-09-16）。

> 生成命令：`python tools/gen_api_docs.py`。签名与说明均直接取自源码，表格中标注 _—_ 表示该符号尚未编写 docstring。

## 模块一览

| 模块 | 类 | 函数 |
| --- | --- | --- |
| [`main`](#main) | 0 | 1 |
| [`desktop`](#desktop) | 0 | 1 |
| [`config`](#config) | 0 | 0 |

---

## `main`

源码：[`main.py`](../../main.py)

gujitools 程序主入口。

古籍处理命令行工具（gujitools），提供 PDF 提取、文本区域检测/裁剪、去底色等功能。

入口职责:
- 注册 SIGINT (Ctrl+C) 信号处理，实现优雅中断；
- 调用 CLI 层的 `cli_main()` 进行命令解析与功能分发。

启动方式:
    python main.py <command> [options]
    或打包后: guji <command> [options]

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `main() -> None` | 程序主入口：注册信号处理并委托给 CLI 层。 |

---

## `desktop`

源码：[`desktop.py`](../../desktop.py)

gujitools 桌面端与 worker 统一入口。

- 启动 GUI：            python desktop.py   （或 hupper -m desktop 热重载开发）
- 子进程执行单个子任务： python desktop.py --worker --config <json>

### 模块函数

| 函数 | 说明 |
| --- | --- |
| `main() -> int` | 桌面端统一入口：按参数路由到 GUI 或 worker 子进程。 |

#### `main() -> int`

桌面端统一入口：按参数路由到 GUI 或 worker 子进程。

若命令行含 --worker 则作为 GUI 子进程执行 desktop.worker.main()，
否则启动 GUI（desktop.app.main()）。返回值为进程退出码。

---

## `config`

源码：[`config.py`](../../config.py)

gujitools 全局配置常量。

当前仅暴露 VERSION（程序版本号 "1.0"），供 CLI/GUI 的 --version 等场景读取。
各功能的运行时配置主要来自命令行参数与 guji.yaml，不在本模块维护。

### 模块常量

| 名称 | 值 |
| --- | --- |
| VERSION | `"1.0"` |

---
