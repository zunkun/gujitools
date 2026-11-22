# -*- coding: utf-8 -*-
"""共享文档缓存（本进程渲染兜底时才会真正用到；关文件句柄的唯一收口）。"""

from __future__ import annotations

import atexit
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 仅类型检查期导入：为共享文档缓存声明元素类型（运行期 fitz 惰性导入）
    import fitz

# --------------------------------------------------------------- 共享文档缓存
# ⚠️ **2026-10-21 起渲染已搬出 GUI 进程**（``pdf_render_service``）：子进程自己
#   ``fitz.open`` + 渲 + 关，本进程**不再**为了渲染而持有 PDF 句柄。
#
#   下面这套 LRU + 单飞锁保留给两类场景：
#   1. 子进程池起不来 / ``GUJI_PDF_RENDER=inproc`` 时的**进程内兜底**（渲染在
#      服务内部走 ``single_flight``，不经过这里的缓存）；
#   2. 仍然导出 ``close_cached_documents()``（删任务/关文档前调用）。现在缓存
#      常态为空，调用是空操作——但**不要删**：它是"关文件句柄"这条纪律的唯一
#      收口，将来若有人重新在 GUI 进程里开文档，删了就立刻复发 Windows
#      ``PermissionError``（rmtree 删不掉被占用的 PDF）。
#: 共享文档缓存的容量（本）。第二本是给放大弹窗换 PDF 场景的余量。
_PDF_DOC_CACHE_MAX = 2
#: 路径 → 已打开的 fitz.Document（LRU，最近用的在队尾）
_PDF_DOC_CACHE: "OrderedDict[str, fitz.Document]" = OrderedDict()
# 单页渲染的全局互斥锁（语义见 render_lock 模块说明）。
# ⚠️ 锁本体已挪到 `desktop/workers/render_lock.py`（零依赖小模块）：导入后台
# 任务与渲染服务也要共用同一把，而它们不能从本模块 import——那会把第四步预览
# 的整套依赖拖进启动路径（见 workers/__init__.py 的惰性导出）。
from desktop.workers.render_lock import single_flight  # noqa: E402  (位置即说明)


def close_cached_documents() -> None:
    """关掉共享文档缓存里的全部文档，释放 Windows 文件句柄。

    ⚠️ 删除任务/关闭文档前必须调用：缓存里的 Document 一直握着 PDF 文件，
    Windows 上不先关掉，`rmtree` 会一直 PermissionError（store 的重试兜底
    救不了"永远不关"的句柄）。会等到当前正在跑的那次渲染结束（≤几百 ms）。
    """
    with single_flight():
        while _PDF_DOC_CACHE:
            _key, document = _PDF_DOC_CACHE.popitem()
            try:
                document.close()
            except Exception:  # noqa: BLE001 - 关不掉就留给进程退出回收
                pass


# 解释器退出前把文档关干净：PyMuPDF 的 Document 活过 fitz 模块自身的
# 清理阶段会在 C 层崩（0xC0000409 之类），atexit 保证先于模块回收执行。
atexit.register(close_cached_documents)


def _get_shared_document(path: Path):
    """取（或打开）共享文档。**必须在 ``single_flight()`` 内调用**。

    fitz.Document 非线程安全，但"持锁串行使用"是安全的——同一时刻只有一个
    线程在碰它。命中缓存直接复用（这正是本缓存的意义：省掉每点一次就重新
    解析 832MB xref 的开销），未命中才打开并插入 LRU。
    """
    key = str(path)
    document = _PDF_DOC_CACHE.pop(key, None)
    if document is not None:
        _PDF_DOC_CACHE[key] = document  # 挪到队尾（最近使用）
        return document
    import fitz

    document = fitz.open(key)
    _PDF_DOC_CACHE[key] = document
    while len(_PDF_DOC_CACHE) > _PDF_DOC_CACHE_MAX:
        _old_key, old_document = _PDF_DOC_CACHE.popitem(last=False)
        try:
            old_document.close()
        except Exception:  # noqa: BLE001
            pass
    return document
