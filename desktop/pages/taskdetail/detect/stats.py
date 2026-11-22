# -*- coding: utf-8 -*-
"""第二步的检测结果统计与全书形态结论（从原 ``detect.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image

from utils.book_layout import (
    demoted_full_summary,
    full_to_half_slots,
    profile_book,
    single_column_summary,
    suspicious_summary,
)
from utils.box_geometry import classify_page_slots

if TYPE_CHECKING:
    from desktop.pages.taskdetail.detect._host import DetectHost
else:
    DetectHost = object


class DetectStatsMixin(DetectHost):
    """按页形态分类计数，并把全书结论同步给预览控件。"""
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

    def _refresh_detect_stats(self) -> None:
        """重算右侧统计：清单 × 每页槽位（内存缓存优先，boxes.json 一次读盘）。"""
        widget = getattr(self, "detect_stats", None)
        if widget is None:
            return
        # ⚠️ 上游没执行成功 ⇒ 这一步没有数据，统计也不能拿旧清单充数
        #    （用户 2026-11-03：上一步没执行，下一步不该看到任何东西）。
        visible = self.current_stage() != "detect" or self._stage_input_visible()
        paths = self._manifest_paths() if visible else []
        if not self.task_id or not paths:
            # 没有页/没有任务＝没有整本书可判 → 明确退回"非单栏"，别让上一本书的
            # 结论残留到下一本（切任务时 stats 也会走这条）。
            setter = getattr(self.detect_viewer, "set_single_column", None)
            if callable(setter):
                setter(False)
            self._half_width_median = None
            self._manual_stems = set()
            widget.set_results(len(paths), {})
            return
        boxes_all = self.store.boxes_all_at(
            self.store.boxes_path(
                self.task_id, **self._node_scope(self.node_of_stage("detect"))
            )
        )
        # ⚠️ 顺手把**每页槽位**攒下来给全书判据用：判据要的是"整本书长什么样"，
        #    而这次遍历已经把每页都读出来了，第二次再读一遍 boxes.json 纯属白花
        #    （320 页时那是整本 JSON 的一次重复解析）。
        sampled: list[tuple[str, list, int]] = []
        #: 每页的框来源（auto / manual）：人工整幅页不参与「整幅→半幅」修正。
        origins: dict[str, str] = {}
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
            cached = self.detect_cache.get(str(path))
            disk_boxes, disk_origin = boxes_all.get(path.stem, ([], "auto"))
            raw = cached if cached is not None else disk_boxes
            origins[path.stem] = str(disk_origin or "auto")
            sampled.append((path.stem, list(raw or []), self._page_width_of(path, sizes)))
        # ⚠️ 全书判据**只算一次**：以前这里算一次、_book_note 里又算一次，
        #    2000 页的书等于白跑一遍（用户报「切类型卡顿」时排查到的重复项之一）。
        profile = profile_book(sampled)
        # 「整幅其实像半幅」的页（用户 2026-10-26，任务 0023）：统计与标注都要
        # 按**半幅**呈现，否则界面仍显示一堆「整幅」，和提交/拼版对不上。
        # 判据本体在 utils.book_layout，这里只负责按来源过滤（人工整幅不动）。
        half_width = profile.half_width_median
        self._half_width_median = half_width
        #: 人工框的页（磁盘 origin=manual）：显示层也不做「整幅→半幅」修正，
        #: 否则用户刚把某页改成整幅，下一次上屏又被自动翻回半幅。
        self._manual_stems = {
            stem for stem, source in origins.items() if source == "manual"
        }
        by_stem = {stem: (raw, width) for stem, raw, width in sampled}
        demoted: dict[str, list] = {}
        if half_width is not None:
            for stem in profile.demoted_full_pages:
                if origins.get(stem) == "manual":
                    continue
                raw, width = by_stem.get(stem, ([], None))
                corrected = full_to_half_slots(raw, width, half_width)
                if corrected != raw:
                    demoted[stem] = corrected
        classes: dict[str, list[tuple[int, str]]] = {}
        for row, path in enumerate(paths):
            raw, _width = by_stem[path.stem]
            slots = demoted.get(path.stem, raw)
            # ⚠️ 传给分类器的是**槽位**（保留 None）：单独页（双槽缺一侧）
            #    过滤掉 None 会被误判成整幅。
            classes.setdefault(classify_page_slots(slots), []).append(
                (row, self._page_label(path))
            )
        # ⚠️ 把整本书的结论交给预览控件：**半幅**标注靠它决定（见 styles.box_styles）。
        self._apply_book_layout(profile)
        widget.set_results(
            len(paths), classes, book_note=self._book_note_from(profile)
        )

    def _single_column_display(self) -> bool:
        """预览控件的全书结论（仅展示用；「半幅」标注已是页级判据）。

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
    def _apply_book_layout(self, profile) -> None:
        """把整本书的形态结论同步给预览控件（供统计/文案）。

        ⚠️ 本页「半幅」标注已是**页级判据**（用户 2026-10-23，任务 0004），
        不再依赖这条结论；同步它只是保留全书结论的唯一入口。整幅书里的可疑
        半幅不改标注（用户 2026-10-17 选择「只警告」），那条只进统计面板文案。
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
                suspicious_summary(profile),
                demoted_full_summary(profile),
                single_column_summary(profile),
            ) if text
        )

    @staticmethod
    def _book_note(sampled) -> str:
        """原始页表 → 提示（内部算 profile；批量场景请用 :meth:`_book_note_from`）。"""
        return DetectStatsMixin._book_note_from(profile_book(sampled))

    def _goto_stats_page(self, row: int) -> None:
        """统计明细里点了页码 → 预览跳到那一页（联动框重读）。"""
        strip = self.detect_viewer.strip
        if 0 <= row < strip.count():
            strip.setCurrentRow(row)
