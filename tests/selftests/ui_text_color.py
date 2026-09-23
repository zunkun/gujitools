# -*- coding: utf-8 -*-
"""文字上色自测：``apply_to(color=…)`` 必须**真的画出来**，以及状态行只有一个入口。

背景（2026-09-23 用户截图报「这个红色没有修改过来」）：
`desktop.ui.widgets.apply_to` 原来一律用 ``setPalette`` 上色，但 qfluentwidgets 的
标签（``FluentLabelBase`` 子类：CaptionLabel / BodyLabel / StrongBodyLabel /
TitleLabel / SubtitleLabel）**不读调色板**，它们用 ``setStyleSheet("color: …")``
自己画（公开接口是 ``setTextColor``）。结果是：调色板里写着 ``#C93A3A``、
画出来是**纯黑**，而当时那条"查 palette()"的护栏一直是**假绿**。

所以本模块有两层判据：

1. **必须看渲染像素**（``_context.painted_color``）——只查 ``palette()`` 或
   ``styleSheet()`` 都只能证明"设了"，证明不了"画了"；三种控件（qfluent 的
   CaptionLabel / BodyLabel + 原生 QLabel）都要各验一遍红→复位。
2. **状态行只有一个写入口**（源码级扫描）——``stage_status`` 被三处共用
   （常规状态 / 版面已修改 / 上游已跑），只要有一处直接 ``setText`` 绕过
   ``_set_stage_status``，上一条提示的红字就会**留在**下一条文案上。
"""

NAME = "ui_text_color"
DEPENDS: list[str] = ["tasklist"]
TITLE = "文字上色（apply_to）"


def run(ctx) -> None:
    from PySide6.QtWidgets import QLabel
    from qfluentwidgets import BodyLabel, CaptionLabel

    from desktop.ui import theme as T
    from desktop.ui.widgets import apply_to
    from tests.selftests._context import ROOT, is_reddish, ok, painted_color, pump

    app = ctx.app
    sample = "上游已重新执行，本步产物可能已过期"

    for cls in (CaptionLabel, BodyLabel, QLabel):
        label = cls(sample)
        label.resize(320, 26)
        label.show()
        pump(app, 2)

        apply_to(label, T.SIZE_CAPTION, color=T.DANGER)
        pump(app, 2)
        painted = painted_color(label)
        palette = label.palette().color(label.foregroundRole()).name()
        ok(f"{cls.__name__} 上警示色后**真的画成红字**",
           is_reddish(painted),
           f"实际渲染 {painted}（调色板 {palette}；qfluent 标签不看它）")

        # 颜色必须能复位：否则一条提示的红字会跟着下一条文案
        apply_to(label, T.SIZE_CAPTION, color=T.INK_SOFT)
        pump(app, 2)
        ok(f"{cls.__name__} 换回常规柔和色后不再是红字",
           not is_reddish(painted_color(label)), str(painted_color(label)))
        label.deleteLater()

    # ---- 状态行的所有写入必须统一走 _set_stage_status ----
    # 用 ast 找到每个 `self.stage_status.setText(...)` 的**所在函数**，只放行
    # `_set_stage_status` 自己（它就是那个唯一入口，里面当然要 setText）。
    import ast

    def enclosing_funcs(tree: ast.AST) -> list[tuple[int, int, str]]:
        spans = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno)
                spans.append((node.lineno, end, node.name))
        return spans

    writers, bypass = [], []
    for path in sorted((ROOT / "desktop" / "pages" / "taskdetail").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        spans = enclosing_funcs(tree)
        for node in ast.walk(tree):
            func = node.func if isinstance(node, ast.Call) else None
            if not isinstance(func, ast.Attribute) or func.attr != "setText":
                continue
            target = func.value
            if not (isinstance(target, ast.Attribute)
                    and target.attr == "stage_status"):
                continue
            owner = min(
                ((end - start, name) for start, end, name in spans
                 if start <= node.lineno <= end),
                default=(0, None),
            )[1]
            where = f"{path.name}:{node.lineno}"
            if owner == "_set_stage_status":
                writers.append(where)
            else:
                bypass.append(f"{where}({owner})")

    ok("状态行的写入点存在（别因为扫描没匹配上而假绿）", writers, str(writers))
    ok("状态行只有 _set_stage_status 一个写入口（颜色才会跟着一起重置）",
       not bypass, f"绕过颜色的写法：{bypass}")
