# -*- coding: utf-8 -*-
"""print 阶段自测：第四步表单、真实生成 PDF、页数/print.json/取图规格。

2026-10-01 起第四步只排版「提交本次任务」的成品图（不再拿去底图按当前
area/border 现算），所以这里断言的是「取图 = 提交产物」。依赖 rembg 模块
先跑过（DEPENDS）：要有提交产物。
"""

NAME = "print"
DEPENDS: list[str] = ["rembg"]
TITLE = "print"


def run(ctx) -> None:
    import json
    import time
    from pathlib import Path

    import pymupdf
    from PySide6.QtTest import QTest

    from tests.selftests._context import ok, wait_worker

    app, d, repo = ctx.app, ctx.d, ctx.repo
    tid = ctx.tid
    img = ctx.inserted_img

    d.set_task(tid)
    d._select_stage(3)
    # border=10 是本模块自己的前置条件，必须自己设好：下面的「border→边距
    # 级联」用例要它非 0。set_task 会让 rembg 面板按历史记录回填，历史里没有
    # border 就会被清空（拆分前 rembg 段设置的 "10" 会残留，掩盖这条依赖；
    # 模块化后不能再靠上游残留）。
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
    # 第三步 border 已在上面设为 "10"（非 0）→ 第四步通用边距默认级联为 0，
    # 避免「图片内留白 + 页面边距」双重留白（feature: border→边距级联）
    _pargs = panel.get_args()
    ok("print 表单参数收集正确",
       _pargs["paper_size"] == "A4"
       and _pargs["orientation"] == "landscape"
       and _pargs["title_printing"] is True
       and _pargs["title_text"] == "测试古籍"
       and _pargs["pdf_name"] == "print.pdf"
       and _pargs["page_margins"] == [0, 0, 0, 0]
       and "input" not in _pargs and "output" not in _pargs,
       str(_pargs))

    # 显式验证 border→边距级联（GUI 接线，而非只靠纯函数守卫）：
    # 清掉 border（视为 0）→ 默认回落 20；再设回 10 → 级联为 0
    # ⚠️ 级联走第三步联动的 200ms 防抖，qWait 冲过去再断言
    _rembg_panel.border.setText("")
    QTest.qWait(260)
    ok("第三步 border 清掉 → 第四步默认边距回落 20",
       panel.get_args()["page_margins"] == [20, 20, 20, 20],
       str(panel.get_args()["page_margins"]))
    _rembg_panel.border.setText("10")
    QTest.qWait(260)
    ok("第三步 border=10 → 第四步默认边距级联为 0",
       panel.get_args()["page_margins"] == [0, 0, 0, 0],
       str(panel.get_args()["page_margins"]))
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
    # worker 实际消费的运行配置（run-<run_id>.json）：取图必须是第三步
    # 「提交本次任务」的成品图，且不带任何区域合成规格（2026-10-01 起第四步
    # 不再拿去底图现算；第三步那边改 area/border 必须先重新提交）。
    # ⚠️ 不查 runs.json 历史：2026-09-26 起入史前剥掉大块运行时派生字段
    # （_effects/files/page_rects）——2400 页的书单条历史 0.5MB，而历史只用于
    # 面板回填，留着它们是纯写放大。
    _run_id = repo.list_stage_runs(tid, "print")[0]["run_id"]
    _run_cfg = json.loads(
        (repo.runs_config_dir(tid) / f"run-{_run_id}.json").read_text(encoding="utf-8")
    )
    _saved_fx = _run_cfg["args"].get("_effects") or []
    ok("print 运行配置的取图 = 提交产物（整图透传，无区域合成规格）",
       len(_saved_fx) == 6
       and all(Path(s["file"]).parent == _rembg_final for s in _saved_fx)
       and all(s.get("effect") is None for s in _saved_fx),
       f"total={len(_saved_fx)} "
       f"effects={[s.get('effect') for s in _saved_fx][:2]}")
    # 历史里则不应再背这份大块派生数据（写放大治理）
    _hist_params = repo.list_stage_runs(tid, "print")[0]["parameters"]
    ok("历史参数已剥离运行时派生字段（_effects/files/page_rects）",
       not ({"_effects", "files", "page_rects"} & set(_hist_params))
       and _hist_params.get("pdf_name") == "print.pdf",
       str(sorted(_hist_params)))
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
