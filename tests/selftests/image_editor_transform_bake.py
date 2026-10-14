# -*- coding: utf-8 -*-
"""图片编辑弹窗·变换的完成收尾、透明底与内容四角 sidecar。

断言线（2026-10-10 一整天的用户报障群，全是"变换不能落地到实体图片"
及其衍生）：

1. **「完成」直接收尾**：挂起态点「完成」，``_finish`` 里的
   ``_commit_transform`` 必须真烘焙（不带 ``force`` 会被"挂起跳过"分支
   原样退回，结果图还是原图——用户报的正是它）；
2. **透明源图**：去底色产物整幅旋转，画布预览空处透明、烘焙也必须透明
   （两处硬编码填白会让存盘变白底）；空处填色统一为 ``_empty_fill``；
3. **旋转→保存→再旋转不再越滚越大**：外框按**非透明像素**的真实外框收，
   二次旋转回到内容本身的 90° 外框；
4. **内容四角节点 sidecar**：p1..p4 旋转后变成 p11..p41、节点数据随图片
   一起保存；二次编辑读回来，「统一变换」的可编辑区域 = 内容四边形本身。
   ⚠️ 回归必须打**色块标记**断言"内容原位"——纯白图查不出"反变换位移"
   （旧回归只查尺寸，矩阵顺序错了照样绿，"PA1 顶部被削一段"就这样漏网）；
   烘焙输入恒 = upright，反变换矩阵 = ``shift * inverse``；
5. **真裁剪 ⇒ 节点整组作废**（边缘变了不恢复）；
6. **首次会话延续**：没有 sidecar 的第一次编辑里转了 30°、切走再切回，
   节点链已在内存里建起来 ⇒ 恢复闸门必须重新武装（带挂起变换的烘焙分支
   不 rearm，切回后框会退成整幅，用户截图报障）；
7. **延迟恢复 + 拖动守卫**：等待恢复像素时有模态进度框（``processEvents``），
   用户可能已在等待中松开 ⇒ 必须守卫，否则"拖动"一直挂着、鼠标一动内容
   就跟着跑。
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

NAME = "image_editor_transform_bake"
DEPENDS: list[str] = []
TITLE = "图片编辑弹窗·变换完成收尾/透明底/内容四角 sidecar"


def run(ctx) -> None:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor

    from tests.selftests._context import ok
    from tests.selftests._editor_kit import canvas_img, make_image

    from desktop.components.viewers.image_editor import (
        ImageEditorDialog, compose_transform, rotate_about,
    )

    # 与 ``image_editor_transform.py`` 同款底图（黑块 x∈[150,170)×y∈[50,70)），
    # 那边是 dialog4 用的；这边若干用例要"从原始图重新起一个弹窗"，
    # 所以自带一份（两边互不共享状态，见各文件的说明）。
    timg = make_image(200, 120)
    for x in range(150, 170):
        for y in range(50, 70):
            timg.setPixel(x, y, 0xFF000000)

    # ---- 「完成」直接收尾：挂起的变换必须落到实体图（2026-10-10 报障） ----
    # 松手只挂起（上面的用例刚验过），此后**不切工具**、直接点「完成」：
    # _finish 里的 _commit_transform 不带 force 的话会被"挂起跳过"分支
    # 原样退回，烘焙整个被跳过 ⇒ 结果图还是原图（用户报的正是它）。
    from PySide6.QtWidgets import QDialog

    dialogF = ImageEditorDialog(None, timg)
    try:
        canvasF = dialogF.canvas
        canvasF.set_tool("transform")
        canvasF.transform_rotate(90)
        canvasF.make_transform_pending()   # 模拟真实拖动松手后的挂起态
        ok("变换：挂起态直接点「完成」前像素未动",
           canvasF.has_pending_transform()
           and canvas_img(canvasF).size() == timg.size(), "")
        dialogF._finish()
        done = dialogF.result_image()
        ok("变换：「完成」直接收尾也烘焙（结果 = 旋转后 120×200）",
           dialogF.result() == QDialog.DialogCode.Accepted
           and done is not None
           and (done.width(), done.height()) == (120, 200)
           and canvasF.transform_pending() is None,
           f"result={dialogF.result()} size="
           + ("None" if done is None
              else f"{done.width()}x{done.height()}"))
    finally:
        dialogF.deleteLater()

    # ---- 透明源图：烘焙后空出来的地方保持透明（2026-10-10 报障） ----
    # 去底色产物整幅旋转：画布预览（10-09 起）空处透明，烘焙却留着
    # 两处硬编码填白（原位 fillRect + grow 底图）⇒ 存盘变白底。
    # 空处填色统一为 _empty_fill：源图真有 alpha ⇒ 透明，否则白。
    # 内容铺满整幅（只留一个透明孔）：内容收紧（_trim_transparent_edges）
    # 对"贴边内容"是 no-op，90° 互换的尺寸口径不变。
    from PySide6.QtGui import QColor as _QC

    timgA = make_image(200, 120)
    timgA.fill(_QC(255, 0, 0, 255))
    for x in range(96, 104):            # 中央 8×8 透明孔
        for y in range(56, 64):
            timgA.setPixel(x, y, 0x00000000)
    dialogA = ImageEditorDialog(None, timgA)
    try:
        canvasA = dialogA.canvas
        canvasA.set_tool("transform")
        canvasA.transform_rotate(90)
        dialogA._commit_transform(force=True)
        got = canvas_img(canvasA)
        ok("变换：透明源图烘焙不染白（尺寸 90° 互换、中心孔保持透明）",
           abs(got.width() - 120) <= 1 and abs(got.height() - 200) <= 1
           and got.pixelColor(60, 100).alpha() == 0,
           f"size={got.width()}x{got.height()} "
           f"hole_a={got.pixelColor(60, 100).alpha()}")
        _reds = [
            (x, y)
            for x in range(0, got.width(), 2)
            for y in range(0, got.height(), 2)
            if got.pixelColor(x, y).alpha() > 200
            and got.pixelColor(x, y).red() > 150
            and got.pixelColor(x, y).green() < 100
        ]
        ok("变换：透明源图烘焙后红块完好（内容没被垫底吃掉）",
           len(_reds) >= 5000
           and got.pixelColor(2, 2).red() > 150,
           f"红块采样点={len(_reds)} "
           f"角={got.pixelColor(2, 2).name()}")
        # clip 档：画布尺寸不变，原位必须真清除（Clear）——
        # 透明色 SourceOver 盖不住，会留 ghost + 白底双重 bug。
        # ⚠️ 入口内容提取后主体＝内容块本身（20×20），转 90° 会铺满
        #    整幅、没有空处可验 ghost ⇒ 转 45°，四角空出来。
        timgC = make_image(200, 120)
        timgC.fill(_QC(0, 0, 0, 0))
        for x in range(150, 170):
            for y in range(50, 70):
                timgC.setPixel(x, y, 0xFFFF0000)
        timgC.setPixel(169, 69, 0x00000000)   # 缺角 ⇒ 真有 alpha
        timgC.setPixel(168, 69, 0x00000000)
        timgC.setPixel(169, 68, 0x00000000)
        dialogC = ImageEditorDialog(None, timgC)
        try:
            canvasC = dialogC.canvas
            gotC = canvas_img(canvasC)
            ok("编辑入口内容提取：打开带空白边的透明图，主体＝内容外框",
               (gotC.width(), gotC.height()) == (20, 20)
               and gotC.pixelColor(10, 10).alpha() > 200,
               f"size={gotC.width()}x{gotC.height()}")
            canvasC.set_tool("transform")
            canvasC._xf_clipping = "clip"
            canvasC.transform_rotate(45)
            dialogC._commit_transform(force=True)
            got2 = canvas_img(canvasC)
            _reds2 = [
                (x, y)
                for x in range(0, got2.width(), 2)
                for y in range(0, got2.height(), 2)
                if got2.pixelColor(x, y).alpha() > 200
                and got2.pixelColor(x, y).red() > 150
                and got2.pixelColor(x, y).green() < 100
            ]
            ok("变换：透明源图 clip 档不染白、原位不留 ghost（红块只有一份）",
               abs(got2.width() - 20) <= 1
               and abs(got2.height() - 20) <= 1
               and got2.pixelColor(2, 2).alpha() == 0
               and 20 <= len(_reds2) <= 90,
               f"size={got2.width()}x{got2.height()} "
               f"corner_a={got2.pixelColor(2, 2).alpha()} "
               f"红块采样点={len(_reds2)}")
        finally:
            dialogC.deleteLater()

        # 入口提取**不碰**不透明图：白边可能是"纸"的内容。
        dialogO = ImageEditorDialog(None, make_image(200, 120))
        try:
            gotO = canvas_img(dialogO.canvas)
            ok("编辑入口不裁不透明图（白边可能是纸的内容）",
               (gotO.width(), gotO.height()) == (200, 120),
               f"size={gotO.width()}x{gotO.height()}")
        finally:
            dialogO.deleteLater()
    finally:
        dialogA.deleteLater()

    # ---- 透明源图「旋转→保存→再旋转」不再越滚越大（2026-10-10） ----
    # 旧版外框按**画布矩形四角**算：A(200×120, 内容 100×60) 转 45° →
    # 外框 ≈114²（恰＝内容外框，暂无多余边）；存盘后二次编辑的主体
    # 变成 A1（含四角空白），再转 45° 外框按 A1 四角又扩 √2 倍 ≈161²，
    # 内容占比每转一次缩一截。内容收紧后：烘焙结果裁到**非透明像素**
    # 的真实外框，二次旋转回到内容本身的 90° 外框 ≈62×102。
    timgB = make_image(200, 120)
    timgB.fill(_QC(0, 0, 0, 0))
    for x in range(50, 150):
        for y in range(30, 90):
            timgB.setPixel(x, y, 0xFF00FF00)   # 居中绿块 100×60
    for x in range(96, 104):            # 中央 8×8 透明孔：去底色
        for y in range(56, 64):         # 产物 bbox 内总有透明像素
            timgB.setPixel(x, y, 0x00000000)
    dialogB = ImageEditorDialog(None, timgB)
    try:
        canvasB = dialogB.canvas
        canvasB.set_tool("transform")
        canvasB.transform_rotate(45)
        dialogB._commit_transform(force=True)
        r1 = canvas_img(canvasB)
        ok("变换：透明图转 45° 外框＝内容外框（≈114²，无多余边）",
           106 <= r1.width() <= 122 and 106 <= r1.height() <= 122,
           f"r1={r1.width()}x{r1.height()}")
        canvasB.set_tool("transform")
        canvasB.transform_rotate(45)
        dialogB._commit_transform(force=True)
        r2 = canvas_img(canvasB)
        _area1, _area2 = r1.width() * r1.height(), \
            r2.width() * r2.height()
        ok("变换：再转 45° 内容收紧回 90° 外框（≈62×102，不按 √2 滚大）",
           54 <= r2.width() <= 72 and 94 <= r2.height() <= 112
           and _area2 < _area1 * 0.6,
           f"r2={r2.width()}x{r2.height()} "
           f"面积比={_area2 / _area1:.2f}")
    finally:
        dialogB.deleteLater()

    # ---- 内容四角节点：sidecar 落盘 + 二次编辑恢复（2026-10-10） ----
    # 用户口径：p1..p4 旋转后变成 p11..p41，节点数据随图片一起保存；
    # 二次编辑时读回来，「统一变换」的可编辑区域＝内容四边形本身，
    # 框/手柄恢复到"没保存时"的状态，区域外都是无意义空白。
    from pathlib import Path as _Path

    from desktop.components.viewers.image_editor import (
        quad_path, read_quad, sync_content_quad, upright_image,
        write_quad,
    )
    from tests.tmpdir import temp_dir as _temp_dir

    _qdir = _temp_dir("quad_")
    _qpath = _qdir / "page.png"
    baseA = make_image(200, 120)
    # ⚠️ 打一个色块标记：纯白图查不出"反变换位移"（旧回归只查尺寸，
    #    矩阵顺序错了照样绿——2026-10-10「PA1 顶部被削一段」漏网）。
    for _mx in range(30, 50):
        for _my in range(15, 35):
            baseA.setPixel(_mx, _my, 0xFF0000FF)   # 蓝块 20×20
    rect0 = QRectF(0, 0, 200, 120)
    v45 = rotate_about(QPointF(100, 60), 45.0)
    look = compose_transform(
        baseA, rect0, v45, baseA.copy(), grow=True)[0]
    look.save(str(_qpath), "PNG")
    write_quad(_qpath, rect0, v45)
    _rq = read_quad(_qpath)
    ok("内容节点：sidecar 写读回环（rect0/V 保真）",
       _rq is not None and _rq[0] == rect0 and _rq[1] == v45,
       f"rect={None if _rq is None else _rq[0]}")
    up = upright_image(look, rect0, v45, "linear")
    _up_ok = up is not None and (up.width(), up.height()) == (200, 120)
    _mark = [
        (36, 21), (44, 29), (40, 25),   # 蓝块内点：原位才算恢复对
        (100, 60),                       # 中心（rotate_about 的轴心）
    ]
    _mark_hits = [
        _up_ok
        and up.pixelColor(x, y).alpha() > 200
        and up.pixelColor(x, y).blue() > 150
        and up.pixelColor(x, y).red() < 100
        for x, y in _mark[:3]]
    ok("内容节点：反变换回 upright（尺寸回到 rect0）",
       _up_ok,
       "size=" + ("None" if up is None
                  else f"{up.width()}x{up.height()}"))
    ok("内容节点：反变换内容**原位**（蓝块 3 内点全中，矩阵顺序正确）",
       all(_mark_hits),
       f"hits={_mark_hits} center={_up_ok and up.pixelColor(100, 60).name()}")

    editorQ = ImageEditorDialog(None, look, save_back=True)
    try:
        editorQ.source_path = str(_qpath)
        # 进变换工具 ⇒ 触发 sidecar 恢复（小图走同步档，无进度框）
        editorQ.canvas.set_tool("transform")
        gotQ = canvas_img(editorQ.canvas)

        from desktop.components.viewers.image_editor.content_quad \
            import quad_frame as _quad_frame
        from PySide6.QtGui import QTransform as _QTx

        _ox, _oy, _fw, _fh = _quad_frame(v45, rect0)
        seedQ = _QTx(v45) * _QTx().translate(-_ox, -_oy)
        ok("内容节点：PB1 作画布不换图（画布＝文件原样、恢复已武装）",
           (gotQ.width(), gotQ.height())
           == (look.width(), look.height())
           and gotQ == look
           and editorQ.canvas._xf_restore_region is None
           and editorQ.canvas._xf_restore_pending
           and editorQ._content_restored,
           f"size={gotQ.width()}x{gotQ.height()} "
           f"restored={editorQ._content_restored} "
           f"pending={editorQ.canvas._xf_restore_pending}")
        # ⚠️ 2026-10-10「切换卡顿」：upright 反变换**延迟**到第一次
        #    建预览才算——进工具后浮层还没像素（restore_region None），
        #    但框/矩阵已经挂好；第一次建预览后像素必须到位。
        editorQ.canvas._ensure_transform_preview()
        ok("内容节点：首次预览补齐 upright 像素（延迟反变换到位）",
           editorQ.canvas._xf_restore_region is not None
           and not editorQ.canvas._xf_restore_pending
           and editorQ.canvas._float_item is not None, "")
        quadQ = editorQ.canvas._transform_quad()
        wantQ = {
            "tl": seedQ.map(rect0.topLeft()),
            "tr": seedQ.map(rect0.topRight()),
            "br": seedQ.map(rect0.bottomRight()),
            "bl": seedQ.map(rect0.bottomLeft()),
        }
        ok("内容节点：PB1 作画布、PA1 恢复为可操作四边形（框在内容节点上）",
           all((quadQ[k] - wantQ[k]).manhattanLength() < 2.5
               for k in wantQ),
           f"tl={quadQ['tl']} want_tl={wantQ['tl']}")
        _xfq = editorQ.canvas._xf
        ok("内容节点：矩阵挂回画布系种子 V（未触摸、零烘焙）",
           _xfq == seedQ and not editorQ.canvas._xf_touched,
           f"touched={editorQ.canvas._xf_touched}")
        # 恢复态继续转 45° ⇒ 总量 90°，烘焙＝从 upright 单次重采样
        editorQ.canvas.transform_rotate(45)
        editorQ._commit_transform(force=True)
        doneQ = canvas_img(editorQ.canvas)
        ok("内容节点：恢复态再转 45° ⇒ 总量 90°（120×200，单次代次）",
           abs(doneQ.width() - 120) <= 1
           and abs(doneQ.height() - 200) <= 1,
           f"size={doneQ.width()}x{doneQ.height()}")
        _st = editorQ.content_state()
        sync_content_quad(str(_qpath), editorQ)
        _rq2 = read_quad(_qpath)
        ok("内容节点：烘焙后 V=总量矩阵并已写回 sidecar",
           _st is not None and _st[0] == rect0 and _rq2 is not None
           and _rq2[1] == _st[1],
           "state=" + ("None" if _st is None else "ok"))
    finally:
        editorQ.deleteLater()

    editorR = ImageEditorDialog(None, look, save_back=True)
    try:
        editorR.source_path = str(_qpath)
        editorR.canvas.set_tool("transform")   # 恢复（PB1 画布＋种子矩阵）
        # 什么都没拖就切走：真实路径先 _commit_transform（无待定 ⇒
        # 退回文件原样），画布不许把 upright 当结果
        editorR._commit_transform()
        editorR.canvas.set_tool("erase")
        gotR = canvas_img(editorR.canvas)
        ok("内容节点：未拖动退出恢复会话 ⇒ 画布回文件原样",
           (gotR.width(), gotR.height())
           == (look.width(), look.height()),
           f"size={gotR.width()}x{gotR.height()} "
           f"expect={look.width()}x{look.height()}")
        # ⚠️ 2026-10-10「切走再切回要恢复」：图片边缘没变（裁剪没裁/
        #    文字/擦除/扭曲都不改边缘）⇒ 切回统一变换 PA1 重新武装
        editorR.canvas.set_tool("transform")
        ok("内容节点：切走没拖再切回 ⇒ PA1 重新武装（框/矩阵/待定像素）",
           editorR.canvas._xf_restore_pending
           and editorR.canvas._xf_restore_region is None
           and editorR.canvas._xf_rect is not None
           and editorR._content_restored,
           f"pending={editorR.canvas._xf_restore_pending} "
           f"restored={editorR._content_restored}")
        ok("内容节点：重挂矩阵＝同一颗种子（框回到内容四边形）",
           editorR.canvas._xf == editorR._content_seed, "")
        # 首次拖动要用的反变换参数必须来自**当前画布**（擦除原地改
        # 引用不变，旧 upright 缓存作废重算才不丢改动）
        _prm = editorR._content_restore_params
        ok("内容节点：重挂后反变换参数引用当前画布像素",
           _prm is not None and _prm["image"] is editorR._image, "")
    finally:
        editorR.deleteLater()

    # ---- 真裁剪 ⇒ 节点整组作废（边缘变了不恢复，2026-10-10 口径） ----
    editorC = ImageEditorDialog(None, look, save_back=True)
    try:
        editorC.source_path = str(_qpath)
        editorC.canvas.set_tool("transform")     # 先武装恢复会话
        editorC._pending_crop = QRectF(10, 10, 80, 60)
        editorC._commit_crop()                   # 真裁一刀（尺寸变了）
        ok("内容节点：真裁剪 ⇒ 节点整组作废",
           editorC._content_state is None
           and not editorC._content_restored,
           f"state={editorC._content_state is not None}")
        editorC._commit_transform()              # 切走（无待定变换）
        editorC.canvas.set_tool("transform")
        ok("内容节点：真裁剪后切回 ⇒ 不再恢复（整幅矩形框架）",
           not editorC.canvas._xf_restore_pending
           and editorC._content_state is None,
           f"pending={editorC.canvas._xf_restore_pending}")
    finally:
        editorC.deleteLater()

    # ---- 首次会话：旋转→烘焙→切走→切回 ⇒ PA1 延续（2026-10-10 报障） ----
    # 没有 sidecar 的第一次编辑里转了 30°、切到别的工具（触发烘焙）、
    # 再切回「统一变换」：节点链已在内存里建起来（_content_after_bake），
    # 恢复闸门必须重新武装、框回到内容四边形——之前带挂起变换的烘焙
    # 分支不 rearm，切回后框退成整幅（用户截图：p5..p8 而非 p11..p41）。
    # ⚠️ 用带透明边的图：烘焙后画布＝烘焙产物（自洽成帧），入口收紧
    #    偏移 t 必须清零——不清的话重挂种子矩阵 V·T(-(o+t)) 整体错位 t。
    _imgS = make_image(300, 220)
    _imgS.fill(_QC(0, 0, 0, 0))
    for _sx in range(70, 230):
        for _sy in range(60, 160):
            _imgS.setPixel(_sx, _sy, 0xFF888888)
    for _sx in range(80, 100):          # 蓝块标记：内容原位可查
        for _sy in range(70, 90):
            _imgS.setPixel(_sx, _sy, 0xFF0000FF)
    editorS = ImageEditorDialog(None, _imgS, save_back=True)
    try:
        # ⚠️ rearm 只在有底片文件时发生（sidecar 机制围着文件转）：
        #    给一个临时路径（不真写盘），模拟拼版宿主回填 source_path
        editorS.source_path = str(_qdir / "first_session.png")
        editorS.canvas.set_tool("transform")
        editorS.canvas.transform_rotate(30)
        _baked = editorS._commit_transform(force=True)
        _st1 = editorS.content_state()
        ok("内容节点：首次会话烘焙 ⇒ 节点链建立（rect0=画布整幅）",
           _baked and _st1 is not None
           and abs(_st1[0].width() - 160) <= 1
           and abs(_st1[0].height() - 100) <= 1,
           f"baked={_baked} state={'None' if _st1 is None else 'ok'}")
        ok("内容节点：烘焙后入口收紧偏移清零（画布＝烘焙产物自洽成帧）",
           getattr(editorS, "_content_trim_offset", None) == (0.0, 0.0),
           f"trim={getattr(editorS, '_content_trim_offset', None)}")
        ok("内容节点：烘焙后恢复闸门重新武装（切回要能恢复）",
           editorS.canvas._content_restore_done is False,
           f"done={editorS.canvas._content_restore_done}")
        editorS.canvas.set_tool("crop")
        editorS.canvas.set_tool("transform")
        _csize = editorS.canvas.image.rect()
        _quad = (editorS._content_seed.mapRect(
            QRectF(0, 0, 160, 100)).toRect()
            if editorS._content_seed else None)
        ok("内容节点：旋转切走再切回 ⇒ PA1 恢复（全量武装、像素就位）",
           editorS.canvas._xf_restore_pending is False
           and editorS.canvas._xf_restore_region is not None
           and (editorS.canvas._xf_restore_region.width(),
                editorS.canvas._xf_restore_region.height())
           == (editorS._content_upright.width(),
               editorS._content_upright.height())
           and editorS._content_restored
           and editorS.canvas._xf_rect is not None
           and abs(editorS.canvas._xf_rect.width() - 160) <= 1
           and abs(editorS.canvas._xf_rect.height() - 100) <= 1,
           f"pending={editorS.canvas._xf_restore_pending} "
           f"region={'None' if editorS.canvas._xf_restore_region is None else 'ok'} "
           f"xf_rect={None if editorS.canvas._xf_rect is None else (editorS.canvas._xf_rect.width(), editorS.canvas._xf_rect.height())}")
        ok("内容节点：切回零等待（upright 缓存复用、无重算参数）",
           editorS._content_upright is not None
           and editorS._content_restore_params is None
           and not editorS._content_pixels_dirty,
           f"upright={'None' if editorS._content_upright is None else 'ok'} "
           f"params={editorS._content_restore_params}")
        ok("内容节点：重挂种子不含旧收紧偏移（内容四边形=烘焙画布原位）",
           _quad is not None
           and abs(_quad.x()) <= 1 and abs(_quad.y()) <= 1
           and abs(_quad.width() - _csize.width()) <= 2
           and abs(_quad.height() - _csize.height()) <= 2,
           f"quad={_quad} canvas={_csize.width()}x{_csize.height()}")
    finally:
        editorS.deleteLater()

    # ---- 延迟恢复 + 拖动守卫（2026-10-10「切换卡顿」） ----
    # 等待恢复像素的那次等待里有模态进度框（processEvents），用户的
    # 左键可能已在等待中松开——那个 release 被进度框吃掉，画布永远
    # 等不到；不守卫的话"拖动"一直挂着，鼠标一动内容就跟着跑。
    # 离屏环境没有真实按键 ⇒ mouseButtons() 恒空 ⇒ 恰好走进守卫。
    editorD = ImageEditorDialog(None, look, save_back=True)
    try:
        editorD.source_path = str(_qpath)
        editorD.canvas.set_tool("transform")
        ok("内容节点：延迟武装（进工具零反变换、框已就位）",
           editorD.canvas._xf_restore_pending
           and editorD.canvas._xf_restore_region is None
           and editorD.canvas._xf_rect is not None, "")
        modeD = editorD.canvas._begin_transform_drag(
            "inside", QPointF(100, 60), Qt.KeyboardModifier.NoModifier)
        ok("内容节点：等待像素期间左键已松 ⇒ 取消本次拖拽（防挂死）",
           modeD is None
           and editorD.canvas._xf_restore_region is not None
           and not editorD.canvas._xf_restore_pending, "")
    finally:
        editorD.deleteLater()