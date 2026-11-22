# -*- coding: utf-8 -*-
"""拼版左列右键菜单 + 「插入拼版」弹窗（用户 2026-11-16）。

> 参考 PDF排版，左列缩略图右键给「上移 / 下移 / 删除 / 向前插入 / 向后插入」；
> 「选择拼版」弹窗改成两个页签（选择拼版 / 删除恢复），并且能自己上传图片，
> 同一张图片可以多次上传。

守护六件事：

1. **菜单**：五条文案与顺序、首/末行的上移/下移置灰、右键即把该页设成当前页；
2. **信号**：每条菜单项发出对应的 ``move/remove/insert`` 请求（视图再转发给
   控制器），落盘与"图片释放回候选池"的语义都不在控件里做；
3. **页签**：弹窗两个页签的文案与切换（``选择拼版`` / ``删除恢复``），删除的
   图恢复后回到候选池；
4. **上传**：拖入/选择本地图的落法与"**同一张图可以多次上传**"（每一次都是
   独立的一条候选，不去重）；
5. **插入模式**：确认按钮文案、落点单选（默认按右键那一项）、``position()``；
6. **落点与成页的纯函数**：``services.imposition_insert`` 的复制（重名避让）、
   成页（每两张一页 + 落单单页）、插入位置。

⚠️ 模块自建控件、DEPENDS 为空：弹窗与视图都不 show，缩略图解码不影响断言。
"""

from __future__ import annotations

from pathlib import Path

NAME = "imposition_edit"
DEPENDS: list[str] = []
TITLE = "拼版左列右键菜单 + 插入拼版弹窗（上移/下移/删除/插入/上传）"


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_menu(ctx, ok)
    _check_single_list(ctx, ok)
    _check_upload(ctx, ok)
    _check_insert_mode(ctx, ok)
    _check_service(ctx, ok)


# ------------------------------------------------------------------ 工具
def _page(*stems: str) -> dict:
    """一页拼版（**虚拟**：只要文件名与 rect，不读盘）。"""
    return {
        "items": [
            {
                "file": f"C:/guji_fake/{stem}.png",
                "rect": [0.0, 0.0, 100.0, 200.0],
                "rotation": 0.0,
            }
            for stem in stems
        ]
    }


def _view(pages: int = 3):
    """建一个 ``pages`` 页的拼版视图（当前在第一页）。"""
    from desktop.components.imposition.view import ImpositionViewWidget

    view = ImpositionViewWidget()
    view.set_pages(
        [_page(f"{i}-r", f"{i}-l") for i in range(1, pages + 1)], current=0,
    )
    return view


def _image(path: Path, size=(240, 360), color="#3366CC") -> Path:
    """落一张真图（``classify_source``/缩略图解码都要读尺寸）。"""
    from PySide6.QtGui import QColor, QImage

    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    image.save(str(path))
    return path


def _menu_exec_patch():
    """把 ``RoundMenu.exec`` 换成**只记录、不弹出**的版本（离屏不真弹菜单）。"""
    from qfluentwidgets.components.widgets.menu import RoundMenu

    captured: dict = {}
    real = RoundMenu.exec

    def fake(self, pos, ani=True, aniType=None):
        captured["actions"] = list(self.actions())
        return None

    RoundMenu.exec = fake
    return captured, lambda: setattr(RoundMenu, "exec", real)


def _texts(actions) -> list[str]:
    return [action.text() for action in actions if not action.isSeparator()]


# ------------------------------------------------------------------ 1. 菜单
def _check_menu(ctx, ok) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QApplication

    view = _view(3)
    page_list = view.page_list
    entries = page_list.entries()
    moved: list = []
    removed: list = []
    inserted: list = []
    selected: list = []
    view.page_move_requested.connect(lambda i, d: moved.append((i, d)))
    view.page_remove_requested.connect(removed.append)
    view.page_insert_requested.connect(lambda i, p: inserted.append((i, p)))
    view.page_selected.connect(selected.append)

    captured, restore = _menu_exec_patch()
    try:
        # 右键第 2 页**自己**（走真实的 QContextMenuEvent → CustomContextMenu →
        # 宿主槽，确认这条管线真的通，而不是只测槽函数）。
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse, QPoint(6, 6), QPoint(6, 6)
        )
        QApplication.sendEvent(entries[1], event)
        actions = captured.get("actions") or []
        ok(
            "右键缩略图弹出菜单：上移 / 下移 / 删除当前拼版 / 向前插入拼版 / "
            "向后插入拼版",
            _texts(actions) == [
                "上移", "下移", "删除当前拼版", "向前插入拼版", "向后插入拼版",
            ],
            str(_texts(actions)),
        )
        ok(
            "右键即把该页设为当前页（菜单动作作用在这一页上）",
            page_list.current() == 1 and selected == [1],
            f"current={page_list.current()} selected={selected}",
        )
        # 用户真正右键的是**缩略图**（不是条目留白）：子控件不处理右键，
        # 事件冒泡到条目 —— 这条不能只靠"读代码觉得应该行"。
        for slot_name in ("thumb", "title_label"):
            captured.clear()
            QApplication.sendEvent(
                getattr(entries[1], slot_name),
                QContextMenuEvent(
                    QContextMenuEvent.Reason.Mouse, QPoint(4, 4), QPoint(4, 4)
                ),
            )
            ok(
                f"右键「{slot_name}」子控件同样弹菜单（事件冒泡到条目）",
                len(_texts(captured.get("actions") or [])) == 5,
                str(captured.get("actions")),
            )
        actions = captured.get("actions") or []
        by_text = {a.text(): a for a in actions if not a.isSeparator()}
        ok(
            "中间页：上移 / 下移都可点",
            by_text["上移"].isEnabled() and by_text["下移"].isEnabled(),
        )
        by_text["上移"].trigger()
        by_text["下移"].trigger()
        by_text["删除当前拼版"].trigger()
        by_text["向前插入拼版"].trigger()
        by_text["向后插入拼版"].trigger()
        ok(
            "菜单项发出对应请求（move / remove / insert before+after）",
            moved == [(1, -1), (1, 1)]
            and removed == [1]
            and inserted == [(1, "before"), (1, "after")],
            f"moved={moved} removed={removed} inserted={inserted}",
        )

        # 首行：上移置灰；末行：下移置灰（点了"没反应"比置灰更困惑）
        QApplication.sendEvent(entries[0], event)
        first = {a.text(): a for a in captured["actions"] if not a.isSeparator()}
        ok(
            "首页：上移置灰、下移可点",
            not first["上移"].isEnabled() and first["下移"].isEnabled(),
        )
        QApplication.sendEvent(entries[2], event)
        last = {a.text(): a for a in captured["actions"] if not a.isSeparator()}
        ok(
            "末页：下移置灰、上移可点",
            not last["下移"].isEnabled() and last["上移"].isEnabled(),
        )
    finally:
        restore()
        view.hide()
        view.deleteLater()

    # 越界保护：控制器侧也要挡住（菜单置灰是第一道，代码路径是第二道）
    page_list2 = _view(2).page_list
    calls: list = []
    page_list2.move_requested.connect(lambda i, d: calls.append((i, d)))
    page_list2._run_menu_action("remove", 5)
    ok("越界下标的菜单动作直接忽略（不发请求）", not calls)


# ------------------------------------------------------------- 2. 弹窗页签
def _check_single_list(ctx, ok) -> None:
    """用户 2026-11-16：**取消两个页签**，弹窗只剩一个列表。

    删掉的图（`删除图片` 那只按钮）也一并取消——列表里恒是"所有还能用的图"：
    上游剩余 + 自己上传过的；删拼版页的图由控制器放回候选池（见
    ``imposition.py`` 的候选池断言）。
    """
    from desktop.components.imposition.picker import ImpositionPickerDialog

    root = ctx.tmp / "imposition_edit" / "list"
    a = _image(root / "1-r.png", color="#CC3333")
    b = _image(root / "1-l.png", color="#33CC33")
    dialog = ImpositionPickerDialog([a, b])
    ok(
        "弹窗没有页签（只剩一个列表）",
        not hasattr(dialog, "toggle")
        and not hasattr(dialog, "stack")
        and not hasattr(dialog, "current_tab"),
    )
    ok(
        "弹窗没有「删除图片 / 恢复选中 / 全部恢复」按钮",
        not hasattr(dialog, "delete_button")
        and not hasattr(dialog, "restore_button")
        and not hasattr(dialog, "restore_all_button")
        and not hasattr(dialog, "removed_cards"),
    )
    ok(
        "候选池里的图全部列出（没有黑名单/隐藏）",
        dialog.count() == 2 and [c.path.name for c in dialog.cards]
        == ["1-r.png", "1-l.png"],
        str([c.path.name for c in dialog.cards]),
    )
    ok(
        "列表外的控件也只剩：说明 / 状态 / 上传 / 确认",
        dialog.upload_row.isVisibleTo(dialog) and dialog.ok_button.isVisibleTo(dialog),
    )
    dialog.deleteLater()


# ----------------------------------------------------------------- 3. 上传
def _check_upload(ctx, ok) -> None:
    from desktop.components.imposition.picker import (
        THUMB_H, THUMB_W, ImpositionPickerDialog,
    )

    root = ctx.tmp / "imposition_edit" / "upload"
    pool_a = _image(root / "pool-a.png", color="#CC3333")
    pool_b = _image(root / "pool-b.png", color="#33CC33")
    mine = _image(root / "my-scan.png", color="#3333CC")

    dialog = ImpositionPickerDialog([pool_a, pool_b])
    ok("上传前候选 = 源池 2 张", dialog.count() == 2)
    # 同一张图**上传两次**：用户 2026-11-16 第 4 条（与「PDF排版」同一规范）
    dialog.add_uploads([str(mine), str(mine)])
    ok(
        "同一张图片上传两次 → 两条独立候选（不去重）",
        dialog.count() == 4
        and [card.path.name for card in dialog.cards[-2:]] == ["my-scan.png"] * 2
        and dialog.cards[-1].cand_key != dialog.cards[-2].cand_key,
        f"count={dialog.count()} keys={[c.cand_key for c in dialog.cards]}",
    )
    ok(
        "上传的图默认勾上（勾满 2 张为止）",
        [card.is_checked() for card in dialog.cards] == [False, False, True, True],
        str([card.is_checked() for card in dialog.cards]),
    )
    chosen = dialog.chosen_items()
    ok(
        "chosen_items 标出「本次上传」（宿主据此把它复制进任务目录）",
        len(chosen) == 2
        and all(item["uploaded"] for item in chosen)
        and [item["path"].name for item in chosen] == ["my-scan.png"] * 2,
        str(chosen),
    )
    ok(
        "上传过但没勾的图也记得住（uploaded_files）",
        len(dialog.uploaded_files()) == 2,
        str(dialog.uploaded_files()),
    )
    # 上传的图**必须带缩略图**（用户 2026-11-16：列表里是空白的）
    for _ in range(6):
        ctx.app.processEvents()
    dialog._fill_thumbs()
    ok(
        "上传的图有缩略图（不再空白）",
        all(
            card._pixmap.width() == THUMB_W and card._pixmap.height() == THUMB_H
            for card in dialog.cards[-2:]
        ),
        str([card._pixmap.size() for card in dialog.cards]),
    )
    dialog.deleteLater()


# ------------------------------------------------------------- 4. 插入模式
def _check_insert_mode(ctx, ok) -> None:
    from desktop.components.imposition.picker import ImpositionPickerDialog

    root = ctx.tmp / "imposition_edit" / "insert"
    a = _image(root / "2-r.png", color="#CC3333")
    dialog = ImpositionPickerDialog(
        [a], mode="insert", position="before", current_row=1, total=4,
    )
    ok(
        "插入模式：标题与确认按钮文案",
        dialog.windowTitle() == "插入拼版" and dialog.ok_button.text() == "插入",
        f"{dialog.windowTitle()} / {dialog.ok_button.text()}",
    )
    ok(
        "插入模式：落点单选可见，默认「之前」（按右键那一项）",
        dialog.position_row.isVisibleTo(dialog) and dialog.position() == "before",
    )
    ok(
        "落点单选写的是当前页号（第 2 页之前 / 之后）",
        dialog.before_radio is not None
        and dialog.before_radio.text() == "插入第 2 页之前"
        and dialog.after_radio.text() == "插入第 2 页之后",
        str(dialog.before_radio and dialog.before_radio.text()),
    )
    dialog.after_radio.setChecked(True)
    ok("改成「之后」→ position() 跟着变", dialog.position() == "after")
    dialog.cards[0].toggle()
    ok("勾 1 张即可插入（单张单独成一页）", dialog.ok_button.isEnabled())
    dialog.cards[0].toggle()
    dialog.cards[0].toggle()
    dialog.cards[0].toggle()
    ok("取消勾选 → 插入不可点", not dialog.ok_button.isEnabled())
    dialog.deleteLater()

    # 追加模式（单图页「新增图片」）：按钮文案仍是「添加」，且没有落点单选
    append = ImpositionPickerDialog([a], mode="append")
    ok(
        "追加模式：确认按钮文案「添加」、无落点单选",
        append.ok_button.text() == "添加"
        and not append.position_row.isVisibleTo(append),
        append.ok_button.text(),
    )
    append.deleteLater()

    pick = ImpositionPickerDialog([a])
    ok(
        "选页模式：确认按钮文案「开始拼版」、无落点单选",
        pick.ok_button.text() == "开始拼版"
        and not pick.position_row.isVisibleTo(pick),
        pick.ok_button.text(),
    )
    pick.deleteLater()


# --------------------------------------------------------------- 5. 纯函数
def _check_service(ctx, ok) -> None:
    from desktop.services.imposition_insert import (
        insert_pages_at,
        pages_from_candidates,
        resolve_chosen,
        upload_dir,
        uploaded_candidates,
    )

    root = ctx.tmp / "imposition_edit" / "service"
    source = _image(root / "src" / "page-1.png", color="#883333")
    target = upload_dir(root / "task")
    ok(
        "上传落点 = <任务目录>/inserted/imposition（不与打印侧混放）",
        target == root / "task" / "inserted" / "imposition",
        str(target),
    )
    files, errors = resolve_chosen(
        [
            {"path": Path("C:/guji_fake/1-r.png"), "uploaded": False},
            {"path": source, "uploaded": True},
            {"path": source, "uploaded": True},
        ],
        target,
    )
    ok(
        "源池的图原样引用；同一张上传两次 → 落成两个不同文件名",
        not errors
        and files[0] == Path("C:/guji_fake/1-r.png")
        and [p.name for p in files[1:]] == ["page-1.png", "page-1-1.png"]
        and all(p.is_file() for p in files[1:]),
        f"files={[p.name for p in files]} errors={errors}",
    )
    ok(
        "复制用的是**副本**（源文件没被改名/移动）",
        source.is_file() and files[1] != source,
    )
    files2, errors2 = resolve_chosen(
        [
            {"path": root / "missing.png", "uploaded": True},
            {"path": source, "uploaded": True},
        ],
        target,
    )
    ok(
        "单张复制失败不拖垮整批（其余照常插入，失败写进说明）",
        len(files2) == 1 and len(errors2) == 1 and "missing.png" in errors2[0],
        f"files={files2} errors={errors2}",
    )

    two = _image(root / "pair" / "a.png")
    three = _image(root / "pair" / "b.png")
    one = _image(root / "pair" / "c.png")
    pages, failed = pages_from_candidates([str(two), str(three), str(one)])
    ok(
        "成页规则：每两张一页、落单的单图一页",
        len(pages) == 2
        and len(pages[0]["items"]) == 2
        and len(pages[1]["items"]) == 1
        and not failed,
        str([[Path(i["file"]).name for i in p["items"]] for p in pages]),
    )
    solo, _ = pages_from_candidates([str(one)])
    ok("单张 → 单图一页", len(solo) == 1 and len(solo[0]["items"]) == 1)
    broken, failed_names = pages_from_candidates([str(root / "nope.png")])
    ok(
        "读不到尺寸的图：不产页、但报出文件名",
        not broken and failed_names == ["nope.png"],
        str(failed_names),
    )

    merged = insert_pages_at(pages, solo, 0)
    ok(
        "插入到最前：新页在 [0]，原页序不变",
        len(merged) == 3
        and merged[0]["items"][0]["file"] == solo[0]["items"][0]["file"]
        and merged[1]["items"][0]["file"] == pages[0]["items"][0]["file"],
    )
    ok(
        "插入位置越界自动夹到末尾（不改入参）",
        insert_pages_at(pages, solo, 99)[-1]["items"][0]["file"]
        == solo[0]["items"][0]["file"]
        and len(pages) == 2,
    )

    # ---- 上传过的图 = 候选池的一部分（删拼版页后要能回到列表）----
    listed = uploaded_candidates(target)
    names = [p.name for p in listed]
    ok(
        "扫上传目录：列出的正好是刚才复制进去的那几张（不多不少）",
        sorted(names) == sorted(["page-1.png", "page-1-1.png", "page-1-2.png"]),
        str(names),
    )
    (target / "note.txt").write_text("不是图片", encoding="utf-8")
    ok(
        "扫上传目录只认图片扩展名（别的文件不混进候选）",
        all(p.suffix.lower() != ".txt" for p in uploaded_candidates(target)),
        str([p.name for p in uploaded_candidates(target)]),
    )
    ok(
        "目录不存在时返回空（不抛异常）",
        uploaded_candidates(root / "nope") == [],
    )
