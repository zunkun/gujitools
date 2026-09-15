# -*- coding: utf-8 -*-
"""print 阶段自测：第四步表单、真实生成 PDF、页数/print.json/实时合成规格。

依赖 rembg 模块注入的 ``ctx.injected_boxes`` 与 ``ctx.preview_dir``。
"""

NAME = "print"
DEPENDS: list[str] = ["rembg"]
TITLE = "print"


def run(ctx) -> None:
    import time
    from pathlib import Path

    import pymupdf

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    img = ctx.inserted_img
    _injected = ctx.injected_boxes
    preview_dir = ctx.preview_dir

    d.set_task(tid)
    d._select_stage(3)
    # 本模块断言 print 运行配置携带 border=10 的合成规格——这是它自己的
    # 前置条件，必须自己设好：set_task 会让 rembg 面板按历史记录回填，
    # 历史里没有 border 就会被清空（拆分前 rembg 段设置的 "10" 会残留，
    # 掩盖这条依赖；模块化后不能再靠上游残留）。
    _rembg_panel = d.control_stack.widget(2)
    _rembg_panel.border.setText("10")
    ok("print 列表直接使用 stages/rembg 最终图",
       d.print_preview.count() == 6, str(d.print_preview.count()))
    _entries, _pdoc = d._print_entries()
    _rembg_final = repo.rembg_output_dir(tid)
    ok("列表条目全部来自 stages/rembg 且无缩略图/区域字段",
       all(Path(e["file"]).parent == _rembg_final
           and "thumb" not in e and "effect" not in e
           and "box" not in e for e in _entries),
       str([(Path(e["file"]).parent.name, sorted(e.keys())) for e in _entries]))
    # 删除后重新派生不复活（rembg 集合快照不变）
    d.print_preview.list.item(2).setSelected(True)
    d.print_preview.remove_selected()
    for _ in range(10):
        app.processEvents(); time.sleep(0.05)
    _entries2, _ = d._print_entries()
    ok("删除的图片重新进入第四步不复活", len(_entries2) == 5, str(len(_entries2)))
    # 恢复初始列表再往下走正式用例
    d.store.save_print_doc(tid, {"rembg_snapshot": [], "pages": []})
    d._refresh_preview(3)
    ok("列表恢复 6 张", d.print_preview.count() == 6,
       str(d.print_preview.count()))

    # 进入第四步触发历史回填后，pdf_name/title_text 仍应保持源 PDF 名派生值
    # （历史里存的旧/自定义 pdf_name 不应覆盖规则值）
    panel = d.control_stack.widget(3)
    ok("历史回填不覆盖 pdf_name 派生值",
       panel.pdf_name.text() == "古籍样例[重制].pdf", panel.pdf_name.text())
    ok("历史回填不覆盖 title_text 派生值",
       panel.title_text.text() == "古籍样例", panel.title_text.text())
    # UI 表单设置 print 参数（不再编辑 YAML）
    panel.paper_size.setCurrentText("A4")
    panel.orientation.setCurrentIndex(panel.orientation.findData("landscape"))
    # 中文显示 / 英文参数值
    ok("方向下拉中文显示英文值",
       panel.orientation.currentText() == "横版"
       and panel.orientation.currentData() == "landscape")
    panel.title_printing.setChecked(True)
    panel.title_text.setText("测试古籍")
    panel.pdf_name.setText("print.pdf")
    _pargs = panel.get_args()
    ok("print 表单参数收集正确",
       _pargs["paper_size"] == "A4"
       and _pargs["orientation"] == "landscape"
       and _pargs["title_printing"] is True
       and _pargs["title_text"] == "测试古籍"
       and _pargs["pdf_name"] == "print.pdf"
       and _pargs["page_margins"] == [20, 20, 20, 20]
       and "input" not in _pargs and "output" not in _pargs,
       str(_pargs))
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["print"]
    ok("print 成功", state["status"] == "success", str(state))
    output_pdf = repo.print_output_pdf(tid)
    ok("输出 PDF 存在", output_pdf.exists())
    for _ in range(15):
        app.processEvents(); time.sleep(0.1)
    doc = pymupdf.open(str(output_pdf))
    ok("输出 PDF 页数与列表一致", doc.page_count == 6, str(doc.page_count))
    doc.close()
    ok("print.json 已保存", len(repo.load_print_pages(tid)) == 6)
    # 运行配置中的 _effects 必须携带第三步当前 border（worker 据此实时合成）
    _saved_fx = repo.list_stage_runs(tid, "print")[0]["parameters"].get("_effects") or []
    _saved_boxed = [s for s in _saved_fx if s.get("effect")]
    ok("print 运行配置携带实时合成规格（源 rembgpreview，border=10）",
       len(_saved_fx) == 6
       and all(Path(s["file"]).parent == preview_dir for s in _saved_fx)
       and len(_saved_boxed) >= 1
       and all(s["effect"]["border"] == "10" for s in _saved_boxed)
       and any(s["effect"]["boxes"] == [_injected] for s in _saved_boxed),
       f"total={len(_saved_fx)} boxed={len(_saved_boxed)}")
    # PDF 生成成功后下载按钮可用，且路径指向实际 PDF
    _pdf = d._latest_print_pdf_path()
    ok("生成 PDF 后下载按钮可用",
       d.print_preview.download_button.isEnabled()
       and _pdf is not None and _pdf.exists()
       and d.print_preview._pdf_path == _pdf,
       str(_pdf))

    # 删除一条 → 列表与 print.json 同步，再重新生成
    d.print_preview.list.item(2).setSelected(True)
    d.print_preview.remove_selected()
    for _ in range(10):
        app.processEvents(); time.sleep(0.05)
    ok("删除条目后列表同步",
       d.print_preview.count() == 5 and len(repo.load_print_pages(tid)) == 5,
       f"count={d.print_preview.count()} json={len(repo.load_print_pages(tid))}")
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    doc = pymupdf.open(str(repo.print_output_pdf(tid)))
    ok("删除后重新生成 PDF 页数一致", doc.page_count == 5, str(doc.page_count))
    doc.close()
