# -*- coding: utf-8 -*-
"""参数标签过长时的折行自测：保证**输入框**不被长标签挤短。

背景（用户 2026-09-23 截图报的）：QFormLayout 的标签列宽 = 所有行里最宽的
那个标签，所以一条长标签会把**整张面板**的输入框一起压扁——第三步
「印章最小饱和度（sealmin_sat）」整条 240px，把全部字段压到 **112px**
（「边距」的占位文字「留空 或 30 / 20,30 / 20,30,25,35」被截、
「阈值偏移」的滑块也短得没法拖）。

修法与口径（用户原话：「参数 label 太长了，如果太长，英文可以放在下一行，
保证输入框表单够长」）——`StagePanel._fit_label` 三档：

1. 整条 ≤ ``LABEL_MAX_WIDTH`` → 原样一行；
2. 整条超了、但**折行后两段都 ≤ 上限** → 把尾部「（键名）」挪到第二行；
3. 连「（键名）」那行自身都超上限（`（sealmin_sat）` 有 156px，括号里的
   下划线英文没法再断行）→ 该行改成「上标签 / 下控件」，输入框吃满卡片。

⚠️ **断言一律不写死像素、也不写死"哪条标签该折行"**。字体在整跑过程中会变
（字体自测模块会装 CJK 字体；详情页的面板在变字体**之前**构造，已经按当时的
度量定好了折行，而模块里**新建**的面板用变后的度量）——第一版就栽在这：
同一条标签，页面上的那一份判"上下排"、新建的那一份判"折行"。
所以这里判的是**机制（三档规则，用当前字体自造标签）**与**不变量**
（标签列不超上限、字段列够宽、每段标签都不超上限），对字体不敏感。
"""

NAME = "panel_label_fit"
DEPENDS: list[str] = ["tasklist"]
TITLE = "参数标签折行"

#: 字段列的最小可接受宽度（px）。修复前第三步是 112；取 200 既留出字体差异的
#: 余量，又能把 112 那种回归卡住（不折行时字段 = 卡片宽 - 标签列 - 间距）。
FIELD_MIN_WIDTH = 200


def _form(panel):
    """取面板里参数表单所在的那个 QFormLayout。"""
    from PySide6.QtWidgets import QFormLayout

    forms = panel.findChildren(QFormLayout)
    assert forms, "面板里没有 QFormLayout"
    return forms[0]


def _rows(panel):
    """逐行拆出这一行是「并排」还是「跨列」，以及各自的尺寸。

    ⚠️ 「跨列」只能靠 ``getWidgetPosition`` 的 ``SpanningRole`` 判：**空标签的
    行**（勾选项写 ``_add_row(form, "", widget)``）在 LabelRole 里也是空的，
    照「LabelRole 没控件就算跨列」会把它们一起算进来（第一版就栽在这）。
    跨列行是**两行**：标签一行、控件一行，两行都报 SpanningRole；所以跨列的
    标签行要靠"控件是个 QLabel"认出来。
    """
    from PySide6.QtWidgets import QFormLayout, QLabel

    form = _form(panel)
    out = []
    for row in range(form.rowCount()):
        item = form.itemAt(row, QFormLayout.ItemRole.FieldRole)
        widget = item.widget() if item is not None else None
        if widget is None:
            continue
        _, role = form.getWidgetPosition(widget)
        spanning = role == QFormLayout.ItemRole.SpanningRole
        label_item = form.itemAt(row, QFormLayout.ItemRole.LabelRole)
        label_widget = label_item.widget() if label_item is not None else None
        is_label_row = spanning and isinstance(widget, QLabel)
        if is_label_row:
            text, label_width = widget.text(), 0
        else:
            text = label_widget.text() if label_widget is not None else ""
            label_width = label_widget.width() if label_widget is not None else 0
        out.append({
            "label": text,
            "label_w": label_width,
            "stacked": spanning,
            "is_label_row": is_label_row,
            "field_w": widget.width(),
            "field_kind": type(widget).__name__,
        })
    return out


def run(ctx) -> None:
    from desktop.components.panels.rembg_panel import RembgPanel
    from tests.selftests._context import ok, show_detail

    # ---------- 1. 三档规则（拿同一块面板的字体自造标签，不碰具体文案）----------
    probe = RembgPanel()
    metrics = probe.fontMetrics()
    limit = probe.LABEL_MAX_WIDTH
    unit = metrics.horizontalAdvance("中")
    assert unit > 0, "字体度量拿不到宽度（环境有问题，后面的断言会假绿）"
    n_fit = max(1, limit // unit)          # 恰好不超上限的中文字数
    ok("上限是正数且能容纳至少一个字", limit > 0 and n_fit >= 1,
       f"上限 {limit} / 单字 {unit}")

    # (a) 短的 / 恰好到上限：原样一行
    for text in ("纸张尺寸", "中" * n_fit):
        ok(f"不超上限的标签原样一行（「{text[:8]}…」）",
           probe._fit_label(text) == (text, False), str(probe._fit_label(text)))

    # (b) 整条超了、键名那行放得下 → 键名折到第二行
    head = "中" * n_fit
    foldable = f"{head}（zoom）"
    assert metrics.horizontalAdvance(foldable) > limit, "前提不成立：整条没超上限"
    assert metrics.horizontalAdvance("（zoom）") <= limit, "前提不成立：键名行太宽"
    ok("整条超宽但键名行放得下 → 键名折到第二行",
       probe._fit_label(foldable) == (f"{head}\n（zoom）", False),
       str(probe._fit_label(foldable)))

    # (c) 连「（键名）」那行自身都超上限 → 整行上下排
    huge_key = "（" + "x" * 60 + "）"
    assert metrics.horizontalAdvance(huge_key) > limit, "前提不成立：键名行没超上限"
    stacked_label = f"中{huge_key}"
    ok("连键名那行都超上限 → 整行上下排",
       probe._fit_label(stacked_label) == (stacked_label, True),
       str(probe._fit_label(stacked_label)))

    # (d) 没有括号的超长标签 → 也只能整行上下排（别原样丢回去把字段压扁）
    bare = "中" * (n_fit * 2 + 4)
    ok("无括号的超长标签 → 整行上下排",
       probe._fit_label(bare) == (bare, True), str(probe._fit_label(bare)))

    # (e) 空标签 / 已含换行的：不做二次处理（幂等，避免重复折行）
    ok("空标签原样返回", probe._fit_label("") == ("", False), str(probe._fit_label("")))
    ok("已含换行的标签不会二次折行",
       probe._fit_label("边距(mm)\n（border）") == ("边距(mm)\n（border）", False))

    # ---------- 2. 真实面板的不变量（与字体无关）----------
    rembg = show_detail(ctx, 2)
    rows = _rows(rembg)
    side = [r for r in rows if not r["stacked"]]
    stacked_fields = [r for r in rows if r["stacked"] and not r["is_label_row"]]
    ok("第三步表单已布局出多行", len(side) >= 4, f"并排 {len(side)} 行")

    widest_label = max(r["label_w"] for r in side)
    ok("第三步标签列宽不超过上限（不折行时会被最长的标签顶到 240）",
       widest_label <= limit, f"{widest_label} > {limit}")

    # 每一条并排行的标签、以及折行后的每一段，都必须放得下
    oversized = [r["label"] for r in side
                 if any(metrics.horizontalAdvance(part) > limit
                        for part in r["label"].split("\n") if part)]
    ok("第三步没有任何一段标签超过上限（折行是真的按两段各自量的）",
       not oversized, str(oversized))

    widest_field = max(r["field_w"] for r in side)
    ok(f"第三步并排行的输入框够宽（≥{FIELD_MIN_WIDTH}px，不折行时只有 112）",
       widest_field >= FIELD_MIN_WIDTH, f"{widest_field}px")

    if stacked_fields:
        full = _form(rembg).parentWidget().width()
        ok("跨列行的输入框吃满整张卡片宽度",
           all(r["field_w"] >= full - 12 for r in stacked_fields),
           f"跨列字段 {[r['field_w'] for r in stacked_fields]} / 表单宽 {full}")
        ok("跨列行的输入框明显比并排行更宽（这才是把宽度让出来的意义）",
           min(r["field_w"] for r in stacked_fields) > widest_field + 50,
           f"跨列 {[r['field_w'] for r in stacked_fields]} / 并排最宽 {widest_field}")

    # ---------- 3. 第一步：标签都不长，同样只是"放得下"这条不变量 ----------
    extract = show_detail(ctx, 0)
    e_rows = _rows(extract)
    e_side = [r for r in e_rows if not r["stacked"]]
    ok("第一步表单已布局出多行", len(e_side) >= 5, f"并排 {len(e_side)} 行")
    e_widest = max(r["label_w"] for r in e_side)
    ok("第一步标签列、字段列同样满足不变量",
       e_widest <= limit and max(r["field_w"] for r in e_side) >= FIELD_MIN_WIDTH,
       f"标签 {e_widest} / 字段 {max(r['field_w'] for r in e_side)}")
