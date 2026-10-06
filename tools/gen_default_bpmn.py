# -*- coding: utf-8 -*-
"""流程模板**校验**工具（两个模板都在 ``desktop/static/`` 下）。

## 为什么只剩校验（历史教训）

本脚本原来叫"生成默认 bpmn"，干的是：拿 ``ports.SUPPLIERS``（**端口级依赖边
表**）派生出 ``task_default.bpmn``。那一步做出了两份错东西：

1. **文件语义错**：端口边的意思是"这一步去谁那儿取产物"，与"先做哪一步"不是
   一回事。把它当流程连线写出来，默认流程图就从「提取图片」炸出 4 条线
   （``extract --pages--> rembg`` / ``--> imposition`` / ``--> submit``），
   画出来是一团麻，**根本不是流程图**。
2. **真源错**：模板本该是人（或页面编辑）决定的东西，却由代码派生 ⇒
   "改文件不生效、改代码才生效"，与"bpmn 文件是真源"直接矛盾。

用户 2026-10-05 的原话：

> 默认流程必须跟 task_default.bpmn 一样，不一样的，改成一样，
> **不要你自己设计默认流程**

所以现在：

- **两个模板都是手工真源**，本脚本**不生成、不改写、不覆盖**任何模板；
- 只做一件事：**校验**它们存在、能被 :class:`FlowDiagram` 解析、且至少能
  认出一个可执行步骤（也就是"页面画得出来、状态机跑得起来"）；
- 直接改模板文件即可（或在页面里用「编辑流程」改），改完跑 ``--check`` 确认
  没写坏。

用法::

    python tools/gen_default_bpmn.py            # 同 --check
    python tools/gen_default_bpmn.py --check    # 只校验（自测/CI 用）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop.steps.bpmn_diagram import FlowDiagram  # noqa: E402
from desktop.utils.files import package_dir  # noqa: E402

#: 默认流程模板（新任务用这份）
TEMPLATE_NAME = "task_default.bpmn"

#: 自定义流程初值（建任务弹窗勾「自定义」时的起点）
CUSTOM_INIT_NAME = "task_detail.bpmn"


def template_path() -> Path:
    """默认模板的标准位置。

    用 :func:`desktop.utils.files.package_dir` 而非 ``project_root``：打包后
    ``desktop`` 在 PYZ 里、磁盘上没有真实目录，模板由 spec 的 ``datas`` 落到
    ``_internal/desktop/static/``，正是这里的返回值。
    """
    return package_dir() / "static" / TEMPLATE_NAME


def custom_init_path() -> Path:
    """自定义初值的标准位置。"""
    return package_dir() / "static" / CUSTOM_INIT_NAME


def _targets() -> list[tuple[Path, str]]:
    return [
        (template_path(), "默认流程模板"),
        (custom_init_path(), "自定义流程初值"),
    ]


def _validate(path: Path, label: str) -> str | None:
    """返回错误信息；没问题返回 ``None``。"""
    if not path.is_file():
        return f"{label}不存在：{path}"
    try:
        diagram = FlowDiagram.load(path)
    except (OSError, ValueError) as exc:
        return f"{label}解析失败：{path}（{exc}）"
    if not diagram.nodes:
        return f"{label}里一个节点都没有：{path}"
    if not diagram.stage_order():
        return f"{label}里没有可执行的步骤（节点都认不出运行阶段）：{path}"
    return None


def main(argv: list[str] | None = None) -> int:
    del argv  # 只有校验一种行为（--check 保留是为了兼容既有调用）
    problems = 0
    for path, label in _targets():
        problem = _validate(path, label)
        if problem:
            print(f"✗ {problem}")
            problems += 1
            continue
        diagram = FlowDiagram.load(path)
        steps = " → ".join(diagram.stage_order())
        print(f"✓ {label}可用：{path}")
        print(f"    节点 {len(diagram.nodes)} 个，运行步骤：{steps}")
    if problems:
        print("\n⚠ 模板是**手工真源**，本工具不会自动生成——请手工修复上面列出的文件。")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
