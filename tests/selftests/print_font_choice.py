# -*- coding: utf-8 -*-
"""第四步字体：可选、可保存、生僻字自动降级。

守住五条不变量：

1. **不能指定死**：字体是一张**候选表 + 降级链**，仿宋优先但绝不是唯一解；
2. **优先级是用户定的顺序**：仿宋 → 宋体 → 微软雅黑 → 黑体 → 其它；
3. **补字字体只补字**：宋体-ExtB 这类只有扩展区生僻字的字体**不出现在
   可选列表**，也不能当主字体（它连常用字都没有）；
4. **生僻字不空白**：主字体缺字形时逐字顺位降级，常用字仍是仿宋；
5. **参数三层一致**：CLI / 桌面 / guji.yaml 都有 title_font 与
   page_number_font（标题与页码各一个），且默认都是"自动"。
"""

NAME = "print_font_choice"
DEPENDS: list[str] = []
TITLE = "第四步字体：可选 / 可保存 / 生僻字降级"

#: 扩展 B 的生僻字：仿宋、宋体、雅黑、黑体**都没有**，只能靠补字字体
_RARE_CHAR = "\U00020BB7"  # 𠮷
_COMMON_CHAR = "古"


def run(ctx) -> None:
    import os

    from tests.selftests._context import ok

    from utils.fonts import (
        GROUP_FANGSONG, GROUP_HEI, GROUP_OTHER, GROUP_SONG, GROUP_SUPPLEMENT,
        GROUP_YAHEI, find_entry, known_entries, pick_font, resolve_chain,
        selectable_entries, supports,
    )

    # ---- 1. 候选表：结构完备且带中文显示名 ----
    entries = known_entries()
    ok("候选表非空", len(entries) > 0, f"{len(entries)} 条")
    ok("每条候选都有中文显示名与路径",
       all(e.display and e.path for e in entries),
       f"{[e.display for e in entries[:3]]}")
    ok("分组常量按用户定的顺序递增",
       GROUP_FANGSONG < GROUP_SONG < GROUP_YAHEI < GROUP_HEI < GROUP_OTHER
       < GROUP_SUPPLEMENT,
       f"{GROUP_FANGSONG},{GROUP_SONG},{GROUP_YAHEI},{GROUP_HEI},"
       f"{GROUP_OTHER},{GROUP_SUPPLEMENT}")

    # ---- 2. 可选列表：不含"仅补字"字体，且按优先级排序 ----
    selectable = selectable_entries()
    ok("可选列表不含仅补字字体",
       all(not e.fallback_only for e in selectable),
       f"{[e.display for e in selectable][:3]}")
    groups = [e.group for e in selectable]
    ok("可选列表按优先级分组升序", groups == sorted(groups), f"{groups[:6]}")
    ok("可选列表里没有重复路径",
       len({e.path for e in selectable}) == len(selectable))

    has_fangsong = any(e.group == GROUP_FANGSONG for e in selectable)
    if has_fangsong:
        ok("有仿宋时它排在最前（用户要求：仿宋优先）",
           selectable[0].group == GROUP_FANGSONG, selectable[0].display)

    # ---- 3. 降级链：补字字体垫底、指定生效、无效值回落 ----
    chain = resolve_chain()
    ok("降级链非空（本机至少有一个中文字体）", len(chain) > 0,
       f"{len(chain)} 级")
    if chain:
        supplement = [e for e in chain if e.fallback_only]
        ok("补字字体在链尾（只在缺字时才轮到它）",
           all(e.fallback_only for e in chain[len(chain) - len(supplement):])
           and bool(supplement) == any(e.fallback_only for e in chain),
           f"链尾={[e.display for e in supplement]}")
        ok("链首不是仅补字字体", not chain[0].fallback_only, chain[0].display)

    song = find_entry("宋体")
    if song is not None:
        ok("指定字体后它就是链首", resolve_chain("宋体")[0].display == "宋体",
           resolve_chain("宋体")[0].display)
    auto_head = resolve_chain()[0]
    ok("指定了一个本机没有的字体 → 回落到自动（不整条链失效）",
       resolve_chain("绝无此字体 XYZ")[0].path == auto_head.path,
       auto_head.display)

    # ---- 4. 字形级降级：生僻字不画空白 ----
    fangsong = find_entry("仿宋")
    if fangsong is not None and fangsong.exists:
        coverage_known = supports(fangsong, _COMMON_CHAR)
        ok("仿宋有常用字（本轮降级不能误伤常用字）", coverage_known,
           f"{_COMMON_CHAR} -> {coverage_known}")
        rare_in_fangsong = supports(fangsong, _RARE_CHAR)
        if not rare_in_fangsong:
            picked = pick_font(chain, _RARE_CHAR)
            ok("仿宋缺的生僻字会顺位落到别的字体（不画空白）",
               picked is not None and picked.path != fangsong.path,
               f"{picked.display if picked else None}")
            ok("补到的是真有这个字的字体",
               picked is not None and supports(picked, _RARE_CHAR),
               f"{picked.display if picked else None}")
        # 常用字必须仍留在首选字体上
        ok("常用字仍用首选字体（降级不误伤）",
           pick_font(chain, _COMMON_CHAR).path == chain[0].path,
           pick_font(chain, _COMMON_CHAR).display)

    # ---- 5. PDF 侧：只注册**实际用到**的字体 ----
    from fpdf import FPDF

    from utils.pdf_draw import build_font_chain

    pdf_common = FPDF()
    chain_common = build_font_chain(pdf_common, texts=[_COMMON_CHAR * 4])
    ok("纯常用字只注册一个字体（不白嵌十几个字体）",
       len(chain_common.entries) == 1,
       f"{[e.display for e in chain_common.entries]}")
    ok("主字体名可用", bool(chain_common.primary), chain_common.primary)

    pdf_rare = FPDF()
    chain_rare = build_font_chain(
        pdf_rare, texts=[_COMMON_CHAR + _RARE_CHAR]
    )
    ok("含生僻字时按需多注册一个字体",
       len(chain_rare.entries) >= 2,
       f"{[e.display for e in chain_rare.entries]}")
    ok("逐字取字体：生僻字与常用字不是同一个",
       chain_rare.name_for(_RARE_CHAR) != chain_rare.name_for(_COMMON_CHAR)
       or len(chain_rare.entries) == 1,
       f"常用={chain_rare.name_for(_COMMON_CHAR)} "
       f"生僻={chain_rare.name_for(_RARE_CHAR)}")

    # ---- 6. 参数三层一致：CLI / 桌面 / 模板 ----
    from core.command_spec import PRINT_DEFAULTS

    ok("CLI 默认有 title_font 且默认为自动",
       "title_font" in PRINT_DEFAULTS and PRINT_DEFAULTS["title_font"] is None,
       str(PRINT_DEFAULTS.get("title_font")))
    ok("CLI 默认有 page_number_font 且默认为自动",
       "page_number_font" in PRINT_DEFAULTS
       and PRINT_DEFAULTS["page_number_font"] is None,
       str(PRINT_DEFAULTS.get("page_number_font")))

    from desktop.components.panels.print_params import DEFAULT_PARAMS

    ok("桌面表单默认含两个字体键",
       {"title_font", "page_number_font"} <= set(DEFAULT_PARAMS),
       f"{sorted(DEFAULT_PARAMS)[:4]}…")

    import yaml

    root = ctx.project_root if hasattr(ctx, "project_root") else None
    if root is None:
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
    template = yaml.safe_load(
        open(os.path.join(str(root), "static", "guji.yaml"),
             encoding="utf-8")
    )
    print_block = template.get("print", {})
    ok("模板 print 段显式给出 title_font",
       "title_font" in print_block, f"{sorted(print_block)[:5]}")
    ok("模板 print 段显式给出 page_number_font",
       "page_number_font" in print_block)
    ok("模板里两个字体默认为空（= 自动）",
       print_block.get("title_font") is None
       and print_block.get("page_number_font") is None,
       f"{print_block.get('title_font')} / "
       f"{print_block.get('page_number_font')}")

    # ---- 7. 面板：下拉可选、值可保存、回填不丢 ----
    from desktop.components.panels.print_panel import PrintPanel
    from desktop.services.font_catalog import AUTO_LABEL, AUTO_VALUE, catalog

    panel = PrintPanel()
    args = panel.get_args()
    ok("面板导出 title_font / page_number_font",
       "title_font" in args and "page_number_font" in args, f"{sorted(args)}")
    ok("未选字体时导出的是 None（= 自动）",
       args.get("title_font") is None and args.get("page_number_font") is None,
       f"{args.get('title_font')} / {args.get('page_number_font')}")

    ok("字体下拉首项是「自动」",
       panel.title_font.itemText(0) == AUTO_LABEL, panel.title_font.itemText(0))
    ok("默认是自动项被选中",
       panel.title_font.currentData() in ("", None),
       repr(panel.title_font.currentData()))

    # 选一个真实字体 → 导出值随之改变，且回填后仍是它
    choices = catalog().choices()
    real = [v for _label, v in choices if v][:1]
    if real:
        target = real[0]
        idx = panel.title_font.findData(target)
        panel.title_font.setCurrentIndex(idx)
        ok("选了字体后面板导出该字体",
           panel.get_args()["title_font"] == target,
           f"{panel.get_args()['title_font']}")
        panel._apply_args({"title_font": target, "page_number_font": target})
        ok("回填后下拉仍显示该字体（不被悄悄改成自动）",
           panel.title_font.currentData() == target,
           repr(panel.title_font.currentData()))
    # 配置里记着一个列表中没有的字体（另一台机器）→ 保住它，别改回自动
    panel._apply_args({"title_font": "某台机器上才有的字体"})
    ok("列表里没有的字体也被保住（不悄悄回落自动）",
       panel.title_font.currentData() == "某台机器上才有的字体",
       repr(panel.title_font.currentData()))

    # ---- 8. 目录服务：自动项在前、按显示名去重、扫描只启动一次 ----
    items = catalog().choices()
    ok("候选首项是自动项且值为空串",
       items[0] == (AUTO_LABEL, AUTO_VALUE), f"{items[0]}")
    labels = [label for label, _ in items]
    ok("候选按显示名去重（不会出现两个同名项）",
       len(labels) == len(set(labels)), f"{len(labels)} vs {len(set(labels))}")

    import utils.font_scan as font_scan

    original = font_scan.scan_system_fonts
    font_scan.scan_system_fonts = lambda force=False: ()
    try:
        from PySide6.QtCore import QCoreApplication

        cat = catalog()
        cat.start_scan()
        thread = cat._thread
        if thread is not None:
            thread.wait(5000)
        # ⚠️ 完成回调是**跨线程排队**的信号：while 里 wait() 阻塞的是主线程，
        # 槽要等回到事件循环才派发。不跑一次事件循环，`_thread` 永远清不掉，
        # 断言会假红（看起来像"线程引用没释放"）。
        QCoreApplication.processEvents()
        ok("扫描结束后不持有线程引用", cat._thread is None,
           repr(cat._thread))
        ok("扫描标记为已启动", cat._started)
        cat.start_scan()
        ok("重复调用不会再起一个线程（全局只扫一次）",
           cat._thread is None or cat._thread is thread)
    finally:
        font_scan.scan_system_fonts = original

    # ---- 9. 预览侧：按**文件**取字体，与 PDF 同一个文件 ----
    from utils.page_layout import plan_print_page

    spec_args = {
        "paper_size": "A4", "orientation": "landscape",
        "page_margins": [20, 20, 20, 20],
        "title_printing": True, "title_text": "古籍",
        "title_font_size": 20, "title_color": "0,0,0",
        "title_position": "top", "title_orientation": "vertical",
        "title_font": "黑体",
        "page_number_printing": True, "page_number_start_page": 1,
        "page_number_base": 0, "page_number_font_size": 20,
        "page_number_color": "0,0,0", "page_number_position": "bottom",
        "page_number_orientation": "vertical",
        "page_number_font": "宋体",
    }
    plan = plan_print_page((100, 200), spec_args, 0, 1)
    ok("标题 spec 带上了 title_font",
       plan.title is not None and plan.title.font == "黑体",
       f"{plan.title.font if plan.title else None}")
    ok("页码 spec 带上了 page_number_font",
       plan.page_number is not None and plan.page_number.font == "宋体",
       f"{plan.page_number.font if plan.page_number else None}")
    ok("两个字体互不影响（标题与页码各一个）",
       plan.title.font != plan.page_number.font)

    from desktop.workers.preview_worker import _pick_content_font

    hei = find_entry("黑体")
    if hei is not None and hei.exists:
        family = _pick_content_font(18, "黑体").family()
        ok("预览按**字体文件**取字（不是族名查表）",
           bool(family) and family not in ("", "Sans Serif"), family)
