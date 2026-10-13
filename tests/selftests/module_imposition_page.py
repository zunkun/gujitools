# -*- coding: utf-8 -*-
"""独立拼图页的面板能力与任务流程对齐（2026-10-13）。

起因：独立拼图页复用了 ``ImpositionPanel``，但「新增图片」
（``add_image_requested``）没接线、``set_single_page`` /
``set_item_rotation`` 从未被同步——「新增图片」「删除选中图片」两个按钮
在独立页**永远不出现**，整版旋转滑块也推了没反应。

守护四件事（都是"少接一根线就静默失效"的那种）：

1. **单图页「新增图片」**：``append`` 弹窗挑 1 张并进当前页，摆放走
   ``append_item_to_page``（原图版面原样保留）；加完变两图页，按钮隐藏；
2. **「删除选中图片」**：画布选中才出现；删掉一张页保留；删**最后一张**
   先弹确认（取消不动 / 确认整页移除）——与任务流程同口径；
3. **面板状态同步**：``_refresh_panel`` 回填整版角/选中角，单图页判定、
   无选中时删除按钮隐藏；
4. **旋转提交防抖**：整体/选中图旋转停手 250ms 统一 flush（写回 doc）+
   重适配 + 回填面板（与任务流程 ``EDIT_COMMIT_DEBOUNCE_MS`` 同档）。

⚠️ **DEPENDS 为空、自建页面**（与 ``module_edit_sync`` 同款做法）：页面级
断言不需要主窗口，隔离掉更稳也更快。
"""

from __future__ import annotations

from pathlib import Path

NAME = "module_imposition_page"
DEPENDS: list[str] = []
TITLE = "独立拼图页面板能力（新增/删除图片·旋转同步）"


def run(ctx) -> None:
    from tests.selftests._context import ok

    _check_add_image(ctx, ok)
    _check_delete_item(ctx, ok)
    _check_rotation_sync(ctx, ok)


# ------------------------------------------------------------------ 工具
def _png(path: Path, color: str, size: tuple[int, int] = (200, 300)) -> Path:
    """落一张纯色 PNG（与 module_edit_sync 同款做法）。"""
    from PySide6.QtGui import QColor, QImage

    image = QImage(size[0], size[1], QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path)), f"存图失败：{path}"
    return path


def _make_page(work: Path):
    """搭一个独立拼图页 + 三张源图（a 无后缀=整幅、b/c 同理）。"""
    from desktop.modules.imposition.page import ImpositionModulePage
    from desktop.services.imposition import make_single_page

    work.mkdir(parents=True, exist_ok=True)
    a = _png(work / "a.png", "#ffffff")
    b = _png(work / "b.png", "#111111")
    c = _png(work / "c.png", "#222222")
    page = ImpositionModulePage()
    page._set_sources([a, b, c])
    single = make_single_page(a)
    assert single is not None, "读不到 a.png 的尺寸"
    page._doc["pages"] = [dict(single)]
    page._refresh_view()
    page.view.set_current(0)  # 首次无选中：手动切到这一页，画布才有内容
    return page, a, b, c


class _StubPicker:
    """``ImpositionPickerDialog`` 替身：记录构造参数，返回预置勾选。"""

    last_init: tuple | None = None
    picked: list = []

    def __init__(self, files, parent=None, removed_files=None, mode="pick"):
        _StubPicker.last_init = (list(files), mode, list(removed_files or []))

    def exec(self) -> int:
        return 1

    def checked_files(self) -> list:
        return list(_StubPicker.picked)

    picked_files = checked_files

    def removed_changed(self) -> bool:
        return False

    def removed_files(self) -> list:
        return []


def _shutdown(page, app) -> None:
    from tests.selftests._context import pump

    try:
        page.shutdown_workers()
    except RuntimeError:
        pass
    page.deleteLater()
    pump(app, times=3)


# ------------------------------------------------------------------ 用例
def _check_add_image(ctx, ok) -> None:
    """单图页「新增图片」：接线 + append 摆放 + 加完按钮隐藏。"""
    import desktop.modules.imposition.page as imp_page_mod

    page, a, b, _c = _make_page(Path(ctx.tmp) / "imp_add")
    app = ctx.app
    try:
        ok("独立拼图页：单图页面板上「新增图片」露出",
           not page.panel.add_image_button.isHidden())
        _StubPicker.last_init = None
        _StubPicker.picked = [b]
        real_picker = imp_page_mod.ImpositionPickerDialog
        # ⚠️ page.py 是 `from ... import ImpositionPickerDialog` 按名导入，
        #    替身必须打在 page 模块的命名上（打在 picker 模块上不生效，
        #    真弹窗会在 offscreen 里 exec() 挂死——探针实测）。
        imp_page_mod.ImpositionPickerDialog = _StubPicker
        try:
            page.panel.add_image_requested.emit()
        finally:
            imp_page_mod.ImpositionPickerDialog = real_picker
        items = page._doc["pages"][0]["items"]
        ok("独立拼图页：「新增图片」接线生效，页里并进了第二张图",
           len(items) == 2 and str(items[1]["file"]) == str(b),
           f"{[it['file'] for it in items]}")
        ok("独立拼图页：append 弹窗是候选池口径（mode=append、剩余未用）",
           _StubPicker.last_init is not None
           and _StubPicker.last_init[1] == "append"
           and str(a) not in [str(f) for f in _StubPicker.last_init[0]],
           str(_StubPicker.last_init))
        ok("独立拼图页：原图的版面原样保留（append 不重排）",
           str(items[0]["file"]) == str(a) and len(items[0]["rect"]) == 4)
        ok("独立拼图页：加完变两图页，「新增图片」按钮隐藏",
           page.panel.add_image_button.isHidden())
        # 恢复单图页再验「弹窗取消：文档不动」
        from desktop.services.imposition import make_single_page

        single = make_single_page(a)
        assert single is not None
        page._doc["pages"] = [dict(single)]
        page._refresh_view()
        page.view.set_current(0)
        _StubPicker.picked = []

        class _CancelPicker(_StubPicker):
            def exec(self) -> int:
                return 0

        imp_page_mod.ImpositionPickerDialog = _CancelPicker
        try:
            before = [dict(it) for it in page._doc["pages"][0]["items"]]
            page.panel.add_image_requested.emit()
            after = page._doc["pages"][0]["items"]
            ok("独立拼图页：弹窗取消不改动版面",
               len(after) == len(before)
               and all(x["file"] == y["file"] for x, y in zip(after, before)))
        finally:
            imp_page_mod.ImpositionPickerDialog = real_picker
    finally:
        _shutdown(page, app)


def _check_delete_item(ctx, ok) -> None:
    """「删除选中图片」：选中才出现；删一张页保留；删最后一张先确认。"""
    import qfluentwidgets

    from desktop.services.imposition import make_page, make_single_page

    page, a, b, c = _make_page(Path(ctx.tmp) / "imp_del")
    app = ctx.app
    try:
        # 两图页：没选中时删除按钮隐藏；画布选中后出现
        two = make_page([b, c])
        assert two is not None
        page._doc["pages"] = [dict(two)]
        page._refresh_view()
        page.view.set_current(0)
        ok("独立拼图页：两图页未选中时「删除选中图片」隐藏",
           page.panel.delete_item_button.isHidden())
        page.view.canvas.select(0)
        ok("独立拼图页：画布选中图片后「删除选中图片」露出",
           not page.panel.delete_item_button.isHidden())
        # 删掉一张：页保留（剩一张），删除按钮随之隐藏（选中被清）
        page.panel.item_delete_requested.emit()
        items = page._doc["pages"][0]["items"]
        ok("独立拼图页：删掉选中的一张，页保留",
           len(items) == 1 and str(items[0]["file"]) == str(c),
           f"{[it['file'] for it in items]}")
        ok("独立拼图页：删除后选中清空，删除按钮隐藏",
           page.panel.delete_item_button.isHidden())
        # 删最后一张：先确认——取消不动 / 确认整页移除
        page.view.canvas.select(0)
        real_dialog = qfluentwidgets.Dialog

        class _FakeDialog:
            result = 1

            def __init__(self, *args, **kwargs) -> None:
                self.yesButton = type("B", (), {"setText": staticmethod(lambda *_: None)})()
                self.cancelButton = self.yesButton

            def exec(self) -> int:
                return _FakeDialog.result

        qfluentwidgets.Dialog = _FakeDialog
        try:
            _FakeDialog.result = 0
            page.panel.item_delete_requested.emit()
            ok("独立拼图页：删最后一张——确认弹窗取消则整页保留",
               len(page._doc["pages"]) == 1)
            _FakeDialog.result = 1
            page.panel.item_delete_requested.emit()
            ok("独立拼图页：删最后一张——确认后整页移除（与任务流程同款）",
               len(page._doc["pages"]) == 0)

            # 换单图页再删一次：确认弹窗同样整页移除（删除走 doc 口径）
            single = make_single_page(b)
            assert single is not None
            page._doc["pages"] = [dict(single)]
            page._refresh_view()
            page.view.set_current(0)
            page.view.canvas.select(0)
            page.panel.item_delete_requested.emit()
            ok("独立拼图页：单图页删最后一张——确认后整页移除",
               len(page._doc["pages"]) == 0)
        finally:
            qfluentwidgets.Dialog = real_dialog
    finally:
        _shutdown(page, app)


def _check_rotation_sync(ctx, ok) -> None:
    """旋转组件：选中角/整版角回填；停手防抖统一提交写回 doc。"""
    from desktop.services.imposition import make_page

    page, _a, b, c = _make_page(Path(ctx.tmp) / "imp_rot")
    app = ctx.app
    try:
        two = make_page([b, c])
        assert two is not None
        page._doc["pages"] = [dict(two)]
        page._refresh_view()
        page.view.canvas.select(0)
        # 选中图绝对角：组件吐角度 → 画布转 → 防抖到期写回 doc + 回填组件
        page.panel.item_rotation_edited.emit(90.0)
        ok("独立拼图页：选中图旋转先挂防抖（不立刻落盘）",
           page._rotate_commit_timer.isActive())
        page._rotate_commit_timer.stop()
        page._commit_rotation_edit()
        items = page._doc["pages"][0]["items"]
        ok("独立拼图页：防抖到期后选中角写回 doc（90°）",
           abs(float(items[0].get("rotation") or 0.0) - 90.0) < 1e-6,
           f"rotation={items[0].get('rotation')}")
        ok("独立拼图页：提交后面板回填选中角",
           abs(page.panel.item_spin.value() - 90.0) < 1e-6,
           f"spin={page.panel.item_spin.value()}")
        # 整版增量：在 90°/0° 基础上整体 +10° → 每张都叠加（相对角不变）：
        # [100, 10]，面板回填平均角 55（spread_rotation 口径）
        page.panel.whole_rotate_delta.emit(10.0)
        page._rotate_commit_timer.stop()
        page._commit_rotation_edit()
        items = page._doc["pages"][0]["items"]
        ok("独立拼图页：整版旋转增量写回 doc（每张都 +10°）",
           abs(float(items[0].get("rotation") or 0.0) - 100.0) < 1e-6
           and abs(float(items[1].get("rotation") or 0.0) - 10.0) < 1e-6,
           f"{[it.get('rotation') for it in items]}")
        ok("独立拼图页：提交后面板回填整版角（平均角）",
           abs(page.panel.whole_spin.value() - 55.0) < 1e-6,
           f"spin={page.panel.whole_spin.value()}")
        # 切页/刷新后面板状态与画布一致（单图页判定）
        ok("独立拼图页：两图页「新增图片」隐藏",
           page.panel.add_image_button.isHidden())
    finally:
        _shutdown(page, app)
