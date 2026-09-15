# -*- coding: utf-8 -*-
"""详情页结构自测：四个阶段的标签页/步骤条/面板/预览区结构。

含「窗口压缩守卫」：控制面板表单统一装在滚动区里，可视区不足时纵向滚动
而不是被静默裁剪（rembg 表单行曾因卡片高度不足而挤进相邻行）。

注意：这些断言必须在**真正显示**详情页之后做。藏在 QStackedWidget 里
未选中的页面从未参与布局，qfluentwidgets ScrollArea 是懒构建的，未显示
时 layout() 为 None、viewport/inner 都是 480x640 的脏默认值——据此算出
的「有没有滚动条」全是假的（详见 _context.show_detail 的说明）。
"""

NAME = "detail_structure"
DEPENDS: list[str] = ["tasklist"]
TITLE = "详情页结构"


def run(ctx) -> None:
    from qfluentwidgets import ScrollArea

    from desktop.ui import theme as T
    from tests.selftests._context import ok, pump, show_detail

    app, w, d = ctx.app, ctx.w, ctx.d

    ok("extract 双标签页", d.extract_tabs.count() == 2
       and d.extract_tabs.tabText(0) == "PDF 预览"
       and d.extract_tabs.tabText(1) == "提取结果")
    ok("步骤条 4 步", len(d.step_bar.buttons) == 4)
    ok("控制面板 4 个", d.control_stack.count() == 4)
    ok("预览区 4 个", d.preview_stack.count() == 4)

    # ---- 窗口压缩守卫：真显示后再量 ----
    # rembg 表单行最多，可视区最紧张，压缩最先在它身上显形
    rembg_panel = show_detail(ctx, stage=2)
    scroll = rembg_panel.findChild(ScrollArea)
    ok("rembg 表单装在可滚动容器里",
       scroll is not None and scroll.widgetResizable())
    if scroll is None:
        return

    inner = scroll.widget()
    natural = inner.minimumSizeHint().height()
    viewport_h = scroll.viewport().height()
    vb = scroll.verticalScrollBar()

    # 前置：确实触发了压缩场景（可视区装不下表单自然高度）
    ok("可视区装不下表单自然高度（压缩场景成立）",
       viewport_h < natural, f"可视区 {viewport_h} vs 表单 {natural}")
    # 核心：表单不被压扁——内容保持自然高度，高度差交给滚动
    ok("表单保持自然高度而非被压扁",
       inner.height() >= natural - 2, f"{inner.height()} vs {natural}")
    ok("可视区不足时提供纵向滚动（无滚动=被静默裁剪）",
       vb.maximum() == natural - viewport_h,
       f"max={vb.maximum()} 期望 {natural - viewport_h}")

    # 滚到底：底部内容能完整进入可视区
    vb.setValue(vb.maximum())
    pump(app)
    ok("滚到底后底部控件完整可见",
       inner.height() - vb.value() <= viewport_h + 2,
       f"{inner.height()} - {vb.value()} vs {viewport_h}")

    ok("滚动条宽度取自主题常量（细滚动条样式生效）",
       0 < T.SCROLLBAR_WIDTH < 16, f"{T.SCROLLBAR_WIDTH}")

    # 复原：滚回顶部，切回第一步
    vb.setValue(0)
    d._select_stage(0)
    pump(app)
