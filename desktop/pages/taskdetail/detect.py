# -*- coding: utf-8 -*-
"""任务详情页的 detect 检测控制器。

框坐标持久化在任务目录的 `boxes.json`（键为页面 stem）：
- 选中图片时优先读已有结果（命中则不再检测，手动框不被自动结果覆盖）；
- 子进程检测到的框写回（origin=auto）；
- 预览区拖动线框后写回（origin=manual），全程不生成新文件。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, cast

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QSize
from PySide6.QtGui import QImageReader
from PIL import Image

from desktop.components.box_kinds import BoxKindEditor
from desktop.components.yolo_export_dialog import ask_yolo_export
from desktop.services.detect_export import export_yolo, yolo_entries
from desktop.settings.config import app_config
from desktop.steps import StepKernel, StepRequest, callable_job
from utils.book_layout import (
    is_single_wide_half, profile_book, single_column_summary, suspicious_summary,
)
from utils.box_geometry import (
    classify_page_slots,
    compute_final_boxes,
    half_slots,
    is_full_content,
    present_boxes,
)
from desktop.store.json_io import write_json
from desktop.utils.files import project_root, reveal_dir

if TYPE_CHECKING:
    from PySide6.QtWidgets import QTextEdit, QWidget
    from desktop.components.viewers import ImageViewerWidget, RembgPreviewWidget
    from desktop.store.store import TaskStore

#: 信息条尾注：按本次框的来源（origin）标注。⚠️ `_apply_boxes` 与
#: `_show_boxes_info` 必须共用这一份——apply_boxes 的 info_text 也会写
#: 信息条，两处后缀不一致时后写的会覆盖先写的（曾丢过「（手动）」标记）。
ORIGIN_SUFFIX = {
    "manual": "（手动）",
    "auto": "",
    "fullpage": "（整页，未检测）",
}


class VersionedBoxCache(dict):
    """``detect_cache`` 的带版本号版：任何写入都自增 ``version``。

    给"整书判据"（单栏书结论 / 逐页检测框）做缓存失效用——那些判据要遍历
    全部页并读 ``boxes.json``，不能每次重算。用户在第二步改框会写这份缓存
    ⇒ 版本号自增 ⇒ 判据缓存失效，不会拿旧框去命名产物。
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.version = 0

    def __setitem__(self, key, value) -> None:  # noqa: ANN001
        super().__setitem__(key, value)
        self.version += 1

    def __delitem__(self, key) -> None:  # noqa: ANN001
        super().__delitem__(key)
        self.version += 1

    def clear(self) -> None:
        super().clear()
        self.version += 1


class DetectMixin:
    """依赖宿主页面提供的属性：store/task_id、detect_viewer、log_view、
    detect_process/detect_cache、current_stage()。"""

    if TYPE_CHECKING:
        # 宿主 TaskDetailPage（或同级 Mixin）提供的属性/方法：Mixin 本体不持有，
        # 这里只做类型声明（类级注解、无赋值），运行时零副作用。
        store: TaskStore
        task_id: str | None
        #: 任务源文件路径（空壳任务为 None）——导出时写进切片的 ``data.json``
        source_path: Path | None
        # 缓存值可能是槽位列表、也可能被置 None（防重复派发），用宽松值类型
        detect_cache: dict[str, Any]
        detect_process: QProcess | None
        detect_viewer: ImageViewerWidget
        rembg_viewer: RembgPreviewWidget
        # 「导出YOLO标注」（开发者模式）那张卡片与按钮，由视图层
        # ``view._build_yolo_export_card`` 建出来后挂在本类实例上
        yolo_export_card: QWidget
        yolo_export_button: QWidget
        log_view: QTextEdit
        _toast: Callable[..., None]
        _acquire_run: Callable[..., bool]
        _release_run: Callable[[], None]
        _mark_run_launched: Callable[[], None]
        _read_worker_error: Callable[[], None]
        _worker_env: Callable[[], QProcessEnvironment]
        _manifest_paths: Callable[[], list]
        #: 立即重算检测统计（不走节流）——由 StageRunnerMixin 提供，
        #: 用户手工改框这类"错一拍就是错的"时机必须用它（见 runner.py）。
        _refresh_stats_now: Callable[[], None]
        current_stage: Callable[[], str]
        current_node: Callable[[], str | None]
        node_of_stage: Callable[[str], str | None]
        _node_scope: Callable[..., dict]
        _size_node_for: Callable[[str], str | None]
        _scope_of: Callable[[str | None], dict]
        imposition_effective: Callable[[], bool]
        window: Callable[[], QWidget]
        # QObject.sender() 在宿主（QWidget）上返回发出信号的对象
        sender: Callable[[], QObject | None]
        # ⚠️ 返回值是 LazyPanelHost 或真面板（属性转发、鸭子类型），用 Any 承接
        panel_host_of_step: Callable[[str], Any]

    @staticmethod
    def _valid_boxes(boxes) -> list:
        """过滤存储中的 null 框（左右身份占位）。

        等价于 :func:`utils.box_geometry.present_boxes`——独立「检测文本框」
        模块页直接用那个纯函数，这里保留这个名字是因为本文件里到处都是它。
        """
        return present_boxes(boxes)

    # ------------------------------------------------------- 框类型（人工干预）
    #
    # 三条约定的落点（用户 2026-09-29 定）：类型在槽位里、半幅左右由位置决定、
    # 整幅显式且互斥。**交互顺序与文案的唯一实现在
    # `desktop/components/box_kinds.py::BoxKindEditor`**（与独立检测页共用）；
    # 本 Mixin 只提供宿主协议（预览控件 / 提示出口 / 落库 / 确认框）。

    def _box_editor(self) -> BoxKindEditor:
        """共享交互器（无状态，按需构造；宿主协议见下面 box_ 前缀一组）。"""
        return BoxKindEditor(self)

    # ---- BoxKindHost 协议（box_ 前缀，避免与页面其他成员撞名）----
    def box_viewer(self):
        return self.detect_viewer

    def box_toast(self, kind: str, title: str, content: str) -> None:
        self._toast(kind, title, content)

    def box_raw_slots(self, path_text: str) -> list:
        return self._raw_boxes_for(path_text)

    def box_page_is_full(self, _path_text: str) -> bool:
        # 查看器的整幅标志即当前页形态（编辑动作都发生在当前显示页上）
        return bool(self.detect_viewer.box_full_mode())

    def box_image_size(self, path_text: str):
        return self._image_size_for(path_text)

    def box_commit(self, path_text: str, slots: list, select_box=None,
                   side="keep") -> None:
        """落库 + 重画；``side`` 按需写入/清除这页的人工左右指定。

        ``side`` 语义（见 ``components.box_kinds.SIDE_KEEP``）：``"left"`` /
        ``"right"`` 写入、``None`` 清除、``"keep"`` 不动。

        ⚠️ **先写 side、再上屏**：``_store_slots`` → ``_apply_boxes`` 会读这一页
        的指定值来决定标签/面板高亮（``box_kinds``）。反过来（先上屏后写）第一次
        点击上屏用的还是**旧 side**，界面看着没切换，必须再点一次才生效——用户
        2026-10-17 报的「第一下只是把按钮点亮、等一小会点第二下才切」就是这个。
        """
        self._write_side_override(path_text, side)
        self._store_slots(path_text, slots, "manual", select_box=select_box)

    def box_page_half_candidate(self, path_text: str) -> bool:
        """这页是否**够「半幅」**（整本书单栏 + 只有一个横跨整页的框）。

        判据本体在 ``utils.book_layout.is_single_wide_half``；这里只取数。
        """
        raw = self._raw_boxes_for(path_text)
        if not self._single_column_display():
            return False
        width = self._page_width_of(Path(path_text))
        return is_single_wide_half(raw, width)

    def _write_side_override(self, path_text: str, side) -> None:
        """写/清人工左右指定（``"keep"`` = 不动）。"""
        if side == "keep" or not self.task_id:
            return
        writer = getattr(self.store, "set_box_side_override", None)
        if not callable(writer):
            return
        writer(
            self.task_id, Path(path_text).stem, side,
            **self._node_scope(self.node_of_stage("detect")),
        )

    def box_confirm(self, title: str, body: str, yes_text: str, cancel_text: str) -> bool:
        # ⚠️ 延迟导入必须留在方法体内：自测靠替换 qfluentwidgets.Dialog 记录确认
        from qfluentwidgets import Dialog  # noqa: PLC0415

        dialog = Dialog(title, body, self.window())
        dialog.yesButton.setText(yes_text)
        dialog.cancelButton.setText(cancel_text)
        return bool(dialog.exec())

    def box_resync_kind(self, index: int) -> None:
        """按现值回填面板的「选中框类型」高亮（类型操作结束后必调）。

        ⚠️ 分段控件在按下那一刻就把滑块移到了被点的段，而有些点击本来就不会
        改数据（普通半幅页点另一侧、整幅声明被取消）——不回填就会停在"看起来
        切了、其实没切"的位置（用户 2026-10-17 报「切换有问题」）。
        """
        self._on_box_selection_changed(index)

    def box_current_path_text(self) -> str:
        path = self.detect_viewer.current_path()
        return str(path) if path else ""

    # ---- 旧入口：保留名字（自测按这些签名钉行为），实现委托共享交互器 ----
    def _box_kinds(self) -> list:
        """预览里每个框当前的类型（"left"/"right"/"full"）。"""
        return self.detect_viewer.box_kinds()

    def _on_box_selection_changed(self, index: int) -> None:
        """预览里选中态变化 → 回填面板的「选中框类型」与删除按钮。"""
        panel = self.panel_host_of_step("detect")
        setter = getattr(panel, "set_box_selection", None)
        if not callable(setter):
            return
        kinds = self._box_kinds()
        kind = kinds[index] if 0 <= index < len(kinds) else ""
        setter(index, kind)

    def _on_box_edit_rejected(self, message: str) -> None:
        """框数已达上限（整幅 1 / 半幅 2）→ 弹出可操作的提示。"""
        self._toast("warning", "框数已达上限", message)

    def _set_selected_box_kind(self, kind: str) -> None:
        """面板里点了「左框 / 右框 / 整幅」。"""
        path = self.detect_viewer.current_path()
        if path is None or not self.task_id:
            return
        self._box_editor().set_kind(str(path), self.detect_viewer.selected_index(), kind)

    def _select_box_of_kind(self, kind: str) -> None:
        """没有选中框时，点类型＝选中该类框；该类型不存在则提示。"""
        self._box_editor().select_box_of_kind(kind)

    def _make_box_full(self, path_text: str, index: int) -> None:
        """把第 index 个框设为「整幅」（整幅与半幅互斥、一页只能一个框）。"""
        self._box_editor().make_full(path_text, index)

    def _make_box_half(self, path_text: str, index: int, kind: str) -> None:
        """把第 index 个框改成半幅（左/右）。"""
        self._box_editor().make_half(path_text, index, kind)

    def _delete_selected_box(self) -> None:
        """删除当前选中的文本框（与 Delete 键同一条路径）。"""
        self._box_editor().delete_selected()

    # ------------------------------------------------------- 检测结果统计
    #
    # 第二步右侧的「检测结果统计」：按页形态（fullcontent / harfcontent /
    # 单独页 / 无文本框）分类计数，默认总览、点进看页码明细。分类规则唯一
    # 实现在 `utils.box_geometry.classify_page_slots`；这里只负责**取数**与
    # 触发时机（切阶段、批量检测、单页检测、人工编辑框之后都要重算）。

    @staticmethod
    def _page_label(path: Path) -> str:
        """页码展示文案：数字页名去掉前导零（0007 → 7），其余原样。"""
        stem = path.stem
        return str(int(stem)) if stem.isdigit() else stem

    # ------------------------------------------------- 检测框的节点作用域（B 方案）
    def _boxes_write_path(self) -> Path | None:
        """**本步要写**的检测框文件：当前「检测文本框」节点那一份。

        主节点 ⇒ ``boxes.json``（零迁移），副本 ⇒ ``boxes~<节点>.json``。
        """
        if not self.task_id:
            return None
        return self.store.boxes_path(
            self.task_id, **self._node_scope(self.node_of_stage("detect"))
        )

    def _boxes_read_path(self) -> Path | None:
        """**消费方要读**的检测框文件：由连线喂给**当前节点**的那个产出方。

        「图片去底色」/「提交」读的框不该是"本阶段的 boxes"，而是**图上喂它的
        那个检测节点**的 boxes（B 方案：同一步骤可以有多个「检测文本框」，
        第二个节点喂第二条去底色链）。解析不到上游时回落到主节点的
        ``boxes.json``——流程里没有检测节点时行为与改造前一致。
        """
        if not self.task_id:
            return None
        node = self.current_node()
        if node:
            path = self.store.node_input(
                self.task_id, node, "boxes", self.imposition_effective()
            )
            if path is not None:
                return path
        step = "detect"
        return self.store.boxes_path(
            self.task_id, **self._node_scope(self.node_of_stage(step))
        )

    def _refresh_detect_stats(self) -> None:
        """重算右侧统计：清单 × 每页槽位（内存缓存优先，boxes.json 一次读盘）。"""
        widget = getattr(self, "detect_stats", None)
        if widget is None:
            return
        paths = self._manifest_paths()
        if not self.task_id or not paths:
            # 没有页/没有任务＝没有整本书可判 → 明确退回"非单栏"，别让上一本书的
            # 结论残留到下一本（切任务时 stats 也会走这条）。
            setter = getattr(self.detect_viewer, "set_single_column", None)
            if callable(setter):
                setter(False)
            widget.set_results(len(paths), {})
            return
        boxes_all = self.store.boxes_all_at(
            self.store.boxes_path(
                self.task_id, **self._node_scope(self.node_of_stage("detect"))
            )
        )
        classes: dict[str, list[tuple[int, str]]] = {}
        # ⚠️ 顺手把**每页槽位**攒下来给全书判据用：判据要的是"整本书长什么样"，
        #    而这次遍历已经把每页都读出来了，第二次再读一遍 boxes.json 纯属白花
        #    （320 页时那是整本 JSON 的一次重复解析）。
        sampled: list[tuple[str, list, int]] = []
        # ⚠️ 尺寸**循环外读一次**：逐页调 image_size 会整份读盘（320 页＝320 次）。
        sizes: dict = {}
        if self.task_id:
            sizes_getter = getattr(self.store, "image_sizes_all", None)
            if sizes_getter is not None:
                try:
                    sizes = sizes_getter(
                        self.task_id,
                        **self._node_scope(self.node_of_stage("detect")),
                    )
                except Exception:  # noqa: BLE001 - 读不到就全部回落图片头
                    sizes = {}
        for row, path in enumerate(paths):
            raw = self.detect_cache.get(str(path))
            if raw is None:
                raw = boxes_all.get(path.stem, ([], "auto"))[0]
            # ⚠️ 传给分类器的是**槽位**（保留 None）：单独页（双槽缺一侧）
            #    过滤掉 None 会被误判成整幅。
            classes.setdefault(classify_page_slots(raw), []).append((row, self._page_label(path)))
            sampled.append((path.stem, list(raw or []), self._page_width_of(path, sizes)))
        # ⚠️ 全书判据**只算一次**：以前这里算一次、_book_note 里又算一次，
        #    2000 页的书等于白跑一遍（用户报「切类型卡顿」时排查到的重复项之一）。
        profile = profile_book(sampled)
        # ⚠️ 把整本书的结论交给预览控件：**半幅**标注靠它决定（见 styles.box_styles）。
        self._apply_book_layout(profile)
        widget.set_results(
            len(paths), classes, book_note=self._book_note_from(profile)
        )

    def _single_column_display(self) -> bool:
        """预览控件当前是否按「单栏书」显示（决定标签是否用「半幅」）。

        ⚠️ 走 ``getattr`` 兜底：自测的 viewer 替身只实现被断言用到的方法，
        缺 ``single_column`` 时不该把整次上屏打断——取不到就按"不是单栏书"
        （旧行为：左/右框）处理。
        """
        getter = getattr(self.detect_viewer, "single_column", None)
        if not callable(getter):
            return False
        try:
            return bool(getter())
        except Exception:  # noqa: BLE001 - 显示口径取不到就退回旧行为
            return False

    def _side_override_of(self, path_text: str, raw=None) -> str | None:
        """某页的**用户指定左右**（``"left"``/``"right"``/None）。

        只在「半幅」页上有意义：那种框横跨整页、中心压在中线上，按位置判左右
        没有意义，由用户点左/右指定（存 boxes.json 的 ``side``）。

        ⚠️ **只有「半幅单框」的页才可能带指定**：双框页/整幅页直接返回 None，
        连 boxes.json 都不读——否则每次切换类型都要整份解析一次文件（2000 页
        约 4ms，切换是高频动作）。

        ⚠️ 走 ``getattr`` 兜底：替身 store 可能没有 ``box_side_at``，取不到就
        当"没指定"（退回自动判定的半幅），不该让上屏中断。
        """
        slots = list(raw if raw is not None else self._raw_boxes_for(path_text))
        present = [b for b in slots if b]
        if len(slots) != 2 or len(present) != 1:
            return None
        getter = getattr(self.store, "box_side_at", None)
        if not callable(getter) or not self.task_id:
            return None
        try:
            return getter(self._boxes_write_path(), Path(path_text).stem)
        except Exception:  # noqa: BLE001 - 取不到就按"没指定"
            return None

    def _apply_book_layout(self, profile) -> None:
        """把整本书的形态结论同步给预览控件（标签/面板高亮同一口径）。

        ⚠️ 只同步**单栏书**这一条：它决定「半幅」标注。整幅书里的可疑半幅
        不改标注（用户 2026-10-17 选择「只警告」），那条只进统计面板文案。
        """
        setter = getattr(self.detect_viewer, "set_single_column", None)
        if callable(setter):
            setter(bool(profile.single_column_book))
            # 结论可能刚变（刚检测完/刚编辑过框）→ 立刻按新口径回填面板高亮，
            # 否则画面已标「半幅」而面板仍停在「左框」。
            self._on_box_selection_changed(self.detect_viewer.selected_index())

    def _page_width_of(self, path: Path, sizes: dict | None = None) -> int:
        """该页原始像素宽度（全书判据用；取不到返回 0＝不参与单宽框判定）。

        优先用 ``sizes.json``（``sizes`` 传入时零读盘，不给就自己读一次）；
        缺记录才回落到图片头。
        ⚠️ 判定要的是**框坐标所处的那个坐标系**的页宽，所以必须按节点作用域
        取尺寸——两个提取节点用了不同 dpi 时共用一份尺寸会算错比例。

        ⚠️ **必须走批量读**（``image_sizes_all``）：逐页调 ``image_size`` 每次都
        整份读盘，320 页就是 320 次全量解析。``sizes`` 由调用方在循环外读一次。

        ⚠️ ``image_sizes_all`` 走 ``getattr`` 兜底而不是直接调：自测的 store
        替身只实现被断言用到的那几个方法，缺它会 AttributeError 把整个统计刷新
        打断。取不到宽度只是让该页不参与单宽框判定（保守回落），不该让整屏统计
        崩掉。
        """
        if sizes is None:
            sizes = {}
            if self.task_id:
                getter = getattr(self.store, "image_sizes_all", None)
                if getter is not None:
                    try:
                        sizes = getter(
                            self.task_id,
                            **self._node_scope(self.node_of_stage("detect")),
                        )
                    except Exception:  # noqa: BLE001 - 取不到就回落读图片头
                        sizes = {}
        size = sizes.get(path.stem) if isinstance(sizes, dict) else None
        if size and size[0] > 0:
            return int(size[0])
        # ⚠️ 没有 sizes 记录时**读图片头**是每页一次文件打开（本机 211 页实测
        #    57ms、2000 页 ≈ 540ms），而"切类型"每次都重算全书统计 ⇒ 主线程卡顿
        #    （用户 2026-10-17 报「点类型卡顿」）。页宽在一次会话里不会变，读一次
        #    就记住；只缓存**成功**结果（读失败可能是文件被占用，下次还要重试）。
        cache = getattr(self, "_page_width_cache", None)
        if cache is None:
            cache = self._page_width_cache = {}
        key = str(path)
        width = cache.get(key)
        if width:
            return width
        try:
            with Image.open(path) as image:
                width = int(image.width)
        except Exception:  # noqa: BLE001 - 取不到宽度按"无页宽"，判据自行回落
            return 0
        if width > 0:
            cache[key] = width
        return width

    @staticmethod
    def _book_note_from(profile) -> str:
        """**已算好的**全书判据 → 统计面板顶部的一行人读提示（无需提示时空串）。

        ⚠️ 收的是 ``BookProfile`` 而不是原始页表：调用方已经算过一次 profile，
        这里再算一遍在 2000 页的书上是纯浪费（用户报「切类型卡顿」的重复项）。

        ⚠️ **警告优先于结论**：整幅书里冒出半幅是"结果可疑"，必须让用户先去
        核对；单栏书只是"已按单栏命名"，是已经生效的事实。两条同时成立时把
        可疑那条放前面——前者要人动手，后者只是告知。
        """
        return "\n".join(
            text for text in (
                suspicious_summary(profile), single_column_summary(profile),
            ) if text
        )

    @staticmethod
    def _book_note(sampled) -> str:
        """原始页表 → 提示（内部算 profile；批量场景请用 :meth:`_book_note_from`）。"""
        return DetectMixin._book_note_from(profile_book(sampled))

    def _goto_stats_page(self, row: int) -> None:
        """统计明细里点了页码 → 预览跳到那一页（联动框重读）。"""
        strip = self.detect_viewer.strip
        if 0 <= row < strip.count():
            strip.setCurrentRow(row)

    def _raw_boxes_for(self, path_text: str) -> list:
        """某页**槽位**表示（保留 null，形态信息就在槽数里）。"""
        raw = self.detect_cache.get(str(path_text))
        if raw is None and self.task_id:
            entry = self.store.boxes_entry_at(
                self._boxes_write_path(), Path(path_text).stem
            )
            raw = entry[0] if entry else []
        return list(raw or [])

    def _store_slots(self, path_text: str, raw: list, origin: str, select_box=None) -> None:
        """把槽位结果落库 + 进缓存 + 刷预览（人工编辑与类型切换共用一条路径）。

        ``select_box`` 给定某个框时，重新上屏后仍选中**同一个框**（按坐标找回）——
        切换类型 / 整理槽位会改变框在列表里的次序，按下标保持会选错框。
        """
        image_key = Path(path_text).stem
        self.detect_cache[str(path_text)] = list(raw)
        if self.task_id:
            self.store.save_detect_boxes(
                self.task_id, image_key, list(raw), origin=origin,
                **self._node_scope(self.node_of_stage("detect")),
            )
        shown = self._valid_boxes(raw)
        index = -1
        if select_box is not None:
            target = list(select_box)
            index = next((i for i, b in enumerate(shown) if list(b) == target), -1)
        self._apply_boxes(path_text, raw, origin, select_index=index)
        self._refresh_reference_boxes()
        # 拖动/删框/切类型都会改这一页的形态 → 右侧统计**立即**重算
        # （不走节流：用户正盯着这页改，错一拍就是错的）
        self._refresh_stats_now()

    def _apply_boxes(self, path_text: str, raw, origin: str | None = None, select_index: int = -1) -> None:
        """把某页的槽位结果画到大图上。

        显示用的名称/颜色**由控件按中心位置现算**（`image_view.box_styles`），
        这里只把 ``full``（整幅页）标志、一行文案与要选中的下标交给它——
        规则不抄第二份。
        """
        from desktop.components.viewers.image_view import box_names  # noqa: PLC0415

        shown = self._valid_boxes(raw)
        full = is_full_content(raw)
        size = self._image_size_for(path_text)
        qsize = QSize(size[0], size[1]) if size else QImageReader(str(path_text)).size()
        # ⚠️ 单栏书里这个横跨整页的框叫「半幅」，不叫左框/右框——整本书的结论
        #    来自 profile_book（见 _refresh_detect_stats 写入 viewer 的那一份），
        #    这里读 viewer 的现值以保证「标签」与「面板高亮」同一口径。
        # ⚠️ 若用户在半幅页上**指定过**左/右，标签就用指定值（优先级见 box_styles）。
        side = self._side_override_of(path_text, raw)
        setter = getattr(self.detect_viewer, "set_side_override", None)
        if callable(setter):
            # ⚠️ rerender=False：下面紧接着 apply_boxes 会重绘一次，这里再画一遍
            #    就是一次切换类型画两遍（用户报的卡顿）。取不到 rerender 形参的
            #    替身按老签名调（自测替身只实现被断言用到的方法）。
            try:
                setter(side, False)
            except TypeError:
                setter(side)
        names = box_names(
            shown, size, full, self._single_column_display(), side
        )
        info = self._describe_boxes(shown, names) + ORIGIN_SUFFIX.get(origin or "", "")
        self._show_boxes_info(shown, origin, names=names)
        self.detect_viewer.apply_boxes(
            shown,
            qsize,
            info,
            full=full,
            selected=select_index,
        )

    # ------------------------------------------------------------ 页面几何
    def _image_size_for(self, path_text: str):
        """页面图片原始尺寸 (w, h)：优先 sizes.json，回退读图头。

        ⚠️ 尺寸基准按**产出这张图的节点**取（B 方案）：两个「图片提取」节点
        用不同 zoom/dpi 时页面尺寸不同，按主节点那份缩放会让副本节点的框错位。
        """
        if self.task_id:
            size = self.store.image_size(
                self.task_id, Path(path_text).stem,
                **self._scope_of(self._size_node_for(path_text)),
            )
            if size and size[0] > 0 and size[1] > 0:
                return int(size[0]), int(size[1])
        head = QImageReader(str(path_text)).size()
        if head.isValid() and head.width() > 0:
            return head.width(), head.height()
        return None

    def _current_boxes_for(self, path_text: str) -> list:
        """当前应展示的框（内存缓存优先）。"""
        return self._valid_boxes(self.detect_cache.get(str(path_text)) or [])

    def _detect_image_selected(self, index: int, path_text: str) -> None:
        """选中图片：只展示已有检测结果，绝不自动执行检测（重负载操作需用户触发）。"""
        path = Path(path_text)
        key = str(path)
        self.detect_viewer.set_reference_boxes([])
        if key in self.detect_cache:
            raw = self.detect_cache[key] or []
            if self._valid_boxes(raw):
                self._apply_boxes(key, raw)
            else:
                self._show_boxes_info([])
                # ⚠️ 无框时也要把预览的形态复位：否则上一页如果是整幅页，
                #    本页会沿用「整幅」的框数上限（只能画一个框）。
                self.detect_viewer.apply_boxes(
                    [],
                    QImageReader(key).size(),
                    self._describe_boxes([]),
                    full=is_full_content(raw),
                )
            self._refresh_reference_boxes()
            return
        # 优先使用库里的框（含手动调整过的）
        entry = (
            self.store.boxes_entry_at(self._boxes_write_path(), path.stem)
            if self.task_id else None
        )
        if entry is not None:
            boxes, origin = entry
            self.detect_cache[key] = boxes
            self._apply_boxes(key, boxes, origin)
            self._refresh_reference_boxes()
            return
        self.detect_viewer.info_label.setText("尚未检测：点右上「检测文本框」批量检测，或点面板里的「检测本页」")

        self.detect_viewer.info_label.setText("尚未检测：点右上「检测文本框」批量检测，或点面板里的「检测本页」")

    def _detect_current_page(self) -> None:
        """手动触发当前页的检测文本框（YOLO 子进程，重负载）。"""
        if not self.task_id:
            return
        path = self.detect_viewer.current_path()
        if not path:
            self._toast("warning", "提示", "请先完成提取，再执行检测。")
            return
        key = str(path)
        entry = self.store.boxes_entry_at(self._boxes_write_path(), Path(path).stem)
        if entry is not None and any(entry[0] or []):
            self.detect_cache[key] = entry[0]
            self._apply_boxes(key, entry[0], entry[1])
            self._refresh_reference_boxes()
            self._toast("info", "已有检测结果", "该页检测结果已存在，直接展示。")
            return
        # 执行权守卫：单页检测同样要抢 worker 槽位（一次 torch 冷启动 5 秒以上）。
        # ``replace=("单页检测",)`` 是刻意留的口子——连点不同页面时应该「换一页重检」
        # （_start_detect 会先断旧进程信号再杀），而不是弹一句"正在执行"卡住用户；
        # 但子任务在跑时必须拦住，那种情况下再塞一个检测只会两个 torch 抢内存。
        if not self._acquire_run("单页检测", replace=("单页检测",)):
            return
        self.detect_viewer.info_label.setText("正在检测文本框位置...")
        self.detect_cache[key] = None  # 防止重复派发
        self._start_detect(path)

    def _detect_boxes_for(self, path_text: str) -> list:
        """某页的检测框（内存缓存优先，其次 boxes.json）。

        ⚠️ 消费方读取（B 方案）：存档框取**连线上喂给当前节点**的那个检测
        节点的文件（``_boxes_read_path``）——两个「检测文本框」节点各有各的框，
        按阶段读会让去底色用错节点的框裁图。

        ⚠️ 走 :meth:`_boxes_map_cached`（整本一次读齐 + 失效缓存）：
        查看器构建条目会**逐页**回调本方法，逐页解析流程图 + 读整份
        ``boxes.json`` 就是 O(n²)。
        """
        boxes = self.detect_cache.get(str(path_text))
        if boxes is not None:
            return boxes or []
        return self._boxes_map_cached().get(Path(path_text).stem, []) or []

    def _boxes_map_cached(self) -> dict:
        """整本 ``{页名: 原始槽位}``，带缓存（``_detect_boxes_for`` 的整本版）。

        ⚠️ 为什么要有缓存：查看器重建条目时会**逐页**回调 ``boxes_provider``
        （110 页 = 110 次），每次走一遍"解析流程图 → 找上游连接线 → 读
        boxes.json"就是 O(n²)——真实 GUI 实测这一步占 0.27~0.58s，是进详情/
        首帧卡顿的主要残留。这里把整本读成一张表，只在下列任一项变化时重算：

        - ``detect_cache.version``（用户改框，``VersionedBoxCache`` 自增）；
        - 框文件指纹（mtime_ns + size，外部落盘如批量检测写回）；
        - 页清单（``_manifest_paths``，内建签名缓存，命中很便宜）；
        - 当前步骤格序（换了节点 ⇒ 上游框可能来自另一份文件）。

        ⚠️ 不能改成"调用方传一张一次性快照"：查看器的 provider 是长期持有的，
        之后改框 / 单页检测落盘都会再次重建条目，快照会把用户刚改的框吃掉。
        """
        paths = self._manifest_paths()
        version = getattr(self.detect_cache, "version", 0)
        bar = getattr(getattr(self, "step_bar", None), "_current", -1)
        file_key = tuple(str(path) for path in paths)
        cache = self.__dict__.get("_boxes_map_cache")
        read_path = cache.get("path") if cache else None
        key = (self.task_id, bar, version, file_key, str(read_path),
               self._file_fingerprint(read_path))
        if cache is not None and cache.get("key") == key:
            return cache["map"]
        # 未命中才现算（见 _boxes_map_all）
        mapping = self._boxes_map_all()
        read_path = self._boxes_read_path() if self.task_id else None
        self._boxes_map_cache = {
            "key": (self.task_id, bar, version, file_key,
                    str(read_path) if read_path else None,
                    self._file_fingerprint(read_path)),
            "map": mapping,
            "path": read_path,
        }
        return mapping

    @staticmethod
    def _file_fingerprint(path) -> tuple[int, int] | None:
        """文件指纹（``mtime_ns`` + ``size``）；文件不存在返回 None。"""
        if path is None:
            return None
        try:
            stat = Path(path).stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def _boxes_map_all(self) -> dict:
        """整本：``{页名: 原始槽位}``，**一次读盘**（语义与 ``_detect_boxes_for`` 对齐）。

        ⚠️ 逐页调 ``_detect_boxes_for`` 会对每页重读整份 ``boxes.json``（O(n²)）；
        提交裁图前要整书判据（单栏书结论），必须一次读齐。

        口径与 :meth:`_detect_boxes_for` 逐条一致：内存缓存（用户刚改过的）优先，
        其次连线上游那个节点的 ``boxes`` 文件。
        """
        paths = self._manifest_paths()
        if not paths:
            return {}
        stored = (
            self.store.boxes_all_at(self._boxes_read_path())
            if self.task_id else {}
        )
        boxes: dict = {}
        for p in paths:
            cached = self.detect_cache.get(str(p))
            if cached is not None:
                boxes[Path(p).stem] = list(cached)
                continue
            entry = stored.get(Path(p).stem)
            boxes[Path(p).stem] = list(entry[0]) if entry else []
        return boxes

    def _refresh_reference_boxes(self) -> None:
        """重算参考框（虚线标注）。

        border 属于裁剪步骤，detect 预览的参考框只体现检测框本身
        （默认不加边距），检测出几个框就画几个参考框。
        """
        path = self.detect_viewer.current_path()
        if path:
            boxes = self._current_boxes_for(str(path))
            if not boxes:
                self.detect_viewer.set_reference_boxes([])
            else:
                self.detect_viewer.set_reference_boxes(compute_final_boxes(boxes, None))
        # rembg 预览的区域同步刷新（显示范围跟随检测框）
        # ⚠️ **只在本步就是「图片去底色」时才刷**（用户 2026-10-17 报「切换
        #    左/右/半幅/整幅卡顿」）：``refresh_display`` 会重建全部条目并重新
        #    解码 + 合成当前页的大图（12MP 扫描件几十到几百毫秒），而第二步
        #    根本看不见那个控件。进第三步时 ``_show_stage`` 会 ``set_images``
        #    重建一次，所以这里跳过不会读到旧框。
        if self.current_stage() == "rembg":
            self.rembg_viewer.refresh_display()

    def _show_boxes_info(self, boxes, origin: str | None = None, names=None) -> None:
        if boxes is None:
            self.detect_viewer.info_label.setText("正在检测文本框位置...")
            return
        suffix = ORIGIN_SUFFIX.get(origin or "", "")
        self.detect_viewer.info_label.setText(self._describe_boxes(boxes, names) + suffix)

    @staticmethod
    def _describe_boxes(boxes, names=None) -> str:
        """框列表 → 一行说明；names 与 boxes 对齐（整幅页显示「整幅」）。

        names 缺失时回退到「左框/右框」（旧的按序号命名）。
        """
        if not boxes:
            return "未检测到文本框"
        labels = list(names) if names else []
        return "  ｜  ".join(
            f"{(labels[i] if i < len(labels) else ('左框', '右框')[i % 2])}" f"({b[0]},{b[1]},{b[2]},{b[3]})"
            for i, b in enumerate(boxes)
        )

    def _save_manual_boxes(self, path_text: str, boxes) -> None:
        """预览区编辑线框后保存到库（origin=manual），不生成任何文件。

        ⚠️ 存的是**槽位**表示，不是"用户画了几个框"：
        - 整幅页 → 1 槽 ``[整幅]``；
        - 半幅页 → **恒 2 槽** ``[左, 右]``（缺失侧 null）。

        这样删到一个不剩或只剩一侧时，形态都不会从半幅变成整幅——用户报的
        "删掉整幅框后，右边的框自动变成了整幅" 就是按元素个数推断类型的后果。
        """
        if not self.task_id:
            return
        normalized = [[int(round(float(v))) for v in box] for box in boxes]
        size = self._image_size_for(path_text) or (0, 0)
        sel = self.detect_viewer.selected_index()
        sel_box = normalized[sel] if 0 <= sel < len(normalized) else None
        if not normalized:
            raw: list = []
        elif self.detect_viewer.box_full_mode() and len(normalized) == 1:
            raw = [normalized[0]]  # 整幅：只允许一个框（控件侧已按 max_boxes 拦住）
        else:
            # 半幅：恒 2 槽。⚠️ 万一"整幅页"却拿到多个框（不该发生），按半幅存——
            # 宁可形态变半幅，也不能悄悄丢掉用户画出来的框。
            raw = half_slots(normalized, size)
        self._store_slots(path_text, raw, "manual", select_box=sel_box)

    def _stop_detect_process(self) -> None:
        """停掉在跑的单页检测并释放执行权（返回列表/切任务前必须调）。

        ⚠️ 不停的话（2026-09-26 第二轮审计 H3）：检测是几秒到十几秒的慢活，
        用户中途「返回」或切到任务 B 后，旧进程的 boxes 事件才姗姗到达——
        而 ``self.task_id`` 已经是 B 了，``save_detect_boxes`` 就会把 A 的
        检测框写进 **B 的** boxes.json（两本书页名同为 0001 时直接污染裁剪）；
        若 A 已被删除，这里还会 FileNotFoundError 从 Qt 槽直接炸出去。
        与 ``_start_detect`` 的顶替逻辑同款：先断信号再 kill。
        """
        proc = self.detect_process
        if proc is None:
            return
        if proc.state() != QProcess.ProcessState.NotRunning:
            for signal in (
                proc.readyReadStandardOutput,
                proc.readyReadStandardError,
                proc.finished,
            ):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            proc.kill()
            proc.waitForFinished(1000)
        self.detect_process = None
        self._detect_out_buffer = ""
        self._release_run()

    def _start_detect(self, path: Path) -> None:
        old = self.detect_process
        if old is not None and old.state() != QProcess.ProcessState.NotRunning:
            # 关键：先断开旧进程的全部信号再杀。否则旧进程迟到的 finished
            # 会把 self.detect_process 清空，新进程的输出就被当成无主的丢弃。
            for signal in (
                old.readyReadStandardOutput,
                old.readyReadStandardError,
                old.finished,
            ):
                try:
                    signal.disconnect()
                except (RuntimeError, TypeError):
                    pass
            old.kill()
            old.waitForFinished(1000)
        task_id = self.task_id
        assert task_id is not None, "单页检测时没有任务在身"
        runs_dir = self.store.runs_config_dir(task_id)
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / "detect-config.json"
        write_json(
            config_path,
            {"mode": "detect", "image": str(path)},
        )
        self.detect_process = QProcess(cast("QObject", self))
        self._detect_out_buffer = ""  # stdout 半行重组缓冲（见 _read_detect_output）
        self.detect_process.setProgram(sys.executable)
        self.detect_process.setProcessEnvironment(self._worker_env())
        if getattr(sys, "frozen", False):
            arguments = ["--worker", "--config", str(config_path)]
        else:
            arguments = ["-m", "desktop.worker", "--config", str(config_path)]
            self.detect_process.setWorkingDirectory(str(project_root()))
        self.detect_process.setArguments(arguments)
        self.detect_process.readyReadStandardOutput.connect(self._read_detect_output)
        self.detect_process.readyReadStandardError.connect(self._read_worker_error)
        self.detect_process.finished.connect(self._detect_finished)
        self.detect_process.start()
        # 进程真的起来了 → 防抖窗口从这里开始计时（见 _run_launched_at）
        self._mark_run_launched()

    def _read_detect_output(self) -> None:
        if not self.detect_process:
            return
        # PySide6 的 QByteArray 运行时可直接 bytes()（存根不认 SupportsBytes）
        data = bytes(
            self.detect_process.readAllStandardOutput()  # type: ignore[reportArgumentType]
        ).decode("utf-8", errors="replace")
        # ⚠️ 半行重组（审计 P2）：readyRead 只保证"有字节"，不保证按行切齐。
        # JSON Lines 事件被切成两半时，两半都 json.loads 失败 → boxes 事件
        # 整条静默丢弃，界面上表现为"检测完了但框没了"。把不完整的首段
        # 留到缓冲，与下一块拼上再解析；进程结束时缓冲里如有残留按坏行丢弃。
        data = getattr(self, "_detect_out_buffer", "") + data
        if "\n" in data:
            data, self._detect_out_buffer = data.rsplit("\n", 1)
        else:
            self._detect_out_buffer = data
            return
        for line in data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "boxes":
                boxes = []
                try:
                    full = event.get("full")
                    if full:
                        # 整幅内容(fullcontent)：单个框、**单槽**
                        boxes = [[int(v) for v in full]]
                    else:
                        # 半幅：固定 2 槽 [左, 右]，缺失侧为 None（保留左右身份），
                        # 与批量检测的 _store_stage_boxes 完全一致的槽位约定。
                        for key in ("left", "right"):
                            value = event.get(key)
                            boxes.append([int(v) for v in value] if value else None)
                except (TypeError, ValueError):
                    # 畸形坐标（int() 转不动）宁可整条丢弃也别让槽抛异常——
                    # 那样 Qt 只往控制台打一句，界面毫无反应
                    self.log_view.append(f"检测输出格式异常，已忽略：{str(event)[:120]}")
                    continue
                if "image" not in event:
                    continue
                self.detect_cache[event["image"]] = boxes
                # 检测结果写回 boxes.json；无框不存，避免下次选中无法重新检测
                # ⚠️ 写**本节点**那一份（B 方案）：单页检测也属于"这个检测节点
                #    的产物"，写进主节点的文件就是覆盖别人的框。
                if any(boxes) and self.task_id:
                    self.store.save_detect_boxes(
                        self.task_id, Path(event["image"]).stem, boxes,
                        origin="auto",
                        **self._node_scope(self.node_of_stage("detect")),
                    )
                self._apply_detect_result(Path(event["image"]), boxes)
            elif event.get("type") == "log":
                # 单页检测路径原先只认 boxes/detect_error，于是「模型加载用时」
                # 「detect xx.jpg …」这些记录全被丢掉，用户看不出执行了什么
                self.log_view.append(event.get("message", ""))
            elif event.get("type") == "detect_error":
                self.log_view.append(f"检测失败：{event.get('message')}")

    def _detect_finished(self, *_args) -> None:
        # sender() 是真正发出信号的那个进程：只有它仍是"当前进程"时才清空引用
        proc = self.sender()
        if proc is not None and proc is not self.detect_process:
            # 被顶替的旧进程（_start_detect 已断其信号，理论上到不了这里）：
            # 绝不能顺手释放执行权——新进程才持有它
            return
        # 结束后缓冲里若还有半行，是坏行/被截断的输出，直接丢弃防串到下一次
        self._detect_out_buffer = ""
        self.detect_process = None
        self._release_run()
        # 单页检测完成 → 该页形态可能变了，**立即**重算右侧统计
        self._refresh_stats_now()

    def _apply_detect_result(self, path: Path, boxes) -> None:
        """自动检测结果到达 → 上屏（只在本页仍是预览页、且还停在第二步时应用）。"""
        if self.current_stage() != "detect":
            return
        if str(self.detect_viewer.current_path()) != str(path):
            return
        if str(path) in self.detect_cache:
            self.detect_cache[str(path)] = boxes or []
        self._apply_boxes(str(path), boxes or [])
        self._refresh_reference_boxes()

    # ------------------------------------------------- 「导出YOLO标注」（开发者模式）
    #
    # 用户 2026-10-16：开发者模式下打开「启用YOLO标注」后，第二步右栏**最底部**
    # 多一个「导出YOLO标注」。点它先弹窗（名称 = 父节点名 = 文件名前缀；
    # 导出目录按**任务**记住），确认后把本任务的页面导出成 YOLO 数据集切片。
    #
    # 与独立「检测文本框」模块页是**同一条业务链**（同一个
    # `services.detect_export.export_yolo` 与同一个弹窗），区别只在宿主：
    # 那边用页面的输出目录，这边用任务目录里的页面清单。

    def _wire_yolo_export_card(self) -> None:
        """卡片建好后接线：订阅两个开关 + 立刻算一次显隐（视图层建卡片时调）。"""
        self._yolo_kernel: StepKernel | None = None
        #: 导出 job 的统计（见 ``detect_export.export_yolo`` 的返回值）
        self._yolo_summary: dict = {}
        cfg = app_config()
        # 配置项是长期存活的 QObject，页面销毁时 Qt 会自动断开
        cfg.developerMode.valueChanged.connect(self._sync_yolo_export_card)
        cfg.yoloAnnotation.valueChanged.connect(self._sync_yolo_export_card)
        self._sync_yolo_export_card()

    def _sync_yolo_export_card(self) -> None:
        """按「当前是不是 detect 步骤 + 开发者模式 + YOLO 开关」显隐那张卡片。

        ⚠️ 三个条件缺一不可：YOLO 标注是开发者模式下的选项（设置页里它在开关
        后面藏着），开发者模式关掉时那个开关不可见 ⇒ 按"未启用"处理，否则会
        出现"设置里看不到开关、详情页却多出一块"的错位。
        """
        card = getattr(self, "yolo_export_card", None)
        if card is None:
            return
        # 构造期/还没任务时不做判断（那时步骤还无从谈起），保持隐藏
        stage = self.current_stage() if getattr(self, "task_id", None) else ""
        cfg = app_config()
        card.setVisible(
            stage == "detect"
            and bool(cfg.developerMode.value)
            and bool(cfg.yoloAnnotation.value)
        )

    def export_yolo_labels(self) -> None:
        """导出 YOLO 数据集切片：先弹窗，确认后在后台线程复制图片 + 写标签。

        导出的页面清单就是第二步左栏那份（``_manifest_paths``，只含还存在的
        文件）；**没有框的页也照导**（图片 + 空标签 = 负样本，用户 2026-10-16）。
        弹窗的两个默认值都取**本任务上次记住的那一份**（名称 + 导出目录，存在
        任务目录的 ``ui.json`` 里，见 ``store.ui_state``）——用户 2026-10-16：
        「导出目录，和前缀都要保存下来，跟任务绑定」。

        **没记过时**：导出目录默认文档目录（``YoloExportPanel`` 自己兜底）、
        名称默认任务号（``_yolo_dataset_name``）。
        """
        if not self.task_id:
            return
        paths = self._manifest_paths()
        if not paths:
            self._toast(
                "warning", "还没有图片",
                "先执行第一步提取，或把图片放进任务目录的 stages/input，再导出。",
            )
            return
        if self._yolo_kernel is not None and self._yolo_kernel.busy():
            self._toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        saved = self.store.load_yolo_export_state(self.task_id)
        chosen = ask_yolo_export(
            self.window(),
            directory=saved.get("directory") or None,
            name=saved.get("name") or self._yolo_dataset_name(),
        )
        if chosen is None:
            self._toast("info", "已取消", "没有导出任何文件。")
            return
        name, directory = chosen
        self.store.save_yolo_export_state(self.task_id, name, directory)
        entries = yolo_entries(paths, self._yolo_boxes_by_stem())
        kernel = self._ensure_yolo_kernel()
        self.yolo_export_button.setEnabled(False)
        self.log_view.append(
            f"开始导出 YOLO 数据集（{len(entries)} 页）→ {directory}"
        )
        request = StepRequest(
            dest=Path(directory),
            args={
                "name": name,
                # 任务号写进切片的 data.json（用户 2026-10-16）：校验工具据此
                # 自动找到 tasks/<id>/boxes.json 当基准，不必再回忆任务号
                "task_id": str(self.task_id),
                "source": self._yolo_source_name(),
                "entries": [(str(p), slots) for p, slots in entries],
            },
        )
        if not kernel.run(request):
            self.yolo_export_button.setEnabled(True)
            self._toast("warning", "正在导出", "上一次导出还没结束，请稍候。")

    def _yolo_dataset_name(self) -> str:
        """弹窗里「名称」的**默认**值 = ``b<任务号>``（用户 2026-10-16：
        「前缀默认改成 b{TASKID}，比如 b0020」）。

        ⚠️ 只是"没记过时"的兜底：一旦导出过一次，下次进来回填的是**上次那个
        名称**（存在任务目录的 ``ui.json`` 里，见 :meth:`export_yolo_labels`）
        ——用户改成 ``bxxxa`` 之后就一直用它，不会被这个默认值盖回去。

        ⚠️ 用任务号而不是任务名：任务名是中文书名（``XX大學圖書館藏…``），既长
        又要过 ``safe_dirname`` 洗一遍；任务号短、稳定、天然适合当切片前缀
        （一个任务 = 一本书，前缀天然唯一），前面加个 ``b`` 只是为了好看好认。
        """
        return f"b{self.task_id}" if self.task_id else ""

    def _yolo_source_name(self) -> str:
        """本任务源文件的**文件名**（写进切片的 ``data.json``，当来龙去脉）。

        空壳任务（还没选 PDF）没有源文件，回落任务名——总比留空强。
        """
        if self.source_path:
            return Path(self.source_path).name
        task = self.store.get_task(self.task_id) if self.task_id else None
        return str((task or {}).get("name") or "")

    def _yolo_boxes_by_stem(self) -> dict:
        """页面 stem → **槽位**（内存缓存优先，其次 ``boxes.json``）。

        与 :meth:`_refresh_detect_stats` 同一套取数口径：``detect_cache`` 里
        可能有 ``None``（检测在跑时的占位），``yolo_entries`` 会把它当空表
        （那一页就是负样本）。
        """
        boxes: dict[str, list] = {}
        if self.task_id:
            boxes_all = self.store.boxes_all_at(self._boxes_write_path())
            for stem, entry in boxes_all.items():
                boxes[stem] = list(entry[0] or [])
        for path_text, raw in self.detect_cache.items():
            boxes[Path(path_text).stem] = list(raw or [])
        return boxes

    def _ensure_yolo_kernel(self) -> StepKernel:
        """导出执行内核（懒建；纯函数 job 跑在后台线程，不冻界面）。

        ⚠️ 不复用第二步那条执行线：那条跑的是检测子进程（重、要抢执行权），
        导出是"读已有框 + 复制图片"的短活，互不影响。
        """
        if self._yolo_kernel is None:
            kernel = StepKernel(callable_job(self._yolo_job), cast("QObject", self))
            kernel.log.connect(self._on_yolo_log)
            kernel.finished.connect(self._on_yolo_finished)
            kernel.failed.connect(self._on_yolo_failed)
            self._yolo_kernel = kernel
        return self._yolo_kernel

    def _yolo_job(self, request: StepRequest, report) -> str | None:
        """导出 job（跑在 worker 线程）：复制图片 + 写标签。"""
        dest = request.dest
        assert dest is not None, "导出 job 必须带输出目录"

        def log(text: str) -> None:
            report("log", {"message": text})

        def progress(done: int, total: int) -> None:
            report("progress", {"done": done, "total": total})

        self._yolo_summary = export_yolo(
            [(Path(p), slots) for p, slots in request.args["entries"]],
            dest,
            str(request.args.get("name", "")),
            task_id=str(request.args.get("task_id", "")),
            source=str(request.args.get("source", "")),
            report=log,
            progress=progress,
        )
        return str(dest)

    def _on_yolo_log(self, message: str) -> None:
        self.log_view.append(message)

    def _on_yolo_finished(self, out_dir: str) -> None:
        """导出完成：恢复按钮 + 报清"几页有框、几页负样本、落点在哪"，
        并**打开导出目录**（用户 2026-10-16：「导出成功后，打开相应的目录」）。"""
        self.yolo_export_button.setEnabled(True)
        summary = self._yolo_summary or {}
        folder = summary.get("folder") or out_dir
        count = len(summary.get("labels") or [])
        detail = (
            f"{summary.get('labeled', 0)} 页有框（{summary.get('boxes', 0)} 个框）、"
            f"{summary.get('empty', 0)} 页负样本"
        )
        self.log_view.append(f"YOLO 数据集导出完成：{detail} → {folder}")
        self._toast("success", "已导出YOLO标注", f"{count} 页（{detail}）→ {folder}")
        if count:
            reveal_dir(folder)

    def _on_yolo_failed(self, message: str) -> None:
        self.yolo_export_button.setEnabled(True)
        self.log_view.append(f"导出YOLO标注失败：{message}")
        self._toast("error", "导出失败", message)
