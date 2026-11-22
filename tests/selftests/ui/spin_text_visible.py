# -*- coding: utf-8 -*-
"""数值输入框必须**看得见值**（2026-11-21 打包版事故）。

用户报：「本地安裝版本（剛打包的）很多輸入框都不顯示值了，開發版正常」。
现场是：值其实还在（``spin.text()`` 正确），但输入框里一个像素都不画，
只剩右边两个「上/下」箭头——看着就像整个界面的参数都丢了。

根因不在我们的面板代码，而在**构建环境的 Qt 版本**：
qfluentwidgets 1.11.3 的 ``SpinBox`` 把上/下按钮放进自己的 ``QHBoxLayout``
（``InlineSpinBoxBase.__init__``）。PySide6 **6.11** 起 ``QAbstractSpinBox``
按"控件已有布局"的方式排内部 ``QLineEdit``，把它压到 **1px 宽**；

* 开发机 PySide6 6.9.2 → lineEdit 宽 246px，文字正常；
* 构建机（``yolobuild``）PySide6 6.11.3 → lineEdit 宽 **1px**，文字全被裁掉。

修法是 ``safecomponents.keep_spin_text_visible``：给内部 ``QLineEdit`` 一个
"放得下最长文本"的**最小**宽度（不是固定宽，6.9 上布局照旧拉伸）。本模块
钉住三件事：

1. 我们所有的 ``Safe*SpinBox`` 建出来后，内部编辑框宽度够放下值；
2. 该兜底函数对**裸** qfluentwidgets spin 也有效（拼版角度框这类直接用的
   地方一旦漏掉兜底，就会在 6.11 的包里变成"空框"）；
3. ``desktop/`` 下不许再出现裸 ``SpinBox(...)`` / ``DoubleSpinBox(...)``
   构造——一律走 ``safecomponents``，否则新加的面板会在打包版里瞎掉。
"""

NAME = "spin_text_visible"
DEPENDS: list[str] = []
TITLE = "数值输入框必须看得见值（Qt 6.11 打包事故）"

#: 一个值的文本至少要占这么宽才可能看得见（"0000.0 mm" 在 13px 字号下约 70px）
MIN_TEXT_W = 60


def run(ctx) -> None:
    import re
    from pathlib import Path

    from PySide6.QtWidgets import QVBoxLayout, QWidget
    from qfluentwidgets import DoubleSpinBox

    from tests.selftests._context import ok, pump

    from desktop.components.common.safecomponents import (
        SafeCompactDoubleSpinBox, SafeCompactSpinBox, SafeDoubleSpinBox,
        SafeSpinBox, keep_spin_text_visible,
    )

    app = ctx.app
    host = QWidget()
    box = QVBoxLayout(host)
    host.resize(460, 320)

    cases = (
        ("SafeSpinBox", SafeSpinBox(), 20, " pt"),
        ("SafeDoubleSpinBox", SafeDoubleSpinBox(), 20.0, " mm"),
        ("SafeCompactSpinBox", SafeCompactSpinBox(), 7, " 页"),
        ("SafeCompactDoubleSpinBox", SafeCompactDoubleSpinBox(), 1.5, " 倍"),
    )
    spins = []
    for name, spin, value, suffix in cases:
        spin.setRange(-1000, 3000)
        if hasattr(spin, "setDecimals") and isinstance(value, float):
            spin.setDecimals(1)  # 让 text() 的期望值可预测（默认 2 位）
        spin.setSuffix(suffix)
        spin.setValue(value)
        box.addWidget(spin)
        spins.append((name, spin, value, suffix))
    host.show()
    pump(app)

    for name, spin, value, suffix in spins:
        edit = spin.lineEdit()
        expected = (
            f"{value:.1f}{suffix}" if isinstance(value, float) else f"{value:g}{suffix}"
        )
        ok(
            f"{name} 的值看得见（编辑框不塌成 1px）",
            edit.width() >= MIN_TEXT_W,
            f"text={spin.text()!r} 编辑框宽={edit.width()}px",
        )
        ok(
            f"{name} 文本确实是那个值",
            spin.text() == expected,
            f"实际={spin.text()!r} 期望={expected!r}",
        )

    # ---- 裸 qfluent spin：兜底函数必须把它救回来 ----
    bare = DoubleSpinBox()
    bare.setRange(0.0, 3000.0)
    bare.setSuffix(" mm")
    bare.setValue(12.5)
    box.addWidget(bare)
    pump(app)
    keep_spin_text_visible(bare)
    pump(app)
    ok(
        "裸 qfluent DoubleSpinBox 调一次兜底就恢复正常宽度",
        bare.lineEdit().width() >= MIN_TEXT_W,
        f"text={bare.text()!r} 编辑框宽={bare.lineEdit().width()}px",
    )

    # ---- 真面板：print「距页边」四个框（用户截图里空掉的就是它们）----
    from desktop.components.panels.print_panel import PrintPanel

    panel = PrintPanel()
    panel.resize(520, 1200)
    panel.show()
    pump(app)
    for which in ("title", "page_number"):
        block = getattr(panel, f"_{which}_inset")
        for key, spin in block["widgets"].items():
            ok(
                f"PDF排版「{which}/{key}」距页边框显示值",
                spin.lineEdit().width() >= MIN_TEXT_W and "mm" in spin.text(),
                f"text={spin.text()!r} 编辑框宽={spin.lineEdit().width()}px",
            )

    # ---- 源码守卫：不许再直接 new 裸 qfluent spin ----
    pattern = re.compile(
        r"(?<![A-Za-z0-9_])(?:CompactDoubleSpinBox|CompactSpinBox|DoubleSpinBox|SpinBox)\s*\("
    )
    root = Path(__file__).resolve().parents[3] / "desktop"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "safecomponents.py":
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(root)}:{lineno}")
    ok(
        "desktop/ 下没有裸 qfluent spin 构造（一律走 Safe*）",
        not offenders,
        "，".join(offenders[:5]) or "干净",
    )

    panel.close()
    host.close()
