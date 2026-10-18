# -*- coding: utf-8 -*-
"""**模块二「拼版操作」控制器**：画布版面操作与拼版合成落盘。

对应 UI 模块二（``desktop/components/imposition/canvas.py`` +
``panel.py``）：
- 画布里拖动 / 缩放拉伸 / 旋转 → ``items_changed`` → 落盘 + 防抖合成；
- **双击预览**（用户 2026-09-30）：双击空白处预览整页左右组合；
- **右键菜单「预览图片 / 编辑图片」**：预览仍可针对单图或整页；编辑统一在
  同一画布显示本页两张源图，点击切换活动图并分别保存有修改的源图；
- **弹窗里「编辑」也落盘**（2026-10-07 用户定：预览弹窗不再只读）：单张
  原图回写源图文件；整页组合只预览，不提供合成图回写入口，
  生效链汇聚在 ``_on_imposition_zoom_image_saved``；
- 面板的**整体旋转**（滑块/输入框增量）、复位本页版面（对当前页或
  选中槽位做版面变换）、**删除选中图片**（2026-09-30 用户定：选中哪张
  就能删哪张，页保留、图回未选择列表）；
- 状态行（当前页 / 选中槽位 / 拼版是否生效 / 单图页显隐「新增图片」）；
- **后台防抖合成**（``stages/imposition/``，列表顺序即页序）与点「生成PDF」前
  的同步兜底合成。

只通过 ``self`` 依赖共享基元（``imposition.ImpositionBaseMixin``）与宿主
页面（``store``、``log_view``、``run_worker``、``_toast``），本文件
**不 import** 其它拼版控制器模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget

from desktop.services.imposition import (
    apply_editor_layout, cn_page_label, default_items, is_product_file,
    page_product_suffix, page_source_stems, product_path,
    refresh_rects_for_edited_source, single_items,
)

if TYPE_CHECKING:
    from desktop.store.store import TaskStore

#: 逐页「已落盘签名」的侧车文件后缀（与版面草稿**同目录、同作用域**）。
#:
#: 为什么必须落盘（用户 2026-10-18：「不应该是只改变一张图片吗……过了好久才更新」）：
#: 签名若只放内存，**一进新会话就没有基线**，判不出"哪些页已经是最新的"，只能把
#: 整本 85 页全量重合成——用户看到的就是"过了好久 + 风扇加快"。落盘后，重启再改
#: 一页 → 只重写那一页。
#:
#: ⚠️ 与版面草稿（``drafts/imposition[~节点].json``）同一个生命周期：任务删除、
#: 换源 PDF 时 ``drafts/`` 整体清掉，记录跟着没——那正是对的（产物也一起没了）。
COMPOSED_SIGS_SUFFIX = ".composed.json"


def _read_composed_sigs(path: Path) -> dict[int, str]:
    """读侧车文件 → ``{页号: 签名}``；缺失/损坏一律当空表（判据退回全量合成）。"""
    from desktop.store.json_io import read_json

    raw = read_json(path, {})
    pages = raw.get("pages") if isinstance(raw, dict) else None
    out: dict[int, str] = {}
    for key, value in (pages or {}).items():
        try:
            index = int(key)
        except (TypeError, ValueError):
            continue
        if isinstance(value, str):
            out[index] = value
    return out


def _write_composed_sigs(path: Path, sigs: dict[int, str]) -> None:
    """原子写侧车文件；目录已不存在（任务被删）时静默跳过，绝不重建目录。"""
    from desktop.store.json_io import write_json

    try:
        write_json(path, {"pages": {str(k): sigs[k] for k in sorted(sigs)}})
    except OSError:
        pass


#: 版面改动 → 后台重新合成落盘的**合并窗口**（同一轮事件循环里的多次排期只跑一次）。
#:
#: ⚠️ 用户 2026-10-18 的硬指标：「移动图片松鼠标，**1s 内**将当前图片更新到相应的
#: 实体图片上面」。这条是从"松鼠标"起算的第一段延迟，所以压到 **0**（= 下一个事件
#: 循环回合就跑）：
#:
#: - 拖动**只在松手时**发一次 ``items_changed``、旋转滑块也只在停顿后补发一次，
#:   没有"连续吐事件"要合并；
#: - 真正的合并由**单飞 + 补轮**机制保证（``_imposition_composing`` /
#:   ``_imposition_dirty``：正在跑的那轮结束再补一轮），不靠这个窗口；
#: - 一页合成实测 ~0.7s（源图 2480×3447 两张），加上 worker 启动 ≈0.8s；
#:   这条窗口只要还留着 250ms 就会顶到 1s 以上，所以它设 0。
COMPOSE_DEBOUNCE_MS = 0
#: 旋转组件（滑块/输入框）连续吐增量 → 停顿多久算"改完了"再统一落盘
EDIT_COMMIT_DEBOUNCE_MS = 250
#: 版面改动 → 左列**单页缩略图**重合成的防抖（用户 2026-10-09：拖动松手/
#: 面板调整/编辑回写之后几秒内，缩略图要跟上页面效果）。比合成防抖长
#: 一截：拖动中签名每帧都在变，等真的停手了再合成一次就够。
THUMB_REFRESH_DEBOUNCE_MS = 2000
#: 「生成PDF」前等后台拼版合成收敛的轮询间隔（ms）。轮询只查两个内存
#: 布尔（在飞/待合成），100ms 足够跟手，事件循环里的开销可忽略。
PRINT_WAIT_POLL_MS = 100


class ImpositionLayoutMixin:
    """拼版版面操作（模块二）：旋转/复位、版面落盘、防抖后台合成。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage 提供的属性（store/task_id/log_view/run_worker/window）
        # 与同级 Mixin 共享的基元（ImpositionBaseMixin 那一组）：本 Mixin 本体不
        # 持有，只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        log_view: Any  # 宿主 log_panel 里的 QTextEdit（.append 取用）
        run_worker: Callable[..., Any]
        window: Callable[[], Any]
        _toast: Callable[..., None]
        _imposition_pages: Callable[[], list]
        _imposition_doc: Callable[[], dict[str, Any]]
        _imposition_scope: Callable[[], dict]
        _imposition_output_dir: Callable[[], Any]
        _imposition_switch_state: Any  # 拼版启用开关控件
        _set_stage_status: Callable[..., None]
        _refresh_print_source: Callable[..., None]
        _save_imposition_pages: Callable[..., None]
        _on_page_image_saved: Callable[..., None]
        #: 同级 Mixin（imposition_pages）提供的页面缩略图实体管理者
        _imposition_page_thumb_manager: Callable[..., Any]
        _drop_imposition_source_thumb: Callable[[str], None]
        imposition_active: Callable[[], bool]
        imposition_effective: Callable[[], bool]
        imposition_has_pages: Callable[[], bool]

    # ------------------------------------------------------------- 版面操作
    def _on_imposition_whole_rotate(self, delta: float) -> None:
        """面板的**整版旋转**组件吐了增量：画布即时转，停顿后统一落盘。

        滑块拖动会连续吐增量（每格 0.5°），不能每格都走一遍
        ``set_page`` + 落盘 + 合成——``rotate_whole`` 只原地改 items 重绘
        （顺带把待落盘标脏），由 ``_imposition_edit_timer`` 在用户停手后
        统一 ``flush_pending``（→ items_changed → 落盘 + 防抖合成）。
        之前积压的任何未上报编辑也由这同一个计时器一并补发。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0 or not view.canvas.has_items():
            return
        view.canvas.rotate_whole(delta)
        self._start_imposition_edit_commit()

    def _on_imposition_item_rotate(self, angle: float) -> None:
        """面板的**选中图旋转**组件设了绝对角度：即时转，停顿后统一落盘。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        if view.selected_slot() < 0:
            return  # 组件没选中时本来就该禁用；防御一下
        view.canvas.set_item_rotation(angle)
        self._start_imposition_edit_commit()

    def _start_imposition_edit_commit(self) -> None:
        """旋转组件改了画布但还没上报：启动停顿计时器（没建就立刻兜底提交）。"""
        timer = getattr(self, "_imposition_edit_timer", None)
        if timer is None:
            view = getattr(self, "imposition_view", None)
            if view is not None:
                view.canvas.flush_pending()
            return
        timer.start()

    def _commit_imposition_edit(self) -> None:
        """旋转组件停顿到期：把画布上的改动补报出去 + 回填面板角度。"""
        view = getattr(self, "imposition_view", None)
        if view is None:
            return
        view.canvas.flush_pending()  # → items_changed → 落盘 + 防抖合成
        # 整版转过后外接框变了：重新适配可视区（拖动画布时有意不适配，这里
        # 是组件操作，落定后一次适配是期望行为）
        view.canvas.refit()
        self._sync_imposition_rotation_ui()

    def _sync_imposition_rotation_ui(self) -> None:
        """把画布当前的角度回填到面板旋转组件（整体=平均角，单图=选中角）。

        回填走 blockSignals 语义（panel 内部挡信号），不会把同步误当成用户
        输入再转一次。没有页时两组组件都禁用。
        """
        panel = getattr(self, "imposition_panel", None)
        view = getattr(self, "imposition_view", None)
        if panel is None or view is None:
            return
        canvas = view.canvas
        if view.current_index() < 0 or not canvas.has_items():
            panel.set_page_available(False)
            panel.set_whole_angle(0.0)
            panel.set_item_rotation(None)
            return
        panel.set_page_available(True)
        panel.set_whole_angle(canvas.spread_rotation() or 0.0)
        panel.set_item_rotation(
            canvas.selected_rotation()
            if canvas.selected() >= 0 else None
        )

    def _on_imposition_reset_layout(self) -> None:
        """把本页版面复位成**刚拼好时的样子**（两张并排、原始尺寸、无旋转）。

        没有纸张之后，"复位"只能以**两张图的原始尺寸**为基准：重新按
        ``default_items`` 摆一遍（右槽在左槽右边、顶部对齐）。这样用户把图拖得
        乱七八糟之后一键就能回到干净的并排版面。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            self._toast("info", "没有拼版页", "请先点左侧的拼版页，或添加一页拼版。")
            return
        view.flush_pending()
        index = view.current_index()
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = pages[index].get("items") or []
        files = [item.get("file") for item in items]
        # 单图页（整幅/落单）只有一项：复位 = 原始尺寸、归零位（没有"并排"）
        reset = single_items(files[0]) if len(files) == 1 else default_items(files)
        if reset is None:
            self._toast(
                "error", "无法复位",
                "读不到源图尺寸（文件可能已被移动或删除）。",
            )
            return
        pages[index] = {**pages[index], "items": reset}
        if not self.task_id:
            return
        scope = self._imposition_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["pages"] = pages
        self.store.save_imposition_doc(self.task_id, doc, **scope)
        view.update_current_items(reset)
        self._schedule_imposition_compose()
        self._schedule_imposition_page_thumb(index)
        self._update_imposition_status(index)
        self.log_view.append(f"第 {index + 1} 页拼版已复位为默认并排版面。")

    def _on_imposition_delete_item(self) -> None:
        """「删除选中图片」（面板）：把画布里选中的那张图从本页删掉。

        **页保留**——剩一张时面板会自动出现「新增图片」可以再补一张；**删到
        最后一张则整页移除**（空页没有意义，与左列「✕」释放同款语义——全部
        页删光后拼版**仍然启用**，只是没有可拼的图，第四步会提示先去拼版；
        2026-09-30 用户定：整页移除前要弹确认框）。被删的图不再被任何页引用，
        即自动回到「未选择列表」（下次「选择拼版」或「新增图片」都能再选它）。
        落盘走 ``_save_imposition_pages``：画布重灌会清空选中，「当前图片样式」
        区随之灰掉。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            self._toast("info", "没有拼版页", "请先点左侧的拼版页，或添加一页拼版。")
            return
        view.flush_pending()
        index = view.current_index()
        slot = view.selected_slot()
        if slot < 0:
            self._toast("info", "没有选中的图片", "先在画布里点选要删除的图片。")
            return
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        items = [dict(item) for item in pages[index].get("items") or []]
        if not 0 <= slot < len(items):
            return
        removed = items.pop(slot)
        if not items:
            # 本页最后一张：页会跟着一起删（2026-09-30 用户定：要确认）。
            # 此刻还没动任何状态（items 是副本），取消直接返回即可。
            from qfluentwidgets import Dialog

            dialog = Dialog(
                "删除图片",
                f"「{Path(removed['file']).stem}」是本页最后一张图片，"
                "删除后整页拼版将一并移除。\n是否继续？",
                self.window(),
            )
            dialog.yesButton.setText("删除")
            dialog.cancelButton.setText("取消")
            if not dialog.exec():
                return
        if items:
            pages[index] = {**pages[index], "items": items}
        else:
            # 单图页删掉最后一张：页一并删除（空页没有意义），与左列
            # 「✕」释放同款语义——拼版仍处于**启用**态，只是没有可拼的图了
            pages.pop(index)
        self._save_imposition_pages(pages)
        view.set_current(min(index, len(pages) - 1))
        self._update_imposition_status(
            view.current_index() if view is not None else -1
        )
        if items:
            self.log_view.append(
                f"已删除{cn_page_label(index)}选中的图片"
                f"「{Path(removed['file']).stem}」，回到未选择列表。"
            )
        else:
            self.log_view.append(
                f"已删除{cn_page_label(index)}最后一张图片"
                f"「{Path(removed['file']).stem}」，本页没有图了，整页移除"
                f"（源图回到未选择列表）。"
            )

    # ------------------------------------------------------------- 双击预览
    def _open_imposition_item_preview(self, _slot: int) -> None:
        """画布右键「预览图片」：预览**本页拼版后的图片**（整页成品组合）。

        用户 2026-10-18：拼版这一步的"图片"是**拼版后的图片**（会实时重合成
        产出新图），不是画布上那张输入源图；「编辑图片」才是作用于两张源图
        （编辑后重新合成，保持不变）。
        """
        self._open_imposition_spread_preview()

    def _open_imposition_spread_preview(self) -> None:
        """画布**双击空白处/右键图片「预览图片」**：预览整页左右组合（按产出口径）。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        current = view.current_index()
        self._open_imposition_zoom(
            lambda _index: self._imposition_spread_target(current), 0
        )

    def _open_imposition_zoom(self, factory, index: int) -> None:
        """打开（或复用）拼版预览弹窗；开头没有可预览的页就静默返回。"""
        from desktop.components.viewers.image_zoom_dialog import ImageZoomDialog

        if factory(index) is None:
            return
        if getattr(self, "_imposition_zoom_dialog", None) is None:
            self._imposition_zoom_dialog = dialog = ImageZoomDialog(
                self.window() or self, factory=factory
            )
            # 弹窗里「编辑」覆盖了真实文件 → 生效链（与各步骤预览区同一套）
            dialog.image_saved.connect(self._on_imposition_zoom_image_saved)
        dialog = self._imposition_zoom_dialog
        # 先 show 再 show_for：视口有了真实尺寸，渲染密度才算得准
        # （ImageZoomDialog 渲染走自己的 worker 线程，不占界面）
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        dialog.show_for(factory=factory, index=index)

    def _imposition_locate_targets(self, _slot: int) -> list[Path]:
        """画布右键「定位图片资源」的落点：**本页拼版成品** → **本节点成品目录**。

        用户 2026-10-18：拼版这一步的"图片资源"是**拼版后的图片**——它由合成
        worker 实时重合成，产出的是 ``stages/imposition[~<节点>]/NNNN.png``；
        画布上那张是**输入源图**（如 ``stages/input``），不是这一步的产物，不能
        拿它当「定位图片资源」的目标（其他步骤定位到自己的输入图是合理的，拼版
        不是）。

        成品页还没合成出来时退到**成品目录**，让用户至少到"这一批产物跟前"；
        两者都不在时由画布按"定位失败"说明原因（不静默）。

        ⚠️ ``_slot`` 只是画布解析器契约的形参（``(index) -> list[Path]``）：
        目标是**整页成品**，与右键的是哪一张子图无关。
        """
        view = getattr(self, "imposition_view", None)
        if view is None or not getattr(self, "task_id", None):
            return []
        output = self._imposition_output_dir()
        if not output.parts:
            return []
        index = view.current_index()
        targets: list[Path] = []
        pages = self._imposition_pages()
        if 0 <= index < len(pages):
            targets.append(product_path(output, index, pages[index]))
        targets.append(output)
        return targets

    def _imposition_spread_target(self, page_index: int) -> "object | None":
        """弹窗「整页左右组合」来源：构造时快照版面，合成在 worker 线程。"""
        from desktop.workers import ImpositionPagePreviewWorker
        from desktop.components.viewers.image_zoom_dialog import ZoomTarget

        pages = self._imposition_pages()
        if not 0 <= page_index < len(pages):
            return None
        items = [dict(item) for item in pages[page_index].get("items") or []]
        if not items:
            return None
        stems = page_source_stems(pages[page_index])
        right = stems[0] if stems else ""
        left = stems[1] if len(stems) > 1 else ""
        edit_path = None
        task_id = getattr(self, "task_id", None)
        output = product_path(
            self._imposition_output_dir(), page_index, pages[page_index]
        )
        if task_id and not getattr(self, "_imposition_dirty", False) and output.is_file():
            edit_path = output
        # ⚠️ 定位**独立于编辑**：整页组合是虚拟图（合成物），
        #    - 成品已落盘 → 定位成品页（这就是这一页产出的那个文件）；
        #    - 还没合成/有未落盘改动 → 退到**源图所在目录**，让用户至少能到
        #      那一批源图跟前；都没有就不给菜单（不弹死按钮）。
        locate_path = None
        if output.is_file():
            locate_path = output
        else:
            first = Path(str(items[0].get("file") or ""))
            if first.parent.is_dir():
                locate_path = first.parent
        return ZoomTarget(
            render=lambda edge,
            page={"items": items}: ImpositionPagePreviewWorker(page, edge),
            note=f"{cn_page_label(page_index)} 左右组合（左「{left}」+ 右「{right}」）",
            stem=f"imposition-{page_index + 1:02d}",
            count=1,
            save_path=edit_path,
            edit_path=edit_path,
            locate_path=locate_path,
            edit_label="编辑图片",
            show_text_tool=False,
        )

    def close_imposition_zoom_popup(self) -> None:
        """关掉拼版预览弹窗（内容失效时调：切任务等）。"""
        dialog = getattr(self, "_imposition_zoom_dialog", None)
        if dialog is not None:
            dialog.close()

    # ------------------------------------------------------------- 右键直接编辑
    def _on_imposition_source_edited(self, path_text: str, edited) -> None:
        """拼版源图被覆盖（画布右键或预览弹窗）：统一的生效链。

        ① 画布丢掉这张图的解码缓存并重绘；② **左列该页的缩略图**也要丢掉
        重渲（它按路径缓存在内存里，不清就永远停在旧图——用户 2026-10-08
        报"预览弹窗里编辑完，拼版页还是老图"就是漏了这一步）；③ 主页面
        ``_on_page_image_saved`` 刷新各查看器（rembg 输出无坐标基准，走其
        "按文件刷新"分支）；④ 重新防抖合成——拼版成品里嵌着这张源图，
        不重合成就白改了。
        """
        view = getattr(self, "imposition_view", None)
        if view is not None:
            view.canvas.invalidate_image(path_text)
        # ⚠️⚠️ 源图尺寸可能变了（编辑器里旋转/裁剪后覆盖回**同一文件**）：
        #    版面 rect 是按旧图尺寸记的，不刷新的话 compose_page 会把新图
        #    硬 resize 回旧宽高 ⇒ 旋转 90° 的图被横向压扁（形变 + 清晰度
        #    下降，用户 2026-10-10 报障）。先把引用它的 rect 刷成新尺寸
        #    （绕中心保持位置）并落盘，缩略图/画布/重合成用的才是新几何。
        pages = self._imposition_pages()
        if refresh_rects_for_edited_source({"pages": pages}, path_text):
            self._save_imposition_pages(pages)
        self._drop_imposition_source_thumb(path_text)
        self._on_page_image_saved(path_text, edited)
        self._schedule_imposition_compose()
        self.log_view.append(
            f"已编辑拼版源图「{Path(path_text).stem}」并覆盖原图"
            f"（{edited.width()}×{edited.height()} px），拼版成品将重新合成。"
        )

    def _open_imposition_spread_edit(self) -> None:
        """「编辑图片」：同一画布显示整页源图并切换活动图片。"""
        view = getattr(self, "imposition_view", None)
        if view is None or view.current_index() < 0:
            return
        view.flush_pending()  # 拖住没松手的改动先落定，快照才是最新的
        items = [dict(item) for item in view.current_items()]
        if not items:
            return
        from PySide6.QtGui import QImage
        from desktop.components.viewers.image_editor import ImageEditorDialog

        for item in items:
            path = Path(str(item.get("file") or ""))
            image = QImage(str(path)) if path.is_file() else QImage()
            if image.isNull():
                self._toast(
                    "warning", "无法编辑",
                    f"读不到拼版源图：{path.name}（文件可能已被移动或删除）。",
                )
                return
            item["image"] = image

        editor = ImageEditorDialog(
            self.window() or self, items[0]["image"], save_back=True,
        )
        set_tool_visible = getattr(editor, "set_tool_visible", None)
        if callable(set_tool_visible):
            set_tool_visible("text", False)
        editor.configure_multiple_images(items)
        editor.multi_image_saved.connect(self._on_imposition_source_edited)
        page_index = view.current_index()
        editor.multi_layout_saved.connect(
            lambda updates, index=page_index:
                self._on_imposition_spread_layout_saved(index, updates)
        )
        editor.exec()
        editor.release_buffers()

    def _on_imposition_spread_layout_saved(
        self, page_index: int, updates: list[dict],
    ) -> None:
        """把编辑弹窗中的双图相对位置/尺寸保存回任务版面。"""
        pages = self._imposition_pages()
        if not 0 <= page_index < len(pages):
            return
        items = pages[page_index].get("items") or []
        if apply_editor_layout(items, updates):
            self._save_imposition_pages(pages)

    def _on_imposition_zoom_image_saved(self, path_text: str,
                                        image=None) -> None:
        """预览弹窗里「编辑」覆盖了真实文件（``image_saved``）：按落点接链。

        回写目标由 ``ZoomTarget.edit_path`` 给（2026-10-07 用户定：预览弹窗里
        的编辑也要生效）——落点只有两种：

        - **拼版成品**（整页组合编辑）：挂着的防抖合成必须取消（定时器停 +
          清脏标记），否则旧合成跑完会把刚覆盖的手改冲掉；版面没变不需要
          再合成，刷新打印源即可。与画布右键空白编辑同一套善后。
        - **拼版源图**（单张原图编辑）：走 :meth:`_on_imposition_source_edited`
          与画布右键完全相同的生效链。
        """
        if image is None or image.isNull():
            return
        path = Path(path_text)
        task_id = getattr(self, "task_id", None)
        if task_id and path.parent == self._imposition_output_dir():
            timer = getattr(self, "_imposition_timer", None)
            if timer is not None:
                timer.stop()
            self._imposition_dirty = False
            self._refresh_print_source()
            self.log_view.append(
                f"已编辑整页组合并覆盖拼版成品「{path.name}」"
                f"（{image.width()}×{image.height()} px，PDF排版用这张）；"
                "再次调整该页版面会重新合成、覆盖这次编辑。"
            )
            return
        self._on_imposition_source_edited(path_text, image)

    # ------------------------------------------------------------- 版面落盘
    def _on_imposition_slot_selected(self, _slot: int) -> None:
        """画布里选中了右槽/左槽/无：刷新状态行。"""
        view = getattr(self, "imposition_view", None)
        if view is not None:
            self._update_imposition_status(view.current_index())

    def _on_imposition_items_changed(self, index: int, items: list) -> None:
        """版面被拖动/缩放/旋转：落盘 + 重新合成（防抖）。"""
        pages = self._imposition_pages()
        if not 0 <= index < len(pages):
            return
        pages[index] = {**pages[index], "items": [dict(item) for item in items]}
        if not self.task_id:
            return
        scope = self._imposition_scope()
        doc = self.store.load_imposition_doc(self.task_id, **scope)
        doc["pages"] = pages
        self.store.save_imposition_doc(self.task_id, doc, **scope)
        self._schedule_imposition_compose()
        self._schedule_imposition_page_thumb(index)
        self._update_imposition_status(index)

    def _update_imposition_status(self, index: int) -> None:
        """状态行：当前页 + 选中槽位 + 生效与否。"""
        label = getattr(self, "imposition_panel_status", None)
        if label is None:
            return
        pages = self._imposition_pages()
        # 「新增图片」只在单图页出现（2026-09-30 用户定）——面板按钮显隐
        # 搭状态行这趟车一起同步（状态行是"当前页变了"的汇聚点）
        panel = getattr(self, "imposition_panel", None)
        if panel is not None:
            single = (
                0 <= index < len(pages)
                and len(pages[index].get("items") or []) == 1
            )
            panel.set_single_page(single)
        if not pages:
            text = "尚未添加拼版页"
        else:
            view = getattr(self, "imposition_view", None)
            slot = view.selected_slot() if view is not None else -1
            slot_text = {0: "（选中：右侧）", 1: "（选中：左侧）"}.get(slot, "")
            text = f"{cn_page_label(index)} / 共 {len(pages)} 页{slot_text}"
        # ⚠️ 四态措辞：**启用**决定取图来源，**有没有页**决定能不能真出东西。
        # 「已启用但一页都没拼」是最容易让人以为"没生效"的一档——必须把话说
        # 死：流程确实已经改走拼版了，只是还没有可拼的图。
        _usable, _reason = self._imposition_switch_state()
        if self.imposition_active() and not self.imposition_effective():
            # ⚠️ 中间档：用户**勾了**但这一步现在用不上（区域模式不支持等）。
            #    只说"已启用"会与实际取图矛盾，只说"未启用"又会让用户怀疑
            #    "我明明勾了"——所以把原因原样说出来。
            text += f"　·　已勾选但当前用不上：{_reason}"
        elif self.imposition_effective():
            text += (
                "　·　拼版已启用：PDF排版用拼版结果"
                if pages
                else "　·　拼版已启用，但还没有拼版页——"
                     "请先「选择拼版」，否则 PDF排版没有输入"
            )
        elif pages:
            text += "　·　拼版未启用：勾选下方开关后 PDF排版 才会用拼版结果"
        label.setText(text)
        # 状态行是所有"当前页/选中变了"路径的汇聚点，旋转组件的回填搭这趟车
        self._sync_imposition_rotation_ui()

    # ------------------------------------------------------------- 合成落盘
    def _schedule_imposition_page_thumb(self, index: int) -> None:
        """版面改动 → 防抖后**只重合成这一页**的左列缩略图（用户 2026-10-09）。

        拖动/缩放/旋转/复位落盘后，左列那条缩略图还是旧版面——攒下页号、
        停手 :data:`THUMB_REFRESH_DEBOUNCE_MS` 后单页重合成（memo 判据：
        版面没真变就原样回缓存里的同一张，不白跑）。页数增删/排序走
        ``_save_imposition_pages`` → ``_refresh_imposition_page_thumbs``
        的整列刷新，不经这里。
        """
        dirty = getattr(self, "_imposition_thumb_dirty", None)
        if dirty is None:
            dirty = self._imposition_thumb_dirty = set()
        dirty.add(int(index))
        timer = getattr(self, "_imposition_thumb_timer", None)
        if timer is not None:
            timer.start()

    def _refresh_imposition_dirty_page_thumbs(self) -> None:
        """防抖到期：把攒下的那几页**单页**重生成缩略图实体并贴回左列。"""
        view = getattr(self, "imposition_view", None)
        dirty = getattr(self, "_imposition_thumb_dirty", None)
        if view is None or not dirty:
            return
        self._imposition_thumb_dirty = set()
        pages = self._imposition_pages()
        manager = self._imposition_page_thumb_manager()
        if manager is not None:
            manager.invalidate(sorted(dirty), pages)

    def _schedule_imposition_compose(self) -> None:
        """版面/页数变化 → 防抖后**后台**把拼版页重写到 stages/imposition。"""
        if not getattr(self, "task_id", None):
            return
        self._imposition_dirty = True
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            timer.start()
        else:
            # 定时器还没建（视图未初始化）：直接同步兜底，别让改动悬着
            self._compose_imposition_now()

    def _init_imposition_compose(self) -> None:
        """建防抖定时器（页面构造期一次）。"""
        self._imposition_dirty = False
        self._imposition_composing = False
        #: **页号 → 上次落盘时的内容签名**（``page_thumb.page_signature``）。
        #: 版面只动一页时靠它算出"只有这一页要重合成"（用户 2026-10-18：
        #: 「不是所有图片都重新存储一份，只存储当前拼版的图片页」）。真正的基线
        #: 存在**侧车文件**里（见 ``_composed_sigs``，跨会话有效）；这个属性只是
        #: "当前节点那一份"的引用，供自测/排查观察。
        self._imposition_page_sigs: dict[int, str] = {}
        #: 侧车签名表的**按路径缓存**（``{侧车文件路径: {页号: 签名}}``）：切节点/
        #: 切任务只换 key，不重读盘。
        self._composed_sigs_cache: dict[str, dict[int, str]] = {}
        #: 本轮合成用的是**哪份文档快照 / 哪张目录 / 哪份记录 / 正在写哪几页**
        #: （收尾时据此记签名、算"这次重存了哪几张图片"并通知第四步）
        self._imposition_compose_doc: dict | None = None
        self._imposition_compose_out_dir: Path | None = None
        self._imposition_compose_sigs_path: Path | None = None
        self._imposition_compose_doc_path: Path | None = None
        self._imposition_compose_doc_mtime: float | None = None
        self._imposition_composed_pages: list[int] = []
        # ⚠️ Mixin 本体是普通类，类型检查器看不到宿主（TaskDetailPage）是 QWidget，
        #    故把 self 收窄成 QWidget 再当 QTimer 的 parent 用；运行时是恒等。
        self._imposition_timer = QTimer(cast(QWidget, self))
        self._imposition_timer.setSingleShot(True)
        self._imposition_timer.setInterval(COMPOSE_DEBOUNCE_MS)
        self._imposition_timer.timeout.connect(self._compose_imposition_async)
        # 旋转组件的停顿提交计时器（滑块连续吐增量期间只转画布，停手才落盘）
        self._imposition_edit_timer = QTimer(cast(QWidget, self))
        self._imposition_edit_timer.setSingleShot(True)
        self._imposition_edit_timer.setInterval(EDIT_COMMIT_DEBOUNCE_MS)
        self._imposition_edit_timer.timeout.connect(self._commit_imposition_edit)
        # 左列单页缩略图的重合成计时器（版面停手后几秒内跟上页面效果）
        self._imposition_thumb_dirty: set[int] = set()
        self._imposition_thumb_timer = QTimer(cast(QWidget, self))
        self._imposition_thumb_timer.setSingleShot(True)
        self._imposition_thumb_timer.setInterval(THUMB_REFRESH_DEBOUNCE_MS)
        self._imposition_thumb_timer.timeout.connect(
            self._refresh_imposition_dirty_page_thumbs
        )

    def _composed_sigs_path(self) -> Path | None:
        """当前拼版节点的「已落盘签名」侧车文件路径（与版面草稿同目录同作用域）。"""
        if not self.task_id:
            return None
        doc = self.store.imposition_doc_path(self.task_id, **self._imposition_scope())
        return doc.with_name(doc.stem + COMPOSED_SIGS_SUFFIX)

    def _composed_sigs(self, path: Path | None = None) -> dict[int, str]:
        """**某个**侧车文件的签名表（缺省 = 当前节点）；按路径缓存，切节点自动换一份。

        ⚠️ 缓存是必须的：本方法在"每次版面改动判过期"路上被调，每调一次读盘
        （几十 KB JSON）就白搭了；而**按路径**缓存又让同一步骤的多个拼版节点
        各拿各的记录（互不串味）。
        """
        target = self._composed_sigs_path() if path is None else path
        if target is None:
            return {}
        cache = getattr(self, "_composed_sigs_cache", None)
        if cache is None:
            cache = self._composed_sigs_cache = {}
        key = str(target)
        mapping = cache.get(key)
        if mapping is None:
            mapping = _read_composed_sigs(Path(target))
            cache[key] = mapping
        # 顺手暴露给自测/排查（"当前节点记了哪些页"）
        self._imposition_page_sigs = mapping
        return mapping

    def _stale_imposition_pages(self) -> list[int]:
        """本次**要重合成的页号**（0 基）：与上次落盘时的内容签名逐页比对。

        签名规则复用缩略图实体那一套（``components.imposition.page_thumb
        .page_signature``：版面 rect/rotation + 每张源图的 (大小, mtime)），所以
        "源图被覆盖"同样会被算成一页要重合成。

        基线来自**侧车文件**（:meth:`_composed_sigs`），因此跨会话也有效——
        这是用户 2026-10-18「不应该是只改变一张图片吗」的关键：内存基线一重启
        就没了，只能整本全量重合成。没有记录的页仍算过期（首次/换任务/记录被清）。
        """
        from desktop.components.imposition.page_thumb import page_signature

        pages = self._imposition_pages()
        recorded = self._composed_sigs()
        return [
            index for index, page in enumerate(pages)
            # ⚠️ ``page_signature`` 对**空页**返回 None：统一折成空串再比，
            #    免得"没签名"与"签名是 None"两种都算过期、反复重合成同一页。
            if (page_signature(page) or "") != recorded.get(index, "")
        ]

    def _compose_imposition_async(self, force_full: bool = False) -> None:
        """后台合成（不阻塞界面）：拖动版面时会被反复触发。

        ``force_full=True``：无视签名记录整本重合成（点「生成PDF」前的兜底用
        ——那边要的是"磁盘一定与落盘版面一致"，不必省这几秒）。
        默认走**增量**：只重写"内容签名变了"的那几页（用户 2026-10-18：
        「不是所有图片都重新存储一份，只存储当前拼版的图片页」）。
        """
        if not self.task_id:
            return
        if self._imposition_composing:
            return  # 上一批还在跑；跑完会看 _imposition_dirty 再补一次
        doc = self._imposition_doc()
        out_dir = self._imposition_output_dir()
        only = None if force_full else self._stale_imposition_pages()
        # ⚠️ **``only=[]``（一页都没变）也要真跑一轮**：它一页都不重合成，但
        #    ``compose_doc`` 收尾的**清扫**（删掉多出来的页号 / 别的后缀）必须执行
        #    ——"用户清空拼版页、删掉后面几页"时，若因为"没有页要重写"就整个跳过，
        #    上一轮的成品会留在盘上，第四步照旧把旧图打进 PDF。这一轮的代价只是
        #    一次目录清扫，零次图片合成。
        page_count = len(doc.get("pages") or [])
        if force_full or only is None:
            order = list(range(page_count))
        else:
            order = sorted(only)
        # ⚠️ 把**用户正看着的那一页排在最前**（用户 2026-10-18：「移动图片松鼠标，
        #    1s 内将当前图片更新到实体图片上」）：全量那一轮（首次还没有"已落盘
        #    记录"时）也是先写他改的那页，不必等整本跑完。
        view = getattr(self, "imposition_view", None)
        current = view.current_index() if view is not None else -1
        if 0 <= current < page_count and current in order and order[0] != current:
            order.remove(current)
            order.insert(0, current)
        self._imposition_dirty = False
        self._imposition_composing = True
        self._imposition_compose_doc = doc
        # ⚠️ **连"这次是哪张目录/哪份记录/哪份快照"一起记下**：合成在后台跑，期间
        #    用户可能切到同一步骤的另一个拼版节点去了——收尾时若现查当前节点，会把
        #    记录与确认写进**别人**的目录/侧车文件（成品落点也就跟着错了）。
        self._imposition_compose_out_dir = out_dir
        self._imposition_compose_sigs_path = self._composed_sigs_path()
        self._imposition_compose_doc_path = self.store.imposition_doc_path(
            self.task_id, **self._imposition_scope()
        )
        # ⚠️ 记的是**这次合成所用快照**对应的文档 mtime，而不是收尾那一刻的实时
        #    mtime：合成跑着用户又改一版时，文档 mtime 会往前跳，拿它当基准会把
        #    已经写好的前几页误判成"没写成功"→ 再排一轮重写（用户 2026-10-18 实测：
        #    先重存了 77 页、紧接着又重存 8 页，那一轮白跑还让他等更久）。
        try:
            self._imposition_compose_doc_mtime = (
                self._imposition_compose_doc_path.stat().st_mtime
            )
        except OSError:
            self._imposition_compose_doc_mtime = None
        self._imposition_composed_pages = list(order)
        from desktop.workers import ImpositionComposeWorker, connect_queued

        self.run_worker(
            # 成品后缀随**该页源图**走（用户 2026-10-17）：输入 png 出 png、
            # 输入 jpg 出 jpg（同一目录里两种后缀可以并存）
            lambda: ImpositionComposeWorker(
                doc, out_dir, suffix_for=page_product_suffix, only=only,
            ),
            lambda worker, thread: (
                connect_queued(
                    self, worker.finished, self._on_imposition_composed, thread
                ),
                connect_queued(
                    self, worker.failed, self._on_imposition_compose_failed, thread
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _record_composed_pages(self) -> None:
        """合成收尾：记下"这次重存了哪几页"、更新签名、通知第四步。

        - **签名**（``_imposition_page_sigs``）：下次只重合成又变了的那几页；
        - **记录**：日志写明重存了哪几页（用户 2026-10-18："那张图片变更，就重新
          存储哪个图片，同时通知下一步要变更的图片"）；
        - **通知下游**：只刷那几页在第四步的条目（见 ``_refresh_print_source``）。

        ⚠️ 每页再核一次"成品确实比版面文档新"才记签名：写盘失败/进程被杀的那页
        不记 —— 下次它还会被算成过期而重试（自愈），不会悄悄留着旧图。
        """
        sigs_path = getattr(self, "_imposition_compose_sigs_path", None)
        out_dir = getattr(self, "_imposition_compose_out_dir", None)
        pages = (self._imposition_compose_doc or {}).get("pages") or []
        indexes = list(getattr(self, "_imposition_composed_pages", None) or [])
        self._imposition_composed_pages = []
        if not indexes or sigs_path is None or out_dir is None:
            return
        try:
            doc_mtime = getattr(self, "_imposition_compose_doc_mtime", None)
        except AttributeError:
            doc_mtime = None
        from desktop.components.imposition.page_thumb import page_signature
        from desktop.services.imposition import product_path

        sigs = self._composed_sigs(sigs_path)
        changed: list[int] = []
        for index in indexes:
            if not 0 <= index < len(pages):
                continue
            page = pages[index]
            if doc_mtime is not None:
                try:
                    if product_path(out_dir, index, page).stat().st_mtime < doc_mtime:
                        continue  # 这一页这次没写成功 → 不记签名，下轮重试
                except OSError:
                    continue
            sigs[index] = page_signature(page) or ""
            changed.append(index)
        if not changed:
            return
        _write_composed_sigs(Path(sigs_path), sigs)
        labels = "、".join(f"第 {i + 1} 页" for i in changed[:6])
        if len(changed) > 6:
            labels += f" 等 {len(changed)} 页"
        self.log_view.append(
            f"拼版成品已重存 {len(changed)} 页（{labels}），"
            "这几张图在第四步会按当前排版参数重新排版。"
        )
        self._refresh_print_source([
            str(product_path(out_dir, index, pages[index])) for index in changed
        ])

    def _on_imposition_composed(self, _out_dir: str, _count: int) -> None:
        """后台合成完成（主线程）：解除忙标记，记签名/通知下游，必要时补一轮。"""
        self._imposition_composing = False
        self._record_composed_pages()
        if self._imposition_dirty:
            self._imposition_timer.start()
            return
        self._refresh_print_source()

    def _on_imposition_compose_failed(self, message: str) -> None:
        self._imposition_composing = False
        self.log_view.append(f"拼版合成失败：{message}")
        self._toast("error", "拼版合成失败", message)

    def _imposition_products_fresh(self) -> bool:
        """stages/imposition 的成品是否已覆盖**落盘版面**（mtime + 页数，不解码）。

        「点生成PDF先同步合成」的**快路径判据**（2026-10-12，用户报障
        「点生成PDF后界面立刻冻结」）：用两个便宜的磁盘事实回答"还要不要
        合成"，避免每次点击都全量重合成——

        - **页数**：``NNNN.png`` 的个数 == 文档页数（compose_doc 收尾会清掉
          多余编号；页数不符 = 有增删还没合出来）；
        - **新旧**：成品里**最旧**一张的 mtime ≥ 拼版文档的 mtime。编辑总是
          先落文档、再防抖合成，文档比成品新 = 有改动还没合出来。

        ⚠️ 只回答**磁盘**问题，刻意不看 `_imposition_dirty` /
        `_imposition_composing` 这两个内存态：跨会话的陈旧（上次编辑后进程
        被杀、防抖合成没跑成）只有磁盘对比能兜住——快路径靠它兜底，后续
        改动别把"无条件全量合成"加回来。
        """
        if not self.task_id:
            return True
        pages = self._imposition_pages()
        if not pages:
            return True
        out_dir = self._imposition_output_dir()
        if not out_dir.is_dir():
            return False
        products = [
            entry for entry in out_dir.iterdir() if is_product_file(entry)
        ]
        if len(products) != len(pages):
            return False
        try:
            # ⚠️ 比对的是**本节点**的版面文档（B 方案）：比错了文件会让"成品
            #    是否最新"永远说不准（一个节点改版面、另一个节点误判新鲜）。
            doc_mtime = self.store.imposition_doc_path(
                self.task_id, **self._imposition_scope()
            ).stat().st_mtime
            oldest = min(entry.stat().st_mtime for entry in products)
        except OSError:
            # 读不到（任务目录被删/竞态）就当不新鲜：重合成一遍无害
            return False
        return oldest >= doc_mtime

    def _compose_imposition_now(self) -> None:
        """点「生成PDF」前保证 stages/imposition 是**最新版面**。

        2026-10-12 改造（用户报障「点生成PDF后界面立刻冻结」，拼版生效时）：
        旧版在这里**无条件**把全部拼版页同步重合成一遍（加载原图→缩放→
        旋转→alpha 合成→整页 PNG 编码，全在 GUI 主线程），几百页的书每次
        点击都冻结几十秒——而绝大多数点击时版面根本没改过。现在分三层：

        1. **磁盘新鲜度快路径**（`_imposition_products_fresh`）：成品已覆盖
           落盘版面 → 一个字节都不碰，立即返回（常见情形，零开销）；
        2. 拼版未生效 → 直接返回（第四步根本不读拼版目录，合成了也白合；
           重新启用时 `_set_imposition_checked` 会重新调度合成）；
        3. 真要合成 → **后台线程**合成（复用 `_compose_imposition_async` 的
           单飞/补轮机制），主线程用 QEventLoop 等收敛——界面保持响应
           （能看日志、滚动界面），执行权仍在 run_stage 手里（按钮已置灰，
           不会重入）。

        ⚠️ 前置条件含 `imposition_has_pages()`：一页都没拼时没有版面可合成
        （真正的拦路在第四步：列表为空 → 点「生成PDF」会明确提示去拼版）。
        ⚠️ 等待期间用户再改版面：`_on_imposition_composed` 的补轮机制会再排
        一轮，本循环等到"无在飞、无待合成"才放行；等待期间切走任务则立即
        放手（磁盘与内存状态由 `_reset_imposition_state` 复位）。
        ⚠️ 合成失败不拦住后续（与旧版同口径）：`_on_imposition_compose_failed`
        会弹 toast，这里把"PDF 按现有成品继续"说进日志。
        """
        if not self.task_id or not self.imposition_has_pages():
            return
        if not self.imposition_effective():
            return
        if self._imposition_products_fresh():
            self._imposition_dirty = False
            return
        owner_task = self.task_id
        self.log_view.append(
            "拼版版面有更新：正在后台合成（界面不阻塞），完成后继续生成PDF…"
        )
        try:
            self._set_stage_status("正在合成最新拼版页…")
        except Exception:  # noqa: BLE001 - 状态行只是提示，不该拖垮流程
            pass
        timer = getattr(self, "_imposition_timer", None)
        if timer is not None:
            # 防抖别再插队：改动已落盘，直接走单飞的异步合成
            timer.stop()
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        poll = QTimer(cast(QWidget, self))
        poll.setInterval(PRINT_WAIT_POLL_MS)

        def _settled() -> None:
            """收敛判据：没有在飞合成、没有待合成的改动（或任务已切走）。"""
            if self.task_id != owner_task or (
                not self._imposition_composing and not self._imposition_dirty
            ):
                loop.quit()

        poll.timeout.connect(_settled)
        poll.start()
        try:
            # ⚠️ 这一条**整本重合成**（``force_full``）：它要的是"磁盘一定与落盘
            #    版面一致"，而签名记录是内存态的、可能不准（跨会话/写盘失败），
            #    宁可多花几秒也不能把一页旧图打进 PDF。拖版面的后台那条走增量。
            self._compose_imposition_async(force_full=True)
            # ⚠️ 事件循环里界面照常收事件（这正是"不冻结"的实现方式）；
            #    期间用户改版面 → 补轮机制再排合成 → 下一轮收敛才放行。
            loop.exec()
        finally:
            poll.stop()
        if self.task_id != owner_task:
            # 等待期间切了任务：内存态已被 _reset_imposition_state 复位，
            # 旧任务的合成自会收尾，这里什么都不补。
            return
        self._imposition_dirty = False
        if not self._imposition_products_fresh():
            self.log_view.append("⚠️ 拼版合成未完成，PDF 将按现有成品页继续。")
