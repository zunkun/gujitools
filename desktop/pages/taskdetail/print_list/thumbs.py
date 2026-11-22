# -*- coding: utf-8 -*-
"""待打印图的缩略图供给与预热（从原 ``print_list.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from desktop.pages.taskdetail.print_list._qt import QTimer
from desktop.pages.taskdetail.print_list.constants import PRINT_WARM_DELAY_MS
from desktop.pages.taskdetail.print_list.helpers import _file_stamp
from desktop.utils.files import THUMBNAIL_EDGE

if TYPE_CHECKING:
    from desktop.pages.taskdetail.print_list._host import PrintListHost
else:
    PrintListHost = object


def _book_key(path: Path) -> str:
    """延迟从本包取 ``book_key``：自测按 ``print_list.book_key`` 打桩计数。"""
    from desktop.pages.taskdetail import print_list as _pkg

    return _pkg.book_key(path)


class PrintThumbsMixin(PrintListHost):
    """缩略图缓存键、预热节流与失效重刷。"""
    def _print_thumb_provider(self, file_text: str):
        """第四步缩略条的小图来源：一律给**已生成的小图**，不现解码原图。

        查找顺序：
        1. 入口图片（``thumbnails/input/``，导入即生成）；
        2. 去底色成品（``thumbnails/print[~<节点>]/<图名>.jpg``，第三步执行时生成）；
        3. **PDF排版统一缓存**（``thumbnails/print_manage/``，本步进入时后台生成）
           ——拼版成品、手动「插入图片」的外部图都靠它，管理弹窗才不用同步
           解码 85 张原图（用户 2026-11-02「弹窗打开慢」）。
        都没有时返回 ``None``（调用方决定要不要回落原图；管理弹窗不再回落）。

        ⚠️ **缩略图目录按节点取**（B 方案）：两个「图片去底色」节点各有各的成品
        产物目录，缩略图缓存也跟着分（``thumbnails/print[~<节点>]``）。这里从
        **产物自己的目录名**反推节点后缀（与写入端 ``rembg_stage.py`` 同一份
        规则，见 :func:`desktop.steps.ports.node_scope_from_output_dir`）——比按
        界面当前节点取更准：第四步消费的是**上游那个**节点交的图，未必是当前选中
        的节点。

        ⚠️⚠️ **结果按 (路径, 大小+mtime) 记住**（``_print_thumb_paths``）：同一页
        在一次进页面里会被问**两遍**——``_warm_print_thumbs`` 一遍、缩略图条
        ``_load_page_thumbs`` 一遍（用户 2026-11-21 报「任务 0032 点进详情有些
        慢」的根因：343 页 × 2 遍 × 每遍 2 次 ``book_key``＋3 次 ``stat``）。
        命中记忆时只付 **1 次 stat**；源图被覆盖（mtime/大小变）自然落回重算，
        切任务时整份清掉（见 ``TaskDetailPage.set_task``）。
        """
        if not self.task_id:
            return None
        page = Path(file_text)
        memo = self.__dict__.setdefault("_print_thumb_paths", {})
        stamp = _file_stamp(page)
        if stamp is not None:
            hit = memo.get(file_text)
            if hit is not None and hit[0] == stamp:
                return hit[1]

        def _remember(value):
            if stamp is not None:
                memo[file_text] = (stamp, value)
            return value

        try:
            # 入口图片的预生成小图优先（按图键缓存，命中即用）
            entry = self.store.entry_thumb_path(self.task_id, page)
            if entry is not None:
                return _remember(entry)
        except (OSError, ValueError):
            return None
        from desktop.steps.ports import node_scope_from_output_dir

        parent = page.parent
        # 去底色成品目录恒为 ``stages/rembg`` 或 ``stages/rembg~<节点>``。
        if parent.parent == self.store.task_dir(self.task_id) / "stages" and (
            parent.name == "rembg" or parent.name.startswith("rembg~")
        ):
            thumb_dir = (
                self.store.task_dir(self.task_id)
                / "thumbnails"
                / f"print{node_scope_from_output_dir(parent.name)}"
            )
            thumb = thumb_dir / f"{page.stem}.jpg"
            try:
                if (
                    thumb.is_file()
                    and thumb.stat().st_mtime >= page.stat().st_mtime
                    and thumb.stat().st_size >= 512
                ):
                    return _remember(thumb)
            except OSError:
                return None
        # PDF排版统一缓存（拼版成品 / 手动插入图 / 其它来源）
        try:
            from desktop.workers.thumb_cache_worker import (
                cache_usable,
                stat_mtime,
            )

            manage = (
                self.store.print_manage_thumbnails_dir(self.task_id)
                / f"{_book_key(page)}.jpg"
            )
            if cache_usable(manage, stat_mtime(page)):
                return _remember(manage)
        except (OSError, ValueError):
            return None
        return _remember(None)

    def _schedule_print_thumbs_warm(self, files) -> None:
        """把"补生成待打印缩略图"**推迟到首帧之后**（``PRINT_WARM_DELAY_MS``）。

        为什么不在 ``_print_entries`` 里直接调 :meth:`_warm_print_thumbs`：
        那次调用要对**全部**待打印图逐条查一遍缩略图缓存（一本 343 页的书
        = 343 次路径查询，实测 ~470ms），而它服务的是「管理图片」弹窗——
        用户此刻还没点开，先让列表上屏才对（用户 2026-11-21：「点任务进详情
        有些慢」）。

        ⚠️ 「管理图片 / 插入图片」两个入口仍**同步**调 ``_warm_print_thumbs``：
        它们紧接着就要用缓存，等定时器就来不及了（见各自调用处）。

        ⚠️ 待办表是**合并覆盖**而不是累加：连续两次刷新（比如刚进来又改了参数）
        只按最新那份清单派发，不会把上一份里已删除的图又生成一遍。
        """
        self._print_warm_pending = [
            str(item or "") for item in (files or ()) if str(item or "").strip()
        ]
        timer = self.__dict__.get("_print_warm_timer")
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._run_print_thumbs_warm)
            self._print_warm_timer = timer
        timer.start(PRINT_WARM_DELAY_MS)

    def _run_print_thumbs_warm(self) -> None:
        """定时器到期：真正去查缓存、缺什么生成什么（用户在界面里了）。"""
        files = self.__dict__.pop("_print_warm_pending", None) or []
        if not files or not self.task_id:
            return
        self._warm_print_thumbs(files)

    def _warm_print_thumbs(self, files) -> None:
        """PDF排版缩略图**后台预生成**到 ``thumbnails/print_manage/``。

        用户 2026-11-02：「管理图片」弹窗打开慢——它构造时逐条同步解码原图。
        这里在**进入本步 / 列表刷新**时就把待打印条目（连同已删除条目，供
        「删除恢复」页签用）的小图生成好，弹窗只读小图。

        ⚠️ 与 ``_warm_entry_thumbs`` 同样按 ``(路径, mtime)`` 记账：读不出来的
        坏图永远写不出缓存，不记账会在每次刷新时反复派发同一批。

        ⚠️ **进页面那条路不要直接调它，走** :meth:`_schedule_print_thumbs_warm`：
        本方法要对**全部**待打印图逐条查一遍缓存（343 页 = 343 次路径查询），
        直接放在 ``_print_entries`` 里就把这笔钱记在"进页面"账上了。
        """
        if not self.task_id:
            return
        cache_dir = self.store.print_manage_thumbnails_dir(self.task_id)
        candidates: list[Path] = []
        for item in files or ():
            text = str(item or "")
            if text:
                candidates.append(Path(text))
        if not candidates:
            return
        from desktop.workers import connect_queued
        from desktop.workers.thumb_cache_worker import (
            ImageThumbCacheWorker,
            stat_mtime,
        )

        warmed = self.__dict__.setdefault("_print_thumb_warmed", {})
        todo: list[Path | str] = []
        for path in candidates:
            # 已有可用小图（入口图 / 去底色成品 / 本缓存）就不用再渲一份：
            # 85 页去底色成品若都往 print_manage 复制一遍，等于白解码 85 次。
            if self._print_thumb_provider(str(path)) is not None:
                continue
            mtime = stat_mtime(path)
            key = str(path)
            if warmed.get(key) == mtime:
                continue  # 已请求过且源没变（多为读不出来的坏图）
            todo.append(path)
            warmed[key] = mtime
        if not todo:
            return
        worker = ImageThumbCacheWorker(todo, cache_dir, edge=THUMBNAIL_EDGE)
        owner_task = self.task_id
        # ⚠️ ``thumbnail_ready`` 第三参数是**缓存文件路径**（见 worker 的信号
        #    注释），而弹窗按**源图路径**认条目；这里用 index → 源图 的回溯，
        #    别把缓存路径直接当 file 传进去（那样一格都匹配不上）。
        sources = list(todo)
        self.run_worker(
            lambda: worker,
            lambda w, thread: (
                connect_queued(
                    self,
                    w.thumbnail_ready,
                    lambda index, _image, _cache, o=owner_task, p=sources:
                    self._on_print_thumb_ready(
                        o, str(p[index]) if 0 <= index < len(p) else "",
                    ),
                    thread,
                ),
                connect_queued(
                    self,
                    w.completed,
                    lambda o=owner_task: self._on_print_thumbs_warmed(o),
                    thread,
                ),
                w.completed.connect(thread.quit),
                w.failed.connect(thread.quit),
            ),
        )

    def _on_print_thumb_ready(self, owner_task: str, path: str) -> None:
        """一张缩略图生成好：管理弹窗正开着就就地换掉那一格。

        ⚠️ 同时把这张图的**路径记忆**丢掉：记忆里可能还压着"没有小图"（``None``），
        不丢的话缩略图条下次刷新仍按原图解码（用户看不到刚生成的小图）。
        """
        if owner_task != self.task_id:
            return
        self.__dict__.get("_print_thumb_paths", {}).pop(str(path), None)
        panel = getattr(self, "_manage_panel", None)
        if panel is not None and panel.isVisible():
            panel.refresh_thumb(str(path))

    def _on_print_thumbs_warmed(self, owner_task: str) -> None:
        """整批缩略图生成完：管理弹窗还开着就整体刷一遍（此时都命中缓存）。"""
        if owner_task != self.task_id:
            return
        # 整批落盘 ⇒ 整份路径记忆作废（否则那批 None 会一直压着）
        self.__dict__.get("_print_thumb_paths", {}).clear()
        panel = getattr(self, "_manage_panel", None)
        if panel is not None and panel.isVisible():
            panel.refresh_thumbs()

    def _print_image_size(self, path_text: str) -> tuple[int, int] | None:
        """某张待打印图片的**当前**像素尺寸（只读文件头，不解码整图）。

        给 ``plan_print_entries`` 当 ``size_for``：逐页 rect 是**用户按当时那张图**
        摆出来的坐标，图像一换（拼版成品重合成、去底色重提交、编辑器回写）旧框
        就不该再套（用户 2026-10-18：「上一步的输出归上一步，当前步 PDF排版，页面
        效果都要按相关参数来调整」）。
        """
        from PySide6.QtGui import QImageReader

        try:
            size = QImageReader(path_text).size()
        except Exception:  # noqa: BLE001 - 坏图/占用：当作读不到（旧框保留）
            return None
        if not size.isValid() or size.width() <= 0 or size.height() <= 0:
            return None
        return (size.width(), size.height())

    def _report_updated_print_images(self, stale: list[dict]) -> None:
        """把"哪几张图被上游更新了、旧版面已按本步参数重排"记进日志（去重）。

        ⚠️ ``_print_entries`` 在切步骤/后台合成收尾/开关变化时都会被调到，
        无条件打日志会刷屏——同一批（路径 + 当前尺寸）只报一次。
        """
        if not stale:
            return
        signature = tuple(
            (str(page["file"]), tuple(page["image"])) for page in stale
        )
        if getattr(self, "_logged_stale_rects", None) == signature:
            return
        self._logged_stale_rects = signature
        names = "、".join(Path(page["file"]).name for page in stale[:6])
        if len(stale) > 6:
            names += f" 等 {len(stale)} 张"
        self.log_view.append(
            f"图片已更新（{names}）：原版面是按旧图尺寸摆的，"
            "已改按当前 PDF排版参数重新排版。"
        )

    def _drop_updated_print_thumbs(self, stale: list[dict]) -> None:
        """更新过的图片：把它在**待打印缩略图缓存**里的那条删掉，下次现解新图。

        ``thumbnails/print[~<节点>]/<图名>.jpg`` 是第三步「执行去底色」时预生成的
        小图；它自带 ``mtime 不旧于源图`` 的有效性判据（改过的图本来就会回落真图），
        这里再**主动删掉**是因为用户要求"更新过的图片不要留旧缓存"（2026-10-18）：
        留着那份文件，翻目录/排查时看到的仍是旧像素。
        """
        if not self.task_id:
            return
        stems = {
            Path(page["file"]).stem for page in stale if page.get("file")
        }
        if not stems:
            return
        thumbs_root = self.store.task_dir(self.task_id) / "thumbnails"
        if not thumbs_root.is_dir():
            return
        for directory in thumbs_root.glob("print*"):
            # 目录名形态 ``print`` / ``print~<节点>``（与 _print_thumb_provider 同源）
            if not directory.is_dir() or not directory.name.startswith("print"):
                continue
            for stem in stems:
                try:
                    (directory / f"{stem}.jpg").unlink(missing_ok=True)
                except OSError:
                    pass
