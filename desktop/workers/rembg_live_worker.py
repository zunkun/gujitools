# -*- coding: utf-8 -*-
"""单页实时去底色的后台 worker（第三步「改参数 / 翻页实时预览」专用）。

与 ``PreviewWorker`` 的分工：那个只负责**显示**（读图 / 按区域裁剪 / 缩放），
本 worker 负责**计算 + 增量落盘**：算完当前页后
①把结果落实时暂存目录（``services.rembg_live.live_dir``）供预览区显示；
②把该页去底色结果**增量**复制进正式预览目录 ``stages/rembgpreview[~节点]``；
③按 area/border 规则合成的「应用图」落 ``stages/rembg[~节点]``（可多张）。

去底色对整页图（数千像素）要百毫秒级 CPU，放主线程会卡住界面，因此一律
丢到 QThread 里跑。结果通过 token 回传，宿主据此丢弃"已经过期的"结果
（用户连拖两次滑块时，慢的那次回来得晚，不能覆盖新的）。

⚠️ 增量落盘的两条硬约定（用户 2026-10-18）：写「应用图」**之前**先落
``.draft`` 哨兵——``stages/rembg`` 里有零星文件**不代表本步已提交**，第四步
只有在该哨兵不存在时才认这个目录（见 ``store.rembg_submit_committed``）。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal


class RembgLiveWorker(QObject):
    """一次性 worker：单页去底色 + 增量落盘（预览目录 / 应用图目录）。"""

    #: (token, 结果图片路径)——预览区显示用（渲染那单才有意义）
    finished = Signal(object, str)
    #: (token, 错误信息)
    failed = Signal(object, str)
    #: (token, 写出的应用图文件名, 错误信息)——增量落盘结果
    applied = Signal(object, list, list)

    def __init__(
        self,
        image_path: str,
        args: dict,
        out_dir: str,
        token: object,
        *,
        render: bool = True,
        preview_out: str | None = None,
        apply_out: str | None = None,
        jobs: list[dict] | None = None,
        draft_marker: str | None = None,
        base_path: str | None = None,
    ) -> None:
        """参数:
        image_path: 待去底色的源图（extract 产物）。
        args: rembg 面板收集的参数（offset/type/seal/…）。
        out_dir: 实时暂存目录（``services.rembg_live.live_dir``）。
        token: 本次请求的标识，供宿主判断结果是否已过期。
        render: 是否重算去底色。``False`` 时（只改了 area/border）直接用
            ``base_path`` 那份已完成的结果重合成「应用图」，不重复去底色。
        preview_out: 正式预览目录（``stages/rembgpreview[~节点]``）；渲染那单
            会把结果增量复制进去。
        apply_out: 「应用图」目录（``stages/rembg[~节点]``）。
        jobs: 提交作业（``print_plan.plan_submit_job`` 产出），逐条合成落盘。
        draft_marker: 写应用图前先落的哨兵文件（``stages/rembg[~节点]/.draft``）。
        base_path: ``render=False`` 时的源图（该页已落盘的去底色结果）。
        """
        super().__init__()
        self._image_path = image_path
        self._args = dict(args)
        self._out_dir = out_dir
        self._token = token
        self._render = bool(render)
        self._preview_out = preview_out
        self._apply_out = apply_out
        self._jobs = list(jobs or [])
        self._draft_marker = draft_marker
        self._base_path = base_path
        self._cancelled = False

    def cancel(self) -> None:
        """请求放弃计算。token 守卫只丢**结果**不省**算力**：连拖滑块时
        每次派发都先取消上一单，别让几个 numpy 重活同时抢 GIL
        （2026-09-26 第二轮审计 L2）。"""
        self._cancelled = True

    def run(self) -> None:
        """线程入口：算完发 finished / applied，异常发 failed（不抛到线程外）。

        ⚠️ 取消路径也必须发终态信号（finished/failed 之一），否则线程事件
        循环永不退出（SourceThumbnailsWorker 同款教训）；空路径结果由宿主
        按 token 丢弃。
        ⚠️ ``QThread.run()`` 必须 try/except：异常逃出线程＝"点了没反应"。
        """
        if self._cancelled:
            self.finished.emit(self._token, "")
            return
        from desktop.services.rembg_live import apply_effects

        out_path = ""
        try:
            if self._render:
                from desktop.services.rembg_live import render_page

                out_path = render_page(self._image_path, self._args, self._out_dir)
            else:
                out_path = str(self._base_path or "")
        except Exception as exc:  # noqa: BLE001 — 子线程异常必须回传主线程
            self.failed.emit(self._token, f"{type(exc).__name__}: {exc}")
            return
        # ⚠️ **显示优先**（用户 2026-10-18）：去底色一算完就把结果交回主线程上屏，
        #    「写正式产物目录」是纯落盘（拷预览 + 合成应用图 + 透明 PNG 编码，
        #    几百毫秒），**不该让大图等它**——以前把 finished 放在落盘之后，
        #    用户看到的就是"界面卡着、效果迟迟不上屏"。
        self.finished.emit(self._token, out_path)
        saved: list[str] = []
        errors: list[str] = []
        if self._render and self._preview_out:
            try:
                self._copy_to_preview(out_path)
            except Exception as exc:  # noqa: BLE001 - 落盘失败不许拖垮显示
                errors.append(f"{type(exc).__name__}: {exc}")
        if self._jobs and self._apply_out:
            try:
                # ⚠️ 先哨兵后写图：保证"应用图目录里有文件"必然伴随哨兵存在，
                #    第四步不会把增量产物误当"已提交"（无窗口可钻）。
                self._write_draft_marker()
                source = out_path if self._render else str(self._base_path or "")
                names, apply_errors = apply_effects(
                    source, self._jobs, self._apply_out
                )
                saved, errors = names, errors + apply_errors
            except Exception as exc:  # noqa: BLE001 - 落盘失败不许拖垮显示
                errors.append(f"{type(exc).__name__}: {exc}")
        self.applied.emit(self._token, saved, errors)

    # -------------------------------------------------------------- 增量落盘
    def _copy_to_preview(self, live_path: str) -> None:
        """把实时结果**原子**复制进正式预览目录（``stages/rembgpreview``）。

        ⚠️ 原子写：``stages/rembgpreview`` 可能正被提交/第四步读，半张文件会
        被当成有效产物（与缩略图同一套理由，见 ``rembg_stage._save_step4_thumb``）。
        内容与实时结果逐像素一致（同一份 ``utils.rembg_page`` 产物）；正式全量
        「生成预览」会整目录覆盖它。
        """
        if not self._preview_out or not live_path:
            return
        from utils.file_utils import write_bytes_atomic

        target = Path(self._preview_out) / f"{Path(self._image_path).stem}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(target, Path(live_path).read_bytes())

    def _write_draft_marker(self) -> None:
        """落 ``.draft`` 哨兵：标记"这个应用图目录是增量拼出来的、尚未提交"。"""
        if not self._draft_marker:
            return
        from utils.file_utils import write_bytes_atomic

        marker = Path(self._draft_marker)
        marker.parent.mkdir(parents=True, exist_ok=True)
        write_bytes_atomic(marker, b"")
