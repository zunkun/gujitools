# -*- coding: utf-8 -*-
"""拼版共享基元的**第四步取图来源刷新**分片。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from desktop.utils.files import dir_content_signature

from desktop.pages.taskdetail.imposition.helpers import _rect_of

if TYPE_CHECKING:
    from desktop.pages.taskdetail.imposition._host import ImpositionBaseHost
else:
    ImpositionBaseHost = object


class PrintSourceMixin(ImpositionBaseHost):
    """第四步取图目录的内容标记与待打印列表刷新。"""

    def _print_source_mark(self) -> tuple:
        """第四步取图目录的**内容标记**：``(目录, 目录内容指纹)``。

        ``_print_source_cache`` 存的就是它。⚠️ 判据必须带上**内容指纹**而不是
        只比目录字符串：拼版成品重合成后目录一个字没变、内容全换了，只比路径
        会让后台合成的收尾回调（``_on_imposition_composed``）把这次变化当成
        "来源没换"直接跳过，第四步的待打印列表就永远停在旧图上——用户
        2026-10-18 报的「拼版图片发生变化，PDF排版不能实时更新」正是这一条。
        """
        directory = self.print_source_dir()
        return (str(directory), dir_content_signature(directory))

    def _print_source_mark_text(self) -> str:
        """第四步取图目录的**内容标记**（可落进 ``runs.json`` 的文本形态）。

        与 :meth:`_print_source_mark` **同一份判据**（目录 + 内容指纹），只是换成
        字符串好进执行记录：第四步据此回答"磁盘上那份 PDF 还是不是当前取图目录
        的产物"（``services.stale_chain.print_input_changed``）。
        """
        directory, signature = self._print_source_mark()
        return f"{directory}|{signature}"

    def _refresh_print_source(self, only_paths=None) -> None:
        """第四步取图来源变了：让待打印列表跟上（拼版 ↔ 去底色 切换、成品重存）。

        ``only_paths``：**这次刚被重存的那几张成品图**（拼版合成收尾时给出）。
        给了它、而且第四步的条目清单没变（同样的图、同样的顺序与逐页坐标）时，
        只就地刷新那几条（缩略图 + 当前页显示），**不整列重建**——否则每改一次
        拼版都会把整张待打印列表清掉重来、把用户正看的那一页翻回第一页
        （用户 2026-10-18：「那张图片变更……同时通知下一步要变更的图片」）。
        清单结构变了（页数/顺序/逐页坐标）时仍走整列重建（``set_entries``）。

        ⚠️ **只作废缓存，不在原地重建**（2026-09-30 用户报「开关拼版后顶部
        空白/卡住 2s 才恢复」）：重建 = 缩略条清空 + 几十条重建 +
        ``_select_entry(0)`` **在 UI 线程同步解码整张首图**——真实任务上
        冻结 1-2s，流程条的新状态（虚线/绕行线）也跟着画不出来。而本方法的
        触发点（启用开关、后台合成完成、自动启用）都发生在**拼版详情里**，
        那一刻第四步根本不可见：进第四步时 ``_refresh_preview`` 本来就会
        重建一次，不怕漏。只有第四步**正被看着**（比如开关后停在第四步等
        后台合成收尾）才当场重建，否则用户会一直盯着旧来源。

        另做两件**不重**的事（它们只动按钮/提示，不碰列表）：
        1. 重算"取图来源已换"缓存（``_print_source_stale``）——本方法是拼版开关
           变化的统一出口，缓存必须在这儿跟上，否则状态行还按旧来源显示提示；
        2. 同步下载按钮：来源一换，磁盘上那份 PDF 就是旧数据，得灭掉
           （用户 2026-10-03："旧的数据不显示"）。
        """
        # 缓存与按钮先无条件跟上（都很轻，不碰列表）
        try:
            self._refresh_stale_notices()
        except Exception:  # noqa: BLE001 - 判定失败不该拦住开关生效
            pass
        preview = getattr(self, "print_preview", None)
        if preview is None or not self.task_id:
            return
        try:
            preview.set_pdf_path(self._current_print_pdf_path())
        except Exception:  # noqa: BLE001 - 第四步尚未就绪时不该拖垮拼版页
            pass
        # ⚠️ 比对的是**内容标记**（路径 + 指纹，见 ``_print_source_mark``）：
        #    用目录字符串的话，"同一个目录、内容刚被重合成换掉"会被判成"没变"
        #    而跳过重建——用户 2026-10-18 报的就是这个（拼版成品变了，PDF排版
        #    的图还是旧的）。
        mark = self._print_source_mark()
        if getattr(self, "_print_source_cache", None) == mark:
            return
        if self.preview_stack.currentIndex() != self.stack_index_of_step("print"):
            self._print_source_cache = None
            # 第四步不可见：状态行/主按钮高亮留给进第四步时的那次刷新
            return
        self._print_source_cache = mark
        try:
            entries, _doc = self._print_entries()
            # 条目清单没变（同样的图、同样的顺序与逐页坐标）→ 只刷那几张：
            # 不整列重建、不动当前页、不重解整条缩略图条。
            current = [
                (str(e.get("file")), _rect_of(e)) for e in preview.entries()
            ]
            fresh = [(str(e.get("file")), _rect_of(e)) for e in entries]
            if only_paths and fresh == current:
                preview.refresh_paths(only_paths)
            else:
                preview.set_entries(entries)
            self._refresh_stage_views()
        except Exception:  # noqa: BLE001 - 第四步尚未就绪时不该拖垮拼版页
            self._print_source_cache = None
            return
