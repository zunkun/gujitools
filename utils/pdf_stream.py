# -*- coding: utf-8 -*-
"""让 fpdf 的输出**边写边落盘**，不再把整本 PDF 建在内存里。

背景（2026-09-26 实测，320 页 4900×4400 的扫描页）
    fpdf2 的 `output()` 走 `OutputProducer.bufferize()`：把**整本 PDF** 写进一个
    bytearray，最后一次 `write_bytes` 落盘（`fpdf.py:6535`）。于是 print 阶段的内存是
        图片缓存里的嵌入数据（≈ PDF 体积）+ 输出缓冲（≈ PDF 体积）= **≈ 2×PDF**
    实测：加载完 2644MB（其中 cache 2548MB），`output()` 期间峰值 **5146MB**。

解法
    `output(output_producer_class=...)` 是 fpdf 的**公开注入口**（`fpdf.py:6463`），
    而 `OutputProducer` 对 `self.buffer` 只有两种用法（全仓 grep 确认过）：
        - `self.buffer += data`（`output.py:1116`，唯一的写入路径）
        - `len(self.buffer)`（算对象偏移、startxref、分段统计）
    **从不切片读它**。所以把 buffer 换成一个"写文件 + 记长度"的假 buffer，
    输出就变成一路落盘：

        峰值 5146MB → **2819MB（−45%）**；`output()` 16.5s → **8.1s**（快一倍）
        **产物 SHA-256 完全相同**（逐字节一致，含 trailer 的 /ID）

⚠️ 两个必须处理的细节
    1. `fpdf._default_file_id()` 会拿**整个 buffer** 做 md5 算 trailer 的 /ID
       （`output.py:650`）——这是唯一真的把 buffer 当 bytes 用的地方。解法不是去改
       fpdf，而是**覆盖 `file_id()`**：fpdf 文档明说这个方法留给子类定义自定义 /ID
       （`fpdf.py:5869`）。假 buffer 维护一份**增量 md5**，增量算与全量算结果必然
       相同 → /ID 一字不差，产物仍然逐字节一致。
    2. 落盘走**临时文件 + `os.replace`**：中途失败/被杀不会留下半本 PDF 被用户
       点开（fpdf 原本的 `write_bytes` 是先截断再写，留得下坏文件）。

只给 `print` 用：它是唯一会把**整本大图**攒进 fpdf 的命令（extract/rembg 等
不经 fpdf 输出）。
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from fpdf import FPDF
from fpdf.output import OutputProducer

from utils.file_utils import replace_with_retry


class _SpoolToFile:
    """假装成 bytearray 的落盘缓冲：只支持 `+=` 与 `len()`。

    `OutputProducer` 对 `.buffer` 的需求就这两样（见模块文档），所以真的够用；
    多余的方法一律不实现——真被用到了会立刻 `AttributeError`，比悄悄返回错数据好。
    """

    __slots__ = ("_fh", "_size", "_md5")

    def __init__(self, path: Path) -> None:
        self._fh: BinaryIO = open(path, "wb")
        self._size = 0
        #: 增量 md5：fpdf 默认要对整个 buffer 做 md5，增量算结果相同（见模块文档）
        self._md5 = hashlib.md5()

    def __iadd__(self, data: bytes) -> "_SpoolToFile":
        """`output.py:1116 self.buffer += data + b"\\n"` —— 唯一的写入路径。"""
        self._fh.write(data)
        self._size += len(data)
        self._md5.update(data)
        return self

    def __len__(self) -> int:
        """算对象偏移、startxref、分段体积统计。"""
        return self._size

    def __bool__(self) -> bool:
        """`bufferize()` 开头 `assert not self.buffer`：还没写过内容时须为假。"""
        return self._size > 0

    def md5_copy(self):
        """当前已写内容的 md5 快照（trailer 的 /ID 用）。"""
        return self._md5.copy()

    def close(self) -> None:
        self._fh.close()


class PdfDocument(FPDF):
    """`print` 用的 FPDF：把 `/ID` 接到流式缓冲上（见模块文档细节 1）。

    没走流式输出时 `file_id()` 返回 -1，交回 fpdf 默认算法 —— 行为与直接用
    `FPDF` 完全一致，所以两条出口的产物可逐字节比对。
    """

    #: 流式输出时的假 buffer；None 表示本次输出没走流式
    _stream_spool: "_SpoolToFile | None" = None

    def file_id(self) -> "str | int":
        spool = self._stream_spool
        if spool is None:
            return -1
        digest = spool.md5_copy()
        if self.creation_date:
            digest.update(self.creation_date.strftime("%Y%m%d%H%M%S").encode("utf8"))
        hexed = digest.hexdigest().upper()
        return f"<{hexed}><{hexed}>"


class _StreamingOutputProducer(OutputProducer):
    """把 `OutputProducer` 的 bytearray 换成写文件的假 buffer，其余逻辑一字不改。"""

    def __init__(self, fpdf: FPDF, spool: _SpoolToFile) -> None:
        super().__init__(fpdf)
        self.buffer = spool  # type: ignore[assignment]
        # 让 PdfDocument.file_id() 能拿到增量摘要（趁 trailer 还没序列化）
        fpdf._stream_spool = spool  # type: ignore[attr-defined]


def write_streaming(pdf: PdfDocument, path: str | os.PathLike[str]) -> None:
    """把 pdf 边写边落盘到 path（先写 `.part` 再原子替换）。

    ⚠️ 同一个 pdf 只能输出一次：fpdf 的 `output()` 会把自己标成"已定稿"，再调
    会抛 `FPDFException`（这是 fpdf 原本就有的约束，不是本模块引入的）。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".part")
    # ⚠️ spool 由**这里**持有而不是 producer：`pdf.output()` 中途抛异常时
    #    producer 对象会被丢掉，句柄就没人关了（Windows 上文件仍被占用，
    #    unlink 也失败 → 残留 .part）。由本函数负责 finally 关闭。
    spool = _SpoolToFile(tmp)

    def _producer(fpdf: FPDF) -> OutputProducer:
        return _StreamingOutputProducer(fpdf, spool)

    try:
        # 不给 name：fpdf 就不会 write_bytes；落盘已经在 bufferize() 里做完了
        pdf.output(output_producer_class=_producer)
    except BaseException:
        spool.close()
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    spool.close()
    try:
        # Windows 上目标 PDF 可能正被阅读器打开（os.replace 会抛 PermissionError）；
        # 先短暂重试，真占用再给用户一句人话。
        replace_with_retry(tmp, target)
    except OSError as exc:
        # 最常见的原因是目标 PDF 正被阅读器打开（Windows 上会 PermissionError）。
        # 说人话，别让用户对着一句 WinError 猜。
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise OSError(
            f"PDF 已生成但无法覆盖 {target}：{exc}。"
            "若该文件正在 PDF 阅读器中打开，请关闭后重试。"
        ) from exc
