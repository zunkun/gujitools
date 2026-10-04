---
name: gujitools-dev
description: 在 gujitools（古籍重製）仓库里做任何开发、重构、修 bug、写文档前使用。提供本仓库的验证流程：自测按改动分档攒批跑、API 文档与文档自检同步、常见契约自测模块对应关系，以及动代码前的契约检查清单（分层、缓存隔离、公共组件输入输出契约）。触发词：gujitools、古籍重製、gui_selftest、desktop 模块、singletask、taskdetail。
---

# gujitools 开发流程

先读仓库根 `AGENTS.md`（分层、事实来源、契约一页读完）；本文只讲**怎么干活**。
深入架构见 `docs/dev/architecture.md`，桌面端细节见 `docs/dev/gui/gui-architecture.md`。

## 动代码前：契约检查清单

1. **分层**：`utils ← core ← {cli, functions, desktop}` 严格单向；desktop 禁止
   import cli；模块页（`desktop/modules/`）不许 import `desktop.pages`
   （壳层 `shell.py` 例外）。守卫：`tests/selftests/layering.py`。
2. **公共组件契约**：组件只认「输入 + 输出 + 参数」（`StepRequest(source, dest,
   args)`；面板只有 `get_args/apply_args/reset_to_default`）。往组件加宿主专属
   概念之前停手——用构造参数声明（先例：`ImpositionPanel(enable_switch=…)`）。
3. **缓存隔离**：singletask 缓存 `singletask/<key>/` 与 taskdetail 缓存
   `tasks/<id>/thumbnails/` 各归各，禁止借道。守卫：
   `tests/selftests/imposition.py` 的缓存边界断言。
4. **别另写事实来源**：CLI 参数在 `core/command_spec.py`、桌面默认值在
   `components/panels/params_spec.py`、步骤元数据在 `desktop/steps/spec.py::SPECS`、
   流程连线在 `steps/ports.py::SUPPLIERS`。发现自己要复制一张表/一份文案，
   先找这里。

## 改完代码后：验证三件套（攒批跑）

⚠️ 自测比较耗时，**不要每改一小处就跑**：把相关改动攒批，最后统一跑。

```bash
# ① GUI 自测：--only 按改动选模块（自动补依赖），动共享底层才全量
QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py --only <模块1[,模块2]>

# ② API 文档同步（docs/api/ 自动生成，改了 py 源码必须过）
python tools/gen_api_docs.py --check      # 过期就去掉 --check 重新生成

# ③ 文档自检（改了任何 md 后）
python tools/check_docs.py
```

⚠️ 自测退出码 **127 是伪错误**（末段 `QThread: Destroyed`），且会吃掉收尾一批
模块：比对 `--list` 的计划数与日志里 `==标题==` 出现次数，缺了用 `--only` 补跑。

### 改动 → 自测模块速查

| 改了什么 | --only 跑什么 |
| --- | --- |
| `desktop/steps/`（spec/ports/kernel/source_zone） | `steps_components,step_ports,modules_shell` |
| `desktop/components/panels/` | `params_spec,detail_structure` |
| `desktop/components/viewers/` | `preview,imposition`（按具体 viewer） |
| `desktop/modules/`（独立任务页） | `modules_shell,module_edit_sync,detect_module_page` |
| `desktop/pages/taskdetail/` | `detail_structure,imposition`（拼版相关必跑） |
| `desktop/store/`、缓存路径 | `imposition,layering` |
| `core/`、`utils/box_geometry` | 全量 + `tests/reporter_cli_parity.py` |

## 改文档后

- user-guide / cli.md 属于**用户操作文档**，会被打进安装包手册：
  改完要 `python build.py --manual-only` 才进安装包（开发模式改完即见）。
- `docs/functions/` 位置固定（`guji help` 运行时读取），不要移动。
- 手册配图受 `tests/selftests/gui_guide.py` 护栏：文件名常量两边一致、无孤儿图。

## 其他坑

- 仓库长期有未提交在制品：**不自动 `git commit`**（等用户明示）；回滚禁用
  `git checkout HEAD -- <路径>`，用标记字符串切片替换，先备份。
- `QThread.run()` 必须 try/except；跨线程用 `desktop.workers.connect_queued`。
- 中文路径图像读写走 `utils.image_io`；GUI 主进程不许 import cv2/torch。
- 运行环境：conda env `py310`（Git Bash 已 conda init）。
