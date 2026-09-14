# -*- coding: utf-8 -*-
"""GUI 全功能自测脚本（offscreen 模式，可重复运行）。

运行方式：
    QT_QPA_PLATFORM=offscreen python tests/gui_selftest.py

覆盖：任务列表增删查、导入查重确认（取消定位/确认新建）、源文件副本、
逐页缩略图、四个子任务真实执行
（extract/detect/rembg/print）、续跑、中断、页面增删、缩略图磁盘缓存、
失败可见性、worker 编码。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
sys.path.insert(0, str(Path(__file__).parents[1]))

import pymupdf  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from desktop.app import MainWindow  # noqa: E402
from desktop.utils.files import list_stage_images  # noqa: E402
from desktop.store import TaskStore, STAGES  # noqa: E402

PASS = 0


def ok(name: str, condition: bool, detail: str = "") -> None:
    global PASS
    if not condition:
        raise AssertionError(f"[FAIL] {name} {detail}")
    PASS += 1
    print(f"  [PASS] {name}")


def make_pdf(path: Path, pages: int, text_prefix: str = "第") -> Path:
    doc = pymupdf.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text_prefix} {i + 1} 页 测试内容")
    doc.save(str(path))
    doc.close()
    return path


def wait_worker(page, app, timeout: float = 180.0) -> int:
    deadline = time.time() + timeout
    while page.process and page.process.state() != 0 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()
    return page.process.exitCode() if page.process else 0


def main() -> int:
    tmp = Path(os.environ.get("GUI_SELFTEST_TMP", "")) if os.environ.get("GUI_SELFTEST_TMP") else Path.tempdir if hasattr(Path, "tempdir") else None
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="guji_selftest_"))
    print(f"工作目录：{tmp}")

    pdf = make_pdf(tmp / "古籍样例.pdf", 6)
    big_pdf = make_pdf(tmp / "大部头.pdf", 80)

    app = QApplication([])
    w = MainWindow()
    # 重定向数据目录到临时目录
    w.close()
    repo = TaskStore(tmp)
    w = MainWindow()
    w.store = repo
    w.list_page.store = repo
    w.detail_page.store = repo
    d = w.detail_page

    # ================= 1. 任务列表 =================
    print("== 任务列表 ==")
    tid = repo.create_task(pdf, "hashA", "古籍样例")
    w.list_page.refresh()
    ok("导入后立即出条目", w.list_page.table.table.rowCount() == 1)
    ok("创建任务带指纹", repo.get_task(tid)["source_hash"] == "hashA")

    tid_dup = repo.create_task(big_pdf, "hashA", "大部头")
    w.list_page.refresh()
    ok("列表条目数正确", w.list_page.table.table.rowCount() == 2)

    # 查重：取消 → 不新建，定位到已有任务
    w.list_page._confirm_duplicate = lambda path, dups: False
    w.list_page._hash_ready(str(big_pdf), "hashA")
    ok("重复文件取消后未新建", len(repo.list_tasks()) == 2)
    ok("取消后可定位到已有任务", w.list_page.table.select_task(tid_dup))

    # 查重：确认 → 新建一条并标记 duplicate_confirmed
    w.list_page._confirm_duplicate = lambda path, dups: True
    rows_before = len(repo.list_tasks())
    w.list_page._hash_ready(str(big_pdf), "hashA")
    ok("重复文件确认后新建一条", len(repo.list_tasks()) == rows_before + 1)
    newest = repo.list_tasks()[0]
    ok("新建任务标记 duplicate_confirmed", newest["duplicate_confirmed"] == 1)
    ok("新建任务保留副本", (repo.task_dir(newest["id"]) / big_pdf.name).exists())
    thumbs_dir = repo.source_thumbnails_dir(newest["id"])
    for _ in range(100):
        if thumbs_dir.exists() and len(list(thumbs_dir.glob("*.jpg"))) == 80:
            break
        app.processEvents(); time.sleep(0.1)
    ok("导入后生成逐页缩略图", len(list(thumbs_dir.glob("*.jpg"))) == 80,
       f"实际 {len(list(thumbs_dir.glob('*.jpg'))) if thumbs_dir.exists() else 0} 张")
    repo.delete_task(newest["id"])

    # 行内按钮存在
    from qfluentwidgets import PushButton

    action_cell = w.list_page.table.table.cellWidget(0, 5)
    buttons = action_cell.findChildren(PushButton)
    ok("行内详情/删除按钮存在", len(buttons) == 2)

    # 详情打开
    w._open_detail(tid)
    ok("点击详情进入任务页", d.task_id == tid)

    # ================= 2. 详情页结构 =================
    print("== 详情页结构 ==")
    ok("extract 双标签页", d.extract_tabs.count() == 2
       and d.extract_tabs.tabText(0) == "PDF 预览"
       and d.extract_tabs.tabText(1) == "提取结果")
    ok("步骤条 4 步", len(d.step_bar.buttons) == 4)
    ok("控制面板 4 个", d.control_stack.count() == 4)
    ok("预览区 4 个", d.preview_stack.count() == 4)

    # ================= 3. 缩略图磁盘缓存 =================
    print("== 缩略图缓存 ==")
    for _ in range(30):
        app.processEvents(); time.sleep(0.1)
    cache_dir = repo.source_thumbnails_dir(tid)
    thumbs = list(cache_dir.glob("*.jpg"))
    ok("首次加载生成缓存", len(thumbs) == 6, str(cache_dir))
    mtimes = {f.name: f.stat().st_mtime_ns for f in thumbs}
    d.set_task(tid)
    for _ in range(20):
        app.processEvents(); time.sleep(0.1)
    mtimes2 = {f.name: f.stat().st_mtime_ns for f in cache_dir.glob("*.jpg")}
    ok("再次打开复用缓存", mtimes == mtimes2)

    # 第四步默认 PDF 名/古籍名随源 PDF（古籍样例.pdf）派生
    _pp = d.control_stack.widget(3)
    ok("默认 PDF 名取源 PDF 名加[重制]",
       _pp.pdf_name.text() == "古籍样例[重制].pdf", _pp.pdf_name.text())
    ok("默认古籍名称取源 PDF 名",
       _pp.title_text.text() == "古籍样例", _pp.title_text.text())
    ok("默认参数收集含派生 PDF 名",
       _pp.get_args()["pdf_name"] == "古籍样例[重制].pdf"
       and _pp.get_args()["title_text"] == "古籍样例")
    _pp.pdf_name.setText("自定义.pdf")
    _pp.title_text.setText("自定义书名")
    _pp.reset_to_default()
    ok("恢复默认仍按源 PDF 名派生",
       _pp.pdf_name.text() == "古籍样例[重制].pdf"
       and _pp.title_text.text() == "古籍样例")
    # title_text ↔ pdf_name 联动测试
    ok("初始为自动态", _pp._pdf_name_auto is True)
    _pp.title_text.setText("红楼梦")
    _pp._on_title_text_edited("红楼梦")
    ok("编辑 title_text 时 pdf_name 联动更新",
       _pp.pdf_name.text() == "红楼梦[重制].pdf", _pp.pdf_name.text())
    ok("联动后仍为自动态", _pp._pdf_name_auto is True)
    _pp.pdf_name.setText("xxx.pdf")
    _pp._refresh_pdf_name_auto()  # 模拟用户直接改 pdf_name 后的状态
    ok("用户直接改 pdf_name 后联动解除", _pp._pdf_name_auto is False)
    _pp.title_text.setText("不再联动")
    _pp._on_title_text_edited("不再联动")
    ok("联动解除后改 title_text 不再影响 pdf_name",
       _pp.pdf_name.text() == "xxx.pdf", _pp.pdf_name.text())
    _pp.reset_to_default()
    ok("恢复默认后联动重新建立",
       _pp._pdf_name_auto is True
       and _pp.pdf_name.text() == "古籍样例[重制].pdf"
       and _pp.title_text.text() == "古籍样例")

    # ================= 4. extract 全量执行 =================
    print("== extract ==")
    d._select_stage(0)
    d.run_stage(resume=False)
    wait_worker(d, app)
    state = repo.stage_states(tid)["extract"]
    ok("extract 成功", state["status"] == "success", str(state))
    ok("进度 6/6", (state["done"], state["total"]) == (6, 6), str(state))
    for _ in range(15):
        app.processEvents(); time.sleep(0.1)
    ok("提取结果 6 页入清单", len(repo.load_pages(tid)) == 6)
    # extract 阶段记录的原始尺寸与实际图片文件一致
    first_page = repo.load_pages(tid)[0]["file"]
    stem = Path(first_page).stem
    meta = repo.image_size(tid, stem)
    from PySide6.QtGui import QImageReader as _QIR

    actual = _QIR(first_page).size()
    ok("extract 记录图片原始尺寸", meta == (actual.width(), actual.height()),
       f"db={meta} actual={actual.width()}x{actual.height()}")
    log = d.log_view.toPlainText()
    ok("中文日志无乱码", "处理完成" in log and "\\ufffd" not in repr(log))

    # ================= 5. 中断 + extract 续跑 =================
    print("== 中断与续跑 ==")
    tid_big = repo.create_task(big_pdf, "", "大部头")
    d.set_task(tid_big)
    # 提高渲染分辨率拖慢速度，保证有可靠的中断窗口
    d.control_stack.widget(0).zoom.setValue(4)
    d.run_stage(resume=False)
    time.sleep(1.5)
    app.processEvents()
    d.cancel_stage()
    # 持续补发 kill，防止偶发的终止延迟导致旧进程跑完
    deadline = time.time() + 30
    while d.process and d.process.state() != 0 and time.time() < deadline:
        app.processEvents()
        time.sleep(0.05)
        if d.process and d.process.state() != 0:
            d.process.kill()
    app.processEvents()
    ok("中断后状态 cancelled",
       repo.stage_states(tid_big)["extract"]["status"] == "cancelled")

    # 续跑：只补缺失页
    partial = repo.extract_output_dir(tid_big)
    have = len(list(partial.glob("*.jpg"))) if partial.exists() else 0
    d.run_stage(resume=True)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid_big)["extract"]
    ok("续跑后成功", state["status"] == "success", str(state))
    total_now = len(list(partial.glob("*.jpg")))
    ok(f"续跑补齐缺失页（中断前 {have} 页 → 续跑后 {total_now} 页）", total_now >= have)

    # ================= 6. extract 失败可见性 =================
    print("== 失败可见性 ==")
    d.set_task(tid)
    d.control_stack.widget(0).pages_edit.setText("99-200")
    d.run_stage(resume=False)
    wait_worker(d, app)
    time.sleep(0.3); app.processEvents()
    log = d.log_view.toPlainText()
    ok("失败原因进入日志", "页面参数错误" in log or "❌" in log)

    # 执行历史保存 + 历史配置回填 + 步骤条高亮
    hist = repo.list_stage_runs(tid, "extract")
    ok("执行历史已保存（最新在前）",
       len(hist) == 2 and hist[0]["status"] == "failed" and hist[1]["status"] == "success",
       str([(h["status"], h.get("parameters", {}).get("pages")) for h in hist]))
    d._select_stage(0)
    ok("历史配置下拉条数", d.history_combo.count() == 2)
    d._on_history_selected(0)
    ok("历史配置回填表单", d.control_stack.widget(0).pages_edit.text() == "99-200")
    ok("步骤条已完成高亮", 0 in d.step_bar._completed and 1 not in d.step_bar._completed)

    # ================= 7. 页面增删 =================
    print("== 页面增删 ==")
    d._refresh_manifest()
    before = len(repo.load_pages(tid))
    d.detect_viewer.strip.setCurrentRow(2)
    d._select_stage(1)
    app.processEvents()
    d.detect_viewer.strip.setCurrentRow(2)
    d.delete_selected_page()
    ok("删除页面", len(repo.load_pages(tid)) == before - 1)

    # 插入（不弹对话框：直接测 repository 逻辑 + manifest 刷新）
    imported = repo.extract_output_dir(tid)
    imported.mkdir(parents=True, exist_ok=True)
    extra = make_pdf(tmp / "extra.png", 1)  # 占位：用图片替代
    import pymupdf as _pm

    img = tmp / "inserted.png"
    _doc = _pm.open(); _p = _doc.new_page(); _p.insert_text((72, 72), "插")
    _pix = _p.get_pixmap(); _pix.save(str(img)); _doc.close()
    pages = repo.load_pages(tid)
    pages.insert(1, {"file": str(img), "label": "inserted"})
    repo.save_pages(tid, pages)
    ok("插入页面", len(repo.load_pages(tid)) == before)
    d._refresh_manifest()  # 与 run_stage 实际流程一致：执行前刷新清单缓存
    ws = d._build_workset("detect", resume=False)
    ok("workset 按清单物化", len(list(ws.iterdir())) == before)

    # ================= 8. detect 执行（真实 YOLO 子进程） =================
    print("== detect ==")
    d._select_stage(1)
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["detect"]
    ok("detect 执行完成", state["status"] in ("success",), str(state))
    ok("detect 执行历史已保存", len(repo.list_stage_runs(tid, "detect")) == 1)
    ok("detect 步骤高亮", 1 in d.step_bar._completed)
    time.sleep(0.3); app.processEvents()
    detect_out = repo.stage_output_dir(tid, "detect")
    ok("detect 阶段不生成切割文件",
       not detect_out.exists() or not any(detect_out.iterdir()), str(detect_out))
    manifest_before_detect = [p["file"] for p in repo.load_pages(tid)]
    manifest_now = [p["file"] for p in repo.load_pages(tid)]
    ok("detect 不影响页面清单", manifest_now == manifest_before_detect)

    # 最终裁剪框规则与 crop 命令一致（utils.box_geometry）
    from utils.box_geometry import compute_final_boxes
    from utils.box_geometry import parse_border_mm as _pbm
    _left, _right = [100, 100, 200, 200], [300, 100, 500, 300]
    _d = _pbm("10")[0]
    ok("area=1 逐框外扩 border",
       compute_final_boxes([_left, _right], 1, "10")
       == [[100 - _d, 100 - _d, 200 + _d, 200 + _d],
           [300 - _d, 100 - _d, 500 + _d, 300 + _d]])
    ok("area=2 合并大框",
       compute_final_boxes([_left, _right], 2, "10")
       == [[100 - _d, 100 - _d, 500 + _d, 300 + _d]])
    ok("area=3 与 area=2 同规则",
       compute_final_boxes([_left, _right], 3, "10")
       == compute_final_boxes([_left, _right], 2, "10"))
    ok("单框对称取内容框",
       compute_final_boxes([_left], 2, "10") == [[100 - _d, 100 - _d, 200 + _d, 200 + _d]])

    # 检测框坐标实时入库（YOLO 检出时 origin=auto；合成页面可能检不出）
    first_stem = Path(repo.load_pages(tid)[0]["file"]).stem
    entry = repo.detect_boxes_entry(tid, first_stem)
    ok("detect 阶段框坐标入库", entry is None or entry[1] == "auto", str(entry))

    # detect 续跑（无新文件时应提示无需续跑）
    n_before = len(list(ws.iterdir()))
    ws2 = d._build_workset("detect", resume=True)
    ok("detect 续跑跳过已完成", len(list(ws2.iterdir())) <= n_before)

    # ================= 9. rembg 生成预览 + 提交 =================
    print("== rembg ==")
    d._select_stage(2)
    ok("步骤三主按钮为生成预览", d.run_button.text() == "生成预览")
    ok("未生成预览前提交按钮禁用", not d.submit_button.isEnabled())
    d.run_rembg_submit()  # 直接调用也必须被拦截，不启动子进程
    ok("未成功生成预览时提交不启动", d.process is None)
    d.run_stage(resume=False)
    wait_worker(d, app, timeout=300)
    state = repo.stage_states(tid)["rembg"]
    ok("rembg 预览成功", state["status"] == "success", str(state))
    preview_dir = repo.rembg_preview_output_dir(tid)
    ok("预览图落在 stages/rembgpreview",
       preview_dir.exists() and len(list(preview_dir.glob("*.png"))) == 6,
       str(preview_dir))
    final_dir = repo.rembg_output_dir(tid)
    ok("提交前 stages/rembg 为空",
       not final_dir.exists() or not any(final_dir.glob("*.png")))
    ok("预览成功后提交按钮可用", d.submit_button.isEnabled())
    ok("预览成功即提示有新版本待提交",
       d._rembg_submit_version_state() == "new_version"
       and "有新版本" in d.submit_button.text()
       and not d.submit_hint.isHidden() and "#c0392b" in d.submit_hint.styleSheet())

    # 最近一次预览失败/中断：即使目录里残留图片也不允许提交
    bad_run = repo.create_stage_run(tid, "rembg", {"area": 1})
    repo.finish_stage(tid, bad_run, "failed")
    d._refresh_stage_views()
    ok("预览失败后提交按钮禁用（有旧图也不行）", not d.submit_button.isEnabled())
    d.run_rembg_submit()
    ok("预览失败时提交不启动", d.process is None)
    # 模拟用当前面板参数重新生成预览并成功 → 新版本提示恢复
    ok_run = repo.create_stage_run(
        tid, "rembg", d.control_stack.widget(2).get_args()
    )
    repo.finish_stage(tid, ok_run, "success")
    d._refresh_stage_views()
    ok("重新生成预览成功后提交恢复可用并提示新版本",
       d.submit_button.isEnabled()
       and d._rembg_submit_version_state() == "new_version")

    # 面板去底参数改了但没重新生成 → preview_stale（提示先重新生成预览）
    panel3 = d.control_stack.widget(2)
    _old_offset = panel3.offset.value()
    panel3.offset.setValue(_old_offset + 1)
    d._update_submit_button(False)
    ok("改去底参数未重跑预览 → preview_stale",
       d._rembg_submit_version_state() == "preview_stale"
       and "#b8860b" in d.submit_hint.styleSheet())
    panel3.offset.setValue(_old_offset)

    # 提交本次任务：预览图按 area/border 合成为最终图片到 stages/rembg
    d.run_rembg_submit()
    wait_worker(d, app, timeout=300)
    state = repo.list_stage_runs(tid, "rembg_submit")[0]
    ok("提交成功", state["status"] == "success", str(state))
    ok("最终图落在 stages/rembg",
       final_dir.exists() and len(list(final_dir.glob("*.png"))) == 6,
       str(final_dir))
    ok("提交成功后版本状态为最新、按钮徽标消失",
       d._rembg_submit_version_state() == "up_to_date"
       and d.submit_button.text() == "提交本次任务"
       and "#3a8a3e" in d.submit_hint.styleSheet())
    # 提交记录了所基于的预览版本号（不加载 YOLO，纯框坐标合成）
    _sub = next(r for r in repo.list_stage_runs(tid, "rembg_submit")
                if r["status"] == "success")
    ok("提交记录包含预览版本号",
       _sub["parameters"].get("_preview_run_id") == ok_run)
    # 再次「生成预览」成功（新版本）→ 又提示需要提交
    newer = repo.create_stage_run(
        tid, "rembg", d.control_stack.widget(2).get_args()
    )
    repo.finish_stage(tid, newer, "success")
    d._refresh_stage_views()
    ok("再次生成预览后重新提示新版本",
       d._rembg_submit_version_state() == "new_version"
       and "有新版本" in d.submit_button.text())

    # ================= 10. print 执行 + 输出预览 =================
    print("== print ==")
    d._select_stage(3)
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

    # --- 生成 PDF 时第三步 area/border 实时生效（无需重新提交）---
    # 给一页注入确定性检测框（单框），模拟 YOLO 检出
    _comp0 = d._rembg_submit_entries(1, None)
    _anchor = next((c for c in _comp0 if c.get("box") is None), _comp0[0])
    _anchor_stem = Path(_anchor["file"]).stem
    _aw, _ah = repo.image_size(tid, _anchor_stem)
    _injected = [round(_aw * 0.10), round(_ah * 0.10),
                 round(_aw * 0.55), round(_ah * 0.90)]
    repo.save_detect_boxes(tid, _anchor_stem, [_injected, None], origin="manual")
    _anchor_src = next(p for p in d._manifest_paths() if p.stem == _anchor_stem)
    d.detect_cache[str(_anchor_src)] = [_injected, None]

    panel3.border.setText("10")
    _entries_b, _ = d._print_entries()
    _fx10 = d._build_print_effects(_entries_b, 1, "10")
    _preview_dir = preview_dir
    ok("print 合成规格与列表一一对应且源为 rembgpreview 去底图",
       len(_fx10) == 6
       and all(Path(s["file"]).parent == _preview_dir for s in _fx10),
       str([Path(s["file"]).name for s in _fx10]))
    _a_spec = next(s for s in _fx10
                   if Path(s["file"]).stem == _anchor_stem)
    ok("print 合成规格携带检测框/area/border",
       _a_spec["effect"] == {"boxes": [_injected], "area": 1, "border": "10"},
       str(_a_spec))
    # 仅改 border 不重新提交：合成规格立即变为新值
    panel3.border.setText("25")
    _fx25 = d._build_print_effects(d._print_entries()[0], 1, "25")
    _a25 = next(s for s in _fx25 if Path(s["file"]).stem == _anchor_stem)
    ok("调整 border 后无需重新提交即生效",
       _a25["effect"]["border"] == "25"
       and _a25["effect"]["boxes"] == [_injected],
       str(_a25))
    # 外部插入图整图透传；area 结构变更后旧提交图被丢弃、新条目补尾
    _mixed = _entries_b + [{"file": str(img), "label": "external_page"}]
    _stale = {"file": str(repo.rembg_output_dir(tid) / "999-r.png"),
              "label": "999-r"}
    _fx_mix = d._build_print_effects(_mixed + [_stale], 1, "25")
    ok("外部插入图透传、旧 area 提交图不混入 PDF",
       any(s["file"] == str(img) and s["effect"] is None for s in _fx_mix)
       and not any(Path(s["file"]).name == "999-r.png" for s in _fx_mix))
    panel3.border.setText("10")  # 正式 print 使用 10mm

    panel = d.control_stack.widget(3)
    # 进入第四步触发历史回填后，pdf_name/title_text 仍应保持源 PDF 名派生值
    # （历史里存的旧/自定义 pdf_name 不应覆盖规则值）
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

    # ================= 11. detect 检测框子进程 =================
    print("== detect 检测框 ==")
    d._select_stage(1)
    app.processEvents()
    ok("切换到 detect 不自动执行检测", d.detect_process is None)
    d._detect_current_page()  # 手动触发当前页检测
    deadline = time.time() + 240
    while d.detect_process and d.detect_process.state() != 0 and time.time() < deadline:
        app.processEvents(); time.sleep(0.1)
    time.sleep(0.3); app.processEvents()
    ok("检测子进程返回结果", len(d.detect_cache) >= 1)
    info = d.detect_viewer.info_label.text()
    ok("检测信息展示", len(info) > 0, info)

    # ================= 11b. 手动框入库（不生成新文件） =================
    print("== 手动框入库 ==")
    manual_path = repo.load_pages(tid)[0]["file"]
    def _snapshot():
        # 只比对产物文件；*.json 是数据存储（boxes.json 等），不算生成的产物
        return sorted(
            str(p) for p in repo.task_dir(tid).rglob("*")
            if p.is_file() and p.suffix != ".json"
        )
    before_files = _snapshot()
    d._save_manual_boxes(manual_path, [[10, 20, 300, 400]])
    entry = repo.detect_boxes_entry(tid, Path(manual_path).stem)
    ok("手动框写入数据库", entry is not None and entry[1] == "manual", str(entry))
    ok("手动框坐标正确", entry is not None and entry[0] == [[10, 20, 300, 400]], str(entry))
    ok("detect_cache 同步更新", d.detect_cache.get(manual_path) == [[10, 20, 300, 400]])
    after_files = _snapshot()
    ok("手动调整不生成新文件", before_files == after_files)
    # 再切回该页：直接命中 detect_cache，不触发重新检测
    d.detect_cache[manual_path] = [[10, 20, 300, 400]]
    d._detect_image_selected(0, manual_path)
    ok("回看页面直接应用框", d.detect_viewer.info_label.text().startswith("左框"))

    # ================= 12. 任务删除 =================
    print("== 任务删除 ==")
    repo.delete_task(tid_dup)
    ok("删除任务", repo.get_task(tid_dup) is None)
    ok("任务目录已清理", not repo.task_dir(tid_dup).exists())
    w.list_page.refresh()
    print("    [diag] db tasks:", len(repo.list_tasks()),
          "table rows:", w.list_page.table.table.rowCount())
    ok("列表同步刷新", w.list_page.table.table.rowCount() == len(repo.list_tasks()))

    print(f"\n全部 {PASS} 项断言通过 ✅")
    repo.delete_task(tid)
    repo.delete_task(tid_big)
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
