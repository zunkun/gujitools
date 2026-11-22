# -*- coding: utf-8 -*-
"""独立拼图页的导出执行线与页面刷新/收尾（从原 ``page.py`` 拆出）。"""

from __future__ import annotations

from pathlib import Path

from desktop.services.imposition import (
    FILE_FMT,
    WHITE_BACKGROUND,
    compose_doc,
    flatten_onto_background,
)
from desktop.steps import StepRequest

from .paths import _page_overrides


class ExportMixin:
    """导出 job、进度/结果回调、视图刷新与离开/收尾。"""

    # ------------------------------------------------------------------ 导出
    def _compose_job(self, request: StepRequest, report) -> str | None:
        """执行内核的 job：把整份文档合成为图片（纯函数，线程里安全）。

        ⚠️ 写成 job 而不是页面方法，是为了让"跑什么"与"怎么跑/怎么汇报"
        分开——内核负责后者（线程 + 信号），本页只管前者。

        **手工修饰过的整页组合优先**：在预览弹窗中编辑后改出来的那张图
        存在 ``singletask/拼图/edited/`` 里（见 :meth:`_open_spread_edit`），
        这里在整套合成之上把它按页盖回去——不盖的话，用户改完一看导出的
        成品还是老样子（这就是"编辑没生效"）。
        """
        doc = request.args["doc"]
        dest = request.dest
        # job 契约：导出一定带输出目录（执行内核总会把 dest 设好）
        assert dest is not None, "拼图导出 job 必须带输出目录"
        dest = Path(dest)
        # ⚠️ 页数按 **compose_doc 的过滤后口径**取（``normalize_page`` 会静默
        #    丢掉不可修复的页），否则这里算出的分母与合成循环报的分母不一致，
        #    进度条会在末页突然倒退。``_page_overrides`` 用的也是这套口径。
        pages = len(_page_overrides(doc))
        # 逐页进度：``compose_doc`` 合成一页报一次（内核转成 progress 信号）。
        # ⚠️ report 为 None 时整条链都不汇报（内核正常运行时一定非None，
        #    但 job 契约允许"只干活"——既有自测就是这么直接调本 job 的）。
        # ⚠️ **白底导出**（2026-10-13 用户）：singletask 导出的 PNG 就是最终
        #    交付物，透明底在看图软件里不合理。任务流程的 ``stages/imposition``
        #    仍走默认透明底（PDF 侧压平白纸、编辑器要透明），互不影响。
        written = compose_doc(
            doc, dest,
            report=None if report is None else (
                lambda done, total: report(
                    "progress", {"done": done, "total": total}
                )
            ),
            background=WHITE_BACKGROUND,
        )
        overrides = _page_overrides(doc)
        for index, source in enumerate(overrides):
            if source is None or not source.is_file():
                continue
            target = dest / FILE_FMT.format(index + 1)
            try:
                # ⚠️ 手改页也压到**白底**（不能原样复制）：手改缓存是编辑器
                #    写出的 RGBA（透明底），原样盖回去的话同一批成品里就
                #    "合成页白底、手改页透明"两种底。
                flatten_onto_background(source, target, WHITE_BACKGROUND)
            except OSError:
                continue  # 盖不上就当没手改过，至少合成结果还在
            if target not in written:
                written.append(target)
        # ⚠️ 合成那 100% **不等于整轮跑完**：手改整页组合还要一页页盖回去。
        #    这里再报一轮"盖回 n/N"，否则进度条会在还有活儿的时候显示完成。
        # ⚠️ ``report`` 可能是 None——job 契约是"可只干活不汇报"（既有自测就是
        #    直接传 None 调本job 的），所以每处汇报前都要判，别假定它可用。
        edited = sum(1 for s in overrides if s is not None and s.is_file())
        if edited and report is not None:
            for index in range(edited):
                report("progress", {
                    "done": pages + index + 1,
                    "total": pages + edited,
                })
        self._export_result["count"] = len(written)
        return str(request.dest)

    def _export(self) -> None:
        """把整份文档合成为 PNG（后台线程，避免大图阻塞界面）。"""
        # 面板旋转组件的改动可能还挂在防抖里（转住没停满 250ms 就点导出）：
        # 先停表补报，导出的 doc 才是最新版面。
        self._rotate_commit_timer.stop()
        self.view.flush_pending()
        pages = self._doc.get("pages") or []
        if not pages:
            self.toast("warning", "没有拼版页", "请先把图片拖到上面的输入框，再拼版。")
            return
        if self.kernel.busy():
            self.toast("warning", "正在导出", "上一次导出还没结束，请稍候。")
            return
        out_dir = self._out_dir
        if out_dir is None:
            # ⚠️ 默认输出目录沿用旧口径（源图旁边「拼图成品/」），但**不再每次
            #    弹选择框**：与其它单任务页一致，输出目录由「输出目录」按钮管
            #    （用户 2026-11-17：控制面板底部统一「输出目录/执行/中断」）。
            base = Path(self._sources[0]).parent if self._sources else Path.cwd()
            out_dir = base / "拼图成品"
            self._out_dir = out_dir

        self.export_button.setEnabled(False)
        # 再导一次：上一轮的「查看处理文件」先收起，成功后按新目录再亮
        self.view_output_button.setVisible(False)
        # 先点亮进度条再起线程：极小的一批可能瞬间跑完，先亮才不会被收尾盖掉
        self.progress_row.start()
        self.status("正在导出…", "info")
        self.log(f"开始导出 {len(pages)} 页 → {out_dir}")
        self._export_result = {}
        request = StepRequest(dest=out_dir, args={"doc": dict(self._doc)})
        if not self.kernel.run(request):
            self.export_button.setEnabled(True)
            self.progress_row.reset()
            self.status("正在导出", "warning")

    def _on_progress(self, done: int, total: int) -> None:
        """一条执行进度：喂给右栏那条进度行。"""
        self.progress_row.update(done, total)

    def _on_exported(self, out_dir: str) -> None:
        """导出成功：恢复按钮、进度条走到头并提示，亮出「查看处理文件」。"""
        count = int(self._export_result.get("count", 0))
        self.export_button.setEnabled(True)
        self._last_output = Path(out_dir)
        self.view_output_button.setVisible(True)
        self.progress_row.succeed(
            f"完成 {count} 页" if count else "已完成"
        )
        self.status(f"导出完成：{out_dir}（{count} 页）", "success")
        self.log(f"导出完成：{count} 页 → {out_dir}")
        self.toast("success", "导出完成", f"共导出 {count} 页到：\n{out_dir}")

    def _open_last_output(self) -> None:
        """「查看处理文件」：资源管理器打开最近一次导出的目录。"""
        if self._last_output is None:
            return
        from desktop.utils.files import reveal_in_explorer

        reveal_in_explorer(self._last_output)

    def _on_export_failed(self, message: str) -> None:
        """导出失败：恢复按钮、进度条停住并提示。"""
        self.export_button.setEnabled(True)
        self.progress_row.fail()
        self.status("导出失败", "error")
        self.log(f"导出失败：{message}")
        self.toast("error", "导出失败", message)

    # ------------------------------------------------------------------ 刷新
    def _refresh_view(self) -> None:
        """把当前文档灌进拼版视图（页清单 + 画布），并同步面板状态。"""
        pages = self._doc.get("pages") or []
        current = min(self.view.current_index(), len(pages) - 1)
        self.view.set_pages(pages, current=current if current >= 0 else -1)
        self._refresh_page_thumbs()
        self._refresh_panel()
        self.export_button.setEnabled(bool(pages))

    # ------------------------------------------------------ 离开/回来（内存）
    def release_buffers(self) -> None:
        """离开本页：画布两张大图 + 左列缩略图 + 缩略图实体管理者的内存位图。

        基类只清 ``view`` 自己那份（画布与左列条目），这里再补管理者那张
        ``_pix`` 表——它挂在**页面**上，不在 view 里。
        """
        super().release_buffers()
        manager = getattr(self, "_page_thumb_mgr", None)
        if manager is not None:
            manager.release_pixmaps()

    def restore_buffers(self) -> None:
        """回来：按磁盘上的文档整条重灌（画布 + 左列缩略图 + 面板状态）。"""
        self._refresh_view()

    # ------------------------------------------------------------------ 收尾
    def shutdown_workers(self) -> None:
        """关闭页面前中止并等待导出线程。"""
        try:
            self.view.flush_pending()
        except RuntimeError:
            pass
        self.kernel.shutdown()
        super().shutdown_workers()
