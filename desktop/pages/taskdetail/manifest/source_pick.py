# -*- coding: utf-8 -*-
"""选择/替换源文件：后台算指纹、查重确认、换源后复位产物。"""

from __future__ import annotations

from pathlib import Path
from qfluentwidgets import MessageBox
from desktop.utils.files import default_open_dir
from desktop.workers import HashWorker, connect_queued
from ._qt import QFileDialog, QWidget
from typing import TYPE_CHECKING, Any, Callable, cast


class ManifestSourcePickMixin:
    """选择与替换源文件（指纹 / 查重 / 产物复位）。"""

    if TYPE_CHECKING:
        # 宿主页面/同级 Mixin 提供的成员（类型检查专用，运行期无副作用）
        _dismiss_source_prompt: Any
        _missing_input_kind: Any
        _prompt_missing_source: Any
        _refresh_source_actions: Any
        _toast: Any
        detect_cache: Any
        run_worker: Any
        set_task: Any
        source_path: Any
        store: Any
        task_id: Any

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """窗口尺寸变了：让「缺源 PDF」提示层**跟着重铺**。

        ⚠️ 这正是 qfluentwidgets ``MaskDialogBase`` 踩的坑（用户2026-10-06
        截图：遮罩只盖住页面左上角一小块）：它只在**构造那一刻**读一次
        ``parent.width()``，之后不跟随。我们的提示层每次显示都重铺，但**显示
        期间**窗口还会变（用户拖窗口、最大化），所以这里再补一次。

        ⚠️⚠️ **别用 ``prompt.isVisible()`` 当条件**（用户 2026-10-06 报"第一次
        进入没有弹窗、第二次才有"）：``set_task`` 是**先于**
        ``setCurrentWidget`` 跑的（见 :meth:`ModuleShell.open_detail`），那一刻
        页面还没被显示，``show()`` 过的子控件 ``isVisible()`` 仍为 **False**
        （Qt 的 isVisible 看整条祖先链）。于是"首次进入"这一路恰好被这个条件
        拦掉，留在 ``640x480`` 时代算出的**零高度**遮罩上（实测
        ``mask=(0, 491, 640, 0)``）——用户看到的就是"压根没弹"。
        重铺一个隐藏的层是无害的，所以这里只判"有没有建过"。
        """
        # 宿主 MRO 里 QWidget 会接住（Mixin 的静态 super() 视图看不到）
        super().resizeEvent(event)  # type: ignore[reportAttributeAccessIssue]
        prompt = getattr(self, "_source_prompt", None)
        if prompt is not None:
            prompt._reanchor()
            prompt.card_host_center()

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        """页面真正显示出来：把「缺源 PDF」提示层铺到**最终**尺寸上。

        ⚠️⚠️ 这是"第一次进入不弹"的**正主修复**（用户 2026-10-06报障）。
        第一次进入时序是 ``set_task`` → ``setCurrentWidget``，而 ``set_task``
        里就调了 ``show_prompt()``：那一刻详情页刚被 ``addWidget`` 进栈、**还没
        布局**，尺寸是 QWidget 默认的 ``640x480``、``_content_top()`` 返回布局
        未跑时的垃圾值（实测 491）。遮罩于是是 ``(0, 491, 640, 0)``——**高度
        0**，看上去就是"没弹"。

        ``showEvent`` 是布局与尺寸都已就绪的第一个时刻（QStackedWidget 切页会先
        resize 子控件再 show），在这里重铺一次就对了。⚠️ 别改成"在
        ``set_current`` 里同步重铺"：那时候尺寸同样还是旧的。

        这里也**顺带兜住"每次进入都弹"**：用户答过「稍后再说」再切回来时，
        ``set_task`` 跑在页面还看不见的时候，``show_prompt()`` 铺的是旧几何；
        真正显示出来时这一句会重新 ``show_prompt()``（内部先重铺再 show），
        用户看到的才是铺好的那一版。
        """
        # 宿主 MRO 里 QWidget 会接住（Mixin 的静态 super() 视图看不到）
        super().showEvent(event)  # type: ignore[reportAttributeAccessIssue]
        # ⚠️⚠️ **必须先判 ``task_id``**：详情页是 ``addWidget`` 进栈的，那一下就会
        # 触发 ``showEvent``——**早于第一次 ``set_task``**，此时 ``task_id`` 还是
        # ``None``。而 ``_missing_source()`` 会拿它去查流程图，
        # ``store.task_dir(None)`` 直接抛 ``ValueError``（自测实测：整个自测进程
        # 都被这一个未捕获异常打断）。这不是"理论上不会发生"——它每次建页都发生。
        if not self.task_id:
            return
        if not self._missing_input_kind():
            return
        prompt = getattr(self, "_source_prompt", None)
        if prompt is None:
            # ⚠️ 正常不会走到（``set_task`` 里已建）；真走到说明那条路径被改
            #    过，这里补建一次，别让用户看不到任何提示。
            self._prompt_missing_source()
            prompt = getattr(self, "_source_prompt", None)
        if prompt is not None:
            prompt.show_prompt()

    def _on_source_prompt_dismissed(self) -> None:
        """用户答「稍后再说」/点了遮罩：只收提示，其余一概不动。

        ⚠️ **不碰**高亮与红字——它们要一直留着，直到真的补上文件（那是用户
        反复需要看到的路标，不是"看一眼就消失的提示"）。
        """

    def _content_top(self) -> int:
        """要遮盖区域的**上沿 y**（页内坐标）＝**页头下沿 + 间距**。

        给 :class:`MissingSourcePrompt` 当 geometry 用。

        ⚠️⚠️ **只能用页头算，不能用步骤条**（这一点踩了两层坑）：

        1. ``_rebuild_step_bar`` 是 ``removeWidget`` + ``insertWidget`` 换的
           控件，Qt 的布局是**延迟**生效的，``set_task`` 末尾那一刻新步骤条
           **还没被定位**——``geometry()`` 仍是 QWidget 默认的 640×480、
           ``isHidden()`` 为 True，``mapTo`` 得到的 y 是 **0**。用它算，遮罩
           会从页头顶上盖下来，"按钮留在遮罩之上"当场作废（库里那个遮罩 bug
           也是同一个根因）。
        2. 连 ``layout.activate()`` 都不管用：那对 ``removeWidget`` +
           ``insertWidget`` 之后的结构不重排（实测 itemAt(row) 仍是 640×480）。

        **页头卡片是稳定的**——它构造后再没被换过，``itemAt(0)`` 的 geometry
        一直是准的（实测 bottom=74 + 间距 12 = 86，正好是步骤条该在的 y）。
        """
        layout = getattr(self, "_root_layout", None)
        if layout is not None:
            item = layout.itemAt(0)
            if item is not None and item.geometry().height() > 0:
                return max(0, item.geometry().bottom() + layout.spacing())
        # 兜底：页头控件自己的位置（万一根布局还没跑）
        header = getattr(self, "header_card", None)
        if header is not None:
            from PySide6.QtCore import QPoint

            return max(0, header.mapTo(self, QPoint(0, 0)).y() + header.height())
        return 0

    def _on_pick_source(self) -> None:
        """页头「选择 PDF」：给任务补上 / 更换源文件（用户 2026-10-06）。

        为什么需要它：创建任务时 PDF **非必需**（用户明确要求），所以会有
        "空壳任务"；另外源文件被移走/删除时也走这里自救。

        ⚠️ **先算指纹再决定**（用户 2026-10-06 第 3 条的判据）：几百 MB 的
        PDF 算一次 SHA-256 要一两秒，所以指纹走**后台**（``HashWorker``），
        算完才进 ``_on_source_hash_ready`` 走三条分支：

        - **这个 PDF 已经在这个任务里** ⇒ 什么都不做（重复选同一个文件，
          换过去等于什么都没变，还要白清一遍产物）；
        - **这个 PDF 已在别的任务里** ⇒ **问一句**"是否仍然使用"，用户答
          "仍然使用"才换（与列表页的查重确认同一个模式，见
          :meth:`_confirm_duplicate_source`）；
        - **是新的 PDF** ⇒ 换源之前先问一句（清空后果），确认后才换。

        ⚠️ 换文件等于换了整本书的内容，**已有的中间产物全部作废**（提取出来
        的图、检测框、去底色结果……都对应着旧文件）。不清理的话，界面上会
        同时摆着"旧书的页"与"新书的结果"。
        """
        if not self.task_id:
            return
        # ⚠️ 用**原生** QFileDialog（项目硬规则：「资源管理器」= 原生选择
        #    对话框，不是浏览窗口）。
        filename, _ = QFileDialog.getOpenFileName(
            cast("QWidget", self),
            "选择 PDF/DjVu 文件",
            str(default_open_dir()),
            "PDF/DjVu 文件 (*.pdf *.djvu *.djv)",
        )
        if not filename:
            return
        source = Path(filename)
        if not source.is_file():
            self._toast(
                "warning",
                "选择失败",
                f"「{source.name}」已经不在那个位置了，请重新选择。",
            )
            return
        self._set_picking_source(True)
        self._pending_source = source
        # ⚠️ 指纹计算**必须进后台**：一本 800MB 的书 SHA-256 要一两秒，
        #    放主线程就是界面白住一两秒（导入链路早就为此建了 HashWorker）。
        self.run_worker(
            lambda: HashWorker(source),
            lambda worker, thread: (
                connect_queued(
                    self,
                    worker.finished,
                    self._on_source_hash_ready,
                    thread,
                ),
                connect_queued(
                    self,
                    worker.failed,
                    self._on_source_hash_failed,
                    thread,
                ),
                worker.finished.connect(thread.quit),
                worker.failed.connect(thread.quit),
            ),
        )

    def _on_source_hash_failed(self, message: str) -> None:
        """指纹算不出来（文件被占用/权限不足/已被删除）。"""
        self._set_picking_source(False)
        self._toast("warning", "无法读取", f"{message}（未更换源文件）")

    def _on_source_hash_ready(self, path_text: str, source_hash: str) -> None:
        """指纹算完 → 三条分支的判据（见 :meth:`_on_pick_source`）。"""
        self._set_picking_source(False)
        source = self._pending_source or Path(path_text)
        self._pending_source = None
        if not self.task_id:
            return  # 算指纹这几秒里用户可能已经切走任务了

        current = (self.store.get_task(self.task_id) or {}).get("source_hash")
        if current and str(current) == source_hash:
            # 同一个文件又选了一遍：换过去等于什么都没变，还要清一遍产物
            self._toast(
                "info",
                "已经是当前文件",
                f"「{source.name}」就是这个任务正在用的源文件，无需更换。",
            )
            return
        duplicates = self.store.find_tasks(source_hash)
        if duplicates:
            # ⚠️ **问一句再决定，不是一律拒绝**（用户 2026-10-06："当前是不
            #    允许的，这个不合理。应该提示已经存在相同文件任务，是否继续
            #    等，跟外层一样"）。与列表页的查重确认同一个模式：把重复的
            #    事实与后果说清，用户答"仍然使用"就换。
            other = duplicates[0]
            if not self._confirm_duplicate_source(source, other):
                return
            # ⚠️ **不再问第二次**：清空后果已经写在这一个弹窗里了，连弹两次
            #    只是折磨用户。
            self._apply_source(source, source_hash, duplicate_of=other)
            return

        # 真的是新 PDF：换源前问一句（清空后果）
        if self.source_path is not None and not self._confirm_replace_source(source):
            return
        self._apply_source(source, source_hash)

    def _confirm_duplicate_source(self, source: Path, other: dict) -> bool:
        """这个 PDF 已在别的任务里 ⇒ 问"是否仍然使用"（``False`` = 取消）。

        ⚠️ 判据（有没有产物、要不要提清空）与弹窗**分开**——离屏自测绝不
        真弹模态（项目硬规则），自测把这个方法替掉就能验两条分支。

        文案**一次把两件事说清**（重复 + 清空后果），别让用户连点两个弹窗。
        """
        if not self._duplicate_source_needs_confirm(other):
            return True
        warning = ""
        if self._has_task_artifacts():
            # ⚠️ MessageBox 是**纯文本**、不解析 markdown：写 ** 粗体会让
            #    用户看到一串星号。要强调就靠措辞。
            warning = (
                "\n\n继续使用会把它换成本任务的源文件，已有的提取图片、"
                "检测框、去底色结果会被清空，四个步骤需要重新跑一遍。"
            )
        dialog = MessageBox(
            "已存在相同的文件",
            f"「{source.name}」的内容与任务「{other.get('name')}」"
            f"（{other.get('id')}）完全相同。\n\n"
            f"是否仍然用它作为本任务的源文件？{warning}",
            self,
        )
        dialog.yesButton.setText("仍然使用")
        dialog.cancelButton.setText("取消")
        return bool(dialog.exec())

    def _duplicate_source_needs_confirm(self, other: dict) -> bool:
        """该问吗（True = 需要问）。

        存在**别的**任务 ⇒ 一律问一句：重复内容是用户该知道的事实（他可能
        是想换个任务继续处理这本），替他决定不合适。本任务自己那条（选了
        一模一样的文件）不走这里，已经在 :meth:`_on_source_hash_ready` 里
        提前处理掉了。
        """
        return str(other.get("id") or "") != str(self.task_id or "")

    def _set_picking_source(self, picking: bool) -> None:
        """算指纹期间锁住按钮并换个提示（免得用户以为没点上）。"""
        self._picking_source = bool(picking)
        button = getattr(self, "source_button", None)
        if button is None:
            return
        button.setEnabled(not picking)
        if picking:
            button.setToolTip("正在读取文件…")
        else:
            self._refresh_source_actions()

    def _apply_source(
        self, source: Path, source_hash: str, duplicate_of: dict | None = None
    ) -> None:
        """确认过了 → 复制进任务目录、改索引、清旧产物、重载页面。

        ``duplicate_of`` 非空 = 用户明知"这个 PDF 已在任务X 里"仍选择使用
        （与列表页建任务时的 ``duplicate_confirmed`` 同一个意图）。这时提示
        里要点出"另一个任务也在处理同一本"，否则用户回头在两个任务的页面上
        看到同一批页，会以为哪里出了错。
        """
        # ⚠️ 调用方 _on_source_hash_ready 已保证有任务在身
        task_id = self.task_id
        assert task_id is not None, "换源时没有任务在身"
        replacing = self.source_path is not None
        # 复制进任务目录 + 改索引（store.set_task_source 内部做拷贝；失败
        # 返回 False 时不碰界面——索引指向一个不存在的文件比什么都不做更糟）
        try:
            ok = self.store.set_task_source(task_id, source, source_hash=source_hash)
        except OSError as exc:
            self._toast("error", "选择失败", f"{type(exc).__name__}: {exc}")
            return
        if not ok:
            self._toast(
                "warning",
                "选择失败",
                f"没能把「{source.name}」收进这个任务（文件可能已被移走）。",
            )
            return
        if replacing:
            self._reset_artifacts_for_new_source()
        # ⚠️ 补上文件了 ⇒ 提示层立刻收掉（它存在的理由已经消失）
        self._dismiss_source_prompt()
        if duplicate_of:
            self._toast(
                "info",
                "已使用相同文件",
                f"源文件：{source.name}（任务「{duplicate_of.get('name')}」"
                "用的也是同一本）。",
            )
        else:
            self._toast("info", "已选择", f"源文件：{source.name}")
        # 重载任务：走一遍 set_task 的全套（源路径、页头、清单、预览、步骤记忆）
        self.set_task(task_id)

    def _confirm_replace_source(self, source: Path) -> bool:
        """换源文件前的确认（``False`` = 取消）。

        ⚠️ 判据（"有没有中间产物"）在 :meth:`_source_replace_is_blocked`
        里，与弹窗分开——**离屏自测绝不真弹模态**（项目硬规则），自测把
        那个方法替掉就能验两条分支。
        """
        if not self._source_replace_is_blocked(source):
            return True
        dialog = MessageBox(
            "更换 PDF 源文件",
            f"确定把本任务的源文件换成「{source.name}」吗？\n\n"
            "已有的提取图片、检测框、去底色结果都对应着旧文件，"
            "换完会被清空，需要重新跑一遍。",
            self,
        )
        dialog.yesButton.setText("更换并清空")
        dialog.cancelButton.setText("取消")
        return bool(dialog.exec())

    def _source_replace_is_blocked(self, source: Path) -> bool:
        """该不该拦住这次替换：True = 需要用户确认，False = 直接换。

        有任何中间产物就要问一句（用户可能白跑了几十分钟）；什么都没有就
        静默换掉（此时换文件没有任何损失，问了只是多一次点击）。
        """
        return self._has_task_artifacts()

    def _has_task_artifacts(self) -> bool:
        """这个任务目录里有没有任何中间产物（页清单/执行记录/阶段输出）。"""
        task_id = self.task_id
        assert task_id is not None, "产物检查只会在任务态出现"
        try:
            names = ("pages.json", "runs.json", "boxes.json", "sizes.json")
            root = self.store.task_dir(task_id)
            for name in names:
                if (root / name).exists():
                    return True
            # ⚠️ **副本节点的同名副本也要算**（B 方案）：``pages~Node_3.json``
            #    / ``boxes~Node_2.json`` 同样是"跑过留下的东西"，漏了它们会
            #    在"换源文件"时既不提示、也不清理。
            for pattern in (
                "pages~*.json",
                "boxes~*.json",
                "sizes~*.json",
                "print~*.json",
            ):
                if next(root.glob(pattern), None) is not None:
                    return True
            stages = root / "stages"
            if stages.is_dir() and any(stages.iterdir()):
                return True
        except OSError:
            return False
        return False

    def _reset_artifacts_for_new_source(self) -> None:
        """换源文件后清掉旧书的中间产物（让下游必须重跑）。

        ⚠️ 只删**产物与清单**，不碰源文件副本（那个已经被新文件替换了）与
        流程图 ``flow.bpmn``（流程是用户配的，与源文件无关）。
        ⚠️ 逐个 ``unlink`` 且**吞掉异常**：某个文件被占用/无权限时不该让
        整个换源流程失败——剩下的残留只会在"上游重跑"时按 mtime 判过期，
        不会算错结果。
        """
        import shutil

        # ⚠️ 调用方 _apply_source 已保证有任务在身
        task_dir = self.store.task_dir(self.task_id)  # type: ignore[reportArgumentType]
        for name in (
            "pages.json",
            "runs.json",
            "boxes.json",
            "sizes.json",
            "print.json",
        ):
            try:
                (task_dir / name).unlink(missing_ok=True)
            except OSError:
                pass
        # ⚠️ **副本节点的同名副本一起删**（B 方案）：``pages~Node_3.json`` /
        #    ``boxes~Node_2.json`` / ``print~Node_2.json`` 都在任务**根**下，
        #    下面 rmtree 的 ``stages``/``drafts`` 收不到它们——留着就是"换完源
        #    文件，旧书的页清单与检测框在副本节点上复活"。
        for pattern in (
            "pages~*.json",
            "boxes~*.json",
            "sizes~*.json",
            "print~*.json",
            # 逐张参数/算法/执行记录都是按**旧书页名**记的，换源后一律作废
            "rembg_offsets*.json",
            "rembg_algorithms*.json",
            "rembg_methods*.json",
        ):
            for stale in task_dir.glob(pattern):
                try:
                    stale.unlink(missing_ok=True)
                except OSError:
                    pass
        for sub in (
            "stages",
            "drafts",
            # 去底色实时预览草稿（``preview/rembg[~节点]/``）按**旧书页名**命名，
            # 换源后不清就是"新书去底色页里冒出旧书的预览图"（用户 2026-11-04）。
            "preview",
        ):
            try:
                shutil.rmtree(task_dir / sub, ignore_errors=True)
            except OSError:
                pass
        # 缩略图缓存**整体作废**：它们全是由旧源派生的（源 PDF 页渲染
        # ``thumbnails/source``、入口图片 ``thumbnails/input``、去底色成品
        # ``thumbnails/print``、拼版合成 ``thumbnails/imposition_pages`` …），
        # 源一换就都不对了。页缓存按**页号**命名，跨书共用会串页（见 MEMORY
        # 「按页号命名的缓存不能跨书共用」）。
        # ⚠️ 目录名按**节点**分（``thumbnails/<名>[~<节点>]``，用户 2026-10-17），
        #    逐个点名删会漏掉副本节点的别名——整棵 ``thumbnails/`` 一起删才干净。
        try:
            shutil.rmtree(task_dir / "thumbnails", ignore_errors=True)
        except OSError:
            pass
        # ⚠️⚠️ **必须把"待写"标记也清掉**：``set_task`` 开头会
        #    ``_flush_param_drafts()`` / ``_flush_annotations()``（切任务前把
        #    用户最后 400ms 的输入、攒批的框与尺寸落盘）。那些暂存是**旧书**
        #    的，目录刚被删掉，这一 flush 又把它们写回来——等于"换完文件，
        #    旧书的参数与检测框复活了"。只删文件不清标记是半个修复。
        self._draft_dirty = {}
        self._pending_sizes = {}
        self._pending_boxes = {}
        # 预览器的内存态也要清，否则还指着旧书的第一页
        self.pages = []
        self.pdf_page_count = 0
        self.detect_cache.clear()
        # 换书/换清单后全书半幅基线作废（见 DetectMixin._refresh_detect_stats）
        self._half_width_median = None
        self._manual_stems = set()
